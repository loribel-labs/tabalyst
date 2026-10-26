# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second-pass count of the copies of the rows that have no ID: the light mode of the engine of
Dedup (design 20.43)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tabalyst.config import CsvConfig
from tabalyst.progress import ProgressCallback
from tabalyst.scanner.models import DatasetResult, ScanResult
from tabalyst.scanner.planner.models import Candidate
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import (
    AnalysisStatus,
    MissingIdColumn,
    MissingIdCopiesResult,
)
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.source_guard import SourceGuard, StaleSource

# Why a count stopped, as the ceiling that stopped it (the codes of ``AnalysisResult.reason``).
_DETAIL = {
    "memory_budget": "the table of the rows without an ID passed deep.copies.memory_mb and the disk is off",
    "disk_budget": "the database of the rows without an ID passed deep.copies.disk_mb",
    "row_limit": "the file has more records than deep.copies.max_rows",
}


@dataclass(frozen=True)
class MissingCopiesOutcome:
    """The end of a count: ``complete`` with the exact figures, or ``limited`` with the ceiling that
    stopped it."""

    status: AnalysisStatus
    result: MissingIdCopiesResult
    reason: str | None = None
    detail: str | None = None


def count_missing_copies(
    candidate: Candidate,
    scan: ScanResult,
    dataset: DatasetResult,
    source: Path,
    on_progress: ProgressCallback | None = None,
) -> MissingCopiesOutcome:
    """Count the copies of the rows that lack a value in each column the plan named.

    Reads the file once, on its own, whatever the workers of the run. A cell holds a value when the
    Scan counted it in ``values.count``: the same classifier and null markers, replayed. Raises
    ``ScanMismatch`` when the count contradicts the Scan (another number of records, another number
    of rows without a value in a column), ``StaleSource`` when the file is not the one the Scan read,
    and ``DedupInputError`` or ``DedupReportError`` for a file Dedup cannot read.
    """
    # Imported here: Dedup imports the services, which import this package.
    from tabalyst.dedup.count_only import CopyLimits, IdColumn, count_missing_id_copies
    from tabalyst.dedup.failures import DedupInputError

    info = scan.source.csv
    if scan.source.format != "csv" or info is None:
        raise ScanMismatch("the copies of rows are counted for a CSV source only")
    parameters = candidate.parameters
    named: list[tuple[str, int]] = [
        (str(name), int(position)) for name, position in json.loads(str(parameters["columns"]))
    ]
    fields = {field.id: field for field in dataset.fields}
    if not named or any(name not in fields for name, _ in named):
        raise ScanMismatch("the plan names a column the scan does not hold")
    limits = CopyLimits(
        max_rows=int(parameters["max_rows"]),
        memory_budget_mb=int(parameters["memory_mb"]),
        disk_budget_mb=int(parameters["disk_mb"]),
    )
    guard = SourceGuard(source, scan.source)
    guard.before()
    csv = CsvConfig(encoding=scan.source.encoding or "utf-8-sig", delimiter=info.delimiter)
    category = CellReader(scan.config).strings.category
    columns = tuple(IdColumn(name, position - 1) for name, position in named)
    try:
        found = count_missing_id_copies(
            source,
            csv=csv,
            limits=limits,
            columns=columns,
            is_present=lambda cell: category(cell) == "content",
            on_progress=on_progress,
        )
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
        for column in found.columns:
            stated = dataset.record_count - fields[column.key].values.count
            if column.rows_without_id != stated:
                raise ScanMismatch(
                    f"{column.key}: the second pass found {column.rows_without_id} records without "
                    f"a value, the scan {stated}"
                )
    result = MissingIdCopiesResult(
        accuracy="exact" if exact else "lower_bound",
        identity=found.identity,  # type: ignore[arg-type]  # the one identity of Dedup
        calculation_version=found.calculation_version,
        records=found.records_read,
        storage=found.storage_mode,  # type: ignore[arg-type]  # "memory" or "disk"
        columns=[
            MissingIdColumn(
                field=column.key,
                rows_without_id=column.rows_without_id,
                distinct_rows_without_id=column.distinct_rows_without_id,
                extra_copies_without_id=column.extra_copies_without_id,
            )
            for column in found.columns
        ],
        source_sha256=found.content_sha256,
    )
    if exact:
        return MissingCopiesOutcome("complete", result)
    assert found.reason is not None
    return MissingCopiesOutcome(
        "limited",
        result,
        reason=found.reason,
        detail=f"stopped after {found.records_read} records: {_DETAIL[found.reason]}",
    )
