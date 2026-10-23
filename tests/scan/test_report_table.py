# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Summary table of the Report (Report overview lot R9a).

The contract is ``docs/dev/report/summary-table.md`` 7.3. The tests read the
rendered HTML as the browser does: eight headers, the identity of a row, the
codes the filters work on, the exposure of the Details and the states of the
findings. They do not freeze the wording of an Overview or of a label.
"""

import pytest
from columns_table_helpers import columns_table, row_for
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.report_findings import (
    Assessment,
    Finding,
    FindingList,
    Population,
)
from tabalyst.report_labels import FAMILY_LABELS, TYPE_LABELS
from tabalyst.report_table import LABELS_SHOWN, _cell, column_table
from tabalyst.reporting import dataset_views, load_profile, render_report
from tabalyst.scanner import ScanConfig

HEADERS = [
    "Column",
    "Type family",
    "Type",
    "Overview",
    "Missing",
    "Errors",
    "Issues",
    "Details",
]
FAMILY, TYPE, MISSING, ERRORS, ISSUES, DETAILS = 1, 2, 4, 5, 6, 7


def _render(tmp_path, content, **exposure):
    source = write_text(tmp_path, "data.csv", content)
    settings = {"exposure": exposure} if exposure else {}
    config = ReportConfig(scan=ScanConfig.model_validate(settings))
    profile = analyze_csv(source, config)
    return profile, render_report(profile)


def _contacts(count=30):
    lines = ["contact,row"] + [f"user{n}@example.com,{n}" for n in range(count)]
    return "\n".join(lines) + "\n"


def _finding(code, count, cls="issue"):
    return Finding(
        code=code,
        cls=cls,
        field="f",
        count=count,
        unit="occurrences",
        population=Population(kind="present_values", size=100),
        accuracy="exact",
    )


ACTIVE_ISSUES = (
    "temporal.ambiguous_date",
    "number.ambiguous",
    "categorical.case_variants",
    "pattern.minority",
    "length.minority",
    "type.mixed",
)


def _a_column(tmp_path):
    """A real column view: the preview of a finding reads the exposure and the
    detectors of its column."""
    profile, _ = _render(tmp_path, "name,amount\nAlice,1\nBob,2\n")
    return dataset_views(profile)[0].columns[0]


def test_the_table_has_the_eight_columns_in_order_and_no_removed_column(tmp_path):
    _, html = _render(tmp_path, "name,amount\nAlice,1\nBob,2\n")

    table = columns_table(html)

    assert table.headers == HEADERS
    assert len(table.rows[0].cells) == len(HEADERS)
    for removed in ("Distinct", "Inferred type", "Examples", "Error"):
        assert removed not in table.headers


def test_a_row_is_identified_by_dataset_and_field_ids(tmp_path):
    profile, html = _render(tmp_path, "name,name\n1,a\n2,b\n")

    table = columns_table(html)

    dataset = profile.report.datasets[0]
    assert [(row.attrs["data-ds"], row.attrs["data-field"]) for row in table.rows] == [
        (dataset.id, column.id) for column in dataset.columns
    ]
    assert len({row.attrs["data-field"] for row in table.rows}) == 2
    # The displayed name is the same; the path tells the two apart.
    assert {row.cells[0]["data-v"] for row in table.rows} == {"name"}
    first, second = (row.cells[0].text for row in table.rows)
    assert first != second


def test_the_summary_table_links_each_column_to_its_page(tmp_path):
    source = write_text(tmp_path, "data.csv", "name,name\n1,a\n2,b\n")
    profile = analyze_csv(source)
    dataset = profile.report.datasets[0]
    links = {
        (dataset.id, column.id): f"columns/{column.id}.html"
        for column in dataset.columns
    }

    html = render_report(profile, column_links=links)

    # Every column label of every table links to its details page, one per field id.
    for column in dataset.columns:
        assert f"columns/{column.id}.html" in columns_table(html).html
        assert f"columns/{column.id}.html" in columns_table(html, "columns-table").html


def test_a_details_cell_holds_two_lines_and_a_hover_with_the_whole_story(tmp_path):
    names = ["Marie"] * 6 + ["marie"] * 3 + ["Anne"] * 4 + ["anne"] * 2
    rows = "".join(f"{names[n % len(names)]},{n}\n" for n in range(60))
    _, html = _render(tmp_path, "name,row\n" + rows, sensitive_values="show")

    table = columns_table(html)

    cell = row_for(table, "name").cells[DETAILS]
    assert "ex" in cell["class"].split() and cell["tabindex"] == "0"
    assert cell.get("aria-describedby")
    for part in ("Values", "Issues", "Spelling variants", "Marie", "marie", "Anne", "anne"):
        assert part in table.html, part
    # Every group the scan found is in the hover, not only the first.
    assert table.html.count('class="vgroup"') == 2


def test_family_and_type_filter_on_independent_codes(tmp_path):
    lines = ["email,phone,note"]
    for n in range(40):
        lines.append(
            f"user{n}@example.com,(514) 555-{n:04d},free text number {n} here"
        )
    _, html = _render(tmp_path, "\n".join(lines) + "\n", sensitive_values="show")

    table = columns_table(html)

    families = {row.cells[0]["data-v"]: row.cells[FAMILY]["data-v"] for row in table.rows}
    types = {row.cells[0]["data-v"]: row.cells[TYPE]["data-v"] for row in table.rows}
    assert families["email"] == families["phone"] == "contact"
    assert families["note"] == "text"
    assert types["email"] == "contact/email"
    assert types["phone"] == "contact/phone"
    # The family filter keeps the two Contact rows; the type then tells them apart.
    contacts = [row for row in table.rows if row.cells[FAMILY]["data-v"] == "contact"]
    assert len(contacts) == 2
    assert [row.cells[0]["data-v"] for row in contacts if row.cells[TYPE]["data-v"] == "contact/email"] == ["email"]
    # The words are carried apart from the codes the filters use.
    assert {row.cells[FAMILY]["data-l"] for row in table.rows} == {"Contact", "Text"}


def test_a_family_code_never_equals_the_code_of_a_type(tmp_path):
    keys = {f"{family}/{kind}" for family, kind in (key.split("/") for key in TYPE_LABELS)}
    assert keys.isdisjoint(FAMILY_LABELS)
    # Two families can name a type alike ("Text" family, "Text" type): the key is
    # family/type, so a filter on one never selects the other.
    assert len(keys) == len(TYPE_LABELS)


def test_filter_options_come_from_the_classifications_present(tmp_path):
    _, html = _render(tmp_path, "name,amount\nAlice,1\nBob,2\n")

    table = columns_table(html)

    present_families = {row.cells[FAMILY]["data-v"] for row in table.rows}
    present_types = {row.cells[TYPE]["data-v"] for row in table.rows}
    assert present_families < set(FAMILY_LABELS)
    assert present_types < set(TYPE_LABELS)


def test_the_table_renders_from_the_json_without_the_source(tmp_path):
    source = write_text(tmp_path, "data.csv", "note,n\nalpha,1\nbeta,2\ngamma,3\n")
    profile = analyze_csv(source)
    document = write_text(
        tmp_path, "report.json", dump_json(profile.model_dump(mode="json"))
    )
    fresh = render_report(profile)
    source.unlink()

    again = render_report(load_profile(document))

    assert again == fresh
    assert columns_table(again).headers == HEADERS


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_table_writes_no_raw_value_of_a_masked_or_hidden_column(tmp_path, mode):
    _, html = _render(tmp_path, _contacts(), sensitive_values=mode)

    table = columns_table(html)

    assert "user" not in table.html
    assert "example.com" not in table.html
    cell = table.rows[0].cells[DETAILS]
    assert ("masked" if mode == "mask" else "hidden") in cell.text


def test_a_shown_column_lists_its_examples_in_the_details_cell(tmp_path):
    _, html = _render(tmp_path, _contacts(), sensitive_values="show")

    table = columns_table(html)

    assert "user" in table.rows[0].cells[DETAILS].text


def test_issues_say_their_state_and_errors_show_a_dash_only_when_not_applicable(tmp_path):
    _, html = _render(tmp_path, "name,amount\nAlice,1\nBob,2\n")

    table = columns_table(html)

    name, amount = table.rows
    # A Text field has no deterministic rule: the Errors cell is a dash, and the
    # word stays in the filter, the tooltip and for a screen reader (maintainer, R9a).
    assert name.cells[ERRORS]["data-v"] == "not_applicable"
    assert name.cells[ERRORS]["data-l"] == "Not applicable"
    assert name.cells[ERRORS].text.startswith("-")
    assert "Not applicable" in name.cells[ERRORS].text
    assert amount.cells[ERRORS].text == "None detected"
    assert amount.cells[ERRORS]["data-v"] == "none_detected"
    for row in table.rows:
        assert not row.cells[ISSUES].text.startswith("-")
        assert row.cells[ISSUES].text


def test_the_previous_columns_table_is_kept_after_the_summary_table(tmp_path):
    _, html = _render(tmp_path, "name,amount\nAlice,1\nBob,2\n")

    old = columns_table(html, "columns-table")

    assert old.headers == [
        "Column",
        "Missing",
        "Distinct",
        "Inferred type",
        "Type",
        "Error",
        "Issues",
        "Examples",
    ]
    assert html.index('id="summary-table"') < html.index('id="columns-table"')
    assert html.index('id="summary"') < html.index('id="columns"')
    assert 'href="#summary"' in html and 'href="#columns"' in html


def test_a_proven_invalid_value_is_an_error_and_flags_the_row_as_an_issue(tmp_path):
    lines = ["email,note"] + [f"user{n}@example.com,n{n}" for n in range(40)]
    lines.append("bad address@example.com,n40")
    _, html = _render(tmp_path, "\n".join(lines) + "\n", sensitive_values="show")

    table = columns_table(html)

    email = row_for(table, "email")
    assert email.cells[ERRORS]["data-v"] == "detected"
    assert "invalid" in email.cells[ERRORS].text
    assert email.cells[ERRORS]["data-s"] == "1"
    assert "issue" in email.attrs["data-flags"].split()


def test_the_segment_offers_the_columns_with_errors(tmp_path):
    lines = ["email,note"] + [f"user{n}@example.com,n{n}" for n in range(40)]
    lines.append("bad address@example.com,n40")
    profile, html = _render(tmp_path, "\n".join(lines) + "\n", sensitive_values="show")

    table = columns_table(html)

    assert "error" in row_for(table, "email").attrs["data-flags"].split()
    assert "error" not in row_for(table, "note").attrs["data-flags"].split()
    assert column_table(dataset_views(profile)[0]).error_count == 1
    assert 'data-mode="error"' in html or ">With errors<" in html


def test_the_segment_counts_the_rows_with_errors_or_issues_not_missing_values(tmp_path):
    lines = ["a,b"] + [f"{n}," + ("" if n % 2 else "x") for n in range(40)]
    profile, html = _render(tmp_path, "\n".join(lines) + "\n")

    table = columns_table(html)
    views = dataset_views(profile)
    counts = column_table(views[0])

    flagged = [row for row in table.rows if "issue" in row.attrs["data-flags"].split()]
    assert counts.issue_count == len(flagged)
    # Missing values alone neither add an Error nor an Issue: column b is Missing only.
    b = row_for(table, "b")
    assert b.cells[ERRORS]["data-v"] != "detected"
    assert b.cells[ISSUES]["data-v"] != "detected"
    assert "issue" not in b.attrs["data-flags"].split()
    assert f'<span class="c">{counts.issue_count}</span>' in html


def test_missing_is_the_figure_of_the_profile(tmp_path):
    profile, html = _render(tmp_path, "amount,name\n1.234567,A\n9.876543,B\n,C\n")

    cell = columns_table(html).rows[0].cells[MISSING]

    column = profile.report.datasets[0].columns[0]
    assert cell["data-v"] == str(column.missing_percent)


def test_a_cell_shows_two_labels_then_previews_the_others(tmp_path):
    items = [_finding(code, n + 1) for n, code in enumerate(ACTIVE_ISSUES[: LABELS_SHOWN + 2])]
    listing = FindingList(items=items, state="detected", assessments=[])

    cell = _cell(listing)

    assert len(cell.shown) == LABELS_SHOWN
    assert len(cell.rest) == 2
    assert cell.order == len(items)
    assert [preview.code for preview in cell.shown + cell.rest] == [
        item.code for item in items
    ]


def test_a_list_that_found_something_names_the_checks_that_went_part_way(tmp_path):
    items = [_finding("categorical.case_variants", 3)]
    assessments = [
        Assessment(code="categorical.case_variants", state="detected"),
        Assessment(code="pattern.minority", state="partial"),
        Assessment(code="length.minority", state="not_assessed"),
        Assessment(code="type.mixed", state="not_applicable"),
    ]
    listing = FindingList(items=items, state="detected", assessments=assessments)

    cell = _cell(listing)

    assert cell.caveat == "1 check partially assessed, 1 check not assessed"
    assert {line.code for line in cell.caveat_checks} == {
        "length.minority",
        "pattern.minority",
    }
    # The words, not the internal codes, tell what each check covered.
    assert all(line.name and "." not in line.name for line in cell.caveat_checks)


def test_a_list_without_finding_has_no_caveat_and_a_count_label(tmp_path):
    listing = FindingList(items=[], state="partial", assessments=[])

    cell = _cell(listing)

    assert cell.caveat is None and cell.state_label == "Partially assessed"
    assert cell.labels == [] and cell.order == 0


def test_a_lower_bound_is_never_worded_exact(tmp_path):
    item = _finding("temporal.invalid_calendar", 4, "error")
    item = item.model_copy(update={"accuracy": "lower_bound"})

    cell = _cell(FindingList(items=[item], state="detected", assessments=[]))

    assert cell.labels[0].startswith("at least ")


def test_the_dashboard_card_has_two_captioned_lists(tmp_path):
    _, html = _render(tmp_path, "name,amount\nAlice,1\nBob,2\n")

    start = html.index("Column types")
    card = html[start : html.index("</section>", start)]

    # The classification first, each family followed by its own types ...
    assert "Classification: family, then its types" in card
    assert card.index("Numeric") < card.index("Integer")
    # ... then the technical types the Columns table still shows.
    assert "Technical type: what the values are made of" in card
    assert card.index("Integer") < card.index("Physical column types")


def test_cells_escape_values_that_look_like_markup(tmp_path):
    values = ["<script>alert(1)</script>", "=1+1", "<img src=x>"] * 4
    lines = ["tag,row"] + [f"{value},{n}" for n, value in enumerate(values)]
    _, html = _render(tmp_path, "\n".join(lines) + "\n", sensitive_values="show")

    table = columns_table(html)

    assert "<script>alert(1)" not in table.html
    assert "<img src=x>" not in table.html
    assert "&lt;script&gt;" in table.html
