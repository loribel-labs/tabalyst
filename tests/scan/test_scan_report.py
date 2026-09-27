"""Scan contract: the report built on Tabalyst Scan (lot 5a).

Parity with the pandas engine on both public demos, each known difference
listed explicitly, then the presentation decisions of lot 5a (design 12.6 and
12.8, O16). The pandas engine is removed in lot 5c with the parity half of
this file.
"""

import json
from pathlib import Path

import pytest
from scan_helpers import write_text

from tabalyst import ConfigurationError
from tabalyst.analysis import analyze_csv_file
from tabalyst.config import AnalysisConfig
from tabalyst.report_config import ReportConfig, resolve_report_config
from tabalyst.reporting import render_report
from tabalyst.scanner.readers import csv_reader
from tabalyst.service import analyze_csv

pytestmark = pytest.mark.lot("5a")

EXAMPLES = Path(__file__).parents[2] / "examples"
DEMO_CONFIG = EXAMPLES / "config.json"
# The pandas engine settings equivalent to examples/config.json.
LEGACY_DEMO_CONFIG = AnalysisConfig(
    missing_values=["", "N/A", "NULL"], preview_rows=20
)
DATE_COLUMNS = {
    "date_naissance",
    "date_debut",
    "date_fin",
    "date_creation",
    "date_modification",
    "date_reclamation",
}
SENSITIVE_COLUMNS = {"courriel", "telephone"}
# Semantic types that differ from the pandas engine (``enum`` and ``date``
# only), by column name.
NEW_SEMANTIC_TYPES = {
    "code_postal": "postal_code",
    "courriel": "email",
    "telephone": "phone",
    # 440 present values: below the 500 values the enumeration detector
    # needs, where the pandas engine counted 3,000 rows.
    "reclamation_status": None,
}


def _config(**scan) -> ReportConfig:
    return ReportConfig.model_validate({"scan": scan})


def _profiles(demo: str):
    source = EXAMPLES / "input" / f"{demo}.csv"
    legacy = analyze_csv_file(source, LEGACY_DEMO_CONFIG)
    report = analyze_csv(source, resolve_report_config([DEMO_CONFIG]))
    assert report.format_revision == 4
    assert report.source.sha256 == legacy.source.sha256
    assert report.source.size_bytes == legacy.source.size_bytes
    (current,) = report.datasets
    return legacy, current


def _dataset(source, config=None):
    """The report of a CSV source and its only dataset."""
    report = analyze_csv(source, config)
    (dataset,) = report.datasets
    return report, dataset


def _issues(profile) -> dict:
    return {issue.code: issue for issue in profile.issues}


@pytest.mark.parametrize("demo", ["basic", "insurance-customers"])
def test_dataset_facts_match_the_pandas_engine(demo):
    legacy, current = _profiles(demo)

    for name in (
        "row_count",
        "column_count",
        "cell_count",
        "missing_count",
        "missing_percent",
        "trim_count",
        "collapse_internal_whitespace_count",
        "duplicate_row_count",
        "empty_row_count",
        "empty_column_count",
        "constant_column_count",
        "numeric_column_count",
        "date_column_count",
        "string_column_count",
        "with_issues_column_count",
    ):
        assert getattr(current.summary, name) == getattr(legacy.summary, name), name
    legacy_issues, current_issues = _issues(legacy), _issues(current)
    for code in (
        "duplicate_rows",
        "missing_values",
        "empty_columns",
        "trimmed_cells",
        "collapsed_whitespace",
        "constant_columns",
        "ambiguous_headers",
    ):
        assert (code in current_issues) == (code in legacy_issues), code
        if code in legacy_issues:
            assert (
                current_issues[code].model_dump() == legacy_issues[code].model_dump()
            ), code
    # Date columns are no longer mixed: their ambiguity has its own issue.
    def mixed(issues):
        return issues["mixed_types"].column_ids if "mixed_types" in issues else []

    date_ids = {column.id for column in legacy.columns if column.name in DATE_COLUMNS}
    assert mixed(current_issues) == [
        column_id for column_id in mixed(legacy_issues) if column_id not in date_ids
    ]
    ambiguous = [
        column
        for column in current.columns
        if column.date_profile and column.date_profile.ambiguous_count
    ]
    if ambiguous:
        issue = current_issues["ambiguous_dates"]
        assert issue.column_ids == [column.id for column in ambiguous]
        assert issue.count == current.date_summary.ambiguous_count
    else:
        assert "ambiguous_dates" not in current_issues


@pytest.mark.parametrize("demo", ["basic", "insurance-customers"])
def test_column_facts_match_the_pandas_engine(demo):
    legacy, current = _profiles(demo)

    for old, new in zip(legacy.columns, current.columns, strict=True):
        name = old.name
        assert (new.id, new.name, new.position) == (old.id, old.name, old.position)
        assert new.missing_count == old.missing_count, name
        assert new.missing_percent == old.missing_percent, name
        assert new.normalization.model_dump() == old.normalization.model_dump(), name
        assert new.distinct_count == old.distinct_count, name
        assert new.with_issues == old.with_issues, name
        if name in DATE_COLUMNS:
            assert (old.inferred_type, new.inferred_type) == ("mixed", "date")
        else:
            assert new.inferred_type == old.inferred_type, name
            assert new.type_counts == old.type_counts, name
            assert new.type_error_count == old.type_error_count, name
        expected_semantic = NEW_SEMANTIC_TYPES.get(
            name, "enumeration" if old.semantic_type == "enum" else old.semantic_type
        )
        assert new.semantic_type == expected_semantic, name
        assert new.exposure == ("mask" if name in SENSITIVE_COLUMNS else None), name

        if old.numeric is None:
            assert new.numeric is None, name
        else:
            for measure in ("minimum", "maximum", "range", "mean", "median"):
                assert getattr(new.numeric, measure) == pytest.approx(
                    getattr(old.numeric, measure), rel=1e-12
                ), (name, measure)

        assert (new.string_profile is None) == (old.string_profile is None), name
        if old.string_profile is not None:
            old_strings, new_strings = old.string_profile, new.string_profile
            for measure in (
                "status",
                "present_count",
                "minimum_length",
                "maximum_length",
                "mean_length",
                "median_length",
                "distinct_length_count",
                "fixed_length",
            ):
                assert getattr(new_strings, measure) == getattr(
                    old_strings, measure
                ), (name, measure)
            assert [
                (item.length, item.count, item.percent, item.relative_percent)
                for item in new_strings.length_distribution
            ] == [
                (item.length, item.count, item.percent, item.relative_percent)
                for item in old_strings.length_distribution
            ], name

        assert (new.date_profile is None) == (old.date_profile is None), name
        if old.date_profile is not None:
            old_dates, new_dates = old.date_profile, new.date_profile
            for measure in (
                "status",
                "present_count",
                "valid_count",
                "ambiguous_count",
                "invalid_date_count",
                "not_date_count",
                "format_count",
            ):
                assert getattr(new_dates, measure) == getattr(old_dates, measure), (
                    name,
                    measure,
                )
            assert [item.model_dump() for item in new_dates.formats] == [
                item.model_dump() for item in old_dates.formats
            ], name
            # Neither demo has one-sided evidence, so the pandas engine did not
            # resolve anything either.
            assert old_dates.ambiguous_order_source is None

        if old.value_profile.selection == "complete" and name not in SENSITIVE_COLUMNS:
            assert new.value_profile.model_dump() == old.value_profile.model_dump(), name
            assert new.examples == old.examples, name


@pytest.mark.parametrize("demo", ["basic", "insurance-customers"])
def test_preview_matches_except_masked_values(demo):
    legacy, current = _profiles(demo)
    sensitive = [
        column.position - 1
        for column in current.columns
        if column.exposure == "mask"
    ]

    assert [row.row_number for row in current.preview] == [
        row.row_number for row in legacy.preview
    ]
    for old, new in zip(legacy.preview, current.preview, strict=True):
        for index, (old_value, new_value) in enumerate(
            zip(old.values, new.values, strict=True)
        ):
            if index in sensitive and old_value:
                assert new_value != old_value
                assert len(new_value) == len(old_value)
            else:
                assert new_value == old_value


# Decisions of lot 5a -----------------------------------------------------------


def test_ambiguous_dates_are_never_resolved_from_column_evidence(tmp_path):
    source = write_text(
        tmp_path, "dates.csv", "day\n01/02/2026\n13/02/2026\n25/12/2026\n"
    )

    profile_report, profile = _dataset(source)

    dates = profile.columns[0].date_profile
    assert dates.ambiguous_count == 1
    assert dates.resolved_ambiguous_order is None
    assert dates.ambiguous_order_source is None
    assert dates.ambiguity_evidence == {"DMY": 2, "MDY": 0}
    assert profile.columns[0].inferred_type == "date"
    assert profile.columns[0].with_issues is True
    assert _issues(profile)["ambiguous_dates"].count == 1
    html = render_report(profile_report)
    assert "Only DMY is attested" in html
    assert "scan.detectors.date.ambiguous_order" in html


def test_configured_order_resolves_ambiguous_dates(tmp_path):
    source = write_text(tmp_path, "dates.csv", "day\n01/02/2026\n13/02/2026\n")

    _profile_report, profile = _dataset(
        source, _config(detectors={"date": {"ambiguous_order": "DMY"}})
    )

    dates = profile.columns[0].date_profile
    assert (dates.valid_count, dates.ambiguous_count) == (2, 0)
    assert (dates.resolved_ambiguous_order, dates.ambiguous_order_source) == (
        "DMY",
        "config",
    )
    assert [item.format for item in dates.formats] == ["DD/MM/YYYY"]
    assert "ambiguous_dates" not in _issues(profile)


def _contacts(tmp_path) -> Path:
    rows = "".join(f"user{index}@example.com,{index}\n" for index in range(3))
    return write_text(tmp_path, "contacts.csv", "email,n\n" + rows + ",3\n")


def test_sensitive_values_are_masked_by_default(tmp_path):
    profile_report, profile = _dataset(_contacts(tmp_path))

    email = profile.columns[0]
    assert email.semantic_type == "email"
    assert email.exposure == "mask"
    assert email.distinct_count == 3
    assert all("@" in value and "user" not in value for value in email.examples)
    assert profile.preview[0].values == ["aaaa9@aaaaaaa.aaa", "0"]
    # Missing cells are not values: they stay as read.
    assert profile.preview[3].values == ["", "3"]
    assert "Masked values" in render_report(profile_report)


def test_sensitive_values_can_be_hidden_or_shown(tmp_path):
    source = _contacts(tmp_path)

    hidden_report, hidden = _dataset(source, _config(exposure={"sensitive_values": "hide"}))
    _shown_report, shown = _dataset(source, _config(exposure={"sensitive_values": "show"}))

    assert hidden.columns[0].examples == []
    assert hidden.preview[0].values == [None, "0"]
    assert ">hidden<" in render_report(hidden_report)
    assert shown.columns[0].exposure == "show"
    assert shown.preview[0].values == ["user0@example.com", "0"]
    assert "user0@example.com" in shown.columns[0].examples


def test_limited_measures_are_reported_not_invented(tmp_path):
    rows = "".join(f"{index},v{index}\n" for index in range(5))
    source = write_text(tmp_path, "wide.csv", "n,label\n" + rows)

    profile_report, profile = _dataset(source, _config(limits={"max_distinct_per_field": 2}))

    for column in profile.columns:
        assert column.distinct_count is None
    assert profile.columns[0].numeric.minimum == 0
    assert profile.columns[0].numeric.median is None
    assert _issues(profile)["limited_measures"].column_ids == ["column_1", "column_2"]
    assert "limited" in render_report(profile_report)


def test_records_excluded_by_the_tolerant_policy_are_an_issue(tmp_path):
    source = write_text(tmp_path, "rows.csv", "a,b\n1,2\n3\n4,5\n6,7,8\n")

    _profile_report, profile = _dataset(source, _config(errors={"policy": "tolerant"}))

    assert profile.summary.row_count == 2
    issue = _issues(profile)["excluded_records"]
    assert (issue.severity, issue.count, issue.row_numbers) == ("warning", 2, [2, 4])
    assert [row.row_number for row in profile.preview] == [1, 3]


def test_report_reads_the_csv_once(tmp_path, monkeypatch):
    source = write_text(tmp_path, "data.csv", "a\n1\n1\n")
    opened = []
    original = csv_reader.CsvReader.__iter__

    def counting(self):
        opened.append(self.path)
        return original(self)

    monkeypatch.setattr(csv_reader.CsvReader, "__iter__", counting)
    _profile_report, profile = _dataset(source)

    assert opened == [source]
    assert profile.summary.duplicate_row_count == 1


def test_report_settings_moved_to_scan_are_named(tmp_path):
    config = write_text(
        tmp_path, "config.json", json.dumps({"missing_values": ["", "NA"]})
    )

    with pytest.raises(ConfigurationError, match="scan.values.null_markers"):
        resolve_report_config([config])


def test_top_level_csv_settings_must_agree_with_scan_csv(tmp_path):
    old_style = write_text(
        tmp_path, "old.json", json.dumps({"csv": {"delimiter": ";"}})
    )
    both = write_text(
        tmp_path,
        "both.json",
        json.dumps({"csv": {"delimiter": ";"}, "scan": {"csv": {"delimiter": ";"}}}),
    )

    with pytest.raises(ConfigurationError, match="scan.csv.delimiter"):
        resolve_report_config([old_style])
    assert resolve_report_config([both]).scan.csv.delimiter == ";"


def test_report_needs_every_column(tmp_path):
    source = write_text(tmp_path, "wide.csv", "a,b,c,d\n1,2,3,4\n")

    with pytest.raises(ConfigurationError, match="max_fields"):
        analyze_csv(source, _config(limits={"max_fields": 2}))


def test_explicit_csv_options_win_over_the_top_level_check(tmp_path):
    shared = write_text(
        tmp_path, "shared.json", json.dumps({"csv": {"delimiter": ";"}})
    )

    config = resolve_report_config([shared], separator=";")

    assert config.scan.csv.delimiter == ";"


def test_legacy_analysis_config_is_rejected_clearly(tmp_path):
    source = write_text(tmp_path, "data.csv", "a\n1\n")

    with pytest.raises(TypeError, match="ReportConfig"):
        analyze_csv(source, AnalysisConfig())

