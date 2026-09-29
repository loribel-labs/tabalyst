"""Internal source-to-project service with revision-2 atomic publication.

The manifest replacement commits the scan/database pair. A failed first scan
stays invisible; a failed rescan preserves the previous committed generation.
No CLI or public tabalyst API is exposed here.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from tabalyst.errors import InputError
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.projects._publication import PublishedGeneration, publish_scan
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner.config import resolve_scan_config
from tabalyst.service import ConfigPath, _config_paths

ProjectScan = PublishedGeneration


def scan_project(
    source: str | Path,
    *,
    location: StorageLocation | None = None,
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
    config = resolve_scan_config(
        _config_paths(config_path),
        delimiter=delimiter,
        encoding=encoding,
        collections=collections,
    )

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
