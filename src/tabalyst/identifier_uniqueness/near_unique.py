# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The near-uniqueness model: how many residual ID repetitions are still few (contract 14).

Pure integer arithmetic on ``R_residual`` and ``U``; it reads no file and decides nothing about
the role of a column.
"""

from math import isqrt

from tabalyst.identifier_uniqueness.models import NearUnique, ToleranceBound

# A fixed share cannot define rarity (1 % of 10,000 and 1 % of a million are not the same
# situation), so the tolerance is the smallest of three terms: one in RELATIVE_DIVISOR of the
# distinct rows, the square root of them, and an absolute cap. Not calibrated on real files yet
# (none exist in the lab): any change of a constant raises ``NEAR_UNIQUE_VERSION``.
RELATIVE_DIVISOR = 100
ABSOLUTE_CAP = 1000
# Below this many distinct rows one repetition is already more than 1 %: no signal either way.
MIN_POPULATION = 100


def tolerance(distinct_records: int) -> tuple[int, ToleranceBound]:
    """The tolerance ``min(U // 100, isqrt(U), 1000)`` and the term that sets it.

    On a tie the first of ``relative``, ``root`` and ``cap`` is named.
    """
    bounds: tuple[tuple[int, ToleranceBound], ...] = (
        (distinct_records // RELATIVE_DIVISOR, "relative"),
        (isqrt(distinct_records), "root"),
        (ABSOLUTE_CAP, "cap"),
    )
    return min(bounds, key=lambda bound: bound[0])


def assess_near_unique(residual: int, distinct_records: int) -> NearUnique:
    """Whether ``residual`` extra occurrences among ``distinct_records`` rows are few.

    ``residual`` is at least 1 (a column with none is unique after deduplication and needs no
    reading). The result is a diagnostic, never a guarantee: the caller keeps ``unique`` false.
    """
    if distinct_records < MIN_POPULATION:
        return NearUnique(
            signal="population_too_small",
            residual_repetitions=residual,
            distinct_records=distinct_records,
            tolerance=0,
            limiting_bound=None,
        )
    limit, bound = tolerance(distinct_records)
    return NearUnique(
        signal="near_unique" if residual <= limit else "not_near_unique",
        residual_repetitions=residual,
        distinct_records=distinct_records,
        tolerance=limit,
        limiting_bound=bound,
    )
