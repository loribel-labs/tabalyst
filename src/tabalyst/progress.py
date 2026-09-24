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


ProgressCallback = Callable[[ProgressEvent], None]


def emit_progress(
    callback: ProgressCallback | None,
    source: Path,
    phase: ProgressPhase,
    *,
    index: int | None = None,
    total: int | None = None,
    detail: str | None = None,
) -> None:
    if callback is not None:
        callback(
            ProgressEvent(
                source=source,
                phase=phase,
                index=index,
                total=total,
                detail=detail,
            )
        )
