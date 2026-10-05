# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Options that a kind of source cannot use are ignored with a warning."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.option_notices import ignored_options
from tabalyst.projects.location import StorageLocation

runner = CliRunner()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    return StorageLocation.local()


def invoke(*args):
    return runner.invoke(app, [str(arg) for arg in args])


def source(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("name", ["a.json", "a.jsonl", "a.ndjson", "a.xlsx"])
def test_a_csv_option_is_ignored_for_other_formats(name):
    notices = ignored_options(Path(name), delimiter=";", encoding="cp1252")
    assert notices == [f"--delimiter and --encoding are ignored: {name} is not a CSV file."]


def test_one_csv_option_is_named_alone():
    assert ignored_options(Path("a.json"), encoding="cp1252") == [
        "--encoding is ignored: a.json is not a CSV file."
    ]


@pytest.mark.parametrize("name", ["a.csv", "a.jsonl"])
def test_collection_options_are_ignored_for_one_dataset_sources(name):
    notices = ignored_options(Path(name), collections=["$.a[]"], all_collections=True)
    assert [n.split(" ")[0] for n in notices] == ["--collection", "--all-collections"]


@pytest.mark.parametrize("name", ["a.json", "a.xlsx"])
def test_options_a_format_uses_raise_no_notice(name):
    assert ignored_options(Path(name), collections=["$.a[]"], all_collections=True) == []
    assert ignored_options(Path("a.csv"), delimiter=";", encoding="cp1252") == []


def test_report_warns_and_still_reports(tmp_path):
    table = source(tmp_path, "t.csv", "id,label\n1,a\n2,b\n")
    data = source(tmp_path, "d.json", json.dumps({"rows": [{"id": 1}, {"id": 2}]}))

    result = invoke("report", table, data, "--delimiter", ";", "--collection", "rows", "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert f"Warning [{table}]: --collection is ignored" in result.output
    assert f"Warning [{data}]: --delimiter is ignored" in result.output
    assert "--delimiter" not in result.output.split(f"Warning [{table}]")[1].splitlines()[0]
    assert (tmp_path / "out" / "t.html").is_file()
    assert (tmp_path / "out" / "d.report.html").is_file()


def test_scan_warns_and_still_scans(tmp_path):
    table = source(tmp_path, "t.csv", "id,label\n1,a\n")

    result = invoke("scan", table, "--collection", "rows", "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert "--collection is ignored: a CSV file holds one table." in result.output
    assert (tmp_path / "out" / "t.scan.json").is_file()


def test_quiet_keeps_the_warning(tmp_path):
    table = source(tmp_path, "t.csv", "id,label\n1,a\n")

    result = invoke("scan", table, "--collection", "rows", "-q", "-d", tmp_path / "out")

    assert "--collection is ignored" in result.output
