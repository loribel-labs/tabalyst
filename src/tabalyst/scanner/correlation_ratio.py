# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Correlation ratio of a number by category from stable moments (design 20.23).

The exploration of the row sample and the second pass share this arithmetic: a
batch of numbers gives its moments by a centered pass, batches are merged with
the update of Chan et al., and the ratio is read from the moments of the groups.
The ratio ``eta_squared`` is the share of the variance of the number that the
categories explain; ``epsilon_squared`` is the same share corrected for the bias
that grows with the number of groups, and ``score`` (its square root) is what
rates a pair, so that many small groups do not outrank a few solid ones.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

# Why a ratio is not defined. Never reported as 0.
TOO_FEW_ROWS = "too_few_rows"
SINGLE_CATEGORY = "single_category"
NO_VARIANCE = "no_variance"


@dataclass(frozen=True, slots=True)
class GroupMoments:
    """Count, mean, sum of squares about the mean, smallest and largest number
    of a group of rows."""

    n: int
    mean: float
    m2: float
    minimum: float
    maximum: float


EMPTY = GroupMoments(0, 0.0, 0.0, 0.0, 0.0)


def moments_of(values: Sequence[float]) -> GroupMoments:
    """Moments of numbers by a centered pass; ``EMPTY`` without any."""
    n = len(values)
    if n == 0:
        return EMPTY
    mean = math.fsum(values) / n
    return GroupMoments(
        n,
        mean,
        math.fsum((x - mean) * (x - mean) for x in values),
        min(values),
        max(values),
    )


def merge(a: GroupMoments, b: GroupMoments) -> GroupMoments:
    """Moments of two sets of rows, by the update of Chan et al.: stable
    whatever the sizes and the order of the batches, up to rounding."""
    if a.n == 0:
        return b
    if b.n == 0:
        return a
    n = a.n + b.n
    delta = b.mean - a.mean
    return GroupMoments(
        n,
        a.mean + delta * b.n / n,
        a.m2 + b.m2 + delta * delta * a.n * b.n / n,
        min(a.minimum, b.minimum),
        max(a.maximum, b.maximum),
    )


@dataclass(frozen=True, slots=True)
class Ratio:
    """The correlation ratio of groups: ``groups`` have rows, over ``n`` rows;
    ``eta_squared`` and the corrected ``epsilon_squared`` (not below 0) and their
    ``score``, or the ``reason`` there are none."""

    n: int
    groups: int
    eta_squared: float | None = None
    epsilon_squared: float | None = None
    score: float | None = None
    reason: str | None = None


def ratio(groups: Sequence[GroupMoments], min_rows: int) -> Ratio:
    """The correlation ratio of the groups that have a row. Fewer than
    ``min_rows`` rows, or no more rows than groups, are too few; one group has
    nothing to compare; numbers that are all equal have no variance to explain."""
    kept = [group for group in groups if group.n > 0]
    n = sum(group.n for group in kept)
    k = len(kept)
    if n < max(min_rows, k + 1):
        return Ratio(n, k, reason=TOO_FEW_ROWS)
    if k < 2:
        return Ratio(n, k, reason=SINGLE_CATEGORY)
    if min(group.minimum for group in kept) == max(group.maximum for group in kept):
        return Ratio(n, k, reason=NO_VARIANCE)
    grand = math.fsum(group.n * group.mean for group in kept) / n
    between = math.fsum(group.n * (group.mean - grand) ** 2 for group in kept)
    within = math.fsum(group.m2 for group in kept)
    total = between + within
    if total <= 0.0 or not math.isfinite(total):
        # The spread is below what a float holds: nothing honest to report.
        return Ratio(n, k, reason=NO_VARIANCE)
    eta = max(0.0, min(1.0, between / total))
    epsilon = max(0.0, min(1.0, (between - (k - 1) * within / (n - k)) / total))
    return Ratio(n, k, eta, epsilon, math.sqrt(epsilon))
