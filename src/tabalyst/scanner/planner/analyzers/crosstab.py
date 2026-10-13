# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Table of a category against a feature of another column (lot 8b)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, ClassVar

from tabalyst.scanner.features import FEATURES
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
    CODE_FEED_ENTRY_BYTES,
    CODER_BYTES,
    NS_PER_CELL,
    PAIR_FEED_ROWS,
    RESULT_BYTES,
    TABLE_CELL_BYTES,
    TABLE_EXAMPLE_BYTES,
)
from tabalyst.scanner.planner.crosstabs import explicit_proposals, explore_dataset
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import (
    Budgets,
    Costs,
    ExploredTables,
    State,
    Utility,
)

if TYPE_CHECKING:
    from tabalyst.scanner.secondpass.replay import CellReader

TABLE_SEPARATOR = ">"


class CategoryCrosstab(PairAnalyzer):
    """Counts the rows of every category by class of a feature of another
    column, over every row (REL-11 to REL-15).

    The category is the first field of the candidate, the column of the feature
    its ``partner``; the order matters, since the purity of a category is not the
    purity of a class. A table reads the source, but for a complete row sample of
    a CSV file, which is the whole population (design 20.13).
    """

    id: ClassVar[str] = "category_crosstab"
    outputs: ClassVar[tuple[str, ...]] = (
        "contingency_table",
        "conditional_coverage",
        "purity",
        "association",
        "exceptions",
        "candidate_rules",
    )
    available: ClassVar[bool] = True
    relations: ClassVar[str] = "tables"
    features: ClassVar[bool] = True
    directed: ClassVar[bool] = True
    budget_reason: ClassVar[str] = "tables_budget"

    def automatic_limit(self, budgets: Budgets) -> int:
        return budgets.automatic_tables

    def explore(
        self,
        scan: ScanResult,
        facts: Sequence[FieldFacts],
        requests: Sequence[AnalysisRequest],
        reader: CellReader,
        lenient: bool,
    ) -> tuple[list[PairProposal], list[ExploredTables]]:
        settings = self.settings.crosstab
        by_dataset: dict[str, list[FieldFacts]] = {}
        for item in facts:
            by_dataset.setdefault(item.dataset, []).append(item)
        datasets: dict[str, DatasetResult] = {dataset.id: dataset for dataset in scan.datasets}
        proposals: list[PairProposal] = []
        blocks: list[ExploredTables] = []
        for dataset in scan.datasets:
            block, listed = explore_dataset(
                scan, dataset, by_dataset.get(dataset.id, []), reader, settings
            )
            if block is not None:
                blocks.append(block)
            proposals.extend(listed)
        known = {
            (p.first.dataset, p.first.field, p.second.field, p.feature) for p in proposals
        }
        for request in requests:
            if request.analyzer != self.id or request.field is None or request.partner is None:
                continue
            wanted = FEATURES if request.feature is None else (request.feature,)
            for dataset_id, members in by_dataset.items():
                if request.dataset not in (None, dataset_id):
                    continue
                first = next((f for f in members if request.field in (f.field, f.display)), None)
                second = next(
                    (f for f in members if request.partner in (f.field, f.display)), None
                )
                if first is None or second is None:
                    continue
                for proposal in explicit_proposals(
                    scan, datasets[dataset_id], first, second, wanted, reader, settings
                ):
                    key = (dataset_id, first.field, second.field, proposal.feature)
                    if key in known:
                        continue
                    known.add(key)
                    proposals.append(proposal)
        return [self._with_rules(proposal, requests) for proposal in proposals], blocks

    def _with_rules(
        self, proposal: PairProposal, requests: Sequence[AnalysisRequest]
    ) -> PairProposal:
        """The proposal with the rules that requests gave for its table."""
        rules = {
            rule
            for request in requests
            if request.analyzer == self.id and request.rules and self.matches(request, proposal)
            for rule in request.rules
        }
        return replace(proposal, rules=tuple(sorted(rules))) if rules else proposal

    def matches(self, request: AnalysisRequest, proposal: PairProposal) -> bool:
        """Whether a request concerns the table: the category, the column and the
        feature it names, in that order."""
        first, second = proposal.first, proposal.second
        if request.dataset not in (None, first.dataset):
            return False
        if request.feature not in (None, proposal.feature):
            return False
        if request.field is None:
            return True
        if request.field not in (first.field, first.display):
            return False
        return request.partner is None or request.partner in (second.field, second.display)

    def assess_pair(self, proposal: PairProposal, lenient: bool) -> Assessment:
        """A table applies once its category and its column do. Only a CSV file
        writes the cells of its sample as the reading does."""
        if proposal.reasons:
            return Assessment("not_applicable", proposal.reasons)
        crosstab = self.settings.crosstab
        feature = proposal.feature or ""
        parameters: dict[str, int | str] = {
            "feature": feature,
            "max_categories": crosstab.max_categories,
            "examples": crosstab.examples,
            "max_exception_cells": crosstab.max_exception_cells,
            "rule_purity": crosstab.rule_purity,
            "rule_support": crosstab.rule_support,
        }
        if feature in ("length", "prefix", "value"):
            parameters["max_classes"] = crosstab.max_classes
        if proposal.rules:
            parameters["rules"] = json.dumps(
                proposal.rules, ensure_ascii=False, separators=(",", ":")
            )
        if feature == "prefix":
            parameters["prefix_length"] = crosstab.prefix_length
        return Assessment(
            "applicable",
            method="contingency_table",
            parameters=parameters,
            requires_source=not (proposal.from_samples and not lenient),
        )

    def estimate_pair(self, proposal: PairProposal, assessment: Assessment) -> Costs:
        """The batch of codes of each column is shared by every table that uses
        it; the table holds its counters and the examples of its exceptions."""
        category, column, feature = proposal.first, proposal.second, proposal.feature or ""
        crosstab = self.settings.crosstab
        rows = min(crosstab.max_categories, category.frequencies_distinct or 0) + 1
        if feature == "pattern":
            patterns = column.patterns.patterns if column.patterns is not None else 0
            width = patterns + 1
        else:
            width = crosstab.max_classes
        size = rows * width * (TABLE_CELL_BYTES + crosstab.examples * TABLE_EXAMPLE_BYTES)
        key = f"{category.where}{TABLE_SEPARATOR}{column.field}:{feature}"
        states = [
            State(key=f"crosstab:{key}", memory=memory(size // 8, size // 2, size)),
            State(key=f"result:{self.id}:{key}", memory=memory(RESULT_BYTES)),
        ]
        if assessment.requires_source:
            for kind, facts in (("category", category), (feature, column)):
                states.append(
                    State(
                        key=f"code_feed:{facts.where}:{kind}",
                        memory=memory(PAIR_FEED_ROWS * CODE_FEED_ENTRY_BYTES),
                    )
                )
                states.append(State(key=f"coder:{facts.where}:{kind}", memory=memory(CODER_BYTES)))
                states.append(replay_state(facts))
        return costs(NS_PER_CELL.get(f"crosstab_{feature}", NS_PER_CELL["crosstab_pattern"]), states)

    def utility_pair(self, proposal: PairProposal) -> Utility:
        """The bias-corrected Cramér's V of the table on the sample, from 0 to
        100: a table is chosen by itself only when it is 0.45 or more."""
        score = getattr(proposal.exploration, "score", None)
        if score is None:
            return Utility(score=0, reasons=["not_explored"])
        return Utility(
            score=min(100, round(score * 100)),
            reasons=["exploratory_association"],
        )
