# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Count-only mode of Dedup: the exact count of the extra copies of rows, with ceilings and no output."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tabalyst.config import CsvConfig
from tabalyst.csv_records import CsvRecordError, open_records
from tabalyst.dedup.analysis import (
    source_changed_error,
    staged,
    stat_differs,
    stat_source,
)
from tabalyst.dedup.calculation import CALCULATION_VERSION
from tabalyst.dedup.diskstore import MIB
from tabalyst.dedup.failures import DedupInputError
from tabalyst.dedup.groups import GroupCounters
from tabalyst.dedup.identity import IDENTITY, canonical_key
from tabalyst.dedup.settings import require_positive_int
from tabalyst.dedup.store import ExactRowStore, MemoryRowStore
from tabalyst.dedup.tiered import TieredRowStore, estimate_disk_bytes
from tabalyst.errors import ConfigurationError
from tabalyst.progress import ProgressCallback, byte_progress

CopyStatus = Literal["exact", "limited"]
LimitReason = Literal["memory_budget", "disk_budget", "row_limit"]


@dataclass(frozen=True)
class CopyLimits:
    """The ceilings of one count, all deterministic (they never depend on a clock).

    ``memory_budget_mb`` is the accounted size of the table of distinct rows, as for
    ``tabalyst dedup``. ``disk_budget_mb`` is the estimated size of the temporary
    database that takes over when the table passes it; ``0`` forbids the disk, so the
    count stops at the memory budget. ``max_rows`` is the number of records read.
    """

    max_rows: int
    memory_budget_mb: int
    disk_budget_mb: int
    temp_dir: Path | None = None


@dataclass(frozen=True)
class CopyCount:
    """What a count-only run proves about the rows of a CSV file.

    ``exact`` counts every record of the file. ``limited`` stopped at a ceiling after
    ``records_read`` records: ``extra_copies`` and ``duplicate_groups`` are then lower
    bounds of the file's, ``distinct_rows`` is the number of distinct rows among the
    records read. ``content_sha256`` is the digest of the whole file and is only known
    when the reading went to its end.
    """

    status: CopyStatus
    records_read: int
    distinct_rows: int
    extra_copies: int
    duplicate_groups: int
    reason: LimitReason | None
    content_sha256: str | None
    bytes_read: int
    storage_mode: str
    seconds: float
    identity: str = IDENTITY
    calculation_version: int = CALCULATION_VERSION


def count_extra_copies(
    source: str | Path,
    *,
    csv: CsvConfig,
    limits: CopyLimits,
    on_progress: ProgressCallback | None = None,
) -> CopyCount:
    """Read ``source`` once and count its extra copies of rows, writing nothing.

    The rows are compared as ``tabalyst dedup`` compares them (``full_decoded_csv_row_v1``,
    whole and without normalization), so an ``exact`` result equals ``extra_copies`` of
    ``dedup_csv``. The ceilings stop the reading cleanly: the copies met so far are a lower
    bound, never a count. The temporary database, if any, is deleted whatever happens and
    no other file is created.

    Raises ``DedupInputError`` for an unreadable or malformed source (``invalid_csv``,
    ``encoding_error``, ``source_unreadable``) and for a source whose size or time changed
    during the reading (``source_changed``); ``DedupReportError`` for a storage failure.
    ``ConfigurationError`` if a ceiling is below its minimum.
    """
    require_positive_int("max_rows", limits.max_rows)
    require_positive_int("memory_budget_mb", limits.memory_budget_mb)
    if limits.disk_budget_mb < 0:
        raise ConfigurationError("disk_budget_mb must be 0 or more.")
    path = Path(source)
    started = time.perf_counter()
    before = stat_source(path)
    forward = staged(on_progress)
    memory_bytes = limits.memory_budget_mb * MIB
    disk_bytes = limits.disk_budget_mb * MIB
    store: ExactRowStore
    if disk_bytes:
        store = TieredRowStore(memory_bytes, limits.temp_dir)
    else:
        store = MemoryRowStore()
    counters = GroupCounters()
    key_bytes = 0
    distinct = 0
    reason: LimitReason | None = None
    digest: str | None = None
    try:
        with open_records(
            path,
            csv,
            hash_content=True,
            on_bytes=byte_progress(forward, path, before.st_size),
        ) as records:
            for position, row in enumerate(records):
                if position >= limits.max_rows:
                    reason = "row_limit"
                    break
                key = canonical_key(row)
                occurrence = store.observe(key, position)
                counters.update(occurrence.count)
                if occurrence.count != 1:
                    continue
                key_bytes += len(key)
                distinct += 1
                if isinstance(store, MemoryRowStore):
                    if store.accounted_bytes > memory_bytes:
                        reason = "memory_budget"
                        break
                elif store.storage_mode == "disk" and (
                    estimate_disk_bytes(key_bytes, distinct) > disk_bytes
                ):
                    reason = "disk_budget"
                    break
            if reason is None:
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
    stats = counters.stats()
    stats.check()
    if stat_differs(before, stat_source(path)) or (
        reason is None and bytes_read != before.st_size
    ):
        raise source_changed_error(stats.total)
    return CopyCount(
        status="exact" if reason is None else "limited",
        records_read=stats.total,
        distinct_rows=stats.distinct,
        extra_copies=stats.extra_copies,
        duplicate_groups=stats.duplicate_groups,
        reason=reason,
        content_sha256=digest,
        bytes_read=bytes_read,
        storage_mode=storage_mode,
        seconds=time.perf_counter() - started,
    )
