# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The cards of the drift along the file and of the columns missing together
(design 20.30 and 20.31, lot 19), rendered from the document alone (HTML-01)."""

import csv
import json
import random

import pytest
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
RECORDS = 1_000


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _source(tmp_path):
    """A region that changes along the file, two references that go missing in the
    same block of records and a note that goes missing anywhere."""
    rng = random.Random(7)
    path = tmp_path / "drift.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "region", "ref", "tag", "note", "<b>amount</b>"])
        for position in range(RECORDS):
            gap = 200 <= position < 330
            writer.writerow(
                [
                    position + 1,
                    "<i>QC</i>" if position < 300 else rng.choice(("QC", "ON", "BC")),
                    "" if gap else f"R{position:04d}",
                    "" if gap or position % 50 == 0 else f"T{position % 40}",
                    "" if rng.random() < 0.2 else rng.choice(("a", "b")),
                    "" if position % 9 == 0 else str(rng.randint(0, 500)),
                ]
            )
    return path


@pytest.fixture
def report(tmp_path):
    source = _source(tmp_path)
    result = runner.invoke(app, ["report", str(source), "--deep", "--yes"])
    assert result.exit_code == 0, result.output
    return source, source.with_suffix(".json"), load_profile(source.with_suffix(".json"))


def test_the_drift_and_the_columns_missing_together_have_cards(report):
    _, _, profile = report

    cards = dataset_views(profile)[0].insights

    families = [card.family for card in cards]
    assert "drift" in families and "missing" in families
    assert families == sorted(families, key=FAMILY_ORDER.index)
    drift = next(card for card in cards if card.family == "drift" and card.column == "ref")
    assert drift.kinds == ["exact"]
    assert drift.bars[0].caption.startswith("Records without a value")
    assert abs(sum(item.share for item in drift.bars[0].items) - 1) < 1e-9
    assert len(drift.bars[0].items) == 10


def test_the_values_followed_are_a_table_of_shares_by_slice(report):
    _, _, profile = report
    cards = dataset_views(profile)[0].insights

    region = next(card for card in cards if card.family == "drift" and card.column == "region")

    table = region.tables[0]
    assert table.headers[:2] == ["Value", "Count"] and table.headers[2:] == [
        str(n) for n in range(1, 11)
    ]
    assert table.code == [0]
    assert table.rows[-1][0] == "(first seen here)"
    assert {row[0] for row in table.rows[:-1]} == {"<i>QC</i>", "QC", "ON", "BC"}


def test_the_dataset_gets_one_card_of_pairs_and_each_column_its_own(report, tmp_path):
    _, _, profile = report
    views = dataset_views(profile)
    dataset = views[0]

    missing = [card for card in dataset.insights if card.family == "missing"]
    assert len(missing) == 1 and missing[0].scope == "dataset"
    pairs = missing[0].tables[0]
    assert {pairs.rows[0][0], pairs.rows[0][1]} == {"ref", "tag"}
    # The cards of the columns are on their pages and not in the dataset panel.
    pages = column_pages(profile, tmp_path / "drift.html", views)
    by_name = {column.name: column for _, _, column in pages}
    own = [card for card in by_name["ref"].insights if card.family == "missing"]
    assert [card.scope for card in own] == ["column"]
    assert own[0].tables[0].rows[0][0] == "tag"
    assert not [card for card in by_name["id"].insights if card.family == "missing"]


def test_the_pages_are_rendered_from_the_json_alone_and_escape_the_data(report, tmp_path):
    source, path, _ = report
    source.unlink()
    profile = load_profile(path)

    html = render_report(profile)

    assert "Drift along the file" in html and "Columns missing together" in html
    assert "<i>QC</i>" not in html and "&lt;i&gt;QC&lt;/i&gt;" in html
    views = dataset_views(profile)
    pages = column_pages(profile, tmp_path / "drift.html", views)
    dataset, column = next((d, c) for _, d, c in pages if c.name == "ref")
    page = render_column_report(profile, dataset, column, "drift.html")
    assert "Missing together" in page and "Also without a value where" in page
    assert "<b>amount</b>" not in html


def test_the_values_of_a_hidden_column_are_never_listed(report):
    _, _, profile = report
    views = dataset_views(profile)
    fields = {column.name: column.id for column in views[0].columns}
    hidden = dict.fromkeys(fields.values(), "mask")

    cards = dataset_insights(profile.analyses, views[0].id, hidden)

    text = json.dumps([card.model_dump() for card in cards])
    assert "<i>QC</i>" not in text and "ON" not in text.replace("ONE", "")
    drift = next(card for card in cards if card.family == "drift" and card.column == "region")
    assert not drift.tables
    assert "withheld by the exposure setting" in " ".join(drift.notes)
    # A masked column takes no part in the pairs either.
    assert not [card for card in cards if card.family == "missing"]


def test_a_report_without_the_analyses_has_neither_card(report):
    _, path, _ = report
    document = json.loads(path.read_text(encoding="utf-8"))
    del document["analyses"]
    older = path.parent / "older.json"
    older.write_text(json.dumps(document), encoding="utf-8")

    profile = load_profile(older)

    assert not [c for c in dataset_views(profile)[0].insights if c.family in ("drift", "missing")]
