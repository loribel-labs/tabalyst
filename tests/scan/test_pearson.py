# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The arithmetic of the Pearson correlation: co-moments, merge, coefficient
and interval (design 20.12, REL-07 to REL-09)."""

import math
import random
from decimal import Decimal
from fractions import Fraction

import pytest

from tabalyst.scanner.measures import UNCONVERTIBLE
from tabalyst.scanner.pearson import (
    EMPTY,
    INSUFFICIENT_PAIRS,
    ZERO_VARIANCE_FIRST,
    ZERO_VARIANCE_SECOND,
    coefficient,
    comoments,
    interval,
    merge,
    score,
    to_float,
)


def exact_r(first, second):
    """The coefficient of the rows where both values exist, in exact fractions."""
    pairs = [
        (Fraction(x), Fraction(y))
        for x, y in zip(first, second, strict=True)
        if x is not None and y is not None
    ]
    n = len(pairs)
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    cross = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    var_x = sum((x - mean_x) ** 2 for x, _ in pairs)
    var_y = sum((y - mean_y) ** 2 for _, y in pairs)
    return n, float(cross) / math.sqrt(float(var_x) * float(var_y))


def columns(count, *, holes=0.0, seed=7, scale=1.0, offset=0.0):
    rng = random.Random(seed)
    first = [offset + scale * rng.gauss(0, 1) for _ in range(count)]
    second = [0.6 * x + scale * rng.gauss(0, 1) for x in first]
    for series in (first, second):
        for index in range(count):
            if rng.random() < holes:
                series[index] = None
    return first, second


def test_the_coefficient_matches_the_exact_value_on_the_common_rows():
    first, second = columns(500, holes=0.2)

    r, reason = coefficient(comoments(first, second), 10)

    n, expected = exact_r(first, second)
    assert reason is None
    assert comoments(first, second).n == n
    assert r == pytest.approx(expected, abs=1e-12)


def test_the_means_are_those_of_the_common_rows_not_of_each_column():
    first = [1.0, 2.0, 3.0, 100.0, None]
    second = [2.0, 4.0, 6.0, None, 50.0]

    moments = comoments(first, second)

    assert moments.n == 3
    assert moments.mean_first == 2.0
    assert moments.mean_second == 4.0


@pytest.mark.parametrize("cuts", [1, 2, 7, 50])
def test_merging_batches_gives_the_co_moments_of_the_whole(cuts):
    first, second = columns(2000, holes=0.1, scale=1e6, offset=1e9)
    edges = sorted(random.Random(cuts).sample(range(1, 2000), cuts))
    merged = EMPTY
    start = 0
    for stop in [*edges, 2000]:
        merged = merge(merged, comoments(first[start:stop], second[start:stop]))
        start = stop

    whole = comoments(first, second)

    assert merged.n == whole.n
    assert coefficient(merged, 10)[0] == pytest.approx(coefficient(whole, 10)[0], abs=1e-12)
    assert merged.mean_first == pytest.approx(whole.mean_first, rel=1e-12)
    assert merged.min_first == whole.min_first and merged.max_second == whole.max_second


def test_a_large_offset_does_not_cost_the_coefficient_its_digits():
    # The centered pass keeps the digits that a sum of squares would lose.
    first, second = columns(1000, scale=1.0, offset=1e8)

    r, _ = coefficient(comoments(first, second), 10)

    assert r == pytest.approx(exact_r(first, second)[1], abs=1e-9)


def test_a_constant_column_is_undefined_even_when_its_value_is_not_exact_in_binary():
    constant = [0.1] * 1000
    varying = [float(n) for n in range(1000)]

    assert coefficient(comoments(constant, varying), 10) == (None, ZERO_VARIANCE_FIRST)
    assert coefficient(comoments(varying, constant), 10) == (None, ZERO_VARIANCE_SECOND)


def test_too_few_common_rows_give_no_coefficient_and_not_zero():
    moments = comoments([1.0, 2.0, None, 4.0], [2.0, 4.0, 6.0, None])

    assert moments.n == 2
    assert coefficient(moments, 3) == (None, INSUFFICIENT_PAIRS)
    assert coefficient(EMPTY, 1) == (None, INSUFFICIENT_PAIRS)


def test_a_perfect_line_gives_one_and_never_leaves_the_range():
    first = [float(n) for n in range(100)]
    up, _ = coefficient(comoments(first, [3 * x + 0.1 for x in first]), 3)
    down, _ = coefficient(comoments(first, [-0.3 * x for x in first]), 3)

    assert up is not None and -1.0 <= up <= 1.0 and up == pytest.approx(1.0, abs=1e-12)
    assert down == pytest.approx(-1.0, abs=1e-12)


def test_the_interval_narrows_with_the_number_of_pairs_and_needs_four():
    assert interval(0.5, 3) is None
    few = interval(0.5, 20)
    many = interval(0.5, 2000)
    assert few[0] < many[0] < 0.5 < many[1] < few[1]
    # A coefficient of 1 has no finite transform: the interval stays finite.
    assert all(math.isfinite(bound) for bound in interval(1.0, 50))


def test_the_score_is_zero_when_the_interval_holds_zero_and_the_nearest_bound_otherwise():
    assert score((-0.1, 0.4)) == 0.0
    assert score((0.3, 0.7)) == 0.3
    assert score((-0.8, -0.5)) == 0.5


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (3, 3.0),
        (Decimal("1.5"), 1.5),
        (10**400, None),
        (Decimal("1e400"), None),
        (UNCONVERTIBLE, None),
        (None, None),
        (True, None),
    ],
)
def test_a_number_beyond_float64_is_not_converted(number, expected):
    assert to_float(number) == expected
