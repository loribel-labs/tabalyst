import csv
from html.parser import HTMLParser

from tabalyst import analyze_csv, render_report


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
    html = render_report(analyze_csv(source))
    assert "No data records." in html
    assert "NaN" not in html


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
            if tag in {"td", "th"} and "data-order" in attrs:
                self.values.append(attrs)

    parser = Cells()
    parser.feed(render_report(profile))
    expected = str(profile.columns[0].numeric.minimum)
    assert any(
        cell["data-order"] == expected and cell["data-search"] == expected
        for cell in parser.values
    )
    assert any(
        cell["data-order"] == "33.33" and cell["data-search"] == "33.33"
        for cell in parser.values
    )
