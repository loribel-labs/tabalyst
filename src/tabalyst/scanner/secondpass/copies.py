# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second-pass count of the extra copies of rows: Dedup's engine in count-only mode (design 20.40)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tabalyst.config import CsvConfig
from tabalyst.progress import ProgressCallback
from tabalyst.scanner.models import DatasetResult, Limited, ScanResult
from tabalyst.scanner.planner.models import Candidate
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import AnalysisStatus, DuplicateRowsResult
from tabalyst.source_guard import SourceGuard, StaleSource

# Why a count stopped, as the ceiling that stopped it (the codes of ``AnalysisResult.reason``).
_DETAIL = {
    "memory_budget": "the table of distinct rows passed deep.copies.memory_mb and the disk is off",
    "disk_budget": "the database of distinct rows passed deep.copies.disk_mb",
    "row_limit": "the file has more records than deep.copies.max_rows",
}


@dataclass(frozen=True)
class CopiesOutcome:
    """The end of a count: ``complete`` with the exact figures, or ``limited`` with the
    ceiling that stopped it."""

    status: AnalysisStatus
    result: DuplicateRowsResult
    reason: str | None = None
    detail: str | None = None


def count_copies(
    candidate: Candidate,
    scan: ScanResult,
    dataset: DatasetResult,
    source: Path,
    on_progress: ProgressCallback | None = None,
) -> CopiesOutcome:
    """Count the extra copies of the rows of ``source`` with the ceilings the plan wrote.

    Reads the file once, on its own, whatever the workers of the run: the count is the one of
    ``tabalyst dedup`` for the same file. Raises ``ScanMismatch`` when the count contradicts
    the Scan (another number of records, fewer copies than the Scan's lower bound),
    ``StaleSource`` when the file is not the one the Scan read, and ``DedupInputError`` or
    ``DedupReportError`` for a file Dedup cannot read.
    """
    # Imported here: Dedup imports the services, which import this package.
    from tabalyst.dedup.count_only import CopyLimits, count_extra_copies
    from tabalyst.dedup.failures import DedupInputError

    info = scan.source.csv
    if scan.source.format != "csv" or info is None:
        raise ScanMismatch("rows are counted for a CSV source only")
    parameters = candidate.parameters
    limits = CopyLimits(
        max_rows=int(parameters["max_rows"]),
        memory_budget_mb=int(parameters["memory_mb"]),
        disk_budget_mb=int(parameters["disk_mb"]),
    )
    guard = SourceGuard(source, scan.source)
    guard.before()
    csv = CsvConfig(encoding=scan.source.encoding or "utf-8-sig", delimiter=info.delimiter)
    try:
        found = count_extra_copies(source, csv=csv, limits=limits, on_progress=on_progress)
    except DedupInputError as exc:
        if exc.reason == "source_changed":
            raise StaleSource(
                f"{source.name} changed while it was read. Run tabalyst scan {source} again."
            ) from exc
        raise
    exact = found.status == "exact"
    if exact:
        assert found.content_sha256 is not None
        guard.finish(found.content_sha256, found.bytes_read)
        if found.records_read != dataset.record_count:
            raise ScanMismatch(
                f"records: the second pass read {found.records_read}, the scan {dataset.record_count}"
            )
        # A stopped count covers a part of the file, which the Scan's bound need not fit.
        stated = dataset.records.duplicates.count
        if isinstance(stated, Limited):
            # ``IntMeasure`` is built by a function, which mypy cannot narrow.
            proved = stated.lower_bound or 0  # type: ignore[attr-defined]
            if proved > found.extra_copies:
                raise ScanMismatch(
                    f"extra copies: the second pass found {found.extra_copies}, "
                    f"fewer than the {proved} the scan proved"
                )
    result = DuplicateRowsResult(
        accuracy="exact" if exact else "lower_bound",
        identity=found.identity,  # type: ignore[arg-type]  # the one identity of Dedup
        calculation_version=found.calculation_version,
        records=found.records_read,
        distinct_rows=found.distinct_rows,
        extra_copies=found.extra_copies,
        duplicate_groups=found.duplicate_groups,
        storage=found.storage_mode,  # type: ignore[arg-type]  # "memory" or "disk"
        source_sha256=found.content_sha256,
    )
    if exact:
        return CopiesOutcome("complete", result)
    assert found.reason is not None
    return CopiesOutcome(
        "limited",
        result,
        reason=found.reason,
        detail=f"stopped after {found.records_read} records: {_DETAIL[found.reason]}",
    )
