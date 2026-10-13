# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact bins, ranks and quantiles of the second pass (HIST-01 to HIST-07).

Edges are exact fractions; a number is placed with one float comparison, and
with the exact one only when its float equals an edge's. Rounding to the
nearest float is monotonic, so ``float(x) > float(edge)`` proves ``x > edge``:
the float path never misplaces a number, whatever the magnitude (D09).
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction

from tabalyst.scanner.measures import output_number
from tabalyst.scanner.models import Number
from tabalyst.scanner.secondpass.models import QUANTILE_LEVELS, Quantile

Exact = int | Decimal


class BinEdges:
    """The edges of the bins, increasing, outer bounds included: bin ``i`` is
    ``[edges[i], edges[i + 1])``, and the last one is closed on the right so
    that the maximum belongs to it, not to a bin of its own (HIST-02)."""

    __slots__ = ("bins", "edges", "floats")

    def __init__(self, edges: Sequence[Fraction]) -> None:
        self.edges = list(edges)
        self.bins = len(self.edges) - 1
        self.floats = [float(edge) for edge in self.edges]

    def index(self, number: Exact) -> int:
        """The bin of ``number``: ``-1`` below the first edge, ``bins`` above the
        last one."""
        try:
            value = float(number)
        except OverflowError:  # an integer beyond float64
            value = math.inf if number > 0 else -math.inf
        floats = self.floats
        position = bisect_right(floats, value)
        if position == 0:
            return -1
        if floats[position - 1] < value:
            if position <= self.bins:
                return position - 1
            return self.bins
        return self._exact(number)

    def _exact(self, number: Exact) -> int:
        edges = self.edges
        value = Fraction(number)
        if value < edges[0]:
            return -1
        if value > edges[-1]:
            return self.bins
        if value == edges[-1]:
            return self.bins - 1
        return bisect_right(edges, value) - 1


def linear_edges(low: Fraction, high: Fraction, bins: int) -> list[Fraction]:
    """``bins`` bins of equal width between two exact bounds; one bin when the
    bounds are equal, so there is never a division by zero (HIST-03)."""
    if high <= low:
        return [low, high]
    width = high - low
    return [low + width * Fraction(i, bins) for i in range(bins)] + [high]


def quantile_edges(
    low: Fraction, high: Fraction, bins: int, sample: Sequence[Fraction]
) -> list[Fraction] | None:
    """Edges at the quantiles of ``sample``, between the exact bounds; ``None``
    when the sample places no inner bound (all its values tie, or lie outside).
    Bounds that tie merge, so there may be fewer bins than asked for."""
    if not sample or high <= low:
        return None
    ordered = sorted(sample)
    size = len(ordered)
    inner: list[Fraction] = []
    for i in range(1, bins):
        candidate = ordered[min(size - 1, i * size // bins)]
        if low < candidate < high and (not inner or candidate > inner[-1]):
            inner.append(candidate)
    return [low, *inner, high] if inner else None


def ranks(count: int, level: tuple[int, int]) -> tuple[int, int, Fraction]:
    """The ranks around the quantile ``level`` of ``count`` ordered values, and
    the weight of the upper one: the quantile is ``x[i] + weight * (x[j] -
    x[i])``. The median of an even count is the mean of the two central
    values (HIST-07)."""
    numerator, denominator = level
    position = Fraction((count - 1) * numerator, denominator)
    lower = position.numerator // position.denominator
    upper = -(-position.numerator // position.denominator)
    return lower, upper, position - lower


def _mix(low: Fraction, high: Fraction, weight: Fraction) -> Fraction:
    return low + weight * (high - low)


def exact_quantiles(values: Sequence[tuple[int, int]], count: int) -> list[Quantile]:
    """The quantiles of integers given as ascending ``(value, count)`` pairs,
    exact. Raises ``Unrepresentable`` for a result float64 cannot hold."""
    cumulative: list[int] = []
    total = 0
    for _, occurrences in values:
        total += occurrences
        cumulative.append(total)

    def at(rank: int) -> int:
        return values[bisect_right(cumulative, rank)][0]

    result = []
    for level in QUANTILE_LEVELS:
        lower, upper, weight = ranks(count, level)
        value = _mix(Fraction(at(lower)), Fraction(at(upper)), weight)
        result.append(
            Quantile(
                level=level[0] / level[1], value=output_number(value), accuracy="exact"
            )
        )
    return result


def binned_quantile_fractions(
    edges: Sequence[Fraction],
    counts: Sequence[int],
    count: int,
    minimum: Fraction,
    maximum: Fraction,
) -> list[tuple[Fraction, Fraction, Fraction]]:
    """The estimate and the certain bounds ``(value, lower, upper)`` of each
    level of ``QUANTILE_LEVELS`` read from bins, as exact fractions: each rank
    is placed at the middle of its place within its bin (the bin is assumed
    uniform), and the bounds are those of the bins that hold the two ranks,
    tightened by the exact minimum and maximum."""
    cumulative: list[int] = []
    total = 0
    for occurrences in counts:
        total += occurrences
        cumulative.append(total)

    def locate(rank: int) -> tuple[Fraction, Fraction, Fraction]:
        index = bisect_right(cumulative, rank)
        before = cumulative[index - 1] if index else 0
        low = max(edges[index], minimum)
        high = min(edges[index + 1], maximum)
        place = Fraction(2 * (rank - before) + 1, 2 * counts[index])
        return _mix(low, high, place), low, high

    result = []
    for level in QUANTILE_LEVELS:
        lower, upper, weight = ranks(count, level)
        value_low, bound_low_a, bound_high_a = locate(lower)
        value_high, bound_low_b, bound_high_b = locate(upper)
        result.append(
            (
                _mix(value_low, value_high, weight),
                _mix(bound_low_a, bound_low_b, weight),
                _mix(bound_high_a, bound_high_b, weight),
            )
        )
    return result


def binned_quantiles(
    edges: Sequence[Fraction],
    counts: Sequence[int],
    count: int,
    minimum: Fraction,
    maximum: Fraction,
) -> list[Quantile]:
    """The quantiles read from bins (``binned_quantile_fractions``) as they are
    written. Raises ``Unrepresentable`` for a result float64 cannot hold."""
    return [
        Quantile(
            level=level[0] / level[1],
            value=output_number(value),
            accuracy="estimated",
            lower=output_number(lower),
            upper=output_number(upper),
        )
        for level, (value, lower, upper) in zip(
            QUANTILE_LEVELS,
            binned_quantile_fractions(edges, counts, count, minimum, maximum),
            strict=True,
        )
    ]


def exact_quantile_fractions(
    values: Sequence[tuple[Exact, int]], count: int
) -> list[Fraction]:
    """The quantiles of numbers given as ascending ``(value, count)`` pairs, as
    exact fractions, for each level of ``QUANTILE_LEVELS``."""
    cumulative: list[int] = []
    total = 0
    for _, occurrences in values:
        total += occurrences
        cumulative.append(total)

    def at(rank: int) -> Fraction:
        return Fraction(values[bisect_right(cumulative, rank)][0])

    result = []
    for level in QUANTILE_LEVELS:
        lower, upper, weight = ranks(count, level)
        result.append(_mix(at(lower), at(upper), weight))
    return result


def rounded(value: Fraction) -> Number:
    """A bound as written in the document: an integer, or a float64."""
    return output_number(value)
