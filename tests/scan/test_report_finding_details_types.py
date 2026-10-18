# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Detail of the mixed types in the Findings table (lot R12, tranche 5).

The contract is ``docs/dev/report/summary-table.md`` 22: the composition of a column with no
dominant technical type, from the types the Scan counted. There is no example and nothing goes
through the exposure.
"""

import json

import pytest
from scan_helpers import write_text

from tabalyst import analyze_csv
from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.reporting import load_profile, render_report
from tabalyst.scanner import ScanConfig


def _csv(integers: int, decimals: int, words: int, dates: int = 0) -> str:
    rows = ["value,row"]
    rows += [str(n + 1) for n in range(integers)]
    rows += [f"{n}.5" for n in range(decimals)]
    rows += [f"word{n}" for n in range(words)]
    rows += [f"2020-01-{n % 28 + 1:02d}" for n in range(dates)]
    body = [f"{value},{n}" for n, value in enumerate(rows[1:])]
    return "\n".join(rows[:1] + body) + "\n"


def _profile(tmp_path, content, mode="show"):
    source = write_text(tmp_path, "data.csv", content)
    config = ReportConfig(scan=ScanConfig.model_validate({"exposure": {"sensitive_values": mode}}))
    return analyze_csv(source, config)


def _column(profile):
    column = profile.report.datasets[0].columns[0]
    assert column.summary is not None
    return column


def _detail(profile):
    return _column(profile).summary.finding_details.types


def test_the_detail_gives_the_composition_by_type(tmp_path):
    profile = _profile(tmp_path, _csv(integers=40, decimals=0, words=10, dates=10))

    detail = _detail(profile)

    assert detail is not None
    assert detail.total == 60
    assert [(item.type, item.count) for item in detail.types] == [
        ("integer", 40),
        ("date", 10),
        ("text", 10),
    ]
    assert (detail.closest.type, detail.closest.count) == ("integer", 40)
    assert detail.outside == 20


def test_integers_and_decimals_count_together_as_the_closest_numeric_type(tmp_path):
    profile = _profile(tmp_path, _csv(integers=20, decimals=20, words=25))

    detail = _detail(profile)

    assert detail is not None
    assert (detail.closest.type, detail.closest.count) == ("number", 40)
    assert detail.outside == 25


def test_the_outside_count_is_the_one_of_the_finding(tmp_path):
    profile = _profile(tmp_path, _csv(integers=40, decimals=0, words=10, dates=10))
    column = _column(profile)

    detail = column.summary.finding_details.types
    finding = next(item for item in column.summary.findings.issues.items if item.code == "type.mixed")

    assert detail is not None
    assert detail.outside == finding.count
    assert detail.total == finding.population.size


def test_a_column_that_is_not_mixed_has_no_detail(tmp_path):
    clean = _profile(tmp_path, _csv(integers=30, decimals=0, words=0))
    # A few words in numbers are type outliers (an Error), not a mixed column.
    outliers = _profile(tmp_path, _csv(integers=60, decimals=0, words=2))

    assert _detail(clean) is None
    assert _detail(outliers) is None


@pytest.mark.parametrize("mode", ["mask", "hide"])
def test_the_exposure_changes_nothing_and_no_value_is_stored(tmp_path, mode):
    profile = _profile(tmp_path, _csv(integers=40, decimals=0, words=10, dates=10))
    shown = _detail(profile)
    document = profile.model_dump(mode="json")
    for column in document["report"]["datasets"][0]["columns"]:
        column["exposure"] = mode
    edited = load_profile(write_text(tmp_path, "edited.json", dump_json(document)))

    render_report(edited)

    detail = _detail(edited)
    assert shown is not None and detail == shown
    text = detail.model_dump_json()
    assert "word" not in text and "2020" not in text


def test_the_stored_detail_holds_codes_and_numbers_and_no_sentence(tmp_path):
    profile = _profile(tmp_path, _csv(integers=40, decimals=0, words=10, dates=10))
    column = json.loads(dump_json(profile.model_dump(mode="json")))["report"]["datasets"][0][
        "columns"
    ][0]

    detail = column["summary"]["finding_details"]["types"]

    assert set(detail) == {"total", "types", "closest", "outside"}
    assert set(detail["types"][0]) == {"type", "count"}
    assert "Integers" not in json.dumps(detail) and "outside" not in json.dumps(detail["types"])


def test_the_findings_table_prints_the_stored_detail(tmp_path):
    profile = _profile(tmp_path, _csv(integers=40, decimals=0, words=10, dates=10))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    html = render_report(reloaded)

    assert "Values by technical type" in html and "Closest type" in html
    assert "Integers 66.67%" in html and "Dates 16.67%" in html
    assert "20 values are outside the closest type." in html


def test_the_render_of_the_detail_equals_the_render_from_memory(tmp_path):
    profile = _profile(tmp_path, _csv(integers=40, decimals=0, words=10, dates=10))
    reloaded = load_profile(
        write_text(tmp_path, "report.json", dump_json(profile.model_dump(mode="json")))
    )

    def strip(html: str) -> str:
        return "\n".join(
            line for line in html.splitlines() if "generated" not in line.lower()
        )

    assert strip(render_report(reloaded)) == strip(render_report(profile))
