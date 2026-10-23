# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The page of one column (Report overview lot R10).

The contract is ``docs/dev/report/summary-table.md`` 19. The tests check that the
page applies the exposure to a raw document, that it shows the classification and
the findings, and that the public signatures did not move.
"""

import inspect
import re

import pytest
from scan_helpers import write_text

import tabalyst
from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_column_page import Neighbour
from tabalyst.report_config import ReportConfig
from tabalyst.reporting import dataset_views, load_profile, render_column_report
from tabalyst.scanner import ScanConfig


def _contacts():
    lines = ["contact,row"]
    lines += [f"zzsecret{n}@example.org,{n}" for n in range(100)]
    lines += [f"zzbad {n}@example.org,{100 + n}" for n in range(3)]
    return "\n".join(lines) + "\n"


# Panels the Scan exposes at the source (strings, patterns, evidence, sample): a raw
# document forced to another exposure is checked on the panels the page gates itself.
SCAN_EXPOSED = ("shape", "formats", "scan-evidence", "sample")


def _gated(html):
    for panel in SCAN_EXPOSED:
        html = re.sub(rf'<section class="panel" id="{panel}".*?</section>', "", html, flags=re.DOTALL)
    return html


def _page(tmp_path, content, name, mode="show", forced=None):
    source = write_text(tmp_path, "data.csv", content)
    exposure = {"sensitive_values": mode}
    config = ReportConfig(scan=ScanConfig.model_validate({"exposure": exposure}))
    profile = analyze_csv(source, config)
    if forced is not None:
        document = profile.model_dump(mode="json")
        for dataset in document["report"]["datasets"]:
            # A document written before its summaries: they are built at the render,
            # through the exposure the document now declares.
            dataset["table"] = None
            for column in dataset["columns"]:
                column["summary"] = None
                if column["name"] == name:
                    column["exposure"] = forced
        profile = load_profile(write_text(tmp_path, "report.json", dump_json(document)))
    dataset = dataset_views(profile)[0]
    column = next(c for c in dataset.columns if c.name == name)
    return render_column_report(profile, dataset, column, "report.html")


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_column_page_writes_no_raw_value_of_a_masked_or_hidden_column(tmp_path, mode):
    html = _page(tmp_path, _contacts(), "contact", mode)

    assert "zzsecret" not in html and "zzbad" not in html


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_column_page_applies_the_exposure_to_a_raw_document(tmp_path, mode):
    html = _gated(_page(tmp_path, _contacts(), "contact", forced=mode))

    assert "zzsecret" not in html and "zzbad" not in html


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_an_enum_page_lists_no_raw_value_when_the_column_is_not_shown(tmp_path, mode):
    content = "status,row\n" + "\n".join(
        f"{word},{n}" for n, word in enumerate(["zzopen"] * 6 + ["zzclosed"] * 4)
    ) + "\n"

    html = _gated(_page(tmp_path, content, "status", forced=mode))

    assert "zzopen" not in html and "zzclosed" not in html


def test_a_shown_column_page_lists_its_values(tmp_path):
    content = "status,row\n" + "\n".join(
        f"{word},{n}" for n, word in enumerate(["zzopen"] * 6 + ["zzclosed"] * 4)
    ) + "\n"

    html = _page(tmp_path, content, "status")

    assert "zzopen" in html and "zzclosed" in html


def test_the_page_shows_the_classification_and_the_findings(tmp_path):
    html = _page(tmp_path, _contacts(), "contact")

    assert "Stored as" in html and "% sure" in html
    assert 'id="findings"' in html and "Type errors" not in html


def _dates():
    cells = [f"2026-01-{n % 28 + 1:02d}" for n in range(60)]
    cells += ["03/04/2026", "05/06/2026", "07/08/2026", "11/12/2026"]
    return "when,row\n" + "\n".join(f"{c},{n}" for n, c in enumerate(cells)) + "\n"


def _sections(html):
    return re.findall(r'<section class="panel" id="([\w-]+)"', html)


def test_the_blocks_come_in_the_order_of_the_questions_a_reader_asks(tmp_path):
    html = _page(tmp_path, _dates(), "when")

    expected = ["summary", "findings", "values", "shape", "formats", "cleaning", "limits", "scan-evidence"]
    assert [i for i in _sections(html) if i in expected] == expected


def test_a_column_with_nothing_to_report_says_so(tmp_path):
    content = "status,row\n" + "\n".join(f"{w},{n}" for n, w in enumerate(["open", "closed"] * 5)) + "\n"

    html = _page(tmp_path, content, "status")

    assert "Nothing was found in this column." in html
    assert "No measure of this column was limited." in html


def test_an_error_has_its_own_card_in_the_class_colour(tmp_path):
    content = "amount,row\n" + "\n".join(f"{n * 3},{n}" for n in range(60)) + "\nabc,60\nxyz,61\n"

    html = _page(tmp_path, content, "amount")

    assert 'class="fnd fnd-error"' in html and "fcls-error" in html


def test_the_detail_of_a_finding_is_printed_in_its_card_from_the_stored_member(tmp_path):
    html = _page(tmp_path, _dates(), "when")

    card = re.search(r'<article class="fnd fnd-issue".*?</article>', html, flags=re.DOTALL).group(0)
    assert "Formats that fit the same values" in card
    assert "DD/MM/YYYY or MM/DD/YYYY" in card


def test_a_format_is_printed_once_and_the_detector_json_is_not_printed(tmp_path):
    html = _page(tmp_path, _dates(), "when")

    assert html.count("<code>YYYY-MM-DD</code>") == 1
    assert '<pre class="column-json"' not in html and "Detector details" not in html


def test_the_whitespace_observation_is_told_by_its_issue_and_not_listed_again_as_a_remark(tmp_path):
    cells = ["alpha beta"] * 40 + ["alpha  beta"] * 3
    content = "text,row\n" + "\n".join(f"{c},{n}" for n, c in enumerate(cells)) + "\n"

    html = _page(tmp_path, content, "text")

    assert "Cells changed by collapsing repeated internal whitespace" not in html
    assert "Repeated whitespace" in html


def test_the_page_links_its_neighbours_when_they_exist(tmp_path):
    source = write_text(tmp_path, "data.csv", "a,b,c\n1,x,2\n2,y,3\n")
    profile = analyze_csv(source, ReportConfig())
    dataset = dataset_views(profile)[0]
    column = dataset.columns[1]
    previous, following = Neighbour(name="a", href="col-01-a.html"), Neighbour(name="c", href="col-03-c.html")

    html = render_column_report(profile, dataset, column, "report.html", previous, following)
    alone = render_column_report(profile, dataset, column, "report.html")

    assert 'rel="prev"' in html and 'href="col-03-c.html"' in html
    assert 'rel="prev"' not in alone and 'rel="next"' not in alone


PUBLIC_PARAMETERS = {
    "scan": "source config registry on_progress on_record workers counters",
    "generate_scans": (
        "input_specs output output_dir config_path delimiter encoding collections force"
        " on_progress workers counters project_storage refresh html"
    ),
    "analyze_scan": "scan_path config_path on_progress",
    "generate_reports": (
        "input_specs output output_dir separator encoding collections config_path force"
        " details on_progress from_scan workers all_collections deep confirmed confirm"
    ),
    "render_report": "profile column_links views",
}


@pytest.mark.parametrize("name", sorted(PUBLIC_PARAMETERS))
def test_the_public_signatures_did_not_change(name):
    parameters = list(inspect.signature(getattr(tabalyst, name)).parameters)

    assert parameters == PUBLIC_PARAMETERS[name].split()


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_variant_groups_of_a_raw_document_go_through_the_exposure(tmp_path, mode):
    cells = ["ZzAlpha"] * 5 + ["zzalpha"] * 4 + ["ZZALPHA"] * 3 + ["zzbeta"] * 4 + ["ZzBeta"] * 3
    content = "tag,row\n" + "\n".join(f"{v},{n}" for n, v in enumerate(cells)) + "\n"

    html = _page(tmp_path, content, "tag", forced=mode)

    assert "ZzAlpha" not in _gated(html) and "zzbeta" not in _gated(html)
    shown = _page(tmp_path, content, "tag")
    assert "ZzAlpha" in shown
