# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The columns of a dataset that miss a value in the same records: for a column
that does, how many records it lacks together with each other (design 20.31,
lot 19), and for the dataset, the records by the exact set of columns they lack
(design 20.44)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import result_state
from tabalyst.scanner.planner.costmodel import (
    MATRIX_BYTES,
    MATRIX_COLUMN_BYTES,
    MATRIX_PAIR_BYTES,
    MISSING_PATTERN_BYTES,
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


class MissingPatterns(Analyzer):
    """Counts the records of a dataset by the exact set of the columns of its matrix
    they lack a value in: the exclusive intersections an UpSet plot draws. One
    candidate for the dataset, named ``$``; the counting shares the reading and the
    tests of the cells of ``missing_matrix``."""

    id: ClassVar[str] = "missing_patterns"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("missing_patterns",)
    datasets: ClassVar[bool] = True

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.dataset_scope and facts.matrix_size >= 2

    def assess(self, facts: FieldFacts) -> Assessment:
        settings = self.settings.missing
        if facts.matrix_size > settings.max_columns:
            return Assessment("not_applicable", ("too_many_columns",))
        return Assessment(
            "applicable",
            method="pattern_table",
            parameters={
                "columns": facts.matrix_size,
                "max_patterns": settings.max_patterns,
                "max_listed": settings.max_patterns_listed,
            },
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        columns = int(assessment.parameters["columns"])
        limit = int(assessment.parameters["max_patterns"])
        base = MATRIX_BYTES + columns * MATRIX_COLUMN_BYTES
        # The unit is the record: each cell of the matrix is tested and joins the
        # combination of its record.
        work = (NS_PER_CELL["matrix"] + NS_PER_CELL["matrix_patterns"]) * columns
        shared = State(key=f"matrix:{facts.dataset}", memory=memory(base))
        table = State(
            key=f"missing_patterns:{facts.dataset}",
            memory=memory(
                MISSING_PATTERN_BYTES,
                min(limit, facts.records) * MISSING_PATTERN_BYTES // 4 or MISSING_PATTERN_BYTES,
                min(limit, facts.records) * MISSING_PATTERN_BYTES or MISSING_PATTERN_BYTES,
            ),
        )
        return costs(work, [shared, table, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass (``--deep``, and
        # ``tabalyst report --details`` once its chart pages ship).
        return Utility(score=40, reasons=["missing_patterns"])
