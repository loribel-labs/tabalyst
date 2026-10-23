# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Incremental processing, ownership and recovery (design 11, S9, ADR ownership):
T10, T14 to T17, T27, T29 and T30."""

import os
import shutil

import pytest
from dedup_helpers import (
    assert_published,
    load_report,
    no_temporary_files,
    output_names,
    run,
    write_csv,
)

TRIPLES = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c"), ("1", "a"), ("2", "b")]
PAIRS = [("1", "a"), ("2", "b"), ("1", "a"), ("2", "b"), ("3", "c")]
DISTINCT = [("1", "a"), ("2", "b"), ("3", "c")]


@pytest.fixture
def source(tmp_path):
    return write_csv(tmp_path, "customers.csv", TRIPLES)


def _bytes(path):
    return path.read_bytes()


def _csv(**options):
    from tabalyst.config import CsvConfig

    return CsvConfig(**options)


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T17")
def test_a_processed_source_is_skipped_by_metadata_and_its_report_is_untouched(
    source, tmp_path
):
    first = run(source)
    assert first.status == "DONE"
    before = _bytes(tmp_path / "customers.dedup.json")
    second = run(source)
    assert second.status == "SKIPPED"
    assert second.reason == "already_processed"
    assert second.verification == "metadata"
    assert _bytes(tmp_path / "customers.dedup.json") == before


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T17")
def test_a_source_without_duplicate_is_skipped_on_the_second_run(tmp_path):
    source = write_csv(tmp_path, "clean.csv", DISTINCT)
    assert run(source).status == "DONE"
    assert run(source).status == "SKIPPED"
    assert not (tmp_path / "clean.unique.csv").exists()


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T14")
def test_a_modified_source_is_reprocessed_and_its_managed_outputs_are_replaced(
    source, tmp_path
):
    run(source)
    write_csv(tmp_path, "customers.csv", PAIRS)
    outcome = run(source)
    assert outcome.status == "DONE"
    assert_published(tmp_path, "customers", PAIRS)
    assert load_report(tmp_path, "customers")["records"]["total"] == len(PAIRS)


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T14")
def test_when_the_duplicates_disappear_the_old_csv_are_deleted_and_the_report_replaced(
    source, tmp_path
):
    run(source)
    write_csv(tmp_path, "customers.csv", DISTINCT)
    assert run(source).status == "DONE"
    for name in output_names("customers").values():
        assert not (tmp_path / name).exists()
    document = load_report(tmp_path, "customers")
    assert document["outputs"]["csv_files_created"] == 0
    assert document["status"] == "complete"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T14")
def test_a_touched_file_with_the_same_content_is_skipped_by_digest(source, tmp_path):
    run(source)
    stat = source.stat()
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    outcome = run(source)
    assert outcome.status == "SKIPPED"
    assert outcome.verification == "digest"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T14")
def test_a_copy_with_a_new_date_is_not_reprocessed(source, tmp_path):
    run(source)
    other = tmp_path / "elsewhere"
    other.mkdir()
    shutil.copy(source, other / "customers.csv")
    for name in [*output_names("customers").values(), "customers.dedup.json"]:
        shutil.copy(tmp_path / name, other / name)
    os.utime(other / "customers.csv", ns=(1, 1))
    assert run(other / "customers.csv").status == "SKIPPED"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T15")
def test_changed_csv_settings_reprocess_a_source(source, tmp_path):
    run(source)
    outcome = run(source, csv=_csv(delimiter=";"))
    assert outcome.status == "DONE"
    assert load_report(tmp_path, "customers")["settings"]["delimiter"] == ";"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T15")
def test_a_lower_row_limit_reprocesses_and_a_higher_one_keeps_the_result(source):
    run(source)
    assert run(source, max_rows=1_000).status == "SKIPPED"
    outcome = run(source, max_rows=3)
    assert outcome.status == "FAILED"
    assert outcome.reason == "row_limit_exceeded"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T16")
def test_a_deleted_expected_csv_reprocesses_the_source(source, tmp_path):
    run(source)
    (tmp_path / "customers.duplicates.csv").unlink()
    assert run(source).status == "DONE"
    assert_published(tmp_path, "customers", TRIPLES)


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T16")
def test_an_output_edited_by_hand_is_foreign_and_refused_without_force(source, tmp_path):
    from tabalyst.errors import ReportError

    run(source)
    edited = tmp_path / "customers.unique.csv"
    edited.write_text(edited.read_text(encoding="utf-8") + "9,z\r\n", encoding="utf-8")
    with pytest.raises(ReportError):
        run(source)
    assert run(source, force=True).status == "DONE"
    assert_published(tmp_path, "customers", TRIPLES)


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T16")
def test_an_unreadable_report_is_foreign_and_replaced_only_with_force(source, tmp_path):
    from tabalyst.errors import ReportError

    (tmp_path / "customers.dedup.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ReportError):
        run(source)
    assert run(source, force=True).status == "DONE"
    assert load_report(tmp_path, "customers")["status"] == "complete"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T29")
def test_force_reprocesses_a_current_source_and_republishes_the_set(source, tmp_path):
    run(source)
    outcome = run(source, force=True)
    assert outcome.status == "DONE"
    assert outcome.verification is None
    assert_published(tmp_path, "customers", TRIPLES)


@pytest.mark.dedup_lot("1")
@pytest.mark.dedup_t("T29", "T30")
def test_force_with_verify_content_is_refused_as_an_option_with_no_effect(source):
    from tabalyst.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        run(source, force=True, verify_content=True)


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T30")
def test_verify_content_finds_a_rewrite_that_keeps_size_and_mtime(tmp_path):
    original = [("1", "a"), ("2", "b"), ("1", "a")]
    source = write_csv(tmp_path, "customers.csv", original)
    run(source)
    stat = source.stat()
    rewritten = [("1", "a"), ("2", "b"), ("2", "b")]  # same size, other duplicates
    write_csv(tmp_path, "customers.csv", rewritten)
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert source.stat().st_size == stat.st_size
    assert run(source).status == "SKIPPED"  # the documented limit of the metadata level
    outcome = run(source, verify_content=True)
    assert outcome.status == "DONE"
    assert_published(tmp_path, "customers", rewritten)


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T30")
def test_verify_content_on_an_unchanged_source_skips_with_the_digest_level(source):
    run(source)
    outcome = run(source, verify_content=True)
    assert outcome.status == "SKIPPED"
    assert outcome.verification == "digest"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T14")
def test_a_failure_replaces_the_report_and_deletes_the_previous_outputs(source, tmp_path):
    run(source)
    source.write_text("id,name\r\n1,a\r\n2\r\n", encoding="utf-8", newline="")
    outcome = run(source)
    assert outcome.status == "FAILED"
    assert outcome.reason == "invalid_csv"
    document = load_report(tmp_path, "customers")
    assert document["status"] == "failed"
    assert "outputs" not in document and "records" not in document
    for name in output_names("customers").values():
        assert not (tmp_path / name).exists()
    assert no_temporary_files(tmp_path)


class Crash(BaseException):
    """An interruption that no handler of the engine may swallow."""


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T27")
def test_an_interruption_at_any_replace_leaves_a_state_that_the_next_run_repairs(
    tmp_path, monkeypatch
):
    real_replace = os.replace
    attempt = 1
    while True:
        folder = tmp_path / f"attempt-{attempt}"
        folder.mkdir()
        source = write_csv(folder, "customers.csv", TRIPLES)
        run(source)
        write_csv(folder, "customers.csv", PAIRS)
        final_rows = PAIRS
        calls = 0

        def flaky(src, dst, *args, _target=attempt, **kwargs):
            nonlocal calls
            calls += 1
            if calls == _target:
                raise Crash
            return real_replace(src, dst, *args, **kwargs)

        monkeypatch.setattr(os, "replace", flaky)
        crashed = False
        try:
            run(source)
        except Crash:
            crashed = True
        finally:
            monkeypatch.setattr(os, "replace", real_replace)
        outcome = run(source)  # the next run, without interruption
        assert outcome.status == ("DONE" if crashed else "SKIPPED")
        assert_published(folder, "customers", final_rows)
        document = load_report(folder, "customers")
        assert document["status"] == "complete"
        assert no_temporary_files(folder)
        if not crashed:
            break
        attempt += 1
    assert attempt >= 4, "the publication has at least a recovery report, CSV and a report"


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T27")
def test_stale_temporary_files_of_the_managed_names_are_removed_and_others_kept(
    source, tmp_path
):
    stale = tmp_path / ".customers.unique.csv.abc123.tmp"
    stale.write_bytes(b"half a file")
    other = tmp_path / ".notes.txt.abc123.tmp"
    other.write_bytes(b"not ours")
    run(source)
    assert not stale.exists()
    assert other.exists()


@pytest.mark.dedup_lot("7")
@pytest.mark.dedup_t("T27")
def test_a_recovery_report_is_never_reused_as_a_processing(source, tmp_path):
    import json

    run(source)
    path = tmp_path / "customers.dedup.json"
    complete = json.loads(path.read_text(encoding="utf-8"))
    outputs = complete["outputs"]
    inventory = [
        {key: outputs[kind][key] for key in ("file", "size_bytes", "sha256")}
        for kind in ("unique", "duplicates", "duplicates_all")
        if outputs[kind]
    ]
    recovery = {
        key: complete[key]
        for key in ("format", "format_version", "format_revision", "generator")
    }
    recovery |= {
        "status": "in_progress",
        "source": complete["source"],
        "settings": complete["settings"],
        "recovery": {"previous_outputs": inventory, "planned_outputs": []},
    }
    path.write_text(json.dumps(recovery), encoding="utf-8")
    outcome = run(source)
    assert outcome.status == "DONE"  # owned through the recovery report, not reused
    assert load_report(tmp_path, "customers")["status"] == "complete"
    assert_published(tmp_path, "customers", TRIPLES)


@pytest.mark.dedup_lot("8")
@pytest.mark.dedup_t("T10")
def test_a_batch_skips_two_processed_files_and_processes_the_third(tmp_path):
    import tabalyst

    names = ["customers", "products", "orders"]
    sources = [write_csv(tmp_path, f"{name}.csv", TRIPLES) for name in names]
    for early in sources[:2]:
        tabalyst.dedup_csv(early)
    batch = tabalyst.generate_dedups([str(tmp_path / "*.csv")])
    statuses = {item.source.name: item.status for item in batch.results}
    assert statuses == {
        "customers.csv": "SKIPPED",
        "products.csv": "SKIPPED",
        "orders.csv": "DONE",
    }
    assert not batch.failures
    assert (tmp_path / "dedup.summary.json").exists()
