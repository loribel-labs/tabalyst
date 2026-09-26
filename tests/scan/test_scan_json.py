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
