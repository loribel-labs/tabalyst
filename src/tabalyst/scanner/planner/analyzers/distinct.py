# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact distinct count of a field whose scan stopped tracking it (lot 7b)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    COMPACT_MAX_LENGTH,
    Analyzer,
    Assessment,
    costs,
    set_entry,
    text_length,
)
from tabalyst.scanner.planner.analyzers.common import (
    name_suggests_identifier,
    result_state,
    uniqueness,
)
from tabalyst.scanner.planner.costmodel import (
    EXACT_SET_FIXED_BYTES,
    EXACT_SET_STATE_PREFIX,
    NS_PER_CELL,
    SET_SMALL_ENTRIES,
    SET_SMALL_EXTRA_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, Memory, State, Utility


class ExactDistinct(Analyzer):
    """The memory is a set of the original values: at least the values the scan
    proved distinct, about the KMV estimate, at most every value read.

    ``key`` is the key that the expected values take: ``integer`` (a string of
    digits or a JSON integer, held as an integer) or ``text``. The firm bound
    always charges a text, since a value that does not fit the compact key goes
    to the generic set of texts (design 20.8).
    """

    id: ClassVar[str] = "exact_distinct"
    outputs: ClassVar[tuple[str, ...]] = ("distinct_count", "uniqueness")
    available: ClassVar[bool] = True
    # Names the set of the analysis in the plan, so two analyses of one field hold two sets.
    state_name: ClassVar[str] = ""
    cell_ns: ClassVar[int] = NS_PER_CELL["distinct_set"]

    def relevant(self, facts: FieldFacts) -> bool:
        return True

    def assess(self, facts: FieldFacts) -> Assessment:
        # Decision O61: a count says nothing of a value, so a masked or hidden field
        # may be counted, whose result is two numbers; it is off until
        # ``deep.sensitive.enabled`` is set.
        if facts.values == 0:
            return Assessment("not_applicable", ("no_values",))
        if facts.withheld and not self.settings.sensitive.enabled:
            return Assessment("not_applicable", ("sensitive_exposure",))
        if facts.cardinality == "complete":
            return Assessment(
                "satisfied",
                ("distinct_exact",),
                satisfied_by=f"{facts.where}/values/cardinality",
            )
        if facts.long_texts_only:
            return Assessment("not_applicable", ("long_texts_only",))
        if facts.max_length is not None and facts.max_length > COMPACT_MAX_LENGTH:
            return Assessment("not_applicable", ("not_compactable",))
        key = "integer" if facts.technical_type == "integer" else "text"
        parameters: dict[str, int | str] = {"key": key}
        if facts.withheld:
            # Part of the key of the result, and of the plan that tells it.
            parameters["exposure"] = str(facts.exposure)
        return Assessment("applicable", method="compact_set", parameters=parameters)

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        lower = facts.distinct_lower_bound or 0
        estimate = facts.distinct_estimate
        maximum = max(facts.values, lower)
        expected = lower if estimate is None else min(max(round(estimate), lower), maximum)
        key = str(assessment.parameters["key"])
        shortest, mean, longest = text_length(facts)
        size = Memory(
            min=EXACT_SET_FIXED_BYTES + lower * set_entry(key, shortest)[0],
            expected=EXACT_SET_FIXED_BYTES + expected * set_entry(key, mean)[1],
            max=(
                EXACT_SET_FIXED_BYTES
                + maximum * set_entry("text", longest)[2]
                + min(maximum, SET_SMALL_ENTRIES) * SET_SMALL_EXTRA_BYTES
            ),
        )
        return costs(
            self.cell_ns,
            [
                State(key=f"{EXACT_SET_STATE_PREFIX}{self.state_name}{facts.where}", memory=size),
                result_state(self.id, facts),
            ],
        )

    def gives_distinct(self, facts: FieldFacts) -> bool:
        # The original count is the analytical one only when no stage changed a value.
        return facts.uniqueness_candidate and not facts.analytical_changed

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        if facts.withheld:
            # Below the automatic threshold: a sensitive field is counted when asked for.
            return Utility(score=40, reasons=["exposure_counts"])
        score = 20
        reasons: list[str] = []
        share = uniqueness(facts)
        if share is not None and share >= 0.9:
            score += 40
            reasons.append("near_unique")
        elif share is not None and share >= 0.5:
            score += 20
            reasons.append("near_unique")
        if name_suggests_identifier(facts.name):
            score += 25
            reasons.append("identifier_name")
        if assessment.parameters.get("key") == "integer":
            score += 10
            reasons.append("integer_key")
        return Utility(score=min(score, 100), reasons=reasons or ["base_value"])
