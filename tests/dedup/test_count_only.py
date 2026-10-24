# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The count-only mode of the engine (Unique ID lot 6, contract 6.2 and design 20.40).

It counts the extra copies of rows like ``analyze_dedup``, under ceilings of its own, and writes
nothing: no output CSV, no report, no temporary file left behind.
"""

import pytest
from dedup_helpers import analyze, generated_rows, write_csv

from tabalyst.config import CsvConfig
from tabalyst.dedup.count_only import (
    CALCULATION_VERSION,
    CopyLimits,
    count_extra_copies,
)
from tabalyst.dedup.failures import DedupInputError
from tabalyst.errors import ConfigurationError

WIDE = ["id", "c1", "c2"]
BIG = CopyLimits(max_rows=10_000_000, memory_budget_mb=256, disk_budget_mb=2_048)


def _count(path, limits=BIG, **options):
    return count_extra_copies(path, csv=options.pop("csv", CsvConfig()), limits=limits, **options)


def _snapshot(directory):
    return sorted(item.name for item in directory.iterdir())


def test_an_exact_count_equals_the_extra_copies_of_the_dedup_analysis(tmp_path):
    source = write_csv(tmp_path, "rows.csv", generated_rows(4_000, 700, width=3), header=WIDE)

    found = _count(source)
    analysis = analyze(source)

    assert found.status == "exact" and found.reason is None
    assert found.extra_copies == analysis.stats.extra_copies == 700
    assert found.distinct_rows == analysis.stats.distinct
    assert found.duplicate_groups == analysis.stats.duplicate_groups
    assert found.records_read == analysis.stats.total == 4_000
    assert found.content_sha256 == analysis.source.content_sha256
    assert found.calculation_version == CALCULATION_VERSION


def test_cells_with_line_breaks_quotes_and_empty_values_count_like_dedup(tmp_path):
    rows = [
        ("1", "a\nb", ""),
        ("1", "a\nb", ""),
        ("2", 'say "hi"', "x,y"),
        ("2", 'say "hi"', "x,y"),
        ("2", 'say "hi"', "x,y"),
        ("3", "", ""),
        ("3", " ", ""),
    ]
    source = write_csv(tmp_path, "cells.csv", rows, header=WIDE)

    found = _count(source)

    assert found.extra_copies == analyze(source).stats.extra_copies == 3
    assert found.records_read == 7


def test_a_file_without_copies_counts_none(tmp_path):
    source = write_csv(tmp_path, "unique.csv", generated_rows(500, 0, width=3), header=WIDE)

    found = _count(source)

    assert (found.status, found.extra_copies, found.duplicate_groups) == ("exact", 0, 0)


def test_a_count_writes_nothing_beside_the_source_or_in_the_temporary_folder(tmp_path):
    source = write_csv(tmp_path, "rows.csv", generated_rows(9_900, 900, width=3), header=WIDE)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    before = _snapshot(tmp_path)

    # One MiB of budget moves the table to the disk: the database must be deleted too.
    found = _count(
        source, CopyLimits(10_000_000, 1, 2_048, temp_dir=scratch)
    )

    assert found.storage_mode == "disk" and found.extra_copies == 900
    assert _snapshot(tmp_path) == before
    assert _snapshot(scratch) == []


def test_the_count_on_disk_is_the_count_in_memory(tmp_path):
    source = write_csv(tmp_path, "rows.csv", generated_rows(30_000, 4_000, width=4), header=[*WIDE, "c3"])

    in_memory = _count(source)
    on_disk = _count(source, CopyLimits(10_000_000, 1, 2_048))

    assert (in_memory.storage_mode, on_disk.storage_mode) == ("memory", "disk")
    assert in_memory.extra_copies == on_disk.extra_copies == 4_000
    assert in_memory.distinct_rows == on_disk.distinct_rows


def test_a_row_ceiling_gives_a_lower_bound_never_a_count(tmp_path):
    source = write_csv(tmp_path, "rows.csv", generated_rows(5_000, 1_500, width=3), header=WIDE)
    exact = analyze(source).stats.extra_copies

    found = _count(source, CopyLimits(2_000, 256, 2_048))

    assert found.status == "limited" and found.reason == "row_limit"
    assert found.records_read == 2_000
    assert 0 < found.extra_copies < exact
    assert found.content_sha256 is None


def test_without_a_disk_the_memory_budget_stops_the_count(tmp_path):
    source = write_csv(tmp_path, "rows.csv", generated_rows(20_000, 2_000, width=3), header=WIDE)
    exact = analyze(source).stats.extra_copies

    found = _count(source, CopyLimits(10_000_000, 1, 0))

    assert found.status == "limited" and found.reason == "memory_budget"
    assert found.storage_mode == "memory"
    assert found.records_read < 20_000
    assert found.extra_copies <= exact


def test_the_disk_budget_stops_the_count_on_disk(tmp_path):
    source = write_csv(tmp_path, "rows.csv", generated_rows(60_000, 6_000, width=3), header=WIDE)
    exact = analyze(source).stats.extra_copies

    found = _count(source, CopyLimits(10_000_000, 1, 1))

    assert found.status == "limited" and found.reason == "disk_budget"
    assert found.storage_mode == "disk"
    assert found.extra_copies <= exact


def test_the_same_file_and_ceilings_stop_at_the_same_record(tmp_path):
    source = write_csv(tmp_path, "rows.csv", generated_rows(20_000, 2_000, width=3), header=WIDE)
    limits = CopyLimits(10_000_000, 1, 0)

    first, second = _count(source, limits), _count(source, limits)

    assert (first.records_read, first.extra_copies) == (second.records_read, second.extra_copies)


def test_a_record_of_another_width_is_refused_like_dedup_refuses_it(tmp_path):
    source = tmp_path / "ragged.csv"
    source.write_text("id,name\r\n1,a\r\n2\r\n", encoding="utf-8")

    with pytest.raises(DedupInputError) as caught:
        _count(source)

    assert caught.value.reason == "invalid_csv"


def test_a_ceiling_below_its_minimum_is_a_configuration_error(tmp_path):
    source = write_csv(tmp_path, "rows.csv", [("1", "a")])

    with pytest.raises(ConfigurationError):
        _count(source, CopyLimits(10, 0, 0))
    with pytest.raises(ConfigurationError):
        _count(source, CopyLimits(10, 1, -1))
