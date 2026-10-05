# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Private point-in-time readiness and exposure-aware pinned query sessions (S17).

Opening never scans, publishes or consults the source index. Source checks are
observations, not continuous validity guarantees; refresh keeps the same Scan.
"""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from tabalyst._version import __version__
from tabalyst.errors import InputError
from tabalyst.projects import _queries
from tabalyst.projects._generation import (
    GenerationConflictError,
    PinnedGeneration,
    open_generation,
)
from tabalyst.projects._query_budget import QueryBudget
from tabalyst.projects.location import StorageLocation
from tabalyst.scan_reuse import SourceCheck, SourceState, compare_source
from tabalyst.scanner.config import ScanConfig, config_sha256, resolve_config_defaults

OpenIntent = Literal["require_current", "snapshot"]


@dataclass(frozen=True)
class SessionAssessment:
    workspace_id: str
    project_id: str
    generation_id: str
    source: Path
    checked_at: datetime
    source_check: SourceCheck | None
    source_error: str | None
    recorded_config_sha256: str
    requested_config_sha256: str | None
    current_ready: bool
    snapshot_ready: bool
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


class SessionRefusedError(InputError):
    """A valid pinned generation cannot satisfy the requested opening intent."""

    def __init__(self, intent: OpenIntent, assessment: SessionAssessment):
        self.assessment = assessment
        self.code = "session_not_ready"
        reasons = assessment.errors
        if intent == "require_current":
            reasons += assessment.warnings
        super().__init__(f"Cannot open project with {intent}: {', '.join(reasons)}")


def _requested_config(config: ScanConfig | None) -> ScanConfig | None:
    if config is None:
        return None
    if not isinstance(config, ScanConfig):
        raise TypeError("requested_config must be a complete ScanConfig")
    # Revalidate even a model constructed/modified without Pydantic validation.
    return ScanConfig.model_validate(config.model_dump(mode="json", by_alias=True))


def requested_config_sha256(config: ScanConfig, source_format) -> str:
    """The hash a scan of ``source_format`` with ``config`` would record."""
    return config_sha256(resolve_config_defaults(config, source_format))


def _assess(
    pinned: PinnedGeneration, requested: ScanConfig | None
) -> SessionAssessment:
    requested_hash = (
        None
        if requested is None
        else requested_config_sha256(requested, pinned.result.source.format)
    )
    source = Path(pinned.project.source.path)
    check, error = None, None
    warnings: tuple[str, ...] = ()
    try:
        check = compare_source(source, pinned.result.source)
    except InputError as exc:
        error = str(exc)
        warnings = ("source_check_failed",)
    else:
        if check.state is SourceState.STALE:
            warnings = ("source_stale",)
        elif check.state is SourceState.MISSING:
            warnings = ("source_not_checked",)
    if pinned.result.engine.version != __version__:
        warnings += ("engine_version_changed",)
    recorded_hash = pinned.result.config_sha256
    errors = (
        ("config_mismatch",)
        if requested_hash is not None and requested_hash != recorded_hash
        else ()
    )
    return SessionAssessment(
        pinned.project.workspace_id,
        pinned.project.project_id,
        pinned.generation_id,
        source,
        datetime.now(UTC),
        check,
        error,
        recorded_hash,
        requested_hash,
        not errors and not warnings,
        not errors,
        warnings,
        errors,
    )


def _expect(pinned: PinnedGeneration, expected_generation_id: str | None) -> None:
    if (
        expected_generation_id is not None
        and pinned.generation_id != expected_generation_id
    ):
        raise GenerationConflictError(
            "Selected project generation changed since inspection"
        )


def inspect_project(
    location: StorageLocation,
    project_id: str,
    *,
    requested_config: ScanConfig | None = None,
    expected_generation_id: str | None = None,
    budget: QueryBudget | None = None,
) -> SessionAssessment:
    """Verify, assess and close. Returned readiness is advisory after closing.

    Integrity/legacy failures raise through open_generation; snapshot has no
    bypass. Legacy failures explicitly require rebuilding from the source.
    """
    requested = _requested_config(requested_config)
    with open_generation(location, project_id, budget=budget) as pinned:
        _expect(pinned, expected_generation_id)
        return _assess(pinned, requested)


class ProjectSession:
    """Owned by open_project; assessment refresh never changes the generation.

    Readiness governs entry. A later refresh reports changed source facts while
    existing queries still describe the stored generation, including cursors.
    """

    def __init__(self, pinned, assessment, resources, intent, requested=None):
        self._pinned = pinned
        self._requested = requested
        self._assessment = assessment
        self._materializations: set[ExitStack] = set()
        resources.callback(self._close_queries)
        self._closed = False
        self.intent = intent

    @property
    def assessment(self) -> SessionAssessment:
        return self._assessment

    @property
    def generation_id(self) -> str:
        return self._assessment.generation_id

    def _require_open(self):
        if self._closed:
            raise InputError("Project session is closed")

    def _close_queries(self):
        with ExitStack() as closing:
            for owned in self._materializations:
                closing.callback(owned.close)
            self._materializations.clear()

    def refresh_assessment(self) -> SessionAssessment:
        self._require_open()
        self._assessment = _assess(self._pinned, self._requested)
        return self._assessment

    def records_page(self, dataset_id, listing_id, *, size=100, cursor=None):
        self._require_open()
        return _queries.records_page(
            self._pinned, dataset_id, listing_id, size=size, cursor=cursor
        )

    @contextmanager
    def materialize_values(self, dataset_id, field_id, *, budget=None):
        self._require_open()
        # Session teardown also closes a materialization whose caller still
        # holds its context. ExitStack.close is idempotent at either boundary.
        with ExitStack() as owned:
            self._materializations.add(owned)
            try:
                query = owned.enter_context(
                    _queries.materialize_values(
                        self._pinned, dataset_id, field_id, budget=budget
                    )
                )
                yield query
            finally:
                self._materializations.discard(owned)


@contextmanager
def open_project(
    location: StorageLocation,
    project_id: str,
    *,
    intent: OpenIntent = "require_current",
    requested_config: ScanConfig | None = None,
    expected_generation_id: str | None = None,
    budget: QueryBudget | None = None,
):
    """Reverify and reassess a selected generation before yielding queries."""
    if intent not in ("require_current", "snapshot"):
        raise ValueError("Unknown project opening intent")
    requested = _requested_config(requested_config)
    with open_generation(location, project_id, budget=budget) as pinned:
        _expect(pinned, expected_generation_id)
        assessment = _assess(pinned, requested)
        ready = (
            assessment.current_ready
            if intent == "require_current"
            else assessment.snapshot_ready
        )
        if not ready:
            raise SessionRefusedError(intent, assessment)
        with ExitStack() as resources:
            session = ProjectSession(pinned, assessment, resources, intent, requested)
            try:
                yield session
            finally:
                session._closed = True
