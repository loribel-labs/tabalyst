# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Errors of a column from the Scan's existing facts (Report overview lot R6a).

The contract is ``docs/dev/report/summary-table.md`` 6.6 and 6.8. The checks are
run through ``column_findings`` on the views of real scans; the cases a scan
cannot make (a failed detector, a detector that tested part of the values) edit
the detector of the view.
"""

import pytest
from scan_helpers import write_json, write_text

from tabalyst import analyze_csv
from tabalyst.report_config import ReportConfig
from tabalyst.report_findings import CHECKS, column_findings
from tabalyst.reporting import dataset_views
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.classify.catalog import FINDINGS
from tabalyst.scanner.models import DetectorDisabled, DetectorFailed


def _views(source, **settings):
    config = ReportConfig(scan=ScanConfig.model_validate(settings))
    return dataset_views(analyze_csv(source, config))[0].columns


def _csv(tmp_path, header, cells, **settings):
    """The view of the first column of a CSV; a second column of row numbers lets
    the first one hold empty cells."""
    lines = [f"{header},row"] + [f"{value},{n}" for n, value in enumerate(cells)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    return _views(source, **settings)[0]


def _with_detector_result(column, result):
    """The view with the detector of ``result`` replaced by it."""
    detectors = [
        result if item.id == result.id else item for item in column.field.detectors
    ]
    field = column.field.model_copy(update={"detectors": detectors})
    return column.model_copy(update={"field": field})


def _with_coverage(column, detector_id, **coverage):
    """The view with the coverage of one detector changed."""
    detector = next(item for item in column.field.detectors if item.id == detector_id)
    changed = detector.coverage.model_copy(update=coverage)
    return _with_detector_result(
        column, detector.model_copy(update={"coverage": changed})
    )


def _errors(column):
    return {item.code: item for item in column_findings(column).errors.items}


# One column per semantic detector: 300 valid values, one with the shape of the
# type that fails its syntax and one that does not have the shape (both Errors).
# The audit of 6.8.
SEMANTIC = [
    ("email", "abc@x.org", "a b@x.org", "bad address"),
    ("phone", "(514) 555-1234", "(014) 555-1234", "call me"),
    ("postal_code", "K1A 0B1", "D1A 0B1", "hello"),
    ("url", "https://example.org/a", "http://exa mple.org", "not a url"),
    ("ip_address", "192.168.1.1", "999.1.1.1", "hello"),
    (
        "uuid",
        "123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-12d3-a456-42661417400g",
        "hello",
    ),
]


@pytest.mark.parametrize(("detector", "valid", "invalid", "other"), SEMANTIC)
def test_a_value_that_fails_the_shape_or_the_syntax_of_an_established_type_is_an_error(
    tmp_path, detector, valid, invalid, other
):
    column = _csv(tmp_path, detector, [valid] * 300 + [invalid, other])

    errors = _errors(column)

    assert column.classification.state == "established"
    assert set(errors) == {"semantic.invalid"}
    error = errors["semantic.invalid"]
    assert (error.cls, error.count, error.unit) == ("error", 2, "occurrences")
    assert error.basis == [detector]
    assert error.population.kind == "eligible_values"
    assert error.accuracy == "exact"
    assert error.share.denominator == error.population.size == 302


def test_invalid_values_are_counted_by_occurrence_out_of_the_eligible_values(
    tmp_path,
):
    column = _csv(tmp_path, "email", ["abc@x.org"] * 300 + ["a b@x.org"] * 4)

    error = _errors(column)["semantic.invalid"]

    assert error.count == 4
    assert error.population.size == 304
    assert round(error.share.percent, 2) == round(400 / 304, 2)


def test_a_value_without_the_shape_of_an_established_type_is_an_error(tmp_path):
    column = _csv(tmp_path, "zone", ["K1A 0B1"] * 30 + ["hello"])

    error = _errors(column)["semantic.invalid"]

    assert column.classification.type == "postal_code"
    assert error.count == 1
    assert error.population.size == 31


def test_CA13_a_value_a_date_detector_does_not_recognize_is_not_an_error(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 300 + ["hello"])

    assert not column_findings(column).errors.items


def test_CA11_an_impossible_date_is_an_error_and_an_ambiguous_one_is_not(tmp_path):
    column = _csv(
        tmp_path, "signed", ["2025-01-15"] * 30 + ["2025-02-30", "03/04/2025"]
    )

    errors = _errors(column)

    assert column.classification.family == "temporal"
    assert set(errors) == {"temporal.invalid_calendar"}
    assert errors["temporal.invalid_calendar"].count == 1
    assert errors["temporal.invalid_calendar"].basis == ["date"]


@pytest.mark.parametrize(
    "value",
    ["2025-02-30", "2025-13-45", "2025-01-15 25:00", "2025/01-15", "31/02/2025"],
)
def test_every_invalid_reason_of_the_date_detector_is_counted(tmp_path, value):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 300 + [value])

    assert _errors(column)["temporal.invalid_calendar"].count == 1


def test_a_text_that_is_not_date_shaped_is_not_an_invalid_date(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 300 + ["hello"])

    assert "temporal.invalid_calendar" not in _errors(column)


def test_invalid_dates_of_a_datetime_field_are_errors_too(tmp_path):
    column = _csv(
        tmp_path,
        "created",
        ["2025-01-15 10:00:00"] * 300 + ["2025-02-30 10:00:00"],
    )

    assert column.classification.type == "datetime"
    assert _errors(column)["temporal.invalid_calendar"].count == 1


def test_values_outside_an_integer_are_an_error(tmp_path):
    column = _csv(tmp_path, "quantity", [str(n) for n in range(300)] + ["abc", "12x"])

    error = _errors(column)["type.outside_family"]

    assert column.classification.type == "integer"
    assert (error.count, error.unit) == (2, "occurrences")
    assert error.population.kind == "present_values"
    assert error.population.size == 302
    assert error.basis == ["technical_type"]


def test_values_outside_a_number_are_an_error(tmp_path):
    column = _csv(tmp_path, "weight", [f"{n}.5" for n in range(300)] + ["abc"])

    assert column.classification.type == "number"
    assert _errors(column)["type.outside_family"].count == 1


def test_a_clean_numeric_field_has_no_error_and_the_check_completed(tmp_path):
    column = _csv(tmp_path, "quantity", [str(n) for n in range(300)])

    findings = column_findings(column)

    assert not findings.errors.items
    states = {item.code: item.state for item in findings.errors.assessments}
    assert states["type.outside_family"] == "none_detected"


def test_a_yes_in_a_boolean_field_is_not_outside_its_family(tmp_path):
    column = _csv(tmp_path, "active", ["true", "false"] * 150 + ["yes"])

    assert column.classification.type == "boolean"
    assert "type.outside_family" not in _errors(column)


def test_a_datetime_in_a_date_field_is_not_outside_its_family(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 300 + ["2025-01-15 10:00:00"])

    assert column.classification.family == "temporal"
    assert column.field.technical_type.outside_count == 1
    assert not _errors(column)


def test_text_has_no_family_to_be_outside_of(tmp_path):
    column = _csv(tmp_path, "note", ["alpha", "beta", "gamma"] * 100 + ["12"])

    findings = column_findings(column)

    assert not findings.errors.items
    assert findings.errors.state == "not_applicable"


def test_CA12_a_name_alone_never_produces_an_error(tmp_path):
    # The name says email and every value has the shape of a bad address, but the
    # values are too few to establish the type: the name creates nothing.
    values = ["a b@x.org"] * 10 + ["bad address"] * 20
    column = _csv(tmp_path, "courriel", values)

    findings = column_findings(column)

    assert column.classification.type != "email"
    assert not findings.errors.items
    assert not any(item.cls == "error" for item in findings.issues.items)


def test_decimals_in_an_integer_field_are_numbers_not_values_outside_it(tmp_path):
    column = _csv(
        tmp_path, "quantity", [str(n) for n in range(300)] + ["12.5", "13.5", "abc"]
    )

    error = _errors(column)["type.outside_family"]

    assert column.classification.type == "integer"
    assert error.count == 1


def test_an_error_on_a_candidate_classification_is_an_issue(tmp_path):
    # The name of a field can make its type a candidate (a name that breaks a tie
    # between two types the values support): the facts of the type are then an Issue.
    column = _csv(tmp_path, "email", ["abc@x.org"] * 300 + ["a b@x.org"])
    candidate = column.model_copy(
        update={
            "classification": column.classification.model_copy(
                update={"state": "candidate"}
            )
        }
    )

    findings = column_findings(candidate)

    assert candidate.classification.type == "email"
    assert not findings.errors.items
    assert [(i.code, i.cls, i.count) for i in findings.issues.items] == [
        ("semantic.invalid", "issue", 1)
    ]
    assert findings.errors.state == "none_detected"


def test_an_undetermined_integer_with_outside_values_is_an_issue(tmp_path):
    column = _csv(tmp_path, "value", [str(10000 + n) for n in range(300)] + ["abc"])

    findings = column_findings(column)

    assert column.classification.state == "undetermined"
    assert not findings.errors.items
    # The Issues of the other rules (R6b) are about other facts of the column.
    assert [
        (i.code, i.cls)
        for i in findings.issues.items
        if i.code == "type.outside_family"
    ] == [("type.outside_family", "issue")]


def test_an_identifier_candidate_is_never_an_error(tmp_path):
    values = [f"C{n:05d}" for n in range(300)] + ["C00001"]
    column = _csv(tmp_path, "customer_id", values)

    findings = column_findings(column)

    assert column.classification.family == "identifier"
    assert column.classification.state == "candidate"
    assert not findings.errors.items


def test_CA30_a_failed_detector_is_never_counted_as_invalid(tmp_path):
    column = _csv(tmp_path, "email", ["abc@x.org"] * 300 + ["a b@x.org"])
    failed = DetectorFailed(id="email", version=2, reason="boom", diagnostic=3)
    broken = _with_detector_result(column, failed)

    findings = column_findings(broken)

    assert not findings.errors.items
    assert findings.errors.state == "failed"
    assessment = next(
        item for item in findings.errors.assessments if item.code == "semantic.invalid"
    )
    assert (assessment.state, assessment.reason) == ("failed", "boom")


def test_a_failed_date_detector_is_not_a_calendar_error(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 300 + ["2025-02-30"])
    failed = DetectorFailed(id="date", version=1, reason="boom", diagnostic=3)
    broken = _with_detector_result(column, failed)

    findings = column_findings(broken)

    assert not findings.errors.items
    assert findings.errors.state == "failed"


def test_a_disabled_detector_leaves_the_error_not_assessed(tmp_path):
    column = _csv(tmp_path, "email", ["abc@x.org"] * 300 + ["a b@x.org"])
    disabled = DetectorDisabled(id="email", version=2)

    findings = column_findings(_with_detector_result(column, disabled))

    assert not findings.errors.items
    assert findings.errors.state == "not_assessed"


def test_CA17_a_detector_that_tested_100_of_1000_values_is_partially_assessed(
    tmp_path,
):
    column = _csv(tmp_path, "email", ["abc@x.org"] * 300 + ["a b@x.org"])
    partial = _with_coverage(
        column,
        "email",
        eligible=1000,
        tested=100,
        matched=100,
        invalid=0,
        not_matched=0,
        not_tested=900,
    )

    findings = column_findings(partial)

    assert not findings.errors.items
    assert findings.errors.state == "partial"
    assessment = next(
        item for item in findings.errors.assessments if item.code == "semantic.invalid"
    )
    assert (assessment.eligible, assessment.tested) == (1000, 100)


def test_a_detector_that_tested_part_of_the_values_gives_a_lower_bound(tmp_path):
    column = _csv(tmp_path, "email", ["abc@x.org"] * 300 + ["a b@x.org"])
    partial = _with_coverage(
        column,
        "email",
        eligible=1000,
        tested=100,
        matched=98,
        invalid=2,
        not_matched=0,
        not_tested=900,
    )

    error = _errors(partial)["semantic.invalid"]

    assert error.count == 2
    assert error.accuracy == "lower_bound"
    assert error.share.accuracy == "lower_bound"
    assert error.share.denominator == 1000


def test_CA21_the_invalid_values_of_a_repeated_json_field_are_occurrences(tmp_path):
    records = [{"emails": ["a@x.org", "b@x.org", "c@x.org"]} for _ in range(100)]
    records[0]["emails"].append("a b@x.org")
    records[1]["emails"].append("c d@x.org")
    columns = _views(write_json(tmp_path, "data.json", records))
    column = next(item for item in columns if item.path == "emails[]")

    error = _errors(column)["semantic.invalid"]

    assert error.unit == "occurrences"
    assert error.count == 2
    assert error.population.size == 302


def test_the_three_error_codes_of_the_catalogue_each_have_their_check():
    errors = {
        entry.code
        for entry in FINDINGS
        if entry.cls == "error" and entry.status == "active"
    }

    assert errors == {
        "temporal.invalid_calendar",
        "semantic.invalid",
        "type.outside_family",
    }
    assert errors <= set(CHECKS)
