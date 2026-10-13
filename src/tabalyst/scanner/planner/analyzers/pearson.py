# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pearson correlation of a pair of numeric columns over every row (lot 8a)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

from tabalyst.scanner.models import DatasetResult, ScanResult
from tabalyst.scanner.planner.analyzer import (
    AnalysisRequest,
    Assessment,
    PairAnalyzer,
    PairProposal,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import replay_state
from tabalyst.scanner.planner.costmodel import (
    NS_PER_CELL,
    PAIR_FEED_ENTRY_BYTES,
    PAIR_FEED_ROWS,
    PAIR_STATE_BYTES,
    RANK_CELL_BYTES,
    RESULT_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import (
    Budgets,
    Costs,
    ExploredDataset,
    State,
    Utility,
)
from tabalyst.scanner.planner.relations import (
    effective_score,
    explicit_proposal,
    explore_dataset,
)

if TYPE_CHECKING:
    from tabalyst.scanner.secondpass.replay import CellReader

PAIR_SEPARATOR = "+"


class PearsonCorrelation(PairAnalyzer):
    """Counts the common rows of a pair and gives their coefficient (REL-07).

    It concerns pairs, not fields: the planner asks ``explore`` for the pairs
    the exploration (``planner/relations.py``) proposes or a request names. A
    pair reads the source, but for a complete row sample of a CSV file, which is
    the whole population (design 20.12).
    """

    id: ClassVar[str] = "pearson_correlation"
    # 2: the result also holds the line (slope, intercept) and the rank
    # correlation (design 20.22).
    version: ClassVar[int] = 2
    outputs: ClassVar[tuple[str, ...]] = (
        "correlation",
        "common_rows",
        "exclusions",
        "regression_line",
        "rank_correlation",
    )
    available: ClassVar[bool] = True
    relations: ClassVar[str] = "datasets"

    def automatic_limit(self, budgets: Budgets) -> int:
        return budgets.automatic_pairs

    def explore(
        self,
        scan: ScanResult,
        facts: Sequence[FieldFacts],
        requests: Sequence[AnalysisRequest],
        reader: CellReader,
        lenient: bool,
    ) -> tuple[list[PairProposal], list[ExploredDataset]]:
        settings = self.settings.pearson
        by_dataset: dict[str, list[FieldFacts]] = {}
        for item in facts:
            by_dataset.setdefault(item.dataset, []).append(item)
        proposals: list[PairProposal] = []
        blocks: list[ExploredDataset] = []
        for dataset in scan.datasets:
            block, listed = explore_dataset(
                dataset, by_dataset.get(dataset.id, []), reader, settings, lenient
            )
            if block is not None:
                blocks.append(block)
            proposals.extend(listed)
        known = {(p.first.dataset, p.first.field, p.second.field) for p in proposals}
        datasets: dict[str, DatasetResult] = {dataset.id: dataset for dataset in scan.datasets}
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
                proposals.append(
                    explicit_proposal(
                        datasets[dataset_id], first, second, reader, settings, lenient
                    )
                )
        return proposals, blocks

    def matches(self, request: AnalysisRequest, proposal: PairProposal) -> bool:
        """Whether a request for pairs concerns the pair (in either order)."""
        first, second = proposal.first, proposal.second
        if request.dataset not in (None, first.dataset):
            return False
        if request.field is None:
            return True
        members = ({first.field, first.display}, {second.field, second.display})
        if request.partner is None:
            return any(request.field in member for member in members)
        return (request.field in members[0] and request.partner in members[1]) or (
            request.field in members[1] and request.partner in members[0]
        )

    def assess_pair(self, proposal: PairProposal, lenient: bool) -> Assessment:
        """A pair is always applicable once its columns are numbers. Only a CSV
        file writes the cells of its sample as the reading does."""
        if proposal.reasons:
            return Assessment("not_applicable", proposal.reasons)
        return Assessment(
            "applicable",
            method="pairwise_complete",
            parameters={
                "min_pairs": self.settings.pearson.min_pairs,
                "rank_bins": self.settings.pearson.rank_bins,
            },
            requires_source=not (proposal.from_samples and not lenient),
        )

    def estimate_pair(self, proposal: PairProposal, assessment: Assessment) -> Costs:
        """The common batch of floats of each column is shared by every pair
        that uses it, and the reading of its cells too."""
        first, second = proposal.first, proposal.second
        bins = self.settings.pearson.rank_bins
        states = [
            State(
                key=f"pearson_pair:{first.where}{PAIR_SEPARATOR}{second.field}",
                memory=memory(PAIR_STATE_BYTES),
            ),
            State(
                key=f"result:{self.id}:{first.where}{PAIR_SEPARATOR}{second.field}",
                memory=memory(RESULT_BYTES),
            ),
        ]
        if bins:
            states.append(
                State(
                    key=f"rank_grid:{first.where}{PAIR_SEPARATOR}{second.field}",
                    memory=memory(bins * bins * RANK_CELL_BYTES // 4, bins * bins * RANK_CELL_BYTES // 2, bins * bins * RANK_CELL_BYTES),
                )
            )
        if assessment.requires_source:
            for column in (first, second):
                states.append(
                    State(
                        key=f"pearson_feed:{column.where}",
                        memory=memory(PAIR_FEED_ROWS * PAIR_FEED_ENTRY_BYTES),
                    )
                )
                states.append(replay_state(column))
        return costs(NS_PER_CELL["pearson"], states)

    def utility_pair(self, proposal: PairProposal) -> Utility:
        """The lower bound of the absolute coefficient on the sample, from 0 to
        100: a pair is chosen by itself only when that bound is 0.45 or more."""
        exploration = proposal.exploration
        rated = None if exploration is None else effective_score(exploration)  # type: ignore[arg-type]
        if rated is None:
            return Utility(score=0, reasons=["not_explored"])
        return Utility(
            score=min(100, round(rated * 100)),
            reasons=["exploratory_correlation"],
        )
