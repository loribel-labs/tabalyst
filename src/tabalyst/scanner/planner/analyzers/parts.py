# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The parts of the dates of a field: year-month, day of the week, hour, dates
after a bound (design 20.25, lot 17)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    distinct_band,
    replay_state,
    result_state,
)
from tabalyst.scanner.planner.analyzers.temporal import DATED_SHARE, date_order
from tabalyst.scanner.planner.costmodel import (
    NS_PER_CELL,
    PARTS_BYTES,
    PARTS_MONTH_BYTES,
    PERIOD_ENTRY_BYTES,
    PERIOD_MEMO_ENTRIES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

DATED_KINDS = ("date", "datetime_naive", "datetime_aware", "time")


def parts_tier(facts: FieldFacts) -> str:
    """The key of ``NS_PER_CELL`` for the parts of the dates of a field: its cost
    follows the distinct strings, which the Scan counted or bounded."""
    return {"few": "parts_few", "mid": "parts", "wide": "parts_wide"}[distinct_band(facts)]


class DatetimeParts(Analyzer):
    """Counts the dates by year-month, day of the week and hour, and reads the
    ambiguous and invalid ones."""

    id: ClassVar[str] = "datetime_parts"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("calendar_parts", "ambiguity", "invalid_reasons")

    def relevant(self, facts: FieldFacts) -> bool:
        if facts.technical_type == "date":
            return True
        if facts.technical_type == "mixed":
            return facts.temporal_status == "complete"
        temporal = facts.temporal
        return (
            facts.technical_type == "text"
            and temporal is not None
            and len(temporal.kinds) == 1
            and temporal.kinds[0] in DATED_KINDS
            and temporal.kinds[0] != "date"
            and temporal.count >= DATED_SHARE * facts.values
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
        settings = self.settings.datetime
        order = date_order(temporal, settings)
        return Assessment(
            "applicable",
            method="calendar_parts",
            parameters={"as_of": settings.as_of or "", "date_order": order},
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        # A counter for each month between the first and the last date (a datetime
        # with an offset can fall a day beyond them), a dictionary entry each, and
        # twice that with the readings of the ambiguous dates.
        span = None if facts.temporal is None else facts.temporal.span_days
        months = 2 if span is None else span // 28 + 3
        state = State(
            key=f"parts:{facts.where}",
            memory=memory(
                PARTS_BYTES,
                PARTS_BYTES + months * PARTS_MONTH_BYTES,
                PARTS_BYTES + 2 * months * PARTS_MONTH_BYTES,
            ),
        )
        entries = PERIOD_MEMO_ENTRIES
        if facts.distinct is not None:
            entries = min(entries, facts.distinct)
        memo = replay_state(facts, entries, PERIOD_ENTRY_BYTES)
        return costs(NS_PER_CELL[parts_tier(facts)], [state, memo, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        reasons = ["calendar_parts"]
        if assessment.parameters.get("date_order"):
            reasons.append("ambiguous_dates_read_by_evidence")
        return Utility(score=40, reasons=reasons)
