# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The columns of a dataset that miss a value in the same records: for a column
that does, how many records it lacks together with each other (design 20.31,
lot 19)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import result_state
from tabalyst.scanner.planner.costmodel import (
    MATRIX_BYTES,
    MATRIX_COLUMN_BYTES,
    MATRIX_PAIR_BYTES,
    NS_PER_CELL,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


class MissingMatrix(Analyzer):
    """Counts, for each pair of columns that lack a value, the records where both
    do. The counters of a dataset are one state however many of its columns the
    plan selects, and the result of a column holds its pairs with every other."""

    id: ClassVar[str] = "missing_matrix"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("missing_together",)

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.matrix_member and facts.matrix_size >= 2

    def assess(self, facts: FieldFacts) -> Assessment:
        settings = self.settings.missing
        if facts.matrix_size > settings.max_columns:
            return Assessment("not_applicable", ("too_many_columns",))
        return Assessment(
            "applicable",
            method="bit_sets",
            parameters={"columns": facts.matrix_size, "max_listed": settings.max_listed},
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        columns = int(assessment.parameters["columns"])
        pairs = columns * (columns - 1) // 2
        base = MATRIX_BYTES + columns * MATRIX_COLUMN_BYTES
        state = State(
            key=f"matrix:{facts.dataset}",
            memory=memory(base, base + pairs * MATRIX_PAIR_BYTES // 4, base + pairs * MATRIX_PAIR_BYTES),
        )
        return costs(NS_PER_CELL["matrix"], [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["missing_together"])
