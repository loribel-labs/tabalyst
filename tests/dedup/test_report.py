# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The JSON report of a source: models, invariants, schema, reading and publication (design 12)."""

import copy
import hashlib
import json
from pathlib import Path

import jsonschema
import pytest
from dedup_helpers import (
    load_report,
    no_temporary_files,
    run,
    validate_report,
    write_csv,
)

import tabalyst
from tabalyst.dedup import report as report_module
from tabalyst.dedup.report import (
    SCHEMA_FILE,
    CompleteReport,
    DedupDocumentError,
    FailedReport,
    dedup_schema,
    dedup_schema_text,
    parse_report,
    read_report,
    report_json,
)

pytestmark = pytest.mark.dedup_lot("6")

PAIRS = [("1", "a"), ("2", "b"), ("1", "a"), ("3", "c"), ("2", "b")]
TRIPLES = [("1", "a")] * 3 + [("2", "b")] * 2 + [("3", "c")]
CASES = {
    "header_only": [],
    "no_duplicate": [("1", "a"), ("2", "b")],
    "pairs_only": PAIRS,
    "with_triples": TRIPLES,
}


def _document(tmp_path, rows, name="data", **options):
    source = write_csv(tmp_path, f"{name}.csv", rows)
    outcome = run(source, **options)
    return source, outcome, load_report(tmp_path, name)


# ------------------------------------------------------------------ schema


def test_the_committed_schema_is_the_generated_one():
    committed = Path(tabalyst.__file__).parent / "schemas" / SCHEMA_FILE
    assert committed.read_text(encoding="utf-8") == dedup_schema_text()


def test_the_schema_is_a_valid_json_schema_with_two_variants():
    schema = dedup_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert len(schema["oneOf"]) == 2
    for name in ("CompleteReport", "FailedReport"):
        required = schema["$defs"][name]["required"]
        assert {"format", "format_version", "format_revision", "status"} <= set(required)


# ---------------------------------------------------------------- variants


@pytest.mark.parametrize("case", CASES)
def test_a_report_of_each_variant_satisfies_the_schema_and_the_models(tmp_path, case):
    source, outcome, document = _document(tmp_path, CASES[case])

    validate_report(document)
    parsed = read_report(tmp_path / "data.dedup.json")

    assert isinstance(parsed, CompleteReport)
    assert outcome.report == parsed
    assert outcome.report_path == tmp_path / "data.dedup.json"
    assert json.loads(report_json(parsed)) == document
    assert document["source"]["name"] == source.name


def test_a_source_without_duplicate_announces_no_csv_and_a_single_pass(tmp_path):
    _, _, document = _document(tmp_path, CASES["no_duplicate"])

    assert document["outputs"] == {
        "csv_files_created": 0,
        "unique": None,
        "duplicates": None,
        "duplicates_all": None,
    }
    assert document["run"]["passes"] == 1
    assert document["run"]["second_pass_seconds"] is None


def test_groups_of_two_only_write_two_files_and_no_duplicates_all(tmp_path):
    _, _, document = _document(tmp_path, CASES["pairs_only"])

    outputs = document["outputs"]
    assert outputs["csv_files_created"] == 2
    assert outputs["duplicates_all"] is None
    assert document["records"]["groups_occurring_three_plus"] == 0
    assert document["run"]["passes"] == 2
    assert document["run"]["second_pass_seconds"] is not None


def test_a_header_only_file_has_zero_counts_and_a_zero_percent(tmp_path):
    _, _, document = _document(tmp_path, CASES["header_only"])

    records = document["records"]
    assert records["total"] == records["max_occurrences"] == 0
    assert records["extra_copy_percent"] == 0
    assert document["outputs"]["csv_files_created"] == 0


def test_the_extra_copy_percent_is_a_hundred_times_the_extra_copies_over_the_total(tmp_path):
    _, _, document = _document(tmp_path, CASES["with_triples"])

    assert document["records"]["extra_copies"] == 3
    assert document["records"]["extra_copy_percent"] == pytest.approx(50.0)


def test_the_inventory_matches_the_published_files(tmp_path):
    _, _, document = _document(tmp_path, CASES["with_triples"])

    for kind in ("unique", "duplicates", "duplicates_all"):
        entry = document["outputs"][kind]
        data = (tmp_path / entry["file"]).read_bytes()
        assert entry["size_bytes"] == len(data)
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["rows"] == len(data.decode().splitlines()) - 1
    assert document["source"]["content_sha256"] == hashlib.sha256(
        (tmp_path / "data.csv").read_bytes()
    ).hexdigest()


def test_a_measure_that_was_not_taken_is_null_and_verbose_takes_the_memory_peak(tmp_path):
    _, _, quiet = _document(tmp_path, PAIRS, name="quiet")
    _, _, verbose = _document(tmp_path, PAIRS, name="verbose", verbose=True)

    assert quiet["run"]["memory_peak_bytes"] is None
    assert verbose["run"]["memory_peak_bytes"] > 0
    assert quiet["run"]["storage_mode"] == "memory"


def test_the_report_holds_the_settings_that_decided_the_result(tmp_path):
    from tabalyst.config import CsvConfig

    source = write_csv(tmp_path, "semi.csv", PAIRS, delimiter=";")
    run(source, csv=CsvConfig(delimiter=";"), max_rows=500)

    document = load_report(tmp_path, "semi")

    assert document["settings"] == {
        "max_rows": 500,
        "delimiter": ";",
        "encoding": "utf-8-sig",
        "identity": "full_decoded_csv_row_v1",
    }
    assert document["generator"] == {"name": "tabalyst", "version": tabalyst.__version__}


# --------------------------------------------------------------- invariants

BREAKS = {
    "total": lambda d: d["records"].update(total=d["records"]["total"] + 1),
    "distinct": lambda d: d["records"].update(singletons=d["records"]["singletons"] + 1),
    "occurrences": lambda d: d["records"].update(duplicate_group_occurrences=99),
    "groups": lambda d: d["records"].update(groups_occurring_twice=5),
    "max_zero_with_records": lambda d: d["records"].update(max_occurrences=0),
    "three_plus_without_max": lambda d: d["records"].update(max_occurrences=2),
    "percent": lambda d: d["records"].update(extra_copy_percent=12.5),
    "unique_rows": lambda d: d["outputs"]["unique"].update(rows=1),
    "duplicates_rows": lambda d: d["outputs"]["duplicates"].update(rows=99),
    "duplicates_all_rows": lambda d: d["outputs"]["duplicates_all"].update(rows=1),
    "files_created": lambda d: d["outputs"].update(csv_files_created=2),
    "missing_output": lambda d: d["outputs"].update(duplicates_all=None, csv_files_created=2),
    "passes": lambda d: d["run"].update(passes=1, second_pass_seconds=None),
    "second_pass_missing": lambda d: d["run"].update(second_pass_seconds=None),
}


@pytest.mark.parametrize("name", BREAKS)
def test_a_document_that_breaks_an_invariant_is_not_a_report(tmp_path, name):
    _, _, document = _document(tmp_path, CASES["with_triples"])
    broken = copy.deepcopy(document)
    BREAKS[name](broken)

    with pytest.raises(DedupDocumentError):
        parse_report(broken)


def test_an_output_that_the_maximum_frequency_does_not_call_for_is_refused(tmp_path):
    _, _, document = _document(tmp_path, CASES["pairs_only"])
    forged = copy.deepcopy(document)
    forged["outputs"]["duplicates_all"] = copy.deepcopy(forged["outputs"]["duplicates"])
    forged["outputs"]["csv_files_created"] = 3

    with pytest.raises(DedupDocumentError, match="duplicates_all"):
        parse_report(forged)


# ----------------------------------------------------------------- reading


def test_the_reading_api_refuses_what_is_not_a_report(tmp_path):
    _, _, document = _document(tmp_path, PAIRS)
    path = tmp_path / "data.dedup.json"
    cases = {
        "truncated": path.read_text(encoding="utf-8")[:40],
        "not json": "not json at all",
        "other format": json.dumps({**document, "format": "tabalyst.scan"}),
        "other revision": json.dumps({**document, "format_revision": 2}),
        "unknown status": json.dumps({**document, "status": "in_progress"}),
        "extra member": json.dumps({**document, "cells": ["secret"]}),
        "not an object": "[]",
    }
    for label, text in cases.items():
        path.write_text(text, encoding="utf-8")
        with pytest.raises(DedupDocumentError):
            read_report(path)
        assert label


def test_a_missing_or_undecodable_report_is_refused(tmp_path):
    with pytest.raises(DedupDocumentError):
        read_report(tmp_path / "absent.dedup.json")
    bad = tmp_path / "bad.dedup.json"
    bad.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(DedupDocumentError):
        read_report(bad)


def test_the_message_of_a_refusal_never_echoes_a_value_of_the_file(tmp_path):
    _, _, document = _document(tmp_path, PAIRS)
    forged = {**document, "source": {**document["source"], "name": 12345678}}

    with pytest.raises(DedupDocumentError) as caught:
        parse_report(forged)

    assert "12345678" not in str(caught.value)


def test_a_forged_hash_that_is_not_a_digest_is_refused_by_the_schema_and_the_models(tmp_path):
    _, _, document = _document(tmp_path, PAIRS)
    forged = copy.deepcopy(document)
    forged["outputs"]["unique"]["sha256"] = "ece53017..."

    with pytest.raises(DedupDocumentError):
        parse_report(forged)
    with pytest.raises(jsonschema.ValidationError):
        validate_report(forged)


# ---------------------------------------------------------- confidentiality


def test_no_report_holds_a_cell_or_an_absolute_path(tmp_path):
    rows = [("secret-4711", "person@example.org")] * 3
    source = write_csv(tmp_path, "private.csv", rows, header=["token", "mail"])
    broken = write_csv(tmp_path, "broken.csv", [("secret-4711", "x", "extra")], header=["token", "mail"])

    run(source)
    run(broken)

    for name in ("private", "broken"):
        text = (tmp_path / f"{name}.dedup.json").read_text(encoding="utf-8")
        assert "secret-4711" not in text
        assert "person@example.org" not in text
        assert str(tmp_path) not in text
        assert tmp_path.name not in text


# ------------------------------------------------------------------ failure


def test_a_failed_report_has_no_count_no_output_and_announces_no_csv(tmp_path):
    source = write_csv(tmp_path, "limit.csv", PAIRS)

    outcome = run(source, max_rows=3)
    document = load_report(tmp_path, "limit")

    validate_report(document)
    assert isinstance(parse_report(document), FailedReport)
    assert outcome.report == parse_report(document)
    assert document["status"] == "failed"
    assert "records" not in document and "outputs" not in document
    assert document["failure"]["reason"] == "row_limit_exceeded"
    assert document["failure"]["limit"] == 3
    assert document["partial"] == {"records_read": 4, "certified": False}
    assert document["source"]["size_bytes"] == source.stat().st_size
    assert document["source"]["mtime_ns"] == source.stat().st_mtime_ns


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"", "invalid_csv"),
        (b"id,name\r\n1,a\r\n2\r\n", "invalid_csv"),
        (b"id,name\r\n1,\xe9\r\n", "encoding_error"),
    ],
)
def test_each_input_failure_gives_a_failed_report_with_its_stable_reason(
    tmp_path, content, reason
):
    source = tmp_path / "bad.csv"
    source.write_bytes(content)

    outcome = run(source)
    document = load_report(tmp_path, "bad")

    validate_report(document)
    assert outcome.reason == reason == document["failure"]["reason"]
    assert "limit" not in document["failure"]


def test_a_source_that_vanished_gets_a_failed_report_without_size_or_time(tmp_path):
    outcome = run(tmp_path / "gone.csv")
    document = load_report(tmp_path, "gone")

    validate_report(document)
    assert outcome.reason == "source_unreadable"
    assert document["source"] == {"name": "gone.csv"}
    assert document["partial"] == {"records_read": None, "certified": False}


def test_a_failed_run_leaves_a_failed_report_beside_no_csv(tmp_path):
    source = write_csv(tmp_path, "limit.csv", PAIRS)

    run(source, max_rows=3)

    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".csv"] == ["limit.csv"]
    assert no_temporary_files(tmp_path)


def test_a_failure_to_write_the_failed_report_keeps_the_primary_failure(tmp_path, monkeypatch):
    source = write_csv(tmp_path, "limit.csv", PAIRS)

    def refuse(path, report):
        raise PermissionError("denied")

    monkeypatch.setattr("tabalyst.dedup.pipeline.write_report", refuse)

    outcome = run(source, max_rows=3)

    assert outcome.status == "FAILED"
    assert outcome.reason == "row_limit_exceeded"
    assert outcome.report is None and outcome.report_path is None
    assert not (tmp_path / "limit.dedup.json").exists()


# -------------------------------------------------------------- publication


def test_the_report_is_published_last_after_the_csv(tmp_path, monkeypatch):
    source = write_csv(tmp_path, "order.csv", PAIRS)
    seen: list[set[str]] = []
    real = report_module.write_text_atomic

    def spy(path, content):
        seen.append({p.name for p in tmp_path.iterdir() if not p.name.startswith(".")})
        real(path, content)

    monkeypatch.setattr(report_module, "write_text_atomic", spy)

    run(source)

    assert seen == [{"order.csv", "order.unique.csv", "order.duplicates.csv"}]
    assert (tmp_path / "order.dedup.json").exists()


def test_a_report_that_cannot_be_written_leaves_no_unowned_csv(tmp_path, monkeypatch):
    source = write_csv(tmp_path, "unowned.csv", PAIRS)
    calls = []

    def refuse(path, report):
        calls.append(path.name)
        if len(calls) == 1:
            raise PermissionError("denied")

    monkeypatch.setattr("tabalyst.dedup.pipeline.write_report", refuse)

    outcome = run(source)

    assert outcome.status == "FAILED"
    assert outcome.reason == "output_unwritable"
    assert not list(tmp_path.glob("unowned.*.csv"))
    assert no_temporary_files(tmp_path)


def test_a_rerun_replaces_the_report_atomically(tmp_path):
    source = write_csv(tmp_path, "twice.csv", PAIRS)
    run(source)
    first = (tmp_path / "twice.dedup.json").read_text(encoding="utf-8")
    write_csv(tmp_path, "twice.csv", TRIPLES)

    run(source)

    second = load_report(tmp_path, "twice")
    assert json.loads(first)["records"]["total"] == 5
    assert second["records"]["total"] == 6
    assert no_temporary_files(tmp_path)
