# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Previews of the Errors and Issues of the Summary table (Report overview lot R9b).

The contract is ``docs/dev/report/summary-table.md`` 18. The tests check what a
preview states (nature, unit, count, population, share, accuracy, examples, limit),
that examples go through the exposure, that an absent piece is never invented, and
that every label and state can be reached without hover or colour (RT-16, CA-27).
"""

import pytest
from columns_table_helpers import columns_table, row_for
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.report_details import exposed_values
from tabalyst.report_findings import (
    Assessment,
    Finding,
    FindingList,
    Population,
    Share,
    column_findings,
)
from tabalyst.report_preview import (
    EXAMPLES_SHOWN,
    check_lines,
    finding_preview,
    percent_text,
)
from tabalyst.reporting import dataset_views, load_profile, render_report
from tabalyst.scanner import ScanConfig

ERRORS, ISSUES = 5, 6


def _profile(tmp_path, content, name="data.csv", **exposure):
    source = write_text(tmp_path, name, content)
    settings = {"exposure": exposure} if exposure else {}
    return analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate(settings)))


def _contacts(bad=3, good=100):
    lines = ["contact,row"]
    lines += [f"zzsecret{n}@example.org,{n}" for n in range(good)]
    lines += [f"zzbad {n}@example.org,{good + n}" for n in range(bad)]
    return "\n".join(lines) + "\n"


def _column(profile, name):
    return next(
        column for column in dataset_views(profile)[0].columns if column.name == name
    )


def _all_findings(found):
    return [*found.errors.items, *found.issues.items]


def _invalid_email(profile):
    column = _column(profile, "contact")
    found = column_findings(column)
    item = next(item for item in _all_findings(found) if item.code == "semantic.invalid")
    return column, found, item


def test_the_preview_of_an_invalid_email_states_what_it_counts(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="show")
    column, found, item = _invalid_email(profile)

    preview = finding_preview(column, item, found.errors.assessments)

    assert preview.code == "semantic.invalid"
    assert preview.cls == "error"
    assert preview.nature and "syntax" in preview.nature
    assert preview.unit == "occurrences"
    assert preview.count_text == "3"
    assert preview.population == "103 eligible values"
    assert preview.share == "2.91% (3 of 103 eligible values)"
    assert preview.accuracy == "Exact"
    assert preview.limits and "syntax" in preview.limits[0]


def test_the_examples_of_a_shown_column_are_the_values_the_detector_set_aside(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="show")
    column, found, item = _invalid_email(profile)

    preview = finding_preview(column, item, found.errors.assessments)

    assert preview.examples_state == "shown"
    assert 0 < len(preview.examples) <= EXAMPLES_SHOWN
    assert all(value.startswith("zzbad") for value in preview.examples)
    assert preview.examples_note is None


def test_a_masked_column_gives_masks_and_says_so(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="mask")
    column, found, item = _invalid_email(profile)

    preview = finding_preview(column, item, found.errors.assessments)

    assert preview.examples_state == "masked"
    assert preview.examples
    assert not any("zz" in value for value in preview.examples)
    assert preview.examples_note and "Masked" in preview.examples_note


def test_a_hidden_column_gives_no_example_and_says_so(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="hide")
    column, found, item = _invalid_email(profile)

    preview = finding_preview(column, item, found.errors.assessments)

    assert preview.examples == [] and preview.examples_state == "hidden"
    assert preview.examples_note and "Withheld" in preview.examples_note


@pytest.mark.parametrize("mode", ["show", "mask", "hide"])
def test_the_preview_applies_the_exposure_again_to_a_raw_document(tmp_path, mode):
    """The Scan already exposes the evidence; a document that holds raw values
    whatever its field announces must not leak them (CA-19)."""
    profile = _profile(tmp_path, _contacts(), sensitive_values="show")
    column, found, item = _invalid_email(profile)
    forced = column.model_copy(update={"exposure": mode})

    preview = finding_preview(forced, item, found.errors.assessments)

    leaked = [value for value in preview.examples if value.startswith("zzbad")]
    assert bool(leaked) == (mode == "show")
    assert preview.examples_state == {"show": "shown", "mask": "masked", "hide": "hidden"}[mode]


def test_no_example_is_invented_where_the_scan_keeps_none(tmp_path):
    profile = _profile(tmp_path, "amount\n" + "\n".join(map(str, range(100))) + "\nx\ny\n")
    column = _column(profile, "amount")
    found = column_findings(column)
    item = next(item for item in _all_findings(found) if item.code == "type.outside_family")

    preview = finding_preview(column, item, found.errors.assessments)

    assert preview.examples == [] and preview.examples_state == "none"
    assert preview.examples_note is None


def test_spelling_variants_show_two_spellings_of_the_largest_group(tmp_path):
    rows = ["city"] + ["Paris"] * 5 + ["PARIS"] * 3 + ["paris"] * 2 + ["Lyon"] * 4
    profile = _profile(tmp_path, "\n".join(rows) + "\n", sensitive_values="show")
    column = _column(profile, "city")
    found = column_findings(column)
    item = next(item for item in found.issues.items if item.code == "categorical.case_variants")

    preview = finding_preview(column, item, found.issues.assessments)

    assert preview.unit == "groups" and preview.count_text == "1"
    assert preview.examples == ["Paris", "PARIS"][:EXAMPLES_SHOWN]
    assert preview.examples_state == "shown"


def test_a_lower_bound_is_worded_at_least_everywhere_in_the_preview(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="show")
    column, found, item = _invalid_email(profile)
    bounded = item.model_copy(update={"accuracy": "lower_bound"})

    preview = finding_preview(column, bounded, found.errors.assessments)

    assert preview.title.startswith("at least ")
    assert preview.count_text == "at least 3"
    assert preview.accuracy == "At least"


def test_an_error_that_the_classification_does_not_establish_says_it_is_an_issue(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="show")
    column, found, item = _invalid_email(profile)
    downgraded = item.model_copy(update={"cls": "issue"})

    preview = finding_preview(column, downgraded, found.errors.assessments)

    assert preview.cls == "issue"
    assert any("not established" in limit for limit in preview.limits)


def test_a_check_that_covered_part_of_the_values_says_how_many(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="show")
    column, _, item = _invalid_email(profile)
    partial = Assessment(
        code=item.code, state="partial", accuracy="lower_bound", eligible=1000, tested=100
    )

    preview = finding_preview(column, item, [partial])

    assert any("100 of 1,000 eligible values" in limit for limit in preview.limits)


def test_a_share_without_a_defined_percentage_is_left_out(tmp_path):
    profile = _profile(tmp_path, _contacts(), sensitive_values="show")
    column, found, item = _invalid_email(profile)
    undefined = item.model_copy(
        update={
            "share": Share(numerator=3, denominator=0, percent=None, accuracy="unavailable"),
            "population": Population(kind="eligible_values", size=None),
        }
    )

    preview = finding_preview(column, undefined, found.errors.assessments)

    assert preview.share is None and preview.population is None


@pytest.mark.parametrize(
    ("percent", "text"),
    [(0, "0%"), (0.004, "<0.01%"), (0.01, "0.01%"), (12.5, "12.5%"), (100, "100%")],
)
def test_percentages_are_never_rounded_to_zero(percent, text):
    assert percent_text(percent) == text


def test_the_checks_of_a_list_are_told_in_words_and_skip_the_ones_that_do_not_apply():
    listing = FindingList(
        items=[],
        state="partial",
        assessments=[
            Assessment(code="pattern.minority", state="partial", reason="patterns_sample"),
            Assessment(code="length.minority", state="not_assessed", reason="too_few_values"),
            Assessment(
                code="temporal.ambiguous_date",
                state="partial",
                eligible=1000,
                tested=100,
            ),
            Assessment(code="type.mixed", state="not_applicable", reason="no_values"),
        ],
    )

    lines = {line.code: line for line in check_lines(listing)}

    assert set(lines) == {"pattern.minority", "length.minority", "temporal.ambiguous_date"}
    assert lines["pattern.minority"].detail == "the patterns were inferred on a sample"
    assert lines["temporal.ambiguous_date"].detail == (
        "100 values tested of 1,000 eligible values"
    )
    assert lines["length.minority"].state_label == "Not assessed"
    assert [line.code for line in check_lines(listing, incomplete_only=True)] == [
        "pattern.minority",
        "length.minority",
        "temporal.ambiguous_date",
    ]


# --- The HTML: reachable without hover or colour (RT-16, CA-27) -------------------


def _issue_row(tmp_path):
    rows = ["name,city"] + [f"user{n},Paris" for n in range(5)] + ["u,PARIS", "v,paris"]
    profile = _profile(tmp_path, "\n".join(rows) + "\n", sensitive_values="show")
    return profile, render_report(profile)


def test_every_label_of_a_cell_is_a_button_that_names_its_own_dialog_content(tmp_path):
    _, html = _issue_row(tmp_path)

    row = row_for(columns_table(html), "city")

    cell = row.cells[ISSUES]
    assert cell.buttons, "the Issues of the column have no button"
    dialogs = {pop.attrs["id"]: pop for pop in cell.pops}
    for attrs, parts in cell.buttons:
        assert attrs.get("type") == "button"
        assert "data-pop" in attrs
        assert attrs.get("aria-haspopup") == "dialog"
        assert attrs.get("aria-expanded") == "false"
        # the content waits in a template; the page's one dialog is filled when it opens
        dialog = dialogs[attrs["data-pop"]]
        assert dialog.attrs.get("data-label")
    first = cell.pops[0].text
    assert "Counted in" in first and "Accuracy" in first and "Limit" in first


def test_the_state_of_a_class_is_in_the_text_and_not_only_in_the_colour(tmp_path):
    _, html = _issue_row(tmp_path)

    row = row_for(columns_table(html), "city")

    # The label carries the class as hidden text, and the dialog as a visible word.
    assert "Issue: " in "".join("".join(parts) for _, parts in row.cells[ISSUES].buttons)
    assert "Issue" in row.cells[ISSUES].pops[0].text
    assert 'class="vh">Issue: ' in columns_table(html).html


def test_nothing_the_cells_say_lives_in_a_title_attribute(tmp_path):
    _, html = _issue_row(tmp_path)
    table = columns_table(html)

    for row in table.rows:
        for index in (ERRORS, ISSUES):
            assert "title" not in row.cells[index].attrs
    for row in table.rows:
        for index in (ERRORS, ISSUES):
            # no element of the cell, outside its dialogs, carries a title
            assert not any("title" in attrs for attrs, _ in row.cells[index].buttons)
    assert " title=" not in "".join(
        "".join(parts) for row in table.rows for _, parts in row.cells[ERRORS].buttons
    )


def test_every_active_finding_has_a_sentence_for_its_nature_and_its_limit():
    from tabalyst.report_labels import FINDING_LIMITS, FINDING_NATURES
    from tabalyst.scanner.classify.catalog import FINDINGS

    active = [e.code for e in FINDINGS if e.status == "active" and e.cls != "information"]
    assert [code for code in active if code not in FINDING_NATURES] == []
    assert [code for code in active if code not in FINDING_LIMITS] == []


def test_a_state_without_finding_is_a_button_that_lists_its_checks(tmp_path):
    _, html = _issue_row(tmp_path)

    cell = row_for(columns_table(html), "name").cells[ERRORS]

    # A Text column has no Error check at all: a dash, no button, the word stays hidden text.
    assert cell.buttons == [] and cell.text.startswith("-")
    issues = row_for(columns_table(html), "name").cells[ISSUES]
    if issues.attrs["data-v"] != "detected":
        assert issues.buttons
        assert "Partially assessed" in issues.pops[0].text or "None detected" in issues.pops[0].text


def test_the_dialogs_of_a_cell_hold_every_finding_once(tmp_path):
    _, html = _issue_row(tmp_path)

    cell = row_for(columns_table(html), "city").cells[ISSUES]

    titles = [pop.attrs["aria-label"] for pop in cell.pops]
    assert len(titles) == len(set(titles))
    spelled = [pop for pop in cell.pops if "spelling" in pop.text.lower()]
    assert len(spelled) == 1


# --- CA-19: the examples of the Columns and Numeric tables ------------------------


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_page_writes_no_raw_value_of_a_masked_or_hidden_column(tmp_path, mode):
    profile = _profile(tmp_path, _contacts(), sensitive_values=mode)

    html = render_report(profile)

    assert "zzsecret" not in html and "zzbad" not in html


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_numeric_and_columns_tables_apply_the_exposure_to_a_raw_document(tmp_path, mode):
    content = "amount,row\n" + "\n".join(f"{7000 + n * 13},{n}" for n in range(30)) + "\n"
    profile = _profile(tmp_path, content, sensitive_values="show")
    document = profile.model_dump(mode="json")
    for dataset in document["report"]["datasets"]:
        for column in dataset["columns"]:
            if column["name"] == "amount":
                column["exposure"] = mode
    path = write_text(tmp_path, "report.json", dump_json(document))

    html = render_report(load_profile(path))

    for table_id in ("numeric-table", "columns-table"):
        table = columns_table(html, table_id)
        row = next(row for row in table.rows if row.cells[0].attrs["data-v"] == "amount")
        last = row.cells[-1]
        assert not any(str(7000 + n * 13) in last.text for n in range(30)), table_id
        assert ("masked" if mode == "mask" else "hidden") in last.text


def test_exposed_values_of_a_shown_column_are_the_profile_values(tmp_path):
    profile = _profile(tmp_path, "note\nalpha\nbeta\nalpha\ngamma\n", sensitive_values="show")
    column = _column(profile, "note")

    values = exposed_values(column)

    assert values.examples and set(values.examples) <= {"alpha", "beta", "gamma"}
    assert dict(values.values)["alpha"] == 2


def test_finding_model_is_unchanged_by_the_preview():
    item = Finding(
        code="type.mixed",
        cls="issue",
        field="f",
        count=2,
        unit="occurrences",
        population=Population(kind="present_values", size=10),
        accuracy="exact",
    )
    assert item.examples == []
