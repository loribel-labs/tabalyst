# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The order of two dates of the same record, counted over every row (design 20.38)."""

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
    PAIR_STATE_BYTES,
    RESULT_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import (
    Budgets,
    Costs,
    ExploredOrders,
    State,
    Utility,
)
from tabalyst.scanner.planner.orders import explicit_proposal, explore_dataset

if TYPE_CHECKING:
    from tabalyst.scanner.secondpass.replay import CellReader

PAIR_SEPARATOR = ">"


class DateOrder(PairAnalyzer):
    """Counts the records where the first date of a pair is after the second.

    It concerns pairs, not fields: the planner asks ``explore`` for the pairs the
    exploration of the row sample proposes (``planner/orders.py``) or a request
    names. The pair is directed: the first column is the one expected to be on or
    before the other. A pair always reads the source.
    """

    id: ClassVar[str] = "date_order"
    outputs: ClassVar[tuple[str, ...]] = ("date_order", "broken_records")
    available: ClassVar[bool] = True
    relations: ClassVar[str] = "orders"
    directed: ClassVar[bool] = True

    def automatic_limit(self, budgets: Budgets) -> int:
        return self.settings.date_order.automatic_pairs

    def explore(
        self,
        scan: ScanResult,
        facts: Sequence[FieldFacts],
        requests: Sequence[AnalysisRequest],
        reader: CellReader,
        lenient: bool,
    ) -> tuple[list[PairProposal], list[ExploredOrders]]:
        settings = self.settings.date_order
        by_dataset: dict[str, list[FieldFacts]] = {}
        for item in facts:
            by_dataset.setdefault(item.dataset, []).append(item)
        proposals: list[PairProposal] = []
        blocks: list[ExploredOrders] = []
        for dataset in scan.datasets:
            block, listed = explore_dataset(dataset, by_dataset.get(dataset.id, []), reader, settings)
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
                if (dataset_id, first.field, second.field) in known:
                    continue
                known.add((dataset_id, first.field, second.field))
                proposals.append(
                    explicit_proposal(datasets[dataset_id], first, second, reader, settings)
                )
        return proposals, blocks

    def matches(self, request: AnalysisRequest, proposal: PairProposal) -> bool:
        """Whether a request concerns the pair: the first column is the earlier one
        in a request that names both."""
        first, second = proposal.first, proposal.second
        if request.dataset not in (None, first.dataset):
            return False
        if request.field is None:
            return True
        if request.partner is None:
            return request.field in (first.field, first.display, second.field, second.display)
        return request.field in (first.field, first.display) and request.partner in (
            second.field,
            second.display,
        )

    def assess_pair(self, proposal: PairProposal, lenient: bool) -> Assessment:
        """A pair of date columns is applicable unless a column cannot be counted by
        record number: a record the Scan left out, or a path that repeats."""
        if proposal.reasons:
            return Assessment("not_applicable", proposal.reasons)
        first, second = proposal.first, proposal.second
        if first.records_excluded or second.records_excluded:
            return Assessment("not_applicable", ("records_excluded",))
        return Assessment(
            "applicable",
            method="compare",
            parameters={"max_listed": self.settings.date_order.max_listed},
            requires_source=True,
        )

    def estimate_pair(self, proposal: PairProposal, assessment: Assessment) -> Costs:
        """The reading of the cells of the two columns and a small counter."""
        first, second = proposal.first, proposal.second
        where = f"{first.where}{PAIR_SEPARATOR}{second.field}"
        states = [
            State(key=f"date_order:{where}", memory=memory(PAIR_STATE_BYTES)),
            State(key=f"result:{self.id}:{where}", memory=memory(RESULT_BYTES)),
            replay_state(first),
            replay_state(second),
        ]
        return costs(NS_PER_CELL["date_order"], states)

    def utility_pair(self, proposal: PairProposal) -> Utility:
        """The share of the sampled rows where the order holds, from 0 to 100: a
        pair is chosen by itself from 45, and the exploration lists none below the
        share the settings ask for."""
        exploration = proposal.exploration
        score = getattr(exploration, "score", None)
        if score is None:
            return Utility(score=0, reasons=["not_explored"])
        return Utility(score=min(100, round(score * 100)), reasons=["ordered_dates"])
