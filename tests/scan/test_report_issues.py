# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Issues of a column from the Scan's existing facts (Report overview lot R6b).

The contract is ``docs/dev/report/summary-table.md`` 6.6 and 6.9. The checks are
run through ``column_findings`` on the views of real scans; the cases a scan
cannot make (a detector that tested part of the values, observations that two
rules share records for) edit the view.
"""

from scan_helpers import write_json, write_text

from tabalyst import analyze_csv
from tabalyst.report_config import ReportConfig
from tabalyst.report_findings import (
    CHECKS,
    column_findings,
    label_for,
    merge_proven,
    prove_overlaps,
)
from tabalyst.report_views import PatternView
from tabalyst.reporting import dataset_views
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.classify.catalog import FINDINGS
from tabalyst.scanner.models import DetectorFailed, Observation

ISSUE_CODES = {
    "temporal.ambiguous_date",
    "number.ambiguous",
    "categorical.case_variants",
    "pattern.minority",
    "length.minority",
    "type.mixed",
    "identifier.repetition",
    "text.surrounding_whitespace",
    "text.repeated_whitespace",
}


def _views(source, **settings):
    config = ReportConfig(scan=ScanConfig.model_validate(settings))
    return dataset_views(analyze_csv(source, config))[0].columns


def _csv(tmp_path, header, cells, **settings):
    """The view of the first column of a CSV; a second column of row numbers lets
    the first one hold empty cells."""
    lines = [f"{header},row"] + [f"{value},{n}" for n, value in enumerate(cells)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    return _views(source, **settings)[0]


def _issues(column):
    return {item.code: item for item in column_findings(column).issues.items}


def _states(column):
    """The state and the reason of the check behind each Issue code."""
    return {
        item.code: (item.state, item.reason)
        for item in column_findings(column).issues.assessments
    }


def _with_coverage(column, detector_id, **coverage):
    detector = next(item for item in column.field.detectors if item.id == detector_id)
    changed = detector.coverage.model_copy(update=coverage)
    detectors = [
        detector.model_copy(update={"coverage": changed}) if item is detector else item
        for item in column.field.detectors
    ]
    return column.model_copy(
        update={"field": column.field.model_copy(update={"detectors": detectors})}
    )


def test_every_active_issue_code_of_the_catalogue_has_its_check():
    issues = {
        entry.code
        for entry in FINDINGS
        if entry.cls == "issue" and entry.status == "active"
    }

    assert issues == ISSUE_CODES
    assert issues <= set(CHECKS)


def test_no_recommended_code_has_a_check():
    recommended = {entry.code for entry in FINDINGS if entry.status == "recommended"}

    assert recommended
    assert not recommended & set(CHECKS)


# Ambiguous dates and numbers ---------------------------------------------------


def test_CA11_an_ambiguous_date_is_an_issue_with_its_population(tmp_path):
    column = _csv(
        tmp_path, "signed", ["2025-01-15"] * 30 + ["2025-02-30", "03/04/2025"]
    )

    issue = _issues(column)["temporal.ambiguous_date"]

    assert (issue.cls, issue.count, issue.unit) == ("issue", 1, "occurrences")
    assert issue.population.kind == "occurrences"
    assert issue.population.size == 31
    assert issue.accuracy == "exact"
    observation = next(
        item.observation
        for item in column.quality
        if item.observation.rule == "ambiguous_dates"
    )
    assert issue.basis == [observation.id]
    assert "temporal.invalid_calendar" in {
        item.code for item in column_findings(column).errors.items
    }


def test_an_ambiguous_date_in_a_column_that_is_not_dated_is_still_an_issue(tmp_path):
    column = _csv(tmp_path, "note", ["alpha"] * 30 + ["03/04/2025", "2025-01-15"])

    findings = column_findings(column)

    assert column.classification.family != "temporal"
    assert [item.code for item in findings.issues.items if "date" in item.code] == [
        "temporal.ambiguous_date"
    ]


def test_ambiguous_numbers_are_counted_by_the_detector(tmp_path):
    column = _csv(tmp_path, "amount", ['"1,234"'] * 3 + ["1234"] * 30 + ['"1.234"'] * 2)

    issue = _issues(column)["number.ambiguous"]

    assert (issue.cls, issue.count, issue.unit) == ("issue", 3, "occurrences")
    assert issue.population.kind == "eligible_values"
    assert issue.basis == ["number"]
    assert issue.share.denominator == issue.population.size


def test_CA17_a_date_detector_that_tested_part_of_the_values_is_partial(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 300)
    partial = _with_coverage(column, "date", eligible=1000, tested=100)

    findings = column_findings(partial)

    assert not findings.issues.items
    assert _states(partial)["temporal.ambiguous_date"][0] == "partial"
    assert findings.issues.state == "partial"


def test_the_count_of_a_partly_tested_date_detector_is_a_lower_bound(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 30 + ["03/04/2025"])
    partial = _with_coverage(column, "date", eligible=1000, tested=100)

    issue = _issues(partial)["temporal.ambiguous_date"]

    assert issue.count == 1
    assert issue.accuracy == "lower_bound"
    assert issue.share.accuracy == "lower_bound"


def test_a_failed_date_detector_is_not_an_absence_of_ambiguity(tmp_path):
    column = _csv(tmp_path, "signed", ["2025-01-15"] * 30)
    failed = DetectorFailed(id="date", version=1, reason="boom", diagnostic=3)
    detectors = [
        failed if item.id == "date" else item for item in column.field.detectors
    ]
    broken = column.model_copy(
        update={"field": column.field.model_copy(update={"detectors": detectors})}
    )

    assert _states(broken)["temporal.ambiguous_date"][0] == "failed"


# Case variants: groups, never occurrences -------------------------------------


def test_CA14_three_case_variant_groups_over_twenty_occurrences_are_three(tmp_path):
    cells = (
        ["Alpha"] * 4
        + ["ALPHA"] * 3
        + ["Beta"] * 3
        + ["BETA"] * 2
        + ["Gamma"] * 4
        + ["GAMMA"] * 4
    )
    column = _csv(tmp_path, "city", cells)

    issue = _issues(column)["categorical.case_variants"]

    assert len(cells) == 20
    assert (issue.count, issue.unit) == (3, "groups")
    assert issue.population.kind == "groups"
    assert issue.share is None
    assert label_for(issue.code, issue.count, issue.unit) == "3 spelling-variant groups"
    assert all(item.count != 20 for item in column_findings(column).issues.items)


def test_one_case_variant_group_is_singular(tmp_path):
    column = _csv(tmp_path, "city", ["Alpha"] * 5 + ["ALPHA"] * 5)

    issue = _issues(column)["categorical.case_variants"]

    assert label_for(issue.code, issue.count, issue.unit) == "1 spelling-variant group"


def test_a_column_without_variants_is_none_detected_for_them(tmp_path):
    column = _csv(tmp_path, "city", ["Alpha"] * 5 + ["Beta"] * 5)

    assert _states(column)["categorical.case_variants"] == ("none_detected", None)


# Minority patterns and lengths -------------------------------------------------


def test_minority_patterns_are_counted_in_distinct_values(tmp_path):
    column = _csv(
        tmp_path, "code", [f"CLI-{n:04d}" for n in range(200)] + ["X-9", "Y-8"]
    )

    issue = _issues(column)["pattern.minority"]
    observation = next(
        item.observation
        for item in column.quality
        if item.observation.rule == "minority_pattern"
    )

    assert (issue.count, issue.unit) == (2, "distinct_values")
    assert issue.population.kind == "distinct_values"
    assert issue.population.size == 202
    assert issue.basis == [observation.id, *observation.patterns]
    assert issue.accuracy == observation.accuracy


def test_minority_lengths_are_counted_in_values_of_the_column(tmp_path):
    column = _csv(
        tmp_path, "ref", [f"AB{n:06d}" for n in range(200)] + ["AB1", "AB2", "AB3"]
    )

    issue = _issues(column)["length.minority"]

    assert (issue.count, issue.unit) == (3, "occurrences")
    assert issue.population.kind == "content_strings"
    assert issue.population.size == 203


def test_too_few_values_are_not_applicable_for_the_minority_length(tmp_path):
    column = _csv(tmp_path, "name", ["a", "b", "c"])

    assert _states(column)["length.minority"] == ("not_applicable", "too_few_values")


def test_no_dominant_length_is_not_applicable_for_the_minority_length(tmp_path):
    # Two legitimate lengths (12 and 10 characters) leave no length at 95 %: the
    # rule of the Scan does not apply, so the odd 13-character ids are not "none".
    cells = (
        [f"CLI-{n:08d}" for n in range(180)]
        + [f"CL{n:08d}" for n in range(20)]
        + ["CLI--00000001", "CLI--00000002"]
    )
    column = _csv(tmp_path, "id", cells)

    assert _states(column)["length.minority"] == (
        "not_applicable",
        "no_dominant_length",
    )
    assert "length.minority" not in _issues(column)


def test_patterns_the_document_does_not_hold_are_not_assessed(tmp_path):
    column = _csv(tmp_path, "code", [f"CLI-{n:04d}" for n in range(200)])
    without = column.model_copy(update={"patterns": PatternView(status="missing")})

    assert _states(without)["pattern.minority"] == (
        "not_assessed",
        "patterns_unavailable",
    )


def test_patterns_of_a_sample_are_partial_when_none_is_found(tmp_path):
    column = _csv(tmp_path, "code", [f"CLI-{n:04d}" for n in range(200)])
    entry = column.patterns.entry
    sampled = entry.model_copy(
        update={"population": entry.population.model_copy(update={"complete": False})}
    )
    column = column.model_copy(
        update={"patterns": column.patterns.model_copy(update={"entry": sampled})}
    )

    assert _states(column)["pattern.minority"] == ("partial", "patterns_sample")


# Mixed types -------------------------------------------------------------------


def test_a_mixed_column_counts_the_values_outside_its_closest_type(tmp_path):
    column = _csv(tmp_path, "stuff", ["abc"] * 10 + ["12"] * 10)

    issue = _issues(column)["type.mixed"]

    assert column.classification.type == "mixed"
    assert (issue.count, issue.unit) == (10, "occurrences")
    assert issue.population.kind == "present_values"
    assert issue.population.size == 20


def test_a_numeric_column_with_outsiders_has_no_mixed_issue_but_an_error(tmp_path):
    column = _csv(tmp_path, "value", [str(n) for n in range(300)] + ["abc"])

    findings = column_findings(column)

    assert "type.outside_family" in {item.code for item in findings.errors.items}
    assert _states(column)["type.mixed"] == ("none_detected", None)


# Identifier repetition: N - D --------------------------------------------------


def test_CA15_a_repeated_identifier_counts_repetitions_beyond_the_first(tmp_path):
    column = _csv(tmp_path, "customer_id", ["A", "A", "A", "B"])

    issue = _issues(column)["identifier.repetition"]

    assert column.classification.type == "id"
    assert (issue.count, issue.unit) == (2, "occurrences")
    assert issue.population.size == 4
    assert label_for(issue.code, issue.count, issue.unit) == (
        "2 repetitions beyond the first"
    )


def test_a_unique_identifier_has_no_repetition(tmp_path):
    column = _csv(tmp_path, "customer_id", [f"C{n:05d}" for n in range(100)])

    assert column.classification.type == "unique_id"
    assert _states(column)["identifier.repetition"][0] == "none_detected"


def test_a_cardinality_that_is_not_exact_leaves_the_repetition_not_assessed(tmp_path):
    cells = [f"C{n:05d}" for n in range(100)] + ["C00001"]
    column = _csv(tmp_path, "customer_id", cells, limits={"max_distinct_per_field": 50})

    assert column.classification.type == "id"
    assert _states(column)["identifier.repetition"] == (
        "not_assessed",
        "cardinality_not_exact",
    )
    assert "identifier.repetition" not in _issues(column)


def test_a_column_that_is_not_an_identifier_has_no_repetition_check(tmp_path):
    column = _csv(tmp_path, "city", ["Alpha", "Alpha", "Beta"])

    assert _states(column)["identifier.repetition"] == (
        "not_applicable",
        "not_identifier",
    )


# Whitespace --------------------------------------------------------------------


def test_surrounding_and_repeated_whitespace_are_counted_apart(tmp_path):
    column = _csv(tmp_path, "name", [" a", "b", "c  d", "e"] * 5)

    issues = _issues(column)

    assert (
        issues["text.surrounding_whitespace"].count,
        issues["text.surrounding_whitespace"].unit,
    ) == (5, "occurrences")
    assert issues["text.repeated_whitespace"].count == 5
    assert issues["text.repeated_whitespace"].population.kind == "content_strings"
    assert issues["text.repeated_whitespace"].population.size == 20


def test_a_stage_that_is_off_leaves_its_check_not_assessed(tmp_path):
    column = _csv(
        tmp_path, "name", [" a", "b", "c  d", "e"] * 5, normalization={"trim": False}
    )

    assert _states(column)["text.surrounding_whitespace"] == (
        "not_assessed",
        "stage_disabled",
    )
    assert "text.repeated_whitespace" in _issues(column)


def test_a_column_without_text_values_has_no_whitespace_check(tmp_path):
    column = _csv(tmp_path, "name", [""] * 5)

    assert _states(column)["text.surrounding_whitespace"] == (
        "not_applicable",
        "no_text",
    )
    assert column_findings(column).issues.state == "not_applicable"


def test_the_whitespace_of_a_repeated_json_field_is_counted_in_occurrences(tmp_path):
    records = [{"tags": [" x", "y", "z "]} for _ in range(100)]
    columns = _views(write_json(tmp_path, "data.json", records))
    column = next(item for item in columns if item.path == "tags[]")

    issue = _issues(column)["text.surrounding_whitespace"]

    assert issue.unit == "occurrences"
    assert issue.count == 200
    assert issue.population.size == 300


# What an absent observation means ----------------------------------------------


def test_without_the_observations_a_fact_that_needs_them_is_not_assessed(tmp_path):
    cells = ["Alpha"] * 4 + ["ALPHA"] * 3
    column = _csv(tmp_path, "city", cells, observations={"enabled": False})

    assert column.observations_state == "unavailable"
    assert not _issues(column)
    assert _states(column)["categorical.case_variants"] == (
        "not_assessed",
        "observations_unavailable",
    )


def test_a_cut_list_of_observations_never_says_none_detected(tmp_path):
    cells = ["Alpha"] * 4 + ["ALPHA"] * 3 + [" Beta "] * 3 + ["Beta"] * 2
    column = _csv(tmp_path, "name", cells, observations={"max_items": 1})

    assert column.observations_state == "truncated"
    assert "categorical.case_variants" in _issues(column)
    assert "text.surrounding_whitespace" not in _issues(column)
    assert _states(column)["text.surrounding_whitespace"] == (
        "partial",
        "observations_truncated",
    )
    assert column_findings(column).issues.state == "detected"


def test_a_cut_list_does_not_hide_a_measure_that_proves_the_absence(tmp_path):
    column = _csv(
        tmp_path, "name", ["Alpha"] * 4 + ["ALPHA"] * 3, observations={"max_items": 1}
    )

    assert _states(column)["text.surrounding_whitespace"] == ("none_detected", None)


# Issues need no established classification -----------------------------------


def test_an_issue_is_stated_on_a_column_whose_classification_is_not_established(
    tmp_path,
):
    column = _csv(tmp_path, "value", [str(10000 + n) for n in range(300)] + ["abc"])

    findings = column_findings(column)

    assert column.classification.state == "undetermined"
    assert all(item.cls == "issue" for item in findings.issues.items)
    assert not findings.errors.items


# Overlap needs a proof (RF-24, CA26) --------------------------------------------


def _with_observations(column, *observations):
    """The view with the given observations in place of its own."""
    template = column.quality[0]
    return column.model_copy(
        update={
            "quality": [
                template.model_copy(update={"observation": item})
                for item in observations
            ]
        }
    )


def _observation(column, number, rule, population, count, records=()):
    return Observation(
        id=f"o{number}",
        rule=rule,
        category="patterns",
        status="candidate_anomaly",
        dataset="rows",
        field=column.field.id,
        population=population,
        count=count,
        of=1000,
        accuracy="exact",
        records=list(records),
    )


def _two_observations_of_36(tmp_path, first_records=(), second_records=()):
    column = _csv(tmp_path, "city", ["Alpha"] * 5 + ["ALPHA"] * 5)
    return _with_observations(
        column,
        _observation(
            column, 1, "minority_pattern", "distinct_values", 36, first_records
        ),
        _observation(
            column, 2, "minority_length", "content_strings", 36, second_records
        ),
    )


def test_two_observations_of_36_without_proof_stay_separate(tmp_path):
    column = _two_observations_of_36(tmp_path)

    findings = column_findings(column).issues.items
    both = [
        item
        for item in findings
        if item.code in ("pattern.minority", "length.minority")
    ]

    assert [item.count for item in both] == [36, 36]
    assert all(item.overlaps == [] for item in both)
    assert len(merge_proven(both)) == 2


def test_lists_of_records_that_do_not_meet_prove_nothing(tmp_path):
    column = _two_observations_of_36(tmp_path, range(36), range(100, 136))

    both = [
        item
        for item in column_findings(column).issues.items
        if item.code in ("pattern.minority", "length.minority")
    ]

    assert all(item.overlaps == [] for item in both)
    assert len(merge_proven(both)) == 2


def test_a_partial_list_of_records_proves_nothing_even_if_it_meets(tmp_path):
    column = _two_observations_of_36(tmp_path, range(10), range(36))

    both = [
        item
        for item in column_findings(column).issues.items
        if item.code in ("pattern.minority", "length.minority")
    ]

    assert all(item.overlaps == [] for item in both)


def test_complete_lists_that_meet_prove_the_overlap_and_keep_each_count(tmp_path):
    column = _two_observations_of_36(tmp_path, range(36), range(20, 56))

    both = [
        item
        for item in column_findings(column).issues.items
        if item.code in ("pattern.minority", "length.minority")
    ]
    groups = merge_proven(both)

    assert {item.code: item.overlaps for item in both} == {
        "pattern.minority": ["length.minority"],
        "length.minority": ["pattern.minority"],
    }
    assert len(groups) == 1
    assert groups[0].counts == [36, 36]


def test_prove_overlaps_leaves_findings_without_observation_untouched(tmp_path):
    column = _csv(tmp_path, "customer_id", ["A", "A", "A", "B"])
    items = column_findings(column).issues.items

    assert prove_overlaps(items, column) == items


# The envelopes of the measures behind the checks ---------------------------------


def _with_field(column, **changes):
    return column.model_copy(update={"field": column.field.model_copy(update=changes)})


def test_the_envelope_of_a_measure_gives_the_state_of_its_check(tmp_path):
    from tabalyst.scanner.models import Disabled, Failed, Limited, NotApplicable

    column = _csv(tmp_path, "city", ["Alpha"] * 5 + ["Beta"] * 5)
    cases = [
        (Limited(reason="budget", limit=1), "partial", "budget"),
        (NotApplicable(reason="no_text"), "not_applicable", "no_text"),
        (Failed(reason="boom", diagnostic=1), "failed", "boom"),
        (Disabled(), "not_assessed", "disabled"),
    ]
    for envelope, state, reason in cases:
        normalization = column.field.normalization.model_copy(
            update={"variant_groups": envelope}
        )
        changed = _with_field(column, normalization=normalization)
        assert _states(changed)["categorical.case_variants"] == (state, reason)

    for envelope, state, reason in cases:
        changed = _with_field(column, string_lengths=envelope)
        assert _states(changed)["length.minority"] == (state, reason)


def test_a_count_with_no_observation_in_a_complete_list_says_so(tmp_path):
    column = _csv(tmp_path, "city", ["Alpha"] * 5 + ["ALPHA"] * 5)
    without = column.model_copy(update={"quality": []})

    assert _states(without)["categorical.case_variants"] == (
        "partial",
        "observation_not_listed",
    )
