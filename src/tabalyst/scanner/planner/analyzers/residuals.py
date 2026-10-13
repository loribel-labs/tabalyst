# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The values that patterns and detectors leave out (design 20.20, lot 15)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    Analyzer,
    Assessment,
    costs,
    memory,
    set_entry,
    text_length,
)
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    replay_state,
    result_state,
)
from tabalyst.scanner.planner.costmodel import (
    EXACT_SET_FIXED_BYTES,
    EXACT_SET_STATE_PREFIX,
    MEASURE_FEW_DISTINCT,
    MEASURE_MEMO_ENTRIES,
    NS_PER_CELL,
    RESIDUAL_ENTRY_BYTES,
    RESIDUAL_MEMO_ENTRY_BYTES,
    SET_SMALL_ENTRIES,
    SET_SMALL_EXTRA_BYTES,
)
from tabalyst.scanner.planner.facts import DetectorFacts, FieldFacts
from tabalyst.scanner.planner.models import Costs, Memory, State, Utility

# The share of the content values a detector must read for the values it leaves
# out to be those of the field: the rule of the codes and of the units.
RESIDUAL_MIN_SHARE = 0.5
# The name of the pattern among the ``sources`` of a candidate.
PATTERN_SOURCE = "pattern"


def pattern_source(facts: FieldFacts) -> bool:
    """Whether the patterns of a field leave values out, or may: some distinct
    value no pattern holds, or patterns found in a sample."""
    patterns = facts.patterns
    return (
        patterns is not None
        and patterns.status == "complete"
        and patterns.patterns > 0
        and (patterns.other_distinct > 0 or patterns.basis != "all_distinct")
    )


def detector_sources(facts: FieldFacts, limit: int) -> list[DetectorFacts]:
    """The detectors that read most of the field and left values out, the one that
    read the most first, ``limit`` at most."""
    found = [
        detector
        for detector in facts.detectors
        if detector.invalid + detector.not_matched > 0
        and detector.matched + detector.ambiguous >= RESIDUAL_MIN_SHARE * facts.values
    ]
    found.sort(key=lambda detector: (-detector.matched, detector.detector))
    return found[:limit]


def residual_tier(facts: FieldFacts) -> str:
    """The suffix of the keys of ``NS_PER_CELL`` for a field: the cost of a
    pattern and of the replay of a detector follows the distinct values of the
    field, as for the values with a unit. A field whose count was stopped is taken
    at its estimate, or as wide."""
    distinct = facts.distinct
    if distinct is None:
        known = facts.distinct_estimate or facts.distinct_lower_bound
        distinct = None if known is None else int(known)
    if distinct is None or distinct > MEASURE_MEMO_ENTRIES:
        return "_wide"
    return "_few" if distinct <= MEASURE_FEW_DISTINCT else ""


def residual_nanoseconds(facts: FieldFacts, pattern: bool, detectors: int) -> int:
    """What a cell adds: the largest of the parts and 30% of the others, which
    share the reading of the cell."""
    tier = residual_tier(facts)
    parts = [NS_PER_CELL[f"residual{tier}"]] * detectors
    if pattern:
        parts.append(NS_PER_CELL[f"residual_pattern{tier}"])
    parts.sort(reverse=True)
    return parts[0] + round(0.3 * sum(parts[1:]))


class ResidualValues(Analyzer):
    """Keeps the values a pattern or a detector leaves out, with exact counts and
    the first record of each, and gives each candidate pattern an example and its
    distinct values over every occurrence."""

    id: ClassVar[str] = "residual_values"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("residual_values", "pattern_profile")

    def relevant(self, facts: FieldFacts) -> bool:
        return pattern_source(facts) or bool(
            detector_sources(facts, self.settings.residuals.max_detectors)
        )

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        settings = self.settings.residuals
        sources = [PATTERN_SOURCE] if pattern_source(facts) else []
        sources += [d.detector for d in detector_sources(facts, settings.max_detectors)]
        if not sources:
            return Assessment("not_applicable", ("nothing_left_out",))
        return Assessment(
            "applicable",
            method="residual_table",
            parameters={
                "sources": ",".join(sources),
                "max_listed": settings.max_listed,
                "max_tracked": settings.max_tracked,
                "max_value_length": settings.max_value_length,
                "records": int(settings.records),
            },
            # Every distinct value is in the Scan with its exact count: the
            # tables follow from them, but for the records, which only the
            # source holds.
            requires_source=not facts.samples_all or settings.records,
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        parameters = assessment.parameters
        sources = str(parameters["sources"]).split(",")
        pattern = PATTERN_SOURCE in sources
        detectors = len(sources) - pattern
        upper = facts.distinct if facts.distinct is not None else facts.values
        tracked = min(int(parameters["max_tracked"]), upper)
        length = min(int(parameters["max_value_length"]), facts.max_length or 1_000)
        tables = (1 if pattern else 0) + 2 * detectors
        states = [
            State(
                key=f"residuals:{facts.where}",
                memory=memory(
                    0,
                    tables * tracked * (RESIDUAL_ENTRY_BYTES + length) // 8,
                    tables * tracked * (RESIDUAL_ENTRY_BYTES + length),
                ),
            ),
            result_state(self.id, facts),
        ]
        nanoseconds = residual_nanoseconds(facts, pattern, detectors)
        if detectors:
            remembered = min(MEASURE_MEMO_ENTRIES, upper)
            states.append(
                State(
                    key=f"residual_memo:{facts.where}",
                    memory=memory(detectors * remembered * RESIDUAL_MEMO_ENTRY_BYTES),
                )
            )
            if assessment.requires_source:
                states.append(replay_state(facts))
        if pattern:
            # The distinct values each candidate reads, in sets of the run's pool.
            states.append(self._sets(facts, upper))
        return costs(nanoseconds, states)

    @staticmethod
    def _sets(facts: FieldFacts, upper: int) -> State:
        lower = facts.distinct_lower_bound or 0
        expected = min(max(round(facts.distinct_estimate or lower), lower), upper)
        shortest, mean, longest = text_length(facts)
        return State(
            key=f"{EXACT_SET_STATE_PREFIX}residual:{facts.where}",
            memory=Memory(
                min=EXACT_SET_FIXED_BYTES + lower * set_entry("text", shortest)[0],
                expected=EXACT_SET_FIXED_BYTES + expected * set_entry("text", mean)[1],
                max=(
                    EXACT_SET_FIXED_BYTES
                    + upper * set_entry("text", longest)[2]
                    + min(upper, SET_SMALL_ENTRIES) * SET_SMALL_EXTRA_BYTES
                ),
            ),
        )

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # The Scan counts these values and keeps a few examples (10.6).
        reasons = ["values_left_out"]
        if not assessment.requires_source:
            reasons.append("derivable_from_samples")
            return Utility(score=60, reasons=reasons)
        return Utility(score=55, reasons=reasons)
