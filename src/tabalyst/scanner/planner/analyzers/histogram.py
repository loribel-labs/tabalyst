# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Distribution of the numbers of a field, as a dense array or as bins."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    BIN_COUNT,
    COUNTER_BYTES,
    Analyzer,
    Assessment,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    identifier_like,
    result_state,
)
from tabalyst.scanner.planner.analyzers.frequencies import dense_domain, dense_state
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

# Two bounds of the bins, as 8 bytes each.
BOUNDS_BYTES = 16


class NumericHistogram(Analyzer):
    """Dense counters for a small integer domain, 100 bins otherwise."""

    id: ClassVar[str] = "numeric_histogram"
    outputs: ClassVar[tuple[str, ...]] = ("histogram", "quantiles", "median_estimate")

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
            "applicable", method="linear_bins", parameters={"bins": BIN_COUNT}
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        if assessment.method == "dense_counts":
            state = dense_state(facts, int(assessment.parameters["domain"]))
        else:
            size = int(assessment.parameters["bins"]) * COUNTER_BYTES + BOUNDS_BYTES
            state = State(key=f"bins:{facts.where}", memory=memory(size))
        return costs("very_low", [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        if identifier_like(facts):
            # The identity of a key is not a quantity (specification 11.2).
            return Utility(score=15, reasons=["identifier_like"])
        if assessment.method == "dense_counts":
            return Utility(
                score=60, reasons=["numeric_distribution", "same_state_exact_median"]
            )
        return Utility(score=50, reasons=["numeric_distribution"])
