"""JSON Inspect contract: detection, selection and observation scope (lot JI-5).

Design section 8. Inspect reads every event of the source once, so candidates
and element counts are exact; the detail of fields comes from the first records
only. The measured parameters (design section 15) are imported, never written
as numbers here.
"""

import copy
import hashlib
import json
import math

import pytest
from inspect_helpers import (
    candidates,
    dataset,
    field,
    inspect_document,
    parameters,
    rows,
    run_scan,
    warning_codes,
    write_json,
    write_jsonl,
    write_text,
)

from tabalyst.errors import InputError

pytestmark = pytest.mark.inspect_lot("JI-5")


def _selection(document: dict) -> dict:
    return document["detection"]["selection"]


def _dataset_path(document: dict):
    return document["config"]["structure"]["dataset_path"]


def _warning(document: dict, code: str) -> dict:
    matches = [item for item in document["warnings"] if item["code"] == code]
    assert len(matches) == 1, f"expected one {code}, found {document['warnings']}"
    return matches[0]


# Selection (CA-08, CA-09, D14) -----------------------------------------------


def test_a_root_array_of_objects_is_the_dataset(tmp_path):
    document = inspect_document(write_json(tmp_path, "rows.json", rows(3)))

    assert _selection(document) == {"path": "$[]", "basis": "root_array"}
    assert _dataset_path(document) == "$[]"
    assert document["detection"]["root"] == {"type": "array"}
    assert list(candidates(document)) == ["$[]"]


def test_results_envelope_selects_that_collection(tmp_path):
    source = write_json(
        tmp_path, "page.json", {"count": 3, "next": None, "results": rows(3)}
    )

    document = inspect_document(source)

    assert _selection(document) == {
        "path": "$.results[]",
        "basis": "only_eligible_candidate",
    }
    assert _dataset_path(document) == "$.results[]"
    assert warning_codes(document) == []


def test_names_of_properties_play_no_role(tmp_path):
    first = inspect_document(
        write_json(tmp_path, "a.json", {"results": rows(3), "data": rows(3)})
    )
    second = inspect_document(
        write_json(tmp_path, "b.json", {"data": rows(3), "results": rows(3)})
    )

    assert _selection(first)["basis"] == _selection(second)["basis"] == "ambiguous"
    assert _selection(first)["path"] is None


def test_equally_plausible_collections_are_not_resolved(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(5), "orders": rows(5)})

    document = inspect_document(source)

    assert _selection(document) == {"path": None, "basis": "ambiguous"}
    assert _dataset_path(document) is None
    found = candidates(document)
    assert list(found) == ["$.customers[]", "$.orders[]"]
    assert {item["elements"] for item in found.values()} == {5}
    assert all(item["eligible"] for item in found.values())
    assert _warning(document, "ambiguous_collections")["count"] == 2


def test_a_dominant_collection_is_selected(tmp_path):
    ratio = parameters().DOMINANCE_RATIO
    small = 4
    big = math.ceil(ratio * small)
    source = write_json(tmp_path, "page.json", {"results": rows(big), "included": rows(small)})

    document = inspect_document(source)

    assert _selection(document) == {
        "path": "$.results[]",
        "basis": "dominant_candidate",
        "over": "$.included[]",
    }
    assert _dataset_path(document) == "$.results[]"


def test_just_below_the_ratio_is_ambiguous(tmp_path):
    ratio = parameters().DOMINANCE_RATIO
    small = 4
    below = math.ceil(ratio * small) - 1
    source = write_json(tmp_path, "page.json", {"results": rows(below), "included": rows(small)})

    document = inspect_document(source)

    assert _selection(document)["basis"] == "ambiguous"
    assert _dataset_path(document) is None


def test_ineligible_candidates_do_not_compete(tmp_path):
    source = write_json(
        tmp_path, "page.json", {"tags": ["a", "b"], "results": rows(2), "empty": []}
    )

    document = inspect_document(source)

    assert _selection(document)["path"] == "$.results[]"
    found = candidates(document)
    assert found["$.tags[]"]["eligible"] is False
    assert found["$.tags[]"]["ineligible_reason"] == "non_object_elements"
    assert found["$.empty[]"]["eligible"] is False
    assert found["$.empty[]"]["ineligible_reason"] == "empty"
    reasons = {
        item["path"]: item["reason"]
        for item in document["warnings"]
        if item["code"] == "candidate_not_eligible"
    }
    assert reasons == {"$.tags[]": "non_object_elements", "$.empty[]": "empty"}


# Shapes without a supported collection (DP-12, I-E02) -------------------------


@pytest.mark.parametrize(
    ("content", "root", "reason", "paths"),
    [
        ("42", "number", "scalar_root", []),
        ('"text"', "string", "scalar_root", []),
        ("null", "null", "scalar_root", []),
        ('{"a": 1, "b": {"c": 2}}', "object", "no_array", []),
        ("[1, 2, 3]", "array", "no_eligible_array", ["$[]"]),
        ('[{"a": 1}, 2]', "array", "no_eligible_array", ["$[]"]),
        ("[]", "array", "no_eligible_array", ["$[]"]),
        ('{"items": []}', "object", "no_eligible_array", ["$.items[]"]),
        ('{"a": [1, 2]}', "object", "no_eligible_array", ["$.a[]"]),
    ],
)
def test_no_collection_is_not_guessed(tmp_path, content, root, reason, paths):
    document = inspect_document(write_text(tmp_path, "odd.json", content))

    assert document["detection"]["root"] == {"type": root}
    assert list(candidates(document)) == paths
    assert _selection(document) == {"path": None, "basis": "no_eligible_candidate"}
    assert _dataset_path(document) is None
    assert _warning(document, "no_collection")["reason"] == reason


def test_a_single_object_is_not_turned_into_a_one_row_dataset(tmp_path):
    document = inspect_document(write_json(tmp_path, "one.json", {"id": 1, "name": "x"}))

    assert _dataset_path(document) is None
    assert candidates(document) == {}


@pytest.mark.parametrize("content", ["", "   \n\t "])
def test_an_empty_source_is_an_error(tmp_path, content):
    with pytest.raises(InputError):
        inspect_document(write_text(tmp_path, "empty.json", content))


# Candidates ----------------------------------------------------------------


def test_candidates_follow_document_order(tmp_path):
    source = write_json(tmp_path, "d.json", {"b": rows(1), "a": rows(2), "c": rows(3)})

    assert list(candidates(inspect_document(source))) == ["$.b[]", "$.a[]", "$.c[]"]


def test_arrays_inside_records_are_not_candidates(tmp_path):
    customers = [{"id": 1, "orders": rows(2)}, {"id": 2, "orders": rows(3)}]

    document = inspect_document(write_json(tmp_path, "shop.json", {"customers": customers}))

    assert list(candidates(document)) == ["$.customers[]"]


def test_depth_of_discovery_comes_from_the_layers(tmp_path):
    deep = {"a": {"b": {"c": rows(2)}}}
    too_deep = {"a": {"b": {"c": {"d": rows(2)}}}}

    assert list(candidates(inspect_document(write_json(tmp_path, "x.json", deep)))) == [
        "$.a.b.c[]"
    ]
    assert candidates(inspect_document(write_json(tmp_path, "y.json", too_deep))) == {}
    shallow = inspect_document(
        write_json(tmp_path, "z.json", {"x": rows(1), "a": {"b": rows(1)}}),
        json={"discovery_max_depth": 1},
    )
    assert list(candidates(shallow)) == ["$.x[]"]


def test_keys_are_written_in_canonical_spelling(tmp_path):
    document = inspect_document(write_json(tmp_path, "k.json", {"a.b": rows(2)}))

    assert list(candidates(document)) == ['$["a.b"][]']
    assert _dataset_path(document) == '$["a.b"][]'


def test_the_candidate_names_what_it_found(tmp_path):
    customers = [{"id": 1, "address": {"city": "Lyon"}, "tags": ["a"]}, {"id": 2}]

    item = candidates(inspect_document(write_json(tmp_path, "s.json", {"c": customers})))[
        "$.c[]"
    ]

    assert item["elements"] == 2
    assert item["element_types"] == {"object": 2}
    assert item["eligible"] is True
    assert "ineligible_reason" not in item
    assert item["observation"] == {
        "records": 2,
        "fields": 5,  # id, address, address.city, tags, tags[]
        "max_depth": 2,
        "nested_objects": True,
        "arrays": True,
        "complete": True,
    }


def test_flat_records_have_no_nesting(tmp_path):
    item = candidates(inspect_document(write_json(tmp_path, "f.json", rows(3))))["$[]"]

    assert item["observation"]["nested_objects"] is False
    assert item["observation"]["arrays"] is False
    assert item["observation"]["max_depth"] == 1
    assert item["observation"]["fields"] == 1


# Scope of the observation (CA-03, EF-05) -------------------------------------


def test_the_scope_says_what_is_exact_and_what_is_bounded(tmp_path):
    document = inspect_document(write_json(tmp_path, "r.json", rows(3)))
    params = parameters()

    scope = document["detection"]["scope"]
    assert scope["structure"] == "complete"
    assert scope["detail"] == "bounded"
    assert scope["limits"] == {
        "records": params.RECORDS_OBSERVED,
        "fields": params.FIELDS_OBSERVED,
    }
    assert scope["discovery_max_depth"] == 3


def test_the_scope_records_the_discovery_depth_that_was_searched(tmp_path):
    source = write_json(tmp_path, "r.json", rows(3))

    document = inspect_document(source, json={"discovery_max_depth": 5})

    assert document["detection"]["scope"]["discovery_max_depth"] == 5


def test_counts_are_exact_but_details_cover_the_first_records_only(tmp_path):
    observed = parameters().RECORDS_OBSERVED
    total = observed + 5
    source = write_json(tmp_path, "many.json", rows(total))

    item = candidates(inspect_document(source))["$[]"]

    assert item["elements"] == total
    assert item["element_types"] == {"object": total}
    assert item["observation"]["records"] == observed
    assert item["observation"]["complete"] is False


def test_a_source_within_the_bounds_is_observed_completely(tmp_path):
    item = candidates(inspect_document(write_json(tmp_path, "few.json", rows(3))))["$[]"]

    assert item["observation"]["records"] == 3
    assert item["observation"]["complete"] is True


def test_the_number_of_tracked_fields_is_bounded(tmp_path):
    limit = parameters().FIELDS_OBSERVED
    wide = {f"k{index}": index for index in range(limit + 3)}

    item = candidates(inspect_document(write_json(tmp_path, "wide.json", [wide])))["$[]"]

    assert item["observation"]["fields"] == limit
    assert item["observation"]["complete"] is False


def test_the_number_of_candidates_is_bounded_and_blocks_the_choice(tmp_path):
    limit = parameters().MAX_CANDIDATES
    document = {f"list{index}": rows(1) for index in range(limit + 2)}

    result = inspect_document(write_json(tmp_path, "keys.json", document))

    assert len(result["detection"]["candidates"]) == limit
    assert result["detection"]["scope"]["candidates"] == "truncated"
    assert _selection(result) == {"path": None, "basis": "candidates_truncated"}
    assert _warning(result, "candidates_truncated")["count"] == limit


def test_ineligible_candidates_are_described_up_to_a_bound_then_counted(tmp_path):
    notes = parameters().MAX_INELIGIBLE_NOTES
    total = notes + 5
    document = {f"empty{index:03d}": [] for index in range(total)}
    document["results"] = rows(3)

    result = inspect_document(write_json(tmp_path, "many.json", document))

    assert _selection(result)["path"] == "$.results[]"
    described = [
        item["path"]
        for item in result["warnings"]
        if item["code"] == "candidate_not_eligible"
    ]
    assert described == [f"$.empty{index:03d}[]" for index in range(notes)]
    summary = _warning(result, "candidate_not_eligible_truncated")
    assert summary["level"] == "info"
    assert summary["count"] == total
    # Every candidate stays in the detection itself.
    assert len(result["detection"]["candidates"]) == total + 1


def test_no_summary_when_every_ineligible_candidate_is_described(tmp_path):
    notes = parameters().MAX_INELIGIBLE_NOTES
    document = {f"empty{index}": [] for index in range(notes)}
    document["results"] = rows(3)

    result = inspect_document(write_json(tmp_path, "few.json", document))

    assert "candidate_not_eligible_truncated" not in warning_codes(result)


# Late fields (CA-11, EF-18) -------------------------------------------------


def test_a_field_after_the_observed_records_is_found_by_the_scan(tmp_path):
    observed = parameters().RECORDS_OBSERVED
    records = rows(observed + 3)
    records[-1]["late"] = "here"
    source = write_json(tmp_path, "late.json", records)

    document = inspect_document(source)

    item = candidates(document)["$[]"]
    assert item["observation"]["fields"] == 1  # id only: the detail stops early
    assert item["observation"]["complete"] is False
    result = run_scan(source, json={"collections": [_dataset_path(document)]})
    late = field(dataset(result, "$[]"), "late")
    assert late["occurrences"] == 1
    assert late["presence"]["absent"] == observed + 2


# No Scan, whole source (ET-08, D18) -------------------------------------------


def test_inspect_builds_no_records_and_runs_no_scan(tmp_path, monkeypatch):
    from tabalyst.scanner.engine import ScanEngine

    def forbidden(self, *args, **kwargs):
        raise AssertionError("Inspect must not run the Scan engine")

    monkeypatch.setattr(ScanEngine, "consume", forbidden)

    document = inspect_document(write_json(tmp_path, "r.json", rows(3)))

    assert _dataset_path(document) == "$[]"


def test_the_hash_covers_every_byte_read(tmp_path):
    source = write_json(tmp_path, "many.json", rows(parameters().RECORDS_OBSERVED + 5))

    document = inspect_document(source)

    assert document["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert document["source"]["size_bytes"] == source.stat().st_size


def test_a_byte_order_mark_is_accepted_and_hashed(tmp_path):
    source = tmp_path / "bom.json"
    source.write_bytes(b"\xef\xbb\xbf" + json.dumps(rows(2)).encode("utf-8"))

    document = inspect_document(source)

    assert _dataset_path(document) == "$[]"
    assert document["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


# Invalid JSON (DP-08, PO-08) -------------------------------------------------


def test_a_syntax_error_anywhere_fails_the_inspection(tmp_path):
    early = write_text(tmp_path, "early.json", '[{"id": 1}, {"id": }]')
    with pytest.raises(InputError):
        inspect_document(early)


def test_a_syntax_error_after_the_observed_records_still_fails(tmp_path):
    text = json.dumps(rows(parameters().RECORDS_OBSERVED + 20))
    truncated = write_text(tmp_path, "cut.json", text[:-5])

    with pytest.raises(InputError):
        inspect_document(truncated)


def test_trailing_garbage_fails(tmp_path):
    with pytest.raises(InputError):
        inspect_document(write_text(tmp_path, "tail.json", '[{"id": 1}] extra'))


def test_invalid_utf8_fails(tmp_path):
    source = tmp_path / "bad.json"
    source.write_bytes(b'[{"id": "\xff"}]')

    with pytest.raises(InputError):
        inspect_document(source)


# JSONL ---------------------------------------------------------------------


def test_jsonl_has_one_implicit_collection(tmp_path):
    source = write_text(
        tmp_path, "events.jsonl", '{"id": 1}\n\n{"id": 2, "a": {"b": 1}}\nnot json\n[1]\n3\n'
    )

    document = inspect_document(source)

    detection = document["detection"]
    assert detection["root"] == {"type": "lines"}
    assert list(candidates(document)) == ["$[]"]
    assert candidates(document)["$[]"]["elements"] == 2
    assert _selection(document) == {"path": "$[]", "basis": "jsonl_records"}
    assert detection["lines"] == {
        "read": 5,
        "blank": 1,
        "objects": 2,
        "invalid": 1,
        "not_object": 2,
    }


def test_jsonl_bad_lines_are_counted_and_located_never_fatal(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\n\nbad\n[1]\n{"id": 2}\n')

    document = inspect_document(source, errors={"policy": "strict"})

    invalid = _warning(document, "invalid_lines")
    assert invalid["count"] == 1
    assert invalid["locations"] == [{"record": 2, "line": 3}]
    not_object = _warning(document, "non_object_lines")
    assert not_object["locations"] == [{"record": 3, "line": 4}]
    assert document["config"]["errors"] == {"policy": "strict"}


def test_jsonl_without_an_object_selects_nothing(tmp_path):
    source = write_text(tmp_path, "events.jsonl", "1\n2\n")

    document = inspect_document(source)

    assert _dataset_path(document) is None
    assert "no_collection" in warning_codes(document)


def test_jsonl_details_use_the_same_observation(tmp_path):
    source = write_jsonl(tmp_path, "events.jsonl", [{"id": 1, "t": ["a"], "a": {"b": 1}}])

    item = candidates(inspect_document(source))["$[]"]

    assert item["observation"]["arrays"] is True
    assert item["observation"]["nested_objects"] is True


def test_an_empty_jsonl_source_is_an_error(tmp_path):
    with pytest.raises(InputError):
        inspect_document(write_text(tmp_path, "events.jsonl", "\n  \n"))


# Stability (CA-27, ET-09) ---------------------------------------------------


def test_two_inspections_differ_only_by_their_date(tmp_path):
    source = write_json(
        tmp_path,
        "shop.json",
        {"customers": rows(3, tags=["a"]), "orders": rows(3), "note": "x"},
    )

    first = inspect_document(source)
    second = inspect_document(source)

    for document in (first, second):
        document["inspect"]["generated_at"] = None
    assert first == second
    assert json.dumps(first) == json.dumps(second)


def test_equal_content_gives_equal_detection_whatever_the_file_name(tmp_path):
    first = inspect_document(write_json(tmp_path, "one.json", rows(3)))
    second = inspect_document(write_json(tmp_path, "two.json", rows(3)))

    first, second = copy.deepcopy(first), copy.deepcopy(second)
    for document in (first, second):
        document["inspect"]["generated_at"] = None
        document["source"]["name"] = None
    assert first == second
