# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rank correlation of a pair of columns (design 20.22).

The exploration of the row sample ranks the values themselves (average ranks
for ties, then Pearson on the ranks). The second pass cannot hold every value,
so it counts the rows in a grid of bins cut at quantiles of what the Scan kept
and reads the correlation of the mid-ranks of the bins, with bounds that hold
for every order the values can have inside their bins.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from tabalyst.scanner.pearson import (
    FISHER_CLAMP,
    FISHER_MIN_PAIRS,
    FISHER_Z,
    Floats,
    comoments,
)

# Why a rank coefficient is not defined. Never reported as 0.
SINGLE_BIN_FIRST = "single_bin_first"
SINGLE_BIN_SECOND = "single_bin_second"
# Rounding slack added outside the bounds of the binned estimate.
BOUND_SLACK = 1e-12


def average_ranks(values: Sequence[float]) -> list[float]:
    """The rank of each value from 1, tied values sharing the mean of the ranks
    they span."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    size = len(order)
    while start < size:
        end = start
        value = values[order[start]]
        while end + 1 < size and values[order[end + 1]] == value:
            end += 1
        mean = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[order[position]] = mean
        start = end + 1
    return ranks


def sample_coefficient(
    first: Floats,
    second: Floats,
    min_pairs: int,
    ranks: tuple[Sequence[float], Sequence[float]] | None = None,
) -> tuple[int, float | None]:
    """The number of rows where both columns have a number and the Spearman
    coefficient over them (Pearson on average ranks), ``None`` when it is not
    defined. ``ranks`` are the average ranks of two columns that have a number in
    every row, computed once for all the pairs that use them."""
    if ranks is not None:
        if len(first) < min_pairs:
            return len(first), None
        return len(first), _rank_pearson(*ranks)
    if None in first or None in second:
        kept = [
            (x, y) for x, y in zip(first, second, strict=True) if x is not None and y is not None
        ]
        xs = [x for x, _ in kept]
        ys = [y for _, y in kept]
    else:
        xs, ys = first, second  # type: ignore[assignment]
    if len(xs) < min_pairs:
        return len(xs), None
    return len(xs), _rank_pearson(average_ranks(xs), average_ranks(ys))


def _rank_pearson(first: Sequence[float], second: Sequence[float]) -> float | None:
    moments = comoments(first, second)
    scale = math.sqrt(moments.m2_first) * math.sqrt(moments.m2_second)
    if scale == 0.0 or not math.isfinite(scale):
        return None
    return max(-1.0, min(1.0, moments.cross / scale))


def rank_interval(r: float, n: int) -> tuple[float, float] | None:
    """The 95% interval of Fisher's transform for a Spearman coefficient over
    ``n`` pairs, with the variance of Bonett and Wright (an estimate), or
    ``None`` when ``n`` is too small."""
    if n < FISHER_MIN_PAIRS:
        return None
    z = math.atanh(max(-FISHER_CLAMP, min(FISHER_CLAMP, r)))
    error = FISHER_Z * math.sqrt((1 + r * r / 2) / (n - 3))
    return math.tanh(z - error), math.tanh(z + error)


@dataclass(frozen=True, slots=True)
class BinnedRank:
    """The rank correlation read from a grid of bins: the estimate, the bounds
    no order inside the bins can leave, and why there is no estimate."""

    coefficient: float | None = None
    lower: float | None = None
    upper: float | None = None
    reason: str | None = None
    bins_first: int = 0
    bins_second: int = 0


def binned_spearman(counts: Sequence[int], width: int) -> BinnedRank:
    """The Spearman coefficient of rows counted in a grid of bins.

    ``counts[i * width + j]`` rows fall in bin ``i`` of the first column and bin
    ``j`` of the second. Bins are ordered, so every row of a bin ranks below
    every row of the next. The estimate is the Pearson coefficient of the
    mid-ranks of the bins. The true centered rank vector of a column is the
    centered mid-rank vector plus a deviation that is orthogonal to it (the
    ranks of a bin sum to its mid-rank times its size), and whose squared norm
    is at most the sum of ``n(n^2 - 1) / 12`` over the bins (reached when no
    values tie). The angle between the true vector and its estimate is therefore
    at most ``atan(deviation / norm)`` for each column, and the angle between
    the two rank vectors differs from the estimated one by at most their sum:
    the cosine of the bounding angles bounds the coefficient.
    """
    height = len(counts) // width
    first = [sum(counts[i * width : (i + 1) * width]) for i in range(height)]
    second = [sum(counts[i * width + j] for i in range(height)) for j in range(width)]
    total = sum(first)
    held_first = sum(1 for n in first if n)
    held_second = sum(1 for n in second if n)
    if held_first < 2 or held_second < 2:
        return BinnedRank(
            reason=SINGLE_BIN_FIRST if held_first < 2 else SINGLE_BIN_SECOND,
            bins_first=held_first,
            bins_second=held_second,
        )

    def centered(sizes: Sequence[int]) -> list[float]:
        middle = (total + 1) / 2
        before = 0
        marks = []
        for size in sizes:
            marks.append(before + (size + 1) / 2 - middle)
            before += size
        return marks

    cx, cy = centered(first), centered(second)
    norm_x = sum(n * c * c for n, c in zip(first, cx, strict=True))
    norm_y = sum(n * c * c for n, c in zip(second, cy, strict=True))
    cross = 0.0
    for i in range(height):
        row = counts[i * width : (i + 1) * width]
        cross += cx[i] * sum(n * c for n, c in zip(row, cy, strict=True) if n)
    rho = max(-1.0, min(1.0, cross / (math.sqrt(norm_x) * math.sqrt(norm_y))))
    spread_x = sum(n * (n * n - 1) / 12 for n in first)
    spread_y = sum(n * (n * n - 1) / 12 for n in second)
    slack = math.atan2(math.sqrt(spread_x), math.sqrt(norm_x)) + math.atan2(
        math.sqrt(spread_y), math.sqrt(norm_y)
    )
    angle = math.acos(rho)
    lower = math.cos(min(math.pi, angle + slack)) - BOUND_SLACK
    upper = math.cos(max(0.0, angle - slack)) + BOUND_SLACK
    return BinnedRank(
        coefficient=rho,
        lower=max(-1.0, lower),
        upper=min(1.0, upper),
        bins_first=held_first,
        bins_second=held_second,
    )
