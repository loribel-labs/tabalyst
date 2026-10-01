"""JSON Inspect contract: flatten, arrays, types and value states (lot JI-3).

Design section 7. ``flatten.max_depth`` keeps a container whole at the limit,
without loss and without warning; ``limits.max_depth`` is a different thing.
The array, type and value-state behaviors are already those of Scan and are
attached here as acceptance tests (CA-15 to CA-17).
"""

import pytest
from inspect_helpers import dataset, displays, field, run_scan, write_json

pytestmark = pytest.mark.inspect_lot("JI-3")

NESTED = [
    {"id": 1, "a": {"b": {"c": 1}}, "tags": ["x", "y"]},
    {"id": 2, "a": {"b": {"c": 2}}, "tags": []},
]


def _scan(tmp_path, data, *, flatten=None, limits=None):
    source = write_json(tmp_path, "data.json", data)
    settings = {"json": {"collections": ["$[]"]}}
    if flatten is not None:
        settings["json"]["flatten"] = flatten
    if limits is not None:
        settings["limits"] = limits
    result = run_scan(source, **settings)
    return result, dataset(result, "$[]")


def _codes(result):
    return [item["code"] for item in result["diagnostics"]]


# CA-12 -------------------------------------------------------------------


def test_default_develops_every_level(tmp_path):
    _, records = _scan(tmp_path, NESTED)

    assert displays(records) == ["id", "a", "a.b", "a.b.c", "tags", "tags[]"]


def test_depth_limit_keeps_the_container_as_a_complex_value(tmp_path):
    _, records = _scan(tmp_path, NESTED, flatten={"max_depth": 2})

    assert displays(records) == ["id", "a", "a.b", "tags", "tags[]"]
    complex_value = field(records, "a.b")
    assert complex_value["native_types"] == {"object": 2}
    assert records["structure"]["max_depth_seen"] == 2


def test_flatten_limit_loses_nothing_and_warns_of_nothing(tmp_path):
    result, records = _scan(tmp_path, NESTED, flatten={"max_depth": 2})

    assert records["structure"]["depth_truncated_observations"] == 0
    assert "depth_limit" not in _codes(result)
    assert records["record_count"] == 2


def test_safety_limit_is_a_different_mechanism(tmp_path):
    result, records = _scan(tmp_path, NESTED, limits={"max_depth": 2})

    assert records["structure"]["depth_truncated_observations"] > 0
    assert "depth_limit" in _codes(result)


def test_array_elements_count_a_segment(tmp_path):
    data = [{"orders": [{"amount": 1}, {"amount": 2}]}]

    _, two = _scan(tmp_path, data, flatten={"max_depth": 2})
    assert displays(two) == ["orders", "orders[]"]
    assert field(two, "orders[]")["native_types"] == {"object": 2}

    _, three = _scan(tmp_path, data, flatten={"max_depth": 3})
    assert displays(three) == ["orders", "orders[]", "orders[].amount"]


def test_disabled_flatten_keeps_only_the_members_of_the_record(tmp_path):
    _, records = _scan(tmp_path, NESTED, flatten={"enabled": False})

    assert displays(records) == ["id", "a", "tags"]
    assert field(records, "a")["native_types"] == {"object": 2}
    # The array itself is observed, its elements are not.
    assert field(records, "tags")["arrays"] == {
        "count": 2,
        "empty": 1,
        "min_length": 0,
        "max_length": 2,
        "total_items": 2,
    }


def test_disabled_flatten_equals_a_depth_of_one(tmp_path):
    source = write_json(tmp_path, "data.json", NESTED)
    disabled = run_scan(source, json={"collections": ["$[]"], "flatten": {"enabled": False}})
    depth_one = run_scan(source, json={"collections": ["$[]"], "flatten": {"max_depth": 1}})

    assert disabled["datasets"] == depth_one["datasets"]


def test_separator_only_changes_the_display(tmp_path):
    data = [{"orders": [{"amount": 1}]}]
    _, dotted = _scan(tmp_path, data)
    _, slashed = _scan(tmp_path, data, flatten={"separator": "/"})

    assert displays(dotted) == ["orders", "orders[]", "orders[].amount"]
    assert displays(slashed) == ["orders", "orders[]", "orders[]/amount"]
    assert [item["path"] for item in dotted["fields"]] == [
        item["path"] for item in slashed["fields"]
    ]


# CA-13 -------------------------------------------------------------------


def test_literal_key_and_nested_key_are_two_fields(tmp_path):
    _, records = _scan(tmp_path, [{"a.b": 1, "a": {"b": 2}}])

    literal = field(records, '["a.b"]')
    nested = field(records, "a.b")
    assert literal["path"] == [{"key": "a.b"}]
    assert nested["path"] == [{"key": "a"}, {"key": "b"}]
    assert literal["id"] != nested["id"]
    assert literal["native_types"] == nested["native_types"] == {"integer": 1}


def test_collision_is_also_prevented_with_another_separator(tmp_path):
    _, records = _scan(
        tmp_path, [{"a/b": 1, "a": {"b": 2}}], flatten={"separator": "/"}
    )

    assert displays(records) == ['["a/b"]', "a", "a/b"]


# CA-15 -------------------------------------------------------------------


def test_arrays_never_add_rows(tmp_path):
    result, records = _scan(tmp_path, [{"id": 1, "tags": ["a", "b", "c"]}])

    assert records["record_count"] == 1
    assert result["scope"]["records_analyzed"] == 1
    tags = field(records, "tags")
    assert tags["native_types"] == {"array": 1}
    assert tags["arrays"]["total_items"] == 3
    assert field(records, "tags[]")["occurrences"] == 3


# CA-16 -------------------------------------------------------------------


def test_mixed_types_stay_distinguishable(tmp_path):
    _, records = _scan(tmp_path, [{"v": 1}, {"v": "a"}, {"v": True}, {"v": 1.5}])

    value = field(records, "v")
    assert value["native_types"] == {
        "integer": 1,
        "number": 1,
        "string": 1,
        "boolean": 1,
    }
    listed = value["values"]["frequencies"]["value"]["listed"]
    assert {(item["value"], item["type"]) for item in listed} == {
        ("1", "integer"),
        ("1.5", "number"),
        ("a", "string"),
        ("true", "boolean"),
    }


def test_the_string_one_and_the_integer_one_are_different_values(tmp_path):
    _, records = _scan(tmp_path, [{"v": 1}, {"v": "1"}])

    listed = field(records, "v")["values"]["frequencies"]["value"]["listed"]
    assert len(listed) == 2


# CA-17 -------------------------------------------------------------------


def test_absent_null_and_empty_string_stay_distinguishable(tmp_path):
    _, records = _scan(tmp_path, [{"id": 1}, {"id": 2, "v": None}, {"id": 3, "v": ""}])

    value = field(records, "v")
    assert value["presence"]["absent"] == 1
    assert value["native_types"]["null"] == 1
    assert value["strings"]["empty"] == 1
    assert value["missing"]["components"]["absent"] == 1
    assert value["missing"]["components"]["null"] == 1
    assert value["missing"]["components"]["empty"] == 1


def test_a_null_parent_leaves_its_children_neither_present_nor_absent(tmp_path):
    _, records = _scan(
        tmp_path, [{"id": 1, "a": {"b": 1}}, {"id": 2, "a": None}, {"id": 3}]
    )

    child = field(records, "a.b")
    assert child["presence"]["parent_count"] == 1
    assert child["presence"]["absent"] == 0
    parent = field(records, "a")
    assert parent["presence"]["absent"] == 1
    assert parent["native_types"]["null"] == 1
