# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The light count of the copies of the rows that have no ID (Unique ID lot 10, contract 6.9).

It follows the rows whose cell is absent in a column and counts, exactly, how many of them repeat
an earlier row: ``E_missing``. It writes nothing and its table follows those rows, not the file.
"""

import random

import pytest
from dedup_helpers import generated_rows, write_csv

from tabalyst.config import CsvConfig
from tabalyst.dedup.count_only import (
    MISSING_CALCULATION_VERSION,
    CopyLimits,
    IdColumn,
    count_extra_copies,
    count_missing_id_copies,
)
from tabalyst.dedup.failures import DedupInputError
from tabalyst.errors import ConfigurationError

HEADER = ["id", "name", "ref"]
BIG = CopyLimits(max_rows=10_000_000, memory_budget_mb=256, disk_budget_mb=2_048)


def _present(cell: str) -> bool:
    return bool(cell.strip())


ID_ONLY = (IdColumn("id", 0),)


def _count(path, columns=ID_ONLY, limits=BIG, **options):
    return count_missing_id_copies(
        path,
        csv=options.pop("csv", CsvConfig()),
        limits=limits,
        columns=columns,
        is_present=options.pop("is_present", _present),
        **options,
    )


def _oracle(rows, index, present=_present):
    """Brute force: the records, the distinct rows and the extra copies among the rows absent in a column."""
    absent = [tuple(row) for row in rows if not present(row[index])]
    return len(absent), len(set(absent)), len(absent) - len(set(absent))


def _snapshot(directory):
    return sorted(item.name for item in directory.iterdir())


def test_the_copies_of_rows_without_an_id_are_counted_exactly(tmp_path):
    rows = [
        ("", "Alice", "x"),
        ("", "Alice", "x"),
        ("", "Alice", "x"),
        ("", "Bob", "y"),
        ("B-1", "Bea", "z"),
        ("B-1", "Bea", "z"),
        ("   ", "Cid", "w"),
    ]
    source = write_csv(tmp_path, "rows.csv", rows, header=HEADER)

    found = _count(source)

    (column,) = found.columns
    assert found.status == "exact" and found.reason is None
    assert found.records_read == 7
    assert (column.rows_without_id, column.distinct_rows_without_id) == (5, 3)
    assert column.extra_copies_without_id == 2
    assert found.calculation_version == MISSING_CALCULATION_VERSION
    assert found.content_sha256 is not None


def test_the_copies_of_rows_with_an_id_are_not_counted(tmp_path):
    rows = [("A", "n", "r")] * 4 + [("", "n", "r")] * 2
    source = write_csv(tmp_path, "rows.csv", rows, header=HEADER)

    (column,) = _count(source).columns

    assert (column.rows_without_id, column.extra_copies_without_id) == (2, 1)


def test_a_file_without_a_missing_id_counts_nothing(tmp_path):
    source = write_csv(tmp_path, "full.csv", generated_rows(300, 40, width=3), header=HEADER)

    found = _count(source)

    assert found.status == "exact"
    assert [(c.rows_without_id, c.extra_copies_without_id) for c in found.columns] == [(0, 0)]
    assert found.records_read == 300


def test_each_column_is_followed_with_its_own_absent_cells(tmp_path):
    rows = [
        ("", "n1", ""),
        ("", "n1", ""),
        ("", "n2", "r"),
        ("a", "n3", ""),
        ("a", "n3", ""),
        ("b", "n4", "r"),
    ]
    source = write_csv(tmp_path, "rows.csv", rows, header=HEADER)

    found = _count(source, columns=(IdColumn("id", 0), IdColumn("ref", 2)))

    by_key = {c.key: c for c in found.columns}
    assert (by_key["id"].rows_without_id, by_key["id"].extra_copies_without_id) == (3, 1)
    assert (by_key["ref"].rows_without_id, by_key["ref"].extra_copies_without_id) == (4, 2)


def test_cells_with_line_breaks_quotes_and_markers_follow_the_reading_of_dedup(tmp_path):
    rows = [
        ("N/A", "a\nb", 'say "hi"'),
        ("N/A", "a\nb", 'say "hi"'),
        ("", "a\nb", 'say "hi"'),
        ("", "a\nb", 'say "hi"'),
        ("", "a\nb", 'say "hi" '),
    ]
    source = write_csv(tmp_path, "cells.csv", rows, header=HEADER)

    (column,) = _count(source, is_present=lambda cell: cell not in ("", "N/A")).columns

    assert (column.rows_without_id, column.distinct_rows_without_id) == (5, 3)
    assert column.extra_copies_without_id == 2


@pytest.mark.parametrize("seed", range(8))
def test_random_files_agree_with_a_brute_force_oracle(tmp_path, seed):
    generator = random.Random(seed)
    values = ["", " ", "a", "b", "N/A"]
    rows = [
        (generator.choice(values), generator.choice("xy"), generator.choice(values))
        for _ in range(generator.randint(1, 400))
    ]
    source = write_csv(tmp_path, "random.csv", rows, header=HEADER)
    columns = (IdColumn("id", 0), IdColumn("ref", 2))
    present = lambda cell: cell.strip() not in ("", "N/A")

    found = _count(source, columns=columns, is_present=present)

    for column, index in zip(found.columns, (0, 2), strict=True):
        records, distinct, extra = _oracle(rows, index, present)
        assert (column.rows_without_id, column.distinct_rows_without_id) == (records, distinct)
        assert column.extra_copies_without_id == extra


def test_the_total_copies_minus_those_without_an_id_leave_the_copies_with_an_id(tmp_path):
    rows = generated_rows(2_000, 300, width=3)
    rows = [("" if n % 7 == 0 else cell, name, ref) for n, (cell, name, ref) in enumerate(rows)]
    rows += rows[:50]
    source = write_csv(tmp_path, "rows.csv", rows, header=HEADER)

    total = count_extra_copies(source, csv=CsvConfig(), limits=BIG)
    (column,) = _count(source).columns
    present_copies = total.extra_copies - column.extra_copies_without_id

    seen: set[tuple[str, ...]] = set()
    expected = 0
    for row in rows:
        if _present(row[0]):
            expected += tuple(row) in seen
            seen.add(tuple(row))
    assert present_copies == expected


def test_the_table_follows_the_rows_without_an_id_not_the_file(tmp_path):
    rows = [(f"id{n}", f"n{n}", "r") for n in range(3_000)] + [("", f"m{n}", "r") for n in range(3)]
    source = write_csv(tmp_path, "wide.csv", rows, header=HEADER)
    # 1 MiB cannot hold 3,000 rows (160 bytes each plus the key) with the disk forbidden, yet
    # three rows fit: the file is read to its end.
    limits = CopyLimits(max_rows=10_000_000, memory_budget_mb=1, disk_budget_mb=0)

    found = _count(source, limits=limits)

    assert found.status == "exact" and found.storage_mode == "memory"
    assert found.columns[0].rows_without_id == 3


def test_a_stopped_count_is_limited_and_gives_lower_bounds(tmp_path):
    rows = [("", f"m{n % 2000}", "r") for n in range(8_000)]
    source = write_csv(tmp_path, "rows.csv", rows, header=HEADER)

    found = _count(source, limits=CopyLimits(max_rows=1_000, memory_budget_mb=256, disk_budget_mb=0))

    assert (found.status, found.reason) == ("limited", "row_limit")
    assert found.records_read == 1_000 and found.content_sha256 is None
    assert found.columns[0].rows_without_id == 1_000


def test_the_memory_ceiling_stops_the_count_when_the_disk_is_forbidden(tmp_path):
    rows = [("", f"{'x' * 200}{n}", "r") for n in range(20_000)]
    source = write_csv(tmp_path, "rows.csv", rows, header=HEADER)

    found = _count(source, limits=CopyLimits(10_000_000, 1, 0))

    assert (found.status, found.reason) == ("limited", "memory_budget")
    assert found.columns[0].distinct_rows_without_id < 20_000


def test_a_count_writes_nothing_beside_the_source_or_in_the_temporary_folder(tmp_path):
    rows = [("", f"{'x' * 100}{n % 4000}", "r") for n in range(9_000)]
    source = write_csv(tmp_path, "rows.csv", rows, header=HEADER)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    before = _snapshot(tmp_path)

    found = _count(source, limits=CopyLimits(10_000_000, 1, 2_048, temp_dir=scratch))

    assert found.storage_mode == "disk" and found.columns[0].extra_copies_without_id == 5_000
    assert _snapshot(tmp_path) == before
    assert _snapshot(scratch) == []


def test_a_malformed_file_is_a_dedup_input_error(tmp_path):
    source = tmp_path / "bad.csv"
    source.write_text("id,name\n1,a\n2\n", encoding="utf-8")

    with pytest.raises(DedupInputError) as caught:
        _count(source)

    assert caught.value.reason == "invalid_csv"


def test_a_count_without_a_column_is_refused(tmp_path):
    source = write_csv(tmp_path, "rows.csv", [("a", "b", "c")], header=HEADER)

    with pytest.raises(ConfigurationError):
        _count(source, columns=())
