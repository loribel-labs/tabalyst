# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests of the relations over every row: the Pearson correlation (plan
tests E01 and E02; design 20.12, REL-07 to REL-09) and the tables of a category
against a feature (E03 to E05; design 20.13, REL-11 to REL-16)."""

import json
import math

import pytest
from pair_helpers import correlated_rows, exact_pair, pair_entry, run_pairs
from planner_helpers import scan_csv
from table_helpers import (
    SHAPE_ORDER,
    branch_rows,
    coded_rows,
    exact_v,
    oracle_table,
    run_tables,
    table_entry,
    tables_of,
)

from tabalyst.config import CrosstabSettings, DeepSettings
from tabalyst.models import AnalysesBlock
from tabalyst.report_relations import relations_view
from tabalyst.scanner.planner import default_registry, plan_analyses
from tabalyst.scanner.secondpass import deep_document


@pytest.mark.scan_json_lot("8a")
def test_E01_pearson_with_different_nulls_per_column_matches_a_pairwise_oracle(tmp_path):
    # `a` and `b` are empty on different rows; the means of the Scan are those
    # of each column alone, never of the rows they share (REL-08).
    rows = correlated_rows(5000, columns=2, noise=0.8, holes={"a": 0.25, "b": 0.4})
    result = scan_csv(tmp_path, "a,b", rows)

    outcome = run_pairs(result, tmp_path / "data.csv", [("a", "b")])

    item = pair_entry(outcome, "a and b")
    pairs, expected = exact_pair(rows, 0, 1)
    assert item.status == "complete"
    assert item.result.rule == "pairwise_complete"
    assert item.result.pairs == pairs
    assert item.result.coefficient == pytest.approx(expected, abs=1e-12)
    excluded = item.result.excluded
    assert item.result.rows == 5000
    assert pairs + excluded.first_missing + excluded.second_missing + excluded.both_missing == 5000
    # The common rows have their own means.
    fields = {f.display: f for f in result.datasets[0].fields}
    assert item.result.mean_first != pytest.approx(fields["a"].numeric.value.mean, abs=1e-6)


@pytest.mark.scan_json_lot("8a")
def test_E02_a_constant_or_rare_pair_is_undefined_with_a_reason_and_never_zero(tmp_path):
    rows = []
    for n in range(2000):
        rare = f"{n * 0.5:.1f}" if n < 6 else ""
        rows.append(f"{n},{n * 2},7,{rare}")
    result = scan_csv(tmp_path, "a,b,flat,rare", rows)

    outcome = run_pairs(
        result,
        tmp_path / "data.csv",
        [("a", "b"), ("a", "flat"), ("flat", "b"), ("a", "rare")],
    )

    constant = pair_entry(outcome, "a and flat").result
    other = pair_entry(outcome, "b and flat").result
    rare = pair_entry(outcome, "a and rare").result
    assert pair_entry(outcome, "a and b").result.coefficient == pytest.approx(1.0, abs=1e-12)
    for item, reason in ((constant, "zero_variance_second"), (other, "zero_variance_second"), (rare, "insufficient_pairs")):
        assert item.defined is False and item.reason == reason
        assert item.coefficient is None
    assert rare.pairs == 6 and rare.min_pairs == 10
    written = json.loads(deep_document(outcome.document))
    for entry in written["analyses"]:
        if entry["analyzer"] == "pearson_correlation" and not entry["result"]["defined"]:
            assert "coefficient" not in entry["result"]


# Tables of a category against a feature of another column (lot 8b) ------------


def _labels(axis):
    return [item.label for item in axis.classes]


def _branch_number(label):
    return int(label.split("-")[1])


@pytest.mark.scan_json_lot("8b")
def test_E03_twelve_branches_by_five_patterns_match_an_exact_oracle(tmp_path):
    # A branch whose clients all take one shape, with an exception every 25 rows
    # and a missing client every 40: counts, margins, coverage, purity and the
    # exceptions are those of a count made by hand (REL-13, REL-15).
    rows, oracle = branch_rows(exception_every=25, blank_every=40)
    result = scan_csv(tmp_path, "branch,client", rows)

    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client")

    item = table_entry(outcome, "pattern")
    table = item.result
    assert item.status == "complete" and table.source == "source"
    branches, shapes = _labels(table.categories)[:-1], _labels(table.classes)[:-1]
    assert len(branches) == 12 and sorted(shapes) == sorted(SHAPE_ORDER)
    expected = oracle_table(oracle, branches, shapes)
    assert table.counts == expected
    assert table.row_totals == [sum(row) for row in expected]
    assert table.column_totals == [sum(row[j] for row in expected) for j in range(6)]
    assert table.counted == 1176 and table.rows == 1200
    assert table.excluded.feature_missing == 24 and table.excluded.unclassified == 0

    for number, branch in enumerate(branches):
        summary = table.by_category[number]
        dominant_shape = SHAPE_ORDER[(_branch_number(branch) - 1) % 5]
        assert shapes[summary.dominant] == dominant_shape
        assert (summary.rows, summary.classified, summary.feature_missing) == (100, 98, 2)
        assert summary.dominant_count == 94 and summary.exceptions == 4
        assert summary.coverage == pytest.approx(0.98)
        assert summary.purity == pytest.approx(94 / 98)
    forward = table.purity.forward
    assert (forward.dominant, forward.total) == (1128, 1176)
    assert forward.value == pytest.approx(1128 / 1176)
    # The reverse direction is another figure: the best branch of each shape.
    best = sum(max(expected[i][j] for i in range(13)) for j in range(6))
    assert table.purity.reverse.dominant == best

    exact = exact_v(expected)
    assert table.association.cramers_v == pytest.approx(math.sqrt(float(exact)), abs=1e-12)
    assert table.association.effective_categories == 12
    assert table.association.effective_classes == 5

    assert table.exceptions.count == 48 and table.exceptions.cells == 12
    for cell in table.exceptions.listed:
        branch, shape = branches[cell.category], shapes[cell.column]
        rows_of_cell = [
            (position + 1, client)
            for position, (b, client, s) in enumerate(oracle)
            if b == branch and s == shape
        ]
        assert cell.count == len(rows_of_cell) == 4
        assert [(e.record, e.value) for e in cell.examples] == rows_of_cell[:3]

    assert len(table.rules) == 12
    for rule in table.rules:
        assert (rule.status, rule.provenance) == ("candidate", "learned")
        assert (rule.support, rule.exceptions) == (98, 4)
        assert rule.confidence == pytest.approx(94 / 98)


@pytest.mark.scan_json_lot("8b")
def test_E04_unexpected_categories_and_patterns_go_to_explicit_classes(tmp_path):
    # Forty categories against five at most: the others are `other`, and a shape
    # that no pattern reads is `other` too; no axis appears while the source
    # streams (REL-12), and no row is lost.
    rows, oracle = branch_rows(branches=40, per_branch=30)
    rows.append("branch-41,??##")
    oracle.append(("branch-41", "??##", "??##"))
    result = scan_csv(tmp_path, "branch,client", rows)
    deep = DeepSettings(crosstab=CrosstabSettings(max_categories=5))

    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client", deep=deep)

    table = table_entry(outcome, "pattern").result
    branches, shapes = _labels(table.categories)[:-1], _labels(table.classes)[:-1]
    assert len(branches) == 5 and _labels(table.categories)[-1] == "other"
    assert _labels(table.classes)[-1] == "other"
    assert table.counts == oracle_table(oracle, branches, shapes)
    assert table.counted == len(rows) == sum(table.row_totals)
    assert table.row_totals[-1] == len(rows) - 5 * 30
    assert table.column_totals[-1] == 1
    # Every named row is bounded by the settings, whatever the data.
    assert len(table.counts) == 6 and all(len(row) == len(shapes) + 1 for row in table.counts)


@pytest.mark.scan_json_lot("8b")
def test_E04_an_axis_without_rows_stays_visible_and_leaves_the_score_alone(tmp_path):
    rows, oracle = branch_rows(branches=12, per_branch=40, exception_every=10)
    result = scan_csv(tmp_path, "branch,client", rows)

    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client")

    table = table_entry(outcome, "pattern").result
    # Twelve branches fit in the table: its `other` row and column are empty.
    assert table.row_totals[-1] == 0 and table.column_totals[-1] == 0
    assert len(table.counts) == 13
    branches, shapes = _labels(table.categories)[:-1], _labels(table.classes)[:-1]
    expected = oracle_table(oracle, branches, shapes)
    assert table.counts == expected
    assert table.association.effective_categories == 12
    assert table.association.effective_classes == 5
    assert table.association.cramers_v == pytest.approx(
        math.sqrt(float(exact_v(expected))), abs=1e-12
    )
    assert table.by_category[-1].classified == 0 and table.by_category[-1].purity is None


@pytest.mark.scan_json_lot("8b")
def test_E04_a_table_with_one_class_has_no_score_and_says_why(tmp_path):
    rows = [f"branch-{n % 6:02d},{n:06d}" for n in range(600)]
    result = scan_csv(tmp_path, "branch,client", rows)

    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client")

    item = table_entry(outcome, "pattern")
    association = item.result.association
    assert item.status == "complete"
    assert association.defined is False and association.reason == "single_class"
    assert association.corrected is None and association.cramers_v is None
    written = json.loads(deep_document(outcome.document))
    entry = next(a for a in written["analyses"] if a["analyzer"] == "category_crosstab")
    assert "cramers_v" not in entry["result"]["association"]
    assert item.result.purity.forward.value == 1.0


@pytest.mark.scan_json_lot("8b")
def test_E05_pattern_length_and_prefix_are_measured_but_reported_as_one_relation(tmp_path):
    rows, oracle = coded_rows()
    result = scan_csv(tmp_path, "branch,client", rows)

    # On its own, the planner keeps the best feature of the two columns.
    plan = plan_analyses(result, registry=default_registry().runnable())
    tables = tables_of(plan)
    assert {t.parameters["feature"] for t in tables} == {"pattern", "length", "prefix"}
    chosen = [t for t in tables if t.selection.state == "selected"]
    left_out = [t for t in tables if t.selection.state == "rejected"]
    assert len(chosen) == 1 and len(left_out) == 2
    assert {t.selection.reason for t in left_out} == {"redundant_feature"}

    # Asked for, the three are all measured and kept.
    outcome = run_tables(
        result, tmp_path / "data.csv", "branch", "client", features=("pattern", "length", "prefix")
    )
    kinds = {a.parameters["feature"]: a for a in outcome.document.analyses}
    assert set(kinds) == {"pattern", "length", "prefix"}
    for kind, item in kinds.items():
        assert item.status == "complete", kind
        assert item.result.counted == 720 and item.result.association.corrected > 0.9
    prefix = kinds["prefix"].result
    branches, codes = _labels(prefix.categories)[:-1], _labels(prefix.classes)[:-1]
    assert prefix.counts == oracle_table(oracle, branches, codes)
    assert prefix.feature.prefix_length == 2 and prefix.classes.domain == "original"
    assert kinds["length"].result.classes.domain == "analytical"
    assert kinds["pattern"].result.categories.domain == "analytical"

    # The report tells it once: one block for the two columns, the best first,
    # and every measure still in the analyses of the document (REL-16).
    view = relations_view(
        AnalysesBlock(mode="forced", outcome="ran", deep=outcome.document), "rows"
    )
    [group] = view.groups
    assert (group.category, group.column) == ("branch", "client")
    assert sorted(t.feature for t in group.tables) == ["length", "pattern", "prefix"]
    assert [t.leading for t in group.tables] == [True, False, False]
