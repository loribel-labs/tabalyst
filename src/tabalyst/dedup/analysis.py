# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""First pass of Dedup over one CSV file: exact counts and record marks, no output (design dedup 8.4)."""

import dataclasses
import os
import stat
import time
import tracemalloc
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tabalyst.config import CsvConfig
from tabalyst.csv_records import CsvRecordError, open_records
from tabalyst.dedup.diskstore import MIB
from tabalyst.dedup.failures import DedupInputError
from tabalyst.dedup.groups import GroupStats, RecordMarks, count_rows
from tabalyst.dedup.settings import require_positive_int
from tabalyst.dedup.tiered import SpillEvent, TieredRowStore
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    byte_progress,
    emit_progress,
)

OutputKind = Literal["unique", "duplicates", "duplicates_all"]

# Names the pass in the progress lines, as the other commands name their stages.
STAGE = "Dedup"


@dataclass(frozen=True)
class SourceIdentity:
    """What the pass knew of the source: its size and time, and the SHA-256 of its bytes."""

    size_bytes: int
    mtime_ns: int
    content_sha256: str


@dataclass(frozen=True)
class DedupAnalysis:
    """The exact result of the first pass; the store behind it is already closed.

    ``stats`` and ``marks`` fix the content of every output (design dedup 8.4), so the
    second pass never needs the store. Nothing here holds a cell.
    """

    stats: GroupStats
    marks: RecordMarks
    source: SourceIdentity
    storage_mode: str
    """``"memory"``, or ``"disk"`` when the memory budget was passed."""
    spilled_at_record: int | None
    """Number of records read when the store moved to disk, ``None`` if it did not."""
    first_pass_seconds: float
    memory_peak_bytes: int | None
    """Peak of the Python allocations during the pass; ``None`` unless measured."""

    @property
    def outputs(self) -> tuple[OutputKind, ...]:
        """The CSV files the run writes (design dedup 6.2)."""
        return planned_outputs(self.stats)

    @property
    def passes(self) -> Literal[1, 2]:
        """One pass when there is no duplicate group, two when the outputs need a second."""
        return 2 if self.stats.duplicate_groups else 1


def planned_outputs(stats: GroupStats) -> tuple[OutputKind, ...]:
    """Zero, two or three outputs by the maximum frequency of a row (design dedup 6.2)."""
    if stats.duplicate_groups == 0:
        return ()
    if stats.max_occurrences >= 3:
        return ("unique", "duplicates", "duplicates_all")
    return ("unique", "duplicates")


def expected_rows(stats: GroupStats, kind: OutputKind) -> int:
    """Data rows that the output ``kind`` must hold (design dedup 12.3)."""
    if kind == "unique":
        return stats.distinct
    if kind == "duplicates":
        return stats.duplicate_groups
    return stats.duplicate_group_occurrences


def analyze_dedup(
    source: str | Path,
    *,
    csv: CsvConfig,
    max_rows: int,
    memory_budget_mb: int,
    temp_dir: Path | None,
    on_progress: ProgressCallback | None = None,
    measure_memory: bool = False,
) -> DedupAnalysis:
    """Read ``source`` once and count its duplicate groups exactly, writing nothing.

    The rows are compared whole, without normalization. The store starts in memory
    and moves to a temporary SQLite database under ``temp_dir`` when its accounted
    bytes pass ``memory_budget_mb`` MiB; the database is deleted whatever happens.
    The SHA-256 of the file comes from the same reading.

    Raises ``DedupInputError`` for an unreadable or malformed source
    (``invalid_csv``, ``encoding_error``, ``source_unreadable``), for more than
    ``max_rows`` data records (``row_limit_exceeded``, at record ``max_rows + 1``)
    and for a source whose size or time changed during the pass
    (``source_changed``); ``DedupReportError`` for a storage failure.
    ``ConfigurationError`` if ``max_rows`` or ``memory_budget_mb`` is below 1.
    ``measure_memory`` traces the Python allocations (slow: ``--verbose`` only).
    """
    require_positive_int("max_rows", max_rows)
    require_positive_int("memory_budget_mb", memory_budget_mb)
    path = Path(source)
    started = time.perf_counter()
    before = stat_source(path)
    forward = _staged(on_progress)
    spilled_at: int | None = None

    def spilled(event: SpillEvent) -> None:
        nonlocal spilled_at
        spilled_at = event.records
        emit_progress(
            forward,
            path,
            ProgressPhase.READING,
            detail=(
                f"memory budget reached at record {event.records:,}, "
                "continuing on disk"
            ),
        )

    store = TieredRowStore(memory_budget_mb * MIB, temp_dir, on_spill=spilled)
    with _peak_memory(measure_memory) as peak:
        try:
            with open_records(
                path,
                csv,
                hash_content=True,
                on_bytes=byte_progress(forward, path, before.st_size),
            ) as records:
                result = count_rows(records, store, max_rows=max_rows)
                digest = records.content_digest()
                bytes_read = records.bytes_read
            storage_mode = store.storage_mode
        except CsvRecordError as exc:
            # A file rewritten during the read often looks malformed: say what changed.
            if stat_differs(before, stat_source(path)):
                raise source_changed_error(exc.records_read) from exc
            message = (
                "The source cannot be opened or read."
                if exc.kind == "source_unreadable"
                else str(exc)
            )
            raise DedupInputError(
                message, reason=exc.kind, records_read=exc.records_read
            ) from exc
        finally:
            store.close()
    if stat_differs(before, stat_source(path)) or bytes_read != before.st_size:
        raise source_changed_error(result.stats.total)
    return DedupAnalysis(
        stats=result.stats,
        marks=result.marks,
        source=SourceIdentity(before.st_size, before.st_mtime_ns, digest),
        storage_mode=storage_mode,
        spilled_at_record=spilled_at,
        first_pass_seconds=time.perf_counter() - started,
        memory_peak_bytes=peak.value,
    )


def stat_source(path: Path) -> os.stat_result:
    # The messages of a failure carry no path: the report that holds them has none (12.1).
    try:
        status = path.stat()
    except OSError as exc:
        raise DedupInputError(
            "The source does not exist or cannot be read.", reason="source_unreadable"
        ) from exc
    if not stat.S_ISREG(status.st_mode):
        raise DedupInputError("The source is not a file.", reason="source_unreadable")
    return status


def stat_differs(before: os.stat_result, after: os.stat_result) -> bool:
    return (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)


def source_changed_error(records_read: int) -> DedupInputError:
    return DedupInputError(
        "The source changed while it was being read.",
        reason="source_changed",
        records_read=records_read,
    )


def _staged(callback: ProgressCallback | None) -> ProgressCallback | None:
    """Name the stage on every event that the pass emits."""
    if callback is None:
        return None

    def forward(event: ProgressEvent) -> None:
        callback(dataclasses.replace(event, stage=STAGE))

    return forward


@dataclass
class _Peak:
    value: int | None = None


@contextmanager
def _peak_memory(enabled: bool) -> Iterator[_Peak]:
    """Peak of the traced Python allocations of the block, ``None`` when not enabled.

    ``tracemalloc`` does not see the page cache of SQLite, which the memory budget
    bounds on its own, so the figure is a measure of the Python side only.
    """
    peak = _Peak()
    if not enabled:
        yield peak
        return
    already = tracemalloc.is_tracing()
    if already:
        tracemalloc.reset_peak()
    else:
        tracemalloc.start()
    try:
        yield peak
    finally:
        peak.value = tracemalloc.get_traced_memory()[1]
        if not already:
            tracemalloc.stop()
