# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The insight cards of the report (design 20.19 to 20.28, lot 20): what the
later analyses of the second pass found, laid out with the accuracy of each
figure, rendered from the document alone (HTML-01, F01)."""

import csv
import json
import re

import pytest
from scan_helpers import write_json
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.report_insights import FAMILY_ORDER, dataset_insights
from tabalyst.reporting import (
    column_pages,
    dataset_views,
    load_profile,
    render_column_report,
    render_report,
)

runner = CliRunner()
BIG = 9007199254740993


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _write(path, header, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _rich_source(tmp_path):
    """Units, a number beyond float64, a repeated reference, hostile text, a
    category that explains a number and dates of several kinds."""
    rows = []
    for n in range(900):
        reference = f"R{n:05d}"
        if n in (7, 300):
            reference = "R<b>00001</b>"
        size = f"{(n * 7) % 90 + 1} {['Go', 'To', 'km/h'][n % 3]}"
        if n == 5:
            size = f"{BIG} Go"
        price = f"{[900, 500, 100][n % 3] + (n * 37) % 90}.{n % 100:02d}"
        rows.append(
            [
                reference,
                size,
                price,
                ["gold", "silver", "bronze"][n % 3],
                f"2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}",
                "<script>alert(1)</script>" if n % 97 == 0 else f"ok{n % 40}",
            ]
        )
    path = tmp_path / "rich.csv"
    _write(path, ["ref", "size", "price", "kind", "signed", "note"], rows)
    return path


def _report(source, *options):
    result = runner.invoke(app, ["report", str(source), *options, "--deep", "--yes"])
    assert result.exit_code == 0, result.output
    return source.with_suffix(".json")


@pytest.fixture
def rich(tmp_path):
    source = _rich_source(tmp_path)
    # One family per column: the hostile values have a structure of their own,
    # which is not published, so no pattern reads them and they are left out.
    config = tmp_path / "families.json"
    config.write_text(
        json.dumps({"scan": {"pattern_inference": {"max_families": 1}}}), encoding="utf-8"
    )
    path = _report(source, "--config", str(config))
    return source, path, load_profile(path)


def test_every_later_analysis_has_a_card_with_its_accuracy(rich):
    _, _, profile = rich

    cards = dataset_views(profile)[0].insights

    families = {card.family for card in cards}
    assert {"measures", "shape", "parts", "residuals", "duplicates", "categories"} <= families
    assert [card.family for card in cards] == sorted(
        (card.family for card in cards), key=FAMILY_ORDER.index
    )
    by_family = {card.family: card for card in cards}
    assert by_family["measures"].kinds == ["exact"]
    # Counts per category are exact, the medians between them are estimates.
    assert by_family["categories"].kinds == ["exact", "estimated"]
    assert all(card.facts for card in cards)


def test_the_insights_panel_is_rendered_from_the_json_alone(rich):
    source, path, _ = rich
    source.unlink()

    html = render_report(load_profile(path))

    assert 'id="insights"' in html and "13 / Insights" in html
    assert "Numbers by category" in html and "Shape of the numbers" in html
    assert "Values left out" in html and "Repeated values" in html
    assert "Parts of the dates" in html and "Values with a unit" in html
    assert re.search(r'class="acc acc-estimated"', html)
    assert "14 / Second pass" in html and "17 / Method" in html


def test_values_of_the_data_are_escaped_in_every_card(rich):
    _, _, profile = rich

    html = render_report(profile)

    assert "<script>alert" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<b>00001" not in html
    assert "R&lt;b&gt;00001&lt;/b&gt;" in html


def test_a_number_beyond_float64_keeps_all_its_digits(rich):
    _, _, profile = rich

    html = render_report(profile)

    assert f"{BIG:,}" in html
    assert str(BIG - 1) not in html and "e+15" not in html


def test_the_page_of_a_column_shows_its_cards_and_what_the_scan_derives(rich, tmp_path):
    _, _, profile = rich
    views = dataset_views(profile)
    pages = column_pages(profile, tmp_path / "rich.html", views)
    by_name = {column.name: (dataset, column) for _, dataset, column in pages}

    dataset, size = by_name["size"]
    page = render_column_report(profile, dataset, size, "rich.html")
    assert 'id="insights"' in page and "Quantities with a unit" in page
    assert f"{BIG:,}" in page
    # A pair concerns both of its columns.
    _, price = by_name["price"]
    assert any(card.family == "categories" for card in price.insights)
    _, kind = by_name["kind"]
    assert any(card.family == "categories" for card in kind.insights)
    # What the report derives from the Scan, without a second pass.
    _, signed = by_name["signed"]
    assert any(card.source == "scan" or card.family == "parts" for card in signed.insights)


def test_a_report_without_analyses_has_no_insights(rich):
    _, path, _ = rich
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["analyses"]
    older = write_json(path.parent, "older.json", document)

    profile = load_profile(older)
    html = render_report(profile)

    assert dataset_views(profile)[0].insights == []
    assert 'id="insights"' not in html and "Insights" not in html.split("Analysis settings")[0]


def test_the_values_of_a_hidden_column_are_never_listed(rich):
    _, _, profile = rich
    views = dataset_views(profile)
    fields = {column.name: column.id for column in views[0].columns}
    hidden = dict.fromkeys(fields.values(), "hide")

    cards = dataset_insights(profile.analyses, views[0].id, hidden)

    text = json.dumps([card.model_dump() for card in cards])
    assert "R<b>00001</b>" not in text and "<script>" not in text
    residual = next(card for card in cards if card.family == "residuals")
    assert "withheld by the exposure setting" in " ".join(residual.notes)


def test_ambiguous_dates_and_numbers_say_how_they_were_read(tmp_path):
    rows = [
        [
            n,
            ["1.234,5 Go", "1.250 Go", "12,5 Go", "7 Go"][n % 4],
            ["25/03/2020", "03/04/2020", "13/11/2021", "05/06/2022"][n % 4],
        ]
        for n in range(300)
    ]
    source = tmp_path / "read.csv"
    _write(source, ["id", "size", "when"], rows)
    profile = load_profile(_report(source))

    cards = {card.family: card for card in dataset_views(profile)[0].insights}
    html = render_report(profile)

    numbers = next(f for f in cards["measures"].facts if f.label == "Ambiguous numbers read")
    dates = next(f for f in cards["parts"].facts if f.label == "Ambiguous dates read")
    assert "decimal comma" in numbers.value and "150 unambiguous" in (numbers.note or "")
    assert "read as DMY" in dates.value and "150 unambiguous" in (dates.note or "")
    assert "ambiguous read as DMY" in html


def test_a_list_of_values_is_bounded_and_says_so(rich):
    _, _, profile = rich

    cards = dataset_views(profile)[0].insights

    for card in cards:
        for table in card.tables:
            assert len(table.rows) <= 25
        for bars in card.bars:
            assert len(bars.items) <= 36
            assert bars.items == [] or abs(sum(i.share for i in bars.items) - 1) < 1e-9


def test_a_family_with_many_cards_does_not_push_the_others_out(rich):
    from tabalyst.report_insights import shown_cards

    _, _, profile = rich
    cards = dataset_views(profile)[0].insights

    kept = shown_cards(cards, 1)

    families = [card.family for card in kept]
    assert len(families) == len(set(families)) == len({card.family for card in cards})
    assert len(kept) < len(cards)


def test_the_panel_says_when_it_shows_fewer_cards_than_it_holds(rich, monkeypatch):
    from tabalyst import reporting

    _, _, profile = rich
    monkeypatch.setitem(reporting.DISPLAY_LIMITS, "insights", 1)

    html = render_report(profile)

    assert "at most 1 of each family" in html
    assert html.count('class="ins"') == len({c.family for c in dataset_views(profile)[0].insights})
