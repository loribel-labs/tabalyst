# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact row identity (design 5, S5): T18, T19 and T20.

Lot 2 provides the pure engine (``canonical_key``, the stores and ``count_rows``);
lot 3 the disk store; lot 5 the written values.
"""

import random

import pytest
from dedup_helpers import (
    assert_published,
    check_invariants,
    reference_key,
    reference_stats,
    run,
    write_csv,
)

VECTORS = [
    (("a", "b"), "02 01 61 01 62"),
    (("a|b", "c"), "02 03 61 7c 62 01 63"),
    (("a", "b|c"), "02 01 61 03 62 7c 63"),
    (("",), "01 00"),
    (("", ""), "02 00 00"),
    (("é",), "01 02 c3 a9"),
]


def _count(rows, **options):
    from tabalyst.dedup.groups import count_rows

    return count_rows(rows, **options)


def _stats_letters(result) -> dict[str, int]:
    stats = result.stats
    return {
        "N": stats.total,
        "D": stats.distinct,
        "G": stats.duplicate_groups,
        "E": stats.extra_copies,
        "O": stats.duplicate_group_occurrences,
        "S": stats.singletons,
        "M": stats.max_occurrences,
        "G2": stats.groups_occurring_twice,
        "G3+": stats.groups_occurring_three_plus,
    }


@pytest.mark.dedup_lot("2")
@pytest.mark.dedup_t("T19")
@pytest.mark.parametrize(("row", "expected"), VECTORS)
def test_canonical_key_matches_the_vectors_of_the_design(row, expected):
    from tabalyst.dedup.identity import canonical_key

    assert canonical_key(row) == bytes.fromhex(expected)


@pytest.mark.dedup_lot("2")
@pytest.mark.dedup_t("T19")
def test_canonical_key_agrees_with_the_reference_on_random_rows():
    from tabalyst.dedup.identity import canonical_key

    rng = random.Random(3)
    alphabet = ["", "a", "|", ",", '"', "\n", "é", "é", "x" * 300]
    for _ in range(2000):
        row = tuple(rng.choice(alphabet) for _ in range(rng.randrange(1, 5)))
        assert canonical_key(row) == reference_key(row)


@pytest.mark.dedup_lot("2")
@pytest.mark.dedup_t("T19")
def test_rows_that_differ_by_blanks_case_or_leading_zeros_are_never_merged():
    rows = [
        ("101", "Alice"),
        ("101", " Alice"),
        ("101", "Alice "),
        ("101", "alice"),
        ("0101", "Alice"),
        ("00101", "Alice"),
        ("101", "Alice", "X"),
        ("101", ""),
        ("101", " "),
        ("é", "n"),
        ("é", "n"),
    ]
    result = _count(rows)
    assert result.stats.distinct == len(rows)
    assert result.stats.duplicate_groups == 0


@pytest.mark.dedup_lot("2")
@pytest.mark.dedup_t("T18")
def test_cells_with_separators_quotes_and_line_breaks_keep_their_identity():
    rows = [
        ("a|b", "c"),
        ("a", "b|c"),
        ("a,b", "c"),
        ("a", "b,c"),
        ('say "hi"', "x"),
        ("line one\nline two", "x"),
        ("line one", "line two\nx"),
        ("a,b", "c"),
        ('say "hi"', "x"),
    ]
    result = _count(rows)
    assert _stats_letters(result) == reference_stats(rows)


@pytest.mark.dedup_lot("2")
@pytest.mark.dedup_t("T18", "T19")
def test_counts_equal_the_counter_reference_on_random_inputs_and_hold_the_invariants():
    rng = random.Random(21)
    pool = [("a",), ("b",), ("a", "b"), ("",), ("a|b",), ("b", "a")]
    for _ in range(300):
        rows = [rng.choice(pool) for _ in range(rng.randrange(0, 60))]
        result = _count(rows)
        letters = _stats_letters(result)
        assert letters == reference_stats(rows)
        check_invariants(letters)


@pytest.mark.dedup_lot("2")
@pytest.mark.dedup_t("T18")
def test_marks_flag_the_extra_copies_and_the_first_record_of_each_repeated_group():
    rows = [("a",), ("b",), ("a",), ("c",), ("a",), ("b",)]
    marks = _count(rows).marks
    assert [marks.is_extra(i) for i in range(6)] == [
        False, False, True, False, True, True,
    ]
    assert [marks.is_group_first(i) for i in range(6)] == [
        True, True, False, False, False, False,
    ]


@pytest.mark.dedup_lot("2")
@pytest.mark.dedup_t("T20")
def test_memory_store_never_merges_two_keys_whose_hashes_collide():
    from tabalyst.dedup.store import MemoryRowStore

    class Colliding(bytes):
        """Every instance hashes to the same value; equality stays by content."""

        def __hash__(self) -> int:
            return 0

    store = MemoryRowStore()
    assert store.observe(Colliding(b"first"), 0) == (1, 0)
    assert store.observe(Colliding(b"second"), 1) == (1, 1)
    assert store.observe(Colliding(b"first"), 2) == (2, 0)
    assert store.observe(Colliding(b"second"), 3) == (2, 1)
    store.close()


@pytest.mark.dedup_lot("3")
@pytest.mark.dedup_t("T20")
def test_disk_store_never_merges_two_keys_whose_digests_collide(tmp_path):
    from tabalyst.dedup.diskstore import SqliteRowStore

    store = SqliteRowStore(tmp_path, digest=lambda key: 0)
    try:
        assert store.observe(b"first", 0) == (1, 0)
        assert store.observe(b"second", 1) == (1, 1)
        assert store.observe(b"first", 2) == (2, 0)
        assert store.observe(b"second", 3) == (2, 1)
    finally:
        store.close()
    assert not list(tmp_path.iterdir()), "the temporary database is deleted"


@pytest.mark.dedup_lot("5")
@pytest.mark.dedup_t("T18")
def test_written_files_keep_commas_quotes_and_multiline_cells(tmp_path):
    rows = [
        ("1", 'say "hi", please'),
        ("2", "line one\nline two"),
        ("1", 'say "hi", please'),
        ("3", ""),
        ("2", "line one\nline two"),
        ("1", 'say "hi", please'),
    ]
    source = write_csv(tmp_path, "tricky.csv", rows)
    run(source)
    assert_published(tmp_path, "tricky", rows)
