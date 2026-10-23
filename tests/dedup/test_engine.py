# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact engine of lot 2: key, store, counters, marks and ``count_rows``.

These tests complement the contract tests of ``test_contract_identity.py`` with the
edge cases of the implementation (design dedup 5, 8.1 to 8.4).
"""

import itertools
import random

import pytest
from dedup_helpers import check_invariants, reference_key, reference_stats, varint

pytestmark = pytest.mark.dedup_lot("2")


def _letters(stats) -> dict[str, int]:
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


def _decode(key: bytes) -> tuple[str, ...]:
    """Decode a key with an independent LEB128 reader: proves the code is unambiguous."""

    def read(position: int) -> tuple[int, int]:
        value = shift = 0
        while True:
            byte = key[position]
            position += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value, position

    cells, position = read(0)
    row = []
    for _ in range(cells):
        length, position = read(position)
        row.append(key[position : position + length].decode("utf-8"))
        position += length
    assert position == len(key)
    return tuple(row)


# ------------------------------------------------------------------ the key


def test_key_of_a_cell_of_200_bytes_uses_two_length_bytes():
    from tabalyst.dedup.identity import canonical_key

    key = canonical_key(("a" * 200,))
    assert key == bytes.fromhex("01c801") + b"a" * 200


@pytest.mark.parametrize("length", [127, 128, 16383, 16384])
def test_key_lengths_cross_the_leb128_byte_boundaries(length):
    from tabalyst.dedup.identity import canonical_key

    key = canonical_key(("a" * length,))
    assert key == b"\x01" + varint(length) + b"a" * length


def test_key_of_a_row_of_130_cells_uses_two_count_bytes():
    from tabalyst.dedup.identity import canonical_key

    row = ("",) * 130
    assert canonical_key(row) == bytes.fromhex("8201") + bytes(130)


def test_varint_is_the_unsigned_leb128_of_the_design():
    from tabalyst.dedup.identity import varint as product_varint

    for value in [0, 1, 127, 128, 255, 300, 16383, 16384, 2**21, 2**35 + 5]:
        assert product_varint(value) == varint(value)


def test_key_counts_utf8_bytes_not_characters():
    from tabalyst.dedup.identity import canonical_key

    assert canonical_key(("€",)) == bytes.fromhex("0103e282ac")
    assert canonical_key(("é",)) != canonical_key(("é",))


def test_every_small_row_has_its_own_key_and_decodes_back():
    from tabalyst.dedup.identity import canonical_key

    alphabet = ["", "a", "b", "|", "ab", "\x00", "é"]
    keys: dict[bytes, tuple[str, ...]] = {}
    for width in range(4):
        for row in itertools.product(alphabet, repeat=width):
            key = canonical_key(row)
            assert key not in keys, f"{row!r} collides with {keys.get(key)!r}"
            keys[key] = row
            assert _decode(key) == row
            assert key == reference_key(row)


# ---------------------------------------------------------------- the store


def test_memory_store_reports_count_and_first_position():
    from tabalyst.dedup.store import MemoryRowStore, Occurrence

    store = MemoryRowStore()
    assert store.storage_mode == "memory"
    assert store.observe(b"x", 5) == Occurrence(1, 5)
    assert store.observe(b"y", 6) == Occurrence(1, 6)
    assert store.observe(b"x", 9) == Occurrence(2, 5)
    assert store.observe(b"x", 12) == Occurrence(3, 5)
    assert len(store) == 2
    store.close()


def test_memory_store_keeps_large_positions_and_counts_apart():
    from tabalyst.dedup.store import MemoryRowStore

    store = MemoryRowStore()
    big = 10_000_000_000
    store.observe(b"k", big)
    for _ in range(1000):
        occurrence = store.observe(b"k", big + 1)
    assert occurrence == (1001, big)
    store.close()


def test_memory_store_accounts_the_key_length_and_the_overhead_per_distinct_key():
    from tabalyst.dedup.store import ENTRY_OVERHEAD, MemoryRowStore

    store = MemoryRowStore()
    store.observe(b"abc", 0)
    store.observe(b"abc", 1)
    store.observe(b"defgh", 2)
    assert store.accounted_bytes == (3 + ENTRY_OVERHEAD) + (5 + ENTRY_OVERHEAD)
    store.close()


def test_memory_store_lists_its_entries_for_the_migration_to_disk():
    from tabalyst.dedup.store import MemoryRowStore, Occurrence

    store = MemoryRowStore()
    store.observe(b"a", 0)
    store.observe(b"b", 1)
    store.observe(b"a", 2)
    assert dict(store.items()) == {b"a": Occurrence(2, 0), b"b": Occurrence(1, 1)}
    store.close()


def test_closed_memory_store_refuses_further_use_and_forgets_its_entries():
    from tabalyst.dedup.store import MemoryRowStore

    store = MemoryRowStore()
    store.observe(b"a", 0)
    store.close()
    assert store.accounted_bytes == 0
    with pytest.raises(RuntimeError, match="closed"):
        store.observe(b"a", 1)
    with pytest.raises(RuntimeError, match="closed"):
        len(store)
    with pytest.raises(RuntimeError, match="closed"):
        list(store.items())
    store.close()


def test_memory_store_fails_instead_of_overflowing_its_packed_count():
    from tabalyst.dedup import store as store_module
    from tabalyst.dedup.failures import DedupReportError

    store = store_module.MemoryRowStore()
    store.observe(b"k", 7)
    store._entries[b"k"] = (7 << store_module._COUNT_BITS) | store_module._COUNT_MASK
    with pytest.raises(DedupReportError) as caught:
        store.observe(b"k", 8)
    assert caught.value.reason == "unexpected_error"
    store.close()


def test_varint_refuses_a_negative_value():
    from tabalyst.dedup.identity import varint as product_varint

    with pytest.raises(ValueError, match="unsigned"):
        product_varint(-1)


def test_dedup_errors_survive_pickling_with_their_reason():
    import pickle

    from tabalyst.dedup.failures import DedupInputError, DedupReportError

    original = DedupInputError("too long", reason="row_limit_exceeded", records_read=11, limit=10)
    copy = pickle.loads(pickle.dumps(original))
    assert (str(copy), copy.reason, copy.records_read, copy.limit) == (
        "too long", "row_limit_exceeded", 11, 10,
    )
    other = pickle.loads(pickle.dumps(DedupReportError("full", reason="insufficient_disk_space")))
    assert (str(other), other.reason, other.records_read) == (
        "full", "insufficient_disk_space", None,
    )


# ------------------------------------------------------ counters and marks


def test_counters_follow_the_count_transitions():
    from tabalyst.dedup.groups import GroupCounters

    counters = GroupCounters()
    for count in [1, 1, 2, 1, 2, 3, 4, 1]:
        counters.update(count)
    stats = counters.stats()
    assert _letters(stats) == {
        "N": 8, "D": 4, "G": 2, "E": 4, "O": 6, "S": 2, "M": 4, "G2": 1, "G3+": 1,
    }
    assert stats.violations() == []


def test_counters_of_an_empty_input_are_all_zero():
    from tabalyst.dedup.groups import GroupCounters

    stats = GroupCounters().stats()
    assert all(value == 0 for value in _letters(stats).values())
    assert stats.extra_copy_percent == 0
    stats.check()


def test_extra_copy_percent_is_the_share_of_extra_copies():
    from tabalyst.dedup.groups import GroupCounters

    counters = GroupCounters()
    for count in [1, 2, 1, 1]:
        counters.update(count)
    assert counters.stats().extra_copy_percent == 25.0


@pytest.mark.parametrize(
    "change",
    [
        {"total": 11},
        {"singletons": 4},
        {"duplicate_group_occurrences": 5},
        {"groups_occurring_twice": 0},
        {"max_occurrences": 1},
        {"max_occurrences": 3},
        {"max_occurrences": 0},
    ],
)
def test_broken_counts_are_an_internal_error_never_a_result(change):
    from tabalyst.dedup.failures import DedupReportError
    from tabalyst.dedup.groups import GroupStats

    good = {
        "total": 10, "distinct": 8, "singletons": 6, "duplicate_groups": 2,
        "groups_occurring_twice": 2, "groups_occurring_three_plus": 0,
        "extra_copies": 2, "duplicate_group_occurrences": 4, "max_occurrences": 2,
    }
    GroupStats(**good).check()
    stats = GroupStats(**{**good, **change})
    assert stats.violations()
    with pytest.raises(DedupReportError) as caught:
        stats.check()
    assert caught.value.reason == "unexpected_error"


def test_marks_read_false_beyond_what_was_marked_and_grow_on_demand():
    from tabalyst.dedup.groups import RecordMarks

    marks = RecordMarks()
    assert not marks.is_extra(10**9)
    marks.mark_extra(3)
    marks.mark_extra(2_000_000)
    marks.mark_group_first(0)
    assert marks.is_extra(3) and marks.is_extra(2_000_000)
    assert not marks.is_extra(4) and not marks.is_extra(2_000_001)
    assert marks.is_group_first(0) and not marks.is_group_first(1)
    assert marks.extra_total() == 2
    assert marks.group_first_total() == 1


def test_marks_trim_to_the_records_read_and_keep_their_bits():
    from tabalyst.dedup.groups import RecordMarks

    marks = RecordMarks()
    marks.mark_extra(9)
    marks.mark_group_first(1)
    marks.trim(10)
    assert marks.nbytes == 4
    assert marks.is_extra(9) and marks.is_group_first(1)


# --------------------------------------------------------------- count_rows


def test_count_rows_on_the_worked_example_of_the_specification():
    from tabalyst.dedup.groups import count_rows

    rows = [("101", "Alice"), ("102", "Bob"), ("101", "Alice"),
            ("103", "Charlie"), ("101", "Alice"), ("102", "Bob")]
    result = count_rows(rows)
    assert _letters(result.stats) == {
        "N": 6, "D": 3, "G": 2, "E": 3, "O": 5, "S": 1, "M": 3, "G2": 1, "G3+": 1,
    }
    assert [result.marks.is_extra(i) for i in range(6)] == [
        False, False, True, False, True, True,
    ]
    assert [result.marks.is_group_first(i) for i in range(6)] == [
        True, True, False, False, False, False,
    ]


def test_count_rows_accepts_a_generator_and_an_empty_input():
    from tabalyst.dedup.groups import count_rows

    assert count_rows(iter([])).stats.total == 0
    assert count_rows((str(i % 2),) for i in range(5)).stats.distinct == 2


def test_count_rows_closes_the_store_it_creates_and_leaves_a_given_one_open(monkeypatch):
    from tabalyst.dedup import groups
    from tabalyst.dedup.store import MemoryRowStore

    created: list[MemoryRowStore] = []

    class Recording(MemoryRowStore):
        def __init__(self) -> None:
            super().__init__()
            created.append(self)

    monkeypatch.setattr(groups, "MemoryRowStore", Recording)
    groups.count_rows([("a",), ("a",)])
    with pytest.raises(RuntimeError, match="closed"):
        len(created[0])

    given = MemoryRowStore()
    groups.count_rows([("a",), ("a",)], given)
    assert len(given) == 1
    given.close()


def test_count_rows_stops_at_the_record_after_the_limit():
    from tabalyst.dedup.failures import DedupInputError
    from tabalyst.dedup.groups import count_rows

    rows = [(str(i),) for i in range(10)]
    assert count_rows(rows, max_rows=10).stats.total == 10
    with pytest.raises(DedupInputError) as caught:
        count_rows(rows, max_rows=9)
    error = caught.value
    assert error.reason == "row_limit_exceeded"
    assert error.records_read == 10
    assert error.limit == 9
    assert "9" in str(error)


def test_count_rows_consumes_no_record_beyond_the_one_that_exceeds_the_limit():
    from tabalyst.dedup.failures import DedupInputError
    from tabalyst.dedup.groups import count_rows

    consumed = 0

    def source():
        nonlocal consumed
        for number in range(1000):
            consumed += 1
            yield (str(number),)

    with pytest.raises(DedupInputError):
        count_rows(source(), max_rows=5)
    assert consumed == 6


def test_count_rows_runs_the_same_on_any_store_that_follows_the_interface():
    from tabalyst.dedup.groups import count_rows
    from tabalyst.dedup.store import Occurrence

    class DictStore:
        storage_mode = "memory"

        def __init__(self) -> None:
            self.table: dict[bytes, list[int]] = {}

        def observe(self, key: bytes, position: int) -> Occurrence:
            entry = self.table.setdefault(key, [0, position])
            entry[0] += 1
            return Occurrence(entry[0], entry[1])

        def close(self) -> None:
            self.table.clear()

    rng = random.Random(5)
    rows = [(rng.choice("abcd"), rng.choice("xy")) for _ in range(200)]
    assert count_rows(rows, DictStore()).stats == count_rows(rows).stats


def test_count_rows_matches_the_counter_reference_on_wider_random_inputs():
    from tabalyst.dedup.groups import count_rows

    rng = random.Random(99)
    for _ in range(50):
        pool = [tuple(rng.choice(["", "a", "b|c", "0", "00"]) for _ in range(rng.randrange(1, 4)))
                for _ in range(rng.randrange(1, 40))]
        rows = [rng.choice(pool) for _ in range(rng.randrange(0, 400))]
        result = count_rows(rows)
        letters = _letters(result.stats)
        assert letters == reference_stats(rows)
        check_invariants(letters)
        # The marks fix the outputs: unique is every record not marked extra.
        assert sum(not result.marks.is_extra(i) for i in range(len(rows))) == letters["D"]
        assert sum(result.marks.is_group_first(i) for i in range(len(rows))) == letters["G"]


def test_marks_of_ten_million_records_stay_in_a_few_megabytes():
    from tabalyst.dedup.groups import RecordMarks

    marks = RecordMarks()
    marks.mark_extra(9_999_999)
    marks.mark_group_first(9_999_999)
    marks.trim(10_000_000)
    assert marks.nbytes == 2 * 1_250_000
