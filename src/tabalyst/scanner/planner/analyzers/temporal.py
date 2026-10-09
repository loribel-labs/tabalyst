# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Distribution of the dates of a field over days, months or years."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    COUNTER_BYTES,
    Analyzer,
    Assessment,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import blocked, result_state
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

# The finest granularity whose number of periods stays small (specification
# 11.2: the periods are sized before the reading).
DAY_SPAN = 2 * 366
MONTH_SPAN = 60 * 366


def granularity(span_days: int) -> tuple[str, int]:
    """The granularity and the number of periods for a span in days."""
    if span_days <= DAY_SPAN:
        return "day", span_days + 1
    if span_days <= MONTH_SPAN:
        return "month", span_days // 28 + 2
    return "year", span_days // 365 + 2


class TemporalDistribution(Analyzer):
    """Counters per day, month or year, sized from the span of the dates."""

    id: ClassVar[str] = "temporal_distribution"
    outputs: ClassVar[tuple[str, ...]] = ("period_counts",)

    def relevant(self, facts: FieldFacts) -> bool:
        return facts.technical_type == "date" or (
            facts.technical_type == "mixed" and facts.temporal_status == "complete"
        )

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        temporal = facts.temporal
        if temporal is None or temporal.count == 0:
            return Assessment("not_applicable", ("measure_unavailable",))
        if facts.technical_type == "mixed":
            return Assessment("not_applicable", ("unreliable_type",))
        if len(temporal.kinds) != 1:
            return Assessment("not_applicable", ("mixed_temporal_kinds",))
        if temporal.kinds[0] == "time":
            return Assessment("not_applicable", ("time_only",))
        if temporal.span_days is None:
            return Assessment("not_applicable", ("measure_unavailable",))
        if temporal.span_days == 0:
            return Assessment(
                "satisfied", ("constant_value",), satisfied_by=f"{facts.where}/temporal"
            )
        unit, periods = granularity(temporal.span_days)
        if unit == "year" and temporal.years_counted:
            return Assessment(
                "satisfied", ("years_counted",), satisfied_by=f"{facts.where}/temporal"
            )
        return Assessment(
            "applicable",
            method="period_counts",
            parameters={"granularity": unit, "periods": periods},
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        size = int(assessment.parameters["periods"]) * COUNTER_BYTES
        state = State(key=f"periods:{facts.where}", memory=memory(size))
        return costs("very_low", [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        return Utility(score=50, reasons=["temporal_distribution"])
