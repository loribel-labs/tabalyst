# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the HTML report (Scan and JSON plan, tests F01 to F04 and F06,
requirements D19 and HTML-01 to HTML-09).

The behavior is specified in ``docs/dev/scan/design.md`` section 18.14. The
expectations are on the page a reader gets from the document alone.
"""

import csv
import io
import json
import re

import pytest
from scan_helpers import write_text

from tabalyst.json_text import dump_json
from tabalyst.report_config import ReportConfig
from tabalyst.reporting import DISPLAY_LIMITS, load_profile, render_report
from tabalyst.service import analyze_csv


def _config(report: dict | None = None, **scan) -> ReportConfig:
    return ReportConfig.model_validate({**(report or {}), "scan": scan})


def _cells(html: str) -> int:
    return html.count("<td") + html.count("<th")


@pytest.mark.scan_json_lot("5")
def test_F01_the_html_is_the_same_from_the_json_alone(tmp_path):
    source = write_text(
        tmp_path,
        "data.csv",
        "id,city\n" + "\n".join(f"{n},{'Laval' if n % 3 else 'laval'}" for n in range(60)),
    )
    profile = analyze_csv(source)
    document = write_text(
        tmp_path, "report.json", dump_json(profile.model_dump(mode="json"))
    )
    fresh = render_report(profile)

    source.unlink()
    again = render_report(load_profile(document))

    # The source is gone and nothing changes: the page reads the document.
    assert again == fresh
    for section in ("overview", "observations", "columns", "patterns", "sample"):
        assert f'id="{section}"' in again


@pytest.mark.scan_json_lot("5")
def test_F02_exact_estimated_sample_limited_and_not_computed_are_labelled(tmp_path):
    rows = [f"ID-{n:05d},{n % 7},C{n % 5}" for n in range(400)]
    source = write_text(
        tmp_path, "data.csv", "key,small,code\n" + "\n".join(rows) + "\n"
    )

    html = render_report(
        analyze_csv(source, _config(limits={"max_distinct_per_field": 50}))
    )

    # A count that a limit stopped is written as a bound, with its estimate.
    assert "≥ 51" in html
    assert re.search(r"≈ [\d,]+ est\.", html)
    # The four words of the legend are on the page, each with its meaning.
    assert '<span class="lb">≥ 51</span>' in html
    for kind in ("exact", "sample"):
        assert f'class="acc acc-{kind}"' in html
    assert "<b>≥</b> at least" in html
    # A candidate is not a defect and a remark is not an issue.
    assert "Candidate anomaly" in html or "Remark" in html
    # The pattern shares say what they count.
    assert "of sampled distinct values" in html or "of every distinct value" in html

    off = render_report(
        analyze_csv(
            source,
            _config(
                observations={"enabled": False}, pattern_inference={"enabled": False}
            ),
        )
    )
    # A block the document does not have is not computed, never rebuilt.
    assert "Not computed" in off
    assert 'id="patterns"' not in off


@pytest.mark.scan_json_lot("5")
def test_F03_html_and_script_in_the_data_are_text(tmp_path):
    hostile = ["<script>alert(1)</script>", '"><img src=x onerror=alert(2)>', "&amp;"]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["name", "<b>col</b>"])
    for n in range(40):
        writer.writerow([hostile[n % 3], hostile[(n + 1) % 3]])
    source = write_text(tmp_path, "evil.csv", buffer.getvalue())
    profile = analyze_csv(source)

    html = render_report(profile)

    for raw in ("<script>alert(1)</script>", "<img src=x onerror", "<b>col</b>"):
        assert raw not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;col&lt;/b&gt;" in html
    # Only the report's own script is in the page.
    assert html.count("<script>") == 2


@pytest.mark.scan_json_lot("5")
def test_F04_a_large_analytic_sample_keeps_the_page_light(tmp_path):
    rows = [f"v{n:05d},w{n:05d},{n}" for n in range(3000)]
    source = write_text(tmp_path, "big.csv", "a,b,c\n" + "\n".join(rows) + "\n")
    config = _config(
        {
            "value_examples": {"kept_per_column": 1000},
            "row_sample": {"start": 1000, "middle": 1000, "end": 1000},
        },
        records={"sample": {"rows": 3000, "edge": 1000}},
    )

    profile = analyze_csv(source, config)
    html = render_report(profile)

    sample = profile.datasets[0].records.sample
    assert sample.kept == 3000
    # The document holds every row; the page prints a bounded number.
    limit = DISPLAY_LIMITS["rows"]
    printed = re.findall(r'<tr data-flags="(?:start|middle|end)(?: end)?">', html)
    assert len(printed) == limit
    assert f"Showing the first {limit} of 3,000 rows kept" in html
    # Tables are paged: the rows past the first page start hidden.
    assert 'data-page-size="25"' in html and 'data-more="sample-table"' in html


@pytest.mark.scan_json_lot("5")
def test_F06_very_large_counters_keep_every_digit(tmp_path):
    big = [9007199254740993, 12345678901234567890123, 9007199254740995]
    rows = [str(big[n % 3]) for n in range(30)]
    source = write_text(tmp_path, "big.csv", "n\n" + "\n".join(rows) + "\n")
    profile = analyze_csv(source)

    html = render_report(profile)
    document = json.loads(dump_json(profile.model_dump(mode="json")))

    # The document is exact; so are the page and its sort keys.
    assert document["datasets"][0]["fields"][0]["numeric"]["value"]["min"] == big[0]
    assert "9,007,199,254,740,993" in html
    assert "12,345,678,901,234,567,890,123" in html
    assert 'data-v="9007199254740993"' in html
    # An integer beyond 2^53 is compared as a BigInt by the sort and the filters.
    assert "BigInt(" in html
