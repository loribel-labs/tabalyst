# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the Report summary table (Report overview plan, lot R0).

The behavior is specified in ``docs/dev/report/summary-table.md``; the ``CA-nn``
names are the acceptance criteria of the requirements specification. Every test
carries the lot that delivers it with ``@pytest.mark.report_lot`` and is
skipped until ``report_gate.ENABLED_LOTS`` names that lot. Imports of modules a
lot creates are inside the tests for that reason.
"""

import json

import pytest
from scan_helpers import field, run_scan, write_text

# Text bounds of decision 12 (contract section 3.6).
TEXT_BOUNDS = (5, 20, 50, 255)


def _csv(directory, header, values):
    lines = [header] + [str(value) for value in values]
    return write_text(directory, "data.csv", "\n".join(lines) + "\n")


def _classify(directory, header, values, **settings):
    """The classification block of the only column of a one-column CSV."""
    result = run_scan(_csv(directory, header, values), **settings)
    return field(result["datasets"][0], header)["classification"]


def _word(length, index):
    """A distinct text of exactly ``length`` letters (never a number or a date)."""
    stem = f"{chr(97 + index % 26)}{chr(97 + index // 26 % 26)}"
    return (stem * length)[:length]


def _with_median(directory, median):
    """Four texts whose exact median length is ``median`` (n or n.5)."""
    low = int(median)
    high = low + 1 if median != low else low
    lengths = [low, low, high, high]
    return _classify(
        directory, "note", [_word(n, i) for i, n in enumerate(lengths)]
    )


def _pair(classification):
    return classification["family"], classification["type"]


# --- R1a: model, Text, fallback ------------------------------------------------


@pytest.mark.report_lot("R1a")
def test_a_classification_has_the_documented_members(tmp_path):
    classification = _classify(tmp_path, "note", ["alpha", "beta", "gamma"])

    assert set(classification) == {
        "family",
        "type",
        "basis",
        "state",
        "traits",
        "evidence",
        "alternatives",
        "rule_version",
    }
    assert classification["basis"] in {"declared", "inferred", "fallback"}
    assert classification["state"] in {"established", "candidate", "undetermined"}
    assert "confidence" not in classification


@pytest.mark.report_lot("R1a")
def test_CA08_the_median_length_gives_the_text_type_not_the_maximum(tmp_path):
    # Lengths 4, 4, 4, 4, 4000: the maximum is Very long, the median is 4.
    values = [_word(4, i) for i in range(4)] + [_word(4000, 9)]

    classification = _classify(tmp_path, "note", values)

    assert _pair(classification) == ("text", "text_very_short")


@pytest.mark.report_lot("R1a")
@pytest.mark.parametrize(
    ("median", "expected"),
    [
        (5, "text_very_short"),
        (5.5, "text_short"),
        (20, "text_short"),
        (21, "text_medium"),
        (50, "text_medium"),
        (51, "text_long"),
        (255, "text_long"),
        (256, "text_very_long"),
    ],
)
def test_CA09_text_types_change_at_the_configured_bounds(tmp_path, median, expected):
    assert _with_median(tmp_path, median)["type"] == expected


@pytest.mark.report_lot("R1a")
def test_the_text_bounds_are_a_scan_setting_with_the_documented_defaults(tmp_path):
    from tabalyst.scanner import ScanConfig

    settings = ScanConfig().classification

    assert (
        settings.very_short_max_length,
        settings.short_max_length,
        settings.medium_max_length,
        settings.long_max_length,
    ) == TEXT_BOUNDS


@pytest.mark.report_lot("R1a")
def test_changing_a_text_bound_moves_the_type_and_the_scan_identity(tmp_path):
    values = [_word(30, i) for i in range(4)]
    default = run_scan(_csv(tmp_path, "note", values))
    wider = run_scan(
        _csv(tmp_path, "note", values),
        classification={"short_max_length": 40, "medium_max_length": 60},
    )

    assert field(default["datasets"][0], "note")["classification"]["type"] == (
        "text_medium"
    )
    assert field(wider["datasets"][0], "note")["classification"]["type"] == (
        "text_short"
    )
    assert default["config_sha256"] != wider["config_sha256"]


@pytest.mark.report_lot("R1a")
@pytest.mark.parametrize(
    "key",
    ["very_short_max_length", "short_max_length", "medium_max_length", "long_max_length"],
)
def test_the_old_string_analysis_bounds_are_refused_with_their_new_place(
    tmp_path, key
):
    from tabalyst.config import load_config
    from tabalyst.errors import ConfigurationError

    path = write_text(
        tmp_path,
        "config.json",
        json.dumps({"report": {"string_analysis": {key: 30}}}),
    )

    with pytest.raises(ConfigurationError, match=f"scan.classification.{key}"):
        load_config([path])


@pytest.mark.report_lot("R1a")
@pytest.mark.parametrize(
    "envelope",
    [
        {"status": "limited", "reason": "memory", "limit": 1},
        {"status": "disabled"},
        {"status": "failed", "reason": "boom", "diagnostic": 0},
        {"status": "not_applicable", "reason": "no_values"},
    ],
)
def test_an_unavailable_median_leaves_the_text_length_undetermined(
    tmp_path, envelope
):
    # The Scan always measures the lengths of its texts: the unavailable
    # measure is built by hand. The maximum must not replace the median.
    from pydantic import TypeAdapter

    from tabalyst.scanner import ScanConfig, scan
    from tabalyst.scanner.classify import ClassifyContext, classify_field
    from tabalyst.scanner.models import FieldResult

    result = scan(_csv(tmp_path, "note", [_word(8, i) for i in range(6)]))
    measure = TypeAdapter(
        FieldResult.model_fields["string_lengths"].annotation
    ).validate_python(envelope)
    broken = result.datasets[0].fields[0].model_copy(
        update={"string_lengths": measure}
    )

    classification = classify_field(
        broken, ClassifyContext(ScanConfig().classification)
    ).model_dump()

    assert classification["family"] == "text"
    assert classification["type"] == "text"
    assert classification["state"] == "undetermined"
    assert classification["alternatives"]
    assert {item["reason"] for item in classification["alternatives"]} == {
        f"string_lengths_{envelope['status']}"
    }


@pytest.mark.report_lot("R1a")
def test_a_column_without_present_values_is_other_empty(tmp_path):
    classification = _classify(tmp_path, "note", ["\"\"", "\"\"", "\"\""])

    assert _pair(classification) == ("other", "empty")


@pytest.mark.report_lot("R1a")
def test_the_same_scan_gives_the_same_classification_with_any_worker_count(tmp_path):
    from tabalyst.scanner import scan

    values = [f"C{n:05d}" for n in range(300)]
    source = _csv(tmp_path, "customer_id", values)

    one = scan(source, workers=1).datasets[0].fields[0].classification
    several = scan(source, workers=2).datasets[0].fields[0].classification

    assert one == several


@pytest.mark.report_lot("R1a")
def test_CA24_secondary_properties_do_not_add_displayed_types(tmp_path):
    classification = _classify(tmp_path, "note", ["a1", "b22", "c333", "d4444"])

    assert isinstance(classification["family"], str)
    assert isinstance(classification["type"], str)
    assert isinstance(classification["traits"], list)


# --- R1b: types carried by the detectors ----------------------------------------


@pytest.mark.report_lot("R1b")
def test_CA10_long_emails_stay_email_and_do_not_become_text(tmp_path):
    # 55 to 57 letters in the local part (the detector accepts 64) make a median
    # length above the Medium bound: by length alone this column would be Text.
    values = [f"{'x' * 55}{n}@example.com" for n in range(40)]

    classification = _classify(tmp_path, "contact", values)

    assert _pair(classification) == ("contact", "email")
    assert classification["state"] == "established"


@pytest.mark.report_lot("R1b")
def test_two_categories_m_and_f_stay_enum_never_boolean(tmp_path):
    classification = _classify(tmp_path, "sexe", ["M", "F"] * 300)

    assert _pair(classification) == ("categorical", "enum")


@pytest.mark.report_lot("R1b")
def test_bare_numbers_are_neither_currency_nor_percentage(tmp_path):
    classification = _classify(tmp_path, "price", [10, 20, 35, 120, 99, 42])

    assert classification["type"] not in {"currency", "percentage"}
    assert classification["family"] == "numeric"


@pytest.mark.report_lot("R1b")
def test_two_credible_candidates_give_the_explicit_fallback(tmp_path):
    # Five digits are read by ``number`` and by ``postal_code`` alike: no choice
    # by registry order, and the technical type is not silently preferred.
    values = ["12345", "90210", "10001", "60601"] * 10
    classification = _classify(tmp_path, "code", values)

    assert classification["state"] == "undetermined"
    assert {item["type"] for item in classification["alternatives"]} == {
        "integer",
        "postal_code",
    }


# --- R2: name engine ------------------------------------------------------------


@pytest.mark.report_lot("R2")
@pytest.mark.parametrize("name", ["CustomerID", "customer_id", "CUSTOMER-ID"])
def test_CA22_naming_conventions_give_equivalent_tokens(name):
    from tabalyst.scanner.classify.names import name_tokens

    assert name_tokens(name) == ("customer", "id")


@pytest.mark.report_lot("R2")
def test_names_are_compared_without_accents_and_keep_acronym_boundaries():
    from tabalyst.scanner.classify.names import name_tokens

    assert name_tokens("Date-Naissance") == ("date", "naissance")
    assert name_tokens("ZIPCode") == ("zip", "code")
    assert name_tokens("idClient") == ("id", "client")
    assert name_tokens("Numéro civique") == ("numero", "civique")


@pytest.mark.report_lot("R2")
@pytest.mark.parametrize(
    "name", ["validity", "email_status", "birth_year", "customer_id_length"]
)
def test_CA23_adverse_names_get_no_generic_hint(name):
    from tabalyst.scanner.classify.names import name_hints

    hints = name_hints(name)

    assert not [hint for hint in hints if hint.polarity == "supports"]


@pytest.mark.report_lot("R2")
def test_contains_means_a_whole_token_never_a_substring():
    from tabalyst.scanner.classify.names import name_hints

    assert not name_hints("validity")
    assert not name_hints("identity")
    assert name_hints("billing_postal_code")


@pytest.mark.report_lot("R2")
def test_postal_code_is_not_postal_code_status():
    from tabalyst.scanner.classify.names import name_hints

    exact = {hint.rule for hint in name_hints("postal_code")}
    status = {hint.rule for hint in name_hints("postal_code_status")}

    assert "name.postal" in exact
    assert "name.postal" not in status


@pytest.mark.report_lot("R2")
def test_CA12_an_email_name_over_free_text_is_not_established(tmp_path):
    values = ["call me later", "see the notes", "unknown", "n/a for now"] * 20

    classification = _classify(tmp_path, "email", values)

    assert classification["type"] != "email"
    assert classification["state"] != "established" or classification["family"] == (
        "text"
    )
    # The name is kept as a suggestion the values do not support.
    assert ("email", "name_only") in {
        (item["type"], item["reason"]) for item in classification["alternatives"]
    }


@pytest.mark.report_lot("R2")
def test_the_names_of_json_paths_keep_their_segments():
    from tabalyst.scanner.classify.names import name_tokens

    assert name_tokens(["billing", "address", "city"]) == ("city",)


@pytest.mark.report_lot("R2")
def test_a_name_alone_creates_no_type_without_supporting_values(tmp_path):
    classification = _classify(tmp_path, "phone", ["abc", "def", "ghi", "jkl"])

    assert classification["type"] != "phone"
    assert any(
        item["reason"] == "name_only" for item in classification["alternatives"]
    )


# --- R3: identifiers ------------------------------------------------------------


@pytest.mark.report_lot("R3")
def test_CA04_a_complete_exact_unique_identifier_is_unique_id(tmp_path):
    values = [f"C{n:05d}" for n in range(1000)]

    classification = _classify(tmp_path, "customer_id", values)

    assert _pair(classification) == ("identifier", "unique_id")
    assert classification["state"] == "candidate"
    assert "observed_unique" in classification["traits"]


@pytest.mark.report_lot("R3")
@pytest.mark.parametrize("breaker", ["missing", "repeated"])
def test_CA05_a_missing_or_repeated_value_keeps_the_field_an_id(tmp_path, breaker):
    values = [f"C{n:05d}" for n in range(1000)]
    values[10] = "" if breaker == "missing" else values[11]
    # A second column keeps the empty cell a cell: in a one-column CSV an empty
    # value is a blank line, which the reader refuses.
    source = write_text(
        tmp_path,
        "data.csv",
        "customer_id,label\n" + "\n".join(f"{value},x" for value in values) + "\n",
    )

    result = run_scan(source)
    classification = field(result["datasets"][0], "customer_id")["classification"]

    assert _pair(classification) == ("identifier", "id")
    assert classification["state"] == "candidate"
    # The present values stay all distinct when a value is missing: it is the
    # missing position, not the uniqueness, that keeps the field an ID.
    assert ("observed_unique" in classification["traits"]) == (breaker == "missing")


@pytest.mark.report_lot("R3")
def test_CA05_a_limited_cardinality_keeps_the_field_an_id(tmp_path):
    values = [f"C{n:05d}" for n in range(1000)]

    classification = _classify(
        tmp_path, "customer_id", values, limits={"max_distinct_per_field": 100}
    )

    assert _pair(classification) == ("identifier", "id")


@pytest.mark.report_lot("R3")
def test_CA06_values_equal_after_trim_are_not_unique(tmp_path):
    values = [f"C{n:05d}" for n in range(50)] + [" C00001 "]

    classification = _classify(tmp_path, "customer_id", values)

    assert _pair(classification) == ("identifier", "id")


@pytest.mark.report_lot("R3")
@pytest.mark.parametrize(
    ("header", "values", "expected"),
    [
        (
            "timestamp",
            [f"2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}" for n in range(40)],
            ("temporal", "date"),
        ),
        ("price", [f"{10 + n}.{n % 100:02d}" for n in range(40)], ("numeric", "number")),
    ],
)
def test_CA07_a_distinct_first_column_of_dates_or_amounts_is_not_an_identifier(
    tmp_path, header, values, expected
):
    # The column is first and all distinct: both are traits, never a role.
    source = write_text(
        tmp_path,
        "data.csv",
        f"{header},label\n" + "\n".join(f"{v},x{i}" for i, v in enumerate(values)) + "\n",
    )

    result = run_scan(source)
    classification = field(result["datasets"][0], header)["classification"]

    assert _pair(classification) == expected
    assert {"first_column", "observed_unique"} <= set(classification["traits"])


@pytest.mark.report_lot("R3")
def test_a_unique_nameless_column_stays_outside_identifier(tmp_path):
    classification = _classify(
        tmp_path, "column_1", [f"Z{n:05d}" for n in range(500)]
    )

    assert classification["family"] != "identifier"
    assert "observed_unique" in classification["traits"]


@pytest.mark.report_lot("R3")
def test_a_field_under_a_json_array_is_never_unique_id(tmp_path):
    rows = [{"orders": [{"id": f"o{n}"}, {"id": f"p{n}"}]} for n in range(30)]
    source = write_text(
        tmp_path, "data.json", __import__("json").dumps(rows)
    )

    result = run_scan(source)
    types = {
        item["name"]: item["classification"]["type"]
        for item in result["datasets"][0]["fields"]
        if item["name"] == "id"
    }

    # Sixty distinct values, an identifier name, no missing: only the array
    # above the field keeps it from being a Unique ID.
    assert types == {"id": "id"}


@pytest.mark.report_lot("R3")
def test_unique_id_publishes_its_scope_in_the_evidence(tmp_path):
    classification = _classify(
        tmp_path, "customer_id", [f"C{n:05d}" for n in range(200)]
    )

    assert _pair(classification) == ("identifier", "unique_id")
    measures = {
        item["id"]: item["scope"]
        for item in classification["evidence"]
        if item["source"] == "measure"
    }
    assert measures["values.cardinality"] == {
        "population": "present_values",
        "of": 200,
        "partial": False,
        "accuracy": "exact",
    }
    assert measures["missing.count"]["population"] == "positions"
    assert measures["missing.count"]["of"] == 200


# --- R4: refinement by the second pass ------------------------------------------


def _limited_id(directory):
    """The Scan of a column named ``customer_id`` whose 300 distinct values the
    scan stopped counting at 50, and the forced second pass that counts them."""
    from second_pass_helpers import deep_csv

    from tabalyst.models import AnalysesBlock

    rows = [f"C{n:05d},x" for n in range(300)]
    result, _, outcome = deep_csv(
        directory, "customer_id,label", rows, limits={"max_distinct_per_field": 50}
    )
    analyses = AnalysesBlock(mode="forced", outcome="ran", deep=outcome.document)
    return result.datasets[0].fields[0], analyses


@pytest.mark.report_lot("R4")
def test_the_second_pass_turns_a_limited_id_into_a_unique_id(tmp_path):
    from tabalyst.report_classification import refine

    field_, analyses = _limited_id(tmp_path)

    first = field_.classification
    refined = refine(field_, analyses)

    assert (first.family, first.type) == ("identifier", "id")
    assert (refined.family, refined.type) == ("identifier", "unique_id")
    assert refined.state == "candidate"
    assert {"exact_distinct.distinct", "missing.count"} <= {
        item.id for item in refined.evidence
    }


@pytest.mark.report_lot("R4")
def test_without_a_valid_second_pass_the_scan_classification_is_unchanged(tmp_path):
    from tabalyst.models import AnalysesBlock
    from tabalyst.report_classification import refine

    field_, analyses = _limited_id(tmp_path)
    failed = AnalysesBlock(mode="auto", outcome="failed", reason="source changed")
    stale = analyses.deep.model_copy(
        update={
            "base": analyses.deep.base.model_copy(update={"facts_sha256": "0" * 64})
        }
    )

    # Absent, failed, or standing on another Scan: nothing is invented.
    assert refine(field_, None) == field_.classification
    assert refine(field_, failed) == field_.classification
    assert (
        refine(
            field_,
            analyses.model_copy(update={"deep": stale}),
            base=analyses.deep.base,
        )
        == field_.classification
    )


@pytest.mark.report_lot("R4")
def test_CA20_the_classification_renders_without_the_source(tmp_path):
    from tabalyst import analyze_csv
    from tabalyst.json_text import dump_json
    from tabalyst.reporting import load_profile, render_report

    source = _csv(tmp_path, "note", ["alpha", "beta", "gamma"] * 10)
    profile = analyze_csv(source)
    document = write_text(
        tmp_path, "report.json", dump_json(profile.model_dump(mode="json"))
    )
    fresh = render_report(profile)
    source.unlink()

    again = load_profile(document)
    column = again.report.datasets[0].columns[0]
    assert column.classification.family == "text"
    assert column.classification == profile.report.datasets[0].columns[0].classification
    assert not hasattr(column, "semantic_type")
    assert render_report(again) == fresh


# --- R5, R6a, R6b: findings -----------------------------------------------------


def _column_view(directory, header, values, **settings):
    """The view of the first column of a CSV. A second column of row numbers lets
    the first one hold empty cells: a line with no field at all is not a record."""
    from tabalyst import analyze_csv
    from tabalyst.reporting import dataset_views

    lines = [f"{header},row"] + [f"{value},{n}" for n, value in enumerate(values)]
    source = write_text(directory, "data.csv", "\n".join(lines) + "\n")
    profile = analyze_csv(source)
    return dataset_views(profile)[0].columns[0]


@pytest.mark.report_lot("R5")
def test_CA16_a_mostly_empty_column_reports_missing_without_error(tmp_path):
    from tabalyst.report_findings import column_findings

    values = ["x"] * 14 + [""] * 86

    findings = column_findings(_column_view(tmp_path, "note", values))

    assert findings.missing.count == 86
    assert round(findings.missing.share.percent) == 86
    assert not findings.errors.items


@pytest.mark.report_lot("R5")
def test_missing_keeps_its_five_components():
    from tabalyst.report_findings import MissingFinding

    assert {"absent", "null", "empty", "blank", "marker"} <= set(
        MissingFinding.model_fields["components"].annotation.model_fields
    )


@pytest.mark.report_lot("R5")
def test_CA17_a_partial_detector_is_not_none_detected():
    from tabalyst.report_findings import evaluation_state

    state = evaluation_state(
        detector_state="complete", eligible=1000, tested=100, found=0
    )

    assert state == "partial"


@pytest.mark.report_lot("R5")
def test_CA18_null_disabled_and_failed_stay_distinguishable():
    from tabalyst.report_findings import evaluation_state

    complete = evaluation_state("complete", eligible=10, tested=10, found=0)
    disabled = evaluation_state("disabled", eligible=0, tested=0, found=0)
    failed = evaluation_state("failed", eligible=0, tested=0, found=0)

    assert {complete, disabled, failed} == {
        "none_detected",
        "not_assessed",
        "failed",
    }


@pytest.mark.report_lot("R5")
def test_CA30_a_failed_check_is_never_counted_as_invalid():
    from tabalyst.report_findings import evaluation_state

    assert evaluation_state("failed", eligible=10, tested=0, found=0) == "failed"


@pytest.mark.report_lot("R5")
def test_CA15_repetitions_beyond_the_first_are_not_duplicated_occurrences():
    from tabalyst.report_findings import repetition_figures

    figures = repetition_figures(["A", "A", "A", "B"])

    assert figures.present == 4
    assert figures.distinct == 2
    assert figures.beyond_first == 2
    assert figures.duplicated_groups == 1
    assert figures.occurrences_in_duplicated_groups == 3


@pytest.mark.report_lot("R5")
def test_a_share_over_a_zero_population_is_unavailable_not_nan():
    from tabalyst.report_findings import share

    result = share(0, 0)

    assert result.percent is None
    assert result.accuracy == "unavailable"


@pytest.mark.report_lot("R5")
def test_CA26_equal_counts_without_proven_overlap_are_not_merged():
    from tabalyst.report_findings import Finding, Population, merge_proven

    def finding(code):
        return Finding(
            code=code,
            cls="issue",
            field="f1",
            count=36,
            unit="occurrences",
            population=Population(kind="content_strings", size=100),
            accuracy="exact",
        )

    assert (
        len(merge_proven([finding("pattern.minority"), finding("length.minority")]))
        == 2
    )


@pytest.mark.report_lot("R5")
def test_CA29_a_recommended_finding_is_never_reported():
    from tabalyst.scanner.classify.catalog import FINDINGS

    recommended = [item for item in FINDINGS if item.status == "recommended"]
    active = [item for item in FINDINGS if item.status == "active"]

    assert recommended and active
    assert not {item.code for item in recommended} & {item.code for item in active}


@pytest.mark.report_lot("R6a")
def test_CA11_an_impossible_calendar_date_is_an_error_and_an_ambiguous_one_is_not(
    tmp_path,
):
    from tabalyst.report_findings import column_findings

    values = ["2025-01-15"] * 30 + ["2025-02-30", "03/04/2025"]

    findings = column_findings(_column_view(tmp_path, "signed", values))

    assert any(
        item.code == "temporal.invalid_calendar" for item in findings.errors.items
    )
    assert all(item.code != "temporal.ambiguous_date" for item in findings.errors.items)


@pytest.mark.report_lot("R6b")
def test_CA11_an_ambiguous_date_is_an_issue(tmp_path):
    from tabalyst.report_findings import column_findings

    values = ["2025-01-15"] * 30 + ["2025-02-30", "03/04/2025"]

    findings = column_findings(_column_view(tmp_path, "signed", values))

    assert any(item.code == "temporal.ambiguous_date" for item in findings.issues.items)


@pytest.mark.report_lot("R6a")
def test_CA13_a_value_a_detector_does_not_recognize_is_not_an_error(tmp_path):
    from tabalyst.report_findings import column_findings

    values = ["K1A 0B1"] * 30 + ["hello"]

    findings = column_findings(_column_view(tmp_path, "zone", values))

    assert not findings.errors.items


@pytest.mark.report_lot("R6a")
def test_an_error_needs_an_established_classification(tmp_path):
    from tabalyst.report_findings import column_findings

    values = ["abc@x.org", "bad address", "no", "yes"] * 5

    findings = column_findings(_column_view(tmp_path, "email", values))

    assert not findings.errors.items


@pytest.mark.report_lot("R6a")
def test_CA21_json_occurrences_are_not_reported_as_rows(tmp_path):
    from scan_helpers import write_json

    from tabalyst import analyze_csv
    from tabalyst.report_findings import column_findings
    from tabalyst.reporting import dataset_views

    records = [{"emails": ["a@x.org", "b@x.org", "c@x.org"]} for _ in range(100)]
    records[0]["emails"].append("a b@x.org")
    records[1]["emails"].append("c d@x.org")
    profile = analyze_csv(write_json(tmp_path, "data.json", records))
    column = next(
        item for item in dataset_views(profile)[0].columns if item.path == "emails[]"
    )

    error = column_findings(column).errors.items[0]

    assert (error.unit, error.count) == ("occurrences", 2)
    assert error.population.size == 302


@pytest.mark.report_lot("R5")
def test_CA14_three_categories_and_twenty_occurrences_are_distinct_figures():
    from tabalyst.report_findings import label_for

    assert label_for("categorical.case_variants", 3, "groups") == (
        "3 spelling-variant groups"
    )
    assert label_for("categorical.case_variants", 1, "groups") == (
        "1 spelling-variant group"
    )


@pytest.mark.report_lot("R6b")
def test_an_identifier_repetition_is_an_issue_with_its_unit(tmp_path):
    from tabalyst.report_findings import column_findings

    values = [f"C{n:05d}" for n in range(100)] + ["C00001", "C00002"]

    findings = column_findings(_column_view(tmp_path, "customer_id", values))

    assert any(
        item.code == "identifier.repetition" and item.unit == "occurrences"
        for item in findings.issues.items
    )


# --- R7, R8: views --------------------------------------------------------------


@pytest.mark.report_lot("R7")
def test_CA25_an_overview_over_several_patterns_names_no_subsidiary(tmp_path):
    from tabalyst.report_overview import overview_text

    values = ["CLI-0001", "CLI-0002", "X9", "X10", "A-1-B", "A-2-B"] * 10

    text = overview_text(_column_view(tmp_path, "code", values)).lower()

    assert "subsidiar" not in text and "filiale" not in text


@pytest.mark.report_lot("R7")
def test_an_overview_never_says_exact_for_a_limited_measure(tmp_path):
    from tabalyst.report_overview import overview_for

    values = [f"C{n:05d}" for n in range(100)] + ["C00001"]
    lines = ["customer_id,row"] + [f"{v},{n}" for n, v in enumerate(values)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    from tabalyst import analyze_csv
    from tabalyst.report_config import ReportConfig
    from tabalyst.reporting import dataset_views
    from tabalyst.scanner import ScanConfig

    config = ReportConfig(
        scan=ScanConfig.model_validate({"limits": {"max_distinct_per_field": 50}})
    )
    column = dataset_views(analyze_csv(source, config))[0].columns[0]

    overview = overview_for(column)

    assert {fact.accuracy for fact in overview.facts if fact.name == "distinct"} == {
        "lower_bound"
    }
    from tabalyst.report_overview import overview_sentence

    assert overview_sentence(overview).lower().startswith("at least")


@pytest.mark.report_lot("R8")
@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_CA19_masked_and_hidden_values_leave_no_raw_example(tmp_path, mode):
    from tabalyst import analyze_csv
    from tabalyst.report_config import ReportConfig
    from tabalyst.report_details import details_for
    from tabalyst.report_overview import overview_for
    from tabalyst.reporting import dataset_views
    from tabalyst.scanner import ScanConfig

    values = [f"user{n}@example.com" for n in range(30)]
    lines = ["contact,row"] + [f"{v},{n}" for n, v in enumerate(values)]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    config = ReportConfig(
        scan=ScanConfig.model_validate({"exposure": {"sensitive_values": mode}})
    )
    column = dataset_views(analyze_csv(source, config))[0].columns[0]

    assert column.exposure == mode
    assert "user" not in details_for(column).model_dump_json()
    assert "user" not in repr(details_for(column))
    assert "user" not in overview_for(column).model_dump_json()


@pytest.mark.report_lot("R8")
def test_CA28_a_report_without_details_links_to_no_missing_page(tmp_path):
    import re

    from tabalyst import analyze

    source = write_text(tmp_path, "data.csv", "name\nAlice\nBob\n")
    for details in (False, True):
        output = tmp_path / f"report-{details}.html"
        analyze(source, output, details=details)
        hrefs = re.findall(r'class="column-link[^"]*" href="([^"]+)"', output.read_text("utf-8"))
        assert bool(hrefs) is details
        assert all((tmp_path / href).is_file() for href in hrefs)


# --- R9a, R9b: table ------------------------------------------------------------


@pytest.mark.report_lot("R9a")
def test_CA01_the_table_has_the_eight_columns_in_order(tmp_path):
    from columns_table_helpers import columns_table

    from tabalyst import analyze_csv
    from tabalyst.reporting import render_report

    source = write_text(tmp_path, "data.csv", "name,amount\nAlice,1\nBob,2\n")

    headers = columns_table(render_report(analyze_csv(source))).headers

    assert headers == [
        "Column",
        "Type family",
        "Type",
        "Overview",
        "Missing",
        "Errors",
        "Issues",
        "Details",
    ]


@pytest.mark.report_lot("R9a")
def test_CA02_a_family_filter_does_not_select_a_homonymous_type(tmp_path):
    from columns_table_helpers import columns_table

    from tabalyst import analyze_csv
    from tabalyst.report_labels import FAMILY_LABELS, TYPE_LABELS
    from tabalyst.reporting import render_report

    lines = ["email,phone,note"] + [
        f"user{n}@example.com,(514) 555-{n:04d},free text number {n} here"
        for n in range(40)
    ]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")

    rows = columns_table(render_report(analyze_csv(source))).rows

    contact = [r for r in rows if r.cells[1]["data-v"] == "contact"]
    assert {r.cells[0]["data-v"] for r in contact} == {"email", "phone"}
    assert {r.cells[2]["data-v"] for r in contact} == {"contact/email", "contact/phone"}
    # A family code is never the code of a type: the two filters cannot meet.
    assert not set(TYPE_LABELS) & set(FAMILY_LABELS)


@pytest.mark.report_lot("R9a")
def test_CA03_two_columns_with_the_same_name_keep_their_own_identity(tmp_path):
    from columns_table_helpers import columns_table

    from tabalyst import analyze_csv
    from tabalyst.reporting import dataset_views, render_report

    source = write_text(tmp_path, "data.csv", "name,name\n1,a\n2,b\n")
    profile = analyze_csv(source)
    links = {
        (profile.report.datasets[0].id, c.id): f"{c.id}.html"
        for c in profile.report.datasets[0].columns
    }

    html = render_report(profile, column_links=links, views=dataset_views(profile))

    rows = columns_table(html).rows
    assert [r.attrs["data-field"] for r in rows] == ["column_1", "column_2"]
    for row in rows:
        assert f"{row.attrs['data-field']}.html" in html


@pytest.mark.report_lot("R9b")
def test_CA27_previews_are_reachable_without_hover_or_color(tmp_path):
    from columns_table_helpers import columns_table

    from tabalyst import analyze_csv
    from tabalyst.reporting import render_report

    rows = ["city"] + ["Paris"] * 5 + ["PARIS"] * 2 + ["paris"] * 2
    source = write_text(tmp_path, "data.csv", "\n".join(rows) + "\n")

    table = columns_table(render_report(analyze_csv(source)))

    row = table.rows[0]
    for index in (5, 6):  # Errors, Issues: a label or a state, never a title alone
        cell = row.cells[index]
        assert "title" not in cell.attrs
        for attrs, _ in cell.buttons:
            # a button, not a hover: it names the dialog it opens and its state
            assert attrs["type"] == "button" and attrs["aria-haspopup"] == "dialog"
            assert attrs["aria-expanded"] == "false" and attrs["data-pop"]
    issues = row.cells[6]
    assert issues.buttons and issues.pops
    # the class is written (hidden text in the label, a word in the dialog)
    assert "Issue" in issues.pops[0].text
    assert any("Issue: " in text for text in issues.button_texts())
