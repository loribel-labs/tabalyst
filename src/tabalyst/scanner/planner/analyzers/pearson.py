# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pearson correlation of a pair of numeric columns over every row (lot 8a)."""

from __future__ import annotations

from typing import ClassVar

from tabalyst.scanner.planner.analyzer import (
    Analyzer,
    Assessment,
    costs,
    memory,
)
from tabalyst.scanner.planner.analyzers.common import replay_state
from tabalyst.scanner.planner.costmodel import (
    NS_PER_CELL,
    PAIR_FEED_ENTRY_BYTES,
    PAIR_FEED_ROWS,
    PAIR_STATE_BYTES,
    RESULT_BYTES,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Costs, Exploration, State, Utility

PAIR_SEPARATOR = "+"


class PearsonCorrelation(Analyzer):
    """Counts the common rows of a pair and gives their coefficient (REL-07).

    It concerns pairs, not fields: ``relevant`` is false and the planner asks
    ``assess_pair``, ``estimate_pair`` and ``utility_pair`` of the pairs the
    exploration (``planner/relations.py``) proposes or a request names. A pair
    reads the source, but for a complete row sample of a CSV file, which is the
    whole population (design 20.12).
    """

    id: ClassVar[str] = "pearson_correlation"
    outputs: ClassVar[tuple[str, ...]] = ("correlation", "common_rows", "exclusions")
    available: ClassVar[bool] = True

    def relevant(self, facts: FieldFacts) -> bool:
        return False

    def assess(self, facts: FieldFacts) -> Assessment:
        return Assessment("not_applicable", ("not_numeric",))

    def estimate(self, facts: FieldFacts, assessment: Assessment) -> Costs:
        raise NotImplementedError("a correlation is estimated for a pair")

    def utility(self, facts: FieldFacts, assessment: Assessment) -> Utility:
        raise NotImplementedError("a correlation is rated for a pair")

    def assess_pair(self, from_samples: bool) -> Assessment:
        """A pair is always applicable once its columns are numbers."""
        return Assessment(
            "applicable",
            method="pairwise_complete",
            parameters={"min_pairs": self.settings.pearson.min_pairs},
            requires_source=not from_samples,
        )

    def estimate_pair(
        self, first: FieldFacts, second: FieldFacts, assessment: Assessment
    ) -> Costs:
        """The common batch of floats of each column is shared by every pair
        that uses it, and the reading of its cells too."""
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

    def utility_pair(self, exploration: Exploration | None) -> Utility:
        """The lower bound of the absolute coefficient on the sample, from 0 to
        100: a pair is chosen by itself only when that bound is 0.45 or more."""
        if exploration is None or exploration.score is None:
            return Utility(score=0, reasons=["not_explored"])
        return Utility(
            score=min(100, round(exploration.score * 100)),
            reasons=["exploratory_correlation"],
        )
