# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The shape of the numbers of a field: asymmetry, outliers, decimals (design
20.24, lot 17)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    distinct_band,
    identifier_like,
    replay_state,
    result_state,
)
from tabalyst.scanner.planner.costmodel import (
    COUNTER_BYTES,
    EDGE_BYTES,
    GRID_BIN_BYTES,
    MEASURE_ENTRY_BYTES,
    MEASURE_MERGE_BYTES,
    NS_PER_CELL,
    SHAPE_BUFFER_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


def shape_tier(facts: FieldFacts) -> str:
    """The key of ``NS_PER_CELL`` for the shape of a field: its cost follows the
    distinct values, which the Scan counted or bounded."""
    return {"few": "shape_few", "mid": "shape", "wide": "shape_wide"}[distinct_band(facts)]


class NumericShape(Analyzer):
    """Counts the distinct numbers (or bins them beyond a limit) to give the
    asymmetry, the kurtosis, the outliers of Tukey, the decimals the numbers are
    written with, and the logarithmic and equal-count views of their spread."""

    id: ClassVar[str] = "numeric_shape"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("moments", "outliers", "decimals", "histogram")

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.technical_type in ("integer", "number") or (
            facts.technical_type == "mixed" and facts.numeric == "complete"
        )

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        if facts.numeric != "complete":
            return Assessment("not_applicable", ("measure_unavailable",))
        if facts.technical_type == "mixed":
            return Assessment("not_applicable", ("unreliable_type",))
        if facts.numeric_min == facts.numeric_max:
            return Assessment(
                "satisfied", ("constant_value",), satisfied_by=f"{facts.where}/numeric"
            )
        return Assessment(
            "applicable",
            method="value_table",
            parameters={
                "max_values": self.settings.shape.max_values,
                "bins": self.settings.bins,
            },
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        parameters = assessment.parameters
        distinct = facts.distinct if facts.distinct is not None else facts.numeric_count
        entries = min(int(parameters["max_values"]), distinct)
        bins = int(parameters["bins"])
        # The table, and the sorted copy the result makes of it.
        table = State(
            key=f"shape:{facts.where}",
            memory=memory(
                entries * MEASURE_ENTRY_BYTES // 2,
                entries * MEASURE_ENTRY_BYTES,
                entries * (MEASURE_ENTRY_BYTES + MEASURE_MERGE_BYTES),
            ),
        )
        # The grid and its buffer of float moments, and the two views.
        grid = State(
            key=f"shape_grid:{facts.where}",
            memory=memory(
                bins * GRID_BIN_BYTES,
                bins * GRID_BIN_BYTES + SHAPE_BUFFER_BYTES // 4,
                bins * GRID_BIN_BYTES + SHAPE_BUFFER_BYTES,
            ),
        )
        views = State(
            key=f"shape_views:{facts.where}",
            memory=memory(2 * (bins * COUNTER_BYTES + (bins + 1) * EDGE_BYTES)),
        )
        return costs(
            NS_PER_CELL[shape_tier(facts)],
            [table, grid, views, replay_state(facts), result_state(self.id, facts)],
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        if identifier_like(facts):
            return Utility(score=15, reasons=["identifier_like"])
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["numeric_shape"])
