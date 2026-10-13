# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The repeated values of an identifier (design 20.21, lot 15)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.planner.analyzer import (
    AnalysisRequest,
    Assessment,
    PairAnalyzer,
    PairProposal,
    costs,
    memory,
    text_length,
)
from tabalyst.scanner.planner.analyzers.common import (
    blocked,
    name_suggests_identifier,
    replay_state,
    result_state,
    uniqueness,
)
from tabalyst.scanner.planner.costmodel import (
    DUPLICATE_ENTRY_BYTES,
    EXACT_SET_FIXED_BYTES,
    EXACT_SET_STATE_PREFIX,
    NS_PER_CELL,
    PAIR_FEED_ENTRY_BYTES,
    PAIR_FEED_ROWS,
    RESIDUAL_ENTRY_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import (
    Budgets,
    Costs,
    ExploredDataset,
    Memory,
    State,
    Utility,
)

if TYPE_CHECKING:
    from tabalyst.scanner.secondpass.replay import CellReader

# The technical types an identifier has; a decimal number or a date is no key.
IDENTIFIER_TYPES = frozenset({"text", "integer", "mixed"})
# The share of distinct values from which a column is a candidate identifier, and
# the one a name that suggests an identifier is enough for.
NEAR_UNIQUE = 0.9
NAMED_UNIQUE = 0.5


def identifier_candidate(facts: FieldFacts) -> bool:
    """Whether the values of the field are almost all different (or half of them,
    under a name that suggests an identifier): a repeated one is then worth a
    mention."""
    if facts.technical_type not in IDENTIFIER_TYPES:
        return False
    share = uniqueness(facts)
    if share is None:
        return False
    return share >= NEAR_UNIQUE or (share >= NAMED_UNIQUE and name_suggests_identifier(facts.name))


class DuplicatesReport(PairAnalyzer):
    """Lists the values found more than once in a column that looks like an
    identifier, with their counts and, when the source is read, their first
    record."""

    id: ClassVar[str] = "duplicates_report"
    available: ClassVar[bool] = True
    outputs: ClassVar[tuple[str, ...]] = ("duplicates", "uniqueness")
    relations: ClassVar[str] = "keys"
    per_field: ClassVar[bool] = True

    def relevant(self, facts: FieldFacts) -> bool:
        return identifier_candidate(facts)

    def assess(self, facts: FieldFacts) -> Assessment:
        stop = blocked(facts)
        if stop is not None:
            return stop
        if facts.long_texts_only:
            return Assessment("not_applicable", ("long_texts_only",))
        if facts.cardinality == "complete" and facts.distinct == facts.values:
            return Assessment(
                "satisfied",
                ("all_distinct",),
                satisfied_by=f"{facts.where}/values/cardinality",
            )
        settings = self.settings.duplicates
        return Assessment(
            "applicable",
            method="digest_table",
            parameters={
                "max_listed": settings.max_listed,
                "max_tracked": settings.max_tracked,
                "records": int(settings.records),
            },
            # Every distinct value is in the Scan with its exact count: the
            # repeated ones follow from them, but for the records.
            requires_source=not facts.samples_all or settings.records,
        )

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        parameters = assessment.parameters
        distinct = facts.distinct if facts.distinct is not None else facts.values
        tracked = min(int(parameters["max_tracked"]), facts.values)
        _, mean, longest = text_length(facts)
        table = Memory(
            min=0,
            expected=tracked * (RESIDUAL_ENTRY_BYTES + mean) // 8,
            max=tracked * (RESIDUAL_ENTRY_BYTES + longest),
        )
        states = [State(key=f"duplicates:{facts.where}", memory=table), result_state(self.id, facts)]
        nanoseconds = NS_PER_CELL["duplicates"]
        if assessment.requires_source:
            lower = facts.distinct_lower_bound or 0
            low, expected, high = DUPLICATE_ENTRY_BYTES
            # The digests of every distinct value, in the pool of the run's sets.
            states.append(
                State(
                    key=f"{EXACT_SET_STATE_PREFIX}duplicates:{facts.where}",
                    memory=Memory(
                        min=EXACT_SET_FIXED_BYTES + lower * low,
                        expected=EXACT_SET_FIXED_BYTES + min(distinct, facts.values) * expected,
                        max=EXACT_SET_FIXED_BYTES + facts.values * high,
                    ),
                )
            )
        return costs(nanoseconds, states)

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        reasons = ["repeated_identifier"]
        if name_suggests_identifier(facts.name):
            reasons.append("identifier_name")
        if not assessment.requires_source:
            reasons.append("derivable_from_samples")
            return Utility(score=60, reasons=reasons)
        return Utility(score=55, reasons=reasons)

    # A combination of two columns (a key), asked for by name ----------------

    def automatic_limit(self, budgets: Budgets) -> int:
        """The planner never picks a combination by itself: there is no telling
        which columns make a key, and the search is not free."""
        return 0

    def explore(
        self,
        scan: ScanResult,
        facts: Sequence[FieldFacts],
        requests: Sequence[AnalysisRequest],
        reader: CellReader,
        lenient: bool,
    ) -> tuple[list[PairProposal], list[ExploredDataset]]:
        """The combinations a request names, and nothing else: it reads no sample
        (``reader`` and ``lenient`` do not matter for a key)."""
        by_dataset: dict[str, list[FieldFacts]] = {}
        for item in facts:
            by_dataset.setdefault(item.dataset, []).append(item)
        proposals: list[PairProposal] = []
        known: set[tuple[str, str, str]] = set()
        for request in requests:
            if request.analyzer != self.id or request.field is None or request.partner is None:
                continue
            for dataset_id, members in by_dataset.items():
                if request.dataset not in (None, dataset_id):
                    continue
                first = next((f for f in members if request.field in (f.field, f.display)), None)
                second = next(
                    (f for f in members if request.partner in (f.field, f.display)), None
                )
                if first is None or second is None:
                    continue
                if members.index(first) > members.index(second):
                    first, second = second, first
                if (dataset_id, first.field, second.field) in known:
                    continue
                known.add((dataset_id, first.field, second.field))
                reasons: tuple[str, ...] = ()
                if first.withheld or second.withheld:
                    reasons = ("sensitive_exposure",)
                elif first.repeated or second.repeated:
                    reasons = ("repeated_field",)
                proposals.append(PairProposal(first, second, None, reasons=reasons))
        return proposals, []

    def matches(self, request: AnalysisRequest, proposal: PairProposal) -> bool:
        """Whether a request for combinations concerns the pair (in either order)."""
        first, second = proposal.first, proposal.second
        if request.dataset not in (None, first.dataset):
            return False
        if request.field is None or request.partner is None:
            return False
        members = ({first.field, first.display}, {second.field, second.display})
        return (request.field in members[0] and request.partner in members[1]) or (
            request.field in members[1] and request.partner in members[0]
        )

    def assess_pair(self, proposal: PairProposal, lenient: bool) -> Assessment:
        """Always applicable but for a withheld or repeated column."""
        if proposal.reasons:
            return Assessment("not_applicable", proposal.reasons)
        settings = self.settings.duplicates
        return Assessment(
            "applicable",
            method="digest_table",
            parameters={"max_listed": settings.max_listed, "max_tracked": settings.max_tracked},
            # The row sample of the Scan holds too few rows to answer.
            requires_source=True,
        )

    def estimate_pair(self, proposal: PairProposal, assessment: Assessment) -> Costs:
        """The digests of every row in the pool of the run, and the feed of each column."""
        first, second = proposal.first, proposal.second
        rows = min(first.values, second.values)
        tracked = min(int(assessment.parameters["max_tracked"]), rows)
        longest = sum(text_length(column)[2] for column in (first, second))
        _, expected, high = DUPLICATE_ENTRY_BYTES
        name = f"{first.where}+{second.field}"
        states = [
            State(
                key=f"duplicates:{name}",
                memory=Memory(
                    min=0,
                    expected=tracked * (RESIDUAL_ENTRY_BYTES + longest // 2) // 8,
                    max=tracked * (RESIDUAL_ENTRY_BYTES + longest),
                ),
            ),
            State(key=f"result:{self.id}:{name}", memory=memory(1_024)),
            State(
                key=f"{EXACT_SET_STATE_PREFIX}duplicates:{name}",
                memory=Memory(
                    min=EXACT_SET_FIXED_BYTES,
                    expected=EXACT_SET_FIXED_BYTES + rows * expected,
                    max=EXACT_SET_FIXED_BYTES + rows * high,
                ),
            ),
        ]
        for column in (first, second):
            states.append(
                State(
                    key=f"duplicates_feed:{column.where}",
                    memory=memory(PAIR_FEED_ROWS * PAIR_FEED_ENTRY_BYTES),
                )
            )
            states.append(replay_state(column))
        return costs(NS_PER_CELL["duplicates_key"], states)

    def utility_pair(self, proposal: PairProposal) -> Utility:
        """Zero: a combination is chosen by a request, never by the planner."""
        return Utility(score=0, reasons=["requested_only"])
