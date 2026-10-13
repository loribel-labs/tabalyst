# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A column followed by position in the file: the values and the missing ones of
ten slices of records, and the values themselves for a column of few distinct ones
(design 20.30, lot 19)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
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
from tabalyst.scanner.planner.costmodel import (
    DRIFT_BYTES,
    DRIFT_VALUE_BYTES,
    FREQUENCY_KEY_BYTES,
    NS_PER_CELL,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

# Fewer records than this leave a slice with too few to be read.
DRIFT_MIN_RECORDS = 100
SLICES = 10


def followed_values(facts: FieldFacts, max_tracked: int) -> int | None:
    """The distinct values of a field when the Scan lists all of them, with their
    counts, and there are few enough to follow each by slice; else ``None``."""
    distinct = facts.frequencies_distinct
    if facts.frequencies != "complete" or facts.frequencies_truncated or distinct is None:
        return None
    return distinct if 2 <= distinct <= max_tracked else None


class PositionDrift(Analyzer):
    """Counts the values and the missing ones by slice of records, and the values
    themselves when the field has few enough distinct ones."""

    id: ClassVar[str] = "position_drift"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("missing_by_position", "values_by_position", "new_values")

    def relevant(self, facts: FieldFacts) -> bool:
        return True

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        if facts.repeated:
            return Assessment("not_applicable", ("repeated_field",))
        if facts.records_excluded:
            return Assessment("not_applicable", ("records_excluded",))
        if facts.records < DRIFT_MIN_RECORDS:
            return Assessment("not_applicable", ("too_few_records",))
        settings = self.settings.drift
        tracked = followed_values(facts, settings.max_tracked)
        if tracked is None and facts.values >= facts.records:
            return Assessment("not_applicable", ("nothing_to_follow",))
        parameters: dict[str, int | str] = {"slices": SLICES, "values": int(tracked is not None)}
        if tracked is not None:
            parameters["max_listed"] = settings.max_listed
        return Assessment("applicable", method="slices", parameters=parameters)

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        distinct = followed_values(facts, self.settings.drift.max_tracked)
        states = [result_state(self.id, facts)]
        if distinct is None:
            state = State(key=f"drift:{facts.where}", memory=memory(DRIFT_BYTES))
            return costs(NS_PER_CELL["drift_presence"], [state, *states])
        _, mean, longest = text_length(facts)
        entry = DRIFT_VALUE_BYTES + FREQUENCY_KEY_BYTES
        state = State(
            key=f"drift:{facts.where}",
            memory=memory(
                DRIFT_BYTES + distinct * (table_entry(mean) + entry),
                maximum=DRIFT_BYTES + distinct * (table_entry(longest) + entry),
            ),
        )
        return costs(NS_PER_CELL["drift_values"], [state, replay_state(facts), *states])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["drift_by_position"])
