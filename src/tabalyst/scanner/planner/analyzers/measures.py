# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The numbers of the values with a currency marker, a percent sign or a unit
(design 20.19, lot 14)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import Analyzer, Assessment, costs, memory
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    replay_state,
    result_state,
)
from tabalyst.scanner.planner.costmodel import (
    GRID_BIN_BYTES,
    MEASURE_ENTRY_BYTES,
    MEASURE_FEW_DISTINCT,
    MEASURE_GROUP_BYTES,
    MEASURE_MEMO_ENTRIES,
    MEASURE_MEMO_ENTRY_BYTES,
    MEASURE_MERGE_BYTES,
    NS_PER_CELL,
    REPLAY_MEMO_ENTRIES,
)
from tabalyst.scanner.planner.facts import (
    MEASURE_DETECTORS,
    UNTRACKED_MARKERS,
    FieldFacts,
    MeasureFacts,
)
from tabalyst.scanner.planner.models import Costs, State, Utility

# The share of the content values a detector must read for its numbers to be
# the field's: the rule of the codes of the numeric block (lot 13).
MEASURE_MIN_SHARE = 0.5


def chosen(facts: FieldFacts) -> MeasureFacts | None:
    """The detector of values with a marker that read the most values of the
    field, the first of ``MEASURE_DETECTORS`` on a tie."""
    if not facts.measures:
        return None
    return max(
        facts.measures,
        key=lambda found: (found.matched, -MEASURE_DETECTORS.index(found.detector)),
    )


def measure_tier(facts: FieldFacts) -> str:
    """The key of ``NS_PER_CELL`` for the extraction of a field: its cost follows
    the distinct values of the field, which the Scan counted or bounded. A field
    whose count was stopped is taken at its estimate, or as wide."""
    distinct = facts.distinct
    if distinct is None:
        known = facts.distinct_estimate or facts.distinct_lower_bound
        distinct = None if known is None else int(known)
    if distinct is None or distinct > MEASURE_MEMO_ENTRIES:
        return "measure_wide"
    return "measure_few" if distinct <= MEASURE_FEW_DISTINCT else "measure"


def measure_memo(cell_ns: int) -> int:
    """The raw strings a route of an extraction remembers: as many as for the
    dates, but for a field of more distinct values than that, whose strings
    would not come back (the tier ``measure_wide``)."""
    if cell_ns >= NS_PER_CELL["measure_wide"]:
        return REPLAY_MEMO_ENTRIES
    return MEASURE_MEMO_ENTRIES


class MeasureExtraction(Analyzer):
    """Extracts the number and the marker of each value with a unit, and gives
    the metrics of a numeric field for the whole field and for each marker, and
    the markers as an enumeration."""

    id: ClassVar[str] = "measure_extraction"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("measures", "histogram", "quantiles", "markers")

    def relevant(self, facts: FieldFacts) -> bool:
        return bool(facts.measures)

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        found = chosen(facts)
        assert found is not None
        if found.matched < MEASURE_MIN_SHARE * facts.values:
            return Assessment("not_applicable", ("low_coverage",))
        settings = self.settings
        return Assessment(
            "applicable",
            method="value_table",
            parameters={
                "detector": found.detector,
                "max_groups": settings.measures.max_groups,
                "max_values": settings.measures.max_values,
                "bins": settings.bins,
            },
            # Every distinct value is in the Scan with its exact count: the
            # numbers follow from them.
            requires_source=not facts.samples_all,
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        parameters = assessment.parameters
        found = next(m for m in facts.measures if m.detector == parameters["detector"])
        distinct = facts.distinct if facts.distinct is not None else facts.values
        entries = min(int(parameters["max_values"]), distinct)
        # The table of the groups, and the one of the whole field that the
        # result merges from them at the end.
        table = State(
            key=f"measures:{facts.where}",
            memory=memory(
                entries * MEASURE_ENTRY_BYTES // 2,
                entries * MEASURE_ENTRY_BYTES,
                entries * (MEASURE_ENTRY_BYTES + MEASURE_MERGE_BYTES),
            ),
        )
        # Values the Scan did not test may bring markers it did not count.
        markers = found.markers
        if found.not_tested:
            markers = min(UNTRACKED_MARKERS, markers + found.not_tested)
        groups = State(
            key=f"measure_groups:{facts.where}",
            memory=memory(
                markers * (MEASURE_GROUP_BYTES + int(parameters["bins"]) * GRID_BIN_BYTES)
            ),
        )
        states = [table, groups, result_state(self.id, facts)]
        nanoseconds = NS_PER_CELL[measure_tier(facts)]
        if assessment.requires_source:
            remembered = measure_memo(nanoseconds)
            if facts.distinct is not None:
                remembered = min(remembered, facts.distinct)
            states.append(replay_state(facts, remembered, MEASURE_MEMO_ENTRY_BYTES))
        return costs(nanoseconds, states)

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        # The Scan counts these values but has no number for them (10.29).
        reasons = ["values_with_unit"]
        if not assessment.requires_source:
            reasons.append("derivable_from_samples")
        return Utility(score=60, reasons=reasons)
