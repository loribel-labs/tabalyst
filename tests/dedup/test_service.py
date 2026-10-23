# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The batch runner, the batch report and the Python API (design dedup 4.3, 13.1)."""

import json
import os
from pathlib import Path

import jsonschema
import pytest
from dedup_helpers import (
    assert_published,
    load_report,
    no_temporary_files,
    settings,
    write_csv,
)

import tabalyst
from tabalyst import dedup_service
from tabalyst.dedup.batch_report import (
    SCHEMA_FILE,
    BatchReport,
    batch_schema,
    batch_schema_text,
    is_batch_report,
    relative_path,
)
from tabalyst.dedup.failures import DedupInputError
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.progress import ProgressPhase

pytestmark = pytest.mark.dedup_lot("8")

TRIPLES = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c"), ("1", "a"), ("2", "b")]
PAIRS = [("1", "a"), ("2", "b"), ("1", "a"), ("2", "b"), ("3", "c")]
DISTINCT = [("1", "a"), ("2", "b"), ("3", "c")]
MALFORMED = "id,name\r\n1,a\r\n2\r\n"


def _batch(*specs, **options):
    return tabalyst.generate_dedups([str(spec) for spec in specs], **options)


def _statuses(batch):
    return {item.source.name: item.status for item in batch.results}


def _summary(folder: Path) -> dict:
    return json.loads((folder / "dedup.summary.json").read_text(encoding="utf-8"))


def _assert_valid_summary(document: dict) -> None:
    schema_path = Path(tabalyst.__file__).parent / "schemas" / SCHEMA_FILE
    jsonschema.validate(document, json.loads(schema_path.read_text(encoding="utf-8")))
    BatchReport.model_validate(document)


def _bad_csv(folder: Path, name: str = "broken.csv") -> Path:
    path = folder / name
    path.write_text(MALFORMED, encoding="utf-8", newline="")
    return path


@pytest.fixture
def folder(tmp_path):
    """Three sources: one processed earlier, one new, one with duplicates only of pairs."""
    write_csv(tmp_path, "a.csv", TRIPLES)
    write_csv(tmp_path, "b.csv", PAIRS)
    write_csv(tmp_path, "c.csv", DISTINCT)
    return tmp_path


# --------------------------------------------------------- the batch runner


def test_a_mixed_batch_reports_done_skipped_failed_and_excluded(folder):
    tabalyst.dedup_csv(folder / "a.csv")
    _bad_csv(folder)

    batch = _batch(folder / "*.csv")

    assert _statuses(batch) == {
        "a.csv": "SKIPPED",
        "b.csv": "DONE",
        "broken.csv": "FAILED",
        "c.csv": "DONE",
    }
    assert {path.name: reason for path, reason in batch.excluded} == {
        "a.unique.csv": "derived_csv",
        "a.duplicates.csv": "derived_csv",
        "a.duplicates_all.csv": "derived_csv",
    }
    assert [item.source.name for item in batch.failures] == ["broken.csv"]
    assert not batch.succeeded
    document = _summary(folder)
    _assert_valid_summary(document)
    assert document["counters"] == {
        "found": 7, "eligible": 4, "excluded": 3, "done": 2, "skipped": 1, "failed": 1,
    }
    assert document["status"] == "partial"
    entries = {item["file"]: item for item in document["sources"]}
    assert entries["a.csv"]["status"] == "SKIPPED"
    assert entries["a.csv"]["reason"] == "already_processed"
    assert entries["a.csv"]["verification"] == "metadata"
    assert entries["a.csv"]["csv_files_created"] == 0
    assert entries["b.csv"]["csv_files_created"] == 2
    assert entries["broken.csv"]["reason"] == "invalid_csv"
    assert entries["broken.csv"]["report"] == "broken.dedup.json"
    assert entries["broken.csv"]["records"] is None
    assert entries["a.unique.csv"] == {
        "file": "a.unique.csv", "status": "EXCLUDED", "reason": "derived_csv",
        "verification": None, "report": None, "records": None, "csv_files_created": 0,
    }


def test_a_failing_source_never_stops_the_others_whatever_its_place(folder):
    first = _bad_csv(folder, "0-first.csv")
    last = _bad_csv(folder, "z-last.csv")

    batch = _batch(first, folder / "a.csv", folder / "b.csv", last)

    assert _statuses(batch) == {
        "0-first.csv": "FAILED", "a.csv": "DONE", "b.csv": "DONE", "z-last.csv": "FAILED",
    }
    assert_published(folder, "a", TRIPLES)
    assert_published(folder, "b", PAIRS)
    for failure in batch.failures:
        assert isinstance(failure.error, DedupInputError)
        assert failure.reason == failure.error.reason == "invalid_csv"
        assert load_report(folder, failure.source.stem)["status"] == "failed"
    assert _summary(folder)["status"] == "partial"


def test_a_batch_where_every_source_fails_is_marked_failed(folder):
    _bad_csv(folder, "x.csv")
    _bad_csv(folder, "y.csv")

    batch = _batch(folder / "x.csv", folder / "y.csv")

    assert [item.status for item in batch.results] == ["FAILED", "FAILED"]
    assert _summary(folder)["status"] == "failed"
    _assert_valid_summary(_summary(folder))


def test_a_batch_without_eligible_file_still_writes_its_report(tmp_path):
    write_csv(tmp_path, "x.unique.csv", TRIPLES)
    write_csv(tmp_path, "x.sample.csv", TRIPLES)

    batch = _batch(tmp_path / "*.csv")

    assert batch.results == ()
    assert batch.failures == ()
    assert batch.succeeded
    document = _summary(tmp_path)
    _assert_valid_summary(document)
    assert document["counters"] == {
        "found": 2, "eligible": 0, "excluded": 2, "done": 0, "skipped": 0, "failed": 0,
    }
    assert document["status"] == "complete"
    assert {item["status"] for item in document["sources"]} == {"EXCLUDED"}
    assert batch.batch_report == tmp_path / "dedup.summary.json"


def test_a_pattern_that_matches_no_file_is_an_input_error_and_writes_nothing(tmp_path):
    with pytest.raises(InputError):
        _batch(tmp_path / "*.csv")
    assert list(tmp_path.iterdir()) == []


def test_results_follow_the_order_of_the_plan_and_each_source_is_processed_once(folder):
    batch = _batch(folder / "*.csv", folder / "c*.csv", folder / "a.csv")

    assert [item.source.name for item in batch.results] == ["a.csv", "b.csv", "c.csv"]
    assert [item.source for item in batch.results] == [
        item.source for item in batch.plan.eligible
    ]


@pytest.mark.dedup_t("T24")
def test_two_patterns_that_find_one_source_process_it_once_and_count_it_once(folder):
    events = []

    batch = _batch(
        folder / "*.csv", folder / "a*.csv", on_progress=events.append
    )

    assert [item.source.name for item in batch.results] == ["a.csv", "b.csv", "c.csv"]
    document = _summary(folder)
    assert document["counters"]["eligible"] == 3
    assert len(document["sources"]) == 3
    assert document["inputs"] == ["*.csv", "a*.csv"]
    done = [e for e in events if e.phase is ProgressPhase.COMPLETE and e.source.name == "a.csv"]
    assert len(done) == 1


def test_the_destination_holds_every_output_and_the_batch_report(folder):
    destination = folder / "out"

    batch = _batch(folder / "*.csv", output_dir=destination)

    assert batch.batch_report == destination / "dedup.summary.json"
    assert_published(destination, "a", TRIPLES)
    assert not (folder / "a.unique.csv").exists()
    document = _summary(destination)
    _assert_valid_summary(document)
    assert document["output_dir"] == "."
    assert document["inputs"] == ["../*.csv"]
    entries = {item["file"]: item for item in document["sources"]}
    assert entries["../a.csv"]["report"] == "a.dedup.json"


def test_the_batch_report_goes_to_the_folder_of_the_sources_or_to_the_current_one(
    tmp_path, monkeypatch
):
    one = tmp_path / "one"
    two = tmp_path / "two"
    here = tmp_path / "here"
    for directory in (one, two, here):
        directory.mkdir()
    write_csv(one, "a.csv", TRIPLES)
    write_csv(two, "b.csv", TRIPLES)
    monkeypatch.chdir(here)

    shared = _batch(one / "a.csv", one / "*.csv")
    apart = _batch(one / "a.csv", two / "b.csv")

    assert shared.batch_report == one / "dedup.summary.json"
    assert apart.batch_report == here / "dedup.summary.json"
    document = _summary(here)
    assert {item["file"] for item in document["sources"]} == {
        relative_path(one / "a.csv", here),
        relative_path(two / "b.csv", here),
    }
    assert all("\\" not in item["file"] for item in document["sources"])


# ------------------------------------------------------- the batch report


def test_one_explicit_file_writes_no_batch_report_but_a_pattern_or_two_files_do(folder):
    _batch(folder / "a.csv")
    assert not (folder / "dedup.summary.json").exists()

    tabalyst.dedup_csv(folder / "b.csv")
    assert not (folder / "dedup.summary.json").exists()

    _batch(folder / "c*.csv")
    assert (folder / "dedup.summary.json").exists()
    (folder / "dedup.summary.json").unlink()

    batch = _batch(folder / "a.csv", folder / "b.csv")
    assert batch.batch_report == folder / "dedup.summary.json"


def test_one_explicit_file_has_no_batch_report_path_in_its_result(folder):
    batch = _batch(folder / "a.csv")

    assert batch.batch_report is None
    assert batch.plan.writes_batch_report is False
    assert batch.succeeded


def test_the_counters_never_count_a_source_twice(folder):
    tabalyst.dedup_csv(folder / "a.csv")
    first = _batch(folder / "*.csv")
    document = _summary(folder)

    totals = document["totals"]
    assert totals["reused"] == {
        "sources": 1, "records": 6, "extra_copies": 3, "duplicate_groups": 2,
    }
    assert totals["processed"] == {
        "sources": 2, "records": 5 + 3, "extra_copies": 2, "duplicate_groups": 2,
    }
    assert document["outputs"] == {
        "csv_files_created": 2, "reports_available": 3, "reports_updated": 2,
    }
    assert sum(
        item["csv_files_created"] for item in document["sources"]
    ) == document["outputs"]["csv_files_created"]
    assert first.succeeded


def test_the_files_created_count_only_this_run(folder):
    _batch(folder / "*.csv")
    assert _summary(folder)["outputs"]["csv_files_created"] == 5

    _batch(folder / "*.csv")
    second = _summary(folder)
    assert second["outputs"] == {
        "csv_files_created": 0, "reports_available": 3, "reports_updated": 0,
    }
    assert second["totals"]["processed"]["sources"] == 0
    assert second["totals"]["reused"]["sources"] == 3

    _batch(folder / "*.csv", force=True)
    forced = _summary(folder)
    assert forced["outputs"]["csv_files_created"] == 5
    assert forced["totals"]["reused"]["sources"] == 0


def test_a_failed_source_adds_nothing_to_the_tallies(folder):
    _bad_csv(folder)
    _batch(folder / "a.csv", folder / "broken.csv")

    document = _summary(folder)
    assert document["totals"]["processed"]["sources"] == 1
    assert document["totals"]["reused"]["sources"] == 0
    assert document["outputs"]["reports_available"] == 2
    assert document["outputs"]["reports_updated"] == 2


def test_the_batch_report_holds_no_absolute_path_and_no_cell(folder):
    write_csv(folder, "secret.csv", [("cell-value-xyz", "a"), ("cell-value-xyz", "a")])
    _bad_csv(folder)

    _batch(folder / "*.csv")

    text = (folder / "dedup.summary.json").read_text(encoding="utf-8")
    assert str(folder) not in text
    assert folder.as_posix() not in text
    assert "cell-value-xyz" not in text


def test_the_committed_batch_schema_is_the_generated_one():
    committed = Path(tabalyst.__file__).parent / "schemas" / SCHEMA_FILE
    assert committed.read_text(encoding="utf-8") == batch_schema_text()
    jsonschema.Draft202012Validator.check_schema(batch_schema())


def test_a_batch_report_that_breaks_a_counter_rule_is_refused(folder):
    _batch(folder / "*.csv")
    document = _summary(folder)
    document["counters"]["done"] += 1

    with pytest.raises(ValueError, match="eligible = done"):
        BatchReport.model_validate(document)


def test_a_batch_report_with_an_unknown_member_or_revision_fails_the_schema(folder):
    _batch(folder / "*.csv")
    document = _summary(folder)
    schema = batch_schema()

    jsonschema.validate(document, schema)
    for change in ({"extra": 1}, {"format_revision": 2}, {"format": "tabalyst.dedup"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({**document, **change}, schema)


def test_the_relative_path_falls_back_to_the_name_on_another_drive(monkeypatch):
    def refuse(path, start):
        raise ValueError("path is on mount 'C:', start on mount 'D:'")

    monkeypatch.setattr(os.path, "relpath", refuse)

    assert relative_path(Path("C:/data/in.csv"), Path("D:/out")) == "in.csv"


def test_a_batch_report_that_cannot_be_written_is_a_diagnostic_not_a_lost_result(
    folder, monkeypatch
):
    def refuse(path, report):
        raise OSError("disk full")

    monkeypatch.setattr(dedup_service, "write_batch_report", refuse)

    batch = _batch(folder / "*.csv")

    assert len(batch.results) == 3
    assert batch.batch_report is None
    assert isinstance(batch.batch_report_error, ReportError)
    assert not batch.succeeded
    assert_published(folder, "a", TRIPLES)


# ------------------------------------------------------ the foreign summary


def test_a_foreign_batch_report_name_is_refused_before_any_work(folder):
    (folder / "dedup.summary.json").write_text('{"mine": true}', encoding="utf-8")

    with pytest.raises(ReportError, match="dedup.summary.json"):
        _batch(folder / "*.csv")

    assert not (folder / "a.dedup.json").exists()
    assert (folder / "dedup.summary.json").read_text(encoding="utf-8") == '{"mine": true}'


def test_force_replaces_a_foreign_batch_report_and_a_dedup_one_is_always_replaced(folder):
    summary = folder / "dedup.summary.json"
    summary.write_text("not json at all", encoding="utf-8")

    _batch(folder / "*.csv", force=True)
    _assert_valid_summary(_summary(folder))

    summary.write_text(
        json.dumps({"format": "tabalyst.dedup.batch", "format_revision": 99}),
        encoding="utf-8",
    )
    assert is_batch_report(summary)
    _batch(folder / "*.csv")
    _assert_valid_summary(_summary(folder))


def test_a_batch_report_name_that_is_a_directory_or_a_source_is_refused_even_with_force(
    folder
):
    (folder / "dedup.summary.json").mkdir()
    with pytest.raises(InputError, match="directory"):
        _batch(folder / "*.csv", force=True)
    (folder / "dedup.summary.json").rmdir()

    (folder / "dedup.summary.json").write_text("x\n1\n", encoding="utf-8")
    with pytest.raises(InputError, match="overwrite an input"):
        _batch(folder / "a.csv", folder / "dedup.summary.json", force=True)


# ----------------------------------------------- refusals before any work


def test_a_foreign_output_of_a_later_source_refuses_the_whole_batch_before_any_work(folder):
    (folder / "c.unique.csv").write_text("mine\n", encoding="utf-8")

    with pytest.raises(ReportError):
        _batch(folder / "a.csv", folder / "b.csv", folder / "c.csv")

    assert not (folder / "a.dedup.json").exists()
    assert not (folder / "a.unique.csv").exists()
    assert not (folder / "dedup.summary.json").exists()
    assert no_temporary_files(folder)


def test_two_sources_with_one_stem_in_one_folder_are_a_collision(folder):
    write_csv(folder, "a.tsv", TRIPLES, delimiter="\t")

    with pytest.raises(ReportError, match="collision"):
        _batch(folder / "a.csv", folder / "a.tsv")

    assert not (folder / "a.dedup.json").exists()


def test_an_output_that_would_replace_a_source_is_refused_even_with_force(folder):
    write_csv(folder, "a.duplicates.csv", TRIPLES)

    with pytest.raises(InputError, match="overwrite an input"):
        _batch(folder / "a.csv", folder / "a.duplicates.csv", force=True)


def test_invalid_options_raise_before_any_work(folder):
    with pytest.raises(ConfigurationError):
        _batch(folder / "*.csv", max_rows=0)
    with pytest.raises(ConfigurationError):
        _batch(folder / "*.csv", force=True, verify_content=True)
    with pytest.raises(ConfigurationError):
        _batch(folder / "**" / "*.csv")
    with pytest.raises(ConfigurationError):
        tabalyst.generate_dedups([])
    assert not (folder / "a.dedup.json").exists()


def test_verify_content_checks_the_outputs_at_the_plan_not_at_the_run(folder):
    tabalyst.dedup_csv(folder / "a.csv")
    unique = folder / "a.unique.csv"
    data = bytearray(unique.read_bytes())
    data[-1] ^= 0x01  # same size: only the content tells
    unique.write_bytes(bytes(data))

    # metadata level: the size matches, so the plan owns the file
    dedup_service.build_dedup_plan([str(folder / "a.csv")], settings())
    with pytest.raises(ReportError):
        _batch(folder / "b.csv", folder / "a.csv", verify_content=True)

    assert not (folder / "b.dedup.json").exists()
    assert no_temporary_files(folder)


def test_a_source_refused_at_run_time_fails_alone_and_the_batch_goes_on(folder, monkeypatch):
    real = dedup_service.process_source

    def flaky(source, settings, **options):
        if Path(source).name == "a.csv":
            raise ReportError("Dedup output already exists")
        return real(source, settings, **options)

    monkeypatch.setattr(dedup_service, "process_source", flaky)

    batch = _batch(folder / "*.csv")

    assert _statuses(batch) == {"a.csv": "FAILED", "b.csv": "DONE", "c.csv": "DONE"}
    refused = batch.failures[0]
    assert refused.reason == "output_refused"
    assert isinstance(refused.error, ReportError)
    assert refused.report_path is None
    document = _summary(folder)
    _assert_valid_summary(document)
    assert document["diagnostics"] == [
        (
            "a.csv: an output was refused just before the run (it changed after "
            "the plan); nothing was written."
        )
    ]
    assert str(folder) not in json.dumps(document)


def test_an_unexpected_exception_fails_one_source_with_a_fixed_message(folder, monkeypatch):
    real = dedup_service.process_source

    def broken(source, settings, **options):
        if Path(source).name == "b.csv":
            raise RuntimeError("cell-value-xyz")
        return real(source, settings, **options)

    monkeypatch.setattr(dedup_service, "process_source", broken)

    batch = _batch(folder / "*.csv")

    assert _statuses(batch) == {"a.csv": "DONE", "b.csv": "FAILED", "c.csv": "DONE"}
    failure = batch.failures[0]
    assert failure.reason == "unexpected_error"
    assert "cell-value-xyz" not in str(failure.error)
    assert isinstance(failure.error.__cause__, RuntimeError)


def test_an_interruption_is_not_swallowed_by_the_batch(folder, monkeypatch):
    def interrupted(source, settings, **options):
        raise KeyboardInterrupt

    monkeypatch.setattr(dedup_service, "process_source", interrupted)

    with pytest.raises(KeyboardInterrupt):
        _batch(folder / "*.csv")


# ------------------------------------------------------- the Python API


def test_dedup_csv_processes_one_file_and_skips_it_the_second_time(folder):
    first = tabalyst.dedup_csv(folder / "a.csv")

    assert first.status == "DONE"
    assert first.reason is None
    assert {path.name for path in first.files} == {
        "a.unique.csv", "a.duplicates.csv", "a.duplicates_all.csv",
    }
    assert first.report.status == "complete"
    assert first.report_path == folder / "a.dedup.json"
    assert first.verification is None
    assert_published(folder, "a", TRIPLES)

    second = tabalyst.dedup_csv(folder / "a.csv")

    assert second.status == "SKIPPED"
    assert second.reason == "already_processed"
    assert second.files == ()
    assert second.verification == "metadata"
    assert second.report == first.report
    assert not (folder / "dedup.summary.json").exists()


def test_dedup_csv_raises_the_error_of_a_failed_source_after_writing_its_report(folder):
    broken = _bad_csv(folder)

    with pytest.raises(DedupInputError) as caught:
        tabalyst.dedup_csv(broken)

    assert caught.value.reason == "invalid_csv"
    assert load_report(folder, "broken")["status"] == "failed"


def test_dedup_csv_refuses_before_any_work_what_the_plan_refuses(folder):
    (folder / "a.unique.csv").write_text("mine\n", encoding="utf-8")

    with pytest.raises(ReportError):
        tabalyst.dedup_csv(folder / "a.csv")
    with pytest.raises(InputError):
        tabalyst.dedup_csv(folder / "missing.csv")
    with pytest.raises(InputError):
        tabalyst.dedup_csv(folder)
    with pytest.raises(ConfigurationError):
        tabalyst.dedup_csv(folder / "b.csv", memory_budget_mb=0)

    assert not (folder / "a.dedup.json").exists()
    assert not (folder / "b.dedup.json").exists()
    assert tabalyst.dedup_csv(folder / "a.csv", force=True).status == "DONE"


def test_dedup_csv_takes_a_path_with_brackets_and_a_derived_name_as_files(tmp_path):
    bracketed = write_csv(tmp_path, "data[1].csv", TRIPLES)
    derived = write_csv(tmp_path, "x.unique.csv", TRIPLES)

    assert tabalyst.dedup_csv(bracketed).status == "DONE"
    assert tabalyst.dedup_csv(derived).status == "DONE"
    assert (tmp_path / "data[1].dedup.json").exists()
    assert (tmp_path / "x.unique.dedup.json").exists()


def test_dedup_csv_options_reach_the_engine(folder):
    semicolons = write_csv(folder, "s.csv", TRIPLES, delimiter=";")
    out = folder / "out"

    result = tabalyst.dedup_csv(semicolons, delimiter=";", output_dir=out, max_rows=10)

    assert result.report_path == out / "s.dedup.json"
    document = load_report(out, "s")
    assert document["settings"]["delimiter"] == ";"
    assert document["settings"]["max_rows"] == 10
    with pytest.raises(DedupInputError) as caught:
        tabalyst.dedup_csv(folder / "a.csv", max_rows=2)
    assert caught.value.reason == "row_limit_exceeded"


def test_dedup_csv_verify_content_reads_the_source(folder):
    tabalyst.dedup_csv(folder / "a.csv")

    result = tabalyst.dedup_csv(folder / "a.csv", verify_content=True)

    assert result.status == "SKIPPED"
    assert result.verification == "digest"


def test_the_config_file_sets_the_options_of_the_api(folder):
    config = folder / "config.json"
    config.write_text(json.dumps({"dedup": {"max_rows": 3}}), encoding="utf-8")

    with pytest.raises(DedupInputError):
        tabalyst.dedup_csv(folder / "a.csv", config_path=config)
    assert tabalyst.dedup_csv(folder / "a.csv", config_path=config, max_rows=10).status == "DONE"


def test_the_api_never_asks_a_question(folder, monkeypatch):
    import builtins
    import sys

    import typer

    def asked(*args, **kwargs):
        raise AssertionError("the API asked a question")

    monkeypatch.setattr(builtins, "input", asked)
    monkeypatch.setattr(typer, "confirm", asked)
    monkeypatch.setattr(typer, "prompt", asked)
    monkeypatch.setattr(sys, "stdin", None)
    _bad_csv(folder)

    tabalyst.dedup_csv(folder / "a.csv")
    tabalyst.dedup_csv(folder / "a.csv")
    tabalyst.dedup_csv(folder / "a.csv", force=True)
    batch = _batch(folder / "*.csv", verify_content=False)
    assert [item.status for item in batch.failures] == ["FAILED"]
    with pytest.raises(ReportError):
        (folder / "b.unique.csv").write_text("mine\n", encoding="utf-8")
        _batch(folder / "b.csv")


def test_the_batch_result_has_the_shape_of_the_sample_batch(folder):
    samples = tabalyst.generate_samples(
        [str(folder / "a.csv"), str(folder / "b.csv")],
        method="random",
        rows=2,
        seed=1,
        output_dir=folder / "samples",
    )
    dedups = _batch(folder / "a.csv", folder / "b.csv")

    for batch in (samples, dedups):
        assert batch.succeeded
        assert batch.failures == ()
    assert len(samples.plan.jobs) == len(dedups.plan.eligible) == 2
    assert [item.job.source for item in samples.successes] == [
        item.source for item in dedups.results
    ]
    single_sample = tabalyst.sample_csv(
        folder / "c.csv", method="random", rows=1, seed=1, output=folder / "c.s.csv"
    )
    single_dedup = tabalyst.dedup_csv(folder / "c.csv")
    assert single_sample.source == single_dedup.source
    assert single_sample.source_rows == single_dedup.report.records.total


def test_a_failure_is_raised_by_the_single_functions_and_collected_by_the_batches(folder):
    broken = _bad_csv(folder)

    with pytest.raises(InputError):
        tabalyst.sample_csv(broken, method="random", rows=1, seed=1, output=folder / "s.csv")
    with pytest.raises(InputError):
        tabalyst.dedup_csv(broken)
    batch = _batch(broken, folder / "a.csv")

    assert len(batch.failures) == 1
    assert isinstance(batch.failures[0].error, InputError)


# ------------------------------------------------------------- progress


def test_every_event_of_a_batch_carries_the_position_of_its_source(folder):
    tabalyst.dedup_csv(folder / "a.csv")
    os.utime(folder / "a.csv", ns=(1, 1))  # touched: the decision reads the file
    _bad_csv(folder)
    events = []

    _batch(folder / "a.csv", folder / "b.csv", folder / "broken.csv", on_progress=events.append)

    assert events
    assert {event.total for event in events} == {3}
    assert {event.stage for event in events} == {"Dedup"}
    by_source = {}
    for event in events:
        by_source.setdefault(event.source.name, []).append(event)
    assert {name: {e.index for e in items} for name, items in by_source.items()} == {
        "a.csv": {1}, "b.csv": {2}, "broken.csv": {3},
    }
    assert [e.phase for e in by_source["a.csv"]][-1] is ProgressPhase.COMPLETE
    assert by_source["a.csv"][-1].detail == "already processed, verified by digest"
    verifying = [e for e in by_source["a.csv"] if e.detail == "verifying the content of the source"]
    assert verifying and all(e.index == 1 and e.total == 3 for e in verifying)
    assert by_source["b.csv"][-1].phase is ProgressPhase.COMPLETE
    assert by_source["b.csv"][-1].detail == "processed"
    assert by_source["b.csv"][-1].duration_seconds is not None
    assert by_source["broken.csv"][-1].phase is ProgressPhase.FAILED
    assert by_source["broken.csv"][-1].detail == "invalid_csv"


def test_the_events_of_the_passes_carry_the_position_and_never_a_cell(tmp_path):
    padding = "p" * 150
    rows = [(f"identifier-{n:06d}", f"cell-value-{n}-{padding}") for n in range(9000)]
    rows += rows[:3]
    big = write_csv(tmp_path, "big.csv", rows)
    other = write_csv(tmp_path, "other.csv", TRIPLES)
    events = []

    _batch(other, big, on_progress=events.append, memory_budget_mb=1)

    spill = [e for e in events if e.detail and "continuing on disk" in e.detail]
    assert len(spill) == 1
    assert (spill[0].index, spill[0].total, spill[0].stage) == (2, 2, "Dedup")
    for event in events:
        assert "cell-value" not in repr(event) and "identifier-" not in repr(event)
        assert (event.index, event.total) in {(1, 2), (2, 2)}
    assert any(e.phase is ProgressPhase.WRITING and e.index == 2 for e in events)


def test_dedup_csv_events_are_the_first_of_one(folder):
    events = []

    tabalyst.dedup_csv(folder / "a.csv", on_progress=events.append)
    tabalyst.dedup_csv(folder / "a.csv", on_progress=events.append)

    assert {(e.index, e.total) for e in events} == {(1, 1)}
    assert [e.detail for e in events if e.phase is ProgressPhase.COMPLETE] == [
        "processed", "already processed, verified by metadata",
    ]


def test_no_event_is_emitted_for_an_excluded_file(tmp_path):
    write_csv(tmp_path, "x.unique.csv", TRIPLES)
    write_csv(tmp_path, "y.csv", TRIPLES)
    events = []

    _batch(tmp_path / "*.csv", on_progress=events.append)

    assert {e.source.name for e in events} == {"y.csv"}
    assert {e.total for e in events} == {1}


def test_the_ownership_test_reads_the_report_of_a_source_once(folder, monkeypatch):
    from tabalyst.dedup import cache
    from tabalyst.dedup.discovery import plan_batch

    tabalyst.dedup_csv(folder / "a.csv")
    calls = []
    real = cache.assess

    def counting(names, **options):
        calls.append(names["report"].name)
        return real(names, **options)

    monkeypatch.setattr(cache, "assess", counting)

    plan_batch(
        [str(folder / "a.csv"), str(folder / "b.csv")],
        settings(),
        is_owned=cache.ownership_test(),
    )

    assert calls == ["a.dedup.json"]
