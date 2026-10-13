# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The grid of bins a pair counts its rows in for the rank correlation (design
20.22).

The edges of each column are fixed before the source is read, from what the
Scan kept of the column, so that the same Scan gives the same grid on any
machine and in any order of reading.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from tabalyst.scanner.models import DatasetResult, FieldResult, NumericStats
from tabalyst.scanner.rankcorr import BinnedRank, binned_spearman
from tabalyst.scanner.secondpass.accumulators import decimal_bounds
from tabalyst.scanner.secondpass.bins import linear_edges, quantile_edges
from tabalyst.scanner.secondpass.boundaries import distinct_numbers, row_numbers
from tabalyst.scanner.secondpass.replay import CellReader


@dataclass(frozen=True, slots=True)
class RankEdges:
    """The inner edges of the bins of one column and where they come from. A
    number goes to bin ``bisect_right(inner, x)``, so equal numbers share a
    bin."""

    inner: tuple[float, ...]
    source: str


def rank_edges(
    dataset: DatasetResult,
    field: FieldResult,
    stats: NumericStats,
    bins: int,
    reader: CellReader,
) -> RankEdges:
    """Edges at the quantiles of the row sample of the Scan (the shape of the
    occurrences), else of its distinct values, else of equal width."""
    low = decimal_bounds(stats.min)[0]
    high = decimal_bounds(stats.max)[1]
    enough = 2 * bins
    source = "rows"
    sample = row_numbers(dataset, field, reader)
    if len(sample) < enough:
        source = "distinct"
        sample = distinct_numbers(field, reader)
    edges = quantile_edges(low, high, bins, sample) if len(sample) >= enough else None
    if edges is None:
        source = "range"
        edges = linear_edges(low, high, bins)
    return RankEdges(tuple(float(edge) for edge in edges[1:-1]), source)


class RankGrid:
    """The rows where both columns have a number, counted by bin of each."""

    __slots__ = ("counts", "first", "second", "width")

    def __init__(self, first: RankEdges, second: RankEdges) -> None:
        self.first = first
        self.second = second
        self.width = len(second.inner) + 1
        self.counts = [0] * ((len(first.inner) + 1) * self.width)

    def add_rows(self, first: Sequence[float | None], second: Sequence[float | None]) -> None:
        """Count aligned rows; those where a column has no number are left out."""
        inner_first, inner_second, width = self.first.inner, self.second.inner, self.width
        keys = [
            bisect_right(inner_first, x) * width + bisect_right(inner_second, y)
            for x, y in zip(first, second, strict=True)
            if x is not None and y is not None
        ]
        counts = self.counts
        for key, count in Counter(keys).items():
            counts[key] += count

    def estimate(self) -> BinnedRank:
        """The rank correlation of the rows counted so far."""
        return binned_spearman(self.counts, self.width)
