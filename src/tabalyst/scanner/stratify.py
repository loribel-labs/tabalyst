# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Arithmetic of stratification shared by ``sample`` and the planner (design 20.14).

The classic allocation, the saturating product of cardinalities and the size
from which a stratum cannot round to zero live here, so that the advice of the
plan and the sample it advises use the same rule.
"""

from __future__ import annotations

import math
from collections.abc import Hashable, Iterable, Mapping
from typing import TypeVar

# The largest count the documents write: a product that reaches it is saturated,
# which means "at least this many", never a number to compute with (STRAT-05).
SATURATED = 2**63 - 1

K = TypeVar("K", bound=Hashable)


def saturating_product(values: Iterable[int], cap: int = SATURATED) -> tuple[int, bool]:
    """The product of non-negative integers, stopped at ``cap``.

    Returns ``(product, saturated)``; when saturated the product is ``cap`` and
    the true product is at least that. A zero factor gives 0 whatever the
    others, even saturated ones.
    """
    product = 1
    saturated = False
    for value in values:
        if value < 0:
            raise ValueError("a cardinality cannot be negative")
        if value == 0:
            return 0, False
        if saturated:
            continue
        if product > cap // value:
            product, saturated = cap, True
        else:
            product *= value
    return product, saturated


def allocate_strata(counts: Mapping[K, int], size: int) -> dict[K, int]:
    """Proportional allocation of ``size`` rows to strata, largest remainder.

    Each stratum gets the floor of its exact quota, then the rows left go to the
    largest remainders (ties: the key as text). There is no minimum of one row:
    a rare stratum can get zero (STRAT-01, STRAT-02).
    """
    total = sum(counts.values())
    if not total or not size:
        return {value: 0 for value in counts}
    exact = {value: count * size / total for value, count in counts.items()}
    allocated = {value: math.floor(value_size) for value, value_size in exact.items()}
    remainder = size - sum(allocated.values())
    order = sorted(
        counts,
        key=lambda value: (-(exact[value] - allocated[value]), str(value)),
    )
    for value in order[:remainder]:
        allocated[value] += 1
    return allocated


def allocate_strata_with_minimum(counts: Mapping[K, int], size: int) -> dict[K, int]:
    """Proportional allocation of ``size`` rows with at least one row per stratum.

    A stratum whose exact quota is under one row is held at one, and the rows
    that costs are taken from the others in proportion: this repeats until no
    free stratum falls under one. The rest is shared by largest remainder (ties:
    the key as text). Only integers are compared, so the result is exact and
    identical on every machine. No stratum gets more rows than it has, and the
    total is ``size``.

    Raises ``ValueError`` when ``size`` is under the number of strata (the
    minimum cannot be kept) or over the rows counted (nothing to draw).
    """
    total = sum(counts.values())
    if size < len(counts):
        raise ValueError("the size is under the number of strata")
    if size > total:
        raise ValueError("the size is over the rows counted")
    allocated: dict[K, int] = {}
    free = dict(counts)
    budget = size
    while free:
        weight = sum(free.values())
        held = [value for value, count in free.items() if count * budget < weight]
        if not held:
            break
        for value in held:
            allocated[value] = 1
            budget -= 1
            del free[value]
    weight = sum(free.values())
    remainders: dict[K, int] = {}
    for value, count in free.items():
        allocated[value], remainders[value] = divmod(count * budget, weight)
    left = size - sum(allocated.values())
    for value in sorted(remainders, key=lambda item: (-remainders[item], str(item)))[:left]:
        allocated[value] += 1
    return allocated


def size_for_every_stratum(smallest: int, total: int) -> int:
    """The smallest sample size at which the exact quota of the rarest stratum
    reaches one row, so that its allocation cannot be zero.

    ``smallest`` is the count of the rarest stratum and ``total`` the rows
    counted. It is a sufficient size, not the only one that can keep the
    stratum (the largest remainder may keep it earlier).
    """
    if smallest <= 0 or total <= 0:
        raise ValueError("counts must be positive")
    return -(-total // smallest)
