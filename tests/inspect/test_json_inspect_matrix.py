"""JSON Inspect: end-to-end cases of the specification matrix (lot JI-8).

Design section 16.3 maps every case of the minimal matrix (specification 10.2)
to a test. These two cases had no test through the command line, only through
the engine: several collections chosen on purpose, and a JSONL source with
nested objects and a bad line, from the file to the report.
"""

import json

import pytest
from inspect_helpers import rows, write_json, write_text
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.projects.location import StorageLocation

pytestmark = pytest.mark.inspect_lot("JI-8")

runner = CliRunner()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    return StorageLocation.local()


def _profile(out, source) -> dict:
    return json.loads((out / f"{source.stem}.report.json").read_text(encoding="utf-8"))


def test_several_collections_are_chosen_on_purpose(tmp_path, storage):
    source = write_json(
        tmp_path, "shop.json", {"a": rows(3), "b": rows(4), "c": rows(2)}
    )

    result = runner.invoke(
        app,
        ["scan", str(source), "--collection", "$.a[]", "--collection", "$.b[]"],
    )

    assert result.exit_code == 0, result.output
    document = json.loads(storage.shared_scan_path(source).read_text(encoding="utf-8"))
    assert [item["id"] for item in document["datasets"]] == ["$.a[]", "$.b[]"]


def test_jsonl_with_nested_objects_and_a_bad_line_reports_partially(tmp_path):
    source = write_text(
        tmp_path,
        "events.jsonl",
        '{"id": 1, "user": {"name": "A", "tags": ["x"]}}\n'
        "not json\n"
        '{"id": 2, "user": {"name": "B", "tags": []}}\n'
        "[1, 2]\n",
    )
    out = tmp_path / "out"

    result = runner.invoke(app, ["report", str(source), "-d", str(out)])

    assert result.exit_code == 0, result.output
    profile = _profile(out, source)
    assert profile["source"]["format"] == "jsonl"
    assert [item["id"] for item in profile["datasets"]] == ["$[]"]
    dataset = profile["datasets"][0]
    assert dataset["summary"]["row_count"] == 2
    excluded = [item for item in dataset["issues"] if item["code"] == "excluded_records"]
    assert [(item["count"], item["row_numbers"]) for item in excluded] == [(2, [2, 4])]
    assert "user.name" in json.dumps(profile)
