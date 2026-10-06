# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: a report built from a scan document (lot 5c, O12).

``tabalyst report --scan data.scan.json`` builds the report from the document
alone, never reading the source again, unless the source beside it changed
or the configuration asks for other scan settings (design 16.6).
"""

import json
import os
from pathlib import Path

import pytest
from scan_helpers import write_text
from typer.testing import CliRunner

from tabalyst import generate_reports
from tabalyst.cli import app
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.scanner.readers import csv_reader
from tabalyst.service import analyze_scan

pytestmark = pytest.mark.lot("5c")

runner = CliRunner()
ROWS = "id,email,city\n1,ann@example.com,Paris\n2,bob@example.com,\n1,ann@example.com,Paris\n"


@pytest.fixture(autouse=True)
def _isolated_project_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage"))


def _scan(path, *options):
    target = path.with_name(f"{path.stem}.scan.json")
    result = runner.invoke(
        app, ["scan", str(path), "--force", "-o", str(target), *options]
    )
    assert result.exit_code == 0, result.output
    return target


def _report(*arguments):
    return runner.invoke(app, ["report", *map(str, arguments)])


def _comparable(profile: dict) -> dict:
    return {
        key: value
        for key, value in profile.items()
        if key not in {"generated_at", "processing_seconds"}
    }


def _config(tmp_path, name, document):
    return write_text(tmp_path, name, json.dumps(document))


def test_report_from_a_scan_equals_the_direct_report(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    config = _config(
        tmp_path,
        "config.json",
        {"value_examples": {"inline_display_size": 2}, "scan": {"records": {"preview": 2}}},
    )
    scan_document = _scan(source, "--config", config)
    direct = tmp_path / "direct" / "data.html"

    assert _report(source, "--config", config, "-o", direct).exit_code == 0
    result = _report("--scan", scan_document, "--config", config)

    assert result.exit_code == 0, result.output
    reused = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))
    expected = json.loads(direct.with_suffix(".json").read_text(encoding="utf-8"))
    assert _comparable(reused) == _comparable(expected)
    assert reused["datasets"][0]["summary"]["duplicate_row_count"] == 1
    assert (tmp_path / "data.html").exists()
    history = json.loads((tmp_path / "executions.json").read_text(encoding="utf-8"))
    assert history["executions"][0]["source_file"] == "data.csv"


def test_report_from_a_scan_includes_the_scan_duration(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)
    document = json.loads(scan_document.read_text(encoding="utf-8"))
    document["duration_seconds"] = 12.5
    scan_document.write_text(json.dumps(document), encoding="utf-8")

    profile = analyze_scan(scan_document)

    assert 12.5 < profile.processing_seconds < 17.5
    assert _report("--scan", scan_document).exit_code == 0
    history = json.loads((tmp_path / "executions.json").read_text(encoding="utf-8"))
    entry = history["executions"][0]
    assert 12.5 < entry["analysis_seconds"] <= entry["total_seconds"] < 17.5


def test_report_from_a_scan_never_reads_the_source(tmp_path, monkeypatch):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)

    def refuse(self):
        raise AssertionError("the source was read")

    monkeypatch.setattr(csv_reader.CsvReader, "__iter__", refuse)
    profile = analyze_scan(scan_document)

    assert profile.datasets[0].summary.row_count == 3
    assert profile.config.scan.records.preview == 10


def test_a_missing_source_is_accepted(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)
    source.unlink()

    profile = analyze_scan(scan_document)

    assert profile.source.filename == "data.csv"
    assert profile.datasets[0].preview[0].values == ["1", "aaa@aaaaaaa.aaa", "Paris"]


def test_a_source_of_another_size_is_stale(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)
    write_text(tmp_path, "data.csv", ROWS + "3,cy@example.com,Lyon\n")

    result = _report("--scan", scan_document)

    assert result.exit_code == 4
    assert "Stale scan" in result.stderr
    assert "tabalyst scan" in result.stderr
    assert not (tmp_path / "data.html").exists()


def test_a_changed_source_of_the_same_size_is_stale(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)
    write_text(tmp_path, "data.csv", ROWS.replace("Paris", "Lille"))
    stat = source.stat()
    os.utime(source, (stat.st_atime, stat.st_mtime + 10))

    with pytest.raises(InputError, match="SHA-256 differs"):
        analyze_scan(scan_document)


def test_a_touched_source_with_the_same_content_is_fresh(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)
    stat = source.stat()
    os.utime(source, (stat.st_atime, stat.st_mtime + 10))

    assert analyze_scan(scan_document).datasets[0].summary.row_count == 3


def test_other_scan_settings_in_the_configuration_are_stale(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)
    other = _config(tmp_path, "other.json", {"scan": {"limits": {"max_samples": 5}}})
    same = _config(tmp_path, "same.json", {"scan": {"random_seed": 42}})
    presentation = _config(
        tmp_path, "presentation.json", {"value_examples": {"inline_display_size": 1}}
    )

    result = _report("--scan", scan_document, "--config", other)

    assert result.exit_code == 2
    assert "Stale scan" in result.stderr
    assert analyze_scan(scan_document, same).datasets[0].summary.row_count == 3
    profile = analyze_scan(scan_document, presentation)
    assert profile.config.value_examples.inline_display_size == 1


def test_scan_settings_of_the_document_apply(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS.replace(",", ";"))
    config = _config(tmp_path, "config.json", {"scan": {"csv": {"delimiter": ";"}}})
    scan_document = _scan(source, "--config", config)

    profile = analyze_scan(scan_document)

    assert profile.source.delimiter == ";"
    assert profile.config.scan.csv.delimiter == ";"


def test_csv_options_cannot_be_combined_with_scan(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)

    result = _report("--scan", scan_document, "--delimiter", ";")

    assert result.exit_code == 2
    assert "--scan" in result.stderr
    with pytest.raises(ConfigurationError):
        generate_reports([scan_document], from_scan=True, encoding="utf-8")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("id\n1\n", "not valid UTF-8 JSON"),
        ('{"format": "other"}', "Not a scan document"),
        (
            json.dumps(
                {
                    "format": "tabalyst.scan",
                    "format_version": "0.1.0a",
                    "format_revision": 1,
                }
            ),
            "0.1.0a revision 1",
        ),
    ],
)
def test_inputs_must_be_current_scan_documents(tmp_path, content, message):
    document = write_text(tmp_path, "data.scan.json", content)

    result = _report("--scan", document)

    assert result.exit_code == 4
    assert message in result.stderr


def test_an_invalid_scan_document_is_an_input_error(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scan_document = _scan(source)
    document = json.loads(scan_document.read_text(encoding="utf-8"))
    del document["datasets"][0]["records"]
    scan_document.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(InputError, match="records"):
        analyze_scan(scan_document)


def test_json_sources_keep_report_names_apart_from_the_source(tmp_path):
    source = write_text(tmp_path, "orders.json", json.dumps([{"id": 1}]))
    scan_document = _scan(source)

    result = _report("--scan", scan_document)

    assert result.exit_code == 0, result.output
    assert (tmp_path / "orders.report.html").exists()
    assert json.loads(source.read_text(encoding="utf-8")) == [{"id": 1}]
    replaced = _report("--scan", scan_document, "-o", tmp_path / "orders.html")
    assert replaced.exit_code == 4
    assert "overwrite an input" in replaced.stderr


def test_scan_documents_run_as_a_batch(tmp_path):
    first = write_text(tmp_path, "a.csv", "x\n1\n")
    second = write_text(tmp_path, "b.csv", "x\n2\n")
    _scan(first)
    _scan(second)
    reports = tmp_path / "reports"

    result = _report("--scan", tmp_path / "*.scan.json", "-d", reports)

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in reports.glob("*.html")) == ["a.html", "b.html"]


def test_pandas_is_gone():
    """Gate 5: the pandas engine and dependency are removed."""
    root = Path(__file__).parents[2]
    for path in (root / "src" / "tabalyst").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "import pandas" not in content, path
        assert "from pandas" not in content, path
    assert "pandas" not in (root / "pyproject.toml").read_text(encoding="utf-8")


def test_settings_absent_from_the_configuration_are_not_compared(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS.replace(",", ";"))
    config = _config(tmp_path, "config.json", {"scan": {"random_seed": 7}})
    scan_document = _scan(source, "--config", config, "--delimiter", ";")

    result = _report("--scan", scan_document, "--config", config)

    assert result.exit_code == 0, result.output


def test_a_source_not_beside_the_scan_is_reported_unchecked(tmp_path):
    source = write_text(tmp_path, "data.csv", ROWS)
    scans = tmp_path / "scans"
    assert runner.invoke(app, ["scan", str(source), "-d", str(scans)]).exit_code == 0

    result = _report("--scan", scans / "data.scan.json")

    assert result.exit_code == 0, result.output
    assert "not found beside the scan document" in result.stderr
    assert (scans / "data.html").exists()


def test_an_unreadable_scan_document_fails_alone(tmp_path):
    _scan(write_text(tmp_path, "a.csv", "x\n1\n"))
    write_text(tmp_path, "b.scan.json", "{}")

    result = _report("--scan", tmp_path / "*.scan.json")

    assert result.exit_code == 4
    assert "1 succeeded, 1 failed" in result.stderr
    assert (tmp_path / "a.html").exists()
    assert not (tmp_path / "b.html").exists()
