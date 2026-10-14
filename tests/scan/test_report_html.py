# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sections of the HTML report that read the findings of the Scan (lot 5):
observations, limits, inferred patterns, row sample and qualified counts.

Everything is read from the document (design 18.14): the tests build a profile
and look at the views and at the page, never at the scanner.
"""

import pytest
from scan_helpers import write_text

from tabalyst.report_config import ReportConfig
from tabalyst.reporting import dataset_views, render_column_report, render_report
from tabalyst.scan_document import base_of
from tabalyst.scanner.rowsample import RowPriority
from tabalyst.scanner.validation import check_scan
from tabalyst.service import analyze_csv


def _config(report: dict | None = None, **scan) -> ReportConfig:
    return ReportConfig.model_validate({**(report or {}), "scan": scan})


def _csv(tmp_path, header: str, rows) -> object:
    return write_text(tmp_path, "data.csv", header + "\n" + "\n".join(rows) + "\n")


# Row sample -----------------------------------------------------------------


def test_report_keeps_the_start_the_end_and_the_smallest_middle_priorities(tmp_path):
    source = _csv(tmp_path, "n", [str(n) for n in range(1, 501)])
    config = _config(
        {"row_sample": {"start": 3, "middle": 5, "end": 2}},
        records={"sample": {"rows": 100, "edge": 10}},
    )

    profile = analyze_csv(source, config)

    sample = profile.datasets[0].records.sample
    assert (sample.kept, sample.of) == (10, 100)
    starts = [row.record for row in sample.rows if row.origins == ["start"]]
    ends = [row.record for row in sample.rows if row.origins == ["end"]]
    middle = [row for row in sample.rows if row.origins == ["middle"]]
    assert starts == [1, 2, 3]
    assert ends == [499, 500]
    # The middle is what a bottom-k of that size keeps: an exact subset.
    priority = RowPriority(profile.config.random_seed)
    full = analyze_csv(source, _config(records={"sample": {"rows": 100, "edge": 10}}))
    scan_middle = [
        row.record
        for row in full.datasets[0].records.sample.rows
        if row.origins == ["middle"]
    ]
    expected = sorted(scan_middle, key=priority.at)[:5]
    assert sorted(row.record for row in middle) == sorted(expected)
    # The reduced base still satisfies the invariants of a Scan base.
    assert check_scan(base_of(profile)) == []


def test_report_end_rows_are_the_last_ones_and_never_more_than_the_scan_kept(tmp_path):
    source = _csv(tmp_path, "n", [str(n) for n in range(1, 501)])
    scan = {"records": {"sample": {"rows": 100, "edge": 5}}}

    def ends(count: int) -> list[int]:
        config = _config({"row_sample": {"start": 0, "middle": 0, "end": count}}, **scan)
        rows = analyze_csv(source, config).datasets[0].records.sample.rows
        return [row.record for row in rows]

    assert ends(3) == [498, 499, 500]
    # Asking for more than the scan kept gives what it kept, the last ones.
    assert ends(9) == [496, 497, 498, 499, 500]


def test_report_with_no_row_says_so_and_keeps_the_header(tmp_path):
    source = _csv(tmp_path, "n", [str(n) for n in range(50)])
    config = _config({"row_sample": {"start": 0, "middle": 0, "end": 0}})

    profile = analyze_csv(source, config)
    html = render_report(profile)

    sample = profile.datasets[0].records.sample
    assert (sample.kept, sample.of) == (0, 50)
    assert "This report keeps no row" in html
    assert check_scan(base_of(profile)) == []


def test_small_dataset_rows_are_all_shown_in_their_groups(tmp_path):
    source = _csv(tmp_path, "n", [str(n) for n in range(1, 8)])

    views = dataset_views(analyze_csv(source))

    rows = views[0].rows.rows
    assert [row.record for row in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert views[0].rows.sample.complete is True


def test_html_labels_the_three_parts_of_the_sample(tmp_path):
    source = _csv(tmp_path, "n", [str(n) for n in range(1, 301)])
    config = _config(records={"sample": {"rows": 100, "edge": 10}})

    html = render_report(analyze_csv(source, config))

    for word in ("Start", "Sampled", "End"):
        assert f'<span class="pill">{word}</span>' in html
    assert "not uniform over the whole file" in html
    assert "records 11 to 290" in html


def test_preview_settings_are_refused_with_their_new_place():
    from tabalyst.scanner import ScanConfig

    with pytest.raises(ValueError, match="scan.records.sample.edge"):
        ScanConfig.model_validate({"records": {"preview": 20}})


# Observations ---------------------------------------------------------------


def test_missing_values_are_a_remark_and_not_a_quality_issue(tmp_path):
    source = _csv(tmp_path, "a,b", ["1,x", "2,", "3,x", "4,"])

    column = {c.name: c for c in dataset_views(analyze_csv(source))[0].columns}["b"]

    assert column.has_observations
    assert not column.has_quality_issues
    assert column.quality[0].observation.rule == "missing_values"
    assert column.quality[0].status_word == "Remark"


def test_a_mixed_column_is_a_candidate_anomaly(tmp_path):
    source = _csv(tmp_path, "a", [str(n) for n in range(30)] + ["x", "y", "z"])

    view = dataset_views(analyze_csv(source))[0]

    column = view.columns[0]
    assert column.has_quality_issues
    assert view.quality_issue_column_count == 1
    html = render_report(analyze_csv(source))
    assert "Candidate anomaly" in html
    assert 'data-mode="issue"' in html


def test_a_limited_duplicate_count_is_written_as_a_lower_bound(tmp_path):
    source = _csv(tmp_path, "a", [str(n % 20) for n in range(200)])

    html = render_report(
        analyze_csv(source, _config(limits={"max_tracked_records": 5}))
    )

    assert "Duplicate rows beyond their first occurrence" in html
    assert 'class="acc acc-at_least"' in html
    assert "≥ " in html


def test_without_observations_the_report_says_not_computed(tmp_path):
    source = _csv(tmp_path, "a,b", ["1,x", "2,", "3,y"])
    profile = analyze_csv(source, _config(observations={"enabled": False}))

    view = dataset_views(profile)[0]
    html = render_report(profile)

    assert view.quality.available is False
    assert view.columns[0].quality == []
    assert html.count("Not computed") >= 2


# Qualified counts -------------------------------------------------------------


def test_a_limited_cardinality_has_a_bound_and_an_estimate(tmp_path):
    source = _csv(tmp_path, "k", [f"key-{n:05d}" for n in range(500)])

    view = dataset_views(
        analyze_csv(source, _config(limits={"max_distinct_per_field": 50}))
    )[0].columns[0]

    assert view.distinct.kind == "at_least"
    assert view.distinct.value == 51
    assert view.distinct.estimate is not None
    assert 300 < view.distinct.estimate < 800
    assert view.distinct.error is not None


def test_a_complete_cardinality_is_exact(tmp_path):
    source = _csv(tmp_path, "k", ["a", "b", "a"])

    view = dataset_views(analyze_csv(source))[0].columns[0]

    assert (view.distinct.kind, view.distinct.value) == ("exact", 2)


# Patterns ---------------------------------------------------------------------


def test_patterns_section_lists_the_patterns_and_the_unmatched(tmp_path):
    source = _csv(
        tmp_path,
        "code",
        [f"AB-{n:04d}" for n in range(40)] + [f"X{n}" for n in range(3)],
    )
    profile = analyze_csv(source)

    html = render_report(profile)
    view = dataset_views(profile)[0].columns[0].patterns

    assert view.status == "complete"
    assert view.rows[0].role == "principal"
    assert 'id="patterns"' in html
    assert "AB" in html
    assert 'class="acc acc-exact"' in html


def test_examples_missing_from_a_reduced_report_are_counted_not_invented(tmp_path):
    source = _csv(tmp_path, "code", [f"AB-{n:04d}" for n in range(300)])
    config = _config(
        {"value_examples": {"kept_per_column": 1}},
        limits={"max_samples": 50, "max_distinct_per_field": 50},
    )

    view = dataset_views(analyze_csv(source, config))[0].columns[0].patterns

    assert view.status == "complete"
    pattern = view.entry.all_patterns()[0]
    shown = view.examples[pattern.id]
    assert len(shown) + view.unresolved[pattern.id] == len(pattern.examples)
    assert len(shown) <= 1


def test_small_numbers_have_no_pattern_and_say_why(tmp_path):
    source = _csv(tmp_path, "n", [str(n) for n in range(20)])

    view = dataset_views(analyze_csv(source))[0].columns[0].patterns

    assert view.status == "not_applicable"
    assert view.reason == "small_integers"
    assert "counts or measures" in view.reason_text


def test_patterns_are_missing_when_the_inference_is_off(tmp_path):
    source = _csv(tmp_path, "code", [f"AB-{n:04d}" for n in range(30)])
    profile = analyze_csv(source, _config(pattern_inference={"enabled": False}))

    html = render_report(profile)

    assert dataset_views(profile)[0].columns[0].patterns.status == "missing"
    assert 'id="patterns"' not in html
    assert "disabled by <code>scan.pattern_inference.enabled</code>" in html


# Column page --------------------------------------------------------------------


def test_column_page_reads_its_observations_patterns_and_rows(tmp_path):
    source = _csv(tmp_path, "code,n", [f"AB-{n:04d},1" for n in range(30)] + [",2"])
    profile = analyze_csv(source)
    view = dataset_views(profile)[0]

    page = render_column_report(profile, view, view.columns[0], "../report.html")

    assert "Missing values" in page
    assert "Remark" in page
    assert 'id="patterns"' in page
    assert 'id="sample"' in page
    assert "Row 1" in page


def test_a_limit_that_is_not_a_setting_does_not_point_to_one():
    from tabalyst.report_labels import REASON_NOTES, REASON_SETTINGS

    # The exposure withholds the values of a column: no setting raises it.
    assert "exposure" not in REASON_SETTINGS
    assert "exposure" in REASON_NOTES
    # The budgets of the discovery of patterns are settings.
    for budget in ("max_values", "max_families", "max_patterns_per_family", "max_patterns"):
        assert REASON_SETTINGS[budget] == f"scan.pattern_inference.{budget}"


# Hierarchy of the patterns (Patterns lot P8) -----------------------------------


def _family_source(tmp_path):
    rows = (
        [f"INV-{n:03d}" for n in range(100, 160)]
        + [f"INV-{n:04d}" for n in range(1000, 1090)]
        + [f"AK-{n:04d}" for n in range(30)]
        + [f"ZZ-{n:04d}" for n in range(30)]
    )
    return _csv(tmp_path, "code", rows)


def test_the_column_view_is_the_hierarchy_of_the_scan_with_shares(tmp_path):
    profile = analyze_csv(_family_source(tmp_path))

    view = dataset_views(profile)[0].columns[0].patterns

    family = view.families[0]
    assert [pattern.id for pattern in family.patterns] == [
        pattern.id for pattern in view.entry.families[0].patterns
    ]
    assert family.d == sum(pattern.d for pattern in family.patterns)
    assert view.node_count == sum(pattern.node_count for pattern in family.patterns)
    assert view.node_count > 0
    assert 0 < family.share_d <= 1
    assert not view.has_validation and family.validated is None


def test_the_column_page_shows_families_patterns_nodes_without_script(tmp_path):
    profile = analyze_csv(_family_source(tmp_path))
    dataset = dataset_views(profile)[0]

    page = render_column_report(profile, dataset, dataset.columns[0], "report.html")

    assert 'class="pfam rcard"' in page and "<details" in page
    assert 'class="ptree"' in page
    assert "Family <code>" in page
    assert "Not validated against the whole file." in page
    assert "Quoted text is a constant" in page


def test_the_global_table_names_the_family_of_each_pattern(tmp_path):
    profile = analyze_csv(_family_source(tmp_path))

    html = render_report(profile)
    view = dataset_views(profile)[0].columns[0].patterns

    assert "Family" in html
    assert view.rows[0].family_key == view.families[0].key


def test_a_table_of_a_family_renders_its_cells_and_an_others_row_on_one_base():
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "examples" / "datasets" / "insurance-customers.csv"
    profile = analyze_csv(source)
    dataset = dataset_views(profile)[0]
    column = next(c for c in dataset.columns if any(f.tables for f in c.patterns.families))

    page = render_column_report(profile, dataset, column, "report.html")

    family = next(f for f in column.patterns.families if f.tables)
    table = family.tables[0]
    assert 'class="ptable"' in page and 'class="pothers"' in page
    # Cells and rest add up to the family, in distinct values.
    assert sum(c.d for c in table.cells) + table.others_d == family.d
    # A folded family keeps its marker: the flex layout is in an inner span.
    assert '<summary class="rcard-title"><span class="sl">' in page
