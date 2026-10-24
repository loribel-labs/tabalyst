# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The extra copies of whole rows of a CSV file, counted with the engine of Dedup (design 20.40,
Unique ID lot 6)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.dedup.store import ENTRY_OVERHEAD
from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import result_state
from tabalyst.scanner.planner.costmodel import NS_PER_CELL, ROWS_COPIES_BYTES
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

MIB = 1 << 20


class DuplicateRows(Analyzer):
    """Counts the rows that repeat an earlier row, whole and exactly.

    The Scan counts them too (``records.duplicates``), within a bound of memory; this is
    for the file where that count is ``limited``. It never overrides a Scan that switched the
    count off, and it is never chosen by itself: the planner takes it when asked for.
    """

    id: ClassVar[str] = "duplicate_rows_count"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("duplicate_rows",)
    rows: ClassVar[bool] = True

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.rows_duplicates != "not_applicable"

    def assess(self, facts: FieldFacts) -> Assessment:
        if facts.rows_duplicates == "complete":
            return Assessment(
                "satisfied",
                ("copies_exact",),
                satisfied_by=facts.where.rsplit("/fields/", 1)[0] + "/records/duplicates",
            )
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
        return costs(NS_PER_CELL["rows"], [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["duplicate_rows"])
