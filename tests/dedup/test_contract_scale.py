# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Row limit, memory budget and large files (design 8.3, 8.5, 9.2): T07, T08, T09,
T21 and T22.

The small versions run by default once their lot is enabled. The full-scale versions
carry ``dedup_heavy``; run them with ``-m dedup_heavy`` and put their data under the
external artifact root, never inside the checkout.
"""

import shutil
import uuid

import pytest
from dedup_helpers import (
    analyze,
    artifact_root,
    assert_published,
    count_stats,
    generated_rows,
    load_report,
    no_temporary_files,
    reference_stats,
    run,
    write_csv,
    write_generated_csv,
)

WIDE = ["id", "c1", "c2"]


def _rows(total, extra, width=3):
    return list(generated_rows(total, extra, width=width))


@pytest.fixture
def heavy_folder():
    folder = artifact_root() / f"dedup-{uuid.uuid4().hex[:8]}"
    folder.mkdir()
    yield folder
    shutil.rmtree(folder, ignore_errors=True)


# ----------------------------------------------------------------- T07


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T07")
def test_a_thousand_rows_with_275_copies_give_the_expected_counts(tmp_path):
    rows = _rows(1000, 275)
    source = write_csv(tmp_path, "t07.csv", rows, header=WIDE)
    letters = count_stats(analyze(source))
    assert letters == reference_stats(rows)
    assert (letters["D"], letters["E"]) == (725, 275)


@pytest.mark.dedup_lot("5")
@pytest.mark.dedup_t("T07")
def test_a_thousand_rows_with_275_copies_publish_the_conditional_files(tmp_path):
    rows = _rows(1000, 275)
    source = write_csv(tmp_path, "t07.csv", rows, header=WIDE)
    run(source)
    assert_published(tmp_path, "t07", rows, header=WIDE)


@pytest.mark.dedup_lot("10")
@pytest.mark.dedup_heavy
@pytest.mark.dedup_t("T07")
def test_one_million_rows_with_275000_copies_are_exact(heavy_folder):
    source = write_generated_csv(heavy_folder / "t07.csv", 1_000_000, 275_000)
    run(source)
    document = load_report(heavy_folder, "t07")
    assert document["status"] == "complete"
    records = document["records"]
    assert (records["total"], records["distinct"], records["extra_copies"]) == (
        1_000_000, 725_000, 275_000,
    )
    outputs = document["outputs"]
    assert outputs["unique"]["rows"] == 725_000
    assert outputs["duplicates"]["rows"] == records["duplicate_groups"]


# ----------------------------------------------------------------- T08


@pytest.mark.dedup_lot("10")
@pytest.mark.dedup_heavy
@pytest.mark.dedup_t("T08")
def test_ten_million_rows_are_exact_within_the_default_limit(heavy_folder):
    source = write_generated_csv(heavy_folder / "t08.csv", 10_000_000, 500_000, width=4)
    run(source)
    document = load_report(heavy_folder, "t08")
    assert document["status"] == "complete"
    records = document["records"]
    assert (records["total"], records["distinct"], records["extra_copies"]) == (
        10_000_000, 9_500_000, 500_000,
    )
    assert document["run"]["storage_mode"] in {"memory", "disk"}
    assert document["outputs"]["unique"]["rows"] == 9_500_000


# ----------------------------------------------------------------- T09


@pytest.mark.dedup_lot("4")
@pytest.mark.dedup_t("T09")
def test_exactly_max_rows_records_are_allowed_and_one_more_fails(tmp_path):
    from tabalyst.dedup.failures import DedupInputError
    from tabalyst.errors import InputError

    allowed = write_csv(tmp_path, "allowed.csv", _rows(100, 10), header=WIDE)
    assert count_stats(analyze(allowed, max_rows=100))["N"] == 100
    refused = write_csv(tmp_path, "refused.csv", _rows(101, 10), header=WIDE)
    with pytest.raises(DedupInputError) as caught:
        analyze(refused, max_rows=100)
    assert isinstance(caught.value, InputError)
    assert caught.value.reason == "row_limit_exceeded"
    assert caught.value.records_read == 101


@pytest.mark.dedup_lot("6")
@pytest.mark.dedup_t("T09")
def test_an_exceeded_limit_publishes_no_csv_and_writes_a_partial_failed_report(tmp_path):
    source = write_csv(tmp_path, "refused.csv", _rows(101, 10), header=WIDE)
    outcome = run(source, max_rows=100)
    assert outcome.status == "FAILED"
    assert outcome.reason == "row_limit_exceeded"
    document = load_report(tmp_path, "refused")
    assert document["status"] == "failed"
    assert document["failure"]["reason"] == "row_limit_exceeded"
    assert document["failure"]["limit"] == 100
    assert document["partial"] == {"records_read": 101, "certified": False}
    assert [p.name for p in tmp_path.glob("refused.*.csv")] == []
    assert no_temporary_files(tmp_path)


@pytest.mark.dedup_lot("10")
@pytest.mark.dedup_heavy
@pytest.mark.dedup_t("T09")
def test_ten_million_and_one_rows_fail_under_the_default_limit(heavy_folder):
    source = write_generated_csv(heavy_folder / "t09.csv", 10_000_001, 100_000, width=2)
    outcome = run(source)
    assert outcome.status == "FAILED"
    assert outcome.reason == "row_limit_exceeded"
    assert not list(heavy_folder.glob("t09.*.csv"))


# ----------------------------------------------------------------- T21


@pytest.mark.dedup_lot("3")
@pytest.mark.dedup_t("T21")
def test_a_tiny_budget_spills_to_disk_and_the_counts_stay_exact(tmp_path):
    rows = _rows(60_000, 10_000)
    source = write_csv(tmp_path, "spill.csv", rows, header=WIDE)
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    spilled = analyze(source, memory_budget_mb=1, temp_dir=scratch)
    assert spilled.storage_mode == "disk"
    assert count_stats(spilled) == reference_stats(rows)
    assert not list(scratch.iterdir()), "the temporary database is deleted"


@pytest.mark.dedup_lot("3")
@pytest.mark.dedup_t("T21")
def test_memory_and_disk_storage_give_identical_counts_and_marks(tmp_path):
    rows = _rows(20_000, 6_000)
    source = write_csv(tmp_path, "both.csv", rows, header=WIDE)
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    in_memory = analyze(source, memory_budget_mb=512)
    on_disk = analyze(source, memory_budget_mb=1, temp_dir=scratch)
    assert in_memory.storage_mode == "memory"
    assert on_disk.storage_mode == "disk"
    assert count_stats(in_memory) == count_stats(on_disk)
    for index in range(len(rows)):
        assert in_memory.marks.is_extra(index) == on_disk.marks.is_extra(index)
        assert in_memory.marks.is_group_first(index) == on_disk.marks.is_group_first(index)


@pytest.mark.dedup_lot("10")
@pytest.mark.dedup_heavy
@pytest.mark.dedup_t("T21")
def test_a_large_file_on_a_tiny_budget_is_exact_or_fails_never_inexact(heavy_folder):
    source = write_generated_csv(heavy_folder / "t21.csv", 3_000_000, 900_000, width=3)
    scratch = heavy_folder / "tmp"
    scratch.mkdir()
    outcome = run(source, memory_budget_mb=1, temp_dir=scratch)
    if outcome.status == "FAILED":
        assert outcome.reason in {"insufficient_disk_space", "storage_unavailable"}
        assert load_report(heavy_folder, "t21")["status"] == "failed"
        return
    records = load_report(heavy_folder, "t21")["records"]
    assert (records["distinct"], records["extra_copies"]) == (2_100_000, 900_000)


# ----------------------------------------------------------------- T22


@pytest.mark.dedup_lot("3")
@pytest.mark.dedup_t("T22")
def test_an_unusable_temporary_folder_fails_cleanly(tmp_path):
    from tabalyst.dedup.failures import DedupReportError

    rows = _rows(60_000, 5_000)
    source = write_csv(tmp_path, "nodisk.csv", rows, header=WIDE)
    not_a_folder = tmp_path / "temp-is-a-file"
    not_a_folder.write_text("occupied", encoding="utf-8")
    with pytest.raises(DedupReportError) as caught:
        analyze(source, memory_budget_mb=1, temp_dir=not_a_folder)
    assert caught.value.reason == "storage_unavailable"
    assert not_a_folder.read_text(encoding="utf-8") == "occupied"


@pytest.mark.dedup_lot("3")
@pytest.mark.dedup_t("T21", "T22")
def test_a_full_disk_fails_with_a_reason_and_leaves_no_temporary_file(
    tmp_path, monkeypatch
):
    from collections import namedtuple

    from tabalyst.dedup.failures import DedupReportError

    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(10, 10, 0))
    rows = _rows(60_000, 5_000)
    source = write_csv(tmp_path, "full.csv", rows, header=WIDE)
    folder = tmp_path / "tmp"
    folder.mkdir()
    with pytest.raises(DedupReportError) as caught:
        analyze(source, memory_budget_mb=1, temp_dir=folder)
    assert caught.value.reason == "insufficient_disk_space"
    assert not list(folder.iterdir())


@pytest.mark.dedup_lot("6")
@pytest.mark.dedup_t("T22")
def test_a_storage_failure_publishes_no_csv_and_reports_the_reason(tmp_path):
    rows = _rows(60_000, 5_000)
    source = write_csv(tmp_path, "nodisk.csv", rows, header=WIDE)
    not_a_folder = tmp_path / "temp-is-a-file"
    not_a_folder.write_text("occupied", encoding="utf-8")
    outcome = run(source, memory_budget_mb=1, temp_dir=not_a_folder)
    assert outcome.status == "FAILED"
    assert outcome.reason == "storage_unavailable"
    assert load_report(tmp_path, "nodisk")["status"] == "failed"
    assert not list(tmp_path.glob("nodisk.*.csv"))
