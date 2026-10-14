# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reading that chooses the rows of a smart sample (design 20.16, SMART-05).

It reads the source once with the configuration the Scan recorded, tells for every
row which targets it covers, keeps the bounded pool of candidates, and publishes
nothing until the digest of the bytes it read has been compared with the Scan's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from tabalyst.errors import InputError
from tabalyst.progress import (
    ProgressCallback,
    ProgressPhase,
    byte_progress,
    emit_progress,
)
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.observations import DatasetOpened, RecordBatch, RecordExcluded
from tabalyst.scanner.process import peak_memory_bytes
from tabalyst.scanner.readers.factory import open_reader
from tabalyst.scanner.rowsample import RowPriority
from tabalyst.scanner.secondpass.models import DeepResult
from tabalyst.scanner.smart.evaluate import Evaluator
from tabalyst.scanner.smart.models import SamplingPlan, Target
from tabalyst.scanner.smart.select import SelectionOutcome, SelectionPool
from tabalyst.source_guard import SourceGuard, check_plan_base


@dataclass(frozen=True)
class SmartSelection:
    """The rows chosen, with what the reading and the choice did.

    ``unresolved`` maps the position of a target of the plan that could not be
    tested to its reason code (``evaluate.UNRESOLVED``).
    """

    header: list[str]
    rows: list[list[str]]
    outcome: SelectionOutcome
    unresolved: dict[int, str]
    records_read: int
    cells_read: int
    reading_seconds: float
    selection_seconds: float
    peak_memory: int | None


def _is_anomaly(target: Target) -> bool:
    """Whether a target says something is wrong with a row, for the score of a row:
    what the Scan observed or found in the characters, not a value, a pattern or an
    extreme every column has, and not an empty cell, which is a remark."""
    return target.family == "quality" and target.predicate.params.get("rule") != "missing_values"


def select_rows(
    scan: ScanResult,
    source: Path,
    plan: SamplingPlan,
    *,
    deep: DeepResult | None = None,
    on_progress: ProgressCallback | None = None,
) -> SmartSelection:
    """Read ``source`` once and choose the rows of the smart sample ``plan`` asks
    for. Writes nothing.

    ``deep`` is the second-pass document the plan was made from (when it was
    current), whose tables the relation targets refer to. Raises ``StalePlan``,
    ``StaleSource`` or ``SourceNotReadable`` (design 20.6) before and after the
    reading, and ``InputError`` when the source is not a CSV file or the plan
    asks for no size: no rows are returned then.
    """
    check_plan_base(plan, scan)
    size = plan.size.requested
    if size is None or plan.reserve.rows_granted is None:
        raise InputError("A smart sample needs a size: the plan has none.")
    if scan.source.format != "csv":
        raise InputError("A smart sample reads CSV files only.")
    dataset = next((d for d in scan.datasets if d.id == plan.dataset), None)
    if dataset is None:
        raise InputError(f"The Scan has no dataset named {plan.dataset!r}.")

    guard = SourceGuard(source, scan.source)
    guard.before()
    evaluator = Evaluator(scan, dataset, deep, plan.targets)
    ready = [
        target.feasibility == "ready" and position not in evaluator.unresolved
        for position, target in enumerate(plan.targets)
    ]
    pool = SelectionPool(
        [t.weight.value if ok else 0.0 for t, ok in zip(plan.targets, ready, strict=True)],
        [t.obligation == "mandatory" and ok for t, ok in zip(plan.targets, ready, strict=True)],
        size=size,
        reserve=plan.reserve.rows_granted,
        worst=plan.settings.worst_rows,
        anomaly=[_is_anomaly(target) and ok for target, ok in zip(plan.targets, ready, strict=True)],
        per_target=plan.candidates.per_target_effective,
        budget=plan.candidates.budget_bytes,
    )
    priority = RowPriority(plan.method.seed)
    emit_progress(
        on_progress,
        source,
        ProgressPhase.READING,
        detail="smart sample",
        bytes_read=0,
        bytes_total=scan.source.size_bytes,
    )
    reader = open_reader(source, scan.config, byte_progress(on_progress, source, scan.source.size_bytes))
    header: list[str] = []
    records = cells = 0
    reading = 0.0
    started = perf_counter()
    for item in reader:
        if isinstance(item, DatasetOpened):
            header = [declared.name for declared in item.fields]
        elif isinstance(item, RecordBatch):
            rows = item.rows
            first = item.start
            covers = evaluator.cover(rows)
            pool.feed(first, rows, covers, priority.range(first, first + len(rows)))
            records += len(rows)
            cells += len(rows) * len(evaluator.columns)
        elif isinstance(item, RecordExcluded):
            continue
    reading = perf_counter() - started
    summary = reader.summary()
    guard.finish(summary.sha256, summary.bytes_read)
    chosen_at = perf_counter()
    outcome = pool.finish()
    return SmartSelection(
        header=header or (summary.csv.header if summary.csv else []),
        rows=[row for _, row in outcome.rows],
        outcome=outcome,
        unresolved=evaluator.unresolved,
        records_read=records,
        cells_read=cells,
        reading_seconds=round(reading, 6),
        selection_seconds=round(perf_counter() - chosen_at, 6),
        peak_memory=peak_memory_bytes(),
    )
