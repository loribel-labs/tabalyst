# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The extra copies of whole rows of a CSV file, counted with the engine of Dedup (design 20.40,
Unique ID lot 6)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.dedup.calculation import CALCULATION_VERSION
from tabalyst.dedup.store import ENTRY_OVERHEAD
from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import (
    AUTOMATIC_IDENTIFIER_SCORE,
    result_state,
)
from tabalyst.scanner.planner.costmodel import (
    NS_PER_CELL,
    ROWS_COPIES_BYTES,
    cpu_class_for,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

MIB = 1 << 20


class DuplicateRows(Analyzer):
    """Counts the rows that repeat an earlier row, whole and exactly.

    The Scan counts them too (``records.duplicates``), within a bound of memory; this is
    for the file where that count is ``limited``. It never overrides a Scan that switched the
    count off. The planner takes it by itself only for a dataset with an identifier column whose
    uniqueness it can settle, when the Scan's count is a lower bound, the distinct count is known
    or planned, and the table of distinct rows fits the automatic memory (design 20.42).
    """

    id: ClassVar[str] = "duplicate_rows_count"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("duplicate_rows",)
    rows: ClassVar[bool] = True
    # The version of the analyzer is that of the calculation of the engine: a change of what the
    # count means makes the stored results stale (they are keyed by it, cahier 12.5).
    version: ClassVar[int] = CALCULATION_VERSION

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.rows_duplicates != "not_applicable"

    def assess(self, facts: FieldFacts) -> Assessment:
        if facts.rows_duplicates == "complete":
            return Assessment(
                "satisfied",
                ("copies_exact",),
                satisfied_by=facts.where.rsplit("/fields/", 1)[0] + "/records/duplicates",
            )
        if facts.rows_proved:
            # A valid Dedup report gives the copies exactly where the Scan only bounded them or
            # did not count: a second reading would only repeat it.
            return Assessment("satisfied", ("copies_proved",), satisfied_by="dedup report")
        if facts.rows_duplicates == "disabled":
            return Assessment("not_applicable", ("duplicates_disabled",))
        if facts.records_excluded:
            return Assessment("not_applicable", ("records_left_out",))
        settings = self.settings.copies
        return Assessment(
            "applicable",
            method="extra_copies",
            parameters={
                "memory_mb": settings.memory_mb,
                "disk_mb": settings.disk_mb,
                "max_rows": settings.max_rows,
            },
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        parameters = assessment.parameters
        ceiling = int(parameters["memory_mb"]) * MIB
        read = min(facts.records, int(parameters["max_rows"]))
        table = read * (facts.row_bytes + ENTRY_OVERHEAD)
        # The table moves to disk at the budget; the database then keeps its cache within it.
        state = State(
            key=f"rows:{facts.dataset}",
            memory=memory(
                ROWS_COPIES_BYTES,
                ROWS_COPIES_BYTES + min(table // 2, ceiling),
                ROWS_COPIES_BYTES + min(table, ceiling),
            ),
        )
        work = costs(NS_PER_CELL["rows"], [state, result_state(self.id, facts)])
        # The CPU class is the nanoseconds a cell of the shared reading costs; the unit of this
        # analysis is the record, so its class is that of its share of a cell: a wide table is cheap
        # per cell, a table of two columns is not. ``cell_ns`` stays per record for the time estimate.
        return work.model_copy(
            update={"cpu": cpu_class_for(NS_PER_CELL["rows"] // max(1, facts.dataset_fields))}
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Above the automatic threshold only when the count can settle the uniqueness of an
        # identifier of the dataset (UID-011). The planner still checks that its distinct count
        # is known or planned; otherwise it is asked for, or run by a forced pass.
        if facts.rows_candidates and facts.rows_duplicates == "limited":
            return Utility(score=AUTOMATIC_IDENTIFIER_SCORE, reasons=["identifier_copies"])
        return Utility(score=40, reasons=["duplicate_rows"])
