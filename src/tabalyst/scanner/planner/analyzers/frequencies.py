# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact frequencies of a field whose scan lists only part of its counts."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    DENSE_DOMAIN_MAX,
    LOW_CARDINALITY_MAX,
    Analyzer,
    Assessment,
    costs,
    memory,
    table_entry,
    text_length,
)
from tabalyst.scanner.planner.analyzers.common import blocked, result_state
from tabalyst.scanner.planner.costmodel import COUNTER_BYTES, NS_PER_CELL
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


def dense_domain(facts: FieldFacts) -> int | None:
    """Number of integers between the minimum and maximum of an integer field
    when a dense array of counters can hold them, else ``None``."""
    if (
        facts.technical_type != "integer"
        or facts.numeric != "complete"
        or facts.numeric_min is None
        or facts.numeric_max is None
    ):
        return None
    domain = int(facts.numeric_max) - int(facts.numeric_min) + 1
    return domain if 0 < domain <= DENSE_DOMAIN_MAX else None


def dense_state(facts: FieldFacts, domain: int) -> State:
    """The array of counters that the frequencies and the histogram of a
    small integer domain share (specification 11.2)."""
    return State(key=f"dense_counts:{facts.where}", memory=memory(domain * COUNTER_BYTES))


class ExactFrequencies(Analyzer):
    """Counts of every distinct value, for a field of a size a table can hold."""

    id: ClassVar[str] = "exact_frequencies"
    outputs: ClassVar[tuple[str, ...]] = ("frequencies", "mode", "proportions")

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
        domain = dense_domain(facts)
        if domain is not None:
            return Assessment(
                "applicable", method="dense_counts", parameters={"domain": domain}
            )
        return Assessment(
            "applicable", method="hash_table", parameters={"distinct": distinct}
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        if assessment.method == "dense_counts":
            state = dense_state(facts, int(assessment.parameters["domain"]))
            work = NS_PER_CELL["dense_counter"]
        else:
            distinct = int(assessment.parameters["distinct"])
            _, mean, longest = text_length(facts)
            state = State(
                key=f"frequencies:{facts.where}",
                memory=memory(
                    distinct * table_entry(mean), maximum=distinct * table_entry(longest)
                ),
            )
            work = NS_PER_CELL["table"]
        return costs(work, [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        return Utility(score=50, reasons=["partial_counts"])
