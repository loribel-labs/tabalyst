# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validation of the hierarchy of patterns of a field against every value (design 20.9)."""

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
    DISTINCT_ENTRY_BYTES,
    NS_PER_CELL,
    PATTERN_CELL_BYTES,
    READER_NODE_BYTES,
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
# Fields the discovery does not assess as text (booleans, structures) or reads
# as measures (design 18.12), and empty fields: no pattern is ever validated
# there, so the analysis is not listed for them.
_IRRELEVANT = frozenset(
    {"booleans_only", "structures_only", "small_integers", "decimal_numbers"}
)


class PatternValidation(Analyzer):
    """The patterns of the Scan come from a sample of the distinct values and
    their shares count distinct values: this counts every occurrence (PAT-07)."""

    id: ClassVar[str] = "pattern_validation"
    # 2: the hierarchy of families, patterns and nodes (Patterns lot P6); the flat
    # candidates of the lot 7c were version 1.
    version: ClassVar[int] = 2
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("pattern_counts", "unmatched")

    def relevant(self, facts: FieldFacts) -> bool:
        patterns = facts.patterns
        return (
            patterns is not None
            and facts.technical_type != "empty"
            and not (patterns.status == "not_applicable" and patterns.reason in _IRRELEVANT)
        )

    def assess(self, facts: FieldFacts) -> Assessment:
        patterns = facts.patterns
        if patterns is None:
            return Assessment("not_applicable", ("patterns_unavailable",))
        if patterns.status == "failed":
            return Assessment("not_applicable", ("patterns_unavailable",))
        if patterns.status == "not_applicable":
            reason = _REASONS.get(patterns.reason or "", "not_eligible")
            return Assessment("not_applicable", (reason,))
        if patterns.patterns == 0:
            return Assessment("not_applicable", ("no_candidates",))
        settings = self.settings.patterns
        return Assessment(
            "applicable",
            method="family_recognizer",
            parameters={
                "patterns": patterns.patterns,
                "nodes": patterns.nodes,
                "facets": patterns.facets,
                "table_bytes": settings.table_bytes,
                "distinct_bytes": settings.distinct_bytes,
                # What made the tree the validation counts (FR-020): another grammar,
                # algorithm or discovery setting is another analysis.
                "grammar_version": patterns.grammar_version,
                "algorithm_version": patterns.algorithm_version,
                "discovery_sha256": patterns.settings_sha256,
            },
            # When the inference read every distinct value, each is in the
            # samples with its exact count: the occurrences follow from them.
            requires_source=patterns.basis != "all_distinct",
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        parameters = assessment.parameters
        nodes = int(parameters["nodes"])
        facets = int(parameters["facets"])
        # The reader and the counters of the patterns and nodes, a table for each
        # facet, and, when the source is read, the set of the distinct values.
        size = nodes * (READER_NODE_BYTES + 3 * COUNTER_BYTES) + COUNTER_BYTES
        # A table cannot hold more cells than the field has distinct values.
        upper = facts.distinct if facts.distinct is not None else facts.values
        tables = facets * min(int(parameters["table_bytes"]), upper * PATTERN_CELL_BYTES)
        distinct = 0
        if assessment.requires_source:
            entry = DISTINCT_ENTRY_BYTES + (facts.max_length or 0)
            distinct = min(int(parameters["distinct_bytes"]), upper * entry)
        # A value is read once, whatever the number of patterns and nodes: the
        # work is its structure and one table lookup for each facet.
        nanoseconds = NS_PER_CELL["pattern_family"] + facets * NS_PER_CELL["pattern_facet"]
        return costs(
            nanoseconds,
            [
                State(
                    key=f"patterns:{facts.where}",
                    memory=memory(size, size + tables // 8 + distinct // 8, size + tables + distinct),
                ),
                result_state(self.id, facts),
            ],
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
