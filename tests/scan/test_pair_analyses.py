# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pairs of numeric columns: the exploration of the row sample, the plan and the
second pass that counts every row (design 20.12, lot 8a)."""

import json
import random

import pytest
from pair_helpers import (
    chosen,
    correlated_rows,
    exact_pair,
    pair_entry,
    pair_plan,
    pairs_of,
    run_pairs,
)
from planner_helpers import scan_csv, with_field
from scan_helpers import write_json, write_text

from tabalyst.config import DeepSettings, PearsonSettings
from tabalyst.errors import ConfigurationError
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner import AnalysisRequest, default_registry, plan_analyses
from tabalyst.scanner.secondpass import analysis_key, run_second_pass


def settings(**pearson):
    return DeepSettings(pearson=PearsonSettings(**pearson))


# Exploration ---------------------------------------------------------------------


def test_correlated_pairs_are_listed_and_independent_ones_are_not(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(3000, noise=0.3))

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    assert [(c.display, c.exploration.scope) for c in pairs_of(plan)] == [
        ("a and b", "interior_rows")
    ]
    block = plan.relations.datasets[0]
    assert (block.numeric, block.columns, block.possible, block.evaluated, block.listed) == (
        3,
        3,
        3,
        3,
        1,
    )
    assert block.rows == 900 and block.work == 3 * 900


def test_the_exploration_ranks_by_the_lower_bound_so_few_rows_do_not_outrank_many(tmp_path):
    rng = random.Random(3)
    rows = []
    for n in range(3000):
        a = rng.gauss(0, 1)
        rows.append(f"{a:.4f},{0.9 * a + 0.4 * rng.gauss(0, 1):.4f},{a + 0.35 * rng.gauss(0, 1):.4f}")
    result = scan_csv(tmp_path, "a,b,c", rows)

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    scores = [c.exploration.score for c in pairs_of(plan)]
    assert scores == sorted(scores, reverse=True) and len(scores) == 3
    assert all(0 < s < c.exploration.coefficient for c in pairs_of(plan) for s in [c.exploration.score])


def test_an_identifier_a_constant_and_a_key_are_left_out_with_their_reasons(tmp_path):
    rng = random.Random(1)
    rows = []
    for n in range(3000):
        a = rng.gauss(0, 1)
        rows.append(f"{n},{n + 1000},7,{a:.3f},{2 * a + rng.gauss(0, 0.2):.3f}")
    result = scan_csv(tmp_path, "customer_id,seq,flag,a,b", rows)

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    block = plan.relations.datasets[0]
    assert block.excluded == {"constant": 1, "identifier_like": 2}
    assert block.columns == 2 and block.possible == 1
    assert [c.display for c in pairs_of(plan)] == ["a and b"]


def test_a_column_that_repeats_in_a_record_is_not_a_column_of_a_pair(tmp_path):
    rng = random.Random(2)
    records = []
    for n in range(300):
        a = rng.gauss(0, 1)
        records.append({"a": a, "b": 2 * a + rng.gauss(0, 0.1), "tags": [n, n + 1]})
    source = write_json(tmp_path, "records.json", records)
    result = scan(source, workers=1)

    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("pearson_correlation", field="a", partner="tags[]")],
        registry=default_registry().runnable(),
    )

    block = plan.relations.datasets[0]
    assert block.excluded.get("repeated_path") == 1
    explicit = [c for c in pairs_of(plan) if "tags[]" in c.display]
    assert [c.applicability.reasons for c in explicit] == [["repeated_path"]]
    assert explicit[0].selection.state == "rejected"


def test_the_columns_beyond_the_budget_are_counted_and_the_most_present_stay(tmp_path):
    rng = random.Random(5)
    rows = []
    for n in range(3000):
        a = rng.gauss(0, 1)
        sparse = "" if n % 2 else f"{a + rng.gauss(0, 0.1):.3f}"
        rows.append(f"{a:.3f},{a + rng.gauss(0, 0.1):.3f},{a + rng.gauss(0, 0.1):.3f},{sparse}")
    result = scan_csv(tmp_path, "a,b,c,sparse", rows)

    plan = plan_analyses(
        result, forced=True, registry=default_registry().runnable(), deep=settings(max_columns=3)
    )

    block = plan.relations.datasets[0]
    assert block.columns == 3 and block.excluded == {"column_budget": 1}
    assert all("sparse" not in c.display for c in pairs_of(plan))


def test_the_work_budget_bounds_the_pairs_times_the_rows_compared(tmp_path):
    result = scan_csv(tmp_path, "a,b,c,d", correlated_rows(3000, columns=4))

    plan = plan_analyses(
        result,
        forced=True,
        registry=default_registry().runnable(),
        deep=settings(max_work=900 * 3),
    )

    block = plan.relations.datasets[0]
    assert block.columns == 3 and block.work == 3 * 900 <= 2700
    assert block.excluded == {"column_budget": 1}


def test_a_dataset_without_a_usable_sample_is_not_explored_and_says_why(tmp_path):
    result = scan_csv(
        tmp_path, "a,b", correlated_rows(500, columns=2), records={"sample": {"rows": 0}}
    )

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    assert [b.unavailable for b in plan.relations.datasets] == ["no_sample"]
    assert pairs_of(plan) == []


def test_a_single_numeric_column_has_no_relations_block(tmp_path):
    result = scan_csv(tmp_path, "a,text", [f"{n},x{n}" for n in range(100)])

    plan = plan_analyses(result, registry=default_registry().runnable())

    assert plan.relations is None
    assert "relations" not in plan.model_dump(mode="json")


# Selection -----------------------------------------------------------------------


def test_a_correlated_pair_is_chosen_automatically_and_an_independent_one_is_not(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(3000, noise=0.3))

    plan = plan_analyses(result, registry=default_registry().runnable())

    chosen = [c for c in pairs_of(plan) if c.selection.state == "selected"]
    assert [(c.display, c.selection.reason, c.utility.score >= 45) for c in chosen] == [
        ("a and b", "automatic", True)
    ]


def test_the_planner_picks_by_itself_no_more_pairs_than_the_budget_allows(tmp_path):
    result = scan_csv(tmp_path, "a,b,c,d,e", correlated_rows(3000, columns=5, noise=0.2))

    automatic = plan_analyses(
        result, registry=default_registry().runnable(), deep=settings(automatic_pairs=2)
    )
    forced = plan_analyses(
        result,
        forced=True,
        registry=default_registry().runnable(),
        deep=settings(automatic_pairs=2),
    )

    states = [(c.selection.state, c.selection.reason) for c in pairs_of(automatic)]
    assert states.count(("selected", "automatic")) == 2
    assert {reason for state, reason in states if state == "rejected"} == {"pairs_budget"}
    assert len(pairs_of(forced)) == 10
    assert {c.selection.reason for c in pairs_of(forced)} == {"forced"}


def test_no_pair_is_listed_beyond_the_maximum_of_candidates(tmp_path):
    result = scan_csv(tmp_path, "a,b,c,d,e", correlated_rows(3000, columns=5, noise=0.2))

    plan = plan_analyses(
        result, forced=True, registry=default_registry().runnable(), deep=settings(max_candidates=4)
    )

    assert len(pairs_of(plan)) == 4
    assert plan.relations.datasets[0].listed == 4
    assert plan.relations.datasets[0].possible == 10


def test_automatic_pairs_zero_never_chooses_a_pair(tmp_path):
    result = scan_csv(tmp_path, "a,b", correlated_rows(3000, columns=2, noise=0.1))

    plan = plan_analyses(
        result, registry=default_registry().runnable(), deep=settings(automatic_pairs=0)
    )

    assert [c.selection.reason for c in pairs_of(plan)] == ["pairs_budget"]


def test_the_plan_is_the_same_whatever_the_workers_of_the_scan(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(3000, noise=0.3))
    other = scan(tmp_path / "data.csv", workers=2)

    first = plan_analyses(result, forced=True, registry=default_registry().runnable())
    second = plan_analyses(other, forced=True, registry=default_registry().runnable())

    assert first.plan_id == second.plan_id
    assert first.model_dump() == second.model_dump()


def test_a_pair_holds_no_value_of_the_data_and_its_figures_are_rounded(tmp_path):
    result = scan_csv(tmp_path, "a,b", correlated_rows(3000, columns=2, noise=0.1))

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    exploration = pairs_of(plan)[0].exploration
    for figure in (exploration.coefficient, exploration.lower, exploration.upper, exploration.score):
        assert round(figure, 6) == figure
    document = json.dumps(plan.model_dump(mode="json"))
    assert "relations" in document and "exploration" in document


# Requests ------------------------------------------------------------------------


def test_a_pair_the_exploration_did_not_list_can_be_asked_for(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(3000, noise=0.3))

    plan = pair_plan(result, "a", "c")

    asked = [c for c in pairs_of(plan) if c.display == "a and c"]
    assert len(asked) == 1 and asked[0].selection.state == "selected"
    assert asked[0].selection.requested and asked[0].selection.reason == "requested"
    assert asked[0].exploration.score == 0.0 and abs(asked[0].exploration.coefficient) < 0.2
    assert plan.objective.requested[0].partner == "c"
    assert plan.objective.requested[0].candidates == 1


def test_a_pair_is_named_in_the_order_of_the_dataset_whichever_way_it_is_asked(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(3000, noise=0.3))

    forward, backward = pair_plan(result, "a", "c"), pair_plan(result, "c", "a")

    assert [c.id for c in chosen(forward)] == [c.id for c in chosen(backward)]
    assert chosen(forward)[0].display == "a and c"


def test_a_field_alone_asks_for_the_listed_pairs_that_use_it(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(3000, noise=0.3))

    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("pearson_correlation", field="a")],
        automatic=False,
        registry=default_registry().runnable(),
    )

    assert plan.objective.requested[0].candidates == 1
    assert [(c.display, c.selection.reason) for c in chosen(plan)] == [("a and b", "requested")]


def test_a_pair_of_a_number_and_a_text_is_not_applicable(tmp_path):
    result = scan_csv(tmp_path, "a,b,name", [f"{n},{n * 2},x{n}" for n in range(200)])

    plan = pair_plan(result, "a", "name")

    [pair] = [c for c in pairs_of(plan) if c.display == "a and name"]
    assert pair.applicability.reasons == ["not_numeric"]
    assert pair.selection.state == "rejected" and pair.selection.requested


@pytest.mark.parametrize(
    ("field", "partner", "message"),
    [
        ("a", "a", "two different fields"),
        (None, "a", "needs the field"),
        ("a", "nope", "both"),
        ("nope", "a", "Unknown field"),
    ],
)
def test_a_wrong_request_for_a_pair_is_refused(tmp_path, field, partner, message):
    result = scan_csv(tmp_path, "a,b", correlated_rows(100, columns=2))

    with pytest.raises(ConfigurationError, match=message):
        plan_analyses(
            result,
            requests=[AnalysisRequest("pearson_correlation", field=field, partner=partner)],
            registry=default_registry().runnable(),
        )


# Cost ------------------------------------------------------------------------------


def test_a_pair_costs_its_columns_once_however_many_pairs_share_them(tmp_path):
    result = scan_csv(tmp_path, "a,b,c,d", correlated_rows(3000, columns=4, noise=0.2))

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    selected = chosen(plan)
    assert len(selected) == 6
    feeds = {s.key for c in selected for s in c.costs.states if s.key.startswith("pearson_feed:")}
    assert len(feeds) == 4
    listed = [s.key for c in selected for s in c.costs.states if s.key.startswith("pearson_feed:")]
    assert len(listed) == 12


# Second pass ---------------------------------------------------------------------


def test_the_coefficient_over_every_row_matches_an_exact_oracle(tmp_path):
    rows = correlated_rows(4000, noise=0.5, holes={"a": 0.1, "b": 0.2})
    result = scan_csv(tmp_path, "a,b,c", rows)

    outcome = run_pairs(result, tmp_path / "data.csv", [("a", "b"), ("a", "c"), ("b", "c")])

    for first, second in (("a", "b"), ("a", "c"), ("b", "c")):
        item = pair_entry(outcome, f"{first} and {second}")
        pairs, expected = exact_pair(rows, "abc".index(first), "abc".index(second))
        assert item.status == "complete" and item.result.source == "source"
        assert item.result.pairs == pairs
        assert item.result.coefficient == pytest.approx(expected, abs=1e-12)
        total = item.result.pairs + sum(item.result.excluded.model_dump().values())
        assert item.result.rows == total == 4000


def test_a_complete_sample_answers_without_reading_the_source(tmp_path):
    rows = correlated_rows(300, columns=2, noise=0.4, holes={"a": 0.2})
    result = scan_csv(tmp_path, "a,b", rows)
    plan = pair_plan(result, "a", "b")
    [candidate] = chosen(plan)
    assert candidate.execution.requires_source is False
    assert candidate.exploration.scope == "all_rows"

    # The file is gone: nothing may be read.
    outcome = run_second_pass(result, tmp_path / "gone.csv", plan)

    item = pair_entry(outcome, "a and b")
    pairs, expected = exact_pair(rows, 0, 1)
    assert not outcome.read_source and outcome.document.run.source_read is False
    assert item.status == "complete" and item.result.source == "samples"
    assert item.result.pairs == pairs
    assert item.result.coefficient == pytest.approx(expected, abs=1e-12)


def test_the_sample_and_the_source_give_the_same_figures(tmp_path):
    rows = correlated_rows(800, columns=2, noise=0.4, holes={"a": 0.1})
    result = scan_csv(tmp_path, "a,b", rows)
    answered = run_second_pass(result, tmp_path / "gone.csv", pair_plan(result, "a", "b"))
    # The same Scan with a sample that is no longer complete reads the source.
    reduced = result.model_copy(
        update={
            "datasets": [
                d.model_copy(
                    update={
                        "records": d.records.model_copy(
                            update={"sample": d.records.sample.model_copy(update={"complete": False})}
                        )
                    }
                )
                for d in result.datasets
            ]
        }
    )
    plan = pair_plan(reduced, "a", "b")
    assert chosen(plan)[0].execution.requires_source

    read = run_second_pass(reduced, tmp_path / "data.csv", plan)

    left, right = pair_entry(answered, "a and b").result, pair_entry(read, "a and b").result
    assert (left.source, right.source) == ("samples", "source")
    assert (left.rows, left.pairs, left.excluded) == (right.rows, right.pairs, right.excluded)
    assert left.coefficient == pytest.approx(right.coefficient, abs=1e-12)
    assert left.covariance == pytest.approx(right.covariance, rel=1e-9)


def test_a_json_source_is_always_read_even_with_a_complete_sample(tmp_path):
    rng = random.Random(4)
    records = []
    for n in range(200):
        a = rng.gauss(0, 1)
        records.append({"a": a, "b": 3 * a + rng.gauss(0, 0.2)})
    source = write_json(tmp_path, "records.json", records)
    result = scan(source, workers=1)

    plan = pair_plan(result, "a", "b")

    assert chosen(plan)[0].execution.requires_source is True
    outcome = run_second_pass(result, source, plan)
    item = pair_entry(outcome, "a and b")
    expected = exact_pair(
        [f"{r['a']!r},{r['b']!r}" for r in records], 0, 1
    )
    assert item.result.source == "source" and item.result.pairs == expected[0]
    assert item.result.coefficient == pytest.approx(expected[1], abs=1e-12)


def test_json_records_with_missing_keys_and_numeric_strings_are_aligned(tmp_path):
    rng = random.Random(6)
    records = []
    rows = []
    for n in range(10_000):
        a = round(rng.gauss(0, 1), 4)
        b = round(2 * a + rng.gauss(0, 0.3), 4)
        record = {"a": a}
        if n % 5:
            record["b"] = b if n % 3 else f"{b}"
        records.append(record)
        rows.append(f"{a},{b if 'b' in record else ''}")
    source = write_json(tmp_path, "records.json", records)
    result = scan(source, workers=1)
    plan = pair_plan(result, "a", "b")

    outcome = run_second_pass(result, source, plan)

    item = pair_entry(outcome, "a and b")
    pairs, expected = exact_pair(rows, 0, 1)
    assert item.status == "complete", (item.reason, item.detail)
    assert item.result.pairs == pairs and item.result.rows == 10_000
    assert item.result.coefficient == pytest.approx(expected, abs=1e-12)
    # More records than one buffer holds: the rows were handed over in pieces.
    assert item.result.rows > 4096


def test_the_columns_of_several_pairs_are_read_once_each(tmp_path):
    rows = correlated_rows(4000, columns=3, noise=0.3)
    result = scan_csv(tmp_path, "a,b,c", rows)
    plan = pair_plan(result, "a", "b", also=[("a", "c"), ("b", "c")])

    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    assert len([a for a in outcome.document.analyses if a.analyzer == "pearson_correlation"]) == 3
    assert outcome.document.run.cells_read == 3 * 4000
    assert outcome.document.run.records_read == 4000


def test_a_count_that_disagrees_with_the_scan_fails_the_pair_alone(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(4000, columns=3, noise=0.3))
    field = next(f for f in result.datasets[0].fields if f.display == "a")
    wrong = field.numeric.model_copy(
        update={"value": field.numeric.value.model_copy(update={"count": field.numeric.value.count + 1})}
    )
    edited = with_field(result, "a", numeric=wrong)

    outcome = run_second_pass(
        edited, tmp_path / "data.csv", pair_plan(edited, "a", "b", also=[("b", "c")])
    )

    assert pair_entry(outcome, "a and b").status == "failed"
    assert pair_entry(outcome, "a and b").reason == "scan_mismatch"
    assert pair_entry(outcome, "b and c").status == "complete"


def test_a_stored_pair_is_reused_and_the_minimum_of_pairs_is_part_of_its_key(tmp_path):
    result = scan_csv(tmp_path, "a,b", correlated_rows(4000, columns=2, noise=0.3))
    plan = pair_plan(result, "a", "b")
    first = run_second_pass(result, tmp_path / "data.csv", plan)

    again = run_second_pass(result, tmp_path / "data.csv", plan, previous=first.document)
    stricter = pair_plan(result, "a", "b", deep=settings(min_pairs=50))
    changed = run_second_pass(
        result, tmp_path / "data.csv", stricter, previous=first.document, settings=settings(min_pairs=50)
    )

    assert again.reused == (chosen(plan)[0].id,) and not again.read_source
    assert changed.executed == (chosen(stricter)[0].id,)
    assert analysis_key(plan.base, chosen(plan)[0]) != analysis_key(
        stricter.base, chosen(stricter)[0]
    )


def test_the_key_of_a_pair_depends_on_both_fields(tmp_path):
    result = scan_csv(tmp_path, "a,b,c", correlated_rows(3000, noise=0.3))
    plan = pair_plan(result, "a", "b", also=[("a", "c")])

    keys = {analysis_key(plan.base, c) for c in chosen(plan)}

    assert len(keys) == 2


def test_the_result_of_a_pair_is_the_same_whatever_the_workers_of_the_first_pass(tmp_path):
    write_text(
        tmp_path,
        "data.csv",
        "a,b\n" + "\n".join(correlated_rows(3000, columns=2, noise=0.3)) + "\n",
    )
    one = scan(tmp_path / "data.csv", workers=1, config=ScanConfig())
    two = scan(tmp_path / "data.csv", workers=2, config=ScanConfig())

    first = run_second_pass(one, tmp_path / "data.csv", pair_plan(one, "a", "b"))
    second = run_second_pass(two, tmp_path / "data.csv", pair_plan(two, "a", "b"))

    assert [a.model_dump() for a in first.document.analyses] == [
        a.model_dump() for a in second.document.analyses
    ]


def test_a_boolean_is_not_a_number_and_a_number_beyond_float64_is_still_counted():
    from tabalyst.scanner.secondpass.pearson import ColumnFeed
    from tabalyst.scanner.secondpass.replay import CellReader

    feed = ColumnFeed(CellReader(ScanConfig()))

    for native_type, value in (("boolean", True), ("integer", 5), ("number", "2.5")):
        feed.push_native(native_type, value)
        feed.end_record()
    feed.push_string("x" * 3)
    feed.end_record()
    feed.push_string("10" + "0" * 400)
    feed.end_record()

    assert feed.rows == [None, 5.0, 2.5, None, None]
    assert feed.numbers == 3


# Settings and the commands -------------------------------------------------------


def test_the_deep_settings_of_a_configuration_file_choose_the_pairs(tmp_path, monkeypatch):
    from tabalyst.deep_service import generate_deep

    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))
    source = write_text(
        tmp_path, "data.csv", "a,b,c,d\n" + "\n".join(correlated_rows(3000, columns=4, noise=0.2)) + "\n"
    )
    config = write_text(
        tmp_path,
        "deep.json",
        json.dumps({"deep": {"pearson": {"max_candidates": 2, "min_pairs": 20}}}),
    )

    done = generate_deep([source], config_path=config, confirmed=True).successes[0]

    pairs = [a for a in done.outcome.document.analyses if a.analyzer == "pearson_correlation"]
    assert len(pairs) == 2
    assert {a.parameters["min_pairs"] for a in pairs} == {20}
    assert done.outcome.document.settings.pearson.max_candidates == 2


def test_a_wrong_pearson_setting_is_refused(tmp_path, monkeypatch):
    from tabalyst.deep_service import generate_deep

    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))
    source = write_text(tmp_path, "data.csv", "a,b\n1,2\n3,4\n")
    config = write_text(
        tmp_path, "deep.json", json.dumps({"deep": {"pearson": {"max_columns": 1}}})
    )

    with pytest.raises(Exception, match="max_columns"):
        generate_deep([source], config_path=config)


def test_excel_pairs_are_read_from_the_records_of_the_workbook(tmp_path):
    from pathlib import Path

    workbook = Path(__file__).resolve().parents[2] / "examples" / "datasets" / "sales.xlsx"
    if not workbook.exists():
        pytest.skip("no workbook fixture")
    config = ScanConfig.model_validate({"excel": {"dataset_path": "$.Orders"}})
    scanned = scan(workbook, config=config, workers=1)
    numeric = [
        f.display
        for f in scanned.datasets[0].fields
        if f.technical_type.type in ("integer", "number") and f.numeric.status == "complete"
    ]
    if len(numeric) < 2:
        pytest.skip("the workbook has fewer than two numeric columns")

    plan = pair_plan(scanned, numeric[0], numeric[1])
    outcome = run_second_pass(scanned, workbook, plan)

    item = outcome.document.analyses[0]
    assert item.analyzer == "pearson_correlation"
    assert item.status == "complete", (item.reason, item.detail)


def test_the_report_summarizes_a_pair_with_its_coefficient_or_its_reason(tmp_path):
    from tabalyst.report_deep import result_summary

    rows = correlated_rows(500, columns=2, noise=0.3, holes={"a": 0.2})
    result = scan_csv(tmp_path, "a,b", rows + ["5,5"] * 0)
    outcome = run_second_pass(result, tmp_path / "gone.csv", pair_plan(result, "a", "b"))
    text, kind = result_summary(pair_entry(outcome, "a and b").result)
    assert text.startswith("r = +0.9") and "common rows" in text and "lack a number" in text
    assert kind == "exact"

    flat = scan_csv(tmp_path, "a,k", [f"{n},7" for n in range(60)])
    outcome = run_second_pass(flat, tmp_path / "gone.csv", pair_plan(flat, "a", "k"))
    text, _ = result_summary(pair_entry(outcome, "a and k").result)
    assert text.startswith("no coefficient: the second column does not vary")


def test_a_partner_is_refused_for_an_analysis_of_a_single_field(tmp_path):
    result = scan_csv(tmp_path, "a,b", correlated_rows(100, columns=2))

    with pytest.raises(ConfigurationError, match="does not analyze pairs"):
        plan_analyses(
            result,
            requests=[AnalysisRequest("numeric_histogram", field="a", partner="b")],
            registry=default_registry().runnable(),
        )


def test_a_source_that_changed_after_the_scan_is_refused_before_a_pair_is_counted(tmp_path):
    from tabalyst.source_guard import StaleSource

    rows = correlated_rows(400, columns=2, noise=0.4)
    result = scan_csv(tmp_path, "a,b", rows)
    reduced = result.model_copy(
        update={
            "datasets": [
                d.model_copy(
                    update={
                        "records": d.records.model_copy(
                            update={"sample": d.records.sample.model_copy(update={"complete": False})}
                        )
                    }
                )
                for d in result.datasets
            ]
        }
    )
    plan = pair_plan(reduced, "a", "b")
    source = tmp_path / "data.csv"
    source.write_text(source.read_text(encoding="utf-8") + "1.0,2.0\n", encoding="utf-8")

    with pytest.raises(StaleSource):
        run_second_pass(reduced, source, plan)


def test_a_masked_column_makes_the_pair_not_applicable(tmp_path):
    result = scan_csv(tmp_path, "a,b", correlated_rows(400, columns=2, noise=0.4))
    masked = with_field(result, "a", exposure="mask")

    plan = pair_plan(masked, "a", "b")

    [pair] = [c for c in pairs_of(plan) if c.selection.requested]
    assert pair.applicability.state == "not_applicable"
    assert pair.applicability.reasons == ["sensitive_exposure"]
