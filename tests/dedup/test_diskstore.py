# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The disk store and the tiered store (design dedup 8.1, 8.3, 8.5; lot 3)."""

import gc
import random
import shutil
import sqlite3
import tempfile
from collections import namedtuple

import pytest
from dedup_helpers import check_invariants, reference_key, reference_stats

pytestmark = pytest.mark.dedup_lot("3")

Usage = namedtuple("Usage", "total used free")


def _rows(seed, total, distinct, width=3):
    rng = random.Random(seed)
    pool = [tuple(f"v{n}-{c}" for c in range(width)) for n in range(distinct)]
    return [rng.choice(pool) for _ in range(total)]


def _letters(stats):
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


def _marks(result, total):
    return (
        [result.marks.is_extra(i) for i in range(total)],
        [result.marks.is_group_first(i) for i in range(total)],
    )


# ------------------------------------------------------------- SqliteRowStore


def test_disk_store_reports_count_and_first_position(tmp_path):
    from tabalyst.dedup.diskstore import SqliteRowStore
    from tabalyst.dedup.store import Occurrence

    store = SqliteRowStore(tmp_path)
    try:
        assert store.storage_mode == "disk"
        assert store.observe(b"a", 4) == Occurrence(1, 4)
        assert store.observe(b"b", 5) == Occurrence(1, 5)
        assert store.observe(b"a", 9) == Occurrence(2, 4)
        assert store.observe(b"a", 12) == Occurrence(3, 4)
        assert store.distinct == len(store) == 2
    finally:
        store.close()


def test_disk_store_keeps_large_positions_and_binary_keys_apart(tmp_path):
    from tabalyst.dedup.diskstore import SqliteRowStore

    keys = [b"", b"\x00", b"\x00\x00", b"\xff" * 40, bytes(range(256))]
    store = SqliteRowStore(tmp_path)
    try:
        for index, key in enumerate(keys):
            assert store.observe(key, 3_000_000_000 + index).count == 1
        for index, key in enumerate(keys):
            assert store.observe(key, 0) == (2, 3_000_000_000 + index)
    finally:
        store.close()


def test_disk_store_commits_in_batches_and_stays_exact(tmp_path, monkeypatch):
    from tabalyst.dedup import diskstore

    monkeypatch.setattr(diskstore, "COMMIT_INTERVAL", 7)
    store = diskstore.SqliteRowStore(tmp_path)
    try:
        for position in range(50):
            store.observe(bytes([position % 11]), position)
        assert store.distinct == 11
        assert store.observe(bytes([0]), 99).count == 6
    finally:
        store.close()


def test_disk_store_deletes_its_folder_on_close_and_refuses_later_use(tmp_path):
    from tabalyst.dedup.diskstore import SqliteRowStore

    store = SqliteRowStore(tmp_path)
    store.observe(b"a", 0)
    assert len(list(tmp_path.iterdir())) == 1
    store.close()
    assert not list(tmp_path.iterdir())
    store.close()
    with pytest.raises(RuntimeError):
        store.observe(b"a", 1)


def test_disk_store_is_cleaned_up_when_it_is_dropped_without_close(tmp_path):
    from tabalyst.dedup.diskstore import SqliteRowStore

    store = SqliteRowStore(tmp_path)
    store.observe(b"a", 0)
    del store
    gc.collect()
    assert not list(tmp_path.iterdir())


def test_disk_store_works_with_an_older_sqlite_without_returning(tmp_path, monkeypatch):
    from tabalyst.dedup import diskstore
    from tabalyst.dedup.groups import count_rows

    monkeypatch.setattr(diskstore, "_RETURNING_SUPPORTED", False)
    rows = _rows(3, 300, 40)
    store = diskstore.SqliteRowStore(tmp_path)
    try:
        assert _letters(count_rows(rows, store).stats) == reference_stats(rows)
    finally:
        store.close()


@pytest.mark.parametrize("returning", [True, False])
def test_injected_digest_collisions_never_merge_different_keys(
    tmp_path, monkeypatch, returning
):
    from tabalyst.dedup import diskstore

    monkeypatch.setattr(diskstore, "_RETURNING_SUPPORTED", returning)
    store = diskstore.SqliteRowStore(tmp_path, digest=lambda key: 0)
    try:
        keys = [reference_key(row) for row in [("a|b", "c"), ("a", "b|c"), ("a", "b"), ("",)]]
        for position, key in enumerate(keys):
            assert store.observe(key, position).count == 1
        for position, key in enumerate(keys):
            assert store.observe(key, 10 + position) == (2, position)
        assert store.distinct == 4
    finally:
        store.close()


def test_digest_accelerator_gives_the_same_counts_as_the_plain_table(tmp_path):
    from tabalyst.dedup.diskstore import SqliteRowStore
    from tabalyst.dedup.groups import count_rows

    rows = _rows(11, 2000, 300)
    plain = SqliteRowStore(tmp_path)
    accelerated = SqliteRowStore(tmp_path, digest=lambda key: len(key) % 5)
    try:
        first = count_rows(rows, plain)
        second = count_rows(rows, accelerated)
    finally:
        plain.close()
        accelerated.close()
    assert first.stats == second.stats
    assert _marks(first, len(rows)) == _marks(second, len(rows))


def test_disk_store_in_a_missing_or_file_folder_is_storage_unavailable(tmp_path):
    from tabalyst.dedup.diskstore import SqliteRowStore
    from tabalyst.dedup.failures import DedupReportError

    occupied = tmp_path / "occupied"
    occupied.write_text("x", encoding="utf-8")
    for place in (occupied, tmp_path / "missing"):
        with pytest.raises(DedupReportError) as caught:
            SqliteRowStore(place)
        assert caught.value.reason == "storage_unavailable"
        assert str(tmp_path) not in str(caught.value), "no path in an exportable message"
    assert occupied.read_text(encoding="utf-8") == "x"


def test_disk_store_refuses_a_volume_without_room_and_leaves_nothing(tmp_path, monkeypatch):
    from tabalyst.dedup.diskstore import MIN_FREE_BYTES, SqliteRowStore
    from tabalyst.dedup.failures import DedupReportError

    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(10, 10, MIN_FREE_BYTES - 1))
    with pytest.raises(DedupReportError) as caught:
        SqliteRowStore(tmp_path)
    assert caught.value.reason == "insufficient_disk_space"
    assert not list(tmp_path.iterdir())


def test_disk_store_reserve_is_added_to_the_minimum_free_space(tmp_path, monkeypatch):
    from tabalyst.dedup.diskstore import MIN_FREE_BYTES, SqliteRowStore
    from tabalyst.dedup.failures import DedupReportError

    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(1, 1, MIN_FREE_BYTES + 99))
    SqliteRowStore(tmp_path, reserve_bytes=99).close()
    with pytest.raises(DedupReportError):
        SqliteRowStore(tmp_path, reserve_bytes=100)


def test_disk_store_stops_with_a_reason_when_the_volume_fills_during_the_run(
    tmp_path, monkeypatch
):
    from tabalyst.dedup import diskstore
    from tabalyst.dedup.failures import DedupReportError

    monkeypatch.setattr(diskstore, "COMMIT_INTERVAL", 10)
    free = [10**12]
    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(1, 1, free[0]))
    store = diskstore.SqliteRowStore(tmp_path)
    try:
        for position in range(25):
            store.observe(bytes([position]), position)
        free[0] = 0
        with pytest.raises(DedupReportError) as caught:
            for position in range(25, 60):
                store.observe(bytes([position]), position)
        assert caught.value.reason == "insufficient_disk_space"
    finally:
        store.close()
    assert not list(tmp_path.iterdir())


def test_a_full_database_is_reported_as_insufficient_disk_space():
    from tabalyst.dedup.diskstore import storage_failure

    full = storage_failure(sqlite3.OperationalError("database or disk is full"))
    assert full.reason == "insufficient_disk_space"
    assert storage_failure(OSError(28, "No space left on device")).reason == (
        "insufficient_disk_space"
    )
    other = storage_failure(sqlite3.OperationalError("unable to open database file"))
    assert other.reason == "storage_unavailable"


@pytest.mark.parametrize("digest", [None, lambda key: len(key)])
@pytest.mark.parametrize("entries", [0, 1, 4, 5, 6, 13])
def test_loading_entries_in_several_batches_keeps_every_count_and_position(
    tmp_path, monkeypatch, entries, digest
):
    from tabalyst.dedup import diskstore
    from tabalyst.dedup.store import Occurrence

    monkeypatch.setattr(diskstore, "_LOAD_BATCH", 5)
    store = diskstore.SqliteRowStore(tmp_path, digest=digest)
    try:
        store.load((b"key%03d" % n, Occurrence(n % 4 + 1, n * 10)) for n in range(entries))
        assert store.distinct == entries
        for n in range(entries):
            assert store.observe(b"key%03d" % n, 999) == (n % 4 + 2, n * 10)
        assert store.observe(b"other", 1000) == (1, 1000)
    finally:
        store.close()


def test_the_memory_store_lists_its_entries_in_key_order_for_the_migration():
    from tabalyst.dedup.store import MemoryRowStore, Occurrence

    store = MemoryRowStore()
    for position, key in enumerate([b"b", b"a", b"c", b"a"]):
        store.observe(key, position)
    assert list(store.sorted_items()) == [
        (b"a", Occurrence(2, 1)),
        (b"b", Occurrence(1, 0)),
        (b"c", Occurrence(1, 2)),
    ]
    store.close()
    with pytest.raises(RuntimeError):
        list(store.sorted_items())


# ------------------------------------------------------------- TieredRowStore


def test_tiered_store_stays_in_memory_under_the_budget(tmp_path):
    from tabalyst.dedup.tiered import TieredRowStore

    store = TieredRowStore(10**9, tmp_path)
    try:
        for position in range(100):
            store.observe(bytes([position]), position)
        assert store.storage_mode == "memory"
        assert not list(tmp_path.iterdir())
    finally:
        store.close()


def test_tiered_store_moves_to_disk_when_the_accounted_bytes_pass_the_budget(tmp_path):
    from tabalyst.dedup.store import ENTRY_OVERHEAD
    from tabalyst.dedup.tiered import SpillEvent, TieredRowStore

    events: list[SpillEvent] = []
    budget = 5 * (ENTRY_OVERHEAD + 3)  # the sixth distinct key of 3 bytes tips it
    store = TieredRowStore(budget, tmp_path, on_spill=events.append)
    try:
        for position in range(5):
            store.observe(b"k%02d" % position, position)
        assert store.storage_mode == "memory" and not events
        store.observe(b"k05", 5)
        assert store.storage_mode == "disk"
        assert events == [SpillEvent(6, 6, 6 * (ENTRY_OVERHEAD + 3), budget)]
        assert store.observe(b"k00", 6) == (2, 0)
        assert store.observe(b"new", 7) == (1, 7)
    finally:
        store.close()
    assert not list(tmp_path.iterdir())


def test_tiered_store_spills_only_on_a_new_key(tmp_path):
    from tabalyst.dedup.store import ENTRY_OVERHEAD
    from tabalyst.dedup.tiered import TieredRowStore

    store = TieredRowStore(2 * (ENTRY_OVERHEAD + 1), tmp_path)
    try:
        store.observe(b"a", 0)
        store.observe(b"b", 1)
        for position in range(2, 50):
            store.observe(b"a", position)
        assert store.storage_mode == "memory"
    finally:
        store.close()


@pytest.mark.parametrize("budget", [1, 300, 2000, 10_000, 10**9])
def test_counts_and_marks_do_not_depend_on_where_the_rows_are_kept(tmp_path, budget):
    from tabalyst.dedup.groups import count_rows
    from tabalyst.dedup.tiered import TieredRowStore

    cases = [(1, 0, 1), (2, 1, 1), (3, 400, 60), (4, 900, 800), (5, 500, 3)]
    for seed, total, distinct in cases:
        rows = _rows(seed, total, distinct)
        store = TieredRowStore(budget, tmp_path)
        try:
            tiered = count_rows(rows, store)
        finally:
            store.close()
        reference = count_rows(rows)
        assert tiered.stats == reference.stats
        assert _marks(tiered, total) == _marks(reference, total)
        assert _letters(tiered.stats) == reference_stats(rows)
        check_invariants(_letters(tiered.stats))
        assert not list(tmp_path.iterdir())


def test_the_move_to_disk_at_every_possible_record_keeps_every_group(tmp_path):
    """The budget is tuned so that the store tips right after each count of distinct rows."""
    from tabalyst.dedup.groups import count_rows
    from tabalyst.dedup.identity import canonical_key
    from tabalyst.dedup.store import ENTRY_OVERHEAD
    from tabalyst.dedup.tiered import TieredRowStore

    rows = _rows(21, 120, 30, width=2)
    reference = count_rows(rows)
    per_row = ENTRY_OVERHEAD + len(canonical_key(rows[0]))
    for distinct_before_spill in range(1, 30):
        store = TieredRowStore(distinct_before_spill * per_row, tmp_path)
        try:
            result = count_rows(rows, store)
            assert store.storage_mode == "disk"
        finally:
            store.close()
        assert result.stats == reference.stats
        assert _marks(result, len(rows)) == _marks(reference, len(rows))


def test_a_failed_move_to_disk_leaves_no_temporary_file_and_names_the_reason(
    tmp_path, monkeypatch
):
    from tabalyst.dedup.failures import DedupReportError
    from tabalyst.dedup.store import ENTRY_OVERHEAD
    from tabalyst.dedup.tiered import TieredRowStore

    monkeypatch.setattr(shutil, "disk_usage", lambda path: Usage(10, 10, 0))
    store = TieredRowStore(3 * (ENTRY_OVERHEAD + 2), tmp_path)
    try:
        with pytest.raises(DedupReportError) as caught:
            for position in range(10):
                store.observe(b"k%d" % position, position)
        assert caught.value.reason == "insufficient_disk_space"
    finally:
        store.close()
    assert not list(tmp_path.iterdir())


def test_a_temporary_folder_that_is_a_file_fails_with_storage_unavailable(tmp_path):
    from tabalyst.dedup.failures import DedupReportError
    from tabalyst.dedup.store import ENTRY_OVERHEAD
    from tabalyst.dedup.tiered import TieredRowStore

    occupied = tmp_path / "file"
    occupied.write_text("keep", encoding="utf-8")
    store = TieredRowStore(2 * (ENTRY_OVERHEAD + 2), occupied)
    try:
        with pytest.raises(DedupReportError) as caught:
            for position in range(10):
                store.observe(b"k%d" % position, position)
        assert caught.value.reason == "storage_unavailable"
    finally:
        store.close()
    assert occupied.read_text(encoding="utf-8") == "keep"


def test_an_interrupted_move_to_disk_deletes_the_database(tmp_path, monkeypatch):
    from tabalyst.dedup import diskstore
    from tabalyst.dedup.store import ENTRY_OVERHEAD
    from tabalyst.dedup.tiered import TieredRowStore

    def interrupted(self, entries):
        raise KeyboardInterrupt

    monkeypatch.setattr(diskstore.SqliteRowStore, "load", interrupted)
    store = TieredRowStore(2 * (ENTRY_OVERHEAD + 2), tmp_path)
    try:
        with pytest.raises(KeyboardInterrupt):
            for position in range(10):
                store.observe(b"k%d" % position, position)
    finally:
        store.close()
    assert not list(tmp_path.iterdir())


def test_tiered_store_uses_the_system_temporary_folder_by_default(monkeypatch, tmp_path):
    from tabalyst.dedup.store import ENTRY_OVERHEAD
    from tabalyst.dedup.tiered import TieredRowStore

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    store = TieredRowStore(2 * (ENTRY_OVERHEAD + 2))
    try:
        for position in range(6):
            store.observe(b"k%d" % position, position)
        assert store.storage_mode == "disk"
        assert len(list(tmp_path.iterdir())) == 1
    finally:
        store.close()
    assert not list(tmp_path.iterdir())


def test_the_estimate_grows_with_the_keys_and_the_entry_count():
    from tabalyst.dedup.tiered import estimate_disk_bytes

    assert estimate_disk_bytes(0, 0) == 0
    assert estimate_disk_bytes(1000, 10) > estimate_disk_bytes(1000, 5)
    assert estimate_disk_bytes(2000, 10) > estimate_disk_bytes(1000, 10)
