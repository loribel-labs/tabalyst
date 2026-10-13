# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact frequencies of a field whose scan lists only part of its counts.

The table is keyed by native type and analytical text, so it is always a table
of counts: counters of integers would merge ``7``, ``007`` and the integer 7,
and at most 1,000 distinct values make a table smaller than any dense array.
"""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    LOW_CARDINALITY_MAX,
    Analyzer,
    Assessment,
    costs,
    memory,
    table_entry,
    text_length,
)
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    replay_state,
    result_state,
)
from tabalyst.scanner.planner.costmodel import FREQUENCY_KEY_BYTES, NS_PER_CELL
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


class ExactFrequencies(Analyzer):
    """Counts of every distinct value, for a field of a size a table can hold."""

    id: ClassVar[str] = "exact_frequencies"
    outputs: ClassVar[tuple[str, ...]] = ("frequencies", "mode", "proportions")
    available: ClassVar[bool] = True

    def relevant(self, facts: FieldFacts) -> bool:
        return True

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        if facts.frequencies == "complete" and not facts.frequencies_truncated:
            return Assessment(
                "satisfied",
                ("counts_complete",),
                satisfied_by=f"{facts.where}/values/frequencies",
            )
        if facts.samples_all:
            # The originals are listed with exact counts: the analytical counts
            # follow by grouping them, without reading the source again.
            return Assessment(
                "satisfied",
                ("counts_in_samples",),
                satisfied_by=f"{facts.where}/values/samples",
            )
        if facts.frequencies != "complete":
            # A released table is a high cardinality; a measure that is off or
            # failed is not.
            reason = "high_cardinality" if facts.frequencies == "limited" else "measure_unavailable"
            return Assessment("not_applicable", (reason,))
        distinct = facts.frequencies_distinct
        if distinct is None or distinct > LOW_CARDINALITY_MAX:
            return Assessment("not_applicable", ("high_cardinality",))
        return Assessment(
            "applicable", method="hash_table", parameters={"distinct": distinct}
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        distinct = int(assessment.parameters["distinct"])
        _, mean, longest = text_length(facts)
        entry = FREQUENCY_KEY_BYTES
        state = State(
            key=f"frequencies:{facts.where}",
            memory=memory(
                distinct * (table_entry(mean) + entry),
                maximum=distinct * (table_entry(longest) + entry),
            ),
        )
        return costs(
            NS_PER_CELL["table"], [state, replay_state(facts), result_state(self.id, facts)]
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        return Utility(score=50, reasons=["partial_counts"])
