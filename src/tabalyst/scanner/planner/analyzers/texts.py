# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The long texts of a field: what they are made of, and how many of them are
different (design 20.34, lot 18)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    COMPACT_MAX_LENGTH,
    Analyzer,
    Assessment,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import blocked, result_state
from tabalyst.scanner.planner.costmodel import (
    CLASS_NS,
    EXACT_SET_FIXED_BYTES,
    EXACT_SET_STATE_PREFIX,
    FINGERPRINT_ENTRY_BYTES,
    FINGERPRINT_NS_PER_CHAR,
    NS_PER_CELL,
    TEXT_BYTES,
    TEXT_NS_PER_CHAR,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, Memory, State, Utility


def is_text(facts: FieldFacts, minimum: int) -> bool:
    """Whether the field holds texts: its longest value reaches ``minimum``
    characters, or the Scan sampled some of its values as long texts."""
    return facts.long_text_occurrences > 0 or (facts.max_length or 0) >= minimum


class TextProfile(Analyzer):
    """Counts the words, the lines and the digits of the texts of a field. The
    memory is constant: a text is read once and forgotten."""

    id: ClassVar[str] = "text_profile"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("text_shape",)

    def relevant(self, facts: FieldFacts) -> bool:
        # A column of short values has no candidate, so a plan does not list one for
        # every string column of a wide file.
        return facts.strings_content > 0 and is_text(facts, self.settings.texts.min_length)

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        return Assessment("applicable", method="text_counters")

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        state = State(key=f"texts:{facts.where}", memory=memory(TEXT_BYTES))
        # The splits and the count of digits read every character once; declared at
        # the top of the class ``moderate`` at most, so the time estimate is low for
        # texts of several kilobytes.
        nanoseconds = min(
            NS_PER_CELL["text_base"] + round(TEXT_NS_PER_CHAR * (facts.mean_length or 0)),
            CLASS_NS["moderate"],
        )
        return costs(nanoseconds, [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["text_shape"])


class FingerprintDistinct(Analyzer):
    """Counts the distinct values by a 128-bit fingerprint, for values too long
    for the exact set, and finds the texts that occur more than once."""

    id: ClassVar[str] = "fingerprint_distinct"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("distinct_count", "repeated_texts")

    def relevant(self, facts: FieldFacts) -> bool:
        # The values the exact set holds, and finds the repeated ones of, have no candidate.
        return facts.strings_content > 0 and (
            facts.long_text_occurrences > 0 or (facts.max_length or 0) > COMPACT_MAX_LENGTH
        )

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        if facts.distinct is not None and facts.distinct == facts.values:
            return Assessment(
                "satisfied",
                ("distinct_exact",),
                satisfied_by=f"{facts.where}/values/cardinality",
            )
        return Assessment(
            "applicable",
            method="fingerprints",
            parameters={"max_listed": self.settings.texts.max_listed},
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        lower = facts.distinct_lower_bound or 0
        known = facts.distinct
        estimate = facts.distinct_estimate
        maximum = max(facts.values, lower)
        expected = (
            known
            if known is not None
            else lower if estimate is None else min(max(round(estimate), lower), maximum)
        )
        entry = FINGERPRINT_ENTRY_BYTES
        size = Memory(
            min=EXACT_SET_FIXED_BYTES + lower * entry[0],
            expected=EXACT_SET_FIXED_BYTES + expected * entry[1],
            max=EXACT_SET_FIXED_BYTES + maximum * entry[2],
        )
        # The table is drawn from the pool of the exact sets of the run, so the
        # state is named like theirs (the plan grants the pool its firm bound).
        return costs(
            min(
                NS_PER_CELL["fingerprint"]
                + round(FINGERPRINT_NS_PER_CHAR * (facts.mean_length or 0)),
                CLASS_NS["moderate"],
            ),
            [
                State(key=f"{EXACT_SET_STATE_PREFIX}fingerprint:{facts.where}", memory=size),
                result_state(self.id, facts),
            ],
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["long_values_distinct"])
