# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON text of scan and report documents: compact by default, indented on demand
(configuration ``output.json_indent``)."""

import json

import pytest
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.config import json_indent, load_config
from tabalyst.errors import ConfigurationError
from tabalyst.json_text import dump_json
from tabalyst.scan_service import scan_document

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_project_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage"))


def _document() -> dict:
    entry = {"id": 0, "value": 'a "quoted", value\n', "type": "string", "count": 2}
    return {
        "name": "x",
        "datasets": [
            {
                "fields": [
                    {
                        "values": {
                            "samples": {
                                "kept": 1,
                                "listed": [entry, {**entry, "id": 1}],
                                "long_texts": {"listed": [{"id": 0, "preview": "é"}]},
                            }
                        }
                    },
                    {"values": {"samples": {"kept": 0, "listed": []}}},
                ]
            }
        ],
        "other": {"listed": [1, 2]},
    }


def test_the_default_text_has_no_indentation_and_ends_with_a_newline():
    text = dump_json(_document())

    assert text.endswith("}\n") and "\n" not in text[:-1]
    assert ": " not in text.replace('"a \\"quoted\\", value\n"', "")
    assert json.loads(text) == _document()


def test_the_indented_text_writes_each_sample_entry_on_one_line():
    document = _document()

    text = dump_json(document, indent=True)

    assert json.loads(text) == document
    lines = text.splitlines()
    entries = [line for line in lines if line.lstrip().startswith('{"id"')]
    assert len(entries) == 3 and all(line.rstrip().endswith(("}", "},")) for line in entries)
    assert '"listed": []' in text
    assert '\n  "other": {\n    "listed": [\n      1,' in text
    # The document given is left as it was.
    assert document == _document()


def test_a_scan_is_written_compact_or_indented_with_the_same_content(tmp_path):
    from tabalyst import scan

    source = tmp_path / "v.csv"
    source.write_text("v\n" + "\n".join(f"id{n}" for n in range(30)) + "\n")
    result = scan(source)

    compact, indented = scan_document(result), scan_document(result, indent=True)

    assert json.loads(compact) == json.loads(indented)
    assert len(compact) < len(indented) and compact.count("\n") == 1


def test_the_output_setting_defaults_to_no_indentation(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"output": {"json_indent": true}}')

    assert json_indent([]) is False
    assert json_indent([config]) is True
    assert load_config([config]).output.json_indent is True


def test_an_unknown_output_setting_is_refused(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"output": {"indent": true}}')

    with pytest.raises(ConfigurationError):
        json_indent([config])


@pytest.mark.parametrize("indent", [False, True])
def test_the_commands_follow_the_output_setting(tmp_path, indent):
    source = tmp_path / "v.csv"
    source.write_text("v\n" + "\n".join(f"id{n}" for n in range(30)) + "\n")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"output": {"json_indent": indent}}))
    scan_json, report_html = tmp_path / "v.scan.json", tmp_path / "v.html"

    first = runner.invoke(
        app, ["scan", str(source), "-o", str(scan_json), "-c", str(config), "--no-progress"]
    )
    second = runner.invoke(
        app, ["report", str(source), "-o", str(report_html), "-c", str(config), "--no-progress"]
    )

    assert first.exit_code == 0 and second.exit_code == 0, (first.output, second.output)
    for path in (scan_json, tmp_path / "v.json"):
        text = path.read_text(encoding="utf-8")
        assert json.loads(text)["datasets"]
        assert (text.count("\n") > 100) is indent


def test_the_indented_text_writes_the_ids_and_pool_of_the_strata_by_length_on_lines():
    document = _document()
    document["datasets"][0]["fields"][0]["values"]["samples"]["by_length"] = {
        "strata": [{"length": 4, "ids": [3, 8, 11]}, {"length": 5, "ids": []}],
        "listed": [{"id": 9, "value": "abcd"}],
    }
    before = json.loads(json.dumps(document))

    text = dump_json(document, indent=True)

    assert '"ids": [3, 8, 11]' in text and '"ids": []' in text
    assert '{"id": 9, "value": "abcd"}' in text
    assert json.loads(text) == before
    assert document == before  # the placeholders are taken out again
