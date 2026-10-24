# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact distinct count of the analytical values of a field whose scan stopped tracking it
(design 20.41, Unique ID lot 7)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import COMPACT_MAX_LENGTH, Assessment, costs
from tabalyst.scanner.planner.analyzers.common import (
    AUTOMATIC_IDENTIFIER_SCORE,
    replay_state,
    result_state,
)
from tabalyst.scanner.planner.analyzers.distinct import ExactDistinct
from tabalyst.scanner.planner.costmodel import (
    EXACT_SET_FIXED_BYTES,
    EXACT_SET_STATE_PREFIX,
    NS_PER_CELL,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

# Changes with what the count means (the stages it applies, the key it compares): a stored
# result is keyed by it, so a change makes the results of an older run stale (cahier 12.5).
CALCULATION_VERSION = 1


class AnalyticalDistinct(ExactDistinct):
    """The set holds the analytical text of each value (the output of the enabled ``nfc``,
    ``trim`` and ``collapse_whitespace`` stages), where ``exact_distinct`` holds the original one.

    Needed only when the Scan lost its table of values and a stage changed a value: if no
    stage did, the count of the original values is the analytical one and ``exact_distinct``
    gives it. Sizes are those of ``exact_distinct``; the reading adds the analytical text of
    the cells. Never chosen by itself: asked for, or run by a forced second pass.
    """

    id: ClassVar[str] = "analytical_distinct"
    version: ClassVar[int] = CALCULATION_VERSION
    outputs: ClassVar[tuple[str, ...]] = ("analytical_distinct_count",)
    state_name: ClassVar[str] = "analytical:"
    cell_ns: ClassVar[int] = NS_PER_CELL["analytical_distinct"]

    def assess(self, facts: FieldFacts) -> Assessment:
        if facts.values == 0:
            return Assessment("not_applicable", ("no_values",))
        if facts.withheld and not self.settings.sensitive.enabled:
            return Assessment("not_applicable", ("sensitive_exposure",))
        if facts.analytical_distinct is not None:
            return Assessment(
                "satisfied",
                ("distinct_exact",),
                satisfied_by=f"{facts.where}/values/cardinality",
            )
        if facts.long_texts_only:
            return Assessment("not_applicable", ("long_texts_only",))
        if facts.max_length is not None and facts.max_length > COMPACT_MAX_LENGTH:
            return Assessment("not_applicable", ("not_compactable",))
        if not facts.analytical_changed:
            return Assessment("not_applicable", ("stages_unchanged",))
        parameters: dict[str, int | str] = {
            "key": "integer" if facts.technical_type == "integer" else "text"
        }
        if facts.withheld:
            parameters["exposure"] = str(facts.exposure)
        return Assessment("applicable", method="compact_set", parameters=parameters)

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        base = super().estimate(facts, assessment)
        sets = [state for state in base.states if state.key.startswith(EXACT_SET_STATE_PREFIX)]
        # The distinct values the Scan proved are original ones: normalization can merge them,
        # so they bound the analytical count from above only, not from below.
        floor = [
            State(key=state.key, memory=state.memory.model_copy(update={"min": EXACT_SET_FIXED_BYTES}))
            for state in sets
        ]
        return costs(self.cell_ns, [*floor, replay_state(facts), result_state(self.id, facts)])

    def gives_distinct(self, facts: FieldFacts) -> bool:
        return facts.uniqueness_candidate

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # Above the automatic threshold only for an identifier whose uniqueness this count
        # decides (UID-011); below it, asked for or run by a forced pass.
        if facts.uniqueness_candidate and not facts.withheld:
            return Utility(score=AUTOMATIC_IDENTIFIER_SCORE, reasons=["identifier_uniqueness"])
        return Utility(score=40, reasons=["analytical_distinct"])
