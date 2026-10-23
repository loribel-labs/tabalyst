# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reference implementation of the Dedup specification proves the worked example.

These tests do not skip: they check the helpers that every later contract test
compares the product to (specification S4, S6.3 and design 5.2), so that a wrong
reference cannot make a wrong product pass.
"""

import random

from dedup_helpers import (
    check_invariants,
    generated_rows,
    read_csv,
    reference_key,
    reference_outputs,
    reference_stats,
    varint,
    write_csv,
)

# The source of S6.3.
EXAMPLE = [
    ("101", "Alice"),
    ("102", "Bob"),
    ("101", "Alice"),
    ("103", "Charlie"),
    ("101", "Alice"),
    ("102", "Bob"),
]


def test_reference_counts_match_the_worked_example_of_the_specification():
    stats = reference_stats(EXAMPLE)
    assert stats == {
        "N": 6, "D": 3, "G": 2, "E": 3, "O": 5, "S": 1, "M": 3, "G2": 1, "G3+": 1,
    }
    check_invariants(stats)


def test_reference_outputs_match_the_worked_example_of_the_specification():
    outputs = reference_outputs(EXAMPLE)
    assert outputs["unique"] == [("101", "Alice"), ("102", "Bob"), ("103", "Charlie")]
    assert outputs["duplicates"] == [("101", "Alice"), ("102", "Bob")]
    assert outputs["duplicates_all"] == [
        ("101", "Alice"),
        ("102", "Bob"),
        ("101", "Alice"),
        ("101", "Alice"),
        ("102", "Bob"),
    ]


def test_reference_writes_no_file_without_a_duplicate_and_two_for_pairs_only():
    assert reference_outputs([("a",), ("b",)]) == {}
    pairs = reference_outputs([("a",), ("b",), ("a",), ("b",)])
    assert sorted(pairs) == ["duplicates", "unique"]


def test_reference_invariants_hold_on_random_inputs():
    rng = random.Random(11)
    for _ in range(200):
        rows = [(str(rng.randrange(8)),) for _ in range(rng.randrange(0, 40))]
        check_invariants(reference_stats(rows))


def test_reference_key_distinguishes_rows_that_a_naive_join_would_merge():
    assert reference_key(("a|b", "c")) != reference_key(("a", "b|c"))
    assert reference_key(("",)) != reference_key(("", ""))
    assert reference_key(("a", "b")) == bytes.fromhex("02 01 61 01 62")
    assert reference_key(("a|b", "c")) == bytes.fromhex("02 03 61 7c 62 01 63")
    assert reference_key(("a", "b|c")) == bytes.fromhex("02 01 61 03 62 7c 63")
    assert reference_key(("",)) == bytes.fromhex("01 00")
    assert reference_key(("", "")) == bytes.fromhex("02 00 00")
    assert reference_key(("é",)) == bytes.fromhex("01 02 c3 a9")
    assert reference_key(("x" * 200,)) == bytes.fromhex("01 c8 01") + b"x" * 200


def test_varint_is_the_unsigned_leb128():
    assert varint(0) == b"\x00"
    assert varint(127) == b"\x7f"
    assert varint(128) == b"\x80\x01"
    assert varint(300) == b"\xac\x02"


def test_reference_key_is_injective_on_random_small_rows():
    rng = random.Random(5)
    alphabet = ["", "a", "b", "|", "a|b", "é", "é", " ", "00", "0"]
    seen: dict[bytes, tuple[str, ...]] = {}
    for _ in range(3000):
        row = tuple(rng.choice(alphabet) for _ in range(rng.randrange(1, 4)))
        key = reference_key(row)
        assert seen.setdefault(key, row) == row


def test_generated_rows_have_exactly_the_requested_copies():
    for total, extra in [(1000, 275), (50, 0), (10, 9), (1, 0)]:
        stats = reference_stats(generated_rows(total, extra))
        assert stats["N"] == total
        assert stats["E"] == extra
        assert stats["D"] == total - extra


def test_csv_helpers_round_trip_multiline_cells_and_delimiters(tmp_path):
    rows = [("1", 'say "hi", please'), ("2", "line one\nline two"), ("3", "")]
    path = write_csv(tmp_path, "t.csv", rows)
    header, read = read_csv(path)
    assert header == ["id", "name"]
    assert read == rows
