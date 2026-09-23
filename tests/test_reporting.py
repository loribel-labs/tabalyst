import csv
from html.parser import HTMLParser

from tabalyst import analyze_csv, render_report
from tabalyst.execution_log import tabalyst_version
from tabalyst.reporting import format_number, format_seconds, format_size


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
    assert profile.preview[0].values[0] == payload


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
    assert html.count('class="rep-tab"') == 8
    for section in ("overview", "columns", "transformations", "numeric", "dates", "strings", "sample", "settings"):
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
    expected = str(profile.columns[0].numeric.minimum)
    assert any(cell["data-v"] == expected for cell in parser.values)
    assert any(
        cell["data-v"] == "33.33"
        for cell in parser.values
    )
