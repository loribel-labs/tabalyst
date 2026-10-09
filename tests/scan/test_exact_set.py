# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact set of the second pass, alone: keys, accounting, the pool and the
limit (design 20.8)."""

import tracemalloc

import pytest

from tabalyst.scanner import ScanConfig
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.exactset import ExactPool, ExactSet
from tabalyst.scanner.secondpass.models import DistinctCount, DistinctLimited
from tabalyst.scanner.secondpass.replay import CellReader

ROOMY = 1 << 40


def _fresh(total: int = ROOMY) -> ExactSet:
    return ExactSet(ExactPool(total))


def test_a_leading_zero_and_a_length_make_other_values():
    held = _fresh()

    held.add_strings(["123", "0123", "00123", "123"], [1, 1, 1, 2])

    assert held.distinct() == 3
    assert held.values == 5
    assert sorted(held.digits) == [3, 4, 5]


def test_digits_beyond_the_compact_length_and_non_ascii_digits_use_the_generic_set():
    held = _fresh()

    held.add_strings(["1" * 18, "1" * 19, "١٢٣", "²", "12 3"], [1] * 5)

    assert len(held.digits[18]) == 1
    assert held.text == {"1" * 19, "١٢٣", "²", "12 3"}
    assert held.distinct() == 5


def test_a_string_and_a_native_with_the_same_text_are_two_values():
    held = _fresh()

    held.add_strings(["123", "1.5"], [1, 1])
    held.add_native("integer", 123)
    held.add_native("number", "1.5")
    held.add_native("boolean", True)
    held.add_native("boolean", True)
    held.add_native("boolean", False)

    assert held.distinct() == 2 + 1 + 1 + 2
    assert held.values == 7


def test_the_result_is_checked_against_the_values_and_the_lower_bound_of_the_scan():
    held = _fresh()
    held.add_strings(["a", "b", "a"], [1, 1, 1])

    counted = held.result(3, 2)

    assert isinstance(counted, DistinctCount)
    assert (counted.values, counted.distinct, counted.redundant, counted.unique) == (3, 2, 1, False)
    with pytest.raises(ScanMismatch, match="values"):
        held.result(4, None)
    with pytest.raises(ScanMismatch, match="at least 3"):
        held.result(3, 3)


@pytest.mark.parametrize("shape", ["digits", "alnum"])
def test_the_bytes_charged_are_the_bytes_the_sets_hold(shape):
    count = 40_000

    def build() -> ExactSet:
        held = _fresh()
        for start in range(0, count, 4_096):
            size = min(4_096, count - start)
            if shape == "digits":
                batch = [f"{n:010d}" for n in range(start, start + size)]
            else:
                batch = [f"K{n:011X}" for n in range(start, start + size)]
            held.add_strings(batch, [1] * size)
        return held

    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    held = build()
    traced = tracemalloc.get_traced_memory()[0] - base
    tracemalloc.stop()

    assert held.distinct() == count
    assert held.used == pytest.approx(traced, rel=0.1)


def test_a_field_that_does_not_fit_the_pool_stops_and_frees_its_sets():
    pool = ExactPool(50_000)
    held = ExactSet(pool)

    for start in range(0, 20_000, 1_000):
        held.add_strings([f"id-{n}" for n in range(start, start + 1_000)], [1] * 1_000)

    assert held.limited
    assert pool.used == 0 and held.used == 0 and not held.text
    limited = held.result(20_000, None)
    assert isinstance(limited, DistinctLimited)
    assert limited.accuracy == "lower_bound"
    assert 0 < limited.lower_bound <= limited.values_read < 20_000
    # Once stopped, nothing more is counted and nothing more is held.
    held.add_strings(["later"], [1])
    held.add_native("integer", 1)
    assert held.values == limited.values_read and pool.used == 0


def test_the_sets_of_a_run_draw_from_one_pool():
    pool = ExactPool(300_000)
    first, second = ExactSet(pool), ExactSet(pool)

    for start in range(0, 1_500, 500):
        first.add_strings([f"a{n}" for n in range(start, start + 500)], [1] * 500)
    for start in range(0, 1_500, 500):
        second.add_strings([f"b{n}" for n in range(start, start + 500)], [1] * 500)

    # Each alone fits (about 200,000 bytes); both together do not.
    assert not first.limited and second.limited
    assert pool.used == first.used <= pool.total


def test_content_is_what_the_first_pass_calls_content():
    reader = CellReader(ScanConfig.model_validate({"values": {"null_markers": ["N/A"]}}))

    assert reader.content(["a", "", " ", "N/A", " x "]) == [True, False, False, False, True]
    plain = CellReader(ScanConfig())
    assert plain.content(["a", "b"]) == [True, True]
    assert plain.content(["a", "\t", ""]) == [True, False, False]
