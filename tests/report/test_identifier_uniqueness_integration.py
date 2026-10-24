# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Report wiring of the identifier uniqueness: the ``--dedup-report`` option and the facts."""

import json

import pytest
from identifier_uniqueness_helpers import (
    population,
    report_document,
    uniqueness_of,
    write_csv,
)
from typer.testing import CliRunner

from tabalyst import generate_reports
from tabalyst.cli import app
from tabalyst.dedup_service import dedup_csv
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.identifier_uniqueness.facts import facts_from_scan
from tabalyst.scanner import scan
from tabalyst.scanner.config import ScanConfig

pytestmark = pytest.mark.uid_lot("3")

LIMITED = ScanConfig.model_validate({"limits": {"max_tracked_records": 500}})


def _with_limited_duplicates(tmp_path, name="d.csv"):
    source = write_csv(tmp_path, name, population(distinct_ids=2000, copies=600))
    return source


def test_a_non_identifier_column_has_no_facts_and_no_object(tmp_path):
    source = write_csv(tmp_path, "n.csv", population(distinct_ids=50, copies=2))
    result = scan(source)
    status = next(f.id for f in result.datasets[0].fields if f.name == "status")

    assert facts_from_scan(result, result.datasets[0].id, status) is None
    assert uniqueness_of(report_document(source), "status") is None


def test_the_dedup_report_option_names_a_file(tmp_path):
    source = _with_limited_duplicates(tmp_path)
    outcome = dedup_csv(source, output_dir=tmp_path / "dd")

    report = generate_reports(
        [source],
        output_dir=tmp_path / "out",
        dedup_report=outcome.report_path,
        config_path=_config(tmp_path),
    )
    document = json.loads((tmp_path / "out" / "d.json").read_text(encoding="utf-8"))
    item = uniqueness_of(document, "customer_id")

    assert report.succeeded
    assert item["evidence"]["duplicate_rows"]["report"]["origin"] == "explicit"
    assert item["evidence"]["duplicate_rows"]["report"]["name"] == "d.dedup.json"
    assert item["explanation"]["id_repetitions_residual"] == 0


def test_the_dedup_report_config_key_is_the_same_option(tmp_path):
    source = _with_limited_duplicates(tmp_path)
    outcome = dedup_csv(source, output_dir=tmp_path / "dd")
    config = _config(tmp_path, dedup_report=str(outcome.report_path.parent))

    generate_reports([source], output_dir=tmp_path / "out", config_path=config)
    document = json.loads((tmp_path / "out" / "d.json").read_text(encoding="utf-8"))

    item = uniqueness_of(document, "customer_id")
    assert item["evidence"]["duplicate_rows"]["source"] == "dedup.report"
    # The path of the report is not part of the stored settings.
    assert document["report"]["config"]["dedup_report"] is None


def test_a_missing_dedup_report_is_an_error_of_the_option(tmp_path):
    source = _with_limited_duplicates(tmp_path)

    batch = generate_reports(
        [source], output_dir=tmp_path / "out", dedup_report=tmp_path / "absent.dedup.json"
    )

    assert not batch.succeeded
    assert isinstance(batch.failures[0].error, InputError)
    assert "--dedup-report" in str(batch.failures[0].error)


def test_a_dedup_report_is_refused_for_a_source_that_is_not_a_csv(tmp_path):
    source = tmp_path / "d.json"
    source.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
    proof = tmp_path / "x.dedup.json"
    proof.write_text("{}", encoding="utf-8")

    batch = generate_reports([source], output_dir=tmp_path / "out", dedup_report=proof)

    assert not batch.succeeded
    assert "not" in str(batch.failures[0].error) and "CSV" in str(batch.failures[0].error)


def test_one_dedup_report_file_cannot_serve_several_sources(tmp_path):
    first = write_csv(tmp_path, "a.csv", population(distinct_ids=20))
    second = write_csv(tmp_path, "b.csv", population(distinct_ids=20))
    proof = tmp_path / "a.dedup.json"
    dedup_csv(first, output_dir=tmp_path)

    with pytest.raises(ConfigurationError, match="folder"):
        generate_reports([first, second], output_dir=tmp_path / "out", dedup_report=proof)


def test_a_dedup_report_option_is_refused_for_a_report_from_a_json_scan(tmp_path):
    source = tmp_path / "d.json"
    source.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
    from tabalyst import generate_scans

    generate_scans([source], output_dir=tmp_path / "scans")
    document = next((tmp_path / "scans").glob("*.scan.json"))

    batch = generate_reports(
        [document], output_dir=tmp_path / "out", from_scan=True, dedup_report=tmp_path
    )

    assert not batch.succeeded


def test_a_report_from_a_scan_finds_the_dedup_report_beside_the_scan_document(tmp_path):
    from tabalyst import generate_scans

    source = _with_limited_duplicates(tmp_path)
    scans = tmp_path / "scans"
    generate_scans([source], output_dir=scans, config_path=_config(tmp_path))
    dedup_csv(source, output_dir=scans)
    document = next(scans.glob("*.scan.json"))

    generate_reports([document], output_dir=tmp_path / "out", from_scan=True)
    report = json.loads((tmp_path / "out" / "d.json").read_text(encoding="utf-8"))

    item = uniqueness_of(report, "customer_id")
    assert item["evidence"]["duplicate_rows"]["report"]["origin"] == "colocated"


def test_the_cli_option_reaches_the_report(tmp_path):
    source = _with_limited_duplicates(tmp_path)
    outcome = dedup_csv(source, output_dir=tmp_path / "dd")

    result = CliRunner().invoke(
        app,
        [
            "report",
            str(source),
            "-d",
            str(tmp_path / "out"),
            "-c",
            str(_config(tmp_path)),
            "--dedup-report",
            str(outcome.report_path),
            "--no-progress",
        ],
    )
    document = json.loads((tmp_path / "out" / "d.json").read_text(encoding="utf-8"))

    assert result.exit_code == 0, result.output
    assert uniqueness_of(document, "customer_id")["evidence"]["duplicate_rows"]["source"] == "dedup.report"


def test_the_cli_reports_an_unusable_option_with_an_error_exit(tmp_path):
    source = _with_limited_duplicates(tmp_path)

    result = CliRunner().invoke(
        app,
        ["report", str(source), "-d", str(tmp_path / "out"), "--dedup-report", str(tmp_path / "no")],
    )

    assert result.exit_code != 0


def _config(tmp_path, **report):
    path = tmp_path / "config.json"
    document = {"scan": LIMITED.model_dump(by_alias=True, mode="json", exclude_defaults=True)}
    if report:
        document["report"] = report
    path.write_text(json.dumps(document), encoding="utf-8")
    return path
