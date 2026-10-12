# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The shape of the numbers of a column: asymmetry, kurtosis, outliers of Tukey,
decimals and two more views of the spread (design 20.24, lot 17).

A number is read as the first pass read it (``CellReader``). Each distinct
number is counted exactly in a table until the field holds ``max_values`` of
them; the table gives exact quartiles and exact counts of outliers. Beyond,
the numbers go on in bins whose width is a power of two (the grid of the values
with a unit): counts, extremes and decimals stay exact, the quartiles become
estimates with certain bounds and the outliers are bracketed. The asymmetry and
the kurtosis come from centered sums in float64, merged by batch.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from fractions import Fraction

from tabalyst.scanner.measures import UNCONVERTIBLE, Unrepresentable, output_number
from tabalyst.scanner.models import DatasetResult, FieldResult, NumericStats
from tabalyst.scanner.secondpass.accumulators import (
    BinAccumulator,
    ScanMismatch,
    decimal_bounds,
)
from tabalyst.scanner.secondpass.bins import (
    BinEdges,
    binned_quantile_fractions,
    binned_quantiles,
    exact_quantile_fractions,
)
from tabalyst.scanner.secondpass.boundaries import place_edges
from tabalyst.scanner.secondpass.measures import (
    GRID_MIN_EXPONENT,
    Grid,
    smallest_exponent,
)
from tabalyst.scanner.secondpass.models import (
    QUANTILE_LEVELS,
    DecimalScale,
    PlacesCount,
    Quantile,
    ShapeMoments,
    ShapeResult,
    Tukey,
    TukeyCount,
    TukeyFence,
)
from tabalyst.scanner.secondpass.replay import CellReader, Exact

# Pairs of a number and its count buffered before a batch of the grid's float
# moments is merged: a pass over them costs about as much as it saves.
FLUSH_ENTRIES = 8_192
# The fences of Tukey: mild (1.5 interquartile ranges) and far (3).
FENCE_FACTORS = (Fraction(3, 2), Fraction(3))
# The indexes of the quartiles among ``QUANTILE_LEVELS``.
Q1, MEDIAN, Q3 = 1, 2, 3
NO_VARIANCE = "no_variance"
TOO_FEW_VALUES = "too_few_values"
NOT_REPRESENTABLE = "not_representable"
NON_POSITIVE = "non_positive"

# A centered summary of a set of numbers: count, mean and the sums of the
# powers 2, 3 and 4 of the distance to the mean.
Moments = tuple[float, float, float, float, float]
_EMPTY: Moments = (0.0, 0.0, 0.0, 0.0, 0.0)


def centered(pairs: list[tuple[float, int]]) -> Moments:
    """The centered summary of ``(value, count)`` pairs."""
    n = float(sum(count for _, count in pairs))
    if not n:
        return _EMPTY
    mean = math.fsum(value * count for value, count in pairs) / n
    m2 = math.fsum(count * (value - mean) ** 2 for value, count in pairs)
    m3 = math.fsum(count * (value - mean) ** 3 for value, count in pairs)
    m4 = math.fsum(count * (value - mean) ** 4 for value, count in pairs)
    return n, mean, m2, m3, m4


def merge_moments(a: Moments, b: Moments) -> Moments:
    """The centered summary of two sets together (Pébay's update)."""
    na, ma, m2a, m3a, m4a = a
    nb, mb, m2b, m3b, m4b = b
    if not na:
        return b
    if not nb:
        return a
    n = na + nb
    delta = mb - ma
    mean = ma + delta * nb / n
    m2 = m2a + m2b + delta**2 * na * nb / n
    m3 = (
        m3a
        + m3b
        + delta**3 * na * nb * (na - nb) / n**2
        + 3 * delta * (na * m2b - nb * m2a) / n
    )
    m4 = (
        m4a
        + m4b
        + delta**4 * na * nb * (na**2 - na * nb + nb**2) / n**3
        + 6 * delta**2 * (na**2 * m2b + nb**2 * m2a) / n**2
        + 4 * delta * (na * m3b - nb * m3a) / n
    )
    return n, mean, m2, m3, m4


def _log_edges(low: Fraction, high: Fraction, bins: int) -> list[Fraction] | None:
    """Edges at equal ratios between two positive bounds, or ``None`` when
    float64 cannot place any inner edge. Bounds that tie merge."""
    try:
        first, last = math.log(float(low)), math.log(float(high))
    except (OverflowError, ValueError):
        return None
    step = (last - first) / bins
    inner: list[Fraction] = []
    for i in range(1, bins):
        edge = Fraction(math.exp(first + i * step))
        if low < edge < high and (not inner or edge > inner[-1]):
            inner.append(edge)
    return [low, *inner, high] if inner else None


def make_views(
    dataset: DatasetResult,
    field: FieldResult,
    stats: NumericStats,
    bins: int,
    cells: CellReader,
) -> tuple[BinAccumulator | None, str | None, BinAccumulator]:
    """The two histograms the shape adds, with their edges placed from the Scan
    alone: the logarithmic one (or why there is none) and the one of equal
    counts."""
    low = decimal_bounds(stats.min)[0]
    high = decimal_bounds(stats.max)[1]
    tight = isinstance(stats.min, int) and isinstance(stats.max, int)
    log: BinAccumulator | None = None
    why: str | None = None
    if low <= 0:
        why = NON_POSITIVE
    else:
        edges = _log_edges(low, high, bins)
        if edges is None:
            why = "no_spread"
        else:
            log = BinAccumulator(
                BinEdges(edges),
                strategy="log",
                requested="log",
                source="range",
                reason=None,
                tight=tight,
            )
    placed = place_edges(dataset, field, stats, bins, "sample_quantile", cells)
    equal = BinAccumulator(
        placed.edges,
        strategy=placed.strategy,
        requested=placed.requested,
        source=placed.source,
        reason=placed.reason,
        tight=placed.tight,
    )
    return log, why, equal


def _places(number: Exact) -> tuple[int, bool]:
    """The decimals a number is written with, and whether the last is a 0."""
    if type(number) is int:
        return 0, False
    _, digits, exponent = number.as_tuple()  # type: ignore[union-attr]
    if not isinstance(exponent, int) or exponent >= 0:
        return 0, False
    return -exponent, digits[-1] == 0


class ShapeAccumulator:
    """The numbers of one field: the table or the grid, the decimals, the float
    moments and the two views."""

    __slots__ = (
        "bins",
        "buffer",
        "cell_ns",
        "count",
        "entries",
        "equal",
        "grid",
        "log",
        "log_reason",
        "max_values",
        "moments",
        "scales",
        "table",
        "unconvertible",
        "unrepresentable",
    )

    def __init__(
        self,
        log: BinAccumulator | None,
        log_reason: str | None,
        equal: BinAccumulator,
        *,
        max_values: int,
        bins: int,
        cell_ns: int = 0,
    ) -> None:
        self.log = log
        self.log_reason = log_reason
        self.equal = equal
        self.max_values = max_values
        self.bins = bins
        # What the plan expects a cell to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.count = 0
        self.unconvertible = 0
        self.table: dict[Exact, int] | None = {}
        self.grid: Grid | None = None
        self.entries = 0
        self.scales: dict[tuple[int, bool], int] = {}
        self.moments: Moments = _EMPTY
        self.buffer: list[tuple[float, int]] = []
        self.unrepresentable = False

    def add(self, number: Exact, count: int) -> None:
        """``count`` occurrences of a number the Scan's detector read."""
        if number is UNCONVERTIBLE:
            self.unconvertible += count
            return
        self.count += count
        key = _places(number)
        self.scales[key] = self.scales.get(key, 0) + count
        if self.log is not None:
            self.log.add(number, count)
        self.equal.add(number, count)
        table = self.table
        if table is None:
            assert self.grid is not None
            self.grid.add(number, count)
            try:
                self.buffer.append((float(number), count))
            except OverflowError:
                self.unrepresentable = True
            if len(self.buffer) >= FLUSH_ENTRIES:
                self._flush()
        elif number in table:
            table[number] += count
        else:
            table[number] = count
            self.entries += 1
            if self.entries > self.max_values:
                self._to_grid()

    def _flush(self) -> None:
        self.moments = merge_moments(self.moments, centered(self.buffer))
        self.buffer = []

    def _floats(self, pairs: list[tuple[Exact, int]]) -> list[tuple[float, int]] | None:
        try:
            return [(float(number), count) for number, count in pairs]
        except OverflowError:
            self.unrepresentable = True
            return None

    def _to_grid(self) -> None:
        """The table is full: its numbers go into a grid and their moments are
        taken, and the numbers that follow only widen the grid."""
        table = self.table
        assert table is not None
        grid = Grid(
            self.bins,
            smallest_exponent(Fraction(min(table)), Fraction(max(table)), self.bins)
            if table
            else GRID_MIN_EXPONENT,
        )
        for number, count in table.items():
            grid.add(number, count)
        floats = self._floats(list(table.items()))
        if floats is not None:
            self.moments = centered(floats)
        self.table, self.grid = None, grid
        self.entries = 0

    # The result -------------------------------------------------------------

    def result(self, stats: NumericStats) -> ShapeResult:
        """The shape, checked against the numeric block of the Scan. Raises
        ``ScanMismatch`` when they disagree and ``Unrepresentable`` for a number
        beyond the precision of the Scan."""
        if self.unconvertible:
            raise Unrepresentable
        if self.count != stats.count:
            raise ScanMismatch(
                f"numeric values: the second pass found {self.count}, the scan {stats.count}"
            )
        # The views check the extremes and that every number is within the Scan's bounds.
        equal = self.equal.result(stats)
        log = self.log.result(stats) if self.log is not None else None
        scale = self._scale()
        if self.table is not None:
            moments = self._moments(centered(self._table_floats()))
            tukey, distinct = self._table_tukey(), len(self.table)
        else:
            if self.buffer:
                self._flush()
            moments = self._moments(self.moments)
            tukey, distinct = self._grid_tukey(), None
        return ShapeResult(
            accuracy="exact" if self.table is not None else "exact_counts",
            storage="table" if self.table is not None else "grid",
            count=self.count,
            distinct=distinct,
            moments=moments,
            tukey=tukey,
            scale=scale,
            log=log,
            log_reason=self.log_reason,
            equal_count=equal,
        )

    def _table_floats(self) -> list[tuple[float, int]]:
        assert self.table is not None
        return self._floats(list(self.table.items())) or []

    def _moments(self, summary: Moments) -> ShapeMoments:
        n, _, m2, m3, m4 = summary
        if self.unrepresentable:
            return ShapeMoments(reason=NOT_REPRESENTABLE)
        if n < 3:
            return ShapeMoments(reason=TOO_FEW_VALUES)
        if not math.isfinite(m2):
            return ShapeMoments(reason=NOT_REPRESENTABLE)
        if m2 <= 0:
            return ShapeMoments(reason=NO_VARIANCE)
        variance = m2 / n
        skewness = (m3 / n) / variance**1.5
        kurtosis = (m4 / n) / variance**2 - 3
        if not (math.isfinite(skewness) and math.isfinite(kurtosis)):
            return ShapeMoments(reason=NOT_REPRESENTABLE)
        return ShapeMoments(skewness=round(skewness, 6), excess_kurtosis=round(kurtosis, 6))

    def _scale(self) -> DecimalScale:
        counts: dict[int, int] = {}
        trailing = 0
        for (places, zero), count in self.scales.items():
            counts[places] = counts.get(places, 0) + count
            if zero:
                trailing += count
        return DecimalScale(
            places=[PlacesCount(places=p, count=counts[p]) for p in sorted(counts)],
            max_places=max(counts),
            trailing_zero=trailing,
            mixed=len([p for p in counts if p > 0]) > 1,
        )

    def _table_tukey(self) -> Tukey:
        table = self.table
        assert table is not None
        pairs = sorted(table.items(), key=lambda item: item[0])
        numbers = [number for number, _ in pairs]
        cumulative: list[int] = []
        total = 0
        for _, occurrences in pairs:
            total += occurrences
            cumulative.append(total)
        if total != self.count:
            raise ScanMismatch("the table of the numbers does not add up to their count")
        exact = exact_quantile_fractions(pairs, total)
        q1, q3 = exact[Q1], exact[Q3]
        spread = q3 - q1

        def below(fence: Fraction) -> int:
            index = bisect_left(numbers, fence)
            return cumulative[index - 1] if index else 0

        def above(fence: Fraction) -> int:
            index = bisect_right(numbers, fence)
            return total - (cumulative[index - 1] if index else 0)

        fences = []
        for factor in FENCE_FACTORS:
            low, high = q1 - factor * spread, q3 + factor * spread
            fences.append(
                TukeyFence(
                    factor=float(factor),
                    low=output_number(low),
                    high=output_number(high),
                    below=_same(below(low)),
                    above=_same(above(high)),
                )
            )
        return Tukey(
            accuracy="exact",
            q1=_exact(QUANTILE_LEVELS[Q1], q1),
            q3=_exact(QUANTILE_LEVELS[Q3], q3),
            iqr=output_number(spread),
            fences=fences,
        )

    def _grid_tukey(self) -> Tukey:
        grid = self.grid
        assert grid is not None
        # The extremes the views have checked against the Scan's.
        assert self.equal.seen_min is not None and self.equal.seen_max is not None
        minimum, maximum = Fraction(self.equal.seen_min), Fraction(self.equal.seen_max)
        count = self.count
        exponent = smallest_exponent(minimum, maximum, self.bins)
        merged: dict[int, int] = {}
        shift = exponent - grid.exponent
        for index, occurrences in grid.counts.items():
            merged[index >> shift] = merged.get(index >> shift, 0) + occurrences
        if sum(merged.values()) != count:
            raise ScanMismatch("the bins of the numbers do not add up to their count")
        low_index, high_index = min(merged), max(merged)
        width = Fraction(2) ** exponent
        edges = [
            minimum,
            *(index * width for index in range(low_index + 1, high_index + 1)),
            maximum,
        ]
        counts = [merged.get(index, 0) for index in range(low_index, high_index + 1)]
        fractions = binned_quantile_fractions(edges, counts, count, minimum, maximum)
        written = binned_quantiles(edges, counts, count, minimum, maximum)
        (q1, q1_low, q1_high), (q3, q3_low, q3_high) = fractions[Q1], fractions[Q3]
        spread = q3 - q1
        last = len(counts) - 1

        def certain_below(limit: Fraction) -> int:
            # A bin is below the limit when all its numbers are: the last bin is
            # closed on the right, so its maximum can touch the limit.
            return sum(
                n
                for i, n in enumerate(counts)
                if edges[i + 1] < limit or (i != last and edges[i + 1] == limit)
            )

        def possible_below(limit: Fraction) -> int:
            return sum(n for i, n in enumerate(counts) if edges[i] < limit)

        def certain_above(limit: Fraction) -> int:
            return sum(n for i, n in enumerate(counts) if edges[i] > limit)

        def possible_above(limit: Fraction) -> int:
            return sum(n for i, n in enumerate(counts) if edges[i + 1] > limit)

        fences = []
        for factor in FENCE_FACTORS:
            reach = 1 + factor
            low_min, low_max = reach * q1_low - factor * q3_high, reach * q1_high - factor * q3_low
            high_min, high_max = reach * q3_low - factor * q1_high, reach * q3_high - factor * q1_low
            fences.append(
                TukeyFence(
                    factor=float(factor),
                    low=output_number(q1 - factor * spread),
                    high=output_number(q3 + factor * spread),
                    below=TukeyCount(
                        certain=certain_below(low_min), possible=possible_below(low_max)
                    ),
                    above=TukeyCount(
                        certain=certain_above(high_max), possible=possible_above(high_min)
                    ),
                )
            )
        return Tukey(
            accuracy="bounds",
            q1=written[Q1],
            q3=written[Q3],
            iqr=output_number(spread),
            fences=fences,
        )


def _same(count: int) -> TukeyCount:
    return TukeyCount(certain=count, possible=count)


def _exact(level: tuple[int, int], value: Fraction) -> Quantile:
    return Quantile(level=level[0] / level[1], value=output_number(value), accuracy="exact")

