# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Signals, column quality and finding details of the report (overview cards, Findings).

The contract is ``docs/dev/report/summary-table.md`` 7.5 and 7.6. The tests check
the figures and the exposure of the values, not the wording of a label.
"""

import pytest
from columns_table_helpers import columns_table
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.report_config import ReportConfig
from tabalyst.report_finding_details import (
    GROUPS_SHOWN,
    SPELLINGS_SHOWN,
    variant_details,
)
from tabalyst.report_findings import column_findings
from tabalyst.report_signals import SIGNALS_SHOWN
from tabalyst.report_table import column_table
from tabalyst.reporting import dataset_views, render_report
from tabalyst.scanner import ScanConfig

NAMES = (
    ["Marie"] * 6 + ["marie"] * 3 + ["MARIE"] + ["Paul"] * 5 + ["paul"] * 2 + ["Anne"] * 4
)


def _csv(tmp_path, columns, rows, **exposure):
    header = ",".join(columns)
    lines = [header] + [",".join(str(cell) for cell in row) for row in rows]
    source = write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    settings = {"exposure": exposure} if exposure else {}
    config = ReportConfig(scan=ScanConfig.model_validate(settings))
    return analyze_csv(source, config)


def _dates(tmp_path, **exposure):
    rows = [
        (f"{1 + n % 9:02d}/{2 + n % 8:02d}/2020", f"{3 + n % 6:02d}/{4 + n % 5:02d}/2021", NAMES[n % len(NAMES)])
        for n in range(60)
    ]
    return _csv(tmp_path, ["first", "second", "name"], rows, **exposure)


def _table(profile):
    view = dataset_views(profile)[0]
    return view, column_table(view)


def test_a_signal_sums_one_code_over_the_columns_that_have_it(tmp_path):
    view, table = _table(_dates(tmp_path))

    found = {
        column.name: {
            item.code: item.count for item in column_findings(column).issues.items
        }
        for column in view.columns
    }
    signal = next(s for s in table.signals.shown if s.code == "temporal.ambiguous_date")

    expected = {n: f["temporal.ambiguous_date"] for n, f in found.items() if "temporal.ambiguous_date" in f}
    assert signal.total == sum(expected.values())
    assert {c.name: c.count for c in signal.columns} == expected
    assert signal.columns[0].relative_percent == 100.0
    assert [c.count for c in signal.columns] == sorted(expected.values(), reverse=True)


def test_signals_list_the_errors_before_the_issues(tmp_path):
    rows = [(f"user{n}@example.com", "01/02/2020") for n in range(40)]
    rows.append(("bad address@example.com", "03/04/2020"))
    _, table = _table(_csv(tmp_path, ["email", "when"], rows, sensitive_values="show"))

    classes = [s.cls for s in table.signals.shown]

    assert "error" in classes
    assert classes == sorted(classes, key=lambda cls: cls != "error")


def test_signals_show_at_most_the_documented_number_and_count_the_rest(tmp_path):
    _, table = _table(_dates(tmp_path))

    assert len(table.signals.shown) <= SIGNALS_SHOWN
    assert table.signals.more >= 0


def test_a_dataset_without_finding_says_so(tmp_path):
    profile = _csv(tmp_path, ["amount"], [(n,) for n in range(1, 30)])

    view, table = _table(profile)
    html = render_report(profile)

    assert not table.signals.shown
    assert "No Error and no Issue was detected" in html
    assert "Derived · sum of" not in html
    assert table.quality.no_finding == len(view.columns)


def test_each_column_is_in_exactly_one_group_of_the_quality(tmp_path):
    view, table = _table(_dates(tmp_path))

    quality = table.quality

    assert quality.columns == len(view.columns)
    assert quality.with_errors + quality.with_issues + quality.no_finding == quality.columns
    groups = (quality.error_columns, quality.issue_columns, quality.clean_columns)
    names = [item.field_id for group in groups for item in group]
    assert sorted(names) == sorted(column.id for column in view.columns)
    assert abs(quality.errors_percent + quality.issues_percent + quality.clean_percent - 100) < 0.2
    # A column with Errors counts under Errors even when it has Issues too.
    assert all(item.labels for item in quality.error_columns + quality.issue_columns)
    assert all(not item.labels for item in quality.clean_columns)


def test_the_states_of_each_list_still_add_up_to_the_columns(tmp_path):
    _, table = _table(_dates(tmp_path))

    quality = table.quality

    for part in (quality.errors, quality.issues):
        assert sum(state.columns for state in part.states) == quality.columns


def test_signals_have_a_title_a_subtitle_and_a_popover_with_their_columns(tmp_path):
    profile = _dates(tmp_path)
    _, table = _table(profile)

    html = render_report(profile)

    assert all(signal.title for signal in table.signals.shown)
    ambiguous = next(s for s in table.signals.shown if s.code == "temporal.ambiguous_date")
    assert ambiguous.title == "Ambiguous dates" and ambiguous.subtitle
    for index in range(1, len(table.signals.shown) + 1):
        assert f'data-pop="pop-s{index}"' in html
        assert f'<template id="pop-s{index}" data-label=' in html
    # The page has one dialog, closed and empty until a button opens it.
    assert 'data-label="Ambiguous dates: affected columns"' in html
    assert html.count('role="dialog"') == 1


def test_an_error_signal_is_a_red_tile_and_an_issue_a_plain_one(tmp_path):
    rows = [(f"user{n}@example.com", "01/02/2020") for n in range(40)]
    rows.append(("bad address@example.com", "03/04/2020"))
    profile = _csv(tmp_path, ["email", "when"], rows, sensitive_values="show")

    html = render_report(profile)

    assert 'class="sig sig-error"' in html and 'class="sig sig-issue"' in html
    # The class is written before the title: the colour is never the only cue.
    assert '<span class="sig-c">Error</span>' in html
    assert '<span class="sig-c">Issue</span>' in html


def test_the_quality_kpis_open_the_columns_behind_them(tmp_path):
    profile = _dates(tmp_path)
    _, table = _table(profile)

    html = render_report(profile)

    assert "Distribution of findings across" in html
    assert 'data-pop="pop-q-issue"' in html
    # A group with no column is a plain figure: there is nothing to open.
    assert ('data-pop="pop-q-clean"' in html) == (table.quality.no_finding > 0)
    assert table.quality.with_issues > 0
    # The statuses of the observations are explained whatever the dataset holds.
    for word in ("Confirmed issue", "Candidate anomaly", "Remark"):
        assert word in html


def test_the_spelling_signal_lists_the_largest_group_of_each_column(tmp_path):
    _, table = _table(_dates(tmp_path, sensitive_values="show"))

    signal = next(s for s in table.signals.shown if s.code == "categorical.case_variants")

    name = next(c for c in signal.columns if c.name == "name")
    assert {sp.value for sp in name.spellings} >= {"Marie", "marie"}
    assert name.spellings[0].most_frequent


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_spelling_signal_leaves_no_raw_value_of_a_masked_or_hidden_column(tmp_path, mode):
    _, table = _table(_emails(tmp_path, sensitive_values=mode))

    signal = next((s for s in table.signals.shown if s.code == "categorical.case_variants"), None)

    if signal is not None:
        assert "Marie" not in signal.model_dump_json()
        if mode == "hide":
            assert all(not column.spellings for column in signal.columns)


def test_the_overview_cards_are_rendered_from_the_model(tmp_path):
    profile = _dates(tmp_path)

    html = render_report(profile)

    assert "Signals / what the checks found" in html
    assert "Column quality" in html
    assert "Ambiguous dates" in html and "data-pop" in html


def test_summary_comes_before_findings_in_the_page_and_in_the_navigation(tmp_path):
    html = render_report(_dates(tmp_path))

    assert html.index('id="summary"') < html.index('id="observations"')
    assert html.index('href="#summary"') < html.index('href="#observations"')
    assert "02 / Summary" in html and "03 / Findings" in html
    assert "04 / Structure" in html


def test_variants_list_the_spellings_to_correct_with_the_most_frequent_first(tmp_path):
    view, _ = _table(_dates(tmp_path, sensitive_values="show"))
    name = next(c for c in view.columns if c.name == "name")

    details = variant_details(name)

    assert details is not None and details.state == "shown"
    first = details.groups[0].spellings
    assert first[0].most_frequent and not any(s.most_frequent for s in first[1:])
    assert [s.count for s in first] == sorted((s.count for s in first), reverse=True)
    assert {s.value for s in first} >= {"Marie", "marie"}
    assert len(details.groups) <= GROUPS_SHOWN
    assert all(len(g.spellings) <= SPELLINGS_SHOWN for g in details.groups)


def test_a_column_without_variants_has_no_details(tmp_path):
    view, _ = _table(_dates(tmp_path))

    assert variant_details(next(c for c in view.columns if c.name == "first")) is None


def test_variant_details_reach_the_findings_table_of_the_page(tmp_path):
    html = render_report(_dates(tmp_path, sensitive_values="show"))

    cell = columns_table(html, "observation-table")

    text = " ".join(row.cells[-1].text for row in cell.rows)
    assert "Marie" in text and "marie" in text and "×6" in text


def _emails(tmp_path, **exposure):
    values = (
        ["Marie@example.com"] * 6
        + ["marie@example.com"] * 3
        + [f"user{n}@example.com" for n in range(30)]
    )
    return _csv(tmp_path, ["contact", "row"], [(v, n) for n, v in enumerate(values)], **exposure)


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_variant_details_leave_no_raw_value_of_a_masked_or_hidden_column(tmp_path, mode):
    profile = _emails(tmp_path, sensitive_values=mode)
    view, _ = _table(profile)
    contact = view.columns[0]

    details = variant_details(contact)
    html = render_report(profile)

    assert contact.exposure == mode
    findings = columns_table(html, "observation-table")
    assert "Marie" not in " ".join(row.cells[-1].text for row in findings.rows)
    assert "marie@" not in " ".join(row.cells[-1].text for row in findings.rows)
    if details is not None:
        assert details.state == ("masked" if mode == "mask" else "hidden")
        assert "Marie" not in details.model_dump_json()
        if mode == "hide":
            assert details.groups == []


def test_a_shown_sensitive_column_lists_its_variants(tmp_path):
    view, _ = _table(_emails(tmp_path, sensitive_values="show"))

    details = variant_details(view.columns[0])

    assert details is not None and details.state == "shown"
    assert {s.value for s in details.groups[0].spellings} == {
        "Marie@example.com",
        "marie@example.com",
    }
