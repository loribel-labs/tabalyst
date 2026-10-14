# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Time estimate and confirmation of the selection of a smart sample (design 20.16,
rule R1).

Like the second pass, the selection reads the whole source again: its time is
estimated from what the first pass spent reading, and only feeds a message and the
threshold that asks before a long run. The plan holds nothing of it.
"""

from __future__ import annotations

from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.planner.costmodel import (
    DEFAULT_CONFIRM_SECONDS,
    READING_CELLS_PER_SECOND,
    READING_LOW_SHARE,
)
from tabalyst.scanner.planner.secondpass import (
    MACHINE_FACTOR,
    TIME_REASON,
    WORK_RANGE,
    Confirmation,
    TimeEstimate,
)
from tabalyst.scanner.smart.models import SamplingPlan

# Nanoseconds the selection adds to the shared reading: for each cell of a column
# that has a test (the first pass's reading of the cell included, remembered per
# distinct string), and for each row (the cover, the priority and the pool).
# Measured on the executor (insurance-combined.csv, 1 million rows, 31 columns
# with a test, 345 targets): 35 s for the selection, with a first pass whose
# reading phase took 5.7 s; 1.8 s for the 90,909 rows of insurance-ontario.csv.
# The model gave 35 s at the centre of its range; rounded up, not scaled down.
#
# The final matrix (lot 11, benchmarks.md) showed the cost of a cell depends on how
# many distinct strings the column holds, because the reading of a cell is
# remembered per distinct string: 0.7 us a cell on the combined file (few distinct
# values), 2.6 us on short identifiers and 3.7 us on columns that are nearly all
# distinct. The cell cost is therefore ``SELECT_NS_PER_CELL`` plus
# ``SELECT_NS_PER_DISTINCT_CELL`` times the average distinct share of the tested
# columns, which the Scan knows.
SELECT_NS_PER_CELL = 600
SELECT_NS_PER_DISTINCT_CELL = 3_000
SELECT_NS_PER_ROW = 2_000
# The digest of every row that recognizing duplicate rows needs: 1.1 us for a row
# of 34 cells of ten characters, measured on the machine of the other constants.
DIGEST_NS_PER_ROW = 300
DIGEST_NS_PER_CELL = 25


def _tested_fields(plan: SamplingPlan) -> set[str]:
    return {field for target in plan.targets if target.feasibility == "ready" for field in target.fields}


def _digests_rows(plan: SamplingPlan) -> bool:
    """Whether a ready target is about the rows as a whole (the duplicate rows)."""
    return any(
        target.feasibility == "ready" and target.predicate.kind == "observation" and not target.fields
        for target in plan.targets
    )


def tested_columns(plan: SamplingPlan) -> int:
    """The columns the targets of the plan read: the fields of its targets, once
    each, the table of a relation included."""
    return len(_tested_fields(plan))


def distinct_share(plan: SamplingPlan, scan: ScanResult) -> float:
    """The average share of distinct values of the columns the plan tests, from the
    Scan: 1.0 when every value of a column is distinct. A column whose count the
    Scan does not know is counted as all distinct (the costly side)."""
    dataset = next(d for d in scan.datasets if d.id == plan.dataset)
    fields = {item.id: item for item in dataset.fields}
    shares: list[float] = []
    for field in sorted(_tested_fields(plan)):
        item = fields.get(field)
        if item is None or not item.values.count:
            shares.append(1.0)
            continue
        cardinality = item.values.cardinality
        # A limited count only proves a floor: the share is then the worst case.
        value = getattr(cardinality, "value", None)
        shares.append(1.0 if value is None else min(1.0, value / item.values.count))
    return sum(shares) / len(shares) if shares else 0.0


def estimate_selection(
    plan: SamplingPlan,
    scan: ScanResult,
    *,
    threshold_seconds: float = DEFAULT_CONFIRM_SECONDS,
) -> Confirmation:
    """What reading the source again to choose the rows would cost and whether it
    must be confirmed first.

    The reading costs what the first pass spent reading, at most, and at least its
    parsing share; the selection adds the nanoseconds of the model for each tested
    cell and each row, scaled by how fast the first pass read compared with the
    reference machine.
    """
    dataset = next(d for d in scan.datasets if d.id == plan.dataset)
    rows = dataset.record_count
    width = max(1, len(dataset.fields))
    reading = scan.run.timings.reading
    modeled = rows * width / READING_CELLS_PER_SECOND
    low_factor, high_factor = MACHINE_FACTOR
    speed = (
        1.0 if reading <= 0 or modeled <= 0 else min(high_factor, max(low_factor, reading / modeled))
    )
    per_cell = SELECT_NS_PER_CELL + SELECT_NS_PER_DISTINCT_CELL * distinct_share(plan, scan)
    digest = (
        DIGEST_NS_PER_ROW + DIGEST_NS_PER_CELL * width if _digests_rows(plan) else 0
    )
    work = (rows * tested_columns(plan) * per_cell + rows * (SELECT_NS_PER_ROW + digest)) / 1e9 * speed
    share = READING_LOW_SHARE if scan.source.format == "csv" else 1.0
    low_work, high_work = WORK_RANGE
    estimate = TimeEstimate(
        low_seconds=reading * share + work * low_work,
        high_seconds=reading + work * high_work,
    )
    reasons = [TIME_REASON] if estimate.high_seconds >= threshold_seconds else []
    return Confirmation(
        required=bool(reasons),
        reasons=tuple(reasons),
        memory_max_bytes=plan.candidates.budget_bytes,
        estimate=estimate,
    )
