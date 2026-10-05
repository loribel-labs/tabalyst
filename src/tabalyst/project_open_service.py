# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Private first-open policy for an eventual Explore adapter (S18).

The decision is transient and advisory. A caller must retain it for an explicit
snapshot or rescan choice; every action revalidates the selected generation.
No CLI, public API, automatic scan or presentation is provided here.
"""

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tabalyst.errors import InputError
from tabalyst.project_scan_service import rescan_project
from tabalyst.projects._generation import GenerationConflictError
from tabalyst.projects._session import (
    ProjectSession,
    SessionAssessment,
    SessionRefusedError,
    inspect_project,
    open_project,
    requested_config_sha256,
)
from tabalyst.projects.location import StorageLocation
from tabalyst.scan_reuse import SourceState
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.identity import source_format_of

OpeningAction = Literal["open_current", "choose", "resolve_config"]


@dataclass(frozen=True)
class ProjectOpenDecision:
    storage_root: Path
    assessment: SessionAssessment
    action: OpeningAction
    choices: tuple[str, ...]


@dataclass(frozen=True)
class ProjectEntry:
    decision: ProjectOpenDecision
    session: ProjectSession | None


def _decision(
    location: StorageLocation, assessment: SessionAssessment
) -> ProjectOpenDecision:
    root = location.root.resolve()
    if assessment.errors:
        choices = ("use_recorded_config",)
        if (
            assessment.source_check is not None
            and assessment.source_check.state is not SourceState.MISSING
        ):
            choices += ("rescan",)
        return ProjectOpenDecision(root, assessment, "resolve_config", choices)
    if assessment.current_ready:
        return ProjectOpenDecision(
            root, assessment, "open_current", ("open_current", "rescan")
        )
    if assessment.source_check is None:
        return ProjectOpenDecision(
            root, assessment, "choose", ("snapshot", "reinspect")
        )
    if assessment.source_check.state is SourceState.MISSING:
        return ProjectOpenDecision(root, assessment, "choose", ("snapshot",))
    return ProjectOpenDecision(root, assessment, "choose", ("snapshot", "rescan"))


def _check_decision(
    location: StorageLocation, decision: ProjectOpenDecision
) -> SessionAssessment:
    if not isinstance(decision, ProjectOpenDecision):
        raise TypeError("A ProjectOpenDecision from inspection is required")
    assessment = decision.assessment
    if assessment.workspace_id != location.workspace_id:
        raise GenerationConflictError("Opening decision belongs to another workspace")
    if decision.storage_root != location.root.resolve():
        raise GenerationConflictError(
            "Opening decision belongs to another storage root"
        )
    if decision != _decision(location, assessment):
        raise ValueError("Inconsistent project opening decision")
    return assessment


def inspect_opening(
    location: StorageLocation,
    project_id: str,
    *,
    requested_config: ScanConfig | None = None,
) -> ProjectOpenDecision:
    """Inspect one verified project, without opening a query session or scanning."""
    return _decision(
        location,
        inspect_project(location, project_id, requested_config=requested_config),
    )


@contextmanager
def enter_project(
    location: StorageLocation,
    project_id: str,
    *,
    requested_config: ScanConfig | None = None,
):
    """Open a fresh source as current; return a decision for every other state."""
    decision = inspect_opening(location, project_id, requested_config=requested_config)
    if decision.action != "open_current":
        yield ProjectEntry(decision, None)
        return
    with ExitStack() as resources:
        try:
            session = resources.enter_context(
                open_project(
                    location,
                    project_id,
                    requested_config=requested_config,
                    expected_generation_id=decision.assessment.generation_id,
                )
            )
        except SessionRefusedError as exc:
            # The source changed between inspection and opening. Report the
            # newer assessment instead of yielding a stale current session.
            yield ProjectEntry(_decision(location, exc.assessment), None)
            return
        if session.assessment.source != decision.assessment.source:
            raise GenerationConflictError("Selected project source binding changed")
        yield ProjectEntry(_decision(location, session.assessment), session)


@contextmanager
def open_snapshot(location: StorageLocation, decision: ProjectOpenDecision):
    """Explicitly query the stored generation, carrying its warning and id."""
    assessment = _check_decision(location, decision)
    if "snapshot" not in decision.choices:
        raise InputError("Snapshot is not an available choice for this assessment")
    with open_project(
        location,
        assessment.project_id,
        intent="snapshot",
        expected_generation_id=assessment.generation_id,
    ) as session:
        if session.assessment.source != assessment.source:
            raise GenerationConflictError("Selected project source binding changed")
        yield session


@contextmanager
def rescan_from_decision(
    location: StorageLocation,
    decision: ProjectOpenDecision,
    *,
    config: ScanConfig | None = None,
    value_limit: int = 10000,
    intent: Literal["require_current", "snapshot"] = "require_current",
):
    """Explicitly rescan only the assessed project/source/generation."""
    assessment = _check_decision(location, decision)
    if "rescan" not in decision.choices:
        raise InputError("Rescan is not an available choice for this assessment")
    if decision.action == "resolve_config":
        if config is None or not isinstance(config, ScanConfig):
            raise InputError("A complete replacement ScanConfig is required")
        validated = ScanConfig.model_validate(
            config.model_dump(mode="json", by_alias=True)
        )
        if (
            requested_config_sha256(validated, source_format_of(Path(assessment.source)))
            != assessment.requested_config_sha256
        ):
            raise InputError("Replacement config differs from the inspected request")
    with rescan_project(
        location,
        assessment.project_id,
        expected_generation_id=assessment.generation_id,
        expected_source=Path(assessment.source),
        config=config,
        value_limit=value_limit,
        intent=intent,
    ) as result:
        yield result
