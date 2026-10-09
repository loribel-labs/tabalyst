# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validation of the inferred patterns of a field against every value."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    Analyzer,
    Assessment,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import result_state
from tabalyst.scanner.planner.costmodel import (
    COUNTER_BYTES,
    MATCHER_BYTES,
    NS_PER_CELL,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, State, Utility

_REASONS = {
    "exposure": "sensitive_exposure",
    "samples_withheld": "sensitive_exposure",
    "long_texts_only": "long_texts_only",
    "no_values": "no_values",
    "too_few_distinct": "too_few_distinct",
}


class PatternValidation(Analyzer):
    """The patterns of the Scan come from a sample of the distinct values and
    their shares count distinct values: this counts every occurrence (PAT-07)."""

    id: ClassVar[str] = "pattern_validation"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("pattern_counts", "unmatched")

    def relevant(self, facts: FieldFacts) -> bool:
        patterns = facts.patterns
        return patterns is not None and not (
            patterns.status == "not_applicable" and patterns.reason == "technical_type"
        )

    def assess(self, facts: FieldFacts) -> Assessment:
        patterns = facts.patterns
        if patterns is None:
            return Assessment("not_applicable", ("patterns_unavailable",))
        if patterns.status == "failed":
            return Assessment("not_applicable", ("patterns_unavailable",))
        if patterns.status == "not_applicable":
            reason = _REASONS.get(patterns.reason or "", "patterns_unavailable")
            return Assessment("not_applicable", (reason,))
        if patterns.candidates == 0:
            return Assessment("not_applicable", ("no_candidates",))
        return Assessment(
            "applicable",
            method="compiled_matcher",
            parameters={"patterns": patterns.candidates},
            # When the inference read every distinct value, each is in the
            # samples with its exact count: the occurrences follow from them.
            requires_source=patterns.basis != "all_distinct",
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        count = int(assessment.parameters["patterns"])
        # One counter and one matcher per candidate, and a counter for the rest.
        size = count * (COUNTER_BYTES + MATCHER_BYTES) + COUNTER_BYTES
        # A value is tried against every candidate (the overlaps are counted).
        nanoseconds = NS_PER_CELL["matcher_base"] + count * NS_PER_CELL["matcher"]
        return costs(
            nanoseconds,
            [State(key=f"patterns:{facts.where}", memory=memory(size)), result_state(self.id, facts)],
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        patterns = facts.patterns
        assert patterns is not None
        if not assessment.requires_source:
            return Utility(score=50, reasons=["derivable_from_samples"])
        score = 40
        reasons: list[str] = []
        if patterns.basis == "sample":
            score += 20
            reasons.append("candidates_unvalidated")
        if patterns.other_distinct > 0:
            score += 10
            reasons.append("values_outside_candidates")
        return Utility(score=score, reasons=reasons or ["base_value"])
