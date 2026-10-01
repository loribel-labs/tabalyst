"""Progress events shared by the engine and its presentation adapters."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class ProgressPhase(StrEnum):
    READING = "reading"
    ANALYZING = "analyzing"
    RENDERING = "rendering"
    WRITING = "writing"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(frozen=True)
class ProgressEvent:
    source: Path
    phase: ProgressPhase
    index: int | None = None
    total: int | None = None
    detail: str | None = None
    # Reading progress of sources that report it: bytes read and file size.
    bytes_read: int | None = None
    bytes_total: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]


def emit_progress(
    callback: ProgressCallback | None,
    source: Path,
    phase: ProgressPhase,
    *,
    index: int | None = None,
    total: int | None = None,
    detail: str | None = None,
    bytes_read: int | None = None,
    bytes_total: int | None = None,
) -> None:
    if callback is not None:
        callback(
            ProgressEvent(
                source=source,
                phase=phase,
                index=index,
                total=total,
                detail=detail,
                bytes_read=bytes_read,
                bytes_total=bytes_total,
            )
        )


# Reading progress is reported at most once per percent of the source, and
# never more often than every MiB.
_BYTE_PROGRESS_MIN_STEP = 1 << 20


def byte_progress(
    callback: ProgressCallback | None, source: Path, total: int
) -> Callable[[int], None] | None:
    """A callback for the reader that reports the bytes read so far, or
    ``None`` when nobody listens."""
    if callback is None:
        return None
    step = max(_BYTE_PROGRESS_MIN_STEP, total // 100)
    next_report = step

    def report(bytes_read: int) -> None:
        nonlocal next_report
        if bytes_read >= next_report:
            next_report = bytes_read + step
            emit_progress(
                callback,
                source,
                ProgressPhase.READING,
                bytes_read=bytes_read,
                bytes_total=max(total, bytes_read),
            )

    return report
