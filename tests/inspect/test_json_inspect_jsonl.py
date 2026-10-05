# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect contract: JSONL and NDJSON sources and their error policy (lot JI-4).

Design section 9. A JSONL source is one dataset ``$[]`` whose records are its
object lines; an excluded line is counted and located by physical line number.
"""

import hashlib
import json

import pytest
from inspect_helpers import (
    dataset,
    displays,
    field,
    run_scan,
    write_json,
    write_text,
)

from tabalyst.errors import ConfigurationError, InputError

pytestmark = pytest.mark.inspect_lot("JI-4")

BAD_BETWEEN = '{"id": 1}\nnot json\n{"id": 3}\n'


def _diagnostic(result: dict, code: str) -> dict:
    matches = [item for item in result["diagnostics"] if item["code"] == code]
    assert len(matches) == 1, f"expected one {code}, found {result['diagnostics']}"
    return matches[0]


def _write_bytes(directory, name, content: bytes):
    path = directory / name
    path.write_bytes(content)
    return path


# Routing and dataset ----------------------------------------------------------


@pytest.mark.parametrize("name", ["events.jsonl", "events.ndjson", "EVENTS.JSONL", "e.NdJson"])
def test_extensions_select_the_jsonl_reader(tmp_path, name):
    result = run_scan(write_text(tmp_path, name, '{"id": 1}\n{"id": 2}\n'))

    assert result["source"]["format"] == "jsonl"
    assert [item["id"] for item in result["datasets"]] == ["$[]"]
    records = dataset(result, "$[]")
    assert records["kind"] == "collection"
    assert records["collection_path"] == [{"items": True}]
    assert records["record_count"] == 2
    assert records["record_types"] == {"object": 2}


def test_the_dataset_may_be_named_explicitly(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n')

    result = run_scan(source, json={"collections": ["$[]"]})

    assert dataset(result, "$[]")["record_count"] == 1


def test_another_collection_path_is_a_configuration_error(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n')

    with pytest.raises(ConfigurationError):
        run_scan(source, json={"collections": ["$.a[]"]})


def test_scan_records_the_resolved_policy(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n')

    assert run_scan(source)["config"]["errors"]["policy"] == "tolerant"


# CA-18 -------------------------------------------------------------------


def test_default_policy_continues_counts_locates_and_reports_partial(tmp_path):
    source = write_text(tmp_path, "events.jsonl", BAD_BETWEEN)

    result = run_scan(source)

    assert result["status"] == "partial"
    assert dataset(result, "$[]")["record_count"] == 2
    scope = result["scope"]
    assert (scope["records_read"], scope["records_analyzed"], scope["records_excluded"]) == (
        3,
        2,
        1,
    )
    assert scope["exclusions"] == {"invalid_line": 1}
    diagnostic = _diagnostic(result, "jsonl_invalid_line")
    assert diagnostic["level"] == "error"
    assert diagnostic["count"] == 1
    assert diagnostic["locations"] == [{"record": 2, "line": 2}]


def test_locations_are_bounded_but_the_count_is_complete(tmp_path):
    lines = "".join(f"bad {index}\n" for index in range(25))
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n' + lines)

    result = run_scan(source, errors={"max_locations": 10})

    diagnostic = _diagnostic(result, "jsonl_invalid_line")
    assert diagnostic["count"] == 25
    assert len(diagnostic["locations"]) == 10
    assert result["scope"]["exclusions"] == {"invalid_line": 25}


def test_physical_line_numbers_count_blank_lines_records_do_not(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n\n   \nbad\n{"id": 2}\n')

    result = run_scan(source)

    assert _diagnostic(result, "jsonl_invalid_line")["locations"] == [
        {"record": 2, "line": 4}
    ]
    assert result["scope"]["records_read"] == 3


@pytest.mark.parametrize("line", ["[1, 2]", "3", '"text"', "null", "true"])
def test_valid_json_that_is_not_an_object_is_excluded(tmp_path, line):
    source = write_text(tmp_path, "events.jsonl", f'{{"id": 1}}\n{line}\n')

    result = run_scan(source)

    assert result["scope"]["exclusions"] == {"not_object": 1}
    diagnostic = _diagnostic(result, "jsonl_record_not_object")
    assert diagnostic["locations"] == [{"record": 2, "line": 2}]
    assert dataset(result, "$[]")["record_count"] == 1


@pytest.mark.parametrize(
    "line",
    [
        '{"a": NaN}',
        '{"a": Infinity}',
        '{"a": "\\ud800"}',
        '{"a": 1,}',
        '{"a": 1} {"b": 2}',
        "{'a': 1}",
        '{"a": 1',
    ],
)
def test_text_that_is_not_json_for_tabalyst_is_an_invalid_line(tmp_path, line):
    source = write_text(tmp_path, "events.jsonl", f'{{"id": 1}}\n{line}\n')

    result = run_scan(source)

    assert result["scope"]["exclusions"] == {"invalid_line": 1}


def test_duplicate_keys_use_the_existing_exclusion(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n{"a": 1, "a": 2}\n')

    result = run_scan(source)

    assert result["scope"]["exclusions"] == {"duplicate_key": 1}
    assert _diagnostic(result, "json_duplicate_key")["locations"] == [
        {"record": 2, "line": 2}
    ]


# CA-19 -------------------------------------------------------------------


def test_strict_policy_stops_at_the_first_invalid_line(tmp_path):
    source = write_text(tmp_path, "events.jsonl", BAD_BETWEEN + "worse\n")

    with pytest.raises(InputError, match="line 2"):
        run_scan(source, errors={"policy": "strict"})


@pytest.mark.parametrize("line", ["[1]", '{"a": 1, "a": 2}'])
def test_strict_policy_also_stops_on_the_other_exclusions(tmp_path, line):
    source = write_text(tmp_path, "events.jsonl", f'{{"id": 1}}\n{line}\n')

    with pytest.raises(InputError, match="line 2"):
        run_scan(source, errors={"policy": "strict"})


def test_policies_give_different_identities(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n')

    strict = run_scan(source, errors={"policy": "strict"})
    tolerant = run_scan(source, errors={"policy": "tolerant"})

    assert strict["config_sha256"] != tolerant["config_sha256"]


# Lines ---------------------------------------------------------------------


def test_blank_lines_are_not_records(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '\n{"id": 1}\n\n  \t \n{"id": 2}\n\n')

    result = run_scan(source)

    assert result["status"] == "complete"
    assert dataset(result, "$[]")["record_count"] == 2
    assert result["scope"]["records_read"] == 2


def test_last_line_without_a_line_break(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n{"id": 2}')

    assert dataset(run_scan(source), "$[]")["record_count"] == 2


def test_crlf_line_breaks(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\r\n{"id": 2}\r\n')

    result = run_scan(source)

    assert result["status"] == "complete"
    assert dataset(result, "$[]")["record_count"] == 2


def test_byte_order_mark(tmp_path):
    source = _write_bytes(tmp_path, "events.jsonl", b'\xef\xbb\xbf{"id": 1}\n{"id": 2}\n')

    result = run_scan(source)

    assert result["source"]["encoding"] == "utf-8-sig"
    assert dataset(result, "$[]")["record_count"] == 2
    assert result["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


@pytest.mark.parametrize("separator", [" ", " ", "\x0b", "\x0c", "\x85"])
def test_only_line_feed_separates_records(tmp_path, separator):
    # JSON strings may hold these characters raw: they are data, not line ends.
    text = json.dumps({"s": f"a{separator}b"}, ensure_ascii=False)
    source = write_text(tmp_path, "events.jsonl", text + "\n" + text + "\n")

    result = run_scan(source)

    assert result["status"] == "complete"
    assert dataset(result, "$[]")["record_count"] == 2


def test_invalid_utf8_is_fatal_in_both_policies(tmp_path):
    source = _write_bytes(tmp_path, "events.jsonl", b'{"a": 1}\n{"a": "\xff"}\n')

    for policy in ("strict", "tolerant"):
        with pytest.raises(InputError):
            run_scan(source, errors={"policy": policy})


@pytest.mark.parametrize("content", ["", "\n", "  \n\n \t\n"])
def test_a_source_without_a_record_line_is_fatal(tmp_path, content):
    source = write_text(tmp_path, "events.jsonl", content)

    with pytest.raises(InputError):
        run_scan(source)


def test_source_with_only_invalid_lines_is_partial_not_fatal(tmp_path):
    source = write_text(tmp_path, "events.jsonl", "oops\nnope\n")

    result = run_scan(source)

    assert result["status"] == "partial"
    assert dataset(result, "$[]")["record_count"] == 0


def test_hash_and_size_cover_every_byte(tmp_path):
    source = write_text(tmp_path, "events.jsonl", BAD_BETWEEN)

    result = run_scan(source)

    assert result["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["source"]["size_bytes"] == source.stat().st_size


def test_a_line_above_the_size_limit_is_excluded_and_still_hashed(tmp_path):
    long_line = json.dumps({"id": 2, "text": "x" * 300})
    source = write_text(
        tmp_path, "events.jsonl", f'{{"id": 1}}\n{long_line}\n{{"id": 3}}\n'
    )

    result = run_scan(source, limits={"max_line_bytes": 100})

    assert result["scope"]["exclusions"] == {"line_too_long": 1}
    assert _diagnostic(result, "jsonl_line_too_long")["locations"] == [
        {"record": 2, "line": 2}
    ]
    assert dataset(result, "$[]")["record_count"] == 2
    assert result["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(InputError, match="line 2"):
        run_scan(source, limits={"max_line_bytes": 100}, errors={"policy": "strict"})


# I-F01 -------------------------------------------------------------------

NESTED = [
    {"id": 1, "name": "Ana", "address": {"city": "Lyon", "geo": {"lat": 45.75}}, "tags": ["a", "b"]},
    {"id": 2, "name": None, "address": None, "tags": []},
    {"id": "3", "name": "", "price": 1.50, "ok": True},
    {"id": 4, "orders": [{"amount": 10}, {"amount": 4.25}]},
]


def test_records_read_alike_from_json_and_jsonl(tmp_path):
    as_json = write_json(tmp_path, "records.json", NESTED)
    as_jsonl = write_text(
        tmp_path,
        "records.jsonl",
        "".join(json.dumps(record) + "\n" for record in NESTED),
    )

    from_json = run_scan(as_json, json={"collections": ["$[]"]})
    from_jsonl = run_scan(as_jsonl)

    assert from_jsonl["datasets"] == from_json["datasets"]
    assert displays(dataset(from_jsonl, "$[]")) == displays(dataset(from_json, "$[]"))


def test_nested_objects_follow_the_flatten_settings(tmp_path):
    source = write_text(
        tmp_path, "events.jsonl", json.dumps(NESTED[0]) + "\n" + json.dumps(NESTED[1]) + "\n"
    )

    result = run_scan(source, json={"flatten": {"max_depth": 2}})

    records = dataset(result, "$[]")
    assert "address.geo" in displays(records)
    assert "address.geo.lat" not in displays(records)
    assert field(records, "address.geo")["native_types"] == {"object": 1}


# Names ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["data.jsonl", "data.ndjson", "DATA.JSONL"])
def test_report_names_do_not_replace_a_sibling_json_source(name):
    from pathlib import Path

    from tabalyst.report_service import report_name

    assert report_name(Path(name)).endswith(".report.html")
