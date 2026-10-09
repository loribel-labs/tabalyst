# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Distribution of the lengths of the text of a field."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    LENGTH_DOMAIN_FALLBACK,
    Analyzer,
    Assessment,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import blocked, result_state
from tabalyst.scanner.planner.costmodel import COUNTER_BYTES, NS_PER_CELL
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


class LengthDistribution(Analyzer):
    """The Scan keeps an exact length histogram of every text field, so this is
    nearly always satisfied; it applies when that measure is limited or off."""

    id: ClassVar[str] = "length_distribution"
    outputs: ClassVar[tuple[str, ...]] = ("length_histogram",)

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.technical_type in ("text", "mixed")

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        if facts.lengths == "complete":
            return Assessment(
                "satisfied",
                ("lengths_complete",),
                satisfied_by=f"{facts.where}/string_lengths",
            )
        if facts.lengths == "not_applicable":
            return Assessment("not_applicable", ("measure_unavailable",))
        return Assessment(
            "applicable",
            method="dense_counts",
            parameters={"domain": LENGTH_DOMAIN_FALLBACK},
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        size = int(assessment.parameters["domain"]) * COUNTER_BYTES
        state = State(key=f"lengths:{facts.where}", memory=memory(size))
        return costs(
            NS_PER_CELL["length_counter"],
            [state, result_state(self.id, facts)],
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        return Utility(score=50, reasons=["length_distribution"])
