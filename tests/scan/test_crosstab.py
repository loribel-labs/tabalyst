# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The arithmetic of a table of counts (design 20.13, REL-13, REL-14)."""

import math
import random
from fractions import Fraction

import pytest
from table_helpers import exact_v

from tabalyst.scanner.crosstab import (
    SINGLE_CATEGORY,
    SINGLE_CLASS,
    TOO_FEW_ROWS,
    association,
    baseline_share,
    dominant,
    margins,
    purity_forward,
    purity_reverse,
)


def test_margins_add_up_to_the_total():
    table = [[3, 0, 2], [1, 4, 0]]

    totals = margins(table)

    assert totals.rows == (5, 5) and totals.columns == (4, 4, 2) and totals.total == 10


def test_the_dominant_class_of_a_tie_is_the_first_one_listed():
    assert dominant([2, 5, 5, 1]) == 1
    assert dominant([0, 0, 0]) is None


def test_the_purity_depends_on_the_direction():
    # Each category is pure, but one class mixes two categories.
    table = [[10, 0], [0, 10], [10, 0]]

    forward, reverse = purity_forward(table), purity_reverse(table)

    assert (forward.dominant, forward.total) == (30, 30) and forward.value == 1.0
    assert (reverse.dominant, reverse.total) == (20, 30)
    assert reverse.value == pytest.approx(2 / 3)


def test_the_baseline_is_the_share_of_the_most_frequent_class():
    assert baseline_share([[6, 1], [3, 0]]) == pytest.approx(0.9)
    assert baseline_share([[0, 0]]) is None


def test_cramers_v_matches_an_exact_fraction_oracle_on_random_tables():
    rng = random.Random(3)
    for _ in range(30):
        rows, columns = rng.randint(2, 7), rng.randint(2, 6)
        table = [[rng.choice([0, 0, 1, 3, 8, 40]) for _ in range(columns)] for _ in range(rows)]
        expected = exact_v(table)

        found = association(table)

        if expected is None:
            assert found.cramers_v is None and found.reason is not None
        else:
            assert found.cramers_v == pytest.approx(math.sqrt(float(expected)), abs=1e-12)


def test_a_perfect_association_has_a_cramers_v_of_one():
    found = association([[50, 0, 0], [0, 50, 0], [0, 0, 50]])

    assert found.cramers_v == pytest.approx(1.0)
    assert found.corrected == pytest.approx(1.0, abs=0.02)
    assert found.stable is True and found.degrees == 4


def test_independent_counts_have_no_association():
    found = association([[20, 20], [30, 30]])

    assert found.cramers_v == pytest.approx(0.0, abs=1e-12)
    assert found.corrected == 0.0


def test_the_bias_correction_does_not_grow_with_the_classes_for_independent_data():
    rng = random.Random(5)
    table = [[rng.randint(3, 6) for _ in range(8)] for _ in range(8)]

    found = association(table)

    assert found.cramers_v > 0.05
    assert found.corrected < found.cramers_v
    assert found.corrected < 0.1


def test_an_axis_with_a_zero_margin_takes_no_part_in_the_score():
    with_zero = [[30, 0, 5, 0], [2, 0, 28, 0], [0, 0, 0, 0]]
    without = [[30, 5], [2, 28]]

    zero, plain = association(with_zero), association(without)

    assert zero.effective_rows == 2 and zero.effective_columns == 2
    assert zero.cramers_v == pytest.approx(plain.cramers_v, abs=1e-12)
    assert zero.corrected == pytest.approx(plain.corrected, abs=1e-12)


@pytest.mark.parametrize(
    ("table", "reason"),
    [
        ([[10, 5], [0, 0]], SINGLE_CATEGORY),
        ([[10, 0], [5, 0]], SINGLE_CLASS),
        ([[1, 0], [0, 1]], TOO_FEW_ROWS),
    ],
)
def test_a_table_without_two_effective_axes_or_enough_rows_has_no_score_and_a_reason(table, reason):
    found = association(table, min_rows=30 if reason == TOO_FEW_ROWS else 2)

    assert found.cramers_v is None and found.corrected is None
    assert found.reason == reason


def test_low_expected_counts_make_a_score_unstable():
    small = association([[3, 0, 1], [0, 3, 1], [1, 1, 3]])
    large = association([[30, 0, 10], [0, 30, 10], [10, 10, 30]])

    assert small.stable is False and small.low_share > 0.2
    assert large.stable is True


def test_the_chi_square_of_a_two_by_two_table_is_the_known_value():
    found = association([[10, 20], [30, 40]])

    expected = Fraction(100 * (10 * 40 - 20 * 30) ** 2, 30 * 70 * 40 * 60)
    assert found.chi_square == pytest.approx(float(expected), abs=1e-12)


def test_a_class_of_a_single_row_does_not_make_a_solid_table_unstable():
    table = [[40, 2, 0], [3, 45, 0], [0, 0, 1]]

    found = association(table)

    assert found.stable is True and found.sparse == 2
    assert found.effective_rows == 3 and found.effective_columns == 3
    assert found.corrected > 0.8


def test_a_table_whose_axes_are_all_sparse_is_unstable():
    found = association([[2, 1], [1, 2]], min_rows=2)

    assert found.stable is False and found.sparse == 4
