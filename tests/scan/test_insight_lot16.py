# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 16: richer relations (G62 onward).

The line and the rank correlation of a pair of numeric columns (design 20.22),
the tables of a category against the values of another column, and the
statistics of a number by category. The oracles are exact fractions computed
from what the generator wrote, never from the code under test.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from fractions import Fraction

import jsonschema
import pytest
from pair_helpers import (
    chosen,
    correlated_rows,
    pair_entry,
    pair_plan,
    pairs_of,
    run_pairs,
)
from planner_helpers import scan_csv
from table_helpers import run_tables, table_entry, tables_of

from tabalyst.config import DeepSettings, PearsonSettings
from tabalyst.errors import ConfigurationError
from tabalyst.report_deep import result_summary
from tabalyst.scanner.planner import AnalysisRequest, default_registry, plan_analyses
from tabalyst.scanner.rankcorr import average_ranks, binned_spearman, sample_coefficient
from tabalyst.scanner.secondpass import analysis_key, deep_document, run_second_pass
from tabalyst.scanner.secondpass.schema import deep_schema


def pearson_settings(**changes) -> DeepSettings:
    return DeepSettings(pearson=PearsonSettings(**changes))


def exact_ranks(values: list[Fraction]) -> list[Fraction]:
    """Average ranks from 1, in exact fractions."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [Fraction(0)] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for position in range(start, end + 1):
            ranks[order[position]] = Fraction(start + end, 2) + 1
        start = end + 1
    return ranks


def exact_spearman(xs: list[Fraction], ys: list[Fraction]) -> float:
    """Pearson of the average ranks, from exact sums."""
    rx, ry = exact_ranks(xs), exact_ranks(ys)
    n = len(rx)
    mx, my = sum(rx) / n, sum(ry) / n
    cross = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = sum((a - mx) ** 2 for a in rx)
    vy = sum((b - my) ** 2 for b in ry)
    return float(cross) / math.sqrt(float(vx) * float(vy))


def read(rows: list[str], column: int) -> list[Fraction]:
    return [Fraction(row.split(",")[column]) for row in rows]


# The line ---------------------------------------------------------------------------


def test_G62_the_line_of_a_pair_is_the_least_squares_line_of_the_common_rows(tmp_path):
    rows = correlated_rows(2000, columns=2, noise=0.5, holes={"b": 0.1})
    result = scan_csv(tmp_path, "a,b", rows)

    outcome = run_pairs(result, tmp_path / "data.csv", [("a", "b")])

    found = pair_entry(outcome, "a and b").result
    pairs = [
        (Fraction(r.split(",")[0]), Fraction(r.split(",")[1]))
        for r in rows
        if r.split(",")[1] != ""
    ]
    n = len(pairs)
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    slope = sum((x - mx) * (y - my) for x, y in pairs) / sum((x - mx) ** 2 for x, _ in pairs)
    assert found.slope == float(slope) or math.isclose(found.slope, float(slope), rel_tol=1e-9)
    assert math.isclose(found.intercept, float(my - slope * mx), rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(found.r_squared, found.coefficient**2, rel_tol=1e-12)


def test_G63_a_pair_without_coefficient_has_no_line(tmp_path):
    rows = [f"{n % 7},5.0" for n in range(500)]
    result = scan_csv(tmp_path, "a,b", rows)

    outcome = run_pairs(result, tmp_path / "data.csv", [("a", "b")])

    found = pair_entry(outcome, "a and b").result
    assert found.reason == "zero_variance_second"
    dumped = json.loads(found.model_dump_json())
    assert not {"slope", "intercept", "r_squared"} & dumped.keys()


# The rank correlation ----------------------------------------------------------------


def test_G64_the_bounds_of_the_binned_rank_hold_for_any_order_inside_the_bins():
    """Random values with many ties, cut into bins at random edges: the exact
    Spearman coefficient (average ranks) is always inside the bounds."""
    rng = random.Random(64)
    for _ in range(400):
        n = rng.randint(6, 60)
        scale = rng.choice([3, 8, 50])
        xs = [rng.randint(0, scale) for _ in range(n)]
        ys = [x + rng.randint(-scale // 2, scale // 2) if rng.random() < 0.7 else rng.randint(0, scale) for x in xs]
        bins = rng.randint(2, 6)
        cuts_x = sorted(rng.sample(range(1, scale + 1), min(bins - 1, scale)))
        cuts_y = sorted(rng.sample(range(-scale // 2, scale + scale // 2), min(bins - 1, scale)))
        width = len(cuts_y) + 1
        counts = [0] * ((len(cuts_x) + 1) * width)
        for x, y in zip(xs, ys, strict=True):
            i = sum(x >= c for c in cuts_x)
            j = sum(y >= c for c in cuts_y)
            counts[i * width + j] += 1
        found = binned_spearman(counts, width)
        _, exact = sample_coefficient([float(x) for x in xs], [float(y) for y in ys], 2)
        if found.coefficient is None:
            continue
        assert exact is not None
        assert found.lower <= exact <= found.upper, (xs, ys, cuts_x, cuts_y)
        assert -1.0 <= found.lower <= found.coefficient <= found.upper <= 1.0


def test_G65_a_grid_in_which_every_value_has_its_bin_is_the_exact_coefficient():
    values = list(range(10))
    counts = [0] * 100
    for v in values:
        counts[v * 10 + (9 - v)] += 1
    found = binned_spearman(counts, 10)
    assert math.isclose(found.coefficient, -1.0) and found.lower <= -1.0 + 1e-9
    assert found.upper - found.coefficient < 1e-9


def test_G66_a_column_in_one_bin_has_no_rank_coefficient_and_never_zero():
    found = binned_spearman([5, 7, 0, 0], 2)
    assert found.coefficient is None and found.reason == "single_bin_first"
    found = binned_spearman([5, 0, 7, 0], 2)
    assert found.coefficient is None and found.reason == "single_bin_second"


def test_G67_the_second_pass_estimates_spearman_within_certain_bounds(tmp_path):
    rng = random.Random(67)
    rows = []
    for _ in range(4000):
        a = rng.randint(1, 400)
        b = a * a + rng.randint(0, 3000) if rng.random() < 0.9 else rng.randint(1, 170000)
        rows.append(f"{a},{b}")
    result = scan_csv(tmp_path, "a,b", rows)

    outcome = run_pairs(result, tmp_path / "data.csv", [("a", "b")])

    found = pair_entry(outcome, "a and b").result
    rank = found.rank
    assert rank.kind == "spearman_binned" and rank.accuracy == "estimated" and rank.defined
    exact = (exact_spearman(read(rows, 0), read(rows, 1)))
    assert rank.lower <= exact <= rank.upper
    assert abs(rank.coefficient - exact) < 0.05
    assert rank.upper - rank.lower < 0.2
    assert rank.bins == 64 and rank.edges_first == "rows" and rank.edges_second == "rows"


def test_G68_rank_bins_is_part_of_the_key_and_zero_turns_the_rank_off(tmp_path):
    rows = correlated_rows(1500, columns=2)
    result = scan_csv(tmp_path, "a,b", rows)
    keys = []
    for bins in (16, 64, 0):
        deep = pearson_settings(rank_bins=bins)
        plan = pair_plan(result, "a", "b", deep=deep)
        keys.append(analysis_key(plan.base, pairs_of(plan)[0]))
        outcome = run_second_pass(result, tmp_path / "data.csv", plan, settings=deep)
        found = pair_entry(outcome, "a and b").result
        assert (found.rank is None) == (bins == 0)
        if bins:
            assert found.rank.bins <= bins
    assert len(set(keys)) == 3


def test_G69_a_monotone_relation_that_is_not_a_line_is_found_by_its_rank(tmp_path):
    rng = random.Random(69)
    rows = []
    for _ in range(3000):
        a = rng.uniform(0, 12)
        rows.append(f"{a:.4f},{math.exp(a) * rng.uniform(0.9, 1.1):.4f}")
    result = scan_csv(tmp_path, "a,b", rows)

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())
    off = plan_analyses(
        result,
        forced=True,
        registry=default_registry().runnable(),
        deep=pearson_settings(rank_bins=0),
    )

    (pair,) = pairs_of(plan)
    assert pair.exploration.rank_coefficient > 0.97
    assert pair.exploration.rank_score > pair.exploration.score
    assert pair.utility.score == round(pair.exploration.rank_score * 100)
    (without,) = pairs_of(off)
    assert without.exploration.rank_score is None
    assert without.utility.score == round(without.exploration.score * 100)


def test_G70_a_pair_whose_rank_is_strong_is_chosen_by_itself_and_by_the_larger_score(tmp_path):
    rng = random.Random(70)
    rows = []
    for _ in range(3000):
        a = rng.uniform(0, 12)
        rows.append(f"{a:.4f},{math.exp(a) * rng.uniform(0.9, 1.1):.4f}")
    result = scan_csv(tmp_path, "a,b", rows)

    plan = plan_analyses(result, registry=default_registry().runnable())

    (pair,) = pairs_of(plan)
    assert pair.exploration.rank_score >= 0.45
    assert [c.display for c in chosen(plan)] == ["a and b"]


def test_G71_the_rank_of_a_complete_sample_agrees_with_the_one_read_from_the_source(tmp_path):
    rows = correlated_rows(400, columns=2, noise=0.4)
    result = scan_csv(tmp_path, "a,b", rows)
    plan = pair_plan(result, "a", "b")
    (candidate,) = pairs_of(plan)
    assert not candidate.execution.requires_source

    from_samples = pair_entry(run_second_pass(result, tmp_path / "data.csv", plan), "a and b").result
    assert from_samples.source == "samples"
    assert from_samples.rank.defined
    exact = (exact_spearman(read(rows, 0), read(rows, 1)))
    assert from_samples.rank.lower <= exact <= from_samples.rank.upper


def test_G72_the_document_with_a_line_and_a_rank_follows_its_schema(tmp_path):
    rows = correlated_rows(1500, columns=2)
    result = scan_csv(tmp_path, "a,b", rows)

    outcome = run_pairs(result, tmp_path / "data.csv", [("a", "b")])

    jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
    summary, _ = result_summary(pair_entry(outcome, "a and b").result)
    assert "slope" in summary and "rank" in summary


def test_G73_the_same_scan_gives_the_same_grid_twice(tmp_path):
    rows = correlated_rows(2500, columns=2)
    result = scan_csv(tmp_path, "a,b", rows)
    plan = pair_plan(result, "a", "b")

    first = run_second_pass(result, tmp_path / "data.csv", plan)
    second = run_second_pass(result, tmp_path / "data.csv", plan)

    assert (
        pair_entry(first, "a and b").result.rank.model_dump()
        == pair_entry(second, "a and b").result.rank.model_dump()
    )


# Tables of a category against the values of another column -------------------------

PLAN_OF = {"east": "basic", "west": "plus", "north": "pro", "south": "basic", "centre": "plus"}
REGIONS = ["east", "west", "north", "south", "centre"]


def region_rows(count: int = 2000, *, slip_every: int = 20, seed: int = 74):
    """Rows ``region,plan,site``: the plan follows the region but for every
    ``slip_every``-th row of a region, which takes another plan. The oracle holds
    the pairs the generator wrote."""
    rng = random.Random(seed)
    others = {"basic": "pro", "plus": "basic", "pro": "plus"}
    rows, oracle = [], []
    seen: dict[str, int] = {}
    for _ in range(count):
        region = rng.choices(REGIONS, weights=[40, 25, 15, 12, 8])[0]
        seen[region] = seen.get(region, 0) + 1
        plan = PLAN_OF[region]
        if slip_every and seen[region] % slip_every == 0:
            plan = others[plan]
        rows.append(f"{region},{plan},S{rng.randint(1, 9)}")
        oracle.append((region, plan))
    return rows, oracle


def ordered_by_count(values: list[str]) -> list[str]:
    counts = Counter(values)
    return sorted(counts, key=lambda value: (-counts[value], value))


def test_G74_a_category_against_another_category_counts_every_row_exactly(tmp_path):
    rows, oracle = region_rows()
    result = scan_csv(tmp_path, "region,plan,site", rows)

    outcome = run_tables(result, tmp_path / "data.csv", "region", "plan", features=("value",))

    table = table_entry(outcome, "value").result
    assert table.feature.kind == "value"
    row_labels = [c.label for c in table.categories.classes]
    column_labels = [c.label for c in table.classes.classes]
    assert row_labels[:-1] == ordered_by_count([r for r, _ in oracle])
    assert column_labels[:-1] == ordered_by_count([p for _, p in oracle])
    assert row_labels[-1] == "other" == column_labels[-1]
    counts = Counter(oracle)
    for i, region in enumerate(row_labels[:-1]):
        for j, plan in enumerate(column_labels[:-1]):
            assert table.counts[i][j] == counts[(region, plan)]
    assert table.counted == table.rows == len(oracle)
    assert 0.9 < table.purity.forward.value < 1.0
    assert table.exceptions.count == sum(sum(row) - max(row) for row in table.counts)


def test_G75_two_columns_that_are_both_categories_are_read_in_one_direction(tmp_path):
    rows, _ = region_rows()
    result = scan_csv(tmp_path, "region,plan,site", rows)

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    fields = {f.id: f.display for f in result.datasets[0].fields}
    values = {
        (fields[c.field], fields[c.partner])
        for c in tables_of(plan)
        if c.parameters["feature"] == "value"
    }
    # Fewer distinct values on the row axis (plan has 3, region 5), never both ways.
    assert ("plan", "region") in values
    assert ("region", "plan") not in values
    assert all((second, first) not in values for first, second in values)


def test_G76_a_request_may_ask_for_the_other_direction(tmp_path):
    rows, _ = region_rows()
    result = scan_csv(tmp_path, "region,plan,site", rows)

    outcome = run_tables(result, tmp_path / "data.csv", "region", "plan", features=("value",))

    table = table_entry(outcome, "value").result
    assert table.categories.display == "region" and table.classes.display == "plan"


def test_G77_the_exceptions_are_listed_up_to_the_bound_and_say_when_they_are_all(tmp_path):
    rows, _ = region_rows(slip_every=3)
    result = scan_csv(tmp_path, "region,plan,site", rows)

    narrow = DeepSettings.model_validate({"crosstab": {"max_exception_cells": 3}})
    outcome = run_tables(
        result, tmp_path / "data.csv", "region", "plan", features=("value",), deep=narrow
    )
    cut = table_entry(outcome, "value").result.exceptions
    assert cut.cells > 3 and len(cut.listed) == 3 and cut.complete is False
    assert [cell.count for cell in cut.listed] == sorted(
        (c.count for c in cut.listed), reverse=True
    )

    wide = DeepSettings.model_validate({"crosstab": {"max_exception_cells": 100}})
    outcome = run_tables(
        result, tmp_path / "data.csv", "region", "plan", features=("value",), deep=wide
    )
    every = table_entry(outcome, "value").result.exceptions
    assert every.complete is True and len(every.listed) == every.cells == cut.cells
    assert sum(cell.count for cell in every.listed) == every.count
    assert table_entry(outcome, "value").parameters["max_exception_cells"] == 100


def test_G78_a_rule_a_user_gives_is_checked_with_its_counter_examples(tmp_path):
    rows, oracle = region_rows()
    result = scan_csv(tmp_path, "region,plan,site", rows)
    request = AnalysisRequest(
        "category_crosstab",
        field="region",
        partner="plan",
        feature="value",
        rules=(("east", "basic"), ("west", "pro"), ("moon", "basic"), ("east", "gold")),
    )
    plan = plan_analyses(
        result, requests=[request], automatic=False, registry=default_registry().runnable()
    )
    assert plan.objective.requested[0].rules == 4

    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    entry = next(a for a in outcome.document.analyses if a.analyzer == "category_crosstab")
    checks = {(r.category_label, r.class_label): r for r in entry.result.provided_rules}
    counts = Counter(oracle)
    east = checks[("east", "basic")]
    total = sum(n for (region, _), n in counts.items() if region == "east")
    assert east.provenance == "provided" and east.status == "violated"
    assert east.support == total and east.exceptions == total - counts[("east", "basic")]
    assert east.confidence == counts[("east", "basic")] / total
    broken = {cell.count for cell in east.counter_examples}
    assert broken == {
        n for (region, other), n in counts.items() if region == "east" and other != "basic"
    }
    first = entry.result.classes.classes[east.counter_examples[0].column].label
    records = [i + 1 for i, (r, p) in enumerate(oracle) if r == "east" and p == first]
    assert [e.record for e in east.counter_examples[0].examples] == records[:3]
    assert checks[("west", "pro")].status == "violated"
    assert checks[("moon", "basic")].status == "unknown_category"
    assert checks[("moon", "basic")].category is None
    assert checks[("east", "gold")].status == "unknown_class"
    assert entry.parameters["rules"] == json.dumps(
        sorted(request.rules), ensure_ascii=False, separators=(",", ":")
    )


def test_G79_a_rule_that_holds_has_no_counter_example_and_rules_change_the_key(tmp_path):
    rows, _ = region_rows(slip_every=0)
    result = scan_csv(tmp_path, "region,plan,site", rows)

    def planned(rules):
        request = AnalysisRequest(
            "category_crosstab", field="region", partner="plan", feature="value", rules=rules
        )
        return plan_analyses(
            result, requests=[request], automatic=False, registry=default_registry().runnable()
        )

    with_rule, without = planned((("east", "basic"),)), planned(())
    keys = [
        analysis_key(p.base, next(c for c in p.candidates if c.selection.state == "selected"))
        for p in (with_rule, without)
    ]
    assert keys[0] != keys[1]
    outcome = run_second_pass(result, tmp_path / "data.csv", with_rule)
    (rule,) = next(
        a for a in outcome.document.analyses if a.analyzer == "category_crosstab"
    ).result.provided_rules
    assert rule.status == "holds" and rule.confidence == 1.0 and rule.counter_examples == []
    plain = run_second_pass(result, tmp_path / "data.csv", without)
    bare = next(a for a in plain.document.analyses if a.analyzer == "category_crosstab")
    assert "provided_rules" not in json.loads(bare.result.model_dump_json())


def test_G80_bad_rules_are_refused_before_the_planning(tmp_path):
    rows, _ = region_rows(200)
    result = scan_csv(tmp_path, "region,plan,site", rows)
    registry = default_registry().runnable()

    for request in (
        AnalysisRequest("category_crosstab", field="region", rules=(("east", "basic"),)),
        AnalysisRequest(
            "category_crosstab",
            field="region",
            partner="plan",
            feature="value",
            rules=(("east", ""),),
        ),
        AnalysisRequest(
            "pearson_correlation", field="region", partner="plan", rules=(("east", "basic"),)
        ),
    ):
        with pytest.raises(ConfigurationError):
            plan_analyses(result, requests=[request], registry=registry)


def test_G81_the_document_with_value_tables_and_rules_follows_its_schema(tmp_path):
    rows, _ = region_rows()
    result = scan_csv(tmp_path, "region,plan,site", rows)
    request = AnalysisRequest(
        "category_crosstab",
        field="region",
        partner="plan",
        feature="value",
        rules=(("east", "basic"),),
    )
    plan = plan_analyses(
        result, requests=[request], automatic=False, registry=default_registry().runnable()
    )
    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
    table = next(a for a in outcome.document.analyses if a.analyzer == "category_crosstab")
    summary, _ = result_summary(table.result)
    assert "by value" in summary


def test_G82_the_cost_of_a_value_table_and_of_a_rank_grid_is_declared_and_charged(tmp_path):
    from tabalyst.scanner.planner.costmodel import (
        COST_MODEL_VERSION,
        NS_PER_CELL,
        RANK_CELL_BYTES,
        cpu_class_for,
    )

    rows, _ = region_rows()
    result = scan_csv(tmp_path, "region,plan,site", rows)
    request = AnalysisRequest("category_crosstab", field="region", partner="plan", feature="value")
    plan = plan_analyses(
        result, requests=[request], automatic=False, registry=default_registry().runnable()
    )

    assert COST_MODEL_VERSION == 10 and plan.cost_model_version == 10
    (table,) = [c for c in plan.candidates if c.selection.state == "selected"]
    assert table.costs.cell_ns == NS_PER_CELL["crosstab_value"]
    assert cpu_class_for(table.costs.cell_ns) == "low"

    (tmp_path / "pairs").mkdir()
    pairs = scan_csv(tmp_path / "pairs", "a,b", correlated_rows(500, columns=2))
    for bins in (0, 64):
        planned = pair_plan(pairs, "a", "b", deep=pearson_settings(rank_bins=bins))
        (pair,) = pairs_of(planned)
        grid = [s for s in pair.costs.states if s.key.startswith("rank_grid:")]
        assert len(grid) == (1 if bins else 0)
        assert pair.parameters["rank_bins"] == bins
        if bins:
            assert grid[0].memory.max == bins * bins * RANK_CELL_BYTES


def test_G83_ranks_shared_by_the_columns_of_the_exploration_give_the_same_rank_score():
    from tabalyst.scanner.planner.relations import explore_pair

    rng = random.Random(83)
    first = [round(rng.gauss(0, 1), 2) for _ in range(300)]
    second = [round(x * x + rng.gauss(0, 0.3), 2) for x in first]
    settings = PearsonSettings()

    alone = explore_pair(first, second, settings, "all_rows")
    shared = explore_pair(
        first, second, settings, "all_rows", (average_ranks(first), average_ranks(second))
    )

    assert alone.rank_score is not None and alone == shared
