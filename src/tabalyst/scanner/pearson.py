# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pearson correlation of a pair of columns from stable co-moments (design 20.12).

The exploration of the row sample and the second pass share this arithmetic: a
batch of aligned values gives its co-moments by a centered pass, batches are
merged with the formula of Chan et al., and the coefficient is read from the
result. Only the rows where both values are numbers count (``pairwise_complete``,
REL-07, REL-08): the means are those of the common rows, never the means of the
Scan.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from operator import mul

# A float64 of the number a column holds; ``None`` for a row without one.
Floats = Sequence[float | None]

# Why a coefficient is not defined (REL-09). Never reported as 0.
INSUFFICIENT_PAIRS = "insufficient_pairs"
ZERO_VARIANCE_FIRST = "zero_variance_first"
ZERO_VARIANCE_SECOND = "zero_variance_second"
# Fisher's interval needs more than three pairs.
FISHER_MIN_PAIRS = 4
FISHER_Z = 1.96
# A coefficient of exactly 1 has no finite Fisher transform.
FISHER_CLAMP = 0.999999999999


def to_float(number: int | Decimal | object) -> float | None:
    """The float64 of a number the Scan counted, or ``None`` when it does not
    fit: an integer or a decimal beyond the range of a float, or the marker of
    a number the Scan could not convert."""
    if not isinstance(number, (int, Decimal)) or isinstance(number, bool):
        return None
    try:
        value = float(number)
    except OverflowError:
        return None
    return value if math.isfinite(value) else None


@dataclass(frozen=True, slots=True)
class CoMoments:
    """Count, means, sums of squares and cross products of the common rows,
    with the smallest and the largest value of each column (a column is
    constant exactly when they are equal, which no float rounding can hide)."""

    n: int
    mean_first: float
    mean_second: float
    m2_first: float
    m2_second: float
    cross: float
    min_first: float
    max_first: float
    min_second: float
    max_second: float

    @property
    def covariance(self) -> float | None:
        """Population covariance of the common rows."""
        return self.cross / self.n if self.n else None


EMPTY = CoMoments(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)


def comoments(first: Floats, second: Floats) -> CoMoments:
    """Co-moments of the rows where both values are numbers, by a centered
    pass. The two sequences have the same length."""
    if None in first or None in second:
        kept_first: list[float] = []
        kept_second: list[float] = []
        for x, y in zip(first, second, strict=True):
            if x is not None and y is not None:
                kept_first.append(x)
                kept_second.append(y)
    else:
        kept_first, kept_second = first, second  # type: ignore[assignment]
    n = len(kept_first)
    if n == 0:
        return EMPTY
    mean_first = math.fsum(kept_first) / n
    mean_second = math.fsum(kept_second) / n
    dx = [x - mean_first for x in kept_first]
    dy = [y - mean_second for y in kept_second]
    return CoMoments(
        n,
        mean_first,
        mean_second,
        math.fsum(map(mul, dx, dx)),
        math.fsum(map(mul, dy, dy)),
        math.fsum(map(mul, dx, dy)),
        min(kept_first),
        max(kept_first),
        min(kept_second),
        max(kept_second),
    )


def merge(a: CoMoments, b: CoMoments) -> CoMoments:
    """Co-moments of two sets of rows, by the update of Chan et al.: stable
    whatever the sizes and the order of the batches, up to rounding."""
    if a.n == 0:
        return b
    if b.n == 0:
        return a
    n = a.n + b.n
    dx = b.mean_first - a.mean_first
    dy = b.mean_second - a.mean_second
    weight = a.n * b.n / n
    return CoMoments(
        n,
        a.mean_first + dx * b.n / n,
        a.mean_second + dy * b.n / n,
        a.m2_first + b.m2_first + dx * dx * weight,
        a.m2_second + b.m2_second + dy * dy * weight,
        a.cross + b.cross + dx * dy * weight,
        min(a.min_first, b.min_first),
        max(a.max_first, b.max_first),
        min(a.min_second, b.min_second),
        max(a.max_second, b.max_second),
    )


def coefficient(moments: CoMoments, min_pairs: int) -> tuple[float | None, str | None]:
    """The coefficient of Pearson of the common rows and no reason, or no
    coefficient and the reason. A coefficient is never 0 for lack of data
    (REL-09); rounding cannot push it outside [-1, 1]."""
    if moments.n < min_pairs:
        return None, INSUFFICIENT_PAIRS
    if moments.min_first == moments.max_first:
        return None, ZERO_VARIANCE_FIRST
    if moments.min_second == moments.max_second:
        return None, ZERO_VARIANCE_SECOND
    scale = math.sqrt(moments.m2_first) * math.sqrt(moments.m2_second)
    if scale == 0.0 or not math.isfinite(scale):
        # The spread is below what a float holds: nothing honest to report.
        return None, ZERO_VARIANCE_FIRST if moments.m2_first == 0.0 else ZERO_VARIANCE_SECOND
    return max(-1.0, min(1.0, moments.cross / scale)), None


def interval(r: float, n: int) -> tuple[float, float] | None:
    """The 95% interval of Fisher's transform for a coefficient over ``n``
    pairs, or ``None`` when ``n`` is too small for it. An estimate: it assumes
    pairs drawn at random from a bivariate normal distribution."""
    if n < FISHER_MIN_PAIRS:
        return None
    z = math.atanh(max(-FISHER_CLAMP, min(FISHER_CLAMP, r)))
    error = FISHER_Z / math.sqrt(n - 3)
    return math.tanh(z - error), math.tanh(z + error)


def score(bounds: tuple[float, float]) -> float:
    """The smallest absolute coefficient the interval allows: 0 when it holds
    0. It is what ranks a pair, so that a few rows do not outrank many."""
    lower, upper = bounds
    if lower <= 0.0 <= upper:
        return 0.0
    return min(abs(lower), abs(upper))
