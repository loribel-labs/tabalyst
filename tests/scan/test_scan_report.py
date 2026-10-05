# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: the report built on Tabalyst Scan (lot 5a).

The demo facts pinned below were equal to those of the former pandas engine
when the parity tests of lot 5a last ran, before lot 5c removed that engine;
then the presentation decisions of lot 5a (design 12.6 and 12.8, O16).
"""

import json
from pathlib import Path

import pytest
from scan_helpers import write_text

from tabalyst import ConfigurationError
from tabalyst.report_config import ReportConfig, resolve_report_config
from tabalyst.reporting import render_report
from tabalyst.scanner.readers import csv_reader
from tabalyst.service import analyze_csv

pytestmark = pytest.mark.lot("5a")

EXAMPLES = Path(__file__).parents[2] / "examples"
DEMO_CONFIG = EXAMPLES / "config.json"
# Dataset facts of the demos shared with the former pandas engine.
DEMO_FACTS = {
    "basic": {
        "row_count": 5,
        "column_count": 6,
        "cell_count": 30,
        "missing_count": 2,
        "trim_count": 0,
        "collapse_internal_whitespace_count": 0,
        "duplicate_row_count": 1,
        "empty_row_count": 0,
        "empty_column_count": 0,
        "constant_column_count": 0,
        "with_issues_column_count": 2,
    },
    "insurance-customers": {
        "row_count": 3000,
        "column_count": 34,
        "cell_count": 102000,
        "missing_count": 12532,
        "trim_count": 0,
        "collapse_internal_whitespace_count": 129,
        "duplicate_row_count": 8,
        "empty_row_count": 0,
        "empty_column_count": 0,
        "constant_column_count": 0,
        "with_issues_column_count": 15,
    },
}
DUPLICATE_ROWS = {
    "basic": [4],
    "insurance-customers": [1521, 1814, 1999, 2064, 2268, 2527, 2543, 2627],
}


def _config(**scan) -> ReportConfig:
    return ReportConfig.model_validate({"scan": scan})


def _dataset(source, config=None):
    """The report of a CSV source and its only dataset."""
    report = analyze_csv(source, config)
    (dataset,) = report.datasets
    return report, dataset


def _issues(profile) -> dict:
    return {issue.code: issue for issue in profile.issues}


@pytest.mark.parametrize("demo", ["basic", "insurance-customers"])
def test_demo_facts_are_those_of_the_former_engine(demo):
    source = EXAMPLES / "input" / f"{demo}.csv"

    _report, current = _dataset(source, resolve_report_config([DEMO_CONFIG]))

    summary = current.summary.model_dump()
    assert {name: summary[name] for name in DEMO_FACTS[demo]} == DEMO_FACTS[demo]
    assert current.summary.duplicate_row_status == "complete"
    issue = _issues(current)["duplicate_rows"]
    assert (issue.count, issue.row_numbers) == (
        DEMO_FACTS[demo]["duplicate_row_count"],
        DUPLICATE_ROWS[demo],
    )
    assert len(current.preview) == min(20, DEMO_FACTS[demo]["row_count"])


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
