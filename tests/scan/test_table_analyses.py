# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tables of a category against a feature: the exploration of the row sample, the
plan and the second pass that counts every row (design 20.13, lot 8b)."""

import json
import random

import pytest
from planner_helpers import scan_csv, with_field
from scan_helpers import write_json, write_text
from table_helpers import (
    branch_rows,
    coded_rows,
    requested_tables,
    run_tables,
    table_entry,
    table_plan,
    tables_of,
)

from tabalyst.config import CrosstabSettings, DeepSettings
from tabalyst.errors import ConfigurationError
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner import AnalysisRequest, default_registry, plan_analyses
from tabalyst.scanner.planner.crosstabs import STRONG_SCORE
from tabalyst.scanner.planner.registry import AnalyzerRegistry
from tabalyst.scanner.secondpass import analysis_key, deep_document, run_second_pass
from tabalyst.source_guard import StaleSource


def settings(**crosstab):
    return DeepSettings(crosstab=CrosstabSettings(**crosstab))


def _plan(result, **kwargs):
    return plan_analyses(result, registry=default_registry().runnable(), **kwargs)


def _csv(tmp_path, rows=None, header="branch,client", **config):
    rows = rows if rows is not None else branch_rows(per_branch=100)[0]
    return scan_csv(tmp_path, header, rows, **config)


# Exploration ---------------------------------------------------------------------


def test_a_category_determining_a_pattern_is_listed_with_its_figures_and_a_block(tmp_path):
    result = _csv(tmp_path)

    plan = _plan(result, forced=True)

    table = next(
        c for c in tables_of(plan) if c.parameters["feature"] == "pattern"
    )
    assert table.id == "category_crosstab:rows:column_1>column_2:pattern"
    assert table.display == "branch and client (pattern)" and table.partner == "column_2"
    assert table.exploration.scope == "interior_rows" and table.exploration.rows == 900
    assert table.exploration.categories == 12 and table.exploration.classes == 5
    assert table.exploration.score > 0.9 and table.utility.reasons == ["exploratory_association"]
    block = plan.relations.tables[0]
    assert (block.categories, block.rows, block.scope) == (1, 900, "interior_rows")
    assert block.possible == block.evaluated == 3 and block.listed == 3
    assert block.work == 3 * 900 and block.cells > 0


def test_the_columns_that_cannot_be_categories_are_counted_with_their_reason(tmp_path):
    rows = [f"v{n % 8},u{n},same,m{n % 300}" for n in range(1500)]
    result = scan_csv(tmp_path, "kind,label,flat,many", rows)

    plan = _plan(result, forced=True)

    block = plan.relations.tables[0]
    assert block.categories == 1
    assert block.excluded_categories == {
        "near_unique": 1,
        "single_value": 1,
        "too_many_categories": 1,
    }


def test_an_exposed_or_repeated_column_is_not_a_category_or_a_feature(tmp_path):
    result = _csv(tmp_path)
    hidden = with_field(result, "client", exposure="hide")

    plan = _plan(hidden, forced=True)

    block = plan.relations.tables[0]
    assert block.excluded_features["sensitive_exposure"] == 1
    assert tables_of(plan) == []
    hidden_category = with_field(result, "branch", exposure="mask")
    assert _plan(hidden_category, forced=True).relations is None


def test_a_column_that_repeats_in_a_record_is_not_a_category(tmp_path):
    records = [
        {"kind": f"k{n % 4}", "tags": [f"t{n % 3}", f"t{n % 5}"], "name": f"n{n}"}
        for n in range(300)
    ]
    source = write_json(tmp_path, "records.json", records)
    result = scan(source, workers=1)

    plan = _plan(result, forced=True)

    block = plan.relations.tables[0]
    assert block.excluded_categories.get("repeated_path") == 1
    assert all(t.partner != "tags" for t in tables_of(plan))


def test_a_dataset_without_a_usable_sample_is_not_explored_and_says_why(tmp_path):
    result = _csv(tmp_path)
    bare = result.model_copy(
        update={
            "datasets": [
                d.model_copy(update={"records": d.records.model_copy(update={"sample": None})})
                for d in result.datasets
            ]
        }
    )

    plan = _plan(bare, forced=True)

    assert [b.unavailable for b in plan.relations.tables] == ["no_sample"]
    assert tables_of(plan) == []


def test_a_dataset_without_a_category_has_no_block(tmp_path):
    result = scan_csv(tmp_path, "a,b", [f"u{n},w{n}" for n in range(200)])

    plan = _plan(result, forced=True)

    assert plan.relations is None and "relations" not in plan.model_dump(mode="json")


def test_the_columns_beyond_the_budget_are_counted_and_the_most_present_stay(tmp_path):
    rows = [f"k{n % 5},k{n % 3},a{n % 7}x{n},b{n % 11}y{n},c{n}z" for n in range(600)]
    result = scan_csv(tmp_path, "k1,k2,t1,t2,t3", rows)

    plan = _plan(result, forced=True, deep=settings(max_columns=4))

    block = plan.relations.tables[0]
    assert block.categories + block.columns <= 4
    assert block.excluded_features.get("column_budget", 0) + block.excluded_categories.get(
        "column_budget", 0
    ) >= 1


def test_the_work_budget_bounds_the_tables_times_the_rows_coded(tmp_path):
    result = _csv(tmp_path)

    plan = _plan(result, forced=True, deep=settings(max_work=500))

    block = plan.relations.tables[0]
    assert block.work <= 500
    assert block.columns == 0 or block.excluded_features.get("column_budget")


def test_no_table_is_listed_beyond_the_maximum_of_candidates(tmp_path):
    result = _csv(tmp_path)

    plan = _plan(result, forced=True, deep=settings(max_candidates=1))

    assert len(tables_of(plan)) == 1 and plan.relations.tables[0].listed == 1


def test_a_strong_table_is_chosen_automatically_and_a_weak_one_is_not(tmp_path):
    rng = random.Random(5)
    strong, _ = branch_rows(branches=6, per_branch=100)
    weak = [f"b{n % 6},{''.join(rng.choice('ABCDEFGH') for _ in range(4))}" for n in range(600)]

    chosen_strong = [c for c in tables_of(_plan(_csv(tmp_path, strong))) if c.selection.state == "selected"]
    other = tmp_path / "weak"
    other.mkdir()
    weak_plan = _plan(_csv(other, weak))

    assert len(chosen_strong) == 1 and chosen_strong[0].selection.reason == "automatic"
    assert not [c for c in tables_of(weak_plan) if c.selection.state == "selected"]


def test_the_planner_picks_by_itself_no_more_tables_than_the_budget_allows(tmp_path):
    rows = []
    for n in range(1200):
        branch = n % 6
        rows.append(f"b{branch},{'AB'[branch % 2]}{branch}{n % 10},{'xy'[branch % 2]}{branch}-{n % 10}")
    result = scan_csv(tmp_path, "branch,one,two", rows)

    plan = _plan(result, deep=settings(automatic_tables=1))

    selected = [c for c in tables_of(plan) if c.selection.state == "selected"]
    capped = [c for c in tables_of(plan) if c.selection.reason == "tables_budget"]
    assert len(selected) == 1
    assert capped or all(c.selection.state == "rejected" for c in tables_of(plan) if c not in selected)


def test_automatic_tables_zero_never_chooses_a_table(tmp_path):
    plan = _plan(_csv(tmp_path), deep=settings(automatic_tables=0))

    assert not [c for c in tables_of(plan) if c.selection.state == "selected"]
    assert {c.selection.reason for c in tables_of(plan)} <= {"tables_budget", "redundant_feature", "low_utility"}


def test_the_plan_is_the_same_whatever_the_workers_of_the_scan(tmp_path):
    rows = branch_rows(per_branch=100)[0]
    one = scan_csv(tmp_path, "branch,client", rows)
    several = scan(tmp_path / "data.csv", workers=2)

    assert _plan(one, forced=True).plan_id == _plan(several, forced=True).plan_id


def test_a_table_holds_no_value_of_the_data_and_its_figures_are_rounded(tmp_path):
    rows, oracle = branch_rows(per_branch=100)
    result = _csv(tmp_path, rows)

    plan = _plan(result, forced=True)

    text = json.dumps(plan.model_dump(mode="json"))
    assert "branch-01" not in text and oracle[0][1] not in text
    for table in tables_of(plan):
        for value in (table.exploration.score, table.exploration.cramers_v, table.exploration.purity):
            assert value is None or value == round(value, 6)


# Requests ------------------------------------------------------------------------


def test_a_table_the_exploration_did_not_list_can_be_asked_for(tmp_path):
    result = _csv(tmp_path)
    # With no candidate listed, only a request produces the table.
    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("category_crosstab", field="branch", partner="client", feature="prefix")],
        automatic=False,
        registry=default_registry().runnable(),
        deep=settings(max_candidates=0),
    )

    [table] = requested_tables(plan)
    assert table.parameters["feature"] == "prefix" and table.selection.reason == "requested"
    assert table.exploration is not None and table.exploration.scope == "interior_rows"


def test_a_request_without_feature_asks_for_every_feature(tmp_path):
    plan = plan_analyses(
        _csv(tmp_path),
        requests=[AnalysisRequest("category_crosstab", field="branch", partner="client")],
        automatic=False,
        registry=default_registry().runnable(),
    )

    selected = [c for c in requested_tables(plan) if c.selection.state == "selected"]
    assert sorted(c.parameters["feature"] for c in selected) == [
        "length",
        "pattern",
        "prefix",
    ]
    # The clients are almost all different: they offer no value for a category.
    [value] = [c for c in requested_tables(plan) if c.selection not in [s.selection for s in selected]]
    assert value.applicability.state == "not_applicable"
    assert plan.objective.requested[0].candidates == 4


def test_a_table_is_directed_from_the_category_to_the_column(tmp_path):
    plan = plan_analyses(
        _csv(tmp_path),
        requests=[AnalysisRequest("category_crosstab", field="client", partner="branch", feature="pattern")],
        automatic=False,
        registry=default_registry().runnable(),
    )

    # The client is almost unique: it is not a category, but it was asked for.
    [table] = requested_tables(plan)
    assert table.field == "column_2" and table.partner == "column_1"
    assert table.applicability.state == "not_applicable"
    assert table.applicability.reasons == ["too_many_categories"]


def test_a_column_is_not_its_own_feature(tmp_path):
    with pytest.raises(ConfigurationError, match="two different fields"):
        plan_analyses(
            _csv(tmp_path),
            requests=[
                AnalysisRequest("category_crosstab", field="branch", partner="branch", feature="pattern")
            ],
            automatic=False,
            registry=default_registry().runnable(),
        )


@pytest.mark.parametrize(
    ("analyzer", "feature", "message"),
    [
        ("category_crosstab", "shape", "Unknown feature"),
        ("pearson_correlation", "pattern", "does not take a feature"),
        ("numeric_histogram", "pattern", "does not take a feature"),
    ],
)
def test_a_wrong_request_for_a_feature_is_refused(tmp_path, analyzer, feature, message):
    with pytest.raises(ConfigurationError, match=message):
        _plan(
            _csv(tmp_path),
            requests=[AnalysisRequest(analyzer, field="branch", partner="client", feature=feature)],
        )


def test_a_table_costs_its_columns_once_however_many_tables_share_them(tmp_path):
    result = _csv(tmp_path)
    one = table_plan(result, "branch", "client", features=("pattern",))
    three = table_plan(result, "branch", "client", features=("pattern", "length", "prefix"))

    category_feed = "code_feed:datasets/rows/fields/column_1:category"
    keys = [s.key for c in tables_of(three) for s in c.costs.states]
    assert keys.count(category_feed) == 3
    # Memory is charged once for a state with the same key.
    assert three.summary.memory.max < 3 * one.summary.memory.max


# The second pass -----------------------------------------------------------------


def test_the_sample_and_the_source_give_the_same_table(tmp_path):
    rows, _ = branch_rows(per_branch=60, exception_every=15, blank_every=30)
    result = _csv(tmp_path, rows)
    plan = table_plan(result, "branch", "client", features=("pattern", "length", "prefix"))
    assert all(not c.execution.requires_source for c in tables_of(plan))

    # The file is gone: nothing may be read.
    answered = run_second_pass(result, tmp_path / "gone.csv", plan)
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
    read = run_second_pass(
        reduced,
        tmp_path / "data.csv",
        table_plan(reduced, "branch", "client", features=("pattern", "length", "prefix")),
    )

    assert not answered.read_source and read.read_source
    for feature in ("pattern", "length", "prefix"):
        left, right = table_entry(answered, feature).result, table_entry(read, feature).result
        assert (left.source, right.source) == ("samples", "source")
        left_dump, right_dump = left.model_dump(), right.model_dump()
        left_dump.pop("source"), right_dump.pop("source")
        assert left_dump == right_dump


def test_a_json_source_is_read_with_its_native_types(tmp_path):
    rng = random.Random(2)
    records = []
    for n in range(6000):
        branch = n % 4
        client = f"{'AB'[branch % 2]}{branch}-{rng.randint(1000, 9999)}"
        record = {"branch": branch if n % 2 else f"b{branch}", "client": client}
        if n % 7 == 0:
            record["client"] = n  # not a string
        if n % 11 == 0:
            del record["client"]
        records.append(record)
    source = write_json(tmp_path, "records.json", records)
    result = scan(source, workers=1)

    plan = table_plan(result, "branch", "client", features=("pattern",))
    [candidate] = requested_tables(plan)
    assert candidate.execution.requires_source is True
    outcome = run_second_pass(result, source, plan)

    item = table_entry(outcome, "pattern")
    assert item.status == "complete", (item.reason, item.detail)
    table = item.result
    # An odd branch is an integer, an even one a string: four categories whose
    # classes keep the native type of the integers.
    classes = table.categories.classes
    assert [c.label for c in classes] == ["1", "3", "b0", "b2", "other"]
    assert [c.type for c in classes] == ["integer", "integer", None, None, None]
    assert table.rows == 6000
    non_strings = sum(1 for n in range(6000) if n % 7 == 0 and n % 11)
    absent = sum(1 for n in range(6000) if n % 11 == 0)
    assert table.excluded.unclassified == non_strings
    assert table.excluded.feature_missing == absent
    assert table.counted + non_strings + absent == 6000
    # More records than one buffer holds: the rows were handed over in pieces.
    assert table.rows > 4096


def test_the_columns_of_several_tables_are_read_once_each(tmp_path):
    rows = branch_rows(per_branch=100)[0]
    result = _csv(tmp_path, rows)
    plan = table_plan(result, "branch", "client", features=("pattern", "length"))

    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    # The category is converted once for the two tables: three feeds, not four.
    assert outcome.document.run.cells_read == 3 * 1200
    assert outcome.document.run.records_read == 1200


def test_a_count_that_disagrees_with_the_scan_fails_the_table_alone(tmp_path):
    result = _csv(tmp_path)
    field = next(f for f in result.datasets[0].fields if f.display == "branch")
    wrong = field.values.model_copy(update={"count": field.values.count + 1})
    edited = with_field(result, "branch", values=wrong)
    plan = table_plan(edited, "branch", "client", features=("pattern",))
    pearson_free = plan.model_copy()

    outcome = run_second_pass(edited, tmp_path / "data.csv", pearson_free)

    item = table_entry(outcome, "pattern")
    assert item.status == "failed" and item.reason == "scan_mismatch"
    assert item.result is None


def test_a_stored_table_is_reused_and_what_the_result_depends_on_is_in_its_key(tmp_path):
    result = _csv(tmp_path)
    plan = table_plan(result, "branch", "client", features=("pattern",))
    first = run_second_pass(result, tmp_path / "data.csv", plan)

    again = run_second_pass(result, tmp_path / "gone.csv", plan, previous=first.document)

    assert again.reused == first.executed and not again.read_source

    base = tables_of(plan)[0]
    keys = {}
    for name, deep in {
        "same": settings(),
        "examples": settings(examples=1),
        "rule": settings(rule_support=10),
        "categories": settings(max_categories=5),
        "budget": settings(max_candidates=3, max_work=10_000, automatic_tables=2),
    }.items():
        other = tables_of(table_plan(result, "branch", "client", features=("pattern",), deep=deep))[0]
        keys[name] = analysis_key(plan.base, other)
    assert keys["same"] == analysis_key(plan.base, base) == keys["budget"]
    assert len({keys["same"], keys["examples"], keys["rule"], keys["categories"]}) == 4


def test_each_feature_has_its_own_key(tmp_path):
    result = _csv(tmp_path)
    plan = table_plan(result, "branch", "client", features=("pattern", "length", "prefix"))

    keys = [analysis_key(plan.base, c) for c in tables_of(plan)]

    assert len(set(keys)) == 3


def test_the_result_is_the_same_whatever_the_workers_of_the_first_pass(tmp_path):
    rows = branch_rows(per_branch=100, exception_every=20)[0]
    rows = ["branch,client", *rows]
    write_text(tmp_path, "data.csv", "\n".join(rows) + "\n")
    one = scan(tmp_path / "data.csv", workers=1, config=ScanConfig())
    several = scan(tmp_path / "data.csv", workers=2, config=ScanConfig())

    left = run_tables(one, tmp_path / "data.csv", "branch", "client").document.analyses[0]
    right = run_tables(several, tmp_path / "data.csv", "branch", "client").document.analyses[0]

    assert left.result == right.result


def test_the_document_is_valid_json_without_unknown_members(tmp_path):
    result = _csv(tmp_path)
    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client")

    written = json.loads(deep_document(outcome.document))

    entry = written["analyses"][0]
    assert entry["domain"] == "mixed" and entry["partner"] == "column_2"
    assert entry["parameters"]["feature"] == "pattern"
    assert entry["result"]["kind"] == "crosstab" and entry["result"]["precision"] == "float64"
    assert entry["result"]["categories"]["domain"] == "analytical"
    assert entry["result"]["classes"]["domain"] == "original"


def test_the_report_summarizes_a_table_with_its_score_or_its_reason(tmp_path):
    from tabalyst.report_deep import result_summary

    result = _csv(tmp_path)
    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client")
    text, kind = result_summary(table_entry(outcome, "pattern").result)
    assert text.startswith("1,200 of 1,200 rows by pattern; Cramér's V 1.00") and kind == "exact"
    assert "12 candidate rules" in text

    (tmp_path / "flat").mkdir()
    flat = scan_csv(tmp_path / "flat", "branch,client", [f"b{n % 4},{n:06d}" for n in range(200)])
    outcome = run_tables(flat, tmp_path / "flat" / "data.csv", "branch", "client")
    text, _ = result_summary(table_entry(outcome, "pattern").result)
    assert text == "200 of 200 rows by pattern; no score: only one class has rows"


def test_the_deep_settings_of_a_configuration_file_choose_the_tables(tmp_path, monkeypatch):
    from tabalyst.config import load_config

    path = write_text(
        tmp_path,
        "deep.json",
        json.dumps({"deep": {"crosstab": {"max_categories": 7, "prefix_length": 3}}}),
    )

    loaded = load_config([path])

    assert loaded.deep.crosstab.max_categories == 7 and loaded.deep.crosstab.prefix_length == 3


def test_a_wrong_crosstab_setting_is_refused():
    with pytest.raises(ValueError):
        CrosstabSettings(max_categories=1)
    with pytest.raises(ValueError):
        CrosstabSettings(rule_purity=30)
    with pytest.raises(ValueError):
        CrosstabSettings(unknown=1)


def test_the_best_of_three_features_is_the_only_automatic_one_of_a_pair_of_columns(tmp_path):
    rows, _ = coded_rows()
    result = scan_csv(tmp_path, "branch,client", rows)

    plan = _plan(result)

    tables = tables_of(plan)
    scores = {t.parameters["feature"]: t.exploration.score for t in tables}
    selected = [t for t in tables if t.selection.state == "selected"]
    assert len(selected) == 1
    assert scores[selected[0].parameters["feature"]] == max(scores.values())
    assert plan.relations.tables[0].listed == 3


def test_a_source_that_changed_after_the_scan_is_refused_before_a_table_is_counted(tmp_path):
    result = _csv(tmp_path)
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
    plan = table_plan(reduced, "branch", "client", features=("prefix",))
    source = tmp_path / "data.csv"
    source.write_text(source.read_text(encoding="utf-8") + "branch-01,ZZ9999\n", encoding="utf-8")

    with pytest.raises(StaleSource):
        run_second_pass(reduced, source, plan)


def test_a_masked_category_or_column_makes_the_table_not_applicable(tmp_path):
    result = _csv(tmp_path)
    request = [AnalysisRequest("category_crosstab", field="branch", partner="client", feature="pattern")]
    for display in ("branch", "client"):
        masked = with_field(result, display, exposure="mask")

        plan = plan_analyses(
            masked, requests=request, automatic=False, registry=default_registry().runnable()
        )

        [table] = requested_tables(plan)
        assert table.applicability.state == "not_applicable"
        assert table.applicability.reasons == ["sensitive_exposure"]


def test_a_table_document_validates_against_its_schema_and_reads_back(tmp_path):
    import jsonschema

    from tabalyst.scanner.secondpass import load_deep
    from tabalyst.scanner.secondpass.schema import deep_schema

    rows, _ = branch_rows(exception_every=25, blank_every=40)
    result = _csv(tmp_path, rows)
    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client", features=("pattern", "prefix"))
    text = deep_document(outcome.document)

    jsonschema.Draft202012Validator(deep_schema()).validate(json.loads(text))

    path = write_text(tmp_path, "deep.json", text)
    loaded = load_deep(path)
    assert loaded is not None
    assert loaded.model_dump() == outcome.document.model_dump()
    explorations = [c.exploration for c in loaded.plan.candidates if c.analyzer == "category_crosstab"]
    assert explorations and all(type(e).__name__ == "TableExploration" for e in explorations if e)


def test_a_table_of_patterns_is_not_displaced_by_a_weaker_table_of_lengths(tmp_path):
    # The pattern of the client is a perfect function of the branch; the length of
    # the code is one with noise. Patterns cost a little more per cell than lengths,
    # but the planner ranks the tables by what the sample says of them.
    rng = random.Random(3)
    shapes = ["XX9999", "999-999", "xx99ab", "XX-999", "99-XXX", "x9x9x9"]
    rows = []
    for n in range(1200):
        branch = n % 6
        client = "".join(
            rng.choice({"X": "ABCDEFGH", "x": "abcdefgh", "9": "0123456789"}.get(c, c))
            if c in "Xx9"
            else c
            for c in shapes[branch]
        )
        length = 2 + branch if rng.random() > 0.2 else 2 + rng.randrange(6)
        code = "k" * length
        rows.append(f"b{branch},{client},{code}")
    result = scan_csv(tmp_path, "branch,client,code", rows)

    plan = _plan(result, deep=settings(automatic_tables=1))

    chosen = [c for c in tables_of(plan) if c.selection.state == "selected"]
    assert [(c.display, c.parameters["feature"]) for c in chosen] == [
        ("branch and client (pattern)", "pattern")
    ]
    length = next(
        c for c in tables_of(plan) if c.display == "branch and code (length)"
    )
    assert length.exploration.score < chosen[0].exploration.score
    assert length.selection.reason == "tables_budget"


def test_a_feature_waits_for_the_best_one_of_its_columns_and_is_chosen_when_it_is_not(tmp_path):
    from tabalyst.scanner.planner import default_budgets

    rows, _ = coded_rows()
    result = scan_csv(tmp_path, "branch,client", rows)
    # The best feature (the prefix) needs more memory than the automatic budget
    # leaves (a complete sample reads no source, so no parser is reserved); the
    # pattern, with its six patterns of fixed length, fits.
    budgets = default_budgets().model_copy(update={"automatic_memory_bytes": 135_000})

    # The tables are the subject: the validation of the patterns, which would take its
    # share of the budget, is left out of the registry.
    registry = AnalyzerRegistry(
        analyzer for analyzer in default_registry().runnable() if analyzer.id != "pattern_validation"
    )

    plan = plan_analyses(result, budgets=budgets, registry=registry)

    by_feature = {c.parameters["feature"]: c for c in tables_of(plan)}
    assert by_feature["prefix"].selection.reason == "budget"
    assert by_feature["pattern"].selection.state == "selected"
    assert by_feature["length"].selection.state == "rejected"
    selected = [c for c in tables_of(plan) if c.selection.state == "selected"]
    assert len(selected) == 1


def test_a_category_beyond_the_hundred_frequencies_the_scan_lists_still_makes_a_table(tmp_path):
    rows, _ = branch_rows(branches=150, per_branch=12)
    result = scan_csv(tmp_path, "branch,client", rows)

    # With the default of 100 distinct values, no column is a category.
    assert _plan(result, forced=True).relations is None

    deep = settings(max_distinct=200)
    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client", deep=deep)

    table = table_entry(outcome, "pattern").result
    labels = [c.label for c in table.categories.classes]
    assert len(labels) == 31 and labels[-1] == "other"
    # The 30 most frequent categories are rows (all have 12 rows: the first in
    # order); the other 120 are `other`, and no row is lost.
    assert table.row_totals[:-1] == [12] * 30 and table.row_totals[-1] == 120 * 12
    assert table.counted == 1800


def test_a_request_naming_a_column_that_repeats_in_a_record_is_not_applicable(tmp_path):
    records = [
        {"kind": f"k{n % 4}", "tags": [f"t{n % 3}", f"t{n % 5}"], "name": f"n{n}"}
        for n in range(300)
    ]
    source = write_json(tmp_path, "records.json", records)
    result = scan(source, workers=1)

    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("category_crosstab", field="kind", partner="tags[]", feature="length")],
        automatic=False,
        registry=default_registry().runnable(),
    )

    [table] = requested_tables(plan)
    assert table.applicability.state == "not_applicable"
    assert table.applicability.reasons == ["repeated_path"]


def test_an_excel_workbook_gives_tables_from_its_records(tmp_path):
    from pathlib import Path

    workbook = Path(__file__).resolve().parents[2] / "examples" / "datasets" / "sales.xlsx"
    if not workbook.exists():
        pytest.skip("no workbook fixture")
    config = ScanConfig.model_validate({"excel": {"dataset_path": "$.Orders"}})
    scanned = scan(workbook, config=config, workers=1)

    plan = plan_analyses(scanned, forced=True, registry=default_registry().runnable())
    tables = [c for c in tables_of(plan) if c.execution.available]
    if not tables:
        pytest.skip("the workbook offers no table")
    outcome = run_second_pass(scanned, workbook, plan)

    for item in outcome.document.analyses:
        if item.analyzer == "category_crosstab":
            assert item.status == "complete", (item.display, item.reason, item.detail)
            assert item.result.source == "source"
            assert item.result.rows == item.result.counted + sum(item.result.excluded.model_dump().values())


def _unstable_strong_and_stable_weak_rows():
    """`prov` and `pname` depend on each other, but twelve of their values have a few
    rows each (unstable, strong); `big` and `kind` are weakly related with large counts."""
    rng = random.Random(3)
    names = {"QC": "Quebec", "ON": "Ontario", **{f"P{i}": f"Zone{i}x" for i in range(12)}}
    rows = []
    for n in range(900):
        draw = rng.random()
        code = "QC" if draw < 0.5 else "ON" if draw < 0.97 else f"P{rng.randrange(12)}"
        big = n % 3
        kind = f"{'AB'[(big + (1 if rng.random() < 0.35 else 0)) % 2]}{rng.randrange(10)}"
        rows.append(f"g{big},{kind},{code},{names[code]}")
    return rows


def _scored(tmp_path):
    result = scan_csv(tmp_path, "big,kind,prov,pname", _unstable_strong_and_stable_weak_rows())
    plan = _plan(result, forced=True)
    return [c for c in tables_of(plan) if c.exploration is not None and c.exploration.score is not None]


def test_a_strong_table_on_low_counts_ranks_before_a_weak_stable_one(tmp_path):
    scored = _scored(tmp_path)

    strong_unstable = [
        i for i, c in enumerate(scored)
        if c.exploration.stable is False and c.exploration.score >= STRONG_SCORE
    ]
    weak_stable = [
        i for i, c in enumerate(scored) if c.exploration.stable and c.exploration.score < STRONG_SCORE
    ]
    assert strong_unstable and weak_stable
    assert max(strong_unstable) < min(weak_stable)
