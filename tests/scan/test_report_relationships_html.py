# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Relationships section of the report (lot 8b, HTML-06, REL-13 to REL-16): the
counts and percentages before the scores, the exceptions in view, one block for
the features of two columns. The renderer reads the document alone (HTML-01)."""

import json
import random

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_json, write_text
from table_helpers import branch_rows, coded_rows, run_tables
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.models import AnalysesBlock
from tabalyst.report_relations import relations_view, strength_word
from tabalyst.reporting import load_profile, render_report

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _report(tmp_path, rows, header="branch,client", *options):
    source = write_text(tmp_path, "branches.csv", header + "\n" + "\n".join(rows) + "\n")
    result = runner.invoke(app, ["report", str(source), "--deep", "--yes", *options])
    assert result.exit_code == 0, result.output
    return load_profile(tmp_path / "branches.json")


def _view(profile):
    return relations_view(profile.analyses, profile.datasets[0].id)


def test_the_section_shows_the_counts_and_the_conditional_percentages_before_the_scores(tmp_path):
    rows, _ = branch_rows(exception_every=25, blank_every=40)
    profile = _report(tmp_path, rows)

    html = render_report(profile)

    assert 'id="relationships"' in html and "11 / Relationships" in html
    assert html.index('id="relationships"') < html.index('id="second-pass"')
    section = html.split('id="relationships"')[1].split('id="second-pass"')[0]
    # The table of counts comes before the exceptions and the rules.
    assert (
        section.index("rel-grid")
        < section.index('<h4 class="subh2">Exceptions')
        < section.index('<h4 class="subh2">Candidate rules')
    )
    assert "95.9%" in section and "dominant class" in section
    assert "Cramér's V, bias-corrected" in section


def test_the_exceptions_are_visible_with_their_exact_counts_and_first_rows(tmp_path):
    rows, oracle = branch_rows(exception_every=25, blank_every=40)
    profile = _report(tmp_path, rows)

    view = _view(profile)

    [group] = view.groups
    table = next(t for t in group.tables if t.feature == "pattern")
    assert table.exception_count == 48 and table.exception_cells == 12
    first = table.exceptions[0]
    assert first.count == 4 and len(first.examples) == 3
    clients = {client for _, client, _ in oracle}
    assert all(value in clients for _, value in first.examples)
    html = render_report(profile)
    assert "48 rows" in html and "Records" in html


def test_a_rule_is_only_a_candidate_and_says_it_is_not_validated(tmp_path):
    rows, _ = branch_rows(exception_every=25)
    profile = _report(tmp_path, rows)

    html = render_report(profile)

    section = html.split('id="relationships"')[1].split('id="second-pass"')[0]
    assert section.count('<span class="pill">candidate</span>') >= 12
    assert "Learned from the data, not validated." in section
    assert "validated by nobody" in section


def test_the_features_of_two_columns_make_one_block_with_the_leading_one_first(tmp_path):
    rows, _ = coded_rows()
    profile = _report(tmp_path, rows)

    view = _view(profile)

    [group] = view.groups
    assert (group.category, group.column) == ("branch", "client")
    assert sorted(t.feature for t in group.tables) == ["length", "pattern", "prefix"]
    assert [t.leading for t in group.tables] == [True, False, False]
    scores = [t.score for t in group.tables]
    assert scores == sorted(scores, reverse=True)
    html = render_report(profile)
    section = html.split('id="relationships"')[1].split('id="second-pass"')[0]
    # The same two columns are one heading; the others are folded in.
    assert section.count('<h3 class="subh"><code>branch</code>') == 1
    assert section.count('<details class="rel rel-more">') == 2
    # Every measure stays in the document.
    analyses = json.loads(json.dumps(profile.analyses.model_dump(mode="json")))
    assert len([a for a in analyses["deep"]["analyses"] if a["analyzer"] == "category_crosstab"]) == 3


def test_a_score_on_low_counts_is_unstable_and_never_called_strong(tmp_path):
    rng = random.Random(4)
    rows = []
    for n in range(48):
        branch = n % 12
        client = ("AB12" if rng.random() < 0.8 and branch % 2 else "12-ab")[: 4] + str(n)
        rows.append(f"b{branch:02d},{client}")
    profile = _report(tmp_path, rows)

    view = _view(profile)

    tables = [t for g in view.groups for t in g.tables]
    unstable = [t for t in tables if t.strength == "unstable"]
    assert unstable, [(t.feature, t.score, t.strength) for t in tables]
    assert all("not reliable" in (t.note or "") for t in unstable)
    html = render_report(profile)
    assert "Unstable: low counts" in html


def test_a_table_without_a_score_says_why_and_shows_no_strength(tmp_path):
    result = scan_csv(tmp_path, "branch,client", [f"b{n % 5},{n:06d}" for n in range(300)])
    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client")
    block = AnalysesBlock(mode="forced", outcome="ran", deep=outcome.document)

    view = relations_view(block, "rows")

    [table] = [t for g in view.groups for t in g.tables]
    assert table.score is None and table.strength is None
    assert table.note == "No score: only one class has rows."
    assert table.purity == 1.0


def test_what_was_explored_but_not_listed_is_said_in_the_notes(tmp_path):
    rows = [f"b{n % 5},{n:06d}" for n in range(300)]
    profile = _report(tmp_path, rows)

    view = _view(profile)

    # Every table has a single class: none is listed, so there is no section.
    assert not view.available
    assert any("without" in note or "only one class" in note for note in view.notes)
    assert 'id="relationships"' not in render_report(profile)


def test_the_notes_of_a_section_tell_that_a_sample_may_miss_a_relation(tmp_path):
    rows, _ = branch_rows()
    profile = _report(tmp_path, rows)

    html = render_report(profile)

    section = html.split('id="relationships"')[1].split('id="second-pass"')[0]
    assert "explored on the sampled rows of the interior" in section
    assert "A relation not found in a sample may still exist in the file." in section


def test_correlations_are_listed_with_their_common_rows(tmp_path):
    rng = random.Random(8)
    rows = []
    for n in range(400):
        base = rng.gauss(50, 10)
        rows.append(f"{base:.2f},{base * 2 + rng.gauss(0, 2):.2f},{n % 3}")
    profile = _report(tmp_path, rows, header="price,cost,kind")

    view = _view(profile)

    pair = next(c for c in view.correlations if c.pair == "price and cost")
    assert pair.coefficient > 0.95 and pair.pairs == 400
    html = render_report(profile)
    assert "Correlations between numeric columns" in html and "price and cost" in html


def test_a_report_without_relations_has_no_section_and_no_tab(tmp_path):
    profile = _report(tmp_path, [f"u{n},w{n}" for n in range(60)])

    html = render_report(profile)

    assert not _view(profile).available
    assert 'id="relationships"' not in html and ">Relationships<" not in html
    # The sections that follow keep their numbers.
    assert "12 / Second pass" in html and "14 / Raw values" in html


def test_a_report_of_an_earlier_build_without_analyses_has_no_relationships(tmp_path):
    rows, _ = branch_rows()
    _report(tmp_path, rows)
    document = json.loads((tmp_path / "branches.json").read_text(encoding="utf-8"))
    del document["analyses"]
    older = write_json(tmp_path, "older.json", document)

    html = render_report(load_profile(older))

    assert 'id="relationships"' not in html


def test_a_value_of_the_data_is_escaped_in_the_tables(tmp_path):
    rows = []
    for n in range(240):
        branch = n % 4
        rows.append(f'"<script>alert({branch})</script>",{("AB12" if branch % 2 else "12-ab")}{n}')
    profile = _report(tmp_path, rows)

    html = render_report(profile)

    section = html.split('id="relationships"')[1].split('id="second-pass"')[0]
    assert "<script>alert" not in section and "&lt;script&gt;" in section


@pytest.mark.parametrize(
    ("score", "word"),
    [(0.02, "negligible"), (0.2, "weak"), (0.4, "moderate"), (0.5, "strong"), (1.0, "strong")],
)
def test_the_strength_word_of_a_score(score, word):
    assert strength_word(score) == word


def test_a_pair_listed_in_both_directions_prints_the_second_one_collapsed(tmp_path):
    rows = [f"{'M' if n % 2 else 'F'}{n % 3},{'H' if n % 2 else 'F'}{n % 3}" for n in range(600)]
    profile = _report(tmp_path, rows, header="civility,sex")

    view = _view(profile)

    pairs = [(g.category, g.column, g.mirror) for g in view.groups]
    assert len(pairs) == 2, pairs
    assert pairs[0][2] is False and pairs[1][2] is True
    assert (pairs[0][0], pairs[0][1]) == (pairs[1][1], pairs[1][0])
    html = render_report(profile)
    assert html.count("The same pair the other way round") == 1
