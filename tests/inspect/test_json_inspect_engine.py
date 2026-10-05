# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect engine beyond the contract tests (lot JI-5).

The selection rule at its exact bounds, the same refusals as the Scan reader,
JSONL lines the contract leaves implicit, the models, and the link from the
proposed ``config`` back to a Scan.
"""

import json

import pytest
from inspect_helpers import (
    candidates,
    dataset,
    inspect_document,
    inspect_object,
    parameters,
    rows,
    run_scan,
    write_json,
    write_jsonl,
    write_text,
)
from pydantic import ValidationError

from tabalyst.errors import ConfigurationError, InputError
from tabalyst.progress import ProgressPhase

pytestmark = pytest.mark.inspect_lot("JI-5")


def _candidates(*counts, objects=True):
    from tabalyst.inspector.json_inspect.detect import Candidate

    result = []
    for index, count in enumerate(counts):
        item = Candidate((f"c{index}",))
        item.elements = count
        item.types = {"object" if objects else "string": count}
        result.append(item)
    return result


# Selection rule -------------------------------------------------------------


def _select(*counts, **kwargs):
    from tabalyst.inspector.json_inspect.detect import select

    return select("object", _candidates(*counts), truncated=False, jsonl=False, **kwargs)


def test_the_ratio_is_inclusive_and_a_tie_never_selects():
    ratio = parameters().DOMINANCE_RATIO

    assert _select(ratio * 3, 3).basis == "dominant_candidate"
    assert _select(ratio * 3 - 1, 3).basis == "ambiguous"
    assert _select(7, 7).basis == "ambiguous"


def test_the_dominant_candidate_is_compared_with_the_next_largest_only():
    ratio = parameters().DOMINANCE_RATIO

    choice = _select(2, ratio * 20, 20, 1)

    assert choice.path == "$.c1[]"
    assert choice.over == "$.c2[]"


def test_a_third_candidate_close_to_the_first_blocks_the_choice():
    ratio = parameters().DOMINANCE_RATIO

    assert _select(ratio * 20, 3, ratio * 20 - 1).basis == "ambiguous"


def test_the_choice_does_not_depend_on_the_order_of_the_candidates():
    ratio = parameters().DOMINANCE_RATIO

    assert _select(5, ratio * 5).path == "$.c1[]"
    assert _select(ratio * 5, 5).path == "$.c0[]"


def test_a_root_array_is_never_compared_with_anything():
    from tabalyst.inspector.json_inspect.detect import select

    choice = select("array", _candidates(1), truncated=False, jsonl=False)

    assert (choice.path, choice.basis) == ("$.c0[]", "root_array")


# The same documents as the Scan ---------------------------------------------

INVALID = {
    "truncated": '[{"id": 1}, {"id"',
    "garbage": '[{"id": 1}] extra',
    # A lone low surrogate: the compiled parser backend rejects it itself.
    "lone_surrogate": '[{"id": "a\\udc00b"}]',
    "exponent": '[{"id": 1e999999999999999999999}]',
    "long_integer": '[{"id": ' + "9" * 5000 + "}]",
    "blank": "  \n",
}


@pytest.mark.parametrize("name", sorted(INVALID))
def test_a_source_the_scan_refuses_is_refused_with_the_same_message(tmp_path, name):
    source = write_text(tmp_path, "bad.json", INVALID[name])

    with pytest.raises(InputError) as scan_error:
        run_scan(source, json={"collections": ["$[]"]})
    with pytest.raises(InputError) as inspect_error:
        inspect_document(source)

    assert str(inspect_error.value) == str(scan_error.value)


def test_the_hash_is_the_one_of_the_scan(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(4)})

    document = inspect_document(source)
    scanned = run_scan(source, json={"collections": ["$.customers[]"]})

    assert document["source"]["sha256"] == scanned["source"]["sha256"]
    assert document["source"]["size_bytes"] == scanned["source"]["size_bytes"]


def test_the_jsonl_hash_is_the_one_of_the_scan(tmp_path):
    source = write_text(tmp_path, "e.jsonl", '{"id": 1}\r\n\r\nbad\n{"id": 2}')

    document = inspect_document(source)
    scanned = run_scan(source)

    assert document["source"]["sha256"] == scanned["source"]["sha256"]


def test_a_source_that_is_not_json_is_refused_before_reading(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a,b\n1,2\n")

    with pytest.raises(ConfigurationError, match="no CSV Inspect"):
        inspect_document(source)


def test_a_missing_source_or_a_directory_is_an_input_error(tmp_path):
    with pytest.raises(InputError):
        inspect_document(tmp_path / "absent.json")
    with pytest.raises(InputError):
        inspect_document(tmp_path)


# Candidates -----------------------------------------------------------------


def test_the_element_types_are_counted_in_a_fixed_order(tmp_path):
    source = write_json(tmp_path, "mixed.json", [None, True, 1, 2.5, "x", [1], {"a": 1}])

    item = candidates(inspect_document(source))["$[]"]

    assert list(item["element_types"].items()) == [
        ("object", 1),
        ("array", 1),
        ("string", 1),
        ("number", 2),
        ("boolean", 1),
        ("null", 1),
    ]
    assert item["ineligible_reason"] == "non_object_elements"
    assert item["observation"]["records"] == 1


def test_arrays_of_a_root_array_are_not_candidates(tmp_path):
    source = write_json(tmp_path, "grid.json", [[{"a": 1}], [{"a": 2}]])

    assert list(candidates(inspect_document(source))) == ["$[]"]


def test_an_array_repeated_under_one_key_is_one_candidate(tmp_path):
    source = write_text(
        tmp_path, "dup.json", '{"a": [{"id": 1}], "b": [{"id": 1}], "a": [{"id": 2}, {"id": 3}]}'
    )

    found = candidates(inspect_document(source))

    assert list(found) == ["$.a[]", "$.b[]"]
    assert found["$.a[]"]["elements"] == 3


def test_a_map_of_objects_gives_a_bounded_candidate_list(tmp_path):
    limit = parameters().MAX_CANDIDATES
    users = {f"u{index}": {"orders": rows(1)} for index in range(limit + 3)}

    document = inspect_document(write_json(tmp_path, "users.json", {"users": users}))

    assert len(document["detection"]["candidates"]) == limit
    assert document["detection"]["selection"]["basis"] == "candidates_truncated"


def test_the_observation_describes_the_source_whatever_the_flatten_rules(tmp_path):
    customers = [{"id": 1, "address": {"city": {"name": "Lyon"}}}]
    source = write_json(tmp_path, "deep.json", {"customers": customers})

    document = inspect_document(source, json={"flatten": {"max_depth": 1}})

    observation = candidates(document)["$.customers[]"]["observation"]
    assert observation["max_depth"] == 3
    assert observation["fields"] == 4  # id, address, address.city, address.city.name
    assert document["config"]["flatten"]["max_depth"] == 1


def test_an_empty_record_has_no_depth(tmp_path):
    item = candidates(inspect_document(write_json(tmp_path, "e.json", [{}, {}])))["$[]"]

    assert item["eligible"] is True
    assert item["observation"]["max_depth"] == 0
    assert item["observation"]["fields"] == 0


def test_the_no_collection_message_names_the_depth_searched(tmp_path):
    source = write_json(tmp_path, "one.json", {"a": {"b": {"c": {"d": rows(2)}}}})

    document = inspect_document(source, json={"discovery_max_depth": 2})

    [warning] = [w for w in document["warnings"] if w["code"] == "no_collection"]
    assert "json.discovery_max_depth" in warning["message"]
    assert "2" in warning["message"]


# JSONL ----------------------------------------------------------------------


def test_a_line_above_the_limit_is_counted_among_the_invalid_lines(tmp_path):
    source = write_text(
        tmp_path, "e.jsonl", '{"id": 1}\n{"id": "' + "x" * 50 + '"}\n{"id": 3}\n'
    )

    document = inspect_document(source, limits={"max_line_bytes": 20})

    assert document["detection"]["lines"]["invalid"] == 1
    [warning] = [w for w in document["warnings"] if w["code"] == "invalid_lines"]
    assert warning["locations"] == [{"record": 2, "line": 2}]
    assert candidates(document)["$[]"]["elements"] == 2


def test_a_line_with_a_duplicate_key_is_an_object(tmp_path):
    source = write_text(tmp_path, "e.jsonl", '{"id": 1, "id": 2}\n{"id": 3}\n')

    document = inspect_document(source)

    assert document["detection"]["lines"]["objects"] == 2
    assert document["warnings"] == []


def test_the_located_lines_are_bounded_and_the_count_is_not(tmp_path):
    source = write_text(tmp_path, "e.jsonl", '{"id": 1}\n' + "bad\n" * 25)

    document = inspect_document(source, errors={"max_locations": 3})

    [warning] = [w for w in document["warnings"] if w["code"] == "invalid_lines"]
    assert warning["count"] == 25
    assert [item["line"] for item in warning["locations"]] == [2, 3, 4]


def test_jsonl_with_more_records_than_observed_is_exact_and_incomplete(tmp_path):
    total = parameters().RECORDS_OBSERVED + 3
    source = write_jsonl(tmp_path, "e.jsonl", rows(total))

    item = candidates(inspect_document(source))["$[]"]

    assert item["elements"] == total
    assert item["observation"]["records"] == parameters().RECORDS_OBSERVED
    assert item["observation"]["complete"] is False


def test_jsonl_is_refused_when_it_holds_invalid_utf8(tmp_path):
    source = tmp_path / "e.jsonl"
    source.write_bytes(b'{"id": 1}\n{"id": "\xff"}\n')

    with pytest.raises(InputError, match="UTF-8"):
        inspect_document(source)


# Document and models --------------------------------------------------------


def test_optional_keys_are_absent_not_null(tmp_path):
    document = inspect_document(write_json(tmp_path, "r.json", rows(2)))

    assert "over" not in document["detection"]["selection"]
    assert "lines" not in document["detection"]
    assert "candidates" not in document["detection"]["scope"]
    assert "ineligible_reason" not in document["detection"]["candidates"][0]


def test_the_document_is_json_and_valid_against_its_model(tmp_path):
    from tabalyst.inspector.models import InspectDocument

    source = write_json(tmp_path, "s.json", {"a": rows(3), "b": ["x"], "c": []})

    text = json.dumps(inspect_document(source))

    assert InspectDocument.model_validate_json(text).model_dump_json() == json.dumps(
        json.loads(text), separators=(",", ":")
    )


def test_the_generation_date_is_utc_without_fractions(tmp_path):
    generated = inspect_document(write_json(tmp_path, "r.json", rows(1)))["inspect"][
        "generated_at"
    ]

    assert len(generated) == len("2026-09-30T10:00:00Z")
    assert generated.endswith("Z")


def test_the_model_refuses_a_warning_with_an_unknown_code(tmp_path):
    from tabalyst.inspector.models import InspectDocument

    document = inspect_document(write_json(tmp_path, "r.json", rows(1)))
    document["warnings"].append({"code": "surprise", "level": "info", "message": "x"})

    with pytest.raises(ValidationError):
        InspectDocument.model_validate(document)


def test_progress_reports_the_reading_then_the_completion(tmp_path):
    source = write_json(tmp_path, "r.json", rows(3))
    seen = []

    from tabalyst.inspector.json_inspect import inspect_source

    inspect_source(source, on_progress=seen.append)

    assert seen[0].phase is ProgressPhase.READING
    assert seen[0].bytes_read == 0
    assert seen[0].bytes_total == source.stat().st_size
    assert seen[-1].phase is ProgressPhase.COMPLETE


# From Inspect back to a Scan ------------------------------------------------


def test_the_proposed_config_drives_a_scan_of_the_selected_dataset(tmp_path):
    from tabalyst.scanner import ScanConfig, scan
    from tabalyst.scanner.config import scan_config_from_layer

    source = write_json(
        tmp_path, "shop.json", {"export": {"v": 1}, "customers": rows(4), "tags": ["a"]}
    )
    document = inspect_object(source)

    config = scan_config_from_layer(document.config.to_scan_layer())
    result = scan(source, config=config).model_dump(mode="json")

    assert config.json_.collections == ["$.customers[]"]
    assert dataset(result, "$.customers[]")["record_count"] == 4
    assert isinstance(config, ScanConfig)


def test_the_config_of_a_jsonl_source_scans_its_implicit_dataset(tmp_path):
    from tabalyst.scanner import scan
    from tabalyst.scanner.config import scan_config_from_layer

    source = write_text(tmp_path, "e.jsonl", '{"id": 1}\nbad\n{"id": 2}\n')
    document = inspect_object(source)

    config = scan_config_from_layer(document.config.to_scan_layer())
    result = scan(source, config=config)

    assert config.errors.policy == "tolerant"
    assert result.status == "partial"
    assert result.scope.records_analyzed == 2


def test_a_collections_setting_below_the_file_does_not_change_the_detection(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(40), "orders": rows(2)})

    document = inspect_document(source, json={"collections": ["$.orders[]"]})

    assert document["detection"]["selection"]["path"] == "$.customers[]"
    assert document["config"]["structure"]["dataset_path"] == "$.customers[]"
