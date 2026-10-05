# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: JSON datasets, structure and presence (lot 1b)."""

import pytest
from scan_helpers import dataset, field, run_scan, write_json, write_text

from tabalyst import InputError

pytestmark = pytest.mark.lot("1b")

LATE_FIELD = [
    {"id": 1, "name": "Ana", "code": "123"},
    {"id": 2, "name": None, "code": 123},
    {"id": 3, "name": "", "code": "123"},
    {"id": 4, "code": "A1"},
    {"id": 5, "name": "Eve", "code": "123", "email": "eve@example.com"},
]

NESTED_ORDERS = {
    "generated": "2026-09-26",
    "customers": [
        {"id": "C1", "orders": [{"amount": 10.5}, {"amount": 4}, {"amount": None}]},
        {"id": "C2", "orders": []},
        {"id": "C3", "orders": [{"amount": "7", "note": "gift"}]},
        {"id": "C4"},
    ],
}


def test_root_array_is_one_collection_of_object_records(tmp_path):
    result = run_scan(write_json(tmp_path, "people.json", LATE_FIELD))

    assert result["source"]["format"] == "json"
    assert [item["id"] for item in result["datasets"]] == ["$[]"]
    people = dataset(result, "$[]")
    assert people["kind"] == "collection"
    assert people["collection_path"] == [{"items": True}]
    assert people["record_count"] == 5
    assert people["record_types"] == {"object": 5}
    assert [item["display"] for item in people["fields"]] == [
        "id",
        "name",
        "code",
        "email",
    ]


def test_absent_null_and_empty_are_distinct(tmp_path):
    """CA05 and EF08."""
    people = dataset(run_scan(write_json(tmp_path, "people.json", LATE_FIELD)), "$[]")

    name = field(people, "name")
    assert name["presence"] == {
        "parent_type": "object",
        "parent_count": 5,
        "present": 4,
        "absent": 1,
    }
    assert name["native_types"] == {"string": 3, "null": 1}
    assert name["strings"] == {
        "count": 3,
        "empty": 1,
        "blank": 0,
        "marker": 0,
        "content": 2,
    }
    assert name["missing"]["count"] == 3
    assert name["missing"]["components"] == {
        "absent": 1,
        "null": 1,
        "empty": 1,
        "blank": 0,
        "marker": 0,
    }


def test_native_number_and_numeric_string_are_distinct(tmp_path):
    """CA05 and EF10: 123 and "123" keep their native types."""
    people = dataset(run_scan(write_json(tmp_path, "people.json", LATE_FIELD)), "$[]")

    code = field(people, "code")
    assert code["native_types"] == {"string": 4, "integer": 1}
    assert code["values"]["count"] == 5
    assert field(people, "id")["native_types"] == {"integer": 5}


def test_field_appearing_late_has_exact_absences(tmp_path):
    """CA01 and CA03: absences before the first appearance are counted."""
    people = dataset(run_scan(write_json(tmp_path, "people.json", LATE_FIELD)), "$[]")

    email = field(people, "email")
    assert email["first_record"] == 5
    assert email["presence"] == {
        "parent_type": "object",
        "parent_count": 5,
        "present": 1,
        "absent": 4,
    }


def test_nested_arrays_do_not_multiply_parent_records(tmp_path):
    """CA04 and EF07."""
    result = run_scan(write_json(tmp_path, "customers.json", NESTED_ORDERS))
    customers = dataset(result, "$.customers[]")

    assert customers["kind"] == "collection"
    assert customers["collection_path"] == [{"key": "customers"}, {"items": True}]
    assert customers["record_count"] == 4
    orders = field(customers, "orders")
    assert orders["presence"] == {
        "parent_type": "object",
        "parent_count": 4,
        "present": 3,
        "absent": 1,
    }
    assert orders["native_types"] == {"array": 3}
    assert orders["arrays"] == {
        "count": 3,
        "empty": 1,
        "min_length": 0,
        "max_length": 3,
        "total_items": 4,
    }
    items = field(customers, "orders[]")
    assert items["occurrences"] == 4
    assert items["native_types"] == {"object": 4}
    assert items["presence"] == {
        "parent_type": "array",
        "parent_count": 3,
        "present": 4,
        "absent": None,
    }
    amount = field(customers, "orders[].amount")
    assert amount["path"] == [{"key": "orders"}, {"items": True}, {"key": "amount"}]
    assert amount["parent"] == items["id"]
    assert amount["presence"] == {
        "parent_type": "object",
        "parent_count": 4,
        "present": 4,
        "absent": 0,
    }
    assert amount["native_types"] == {"number": 1, "integer": 1, "null": 1, "string": 1}
    note = field(customers, "orders[].note")
    assert (note["presence"]["present"], note["presence"]["absent"]) == (1, 3)


def test_root_object_keeps_a_document_dataset_beside_its_collections(tmp_path):
    """D07 and EF01: content outside collections is analyzed too."""
    result = run_scan(write_json(tmp_path, "customers.json", NESTED_ORDERS))

    assert sorted(item["id"] for item in result["datasets"]) == ["$", "$.customers[]"]
    document = dataset(result, "$")
    assert document["kind"] == "document"
    assert document["record_count"] == 1
    assert field(document, "generated")["native_types"] == {"string": 1}
    customers = field(document, "customers")
    assert customers["collection"] == "$.customers[]"
    assert customers["arrays"]["total_items"] == 4
    assert not any(
        item["display"].startswith("customers[]") for item in document["fields"]
    )


def test_keys_that_look_like_paths_never_collide(tmp_path):
    """O02 and specification scenario 4."""
    source = write_json(
        tmp_path, "keys.json", [{"a.b": 1, "a": {"b": 2}, "c[]": 3, "c": [4]}]
    )

    fields = dataset(run_scan(source), "$[]")["fields"]

    displays = {item["display"]: item["path"] for item in fields}
    assert displays == {
        '["a.b"]': [{"key": "a.b"}],
        "a": [{"key": "a"}],
        "a.b": [{"key": "a"}, {"key": "b"}],
        '["c[]"]': [{"key": "c[]"}],
        "c": [{"key": "c"}],
        "c[]": [{"key": "c"}, {"items": True}],
    }


def test_records_of_mixed_native_types(tmp_path):
    """O03: non-object records are analyzed at the root field."""
    source = write_json(tmp_path, "mixed.json", [{"a": 1}, 2, "x", None, [1, 2]])

    records = dataset(run_scan(source), "$[]")

    assert records["record_count"] == 5
    expected_types = {"object": 1, "integer": 1, "string": 1, "null": 1, "array": 1}
    assert records["record_types"] == expected_types
    root = field(records, "$")
    assert root["path"] == []
    assert root["native_types"] == expected_types
    assert root["presence"] == {
        "parent_type": "record",
        "parent_count": 5,
        "present": 5,
        "absent": 0,
    }
    assert field(records, "a")["presence"]["parent_count"] == 1
    items = field(records, "[]")
    assert items["native_types"] == {"integer": 2}
    assert items["presence"]["parent_count"] == 1


def test_object_records_have_no_root_field(tmp_path):
    people = dataset(run_scan(write_json(tmp_path, "people.json", LATE_FIELD)), "$[]")

    assert all(item["display"] != "$" for item in people["fields"])


def test_scalar_root_is_a_one_record_document(tmp_path):
    document = dataset(run_scan(write_text(tmp_path, "answer.json", "42")), "$")

    assert document["kind"] == "document"
    assert document["record_count"] == 1
    assert document["record_types"] == {"integer": 1}
    assert field(document, "$")["native_types"] == {"integer": 1}


def test_empty_root_array_is_an_empty_collection(tmp_path):
    """O15."""
    records = dataset(run_scan(write_text(tmp_path, "empty.json", "[]")), "$[]")

    assert records["record_count"] == 0
    assert records["fields"] == []


@pytest.mark.parametrize("policy", ["strict", "tolerant"])
def test_invalid_json_is_fatal_in_every_policy(tmp_path, policy):
    source = write_text(tmp_path, "broken.json", '[{"a": 1}, {"a": ]')

    with pytest.raises(InputError):
        run_scan(source, errors={"policy": policy})


def test_explicit_collection_limits_the_requested_scope(tmp_path):
    """D07 and EF05."""
    source = write_json(
        tmp_path,
        "export.json",
        {"meta": {"v": 1}, "customers": [{"id": 1}], "orders": [{"id": 9}]},
    )

    automatic = run_scan(source)
    explicit = run_scan(source, json={"collections": ["$.customers[]"]})

    assert sorted(item["id"] for item in automatic["datasets"]) == [
        "$",
        "$.customers[]",
        "$.orders[]",
    ]
    assert automatic["scope"]["collections"] == {"mode": "auto", "requested": None}
    assert [item["id"] for item in explicit["datasets"]] == ["$.customers[]"]
    assert explicit["scope"]["collections"] == {
        "mode": "explicit",
        "requested": ["$.customers[]"],
    }


def test_explicit_collection_can_gather_nested_arrays(tmp_path):
    source = write_json(
        tmp_path,
        "customers.json",
        {"customers": [{"orders": [{"n": 1}, {"n": 2}]}, {"orders": [{"n": 3}]}]},
    )

    result = run_scan(source, json={"collections": ["$.customers[].orders[]"]})

    orders = dataset(result, "$.customers[].orders[]")
    assert orders["record_count"] == 3
    assert field(orders, "n")["presence"]["present"] == 3


def test_field_limit_bounds_structure_and_says_so(tmp_path):
    """ET07 and specification scenario 5: every record introduces new keys."""
    records = [
        {f"k{index}": index for index in range(start, start + 5)}
        for start in (1, 6, 11)
    ]
    source = write_json(tmp_path, "wide.json", records)

    result = run_scan(source, limits={"max_fields": 10})

    collection = dataset(result, "$[]")
    assert len(collection["fields"]) == 10
    assert collection["structure"]["paths"] == {
        "status": "limited",
        "reason": "field_limit",
        "limit": 10,
        "lower_bound": 11,
    }
    assert collection["structure"]["untracked_observations"] == 5
    assert any(
        item["code"] == "field_limit" and item["level"] == "warning"
        for item in result["diagnostics"]
    )
    assert result["status"] == "complete"


def test_numbers_keep_the_type_of_their_lexical_form(tmp_path):
    """Section 6: 1 is an integer, 1.0 and 1e3 are numbers, "1" is a string."""
    source = write_text(
        tmp_path, "numbers.json", '[1, -0, 12345678901234567890123, 1.0, 1e3, "1"]'
    )

    root = field(dataset(run_scan(source), "$[]"), "$")

    assert root["native_types"] == {"integer": 3, "number": 2, "string": 1}
    assert root["values"]["count"] == 6


def test_document_links_promoted_arrays_up_to_the_discovery_depth(tmp_path):
    """Section 5.2: arrays reachable through keys only become collections."""
    data = {"a": {"b": {"c": [1, 2]}}, "d": [{"x": 1}], "e": [[1], [2, 3]]}
    source = write_json(tmp_path, "document.json", data)

    automatic = run_scan(source)
    shallow = run_scan(source, json={"discovery_max_depth": 2})
    none = run_scan(source, json={"discovery_max_depth": 0})

    assert [item["id"] for item in automatic["datasets"]] == [
        "$",
        "$.a.b.c[]",
        "$.d[]",
        "$.e[]",
    ]
    document = dataset(automatic, "$")
    assert document["collection_path"] is None
    assert field(document, "a.b.c")["collection"] == "$.a.b.c[]"
    assert field(document, "a.b")["collection"] is None
    nested = dataset(automatic, "$.e[]")
    assert nested["record_types"] == {"array": 2}
    assert field(nested, "[]")["native_types"] == {"integer": 3}
    assert field(dataset(automatic, "$.d[]"), "x")["presence"]["present"] == 1

    assert [item["id"] for item in shallow["datasets"]] == ["$", "$.d[]", "$.e[]"]
    shallow_document = dataset(shallow, "$")
    assert field(shallow_document, "a.b.c")["collection"] is None
    assert field(shallow_document, "a.b.c[]")["native_types"] == {"integer": 2}
    assert [item["id"] for item in none["datasets"]] == ["$"]


def test_explicit_collection_without_array_is_empty_and_says_so(tmp_path):
    source = write_json(tmp_path, "export.json", {"customers": {"id": 1}})

    result = run_scan(source, json={"collections": ["$.customers[]", "$.orders[]"]})

    assert [item["id"] for item in result["datasets"]] == [
        "$.customers[]",
        "$.orders[]",
    ]
    assert all(item["record_count"] == 0 for item in result["datasets"])
    warnings = [
        item["dataset"]
        for item in result["diagnostics"]
        if item["code"] == "json_collection_not_found"
    ]
    assert warnings == ["$.customers[]", "$.orders[]"]
    assert result["status"] == "complete"


@pytest.mark.parametrize(
    "collections",
    [[], ["$.a[]", "$.a[].b[]"], ["$.a[]", '$["a"][]'], ["$.a"], ["a[]"]],
)
def test_invalid_collection_selections_are_rejected(collections):
    from tabalyst.scanner import ScanConfig

    with pytest.raises(ValueError):
        ScanConfig.model_validate({"json": {"collections": collections}})


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"  ",
        b'["\xff"]',
        b'"\xed\xa0\x80"',
        b'["a\\udc00b"]',
        b'{"\\udc00": 1}',
        b"[NaN]",
        b"[1] [2]",
        b'"a\x00b"',
    ],
    ids=[
        "empty",
        "blank",
        "utf8",
        "surrogate",
        "lone_surrogate_escape",
        "lone_surrogate_key",
        "nan",
        "trailing",
        "control",
    ],
)
@pytest.mark.parametrize("backend", ["yajl2_c", "python"])
def test_unreadable_json_is_an_input_error(tmp_path, monkeypatch, content, backend):
    import ijson

    from tabalyst.scanner.readers import json_reader

    monkeypatch.setattr(json_reader, "BACKEND", ijson.get_backend(backend))
    source = tmp_path / "bad.json"
    source.write_bytes(content)

    with pytest.raises(InputError, match=r"bad\.json") as error:
        run_scan(source, errors={"policy": "tolerant"})
    assert "b'" not in str(error.value)


def test_errors_outside_the_parser_are_not_reported_as_invalid_json(
    tmp_path, monkeypatch
):
    """Only parser failures become input errors; other exceptions stay bugs."""
    from tabalyst.scanner.readers import json_reader

    def broken(event, value):
        raise ValueError("engine bug")

    monkeypatch.setattr(json_reader, "_native", broken)
    source = write_json(tmp_path, "ok.json", [1])

    with pytest.raises(ValueError, match="engine bug") as error:
        run_scan(source)
    assert not isinstance(error.value, InputError)


def test_canonical_collection_spelling_names_the_dataset(tmp_path):
    source = write_json(tmp_path, "export.json", {"a": [{"x": 1}]})

    result = run_scan(source, json={"collections": ['$["a"][]']})

    assert [item["id"] for item in result["datasets"]] == ["$.a[]"]
    assert result["scope"]["collections"]["requested"] == ["$.a[]"]
    assert dataset(result, "$.a[]")["record_count"] == 1


def test_utf8_byte_order_mark_is_accepted(tmp_path):
    source = tmp_path / "bom.json"
    content = b'\xef\xbb\xbf[{"a": 1}]'
    source.write_bytes(content)

    result = run_scan(source)

    assert result["source"]["encoding"] == "utf-8-sig"
    assert result["source"]["size_bytes"] == len(content)
    assert dataset(result, "$[]")["record_count"] == 1


@pytest.mark.parametrize("policy", ["strict", "tolerant"])
def test_duplicate_keys_make_a_record_malformed(tmp_path, policy):
    """Which duplicate applies is ambiguous; presence must stay exact."""
    source = write_text(
        tmp_path, "dup.json", '[{"a": 1}, {"a": 2, "b": {"a": 3, "a": 4}}, {"a": 5}]'
    )

    if policy == "strict":
        with pytest.raises(InputError, match="Record 2.*duplicate key 'a'"):
            run_scan(source)
        return
    result = run_scan(source, errors={"policy": policy})

    assert result["status"] == "partial"
    assert result["scope"]["exclusions"] == {"duplicate_key": 1}
    records = dataset(result, "$[]")
    assert records["record_count"] == 2
    assert field(records, "a")["presence"]["present"] == 2
    [diagnostic] = result["diagnostics"]
    assert diagnostic["code"] == "json_duplicate_key"
    assert diagnostic["level"] == "error"
    assert diagnostic["locations"] == [{"record": 2, "element": 1}]


def test_depth_limit_truncates_deeper_content_and_says_so(tmp_path):
    """ET06: content below max_depth is counted, not analyzed."""
    source = write_json(
        tmp_path, "deep.json", [{"a": {"b": {"c": 1, "d": [1]}}}, {"a": 1}]
    )

    result = run_scan(source, limits={"max_depth": 2})

    records = dataset(result, "$[]")
    assert [item["display"] for item in records["fields"]] == ["a", "a.b"]
    assert field(records, "a.b")["native_types"] == {"object": 1}
    assert records["structure"]["depth_truncated_observations"] == 3
    assert records["structure"]["max_depth_seen"] == 2
    assert records["structure"]["paths"] == {"status": "complete", "value": 2}
    [diagnostic] = result["diagnostics"]
    assert (diagnostic["code"], diagnostic["level"]) == ("depth_limit", "warning")
    assert diagnostic["locations"] == [{"record": 1, "element": 0}]
    assert result["status"] == "complete"


def test_array_length_counts_elements_below_the_depth_limit(tmp_path):
    source = write_json(tmp_path, "deep.json", [{"a": [[1, 2], [3]]}])

    records = dataset(run_scan(source, limits={"max_depth": 2}), "$[]")

    assert field(records, "a")["arrays"]["total_items"] == 2
    assert field(records, "a[]")["arrays"]["total_items"] == 3
    assert records["structure"]["depth_truncated_observations"] == 3


@pytest.mark.parametrize("policy", ["strict", "tolerant"])
def test_record_above_the_observation_limit(tmp_path, policy):
    """Section 14: fatal when strict, excluded and visible when tolerant."""
    records = [{"a": 1}, {"a": [1, 2, 3, 4]}, {"a": 2}]
    source = write_json(tmp_path, "large.json", records)
    limits = {"max_record_observations": 4}

    if policy == "strict":
        with pytest.raises(InputError, match="Record 2.*max_record_observations"):
            run_scan(source, limits=limits)
        return
    result = run_scan(source, errors={"policy": policy}, limits=limits)

    assert result["status"] == "partial"
    assert result["scope"]["records_read"] == 3
    assert result["scope"]["exclusions"] == {"record_too_large": 1}
    collection = dataset(result, "$[]")
    assert collection["record_count"] == 2
    assert field(collection, "a")["native_types"] == {"integer": 2}
    [diagnostic] = result["diagnostics"]
    assert diagnostic["code"] == "record_too_large"
    assert diagnostic["locations"] == [{"record": 2, "element": 1}]


def test_compiled_and_python_backends_give_the_same_result(tmp_path, monkeypatch):
    """Principle 6: the ijson backend changes speed, never results."""
    import ijson

    from tabalyst.scanner.readers import json_reader

    data = dict(NESTED_ORDERS, big=12345678901234567890123, values=[1.5, True, "é"])
    source = write_json(tmp_path, "customers.json", data)

    compiled = run_scan(source)
    monkeypatch.setattr(json_reader, "BACKEND", ijson.get_backend("python"))
    python = run_scan(source)

    for result in (compiled, python):
        del result["started_at"], result["duration_seconds"]
    assert python == compiled


@pytest.mark.lot("2a")
def test_lone_high_surrogate_is_rejected_by_the_python_backend(tmp_path, monkeypatch):
    """Strings that are not valid Unicode are rejected, never altered.

    The compiled backend replaces a lone high surrogate with ``?`` before
    Tabalyst sees it, a documented limitation of that backend.
    """
    import ijson

    from tabalyst.scanner.readers import json_reader

    monkeypatch.setattr(json_reader, "BACKEND", ijson.get_backend("python"))
    source = tmp_path / "bad.json"
    source.write_bytes(b'[{"name": "a\\ud800"}]')

    with pytest.raises(InputError, match="lone surrogate"):
        run_scan(source)


@pytest.mark.lot("2a")
def test_valid_surrogate_pairs_give_the_same_value_in_both_backends(
    tmp_path, monkeypatch
):
    import ijson

    from tabalyst.scanner.readers import json_reader

    source = tmp_path / "emoji.json"
    source.write_bytes(b'[{"name": "\\ud83d\\ude00"}]')

    compiled = field(dataset(run_scan(source), "$[]"), "name")
    monkeypatch.setattr(json_reader, "BACKEND", ijson.get_backend("python"))
    python = field(dataset(run_scan(source), "$[]"), "name")

    assert compiled["values"]["first"]["value"] == "\U0001f600"
    assert python["values"] == compiled["values"]
