# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Detail of the ambiguous dates in the Findings table (lot R12, tranche 1).

The contract is ``docs/dev/report/summary-table.md`` 22: the pairs of formats that fit
the same values, the evidence of each day-month order and the formats read without doubt,
stored with the summary of the column, in codes and numbers.
"""

import json

import pytest
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.report_finding_details import DATE_FORMATS_SHOWN
from tabalyst.reporting import load_profile, render_report
from tabalyst.scanner import ScanConfig


def _dates() -> str:
    # 6 unambiguous day-first, 2 month-first, 5 that fit both orders, 3 ISO.
    rows = ["born,name"]
    rows += [f"{day:02d}/03/2020,a{day}" for day in range(13, 19)]
    rows += [f"03/{day:02d}/2021,b{day}" for day in range(20, 22)]
    rows += [f"0{day}/04/2020,c{day}" for day in (1, 2, 3, 5, 6)]
    rows += [f"2022-01-0{day},d{day}" for day in range(1, 4)]
    return "\n".join(rows) + "\n"


def _profile(tmp_path, content, mode="show", **detectors):
    source = write_text(tmp_path, "data.csv", content)
    config = ReportConfig(
        scan=ScanConfig.model_validate(
            {"exposure": {"sensitive_values": mode}, "detectors": detectors}
        )
    )
    return analyze_csv(source, config)


def _detail(profile, name="born"):
    column = next(c for c in profile.report.datasets[0].columns if c.name == name)
    assert column.summary is not None
    return column.summary.finding_details.dates


def test_the_detail_names_the_formats_that_fit_the_same_values(tmp_path):
    detail = _detail(_profile(tmp_path, _dates()))

    assert detail is not None
    assert detail.ambiguous_count == 5
    assert [(item.formats, item.count) for item in detail.candidates] == [
        (["DD/MM/YYYY", "MM/DD/YYYY"], 5)
    ]
    assert detail.more_candidates == 0


def test_the_detail_counts_the_values_written_without_doubt_by_order(tmp_path):
    detail = _detail(_profile(tmp_path, _dates()))

    assert detail is not None
    assert [(item.order, item.count) for item in detail.readings] == [
        ("DMY", 6),
        ("MDY", 2),
    ]
    assert {(item.format, item.order, item.count) for item in detail.formats} >= {
        ("DD/MM/YYYY", "DMY", 6),
        ("YYYY-MM-DD", "YMD", 3),
    }


def test_a_column_whose_order_the_configuration_chose_has_no_detail(tmp_path):
    # The Scan reads those values, so it raises no observation: nothing is ambiguous.
    profile = _profile(tmp_path, _dates(), date={"ambiguous_order": "DMY"})

    assert _detail(profile) is None


def test_a_column_without_ambiguous_dates_has_no_detail(tmp_path):
    rows = ["born,name"] + [f"{day:02d}/03/2020,a{day}" for day in range(13, 25)]
    profile = _profile(tmp_path, "\n".join(rows) + "\n")

    assert _detail(profile) is None
    assert _detail(profile, "name") is None


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_exposure_keeps_the_shapes_and_leaks_no_date(tmp_path, mode):
    profile = _profile(tmp_path, _dates())
    shown = _detail(profile)
    document = profile.model_dump(mode="json")
    for column in document["report"]["datasets"][0]["columns"]:
        column["exposure"] = mode
    edited = load_profile(write_text(tmp_path, "edited.json", dump_json(document)))

    render_report(edited)

    column = next(c for c in edited.report.datasets[0].columns if c.name == "born")
    assert column.exposure == mode
    assert column.summary is not None
    # A format is a shape, not a value: it stays whatever the exposure says.
    assert column.summary.finding_details.dates == shown
    text = column.summary.finding_details.model_dump_json()
    assert "2020" not in text and "2021" not in text and "2022" not in text


def test_formats_beyond_the_bound_are_counted_not_listed(tmp_path):
    separators = ["-", "/", "."]
    rows = ["born"] + [
        f"{day}{sep}{month}{sep}2020"
        for sep in separators
        for day, month in ((1, 2), (13, 2), (2, 13))
    ]
    profile = _profile(tmp_path, "\n".join(rows) + "\n")

    detail = _detail(profile)

    assert detail is not None
    assert len(detail.candidates) <= DATE_FORMATS_SHOWN
    assert len(detail.formats) <= DATE_FORMATS_SHOWN
    assert detail.more_candidates == max(0, 3 - DATE_FORMATS_SHOWN)


def test_the_stored_detail_holds_codes_and_numbers_and_no_sentence(tmp_path):
    profile = _profile(tmp_path, _dates())
    document = profile.model_dump(mode="json")
    column = next(c for c in document["report"]["datasets"][0]["columns"] if c["name"] == "born")

    text = json.dumps(column["summary"]["finding_details"])

    assert set(column["summary"]["finding_details"]["dates"]) == {
        "ambiguous_count",
        "candidates",
        "more_candidates",
        "readings",
        "formats",
        "more_formats",
    }
    assert "Ambiguous" not in text and "ambiguous" not in text.replace("ambiguous_count", "")
    assert "variants" in column["summary"]["finding_details"]


def test_the_findings_table_prints_the_stored_detail(tmp_path):
    profile = _profile(tmp_path, _dates())
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    html = render_report(reloaded)

    assert "DD/MM/YYYY or MM/DD/YYYY" in html
    assert "Formats that fit the same values" in html
    assert "Day first (DD/MM)" in html and "Month first (MM/DD)" in html
    assert "No order was chosen" in html


def test_the_render_of_the_detail_equals_the_render_from_memory(tmp_path):
    profile = _profile(tmp_path, _dates())
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    def strip(html: str) -> str:
        return "\n".join(
            line for line in html.splitlines() if "generated" not in line.lower()
        )

    assert strip(render_report(reloaded)) == strip(render_report(profile))
