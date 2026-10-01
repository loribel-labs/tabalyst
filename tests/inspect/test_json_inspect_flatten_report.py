"""JSON Inspect: complex columns, late fields and scan modes under flatten (lot JI-3).

Design sections 7.2 and 16.3. The report shows a container kept whole at the
flatten limit as a column of type ``complex``; nothing changes without a limit.
"""

import json

import pytest
from inspect_helpers import (
    dataset,
    displays,
    field,
    rows,
    run_scan,
    write_json,
    write_text,
)

from tabalyst.report_config import ReportConfig
from tabalyst.service import analyze_csv

pytestmark = pytest.mark.inspect_lot("JI-3")

CUSTOMERS = [
    {"id": 1, "address": {"city": "Paris", "geo": {"lat": 1}}, "tags": ["a", "b"]},
    {"id": 2, "address": {"city": "Lyon", "geo": {"lat": 2}}, "tags": []},
    {"id": 3},
]


def _profile(tmp_path, data=CUSTOMERS, **flatten):
    source = write_json(tmp_path, "data.json", data)
    scan = {"json": {"collections": ["$[]"], "flatten": flatten}}
    profile = analyze_csv(source, ReportConfig.model_validate({"scan": scan}))
    assert [item.id for item in profile.datasets] == ["$[]"]
    return profile.datasets[0]


def _columns(profile):
    return {column.name: column for column in profile.columns}


def test_without_a_limit_containers_stay_structure(tmp_path):
    columns = _columns(_profile(tmp_path))

    assert list(columns) == ["id", "address.city", "address.geo.lat", "tags[]"]
    assert not any(column.inferred_type == "complex" for column in columns.values())


def test_a_container_at_the_limit_is_a_complex_column(tmp_path):
    profile = _profile(tmp_path, max_depth=2)
    columns = _columns(profile)

    assert list(columns) == ["id", "address.city", "address.geo", "tags[]"]
    geo = columns["address.geo"]
    assert geo.inferred_type == "complex"
    assert geo.type_counts == {"object": 2}
    # Absent where the parent object exists but has no such member.
    assert geo.missing_count == 0
    assert profile.summary.inferred_type_counts["complex"] == 1
    assert "empty_columns" not in {issue.code for issue in profile.issues}


def test_arrays_at_the_limit_are_complex_columns(tmp_path):
    columns = _columns(_profile(tmp_path, max_depth=1))

    assert list(columns) == ["id", "address", "tags"]
    assert columns["address"].type_counts == {"object": 2}
    assert columns["address"].missing_count == 1  # the absent member
    assert columns["tags"].type_counts == {"array": 2}
    assert columns["tags"].missing_count == 1


def test_null_next_to_complex_values_is_still_a_complex_column(tmp_path):
    data = [{"a": {"x": 1}}, {"a": None}, {"a": {}}]
    columns = _columns(_profile(tmp_path, data, max_depth=1))

    assert columns["a"].inferred_type == "complex"
    assert columns["a"].type_counts == {"object": 2}
    assert columns["a"].missing_count == 1  # the null


def test_disabled_flatten_is_a_depth_of_one(tmp_path):
    disabled = _columns(_profile(tmp_path, enabled=False))

    assert list(disabled) == ["id", "address", "tags"]


def test_the_separator_names_the_columns(tmp_path):
    columns = _columns(_profile(tmp_path, separator="/"))

    assert list(columns) == ["id", "address/city", "address/geo/lat", "tags[]"]
    assert columns["address/city"].path == "address/city"


def test_array_length_is_kept_at_the_limit_whatever_the_content(tmp_path):
    data = [{"v": [1, {"deep": [True, None]}, [3], "x"]}, {"v": []}]
    source = write_json(tmp_path, "data.json", data)
    result = run_scan(
        source, json={"collections": ["$[]"], "flatten": {"max_depth": 1}}
    )

    records = dataset(result, "$[]")
    assert displays(records) == ["v"]
    assert field(records, "v")["arrays"] == {
        "count": 2,
        "empty": 1,
        "min_length": 0,
        "max_length": 4,
        "total_items": 4,
    }


def test_content_below_the_limit_is_not_read_for_duplicate_keys(tmp_path):
    source = write_text(
        tmp_path, "data.json", '[{"id": 1, "blob": {"a": 1, "a": 2}}]'
    )

    flat = run_scan(source, json={"collections": ["$[]"], "flatten": {"max_depth": 1}})
    assert dataset(flat, "$[]")["record_count"] == 1
    assert flat["scope"]["records_excluded"] == 0

    strict = run_scan(
        source, json={"collections": ["$[]"]}, errors={"policy": "tolerant"}
    )
    assert strict["scope"]["records_excluded"] == 1


def test_invalid_syntax_below_the_limit_is_still_an_error(tmp_path):
    from tabalyst.errors import InputError

    source = write_text(tmp_path, "data.json", '[{"blob": {"a": [1, }}]')

    with pytest.raises(InputError):
        run_scan(source, json={"collections": ["$[]"], "flatten": {"max_depth": 1}})


# CA-11 -------------------------------------------------------------------


def test_a_field_appearing_late_is_discovered(tmp_path):
    data = rows(5000)
    data.append({"id": 5001, "late": "new", "nested": {"deep": 1}})
    source = write_json(tmp_path, "data.json", data)

    result = run_scan(source, json={"collections": ["$[]"]})

    records = dataset(result, "$[]")
    assert displays(records) == ["id", "late", "nested", "nested.deep"]
    assert field(records, "late")["occurrences"] == 1
    assert field(records, "late")["presence"]["absent"] == 5000


# Automatic mode (Python API, no Inspect) ----------------------------------


def test_automatic_mode_still_promotes_collections_below_the_limit(tmp_path):
    data = {"meta": {"inner": {"items": [{"x": 1}, {"x": 2}]}}, "info": {"k": 1}}
    source = write_text(tmp_path, "data.json", json.dumps(data))

    result = run_scan(source, json={"flatten": {"max_depth": 1}})

    ids = [item["id"] for item in result["datasets"]]
    assert "$.meta.inner.items[]" in ids
    document = dataset(result, "$")
    assert displays(document) == ["meta", "info"]
    assert dataset(result, "$.meta.inner.items[]")["record_count"] == 2
