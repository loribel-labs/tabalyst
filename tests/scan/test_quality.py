# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Observations, quality issues and limits, and the adaptive normalization
(design 10 and 18.13): the rules, the bounds, the document and the Report."""

import json
from pathlib import Path

import pytest
from scan_helpers import write_text

from tabalyst.report_config import ReportConfig
from tabalyst.report_profile import build_profile
from tabalyst.scan_document import base_of, facts_sha256
from tabalyst.scan_reuse import scan_from_document
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner import api as scanner_api
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.quality import RULES
from tabalyst.scanner.validation import check_scan

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "input"


def _scan(tmp_path: Path, header: str, rows, name: str = "data.csv", **settings):
    source = write_text(tmp_path, name, header + "\n" + "\n".join(rows) + "\n")
    return scan(source, config=ScanConfig.model_validate(settings))


def _items(result: ScanResult, rule: str):
    assert result.observations is not None
    return [item for item in result.observations.items if item.rule == rule]


def _field_names(result: ScanResult) -> dict[str, str]:
    return {field.id: field.name for field in result.datasets[0].fields}


# Rules -------------------------------------------------------------------------


def test_records_excluded_by_the_tolerant_policy_are_a_confirmed_issue(tmp_path):
    source = write_text(
        tmp_path, "lines.jsonl", '{"a": 1}\nnot json\n{"a": 2}\n{"a": 3}\n'
    )

    result = scan(source)

    [item] = _items(result, "excluded_records")
    assert (item.status, item.category) == ("confirmed_issue", "records")
    assert (item.count, item.of, item.dataset, item.field) == (1, 4, None, None)
    assert item.diagnostics
    assert all(
        result.diagnostics[index].code == "jsonl_invalid_line" for index in item.diagnostics
    )
    assert result.status == "partial"
    assert check_scan(result) == []


def test_blank_and_repeated_column_names_are_a_confirmed_issue(tmp_path):
    result = _scan(tmp_path, "a,,a", ["1,2,3", "4,5,6"])

    names = _field_names(result)
    found = {
        names[item.field]: item.count for item in _items(result, "ambiguous_header")
    }

    assert found == {"a": 2, "": 1}
    assert {item.status for item in _items(result, "ambiguous_header")} == {
        "confirmed_issue"
    }


def test_a_column_without_a_dominant_type_is_mixed(tmp_path):
    rows = [f"{index}" if index % 2 else f"word{index}" for index in range(100)]
    result = _scan(tmp_path, "v", rows)

    [item] = _items(result, "mixed_types")

    assert (item.status, item.population, item.of) == (
        "candidate_anomaly",
        "occurrences",
        100,
    )
    assert item.count == 50
    assert not _items(result, "type_outliers")


def test_a_few_values_outside_a_clear_type_are_outliers(tmp_path):
    rows = [str(index) for index in range(100)] + ["oops", "n/a", "??"]
    result = _scan(tmp_path, "v", rows)

    [item] = _items(result, "type_outliers")

    assert (item.count, item.of) == (3, 103)
    assert not _items(result, "mixed_types")


def test_a_text_column_is_never_an_outlier_report(tmp_path):
    rows = [f"name {index}" for index in range(100)] + ["2024"]

    assert not _items(_scan(tmp_path, "v", rows), "type_outliers")


def test_dates_that_read_in_two_orders_are_ambiguous(tmp_path):
    rows = [f"{day:02d}/{month:02d}/2021" for day in (1, 2, 3) for month in (4, 5, 6)]
    result = _scan(tmp_path, "d", rows)

    [item] = _items(result, "ambiguous_dates")

    assert item.status == "candidate_anomaly"
    assert 0 < item.count <= item.of


def test_empty_and_constant_columns_are_remarks(tmp_path):
    result = _scan(tmp_path, "id,flag,nothing", [f"{i},yes," for i in range(20)])
    names = _field_names(result)

    [constant] = _items(result, "constant_column")
    [empty] = _items(result, "empty_column")

    assert names[constant.field] == "flag"
    assert (constant.status, constant.count, constant.of) == ("informational", 20, 20)
    assert names[empty.field] == "nothing"
    # An empty column is not also reported as missing values.
    assert [names[item.field] for item in _items(result, "missing_values")] == []


def test_a_single_record_is_not_a_constant_column(tmp_path):
    assert not _items(_scan(tmp_path, "a,b", ["1,2"]), "constant_column")


def test_whitespace_changes_are_remarks_over_the_content_strings(tmp_path):
    result = _scan(
        tmp_path, "v", ['" a"', '"b "', '"c  d"', "e", "f", "g", "h", "i"]
    )

    [trimmed] = _items(result, "trimmed_cells")
    [collapsed] = _items(result, "collapsed_whitespace")

    assert (trimmed.count, trimmed.of, trimmed.population) == (2, 8, "content_strings")
    assert (collapsed.count, collapsed.of) == (1, 8)
    assert {trimmed.status, collapsed.status} == {"informational"}


def test_spellings_that_normalization_compares_as_equal_form_groups(tmp_path):
    result = _scan(tmp_path, "city", ["Paris", "paris", "PARIS", "Lyon", "lyon", "Nice"])

    [item] = _items(result, "variant_groups")

    assert (item.count, item.population, item.status) == (
        2,
        "groups",
        "candidate_anomaly",
    )


def test_a_rare_structure_next_to_a_dominant_one_is_a_candidate_anomaly(tmp_path):
    common = [f"AB{index:04d}" for index in range(190)]
    rare = ["x-1", "y-2", "z-3", "w-4"]
    result = _scan(tmp_path, "id", [*common, *rare])

    [item] = _items(result, "minority_pattern")

    assert (item.status, item.population, item.accuracy) == (
        "candidate_anomaly",
        "distinct_values",
        "exact",
    )
    assert (item.count, item.of) == (4, 194)
    assert item.patterns and not item.limited_by


def test_a_minority_found_in_a_sample_says_so(tmp_path):
    common = [f"AB{index:04d}" for index in range(1_500)]
    # The strata by length keep the rare lengths whole: few values, or the
    # sample of distinct values would make them more than a twentieth.
    rare = [f"{chr(97 + index)}-{index}" for index in range(8)]
    result = _scan(tmp_path, "id", [*common, *rare], limits={"max_samples": 300})

    [item] = _items(result, "minority_pattern")

    assert item.accuracy == "sample"


def test_a_balanced_column_has_no_minority_pattern(tmp_path):
    rows = [f"AB{index:04d}" for index in range(50)] + [
        f"x-{index}" for index in range(50)
    ]

    assert not _items(_scan(tmp_path, "id", rows), "minority_pattern")


# Limits ------------------------------------------------------------------------


def test_the_limits_name_what_was_cut_and_why(tmp_path):
    rows = [f"user{index}@example.com" for index in range(60)]
    result = _scan(tmp_path, "email", rows, limits={"max_distinct_per_field": 20})
    assert result.observations is not None

    limits = {
        (limit.field, limit.measure, limit.reason)
        for limit in result.observations.limits
    }

    column = result.datasets[0].fields[0].id
    assert (column, "values.cardinality", "distinct_limit") in limits
    assert (column, "values.samples", "exposure") in limits


def test_a_failed_pattern_inference_is_a_limit_with_its_diagnostic(tmp_path, monkeypatch):
    from tabalyst.scanner import patterninfer

    monkeypatch.setattr(
        patterninfer, "_infer", lambda *args: (_ for _ in ()).throw(KeyError("x"))
    )
    result = _scan(tmp_path, "id", [f"ID-{i:03d}" for i in range(40)])
    assert result.observations is not None

    [limit] = [item for item in result.observations.limits if item.measure == "derived.patterns"]

    assert limit.reason == "inference_error"
    assert result.diagnostics[limit.diagnostic].code == "pattern_inference_failed"
    assert check_scan(result) == []


# Bounds, switches, failure -----------------------------------------------------


def test_the_listing_is_bounded_and_the_summaries_keep_counting():
    result = scan(
        EXAMPLES / "insurance-customers.csv",
        config=ScanConfig.model_validate({"observations": {"max_items": 5}}),
    )
    full = scan(EXAMPLES / "insurance-customers.csv")
    assert result.observations is not None and full.observations is not None

    assert len(result.observations.items) == 5
    # Columns that are not eligible for patterns no longer reach their budget,
    # so the file may list fewer limits than the bound.
    assert len(result.observations.limits) == min(5, len(full.observations.limits))
    assert result.observations.truncated is True
    assert full.observations.truncated is False
    assert result.observations.summary == full.observations.summary
    assert result.observations.items == [
        item.model_copy(update={"id": f"o{number}"})
        for number, item in enumerate(full.observations.items[:5], 1)
    ]
    assert check_scan(result) == []


def test_observations_can_be_turned_off(tmp_path):
    source = write_text(tmp_path, "data.csv", "a\n1\n")
    config = ScanConfig.model_validate({"observations": {"enabled": False}})

    result = scan(source, config=config)

    assert result.observations is None
    assert "observations" not in result.model_dump(mode="json")
    assert check_scan(result) == []
    assert result.config_sha256 != scan(source).config_sha256


def test_observations_that_raise_do_not_lose_the_scan(tmp_path, monkeypatch):
    def failing(**kwargs):
        raise ValueError("secret-value-123")

    monkeypatch.setattr(scanner_api, "build_observations", failing)
    source = write_text(tmp_path, "data.csv", "a\n1\n2\n")

    result = scan(source)

    assert result.observations is None
    [diagnostic] = [d for d in result.diagnostics if d.code == "observations_failed"]
    assert diagnostic.level == "error"
    assert "ValueError" in diagnostic.message
    assert "secret-value-123" not in diagnostic.message
    assert result.status == "complete"
    assert result.datasets[0].fields
    assert check_scan(result) == []


def test_the_result_does_not_depend_on_the_number_of_workers():
    source = EXAMPLES / "insurance-customers.csv"

    single = scan(source, workers=1)
    several = scan(source, workers=2)

    assert single.observations == several.observations
    assert single.observations is not None


def test_the_observations_are_deterministic(tmp_path):
    rows = [f"{index % 7},{index}" for index in range(300)]

    first = _scan(tmp_path, "a,b", rows)
    second = _scan(tmp_path, "a,b", rows)

    assert first.observations == second.observations


def test_no_observation_carries_a_value():
    result = scan(EXAMPLES / "insurance-customers.csv")
    assert result.observations is not None
    text = result.observations.model_dump_json()
    values = {
        entry.value
        for dataset in result.datasets
        for field in dataset.fields
        for entry in field.values.samples.listed[:20]
        if len(entry.value) > 6
    }

    assert values
    assert not any(value in text for value in values)


def test_the_observations_time_counts_in_the_derived_part_of_the_run(tmp_path):
    result = _scan(tmp_path, "a", ["1", "2"])

    timings = result.run.timings

    assert timings.derived > 0
    assert abs(sum(timings.model_dump().values()) - result.run.duration_seconds) < 1e-3


# Document, schema, validator ----------------------------------------------------


def test_a_scan_with_observations_is_valid_and_reads_back_identical():
    result = scan(EXAMPLES / "insurance-customers.csv")

    assert check_scan(result) == []
    document = json.loads(json.dumps(result.model_dump(mode="json", by_alias=True)))
    again = scan_from_document(document, "memory")

    assert again.observations == result.observations
    assert check_scan(again) == []


def test_the_schema_accepts_the_observations_and_rejects_a_damaged_block():
    jsonschema = pytest.importorskip("jsonschema")
    from tabalyst.scanner.schema import scan_schema

    validator = jsonschema.Draft202012Validator(scan_schema())
    document = scan(EXAMPLES / "insurance-customers.csv").model_dump(mode="json")

    validator.validate(document)
    document["observations"]["items"][0]["status"] = "doubtful"
    assert not validator.is_valid(document)


def _damaged(mutate) -> list[str]:
    document = scan(EXAMPLES / "insurance-customers.csv").model_dump(mode="json")
    mutate(document["observations"])
    return check_scan(ScanResult.model_validate(document))


def _first(block: dict, rule: str) -> dict:
    return next(item for item in block["items"] if item["rule"] == rule)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b.update(version=9),
        lambda b: b["summary"].update(has_quality_issues=False),
        lambda b: b["datasets"][0].update(has_limits=False),
        lambda b: b["summary"].update(informational=b["summary"]["informational"] + 1),
        lambda b: b.update(truncated=True),
        lambda b: b["items"][0].update(id="o9"),
        lambda b: b["items"].reverse(),
        lambda b: b["items"][0].update(rule="invented"),
        lambda b: b["items"][0].update(status="confirmed_issue"),
        lambda b: b["items"][0].update(field="column_999"),
        lambda b: b["items"][0].update(dataset="nowhere"),
        lambda b: b["items"][0].update(count=0),
        lambda b: b["items"][0].update(limited_by=["l999"]),
        lambda b: _first(b, "duplicate_rows").update(count=2),
        lambda b: _first(b, "missing_values").update(count=1),
        lambda b: _first(b, "trimmed_cells" if any(i["rule"] == "trimmed_cells" for i in b["items"]) else "collapsed_whitespace").update(count=1),
        lambda b: _first(b, "minority_pattern").update(patterns=["p99"]),
        lambda b: b["limits"][0].update(diagnostic=999),
        lambda b: b["limits"][0].update(dataset="nowhere"),
    ],
    ids=[
        "version",
        "flag",
        "dataset-flag",
        "summary",
        "truncated",
        "item-id",
        "order",
        "rule",
        "status",
        "field",
        "dataset",
        "count",
        "limited-by",
        "duplicates",
        "missing",
        "whitespace",
        "pattern",
        "limit-diagnostic",
        "limit-dataset",
    ],
)
def test_the_validator_catches_observations_that_do_not_reconcile(mutate):
    assert any(problem.startswith("observations") for problem in _damaged(mutate))


def test_the_validator_asks_for_the_block_unless_it_failed_or_is_off(tmp_path):
    result = _scan(tmp_path, "a", ["1"])
    bare = result.model_copy(update={"observations": None})

    assert any("missing although" in problem for problem in check_scan(bare))


def test_the_validator_catches_a_stage_that_takes_a_count_it_should_not():
    document = scan(EXAMPLES / "insurance-customers.csv").model_dump(mode="json")
    column = document["datasets"][0]["fields"][3]
    trim = next(s for s in column["normalization"]["stages"] if s["stage"] == "trim")
    trim["changed"] = 3
    trim["equals"] = "nfc"

    problems = check_scan(ScanResult.model_validate(document))

    assert any("normalization.stages[trim]" in problem for problem in problems)


def test_the_validator_catches_a_stage_that_forgot_to_take_the_count(tmp_path):
    document = _scan(tmp_path, "v", ["a", "b"]).model_dump(mode="json")
    stage = document["datasets"][0]["fields"][0]["normalization"]["stages"][1]
    del stage["equals"]

    problems = check_scan(ScanResult.model_validate(document))

    assert any("equals goes with a stage that changed nothing" in p for p in problems)


# Facts and Report -------------------------------------------------------------


def test_the_facts_hash_ignores_the_observations():
    result = scan(EXAMPLES / "insurance-customers.csv")
    bare = result.model_copy(update={"observations": None})

    assert facts_sha256(result) == facts_sha256(bare)


def test_a_report_carries_the_observations_of_its_scan():
    result = scan(EXAMPLES / "insurance-customers.csv")
    profile = build_profile(result, ReportConfig(scan=result.config))

    assert profile.observations == result.observations
    assert base_of(profile).observations == result.observations
    document = json.loads(profile.model_dump_json(by_alias=True))
    assert document["observations"]["version"] == 2
    assert check_scan(base_of(profile)) == []


def test_the_rules_of_version_2_are_these():
    # A rule added or removed changes the version of the rules (design 18.13).
    assert set(RULES) == {
        "excluded_records",
        "ambiguous_header",
        "duplicate_rows",
        "mixed_types",
        "type_outliers",
        "ambiguous_dates",
        "variant_groups",
        "minority_pattern",
        "minority_length",
        "missing_values",
        "empty_column",
        "constant_column",
        "trimmed_cells",
        "collapsed_whitespace",
    }
