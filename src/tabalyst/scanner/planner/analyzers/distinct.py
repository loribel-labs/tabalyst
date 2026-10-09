# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact distinct count of a field whose scan stopped tracking it."""

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
    blocked,
    name_suggests_identifier,
    result_state,
    uniqueness,
)
from tabalyst.scanner.planner.costmodel import NS_PER_CELL
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, Memory, State, Utility


class ExactDistinct(Analyzer):
    """The memory is a set of the original values: at least the values the scan
    proved distinct, about the KMV estimate, at most every value read."""

    id: ClassVar[str] = "exact_distinct"
    outputs: ClassVar[tuple[str, ...]] = ("distinct_count", "uniqueness")

    def relevant(self, facts: FieldFacts) -> bool:
        return True

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
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
        return Assessment("applicable", method="compact_set", parameters={"key": key})

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        lower = facts.distinct_lower_bound or 0
        estimate = facts.distinct_estimate
        maximum = max(facts.values, lower)
        expected = lower if estimate is None else min(max(round(estimate), lower), maximum)
        key = str(assessment.parameters["key"])
        shortest, mean, longest = text_length(facts)
        size = Memory(
            min=lower * set_entry(key, shortest)[0],
            expected=expected * set_entry(key, mean)[1],
            max=maximum * set_entry(key, longest)[2],
        )
        return costs(
            NS_PER_CELL["distinct_set"],
            [State(key=f"exact_set:{facts.where}", memory=size), result_state(self.id, facts)],
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
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
