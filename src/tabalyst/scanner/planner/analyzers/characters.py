# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The characters of the strings of a field: the most frequent ones, their Unicode
families, the case of the ends and the emoji, on every value (design 20.37, lot C2)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import blocked, result_state
from tabalyst.scanner.planner.costmodel import (
    CHARACTER_BYTES,
    CHARACTER_NS_PER_CHAR,
    CLASS_NS,
    NS_PER_CELL,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility


class CharacterProfile(Analyzer):
    """Counts the characters of the original strings of a field exactly. The Scan
    already maps the characters of its samples; this replaces that map with the
    exact one. The tables are bounded, so the memory is constant per field."""

    id: ClassVar[str] = "character_profile"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("character_map",)

    def relevant(self, facts: FieldFacts) -> bool:
        # The map is off when the Scan lists no character (``max_top_characters`` 0).
        return facts.strings_content > 0 and facts.top_characters > 0

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        if (
            facts.samples_all
            and facts.long_text_occurrences == 0
            and facts.character_map == "complete"
        ):
            # Every distinct original value is listed with its exact count: the map
            # of the Scan is already the exact one.
            return Assessment(
                "satisfied",
                ("map_in_samples",),
                satisfied_by=f"derived/characters/{facts.dataset}/{facts.field}",
            )
        return Assessment(
            "applicable",
            method="character_census",
            parameters={"top": facts.top_characters},
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        smallest, largest = CHARACTER_BYTES
        state = State(
            key=f"characters:{facts.where}",
            memory=memory(smallest, smallest * 2, largest),
        )
        # Declared at the top of ``moderate`` at most, so the estimate is low for texts
        # of several hundred characters.
        nanoseconds = min(
            NS_PER_CELL["characters"]
            + round(CHARACTER_NS_PER_CHAR * (facts.mean_length or 0)),
            CLASS_NS["moderate"],
        )
        return costs(nanoseconds, [state, result_state(self.id, facts)])

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Below the automatic threshold: asked for, or run by a forced pass.
        return Utility(score=40, reasons=["character_map"])
