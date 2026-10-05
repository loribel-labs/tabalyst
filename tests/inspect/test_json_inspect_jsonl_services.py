# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSONL beyond the contract: parity with JSON under every limit, and services (lot JI-4).

The JSONL reader walks a parsed line instead of consuming parser events; these
tests keep it equal to the JSON reader for the same records under the
settings that shape observations.
"""

import json

import pytest
from inspect_helpers import dataset, run_scan, write_json, write_text
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.errors import InputError

pytestmark = pytest.mark.inspect_lot("JI-4")

BACKSLASH = chr(92)
NEWLINE = chr(10)

RECORDS = [
    {"id": 1, "a": {"b": {"c": [1, {"d": 2}], "e": []}}, "t": ["x", None, 2.5]},
    {"id": 2, "a": None, "t": [[1, 2], [3]], "o": {}},
    {"id": 3, "a": {"b": 5}, "é": {"x y": True, "": "empty key"}},
]


def _sources(tmp_path, records=RECORDS):
    as_json = write_json(tmp_path, "r.json", records)
    as_jsonl = write_text(
        tmp_path, "r.jsonl", "".join(json.dumps(item) + "\n" for item in records)
    )
    return as_json, as_jsonl


def _same_datasets(tmp_path, records=RECORDS, **settings):
    as_json, as_jsonl = _sources(tmp_path, records)
    from_json = run_scan(
        as_json, **{**settings, "json": {**settings.get("json", {}), "collections": ["$[]"]}}
    )
    from_jsonl = run_scan(as_jsonl, **settings)
    assert from_jsonl["datasets"] == from_json["datasets"]
    assert from_jsonl["scope"]["records_analyzed"] == from_json["scope"]["records_analyzed"]
    return from_jsonl


@pytest.mark.parametrize(
    "flatten",
    [
        {"max_depth": 1},
        {"max_depth": 2},
        {"max_depth": 3},
        {"enabled": False},
        {"separator": "/"},
    ],
)
def test_flatten_reads_alike_in_both_formats(tmp_path, flatten):
    _same_datasets(tmp_path, json={"flatten": flatten})


@pytest.mark.parametrize("max_depth", [1, 2, 3])
def test_the_safety_depth_truncates_alike_in_both_formats(tmp_path, max_depth):
    result = _same_datasets(tmp_path, limits={"max_depth": max_depth})

    assert dataset(result, "$[]")["structure"]["depth_truncated_observations"] > 0
    assert "depth_limit" in [item["code"] for item in result["diagnostics"]]


def test_large_numbers_and_decimals_read_alike(tmp_path):
    records = [{"n": 10**30, "d": 1.25, "e": 1e3, "z": -0, "s": "1.50"}]

    _same_datasets(tmp_path, records)


def test_an_integer_above_the_python_limit_is_an_invalid_line(tmp_path):
    source = write_text(tmp_path, "r.jsonl", '{"id": 1}\n{"n": ' + "9" * 5000 + "}\n")

    result = run_scan(source)

    assert result["scope"]["exclusions"] == {"invalid_line": 1}


def test_an_exponent_out_of_range_is_an_invalid_line(tmp_path):
    source = write_text(tmp_path, "r.jsonl", '{"id": 1}\n{"n": 1e9999999999999999999}\n')

    assert run_scan(source)["scope"]["exclusions"] == {"invalid_line": 1}


def test_deeply_nested_lines_are_handled_without_crashing(tmp_path):
    deep = '{"a": ' * 3000 + "1" + "}" * 3000
    source = write_text(tmp_path, "r.jsonl", '{"id": 1}\n' + deep + "\n")

    result = run_scan(source)

    assert result["scope"]["records_read"] == 2


def test_a_record_above_the_observation_limit_is_excluded(tmp_path):
    source = write_text(
        tmp_path,
        "r.jsonl",
        '{"id": 1}\n' + json.dumps({"v": list(range(50))}) + "\n",
    )

    result = run_scan(source, limits={"max_record_observations": 20})

    assert result["scope"]["exclusions"] == {"record_too_large": 1}
    with pytest.raises(InputError, match="line 2"):
        run_scan(
            source,
            limits={"max_record_observations": 20},
            errors={"policy": "strict"},
        )


def test_a_lone_surrogate_is_invalid_even_below_the_flatten_limit(tmp_path):
    line = '{"blob": {"deep": "' + BACKSLASH + 'ud800"}}'
    source = write_text(tmp_path, "r.jsonl", '{"id": 1}' + NEWLINE + line + NEWLINE)

    result = run_scan(source, json={"flatten": {"max_depth": 1}})

    assert result["scope"]["exclusions"] == {"invalid_line": 1}


def test_a_surrogate_pair_is_a_valid_character(tmp_path):
    pair = BACKSLASH + "ud83d" + BACKSLASH + "ude00"
    source = write_text(tmp_path, "r.jsonl", '{"s": "' + pair + '"}' + NEWLINE)

    assert run_scan(source)["status"] == "complete"


def test_duplicate_keys_below_the_flatten_limit_are_not_checked(tmp_path):
    source = write_text(tmp_path, "r.jsonl", '{"id": 1, "blob": {"a": 1, "a": 2}}\n')

    flat = run_scan(source, json={"flatten": {"max_depth": 1}})
    full = run_scan(source)

    assert flat["scope"]["records_excluded"] == 0
    assert full["scope"]["exclusions"] == {"duplicate_key": 1}


def test_the_size_limit_boundary_is_the_content_without_the_line_break(tmp_path):
    # Content of exactly 20 bytes is read, 21 is excluded, with LF, CRLF or no break.
    exact = '{"k": "' + "x" * 11 + '"}'
    over = '{"k": "' + "x" * 12 + '"}'
    assert (len(exact), len(over)) == (20, 21)
    for ending in ("\n", "\r\n", ""):
        source = write_text(
            tmp_path, "r.jsonl", exact + "\n" + over + ending
        )
        result = run_scan(source, limits={"max_line_bytes": 20})
        assert result["scope"]["exclusions"] == {"line_too_long": 1}, repr(ending)
        source = write_text(tmp_path, "s.jsonl", over + "\n" + exact + ending)
        result = run_scan(source, limits={"max_line_bytes": 20})
        assert result["scope"]["records_analyzed"] == 1, repr(ending)


def test_a_long_line_is_skipped_across_many_reads_and_still_hashed(tmp_path):
    import hashlib

    long_line = '{"k": "' + "x" * (3 << 20) + '"}'
    source = write_text(tmp_path, "r.jsonl", f'{{"id": 1}}\n{long_line}\n{{"id": 3}}')

    result = run_scan(source, limits={"max_line_bytes": 1000})

    assert result["scope"]["exclusions"] == {"line_too_long": 1}
    assert dataset(result, "$[]")["record_count"] == 2
    assert result["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_the_default_line_limit_is_16_mib(tmp_path):
    from tabalyst.scanner import ScanConfig

    limits = ScanConfig().limits
    assert limits.max_line_bytes == 16 * 1024 * 1024


# Services ------------------------------------------------------------------


def test_report_command_on_a_jsonl_source(tmp_path):
    source = write_text(
        tmp_path,
        "events.jsonl",
        '{"id": 1, "kind": "a"}\nnot json\n{"id": 2, "kind": "b"}\n',
    )

    result = CliRunner().invoke(app, ["report", str(source)])

    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "events.report.json").read_text(encoding="utf-8"))
    assert (tmp_path / "events.report.html").exists()
    assert report["source"]["format"] == "jsonl"
    dataset_profile = report["datasets"][0]
    assert dataset_profile["id"] == "$[]"
    assert dataset_profile["summary"]["row_count"] == 2
    issues = {item["code"]: item for item in dataset_profile["issues"]}
    assert issues["excluded_records"]["count"] == 1
    assert issues["excluded_records"]["row_numbers"] == [2]


def test_scan_command_writes_a_scan_of_a_ndjson_source(tmp_path):
    source = write_text(tmp_path, "events.ndjson", '{"id": 1}\n{"id": 2}\n')

    output = tmp_path / "events.scan.json"
    result = CliRunner().invoke(app, ["scan", str(source), "-o", str(output)])

    assert result.exit_code == 0, result.output
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["source"]["format"] == "jsonl"
    assert document["scope"]["collections"] is None
