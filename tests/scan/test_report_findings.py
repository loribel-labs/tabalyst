# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Findings of a column: Missing, the evaluation states, populations and shares
(Report overview lot R5).

The contract is ``docs/dev/report/summary-table.md`` 6. The Errors and Issues
builders come with lots R6a and R6b; here the machinery is tested with checks
written for the test, and with the facts of real scans.
"""

import json

import pytest
from scan_helpers import write_json, write_text

from tabalyst import analyze_csv
from tabalyst.models import ColumnProfile
from tabalyst.report_config import ReportConfig
from tabalyst.report_findings import (
    CHECKS,
    Assessment,
    CheckResult,
    Finding,
    Population,
    assess_detector,
    column_findings,
    detector_of,
    evaluation_state,
    finding_from_observation,
    label_for,
    list_state,
    merge_proven,
    missing_finding,
    records_overlap,
    repetition_figures,
    repetition_from_counts,
    share,
)
from tabalyst.report_labels import (
    ASSESSMENT_LABELS,
    FINDING_NOUNS,
    plural,
    population_phrase,
)
from tabalyst.reporting import dataset_views
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.classify.catalog import FINDING_CODES, FINDINGS
from tabalyst.scanner.models import (
    DetectorDisabled,
    DetectorFailed,
    DetectorNotApplicable,
    Observation,
)


def _views(source, **settings):
    config = ReportConfig(scan=ScanConfig.model_validate(settings))
    return dataset_views(analyze_csv(source, config))[0].columns


def _csv(tmp_path, header, cells, **settings):
    """The views of a CSV whose first column is ``header``. A second column of row
    numbers lets the first one hold empty cells."""
    lines = [f"{header},row"] + [f"{value},{n}" for n, value in enumerate(cells)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    return _views(source, **settings)[0]


def _json(tmp_path, records, **settings):
    return _views(write_json(tmp_path, "data.json", records), **settings)


def _finding(code="pattern.minority", count=36, overlaps=(), cls="issue"):
    return Finding(
        code=code,
        cls=cls,
        field="f1",
        count=count,
        unit="occurrences",
        population=Population(kind="content_strings", size=100),
        accuracy="exact",
        overlaps=list(overlaps),
    )


def _observation(**changes):
    values = {
        "id": "o1",
        "rule": "minority_length",
        "category": "patterns",
        "status": "candidate_anomaly",
        "field": "f1",
        "population": "content_strings",
        "count": 3,
        "of": 100,
        "accuracy": "exact",
    }
    return Observation(**{**values, **changes})


# --- Missing ---------------------------------------------------------------------


def test_missing_counts_the_five_components_apart(tmp_path):
    records = (
        [{"a": "x", "b": 1}] * 10
        + [{"b": 2}] * 2  # absent
        + [{"a": None, "b": 3}] * 3  # null
        + [{"a": "", "b": 4}] * 4  # empty
        + [{"a": "  ", "b": 5}] * 5  # blank
        + [{"a": "N/A", "b": 6}] * 6  # marker
    )

    columns = _json(tmp_path, records, values={"null_markers": ["N/A"]})
    missing = missing_finding(columns[0])

    components = missing.components
    assert (components.absent, components.null, components.empty) == (2, 3, 4)
    assert (components.blank, components.marker) == (5, 6)
    assert missing.count == 2 + 3 + 4 + 5 + 6
    assert missing.population.size == len(records)
    assert missing.unit == "positions"
    assert missing.accuracy == "exact"
    assert missing.state == "detected"


def test_missing_share_is_the_percentage_of_the_column(tmp_path):
    column = _csv(tmp_path, "note", ["x"] * 3 + [""])

    missing = missing_finding(column)

    assert missing.share.percent == column.missing_percent == 25
    assert (missing.share.numerator, missing.share.denominator) == (1, 4)


def test_a_component_outside_the_definition_is_shown_but_not_counted(tmp_path):
    column = _csv(
        tmp_path,
        "note",
        ["x"] * 3 + ["", " "],
        values={"missing": ["empty"]},
    )

    missing = missing_finding(column)

    assert missing.definition == ["empty"]
    assert missing.count == 1
    assert missing.components.blank == 1


def test_a_column_without_missing_values_reports_none_detected(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])

    missing = missing_finding(column)

    assert missing.count == 0
    assert missing.share.percent == 0
    assert missing.state == "none_detected"


def test_an_all_missing_column_is_one_hundred_percent_missing(tmp_path):
    column = _csv(tmp_path, "note", ["", "", ""])

    missing = missing_finding(column)

    assert missing.share.percent == 100
    assert missing.state == "detected"


def test_missing_in_a_json_array_counts_occurrences_not_rows(tmp_path):
    records = [{"orders": [{"amount": 1}, {"amount": None}, {"amount": 3}]}]

    columns = _json(tmp_path, records)
    amount = next(column for column in columns if column.path == "orders[].amount")
    missing = missing_finding(amount)

    assert missing.unit == "occurrences"
    assert missing.count == 1
    assert missing.population.size == 3


def test_missing_is_never_an_error_or_an_issue(tmp_path):
    column = _csv(tmp_path, "note", ["x"] * 14 + [""] * 86)

    findings = column_findings(column)

    assert findings.missing.count == 86
    assert not findings.errors.items
    assert not findings.issues.items


# --- Evaluation states -------------------------------------------------------------


@pytest.mark.parametrize(
    ("detector_state", "eligible", "tested", "found", "expected"),
    [
        ("complete", 10, 10, 0, "none_detected"),
        ("complete", 1000, 100, 0, "partial"),
        ("complete", 10, 10, 2, "detected"),
        ("complete", 1000, 100, 2, "detected"),
        ("complete", 0, 0, 0, "not_applicable"),
        ("complete", 10, 0, 0, "not_assessed"),
        ("disabled", 0, 0, 0, "not_assessed"),
        ("not_applicable", 0, 0, 0, "not_applicable"),
        ("failed", 10, 10, 0, "failed"),
        ("failed", 10, 10, 4, "failed"),
    ],
)
def test_the_state_of_a_check_follows_its_detector_and_coverage(
    detector_state, eligible, tested, found, expected
):
    assert evaluation_state(detector_state, eligible, tested, found) == expected


def test_an_unknown_detector_state_is_refused():
    with pytest.raises(ValueError, match="Unknown detector state"):
        evaluation_state("sleeping", 1, 1, 0)


def test_the_five_states_have_their_visible_words():
    assert ASSESSMENT_LABELS == {
        "none_detected": "None detected",
        "not_assessed": "Not assessed",
        "partial": "Partially assessed",
        "not_applicable": "Not applicable",
        "failed": "Assessment failed",
    }


def test_a_real_detector_that_tested_everything_and_found_nothing(tmp_path):
    column = _csv(tmp_path, "courriel", ["a@b.org", "c@d.org", "e@f.org"])
    detector = detector_of(column.field, "email")

    assessment = assess_detector("semantic.invalid", detector, "invalid")

    assert assessment.state == "none_detected"
    assert assessment.accuracy == "exact"
    assert (assessment.eligible, assessment.tested) == (3, 3)


def test_a_real_detector_counts_its_invalid_values(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 20 + ["2025-02-30"])
    detector = detector_of(column.field, "date")

    assessment = assess_detector("temporal.invalid_calendar", detector, "invalid")

    assert detector.coverage.invalid == 1
    assert assessment.state == "detected"
    assert assessment.accuracy == "exact"


def test_an_unrecognized_value_is_not_an_invalid_one(tmp_path):
    column = _csv(tmp_path, "courriel", ["a@b.org"] * 20 + ["bad address"])
    detector = detector_of(column.field, "email")

    assessment = assess_detector("semantic.invalid", detector, "invalid")

    assert detector.coverage.not_matched == 1
    assert assessment.state == "none_detected"


def test_a_detector_that_tested_part_of_its_values_is_partial(tmp_path):
    column = _csv(tmp_path, "courriel", ["a@b.org", "c@d.org", "e@f.org"])
    detector = detector_of(column.field, "email")
    coverage = detector.coverage.model_copy(
        update={"eligible": 1000, "tested": 100, "not_tested": 900}
    )
    partial = detector.model_copy(update={"coverage": coverage})

    assessment = assess_detector("semantic.invalid", partial, "invalid")

    assert assessment.state == "partial"
    assert assessment.accuracy == "lower_bound"
    assert (assessment.eligible, assessment.tested) == (1000, 100)


def test_a_failed_detector_is_a_failure_whatever_it_counted():
    failed = DetectorFailed(id="email", version=1, reason="boom", diagnostic=3)

    assessment = assess_detector("semantic.invalid", failed, "invalid")

    assert assessment.state == "failed"
    assert assessment.reason == "boom"
    assert assessment.accuracy == "unavailable"


def test_a_disabled_detector_is_not_assessed_and_stays_apart_from_a_failed_one():
    disabled = DetectorDisabled(id="email", version=1)
    inapplicable = DetectorNotApplicable(id="email", version=1, reason="no_text")

    states = {
        assess_detector("semantic.invalid", disabled, "invalid").state,
        assess_detector("semantic.invalid", inapplicable, "invalid").state,
    }

    assert states == {"not_assessed", "not_applicable"}


def test_a_missing_detector_is_none(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y"])

    assert detector_of(column.field, "no_such_detector") is None


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        ([], "not_applicable"),
        (["not_applicable", "not_applicable"], "not_applicable"),
        (["none_detected", "none_detected"], "none_detected"),
        (["not_assessed", "not_assessed"], "not_assessed"),
        (["failed", "failed"], "failed"),
        (["none_detected", "not_assessed"], "partial"),
        (["none_detected", "failed"], "partial"),
        (["partial", "not_assessed"], "partial"),
        (["failed", "not_assessed"], "failed"),
        (["none_detected", "not_applicable"], "none_detected"),
    ],
)
def test_the_state_of_a_list_without_findings_follows_the_checks_behind_it(
    states, expected
):
    assessments = [
        Assessment(code=f"c{n}", state=state) for n, state in enumerate(states)
    ]

    assert list_state([], assessments) == expected


def test_a_list_with_findings_is_detected_whatever_else_failed():
    assessments = [Assessment(code="c", state="failed")]

    assert list_state([_finding()], assessments) == "detected"


# --- Errors and Issues lists -------------------------------------------------------


def _active(*classes):
    return [
        entry for entry in FINDINGS if entry.status == "active" and entry.cls in classes
    ]


def _all_clear():
    """A check for every active Error and Issue that completes with nothing found."""
    return {
        entry.code: (
            lambda column, code=entry.code: CheckResult(
                assessment=Assessment(
                    code=code, state="none_detected", accuracy="exact"
                )
            )
        )
        for entry in _active("error", "issue")
    }


def test_with_no_check_delivered_the_lists_are_not_assessed(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])

    findings = column_findings(column, {})

    assert findings.errors.state == "not_assessed"
    assert findings.issues.state == "not_assessed"
    assert not findings.errors.items and not findings.issues.items
    assert {item.reason for item in findings.errors.assessments} == {"no_check"}


def test_the_default_registry_is_the_one_the_lots_fill(tmp_path, monkeypatch):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    calls = []

    def check(column):
        calls.append(column.field.id)
        return CheckResult(
            assessment=Assessment(code="type.mixed", state="none_detected")
        )

    monkeypatch.setitem(CHECKS, "type.mixed", check)
    findings = column_findings(column)

    assert calls == [column.field.id]
    states = {item.code: item.state for item in findings.issues.assessments}
    assert states["type.mixed"] == "none_detected"
    # The checks of the Issues are registered (R6b): they ran, none is missing.
    assert "no_check" not in {item.reason for item in findings.issues.assessments}
    assert set(CHECKS) <= {entry.code for entry in _active("error", "issue")}


def test_none_detected_needs_every_check_behind_the_list_to_have_completed(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    checks = _all_clear()

    complete = column_findings(column, checks)
    dropped = dict(checks)
    del dropped["type.mixed"]
    incomplete = column_findings(column, dropped)

    assert complete.errors.state == "none_detected"
    assert complete.issues.state == "none_detected"
    assert incomplete.issues.state == "partial"
    assert incomplete.errors.state == "none_detected"


def test_a_finding_makes_its_list_detected_and_goes_to_its_class(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    checks = _all_clear()
    issue = _finding("type.mixed")
    checks["type.mixed"] = lambda column: CheckResult(
        assessment=Assessment(code="type.mixed", state="detected", accuracy="exact"),
        items=[issue],
    )

    findings = column_findings(column, checks)

    assert findings.issues.items == [issue]
    assert findings.issues.state == "detected"
    assert findings.errors.state == "none_detected"


def test_an_error_downgraded_to_an_issue_is_not_an_error(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    checks = _all_clear()
    downgraded = _finding("semantic.invalid", cls="issue")
    checks["semantic.invalid"] = lambda column: CheckResult(
        assessment=Assessment(
            code="semantic.invalid", state="detected", accuracy="exact"
        ),
        items=[downgraded],
    )

    findings = column_findings(column, checks)

    assert not findings.errors.items
    assert findings.errors.state == "none_detected"
    assert findings.issues.items == [downgraded]
    assert findings.issues.state == "detected"


def test_a_downgraded_error_found_on_part_of_the_values_is_partial_for_errors(
    tmp_path,
):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    checks = _all_clear()
    checks["semantic.invalid"] = lambda column: CheckResult(
        assessment=Assessment(
            code="semantic.invalid", state="detected", accuracy="lower_bound"
        ),
        items=[_finding("semantic.invalid", cls="issue")],
    )

    findings = column_findings(column, checks)

    assert findings.errors.state == "partial"


def test_a_check_cannot_return_a_class_or_a_code_it_was_not_given(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])

    def returning(item):
        checks = _all_clear()
        checks["type.mixed"] = lambda column: CheckResult(
            assessment=Assessment(code="type.mixed", state="detected"), items=[item]
        )
        return checks

    with pytest.raises(ValueError, match="information finding"):
        column_findings(column, returning(_finding("type.mixed", cls="information")))
    with pytest.raises(ValueError, match="error finding"):
        column_findings(column, returning(_finding("type.mixed", cls="error")))
    with pytest.raises(ValueError, match="returned a categorical.rare finding"):
        column_findings(column, returning(_finding("categorical.rare")))


def test_an_error_on_a_classification_that_is_not_established_is_an_issue(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    assert column.classification.state == "established"
    candidate = column.model_copy(
        update={
            "classification": column.classification.model_copy(
                update={"state": "candidate"}
            )
        }
    )
    checks = _all_clear()
    checks["semantic.invalid"] = lambda column: CheckResult(
        assessment=Assessment(
            code="semantic.invalid", state="detected", accuracy="exact"
        ),
        items=[_finding("semantic.invalid", cls="error")],
    )

    established = column_findings(column, checks)
    uncertain = column_findings(candidate, checks)

    assert [item.cls for item in established.errors.items] == ["error"]
    assert not uncertain.errors.items
    assert [(i.code, i.cls) for i in uncertain.issues.items] == [
        ("semantic.invalid", "issue")
    ]
    assert uncertain.errors.state == "none_detected"


def test_an_issue_check_that_reports_detected_without_a_finding_is_not_detected(
    tmp_path,
):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    checks = _all_clear()
    checks["type.mixed"] = lambda column: CheckResult(
        assessment=Assessment(code="type.mixed", state="detected", accuracy="exact")
    )

    findings = column_findings(column, checks)

    assert not findings.issues.items
    assert findings.issues.state == "none_detected"


def test_findings_are_deterministic_and_never_a_member_of_the_document(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])

    assert column_findings(column) == column_findings(column)
    assert "findings" not in ColumnProfile.model_fields
    assert "errors" not in ColumnProfile.model_fields
    profile = analyze_csv(write_text(tmp_path, "b.csv", "a,b\n1,2\n"))
    assert '"findings"' not in json.dumps(profile.model_dump(mode="json"))


# --- Catalogue ----------------------------------------------------------------------


def test_codes_are_unique_and_a_recommended_one_has_no_active_twin():
    codes = [entry.code for entry in FINDINGS]

    assert len(codes) == len(set(codes)) == len(FINDING_CODES)
    assert {entry.status for entry in FINDINGS} == {"active", "recommended"}


def test_every_active_finding_is_worded_in_its_usual_unit():
    for entry in _active("error", "issue", "information"):
        assert entry.unit in FINDING_NOUNS[entry.code], entry.code


def test_only_an_error_downgrades_to_an_issue():
    for entry in FINDINGS:
        if entry.downgrades_to_issue:
            assert entry.cls == "error"
            assert "classification:established" in entry.prerequisites


def test_a_recommended_finding_is_never_reported(tmp_path):
    column = _csv(tmp_path, "note", ["x", "y", "z"])
    checks = {
        entry.code: (
            lambda column, code=entry.code: CheckResult(
                assessment=Assessment(code=code, state="detected"),
                items=[_finding(code)],
            )
        )
        for entry in FINDINGS
    }

    findings = column_findings(column, checks)

    recommended = {entry.code for entry in FINDINGS if entry.status == "recommended"}
    reported = {item.code for item in findings.errors.items + findings.issues.items}
    assert reported.isdisjoint(recommended)
    assert not {item.code for item in findings.issues.assessments} & recommended


# --- Shares and divisions by zero ----------------------------------------------------


def test_a_share_is_a_percentage_of_its_population():
    result = share(25, 200)

    assert (result.numerator, result.denominator) == (25, 200)
    assert result.percent == 12.5
    assert result.accuracy == "exact"


def test_a_share_keeps_the_accuracy_of_its_count():
    assert share(3, 10, "lower_bound").accuracy == "lower_bound"


@pytest.mark.parametrize(
    ("count", "population"), [(0, 0), (5, 0), (3, -1), (11, 10), (-1, 10)]
)
def test_a_share_that_is_not_defined_has_no_percentage(count, population):
    result = share(count, population)

    assert result.percent is None
    assert result.accuracy == "unavailable"


def test_the_ratio_of_distinct_values_to_present_values_has_no_division_by_zero():
    assert repetition_figures([]).distinct_ratio is None
    assert repetition_from_counts(0, 0).distinct_ratio is None
    assert repetition_from_counts(4, 2).distinct_ratio == 0.5


# --- Repetitions -----------------------------------------------------------------------


def test_repetitions_beyond_the_first_are_neither_groups_nor_duplicated_occurrences():
    figures = repetition_figures(["A", "A", "A", "B"])

    assert figures.present == 4
    assert figures.distinct == 2
    assert figures.beyond_first == 2
    assert figures.duplicated_groups == 1
    assert figures.occurrences_in_duplicated_groups == 3
    assert figures.distinct_ratio == 0.5


def test_several_groups_of_repeated_values():
    figures = repetition_figures(["A", "A", "B", "B", "B", "C"])

    assert figures.beyond_first == 3
    assert figures.duplicated_groups == 2
    assert figures.occurrences_in_duplicated_groups == 5


def test_unique_values_have_no_repetition():
    figures = repetition_figures(["A", "B", "C"])

    assert figures.beyond_first == 0
    assert figures.duplicated_groups == 0
    assert figures.occurrences_in_duplicated_groups == 0


def test_present_and_distinct_counts_alone_give_no_group_figure():
    figures = repetition_from_counts(10, 7)

    assert figures.beyond_first == 3
    assert figures.duplicated_groups is None
    assert figures.occurrences_in_duplicated_groups is None


@pytest.mark.parametrize(("present", "distinct"), [(10, None), (3, 4), (3, -1)])
def test_a_distinct_count_that_is_not_exact_or_not_possible_gives_nothing(
    present, distinct
):
    assert repetition_from_counts(present, distinct) is None


# --- Words -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (0, "0 spelling-variant groups"),
        (1, "1 spelling-variant group"),
        (2, "2 spelling-variant groups"),
        (1200, "1,200 spelling-variant groups"),
    ],
)
def test_the_noun_follows_the_real_quantity(count, expected):
    assert label_for("categorical.case_variants", count, "groups") == expected


def test_the_name_follows_the_unit_the_scan_really_has():
    assert label_for("identifier.repetition", 2, "occurrences") == (
        "2 repetitions beyond the first"
    )
    assert label_for("identifier.repetition", 1, "groups") == "1 repeated identifier"
    assert label_for("pattern.minority", 3, "patterns") == "3 minority patterns"
    assert label_for("pattern.minority", 1, "distinct_values") == (
        "1 distinct value in a minority pattern"
    )


def test_a_finding_without_a_name_of_its_own_is_worded_by_its_unit():
    assert label_for("categorical.rare", 1, "categories") == "1 category"
    assert label_for("no.such.code", 4, "records") == "4 records"


def test_plural_and_population_phrases():
    assert plural(1, "row", "rows") == "1 row"
    assert plural(1234567, "row", "rows") == "1,234,567 rows"
    assert population_phrase("positions", 100) == "100 positions"
    assert population_phrase("eligible_values", 1) == "1 eligible value"


# --- Findings from the facts of the Scan ------------------------------------------------


def test_an_observation_is_stated_as_it_is(tmp_path):
    column = _csv(
        tmp_path, "tag", ["Paris", "paris", "PARIS", "Lyon", "lyon", "Nice"] * 5
    )
    item = next(
        item for item in column.quality if item.observation.rule == "variant_groups"
    )

    finding = finding_from_observation("categorical.case_variants", item.observation)

    assert finding.code == "categorical.case_variants"
    assert finding.cls == "issue"
    assert finding.count == item.observation.count == 2
    assert finding.unit == "groups"
    assert finding.population.kind == "groups"
    # A number of groups has no denominator: no share is made up.
    assert finding.population.size is None
    assert finding.share is None
    assert finding.basis == [item.observation.id]
    assert finding.overlaps == []


def test_a_recommended_finding_cannot_be_stated_from_an_observation():
    with pytest.raises(ValueError, match="never reported"):
        finding_from_observation("categorical.rare", _observation())


def test_an_observation_with_a_population_gives_a_share_and_its_accuracy():
    finding = finding_from_observation(
        "length.minority", _observation(count=3, of=100, accuracy="sample")
    )

    assert finding.unit == "occurrences"
    assert finding.population == Population(kind="content_strings", size=100)
    assert finding.share.percent == 3
    assert finding.share.accuracy == "sample"
    assert finding.accuracy == "sample"


def test_an_observation_counted_in_columns_is_not_a_finding_of_a_column():
    with pytest.raises(ValueError, match="no finding of a column"):
        finding_from_observation("length.minority", _observation(population="columns"))


def test_an_observation_of_the_whole_scan_is_not_a_finding_of_a_column():
    with pytest.raises(ValueError, match="not about a field"):
        finding_from_observation(
            "length.minority", _observation(field=None, population="records")
        )


# --- Merging on proof ---------------------------------------------------------------------


def test_equal_counts_without_proof_stay_apart():
    groups = merge_proven(
        [_finding("pattern.minority", 36), _finding("length.minority", 36)]
    )

    assert [group.merged for group in groups] == [False, False]


def test_a_proven_overlap_presents_findings_as_one_group_without_a_total():
    first = _finding("pattern.minority", 36, overlaps=["length.minority"])
    second = _finding("length.minority", 30)
    third = _finding("type.mixed", 5)

    groups = merge_proven([first, third, second])

    assert [len(group.members) for group in groups] == [2, 1]
    assert groups[0].merged
    assert groups[0].counts == [36, 30]
    assert [member.code for member in groups[0].members] == [
        "pattern.minority",
        "length.minority",
    ]
    # The findings themselves are untouched.
    assert first.count == 36 and second.count == 30


def test_the_overlap_is_closed_by_transitivity():
    first = _finding("pattern.minority", overlaps=["length.minority"])
    second = _finding("length.minority", overlaps=["type.mixed"])
    third = _finding("type.mixed")

    groups = merge_proven([first, second, third])

    assert len(groups) == 1 and len(groups[0].members) == 3


def test_an_overlap_naming_a_code_that_several_findings_bear_merges_nothing():
    first = _finding("pattern.minority", overlaps=["semantic.invalid"])
    others = [_finding("semantic.invalid", 5), _finding("semantic.invalid", 7)]

    groups = merge_proven([first, *others])

    assert [group.merged for group in groups] == [False, False, False]


def test_an_overlap_naming_an_absent_code_merges_nothing():
    groups = merge_proven([_finding("pattern.minority", overlaps=["type.mixed"])])

    assert len(groups) == 1 and not groups[0].merged


def test_two_observations_overlap_only_when_they_list_every_record_and_meet():
    first = _observation(population="records", count=3, records=[1, 2, 3])
    second = _observation(population="records", count=2, records=[3, 9])
    apart = _observation(population="records", count=2, records=[7, 9])
    partial = _observation(population="records", count=50, records=[1, 2, 3])
    estimated = _observation(
        population="records", count=2, records=[3, 9], accuracy="lower_bound"
    )

    assert records_overlap(first, second)
    assert not records_overlap(first, apart)
    assert not records_overlap(first, partial)
    assert not records_overlap(first, estimated)
    # Equal counts alone prove nothing.
    assert not records_overlap(_observation(count=36), _observation(count=36))
