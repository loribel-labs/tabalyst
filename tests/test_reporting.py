# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import csv
import json
from html.parser import HTMLParser
from pathlib import Path

import pytest

from tabalyst import ReportConfig, analyze, analyze_csv, render_report
from tabalyst.errors import ReportError
from tabalyst.execution_log import tabalyst_version
from tabalyst.reporting import (
    breakable,
    column_pages,
    format_number,
    format_seconds,
    format_size,
    render_column_report,
)


@pytest.fixture(autouse=True)
def isolated_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))


def test_report_numbers_use_scientific_notation_only_above_threshold():
    assert format_number(10**10) == "10,000,000,000"
    assert format_number(12_345_678_901) == "1.2346e+10"
    assert format_number(-123_456_789_012) == "-1.2346e+11"
    assert format_number(1234.5) == "1,234.5"


def test_report_metadata_formats_duration_and_source_size_compactly():
    assert format_seconds(0.645) == "0.65"
    assert format_seconds(1.0) == "1"
    assert format_size(805 * 1024 + 307) == "805.3 KB"
    assert format_size(1024**2) == "1.0 MB"


def test_long_names_may_break_after_separators_and_stay_escaped():
    assert breakable("frequence_paiement") == "frequence_<wbr>paiement"
    assert breakable("orders[].items[].unit_price") == (
        "orders[].<wbr>items[].<wbr>unit_<wbr>price"
    )
    assert breakable("<b>_x") == "&lt;b&gt;_<wbr>x"
    assert breakable("plain") == "plain"


def test_sample_headers_let_long_names_break(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("date_of_birth,city\n2001-02-03,Laval\n", encoding="utf-8")

    html = render_report(analyze_csv(source))

    assert "date_<wbr>of_<wbr>birth" in html


def test_csv_content_cannot_inject_markup(tmp_path):
    source = tmp_path / "input.csv"
    payload = '<script>alert("injected")</script>'
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([payload, "other"])
        writer.writerow([payload, '<img src=x onerror="alert(1)">'])
    profile = analyze_csv(source)
    html = render_report(profile)
    assert payload not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html
    assert profile.datasets[0].preview[0].values[0] == payload


def test_header_only_report_is_renderable(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\n", encoding="utf-8")
    profile = analyze_csv(source)
    html = render_report(profile)
    assert "No data records." in html
    assert ">NaN<" not in html


def test_footer_includes_version_copyright_and_official_links(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a\n1\n", encoding="utf-8")

    profile = analyze_csv(source)
    html = render_report(profile)

    assert f"v{tabalyst_version()}" in html
    assert "Gregory Borelli" in html
    assert "Catalyseur Numérique" in html
    assert f"© {profile.generated_at.year} Gregory Borelli" in html
    assert html.count('href="https://tabalyst.com/"') == 3
    assert html.count('aria-label="Tabalyst official website"') == 2
    assert 'href="https://github.com/loribel-labs/tabalyst"' in html
    assert html.count('target="_blank" rel="noopener noreferrer"') == 4


def test_report_includes_sidebar_navigation_for_each_report_section(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("amount,joined,name\n1,2026-01-01,Alice\n", encoding="utf-8")

    html = render_report(analyze_csv(source))

    assert 'class="side"' in html
    assert 'rel="icon" type="image/svg+xml"' in html
    assert '<section class="panel" id="overview"' in html
    assert '<section class="panel" id="columns"' in html
    assert '<section class="panel" id="sample"' in html
    assert 'Numeric analysis' in html
    assert html.count('class="rep-tab"') == 9
    for section in ("overview", "columns", "transformations", "numeric", "dates", "strings", "detectors", "sample", "settings"):
        assert f'href="#{section}"' in html

    assert 'data-label="Median"' in html
    assert 'data-label="Distinct"' in html
    assert '<span class="ht">Formats</span>' in html


def test_report_omits_navigation_for_absent_analysis_sections(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name\nAlice\nBob\n", encoding="utf-8")

    html = render_report(analyze_csv(source))

    assert 'href="#numeric"' not in html
    assert 'href="#dates"' not in html
    assert 'href="#strings"' in html
    assert html.count('<div class="metric') == 4


def test_numeric_sort_and_filter_values_are_not_display_rounded(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("amount,name\n1.234567,A\n9.876543,B\n,C\n", encoding="utf-8")
    profile = analyze_csv(source)

    class Cells(HTMLParser):
        def __init__(self):
            super().__init__()
            self.values = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag in {"td", "th"} and "data-v" in attrs:
                self.values.append(attrs)

    parser = Cells()
    parser.feed(render_report(profile))
    expected = str(profile.datasets[0].columns[0].numeric.minimum)
    assert any(cell["data-v"] == expected for cell in parser.values)
    assert any(
        cell["data-v"] == "33.33"
        for cell in parser.values
    )


def test_column_reports_are_independent_and_linked(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("Status,Statüs,empty\nopen,closed,\nclosed,open,\n", encoding="utf-8")
    output = tmp_path / "report.html"

    analyze(source, output, details=True)

    pages = sorted((tmp_path / "report").glob("col-*.html"))
    assert [page.name for page in pages] == [
        "col-01-status.html",
        "col-02-status.html",
        "col-03-empty.html",
    ]
    main = output.read_text(encoding="utf-8")
    assert 'href="report/col-01-status.html"' in main
    for page in pages:
        html = page.read_text(encoding="utf-8")
        assert 'href="../report.html"' in html
        assert 'class="side"' in html
        assert '<style>' in html and '<script>' in html
        assert '<section class="panel" id="overview"' in html
    assert "open" in pages[0].read_text(encoding="utf-8")

    with pytest.raises(ReportError):
        analyze(source, output)
    analyze(source, output, force=True, details=False)
    assert not (tmp_path / "report").exists()
    assert 'href="report/col-01-status.html"' not in output.read_text(encoding="utf-8")
    analyze(source, output, force=True, details=True)
    assert len(list((tmp_path / "report").glob("col-*.html"))) == 3


def test_report_has_no_column_pages_by_default(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name\nAlice\n", encoding="utf-8")
    output = tmp_path / "report.html"

    analyze(source, output)

    assert output.is_file()
    assert not (tmp_path / "report").exists()
    assert "col-01-name.html" not in output.read_text(encoding="utf-8")


def test_disabling_details_preserves_unrelated_files(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name\nAlice\n", encoding="utf-8")
    output = tmp_path / "report.html"
    analyze(source, output, details=True)
    notes = tmp_path / "report" / "notes.txt"
    notes.write_text("Keep this", encoding="utf-8")

    analyze(source, output, force=True)

    assert notes.read_text(encoding="utf-8") == "Keep this"
    assert not list((tmp_path / "report").glob("col-*.html"))


def test_column_page_shows_all_stored_enum_values_and_escapes_them(tmp_path):
    source = tmp_path / "input.csv"
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["state"])
        writer.writerows([["open"], ["closed"], ["<b>bad</b>"]])
    profile = analyze_csv(source)
    page, dataset, column = column_pages(profile, Path("report.html"))[0]

    html = render_column_report(profile, dataset, column, "../report.html")

    assert page.name == "col-01-state.html"
    assert "open" in html and "closed" in html
    assert "&lt;b&gt;bad&lt;/b&gt;" in html
    assert "<b>bad</b>" not in html
    assert column.scan_details.value_count == 3
    assert column.scan_details.first.value == "open"
    assert column.scan_details.last.value == "<b>bad</b>"


def test_json_datasets_get_distinct_numbered_column_pages(tmp_path):
    source = tmp_path / "input.json"
    source.write_text(
        '{"customers":[{"city":"Ottawa"},{"city":"Laval"}]}',
        encoding="utf-8",
    )
    output = tmp_path / "report.html"

    analyze(source, output, details=True)

    pages = sorted((tmp_path / "report").glob("col-*.html"))
    profile = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
    assert len(pages) == sum(len(dataset["columns"]) for dataset in profile["datasets"])
    assert [int(page.name.split("-")[1]) for page in pages] == list(
        range(1, len(pages) + 1)
    )
    assert all('href="../report.html"' in page.read_text(encoding="utf-8") for page in pages)


def test_scan_evidence_keeps_sensitive_values_masked(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("email\nalice@example.org\nbob@example.org\n", encoding="utf-8")

    profile = analyze_csv(source)
    column = profile.datasets[0].columns[0]
    html = render_column_report(profile, profile.datasets[0], column, "../report.html")

    assert column.exposure == "mask"
    assert "alice@example.org" not in profile.model_dump_json()
    assert "alice@example.org" not in html
    assert column.scan_details.first.value != "alice@example.org"


def test_enumeration_keeps_all_values_above_general_display_limit(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("state\nopen\nclosed\nopen\n", encoding="utf-8")
    config = ReportConfig(
        value_examples={"full_distribution_max_distinct": 1},
        scan={"detectors": {"enumeration": {"minimum_values": 1}}},
    )

    column = analyze_csv(source, config).datasets[0].columns[0]

    assert column.semantic_type == "enumeration"
    assert column.value_profile.selection == "complete"
    assert {item.value: item.count for item in column.value_profile.values} == {
        "open": 2,
        "closed": 1,
    }


def test_column_links_encode_special_output_names(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("name\nAlice\n", encoding="utf-8")
    output = tmp_path / "sales #1.html"

    analyze(source, output, details=True)

    main = output.read_text(encoding="utf-8")
    page = tmp_path / "sales #1" / "col-01-name.html"
    assert 'href="sales%20%231/col-01-name.html"' in main
    assert 'href="../sales%20%231.html"' in page.read_text(encoding="utf-8")
