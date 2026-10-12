# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Accumulator of the numbers of a column described by category (design 20.23).

The category is coded once per batch (``CodeFeed``) and the number converted once
(``ColumnFeed``), whatever the number of analyses that read them (REL-03); each
pair keeps, for every category, the moments of its numbers, their extremes and
sums, and a counter per bin of edges that are the same for all of them. The edges
are fixed before the source is read, from what the Scan kept of the column.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from fractions import Fraction

from tabalyst.scanner.correlation_ratio import (
    EMPTY,
    GroupMoments,
    merge,
    moments_of,
    ratio,
)
from tabalyst.scanner.features import MISSING, Coder
from tabalyst.scanner.models import DatasetResult, FieldResult, NumericStats
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.bins import binned_quantiles
from tabalyst.scanner.secondpass.boundaries import place_edges
from tabalyst.scanner.secondpass.crosstab import CodeFeed, axis
from tabalyst.scanner.secondpass.models import (
    StatsAssociation,
    StatsBins,
    StatsExclusions,
    StatsGroup,
    StatsResult,
    StatsSummary,
)
from tabalyst.scanner.secondpass.pearson import ColumnFeed
from tabalyst.scanner.secondpass.replay import CellReader

# Partial sums a group keeps before folding them into one: a sum of correctly
# rounded sums of batches stays within a few units of the last place.
MAX_PARTS = 64


@dataclass(frozen=True, slots=True)
class StatsEdges:
    """The inner edges of the bins of a number and where they come from. A number
    goes to bin ``bisect_right(inner, x)``, so equal numbers share a bin. ``low``
    and ``high`` bound the bins from outside (the extremes of the Scan, widened
    to the neighbouring floats)."""

    inner: tuple[float, ...]
    low: Fraction
    high: Fraction
    strategy: str
    requested: str
    source: str
    reason: str | None
    minimum: float
    maximum: float

    def bounds(self) -> list[Fraction]:
        """Every edge as an exact fraction, the outer bounds included."""
        return [self.low, *(Fraction(edge) for edge in self.inner), self.high]

    def written(self) -> list[float]:
        """The edges as the document writes them: the extremes of the Scan and
        the inner edges between."""
        return [self.minimum, *self.inner, self.maximum]


def stats_edges(
    dataset: DatasetResult,
    field: FieldResult,
    stats: NumericStats,
    bins: int,
    strategy: str,
    reader: CellReader,
) -> StatsEdges:
    """Place the edges of the bins of a number as ``numeric_histogram`` does,
    then keep them as float64 edges strictly between its extremes."""
    placement = place_edges(dataset, field, stats, bins, strategy, reader)
    minimum, maximum = float(stats.min), float(stats.max)
    inner: list[float] = []
    for fraction in placement.edges.edges[1:-1]:
        edge = float(fraction)
        if minimum < edge < maximum and (not inner or edge > inner[-1]):
            inner.append(edge)
    return StatsEdges(
        tuple(inner),
        placement.edges.edges[0],
        placement.edges.edges[-1],
        placement.strategy,
        placement.requested,
        placement.source,
        placement.reason,
        minimum,
        maximum,
    )


class _Group:
    """What a category keeps: the moments and partial sums of its numbers, the
    signs and a counter per bin."""

    __slots__ = ("counts", "moments", "negative", "parts", "positive", "value_missing", "zero")

    def __init__(self, bins: int) -> None:
        self.moments: GroupMoments = EMPTY
        self.parts: list[float] = []
        self.positive = self.negative = self.zero = 0
        self.counts = [0] * bins
        self.value_missing = 0

    def add(self, values: list[float], inner: tuple[float, ...]) -> None:
        """Account for the numbers of a batch. Sorted, a count of the numbers
        below each edge gives every bin, the signs and the extremes."""
        values.sort()
        self.moments = merge(self.moments, moments_of(values))
        self.parts.append(math.fsum(values))
        if len(self.parts) > MAX_PARTS:
            self.parts[:] = [math.fsum(self.parts)]
        below_zero = bisect_left(values, 0.0)
        not_above = bisect_right(values, 0.0)
        self.negative += below_zero
        self.zero += not_above - below_zero
        self.positive += len(values) - not_above
        previous = 0
        counts = self.counts
        for index, edge in enumerate(inner):
            position = bisect_left(values, edge)
            counts[index] += position - previous
            previous = position
        counts[len(inner)] += len(values) - previous


class StatsAccumulator:
    """The numbers of one column for each class of a category, over the rows
    where both are present, and the rows left out (design 20.23)."""

    def __init__(self, first: CodeFeed, second: ColumnFeed, edges: StatsEdges) -> None:
        self.first = first
        self.second = second
        self.edges = edges
        self.failure: str | None = None
        self.groups: list[_Group] = [
            _Group(len(edges.inner) + 1) for _ in range(len(first.coder.classes))
        ]
        self.rows = 0
        self.category_present = 0
        self.category_missing = 0
        self.both_missing = 0
        # The numbers of the rows without a category: they take part in no group
        # but the extremes of the Scan are checked against them.
        self.outside_min = math.inf
        self.outside_max = -math.inf

    def add(self, codes: list[int], values: list[float | None]) -> None:
        """Account for aligned rows of the category and the number."""
        total = len(codes)
        self.rows += total
        self.category_present += total - codes.count(MISSING)
        grouped: dict[int, list[float]] = {}
        groups = self.groups
        for code, number in zip(codes, values, strict=True):
            if number is None:
                if code < 0:
                    self.both_missing += 1
                else:
                    groups[code].value_missing += 1
            elif code < 0:
                self.category_missing += 1
                self.outside_min = min(self.outside_min, number)
                self.outside_max = max(self.outside_max, number)
            else:
                bucket = grouped.get(code)
                if bucket is None:
                    grouped[code] = [number]
                else:
                    bucket.append(number)
        inner = self.edges.inner
        for code, numbers in grouped.items():
            groups[code].add(numbers, inner)

    def check(self, category: FieldResult, number: NumericStats) -> None:
        """The values the reading found are the Scan's; a difference means the
        analysis was not read as the Scan read the columns."""
        for label, found, expected in (
            ("category", self.category_present, category.values.count),
            ("number column", self.second.numbers, number.count),
        ):
            if found != expected:
                raise ScanMismatch(f"the {label} holds {found} values, the scan counted {expected}")
        counted = sum(group.moments.n for group in self.groups) + self.category_missing
        if counted > number.count:
            raise ScanMismatch("the groups hold more numbers than the scan counted")
        if counted == number.count and counted:
            lows = [group.moments.minimum for group in self.groups if group.moments.n]
            highs = [group.moments.maximum for group in self.groups if group.moments.n]
            low = min([*lows, self.outside_min])
            high = max([*highs, self.outside_max])
            if low != self.edges.minimum or high != self.edges.maximum:
                raise ScanMismatch("the extremes of the groups are not the scan's")

    def _summary(
        self,
        moments: GroupMoments,
        parts: list[float],
        signs: tuple[int, int, int],
        counts: list[int],
        bounds: list[Fraction],
    ) -> StatsSummary:
        if moments.n == 0:
            return StatsSummary(count=0, counts=list(counts))
        total = math.fsum(parts)
        quantiles = binned_quantiles(
            bounds, counts, moments.n, Fraction(moments.minimum), Fraction(moments.maximum)
        )
        return StatsSummary(
            count=moments.n,
            min=moments.minimum,
            max=moments.maximum,
            sum=total,
            mean=total / moments.n,
            std=math.sqrt(moments.m2 / moments.n),
            positive=signs[0],
            negative=signs[1],
            zero=signs[2],
            counts=list(counts),
            median=quantiles[2],
            quantiles=quantiles,
        )

    def result(self, source: str, category: FieldResult, number: NumericStats) -> StatsResult:
        """The description of the numbers by category, checked against the Scan:
        the rows add up and the values of each column are the ones it counted."""
        coder: Coder = self.first.coder
        self.check(category, number)
        bounds = self.edges.bounds()
        width = len(self.edges.inner) + 1
        groups: list[StatsGroup] = []
        overall = EMPTY
        parts: list[float] = []
        signs = [0, 0, 0]
        counts = [0] * width
        value_missing = 0
        for group in self.groups:
            summary = self._summary(
                group.moments,
                group.parts,
                (group.positive, group.negative, group.zero),
                group.counts,
                bounds,
            )
            groups.append(
                StatsGroup(
                    **{name: getattr(summary, name) for name in StatsSummary.model_fields},
                    rows=group.moments.n + group.value_missing,
                    value_missing=group.value_missing,
                )
            )
            overall = merge(overall, group.moments)
            parts.extend(group.parts)
            signs[0] += group.positive
            signs[1] += group.negative
            signs[2] += group.zero
            counts = [a + b for a, b in zip(counts, group.counts, strict=True)]
            value_missing += group.value_missing
        counted = overall.n + value_missing
        if counted + self.category_missing + self.both_missing != self.rows:
            raise ScanMismatch("the counts of the groups do not add up to the rows read")
        found = ratio([group.moments for group in self.groups[:-1]], 0)
        return StatsResult(
            source=source,  # type: ignore[arg-type]
            categories=axis(category, coder),
            rows=self.rows,
            counted=overall.n,
            excluded=StatsExclusions(
                category_missing=self.category_missing,
                value_missing=value_missing,
                both_missing=self.both_missing,
            ),
            bins=StatsBins(
                strategy=self.edges.strategy,  # type: ignore[arg-type]
                requested_strategy=self.edges.requested,  # type: ignore[arg-type]
                bounds_source=self.edges.source,  # type: ignore[arg-type]
                reason=self.edges.reason,
                edges=self.edges.written(),
            ),
            overall=self._summary(overall, parts, (signs[0], signs[1], signs[2]), counts, bounds),
            groups=groups,
            association=StatsAssociation(
                defined=found.score is not None,
                n=found.n,
                groups=found.groups,
                eta_squared=found.eta_squared,
                epsilon_squared=found.epsilon_squared,
                score=found.score,
                reason=found.reason,
            ),
        )
