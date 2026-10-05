# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Internal source-to-project service with revision-2 atomic publication.

The manifest replacement commits the scan/database pair. A failed first scan
stays invisible; a failed rescan preserves the previous committed generation.
No CLI or public tabalyst API is exposed here.
"""

from collections.abc import Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tabalyst.errors import InputError, ReportError
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.projects._publication import (
    PublishedGeneration,
    publish_scan,
    publish_selected_scan,
)
from tabalyst.projects._session import ProjectSession, open_project
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.config import resolve_scan_config
from tabalyst.service import ConfigPath, _config_paths

ProjectScan = PublishedGeneration


def scan_project(
    source: str | Path,
    *,
    location: StorageLocation | None = None,
    config: ScanConfig | None = None,
    config_path: ConfigPath | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
    on_progress: ProgressCallback | None = None,
    workers: int | None = None,
    now: datetime | None = None,
) -> ProjectScan:
    """Explicitly scan/rebuild one source and commit one immutable generation."""
    source = Path(source)
    if not source.is_file():
        raise InputError(f"Source does not exist or is not a file: {source}")
    location = location or StorageLocation.local()
    if config is None:
        config = resolve_scan_config(
            _config_paths(config_path),
            delimiter=delimiter,
            encoding=encoding,
            collections=collections,
        )
    elif config_path is not None or any(
        value is not None for value in (delimiter, encoding, collections)
    ):
        raise ValueError("A complete config cannot be combined with config overrides")

    def forward(event: ProgressEvent):
        if on_progress is not None and event.phase != ProgressPhase.COMPLETE:
            on_progress(
                ProgressEvent(
                    source=event.source,
                    phase=event.phase,
                    index=1,
                    total=1,
                    detail=event.detail,
                    bytes_read=event.bytes_read,
                    bytes_total=event.bytes_total,
                )
            )

    try:
        outcome = publish_scan(
            source, location, config, workers=workers, now=now, on_progress=forward
        )
    except BaseException as exc:
        emit_progress(
            on_progress, source, ProgressPhase.FAILED, index=1, total=1, detail=str(exc)
        )
        raise
    emit_progress(on_progress, source, ProgressPhase.COMPLETE, index=1, total=1)
    return outcome


@dataclass(frozen=True)
class ProjectRescan:
    """A committed publication and its separately verified live reader."""

    published: PublishedGeneration
    session: ProjectSession


class CommittedRescanOpenError(ReportError):
    """The rescan committed, but opening its newly selected generation failed."""

    def __init__(self, published: PublishedGeneration, cause: BaseException):
        self.published = published
        self.cause = cause
        super().__init__(
            f"Project {published.project.project_id} committed generation "
            f"{published.project.generation.id}, but reopening failed: {cause}"
        )


@contextmanager
def rescan_project(
    location: StorageLocation,
    project_id: str,
    *,
    expected_generation_id: str,
    expected_source: str | Path,
    config: ScanConfig | None = None,
    value_limit: int = 10000,
    intent: str = "require_current",
    workers: int | None = None,
    now: datetime | None = None,
    on_progress: ProgressCallback | None = None,
):
    """Explicitly replace one selected project and open only that new generation.

    The caller's generation and source preconditions come from inspection.
    `config=None` retains its recorded ScanConfig. A smaller stored-value limit
    is an explicit opt-in; there is no inferred cap from previous metadata.
    Publication completes before a new, independently verified reader opens.
    A post-commit open failure carries the committed result to avoid ambiguity.
    """
    if intent not in ("require_current", "snapshot"):
        raise ValueError("Unknown project opening intent")
    source = Path(expected_source)

    def forward(event: ProgressEvent):
        if on_progress is not None and event.phase not in (
            ProgressPhase.COMPLETE,
            ProgressPhase.FAILED,
        ):
            on_progress(
                ProgressEvent(
                    source=event.source,
                    phase=event.phase,
                    index=1,
                    total=1,
                    detail=event.detail,
                    bytes_read=event.bytes_read,
                    bytes_total=event.bytes_total,
                )
            )

    def failed(exc: BaseException):
        # Diagnostics must not hide whether a publication committed.
        with suppress(BaseException):
            emit_progress(
                on_progress,
                source,
                ProgressPhase.FAILED,
                index=1,
                total=1,
                detail=str(exc),
            )

    try:
        published = publish_selected_scan(
            location,
            project_id,
            expected_generation_id=expected_generation_id,
            expected_source=source,
            config=config,
            value_limit=value_limit,
            workers=workers,
            now=now,
            on_progress=forward,
        )
    except BaseException as exc:
        failed(exc)
        raise
    opened = None
    session = None
    try:
        opened = open_project(
            location,
            project_id,
            intent=intent,
            expected_generation_id=published.project.generation.id,
        )
        session = opened.__enter__()
        emit_progress(on_progress, source, ProgressPhase.COMPLETE, index=1, total=1)
    except BaseException as exc:
        if session is not None:
            opened.__exit__(type(exc), exc, exc.__traceback__)
        failed(exc)
        raise CommittedRescanOpenError(published, exc) from exc
    try:
        yield ProjectRescan(published, session)
    except BaseException as exc:
        opened.__exit__(type(exc), exc, exc.__traceback__)
        raise
    else:
        opened.__exit__(None, None, None)
