# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Detail of the whitespace findings in the Findings table (lot R12, tranche 4).

The contract is ``docs/dev/report/summary-table.md`` 22: the cells each normalization stage
changed, and examples of them taken from the sample (the original values, whitespace kept),
by kind, through the exposure of the column.
"""

import json

import pytest
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.report_finding_details import (
    EXAMPLE_MAX_CHARS,
    EXAMPLES_PER_KIND,
    whitespace_window,
)
from tabalyst.report_labels import spoken_whitespace, visible_whitespace
from tabalyst.report_profile import build_profile
from tabalyst.report_summary import attach_summaries
from tabalyst.reporting import load_profile, render_report
from tabalyst.scanner import ScanConfig, scan

NAMES = [f"Name{n:03d}" for n in range(90)]
# One leading, one trailing, one repeated, one with all three.
MIXED = [" Alice", "Bob ", "Carl  Dean", " Eve  Fay "]


def _csv(odd: list[str]) -> str:
    rows = ["name,row"] + [f'"{value}",{n}' for n, value in enumerate(NAMES + odd)]
    return "\n".join(rows) + "\n"


def _built(tmp_path, content):
    """The Scan and the Report built from it, as ``tabalyst report`` does."""
    source = write_text(tmp_path, "data.csv", content)
    result = scan(source, config=ScanConfig.model_validate({}))
    return result, build_profile(result, ReportConfig(scan=result.config))


def _detail(profile):
    column = profile.report.datasets[0].columns[0]
    assert column.summary is not None
    return column.summary.finding_details.whitespace


def _examples(detail):
    return {kind: [e.value for e in detail.examples if e.kind == kind] for kind in ("leading", "trailing", "repeated")}


def test_the_detail_counts_the_cells_each_stage_changed(tmp_path):
    _, profile = _built(tmp_path, _csv(MIXED))

    detail = _detail(profile)

    assert detail is not None
    # Trimmed: Alice, Bob, Eve. Collapsed (after trimming): Carl and Eve.
    assert [(item.stage, item.changed) for item in detail.stages] == [
        ("trim", 3),
        ("collapse_whitespace", 2),
    ]
    assert detail.state == "shown" and detail.examples_from == "sample"


def test_the_examples_are_original_values_by_kind(tmp_path):
    _, profile = _built(tmp_path, _csv(MIXED))

    detail = _detail(profile)

    assert detail is not None
    assert _examples(detail) == {
        "leading": [" Alice", " Eve  Fay "],
        "trailing": ["Bob "],
        "repeated": [" Eve  Fay ", "Carl  Dean"],
    }


def test_only_the_stages_that_have_an_observation_are_described(tmp_path):
    _, profile = _built(tmp_path, _csv(["Carl  Dean", "Fay   Gus"]))

    detail = _detail(profile)

    assert detail is not None
    assert [item.stage for item in detail.stages] == ["collapse_whitespace"]
    assert set(_examples(detail)["leading"] + _examples(detail)["trailing"]) == set()
    assert _examples(detail)["repeated"] == ["Carl  Dean", "Fay   Gus"]


def test_a_column_without_whitespace_findings_has_no_detail(tmp_path):
    _, profile = _built(tmp_path, _csv([]))

    assert _detail(profile) is None


def test_the_examples_of_a_kind_are_bounded_and_ordered(tmp_path):
    odd = [f" Lead{n}" for n in range(6)]
    _, profile = _built(tmp_path, _csv(odd))

    detail = _detail(profile)

    assert detail is not None
    leading = _examples(detail)["leading"]
    assert len(leading) == EXAMPLES_PER_KIND
    assert leading == sorted(leading)


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_exposure_keeps_the_counts_and_gates_the_examples(tmp_path, mode):
    result, profile = _built(tmp_path, _csv(MIXED))
    shown = _detail(profile)
    for column in profile.report.datasets[0].columns:
        column.exposure = mode

    attach_summaries(profile, result)

    detail = _detail(profile)
    assert shown is not None and detail is not None
    assert detail.state == ("masked" if mode == "mask" else "hidden")
    assert detail.stages == shown.stages
    text = detail.model_dump_json()
    assert "Alice" not in text and "Carl" not in text and "Fay" not in text
    if mode == "hide":
        assert detail.examples_from == "none" and not detail.examples


def test_a_document_attached_at_the_render_keeps_the_counts(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(MIXED))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    whole = _detail(profile)
    document = profile.model_dump(mode="json")
    for dataset in document["report"]["datasets"]:
        dataset["table"] = None
        for column in dataset["columns"]:
            column["summary"] = None
    older = load_profile(write_text(tmp_path, "older.json", dump_json(document)))

    render_report(older)

    detail = _detail(older)
    assert whole is not None and detail is not None
    assert detail.stages == whole.stages


def test_the_stored_detail_holds_numbers_and_values_and_no_sentence(tmp_path):
    _, profile = _built(tmp_path, _csv(MIXED))
    column = json.loads(dump_json(profile.model_dump(mode="json")))["report"]["datasets"][0][
        "columns"
    ][0]

    detail = column["summary"]["finding_details"]["whitespace"]

    assert set(detail) == {"state", "examples_from", "stages", "examples"}
    assert set(detail["examples"][0]) == {"kind", "value", "count", "truncated"}
    # The value is the raw one: the marks are written at the render.
    assert " Alice" in {item["value"] for item in detail["examples"]}
    assert "Surrounding" not in json.dumps(detail)


def test_the_marks_and_the_words_of_an_example():
    assert visible_whitespace(" a\tb  c\n") == "·a→b··c↵"
    assert visible_whitespace("a b") == "a␣b"
    assert spoken_whitespace("leading", "  x") == "2 leading whitespace characters"
    assert spoken_whitespace("trailing", "x ") == "1 trailing whitespace character"
    assert spoken_whitespace("repeated", "a  b") == "whitespace repeated inside the text"


def test_the_findings_table_prints_the_examples_with_visible_marks(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(MIXED))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    html = render_report(reloaded)

    assert "Whitespace before the text" in html and "Whitespace after the text" in html
    assert "Whitespace repeated inside the text" in html
    assert "·Alice" in html and "Bob·" in html and "Carl··Dean" in html
    assert "1 leading whitespace character" in html
    assert "Marks show the whitespace" in html


def test_the_render_of_the_detail_equals_the_render_from_memory(tmp_path):
    source = write_text(tmp_path, "data.csv", _csv(MIXED))
    profile = analyze_csv(source, ReportConfig(scan=ScanConfig.model_validate({})))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    def strip(html: str) -> str:
        return "\n".join(
            line for line in html.splitlines() if "generated" not in line.lower()
        )

    assert strip(render_report(reloaded)) == strip(render_report(profile))


@pytest.mark.parametrize("kind", ["leading", "trailing", "repeated"])
def test_a_long_example_keeps_the_part_that_shows_its_whitespace(kind):
    body = "x" * 100
    value = {"leading": " " + body, "trailing": body + " ", "repeated": body + "  " + body}[kind]

    window, cut = whitespace_window(kind, value)

    assert cut and len(window) <= EXAMPLE_MAX_CHARS
    assert {"leading": window[0] == " ", "trailing": window[-1] == " ", "repeated": "  " in window}[kind]
    # A cut side is marked, so that the reader knows the text goes on.
    assert ("…" in window) is True
    assert whitespace_window(kind, "short ") == ("short ", False)
