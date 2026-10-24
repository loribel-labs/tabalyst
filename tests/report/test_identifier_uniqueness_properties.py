# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Mathematical properties of the identifier uniqueness (cahier 15.2).

They check the formulas of the contract section 2 against an explicit in-memory
deduplication, with no Tabalyst code, so they run from lot 0 and later bind the pure rule.
"""

import random

import pytest
from identifier_uniqueness_helpers import (
    formula,
    oracle,
    population,
    random_population,
    trim,
)

pytestmark = [pytest.mark.uid_lot("0")]


@pytest.mark.parametrize("seed", range(200))
def test_the_formulas_hold_on_random_populations_without_missing_ids(seed):
    rng = random.Random(seed)
    rows = [row for row in random_population(rng) if row[0] != ""]
    if not rows:
        return
    result = oracle(rows)
    figures = formula(result.n, result.d, result.e)

    assert result.m == 0
    assert result.r_raw >= result.e
    assert result.r_residual == (result.n - result.d) - result.e
    assert result.r_residual == (result.n - result.e) - result.d
    assert figures["U"] == result.u
    assert figures["R_residual"] == result.r_residual
    assert figures["R_explained"] == result.r_explained
    assert result.d_after == result.d
    assert result.r_residual >= 0
    assert (result.r_residual == 0) == (result.d == result.n - result.e)
    assert result.r_raw == result.r_explained + result.r_residual


@pytest.mark.parametrize("seed", range(100))
def test_the_formulas_hold_when_the_analytical_domain_merges_ids(seed):
    rng = random.Random(1000 + seed)
    spaces = ["", " ", "  "]
    rows = [
        (f"{rng.choice(spaces)}I{rng.randint(1, 8)}{rng.choice(spaces)}", rng.choice("ab"))
        for _ in range(rng.randint(2, 40))
    ]
    result = oracle(rows, normalize=trim)

    assert result.r_residual == (result.n - result.e) - result.d
    assert result.r_residual == (result.n - result.d) - result.e
    assert result.r_residual >= 0


@pytest.mark.parametrize(
    ("distinct", "shared", "copies"),
    [(1000, 0, 0), (1000, 0, 5), (1000, 20, 5), (1000, 7, 0), (50, 3, 40)],
)
def test_generated_populations_have_the_designed_repetitions(distinct, shared, copies):
    result = oracle(population(distinct_ids=distinct, shared_id_rows=shared, copies=copies))

    assert result.n == distinct + shared + copies
    assert result.d == distinct
    assert result.r_residual == shared
    assert result.r_raw == shared + copies
    assert result.r_explained == copies
    assert result.raw_unique is (shared == 0 and copies == 0)
    assert result.unique_after_dedup is (shared == 0 and distinct + shared >= 2)


def test_the_example_of_the_cahier_a_has_no_residual_repetition():
    result = oracle(population(distinct_ids=995, copies=5))

    assert (result.n, result.u, result.e, result.d) == (1000, 995, 5, 995)
    assert (result.r_raw, result.r_residual) == (5, 0)
    assert result.unique_after_dedup and not result.raw_unique


def test_the_example_of_the_cahier_b_keeps_a_residual_repetition():
    result = oracle(population(distinct_ids=980, shared_id_rows=15, copies=5))

    assert (result.r_raw, result.r_explained, result.r_residual) == (20, 5, 15)
    assert not result.unique_after_dedup


def test_same_id_with_other_columns_is_a_residual_repetition():
    result = oracle([("A-001", "active"), ("A-001", "inactive")])

    assert (result.e, result.r_raw, result.r_residual) == (0, 1, 1)


def test_an_id_that_only_differs_by_blanks_stays_residual_in_the_analytical_domain():
    result = oracle([("A-001", "Alice"), (" A-001 ", "Alice")], normalize=trim)

    assert (result.e, result.d, result.r_residual) == (0, 1, 1)


def test_one_distinct_row_repeated_is_not_a_unique_key():
    result = oracle([("A-001", "Alice")] * 3)

    assert (result.e, result.r_residual, result.u) == (2, 0, 1)
    assert not result.unique_after_dedup and not result.raw_unique


def test_subtracting_all_copies_is_wrong_when_a_copied_row_has_no_id():
    """Case E of the cahier: the formula is invalid, which is why M > 0 never concludes."""
    result = oracle([("", "Alice"), ("", "Alice"), ("B-002", "Bob")])

    assert (result.m, result.e, result.r_raw, result.r_residual) == (2, 1, 0, 0)
    assert result.r_raw - result.e == -1
    assert not result.raw_unique and not result.unique_after_dedup


def test_many_copies_of_one_row_count_extra_copies_not_groups():
    rows = [("A", "x")] * 10 + [("B", "y")] * 3 + [("C", "z")]
    result = oracle(rows)

    assert result.e == 9 + 2
    assert result.r_residual == 0
    assert result.unique_after_dedup
