# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: normalization, limits and structure sections of the report
(lot 5d).

Profile revision 6 carries every normalization stage and the variant groups
of each column, the limited measures and diagnostics of each dataset, and the
structure of JSON datasets (design 16.7).
"""

import json

import pytest
from scan_helpers import write_text

from tabalyst.report_config import ReportConfig
from tabalyst.reporting import render_report
from tabalyst.service import analyze_csv

pytestmark = pytest.mark.lot("5d")

CITIES = "city\nMontréal\nmontreal\nMONTREAL\nQuébec\nLaval\n"


def _config(**scan) -> ReportConfig:
    return ReportConfig.model_validate({"scan": scan})


def _column(profile, name):
    return next(
        column for column in profile.datasets[0].columns if column.name == name
    )


def test_every_normalization_stage_is_listed_raw_first(tmp_path):
    source = write_text(tmp_path, "cities.csv", CITIES)

    normalization = _column(analyze_csv(source), "city").normalization

    stages = {stage.stage: stage for stage in normalization.stages}
    assert list(stages) == [
        "raw",
        "nfc",
        "trim",
        "collapse_whitespace",
        "casefold",
        "strip_accents",
    ]
    assert stages["raw"].changed_count is None
    assert stages["raw"].distinct_count == 5
    assert stages["casefold"].changed_count == 4
    assert stages["casefold"].changed_percent == 80.0
    assert stages["casefold"].distinct_count == 4
    assert stages["strip_accents"].changed_count == 2
    assert stages["strip_accents"].distinct_count == 3
    assert stages["strip_accents"].distinct_status == "complete"


def test_disabled_stage_has_no_counts(tmp_path):
    source = write_text(tmp_path, "cities.csv", CITIES)

    profile = analyze_csv(source, _config(normalization={"strip_accents": False}))

    stage = _column(profile, "city").normalization.stages[-1]
    assert stage.stage == "strip_accents"
    assert not stage.enabled
    assert stage.changed_count is None
    assert stage.distinct_count is None
    assert stage.distinct_status == "disabled"


def test_variant_groups_list_raw_spellings_and_raise_an_issue(tmp_path):
    source = write_text(tmp_path, "cities.csv", CITIES)

    profile = analyze_csv(source)

    normalization = _column(profile, "city").normalization
    assert normalization.variant_group_status == "complete"
    assert normalization.variant_group_count == 1
    assert not normalization.variant_groups_truncated
    [group] = normalization.variant_groups
    assert group.key == "montreal"
    assert group.count == 3
    assert group.distinct_count == 3
    assert {item.value for item in group.variants} == {
        "Montréal",
        "montreal",
        "MONTREAL",
    }
    issues = {issue.code: issue for issue in profile.datasets[0].issues}
    assert issues["variant_groups"].count == 1
    assert issues["variant_groups"].severity == "info"
    html = render_report(profile)
    assert 'id="variant-table"' in html
    assert "Compared distinct" in html


def test_variant_groups_of_a_sensitive_column_are_masked(tmp_path):
    source = write_text(
        tmp_path, "people.csv", "email\nAnn@example.com\nann@example.com\n"
    )

    normalization = _column(analyze_csv(source), "email").normalization

    [group] = normalization.variant_groups
    assert group.key == "aaa@aaaaaaa.aaa"
    assert {item.value for item in group.variants} == {
        "Aaa@aaaaaaa.aaa",
        "aaa@aaaaaaa.aaa",
    }


def test_limited_measures_name_their_field_measure_and_setting(tmp_path):
    source = write_text(
        tmp_path, "ids.csv", "id\n" + "".join(f"v{i}\n" for i in range(12))
    )

    profile = analyze_csv(source, _config(limits={"max_distinct_per_field": 10}))

    limits = profile.datasets[0].limits
    measures = {measure.measure: measure for measure in limits.measures}
    cardinality = measures["values.cardinality"]
    assert cardinality.column_id == profile.datasets[0].columns[0].id
    assert cardinality.path == "id"
    assert cardinality.reason == "distinct_limit"
    assert cardinality.limit == 10
    assert cardinality.lower_bound == 11
    assert "normalization.stages.casefold.cardinality" in measures
    assert "normalization.variant_groups" in measures
    assert [item.code for item in limits.diagnostics] == ["measures_limited"]
    html = render_report(profile)
    assert 'id="limits"' in html
    assert 'href="#limits"' in html
    assert "scan.limits.max_distinct_per_field" in html


def test_limits_section_is_absent_when_nothing_is_limited(tmp_path):
    source = write_text(tmp_path, "cities.csv", CITIES)

    profile = analyze_csv(source)

    limits = profile.datasets[0].limits
    assert limits.measures == []
    assert limits.diagnostics == []
    assert limits.untracked_observations == 0
    assert 'id="limits"' not in render_report(profile)


def test_structural_limits_and_diagnostics_of_a_json_dataset(tmp_path):
    records = [{"id": i, "deep": {"a": {"b": i}}, f"x{i % 3}": 1} for i in range(6)]
    source = write_text(tmp_path, "records.json", json.dumps(records))

    profile = analyze_csv(
        source, _config(limits={"max_depth": 2, "max_fields": 3})
    )

    limits = profile.datasets[0].limits
    paths = next(item for item in limits.measures if item.measure == "structure.paths")
    assert paths.column_id is None
    assert paths.path is None
    assert paths.reason == "field_limit"
    assert paths.lower_bound == 4
    assert limits.untracked_observations > 0
    assert limits.depth_truncated_observations == 6
    codes = {item.code for item in limits.diagnostics}
    assert {"field_limit", "depth_limit"} <= codes
    depth = next(item for item in limits.diagnostics if item.code == "depth_limit")
    assert depth.level == "warning"
    assert depth.locations[0].record == 1
    assert profile.datasets[0].structure.path_status == "limited"
    assert profile.datasets[0].structure.path_count is None


def test_excluded_records_appear_as_diagnostics(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a,b\n1,2\n3\n4,5\n")

    profile = analyze_csv(source, _config(errors={"policy": "tolerant"}))

    [diagnostic] = profile.datasets[0].limits.diagnostics
    assert diagnostic.code == "csv_width_mismatch"
    assert diagnostic.level == "error"
    assert diagnostic.locations[0].record == 2
    assert diagnostic.locations[0].line == 3


def test_json_structure_lists_containers_presence_and_arrays(tmp_path):
    document = {
        "customers": [
            {"id": 1, "tags": ["a", "b"], "address": {"city": "Paris"}},
            {"id": 2, "tags": [], "address": {}},
            {"id": 3, "address": {"city": "Lyon"}},
        ],
        "meta": {"version": 1},
    }
    source = write_text(tmp_path, "shop.json", json.dumps(document))

    profile = analyze_csv(source)

    datasets = {dataset.id: dataset for dataset in profile.datasets}
    customers = datasets["$.customers[]"].structure
    assert customers.record_types == {"object": 3}
    assert customers.path_status == "complete"
    assert customers.path_count == 5
    assert customers.max_depth_seen == 2
    fields = {field.path: field for field in customers.fields}
    assert list(fields) == ["id", "tags", "tags[]", "address", "address.city"]
    tags = fields["tags"]
    assert tags.depth == 1
    assert tags.parent is None
    assert tags.native_types == {"array": 2}
    assert (tags.present_count, tags.parent_count, tags.absent_count) == (2, 3, 1)
    assert tags.present_percent == 66.67
    assert tags.arrays.count == 2
    assert tags.arrays.empty_count == 1
    assert (tags.arrays.minimum_length, tags.arrays.maximum_length) == (0, 2)
    assert tags.arrays.mean_length == 1.0
    assert tags.arrays.item_count == 2
    assert not tags.column
    items = fields["tags[]"]
    assert items.parent == "tags"
    assert items.parent_type == "array"
    assert items.absent_count is None
    assert items.present_percent is None
    assert items.column
    city = fields["address.city"]
    assert (city.depth, city.parent, city.absent_count) == (2, "address", 1)
    assert not fields["address"].column
    root = {field.path: field for field in datasets["$"].structure.fields}
    assert root["customers"].collection == "$.customers[]"
    assert root["customers"].arrays.item_count == 3
    html = render_report(profile)
    assert 'id="d1-structure"' in html
    assert 'id="d2-structure"' in html


def test_csv_sources_have_no_structure_section(tmp_path):
    source = write_text(tmp_path, "cities.csv", CITIES)

    profile = analyze_csv(source)

    assert profile.datasets[0].structure is None
    assert 'id="structure"' not in render_report(profile)
