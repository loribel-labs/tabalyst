# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The numbers of a column described by category over every row (lot 16c)."""

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
from tabalyst.scanner.planner.categorystats import explicit_proposal, explore_dataset
from tabalyst.scanner.planner.costmodel import (
    CODE_FEED_ENTRY_BYTES,
    CODER_BYTES,
    NS_PER_CELL,
    PAIR_FEED_ENTRY_BYTES,
    PAIR_FEED_ROWS,
    RANK_CELL_BYTES,
    RESULT_BYTES,
    STATS_GROUP_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import (
    Budgets,
    Costs,
    ExploredStats,
    State,
    Utility,
)

if TYPE_CHECKING:
    from tabalyst.scanner.secondpass.replay import CellReader

STATS_SEPARATOR = ">"


class CategoryStats(PairAnalyzer):
    """Counts, extremes, mean, spread and a histogram of a numeric column for
    each value of a category, over every row (design 20.23).

    The category is the first field of the candidate, the numeric column its
    ``partner``; the order matters, since the numbers by category are not the
    categories by number. A pair reads the source, but for a complete row sample
    of a CSV file, which is the whole population.
    """

    id: ClassVar[str] = "category_stats"
    outputs: ClassVar[tuple[str, ...]] = (
        "group_counts",
        "group_extremes",
        "group_moments",
        "group_histograms",
        "group_quantiles",
        "correlation_ratio",
    )
    available: ClassVar[bool] = True
    relations: ClassVar[str] = "stats"
    directed: ClassVar[bool] = True
    budget_reason: ClassVar[str] = "stats_budget"

    def automatic_limit(self, budgets: Budgets) -> int:
        return budgets.automatic_stats

    def explore(
        self,
        scan: ScanResult,
        facts: Sequence[FieldFacts],
        requests: Sequence[AnalysisRequest],
        reader: CellReader,
        lenient: bool,
    ) -> tuple[list[PairProposal], list[ExploredStats]]:
        settings = self.settings.stats
        by_dataset: dict[str, list[FieldFacts]] = {}
        for item in facts:
            by_dataset.setdefault(item.dataset, []).append(item)
        datasets: dict[str, DatasetResult] = {dataset.id: dataset for dataset in scan.datasets}
        proposals: list[PairProposal] = []
        blocks: list[ExploredStats] = []
        for dataset in scan.datasets:
            block, listed = explore_dataset(
                dataset, by_dataset.get(dataset.id, []), reader, settings, lenient
            )
            if block is not None:
                blocks.append(block)
            proposals.extend(listed)
        known = {(p.first.dataset, p.first.field, p.second.field) for p in proposals}
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
                key = (dataset_id, first.field, second.field)
                if key in known:
                    continue
                known.add(key)
                proposals.append(
                    explicit_proposal(
                        datasets[dataset_id], first, second, reader, settings, lenient
                    )
                )
        return proposals, blocks

    def matches(self, request: AnalysisRequest, proposal: PairProposal) -> bool:
        """Whether a request concerns the pair: the category then the number, in
        that order."""
        first, second = proposal.first, proposal.second
        if request.dataset not in (None, first.dataset):
            return False
        if request.field is None:
            return True
        if request.field not in (first.field, first.display):
            return False
        return request.partner is None or request.partner in (second.field, second.display)

    def assess_pair(self, proposal: PairProposal, lenient: bool) -> Assessment:
        """A pair applies once its category and its number do. Only a CSV file
        writes the cells of its sample as the reading does."""
        if proposal.reasons:
            return Assessment("not_applicable", proposal.reasons)
        stats = self.settings.stats
        return Assessment(
            "applicable",
            method="group_moments",
            parameters={
                "max_categories": stats.max_categories,
                "bins": stats.bins,
                "strategy": self.settings.bin_strategy,
            },
            requires_source=not (proposal.from_samples and not lenient),
        )

    def estimate_pair(self, proposal: PairProposal, assessment: Assessment) -> Costs:
        """The batch of floats of the number and the codes of the category are
        shared with every pair or table that reads them; the pair holds the
        moments and the bins of each category."""
        category, number = proposal.first, proposal.second
        stats = self.settings.stats
        groups = min(stats.max_categories, category.frequencies_distinct or 0) + 1
        size = groups * (STATS_GROUP_BYTES + stats.bins * RANK_CELL_BYTES)
        key = f"{category.where}{STATS_SEPARATOR}{number.field}"
        states = [
            State(key=f"stats:{key}", memory=memory(size // 8, size // 2, size)),
            State(key=f"result:{self.id}:{key}", memory=memory(RESULT_BYTES)),
        ]
        if assessment.requires_source:
            states.append(
                State(
                    key=f"pearson_feed:{number.where}",
                    memory=memory(PAIR_FEED_ROWS * PAIR_FEED_ENTRY_BYTES),
                )
            )
            states.append(replay_state(number))
            states.append(
                State(
                    key=f"code_feed:{category.where}:category",
                    memory=memory(PAIR_FEED_ROWS * CODE_FEED_ENTRY_BYTES),
                )
            )
            states.append(
                State(key=f"coder:{category.where}:category", memory=memory(CODER_BYTES))
            )
            states.append(replay_state(category))
        return costs(NS_PER_CELL["category_stats"], states)

    def utility_pair(self, proposal: PairProposal) -> Utility:
        """The square root of the corrected correlation ratio on the sample,
        from 0 to 100: a pair is chosen by itself only when it is 0.45 or more."""
        score = getattr(proposal.exploration, "score", None)
        if score is None:
            return Utility(score=0, reasons=["not_explored"])
        return Utility(
            score=min(100, round(score * 100)),
            reasons=["exploratory_correlation_ratio"],
        )
