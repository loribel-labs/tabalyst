# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Distribution of the numbers of a field, as a dense array or as bins."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    DENSE_DOMAIN_MAX,
    Analyzer,
    Assessment,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    identifier_like,
    replay_state,
    result_state,
)
from tabalyst.scanner.planner.costmodel import COUNTER_BYTES, EDGE_BYTES, NS_PER_CELL
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


def dense_domain(facts: FieldFacts) -> int | None:
    """Number of integers between the minimum and maximum of an integer field
    when a dense array of counters can hold them, else ``None``. The bounds
    must be written as integers, which are exact: the array starts at the
    minimum."""
    if (
        facts.technical_type != "integer"
        or facts.numeric != "complete"
        or not isinstance(facts.numeric_min, int)
        or not isinstance(facts.numeric_max, int)
    ):
        return None
    domain = facts.numeric_max - facts.numeric_min + 1
    return domain if 0 < domain <= DENSE_DOMAIN_MAX else None


def dense_state(facts: FieldFacts, domain: int) -> State:
    """The array of counters of a small integer domain."""
    return State(key=f"dense_counts:{facts.where}", memory=memory(domain * COUNTER_BYTES))


class NumericHistogram(Analyzer):
    """Dense counters for a small integer domain, 100 bins otherwise."""

    id: ClassVar[str] = "numeric_histogram"
    outputs: ClassVar[tuple[str, ...]] = ("histogram", "quantiles", "median_estimate")
    available: ClassVar[bool] = True

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
            # No spread to bin, and no division by zero to guard (D09).
            return Assessment(
                "satisfied",
                ("constant_value",),
                satisfied_by=f"{facts.where}/numeric",
            )
        domain = dense_domain(facts)
        if domain is not None:
            return Assessment(
                "applicable", method="dense_counts", parameters={"domain": domain}
            )
        return Assessment(
            "applicable",
            method="bins",
            parameters={
                "bins": self.settings.bins,
                "strategy": self.settings.bin_strategy,
            },
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        if assessment.method == "dense_counts":
            state = dense_state(facts, int(assessment.parameters["domain"]))
            work = NS_PER_CELL["dense_counter"]
        else:
            bins = int(assessment.parameters["bins"])
            size = bins * COUNTER_BYTES + (bins + 1) * EDGE_BYTES
            state = State(key=f"bins:{facts.where}", memory=memory(size))
            work = NS_PER_CELL["bin"]
        return costs(work, [state, replay_state(facts), result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        if identifier_like(facts):
            # The identity of a key is not a quantity (specification 11.2).
            return Utility(score=15, reasons=["identifier_like"])
        if assessment.method == "dense_counts":
            return Utility(
                score=60, reasons=["numeric_distribution", "same_state_exact_median"]
            )
        return Utility(score=50, reasons=["numeric_distribution"])
