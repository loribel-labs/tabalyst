# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Classification foundation (Report overview lot R1a): fallback of the technical
type, the Text bounds as a scan setting, and the version of the rules."""

import json

import pytest
from pydantic import ValidationError
from scan_helpers import field, run_scan, write_text

from tabalyst.config import PresentationSettings
from tabalyst.errors import ConfigurationError
from tabalyst.report_config import ReportConfig, check_length_distribution
from tabalyst.scan_reuse import engine_warning
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.classify import classification_versions, version_record
from tabalyst.scanner.classify.catalog import FAMILIES, is_catalogued


def _classification(tmp_path, header, values):
    source = write_text(tmp_path, "data.csv", "\n".join([header, *values]) + "\n")
    return field(run_scan(source)["datasets"][0], header)["classification"]


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["1", "2", "3"], ("numeric", "integer")),
        (["1.5", "2.5", "3.25"], ("numeric", "number")),
        (["true", "false", "true"], ("categorical", "boolean")),
        (["2024-01-15", "2024-02-20", "2024-03-31"], ("temporal", "date")),
    ],
)
def test_a_technical_type_without_detector_gives_its_fallback_type(
    tmp_path, values, expected
):
    classification = _classification(tmp_path, "value", values)

    assert (classification["family"], classification["type"]) == expected
    assert classification["basis"] == "fallback"
    assert classification["state"] == "established"
    assert classification["evidence"][0]["source"] == "technical_type"


def test_a_mixed_column_is_other_mixed(tmp_path):
    values = ["1", "alpha", "2024-01-15", "true"] * 5

    classification = _classification(tmp_path, "value", values)

    assert (classification["family"], classification["type"]) == ("other", "mixed")


def test_a_text_cites_the_median_as_its_evidence(tmp_path):
    classification = _classification(tmp_path, "word", ["alpha", "beta", "gamma"])

    assert classification["basis"] == "inferred"
    assert [item["id"] for item in classification["evidence"]] == [
        "text",
        "string_lengths.median_length",
    ]
    scope = classification["evidence"][1]["scope"]
    assert scope == {
        "population": "present_values",
        "of": 3,
        "partial": False,
        "accuracy": "exact",
    }


def test_every_family_code_and_type_code_is_unique_and_catalogued():
    pairs = [(family.code, code) for family in FAMILIES for code in family.types]

    assert len(pairs) == len(set(pairs))
    assert all(is_catalogued(*pair) for pair in pairs)
    assert not is_catalogued("text", "banana")


def test_a_classification_outside_the_catalogue_is_refused():
    from tabalyst.scanner.classify.models import Classification

    with pytest.raises(ValidationError, match="catalogue"):
        Classification(
            family="text",
            type="banana",
            basis="fallback",
            state="undetermined",
            traits=[],
            evidence=[],
            alternatives=[],
            rule_version=1,
        )


@pytest.mark.parametrize(
    "bounds",
    [
        {"very_short_max_length": 20},
        {"short_max_length": 5},
        {"medium_max_length": 255},
        {"very_short_max_length": 0},
    ],
)
def test_the_text_bounds_must_increase_and_be_positive(bounds):
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"classification": bounds})


def test_the_text_bounds_are_recorded_in_the_scan_configuration(tmp_path):
    result = run_scan(
        write_text(tmp_path, "data.csv", "note\nalpha\n"),
        classification={"long_max_length": 300},
    )

    assert result["config"]["classification"]["long_max_length"] == 300


def test_the_string_analysis_class_follows_the_scan_bounds(tmp_path):
    from tabalyst.report_profile import build_string_profile

    lines = ["note", *["x" * 30] * 4]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    result = scan(
        source,
        config=ScanConfig.model_validate(
            {"classification": {"short_max_length": 40, "medium_max_length": 60}}
        ),
    )

    profile = build_string_profile(
        result.datasets[0].fields[0], "text", ReportConfig(scan=result.config)
    )

    # Medium by default, Short with the wider bound of the scan.
    assert profile is not None and profile.status == "short"


def test_a_length_distribution_beyond_the_medium_bound_is_refused():
    scan_config = ScanConfig.model_validate(
        {"classification": {"short_max_length": 10, "medium_max_length": 30}}
    )

    with pytest.raises(ConfigurationError, match="medium_max_length"):
        ReportConfig.from_presentation(PresentationSettings(), scan_config)
    with pytest.raises(ConfigurationError, match="medium_max_length"):
        check_length_distribution(PresentationSettings(), scan_config)
    ReportConfig.from_presentation(
        PresentationSettings.model_validate(
            {"string_analysis": {"length_distribution_max_length": 30}}
        ),
        scan_config,
    )


def test_the_scan_records_the_version_of_the_rules_and_warns_when_it_differs(
    tmp_path,
):
    source = write_text(tmp_path, "data.csv", "note\nalpha\n")
    result = scan(source)

    assert result.engine.classification == version_record()
    assert engine_warning(result) is None

    older = result.model_copy(
        update={"engine": result.engine.model_copy(update={"classification": {}})}
    )
    warning = engine_warning(older)
    assert warning is not None and "classif" in warning


def test_the_versions_of_the_rules_are_read_through_a_function(monkeypatch):
    from tabalyst.scanner.classify import rules

    assert classification_versions() == (
        rules.CATALOGUE_VERSION,
        rules.NAME_RULES_VERSION,
    )
    monkeypatch.setattr(rules, "CATALOGUE_VERSION", rules.CATALOGUE_VERSION + 1)
    monkeypatch.setattr(rules, "NAME_RULES_VERSION", rules.NAME_RULES_VERSION + 1)
    assert classification_versions() == (
        rules.CATALOGUE_VERSION,
        rules.NAME_RULES_VERSION,
    )


def test_a_json_container_field_has_no_present_value_and_is_other_empty(tmp_path):
    source = write_text(
        tmp_path, "data.json", json.dumps([{"order": {"n": 1}}, {"order": {"n": 2}}])
    )

    result = run_scan(source)
    types = {
        item["display"]: (
            item["classification"]["family"],
            item["classification"]["type"],
        )
        for item in result["datasets"][0]["fields"]
    }

    assert types["order"] == ("other", "empty")
    assert types["order.n"] == ("numeric", "integer")
