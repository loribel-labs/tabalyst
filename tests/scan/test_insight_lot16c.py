# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 16c: the numbers of a column by category (G84 onward).

The analyzer ``category_stats`` (design 20.23): count, extremes, sum, mean,
spread, signs and a histogram of a number for each value of a category, over every
row, with the correlation ratio that rates the pairs. The oracles are exact
fractions computed from what the generator wrote, never from the code under test.
"""

from __future__ import annotations

import json
import math
import random
from bisect import bisect_right
from fractions import Fraction

import jsonschema
import pytest
from planner_helpers import scan_csv, with_field
from scan_helpers import write_json
from stats_helpers import (
    REGIONS,
    exact_ratio,
    groups_of,
    region_rows,
    run_stats,
    stats_entry,
    stats_of,
    stats_plan,
)

from tabalyst.config import DeepSettings, StatsSettings
from tabalyst.report_deep import result_summary
from tabalyst.scanner import scan
from tabalyst.scanner.correlation_ratio import (
    NO_VARIANCE,
    SINGLE_CATEGORY,
    TOO_FEW_ROWS,
    merge,
    moments_of,
    ratio,
)
from tabalyst.scanner.planner import AnalysisRequest, default_registry, plan_analyses
from tabalyst.scanner.planner.categorystats import explore_pair
from tabalyst.scanner.secondpass import analysis_key, deep_document, run_second_pass
from tabalyst.scanner.secondpass.schema import deep_schema
from tabalyst.source_guard import StaleSource


def by_label(result) -> dict[str, object]:
    """The groups of a result by the label of their category."""
    return {
        axis.label: group
        for axis, group in zip(result.categories.classes, result.groups, strict=True)
    }


def exact_quantile(values: list[Fraction], level: Fraction) -> Fraction:
    """The quantile by linear interpolation between the ranks around
    ``(n - 1) * level``, in exact fractions."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * level
    low = position.numerator // position.denominator
    high = -(-position.numerator // position.denominator)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def signed_rows(count: int = 1500, seed: int = 84) -> list[str]:
    """Rows ``kind,delta,other``: the deltas are quarters from -3 to 3, so that
    negative, zero and positive numbers all occur, some cells are empty."""
    rng = random.Random(seed)
    rows = []
    for n in range(count):
        kind = rng.choice(["a", "b", "c", "d"])
        shift = {"a": -1, "b": 0, "c": 1, "d": 2}[kind]
        delta = "" if n % 17 == 0 else f"{rng.randint(-12, 12) / 4 + shift:.2f}"
        rows.append(f"{kind},{delta},{rng.randint(0, 99)}")
    return rows


# The arithmetic ---------------------------------------------------------------------


def test_G84_the_moments_of_batches_merge_into_the_moments_of_the_whole():
    rng = random.Random(84)
    values = [rng.gauss(100, 30) for _ in range(1000)]

    whole = moments_of(values)
    merged = merge(merge(moments_of(values[:7]), moments_of(values[7:600])), moments_of(values[600:]))

    assert merged.n == whole.n == 1000
    assert math.isclose(merged.mean, whole.mean, rel_tol=1e-12)
    assert math.isclose(merged.m2, whole.m2, rel_tol=1e-9)
    assert (merged.minimum, merged.maximum) == (min(values), max(values))
    assert merge(whole, moments_of([])) is whole


def test_G85_a_ratio_without_enough_to_compare_says_why_and_is_never_zero():
    one = [moments_of([1.0, 2.0, 3.0] * 20)]
    assert ratio(one, 30).reason == SINGLE_CATEGORY
    assert ratio([moments_of([1.0, 2.0]), moments_of([3.0])], 30).reason == TOO_FEW_ROWS
    flat = [moments_of([5.0] * 40), moments_of([5.0] * 40)]
    found = ratio(flat, 30)
    assert found.reason == NO_VARIANCE and found.score is None
    # Groups with no row do not count as categories.
    assert ratio([moments_of([]), *one], 30).groups == 1


def test_G86_the_corrected_ratio_is_the_exact_one_and_never_below_zero(tmp_path):
    rows = region_rows(1200, spread=2.0)
    groups = groups_of(rows)
    eta, epsilon = exact_ratio(groups)

    found = ratio([moments_of([float(x) for x in g]) for g in groups.values()], 30)

    assert math.isclose(found.eta_squared, float(eta), rel_tol=1e-9)
    assert math.isclose(found.epsilon_squared, float(epsilon), rel_tol=1e-9)
    assert math.isclose(found.score, math.sqrt(float(epsilon)), rel_tol=1e-9)
    # Numbers that do not depend on the category: the correction pulls the ratio
    # down, clamped at 0, while the plain ratio stays positive.
    rng = random.Random(86)
    noise = [moments_of([rng.gauss(0, 1) for _ in range(40)]) for _ in range(10)]
    pure = ratio(noise, 30)
    assert pure.eta_squared > 0.0 and pure.epsilon_squared < pure.eta_squared


# The groups -------------------------------------------------------------------------


def test_G87_every_category_has_the_exact_counts_extremes_and_moments(tmp_path):
    rows = signed_rows()
    result = scan_csv(tmp_path, "kind,delta,other", rows)

    outcome = run_stats(result, tmp_path / "data.csv", "kind", "delta")

    item = stats_entry(outcome)
    assert item.status == "complete", (item.reason, item.detail)
    found = item.result
    assert found.source == "source" and found.accuracy == "exact_counts"
    groups = groups_of(rows)
    labelled = by_label(found)
    for kind, numbers in groups.items():
        group = labelled[kind]
        n = len(numbers)
        mean = sum(numbers) / n
        assert group.count == n
        assert group.min == float(min(numbers)) and group.max == float(max(numbers))
        assert math.isclose(group.sum, float(sum(numbers)), rel_tol=1e-12, abs_tol=1e-12)
        assert math.isclose(group.mean, float(mean), rel_tol=1e-12, abs_tol=1e-12)
        spread = sum((x - mean) ** 2 for x in numbers) / n
        assert math.isclose(group.std, math.sqrt(float(spread)), rel_tol=1e-9)
        assert group.positive == sum(x > 0 for x in numbers)
        assert group.negative == sum(x < 0 for x in numbers)
        assert group.zero == sum(x == 0 for x in numbers)
        assert group.positive + group.negative + group.zero == group.count
        assert sum(group.counts) == group.count
    assert any(g.negative and g.zero and g.positive for g in found.groups)


def test_G88_the_rows_left_out_are_counted_and_everything_adds_up(tmp_path):
    rows = region_rows(2000, blank_region_every=11, blank_price_every=7)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "region", "price")).result

    wanted = sum(1 for r in rows if r.split(",")[0] and r.split(",")[1])
    no_category = sum(1 for r in rows if not r.split(",")[0] and r.split(",")[1])
    no_number = sum(1 for r in rows if r.split(",")[0] and not r.split(",")[1])
    neither = sum(1 for r in rows if not r.split(",")[0] and not r.split(",")[1])
    assert found.rows == 2000 and found.counted == wanted
    assert found.excluded.category_missing == no_category
    assert found.excluded.value_missing == no_number
    assert found.excluded.both_missing == neither
    assert found.rows == found.counted + sum(found.excluded.model_dump().values())
    assert sum(g.count for g in found.groups) == found.counted == found.overall.count
    assert sum(g.rows for g in found.groups) == found.counted + found.excluded.value_missing
    assert sum(g.value_missing for g in found.groups) == found.excluded.value_missing


def test_G89_the_overall_block_is_the_whole_of_the_groups(tmp_path):
    rows = region_rows(1500)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "region", "price")).result

    values = [x for numbers in groups_of(rows).values() for x in numbers]
    overall = found.overall
    assert overall.count == len(values)
    assert overall.min == float(min(values)) and overall.max == float(max(values))
    assert math.isclose(overall.mean, float(sum(values) / len(values)), rel_tol=1e-12)
    assert overall.counts == [sum(c) for c in zip(*(g.counts for g in found.groups), strict=True)]
    assert (overall.positive, overall.negative, overall.zero) == (len(values), 0, 0)


def test_G90_the_histograms_share_their_edges_and_count_by_the_float_comparison(tmp_path):
    rows = region_rows(1800)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "region", "price")).result

    edges = found.bins.edges
    inner = edges[1:-1]
    assert len(edges) == 51 and edges == sorted(set(edges))
    assert edges[0] == found.overall.min and edges[-1] == found.overall.max
    for kind, numbers in groups_of(rows).items():
        expected = [0] * 50
        for x in numbers:
            expected[bisect_right(inner, float(x))] += 1
        assert by_label(found)[kind].counts == expected
    assert found.bins.strategy == "linear" and found.bins.bounds_source == "range"


def test_G91_the_quantiles_are_estimated_with_bounds_that_hold_the_exact_ones(tmp_path):
    rows = region_rows(2500, spread=1.5)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "region", "price")).result

    levels = [Fraction(5, 100), Fraction(25, 100), Fraction(1, 2), Fraction(75, 100), Fraction(95, 100)]
    for kind, numbers in groups_of(rows).items():
        group = by_label(found)[kind]
        assert group.median == group.quantiles[2]
        for level, quantile in zip(levels, group.quantiles, strict=True):
            truth = float(exact_quantile(numbers, level))
            assert quantile.accuracy == "estimated"
            assert quantile.lower - 1e-9 <= truth <= quantile.upper + 1e-9, (kind, level)
            assert quantile.lower <= quantile.value <= quantile.upper
            assert group.min <= quantile.lower and quantile.upper <= group.max


def test_G92_sample_quantile_edges_follow_the_shape_of_the_rows(tmp_path):
    rng = random.Random(92)
    rows = [
        f"{rng.choice('xyz')},{math.exp(rng.gauss(2, 1.2)):.3f}" for _ in range(3000)
    ]
    result = scan_csv(tmp_path, "kind,size", rows)
    deep = DeepSettings(bin_strategy="sample_quantile", stats=StatsSettings(bins=20))

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "kind", "size", deep=deep)).result

    assert found.bins.strategy == "sample_quantile" and found.bins.bounds_source == "rows"
    assert len(found.bins.edges) == 21
    # Cut at the quantiles of the rows, the bins of the whole are about equally full.
    counts = found.overall.counts
    assert max(counts) < 3 * (sum(counts) / len(counts))
    assert sum(counts) == found.overall.count == 3000


def test_G93_the_categories_beyond_the_limit_are_other_and_take_no_part_in_the_ratio(tmp_path):
    rows = region_rows(2000)
    result = scan_csv(tmp_path, "region,price,noise", rows)
    deep = DeepSettings(stats=StatsSettings(max_categories=3))

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "region", "price", deep=deep)).result

    labels = [c.label for c in found.categories.classes]
    assert len(labels) == 4 and labels[-1] == "other"
    other = found.groups[-1]
    named = found.groups[:-1]
    assert other.count and sum(g.count for g in found.groups) == found.counted
    assert found.association.groups == 3
    assert found.association.n == sum(g.count for g in named)


# The ratio of a pair ----------------------------------------------------------------


def test_G94_the_ratio_of_the_result_is_the_exact_one(tmp_path):
    rows = region_rows(1600, spread=2.5, blank_price_every=9)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "region", "price")).result

    eta, epsilon = exact_ratio(groups_of(rows))
    association = found.association
    assert association.defined and association.groups == len(REGIONS)
    assert math.isclose(association.eta_squared, float(eta), rel_tol=1e-9)
    assert math.isclose(association.epsilon_squared, float(epsilon), rel_tol=1e-9)
    assert math.isclose(association.score, math.sqrt(float(epsilon)), rel_tol=1e-9)
    summary, _ = result_summary(found)
    assert "explain" in summary and "rows described by 5 categories" in summary


def test_G95_a_result_without_a_ratio_says_why(tmp_path):
    rows = [f"a,{n % 7}" for n in range(300)] + ["b," for _ in range(5)]
    result = scan_csv(tmp_path, "kind,value", rows)

    found = stats_entry(run_stats(result, tmp_path / "data.csv", "kind", "value")).result

    association = found.association
    assert association.defined is False and association.reason == "single_category"
    assert association.groups == 1 and association.eta_squared is None
    assert dict(by_label(found))["b"].count == 0
    summary, _ = result_summary(found)
    assert summary.endswith("only one category has rows")


# The planner ------------------------------------------------------------------------


def test_G96_a_category_that_explains_a_number_is_chosen_by_itself_and_noise_is_not(tmp_path):
    rows = region_rows(3000)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    plan = plan_analyses(result, registry=default_registry().runnable())

    candidates = stats_of(plan)
    chosen = [c for c in candidates if c.selection.state == "selected"]
    assert [c.display for c in chosen] == ["region and price"]
    (stats,) = chosen
    assert stats.id == "category_stats:rows:column_1>column_2"
    assert stats.exploration.score > 0.9 and stats.utility.reasons == ["exploratory_correlation_ratio"]
    assert stats.selection.reason == "automatic"
    assert stats.method == "group_moments"
    assert stats.parameters == {"max_categories": 30, "bins": 50, "strategy": "linear"}
    (block,) = plan.relations.stats
    assert (block.categories, block.numeric, block.rows, block.scope) == (1, 2, 900, "interior_rows")
    assert block.possible == block.evaluated == 2 and block.work == 2 * 900
    assert block.listed + block.undefined <= block.possible


def test_G97_an_analysis_that_the_sample_scores_low_is_not_chosen_by_itself(tmp_path):
    rows = region_rows(3000, spread=40.0)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    plan = plan_analyses(result, registry=default_registry().runnable())

    assert [c for c in stats_of(plan) if c.selection.state == "selected"] == []
    weak = [c for c in stats_of(plan) if c.display == "region and price"]
    assert weak and weak[0].selection.reason == "low_utility"


def test_G98_a_pair_the_sample_cannot_score_is_counted_with_its_reason():
    rng = random.Random(98)
    codes = [rng.randrange(3) for _ in range(120)]
    values = [rng.gauss(0, 1) for _ in range(120)]
    settings = StatsSettings()

    scored = explore_pair(codes, values, 4, settings, "all_rows")
    single = explore_pair([0] * 120, values, 4, settings, "all_rows")
    short = explore_pair(codes[:20], values[:20], 4, settings, "all_rows")
    # The last class is ``other``: it holds rows but is no category.
    only_other = explore_pair([0] * 100 + [3] * 20, values, 4, settings, "all_rows")

    assert scored.score is not None and scored.groups == 3 and scored.rows == 120
    assert (single.score, single.reason, single.groups) == (None, "single_category", 1)
    assert short.reason == "too_few_rows"
    assert only_other.reason == "single_category" and only_other.rows == 120


def test_G99_a_request_names_a_pair_the_exploration_did_not_list(tmp_path):
    rows = region_rows(3000)
    result = scan_csv(tmp_path, "region,price,noise", rows)

    plan = stats_plan(result, "region", "noise")

    (requested,) = [c for c in stats_of(plan) if c.selection.requested]
    assert requested.display == "region and noise" and requested.selection.state == "selected"
    assert requested.selection.reason == "requested"
    assert requested.exploration is not None
    assert [c.selection.state for c in stats_of(plan)].count("selected") == 1
    (item,) = plan.objective.requested
    assert item.analyzer == "category_stats" and item.candidates == 1


def test_G100_a_pair_that_cannot_play_its_parts_is_not_applicable_with_the_reason(tmp_path):
    rows = [f"{row},{'tag-' + str(n % 4)}" for n, row in enumerate(region_rows(3000))]
    result = scan_csv(tmp_path, "region,price,noise,tag", rows)
    registry = default_registry().runnable()

    def reasons(category: str, number: str) -> list[str]:
        request = AnalysisRequest("category_stats", field=category, partner=number)
        plan = plan_analyses(result, requests=[request], automatic=False, registry=registry)
        (candidate,) = [c for c in stats_of(plan) if c.selection.requested]
        assert candidate.applicability.state == "not_applicable"
        return candidate.applicability.reasons

    # A number is no category (too many distinct values), a text is no number.
    assert reasons("price", "noise") == ["too_many_categories"]
    assert reasons("region", "tag") == ["not_numeric"]


def test_G101_two_columns_that_could_both_be_categories_are_read_in_one_direction(tmp_path):
    rng = random.Random(101)
    rows = []
    for _ in range(2000):
        grade = rng.randint(1, 4)
        rows.append(f"{grade},{grade * 10 + rng.randint(0, 5)}")
    result = scan_csv(tmp_path, "grade,mark", rows)

    plan = plan_analyses(result, registry=default_registry().runnable())

    # ``grade`` has the fewer distinct values: it is the category.
    assert [c.id for c in stats_of(plan)] == ["category_stats:rows:column_1>column_2"]
    other_way = stats_plan(result, "mark", "grade")
    assert [c.id for c in stats_of(other_way) if c.selection.requested] == [
        "category_stats:rows:column_2>column_1"
    ]


def test_G102_a_masked_category_or_number_makes_the_pair_not_applicable(tmp_path):
    result = scan_csv(tmp_path, "region,price,noise", region_rows(3000))
    request = [AnalysisRequest("category_stats", field="region", partner="price")]
    for display in ("region", "price"):
        masked = with_field(result, display, exposure="mask")

        plan = plan_analyses(
            masked, requests=request, automatic=False, registry=default_registry().runnable()
        )

        (candidate,) = [c for c in stats_of(plan) if c.selection.requested]
        assert candidate.applicability.state == "not_applicable"
        assert candidate.applicability.reasons == ["sensitive_exposure"]


def test_G103_the_columns_left_out_of_the_exploration_are_counted_with_their_reason(tmp_path):
    rows = [f"v{n % 6},u{n},{n},{n % 5}.5" for n in range(1500)]
    result = scan_csv(tmp_path, "kind,label,serial,weight", rows)

    plan = plan_analyses(result, registry=default_registry().runnable())

    (block,) = plan.relations.stats
    assert block.excluded_categories["near_unique"] >= 2
    assert block.categories >= 1 and block.numeric >= 1
    assert block.possible == block.evaluated


# The source -------------------------------------------------------------------------


def test_G104_a_complete_sample_answers_without_reading_the_source(tmp_path):
    rows = region_rows(500)
    result = scan_csv(tmp_path, "region,price,noise", rows)
    plan = stats_plan(result, "region", "price")
    (candidate,) = [c for c in stats_of(plan) if c.selection.requested]
    assert candidate.execution.requires_source is False

    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    assert outcome.read_source is False
    found = stats_entry(outcome).result
    assert found.source == "samples"
    for kind, numbers in groups_of(rows).items():
        group = by_label(found)[kind]
        assert group.count == len(numbers) and group.min == float(min(numbers))
        assert math.isclose(group.mean, float(sum(numbers) / len(numbers)), rel_tol=1e-12)
    eta, _ = exact_ratio(groups_of(rows))
    assert math.isclose(found.association.eta_squared, float(eta), rel_tol=1e-9)


def test_G105_the_result_is_the_same_in_one_process_and_in_several(tmp_path):
    rows = region_rows(6000)
    result = scan_csv(tmp_path, "region,price,noise", rows)
    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())
    assert [c for c in stats_of(plan) if c.selection.state == "selected"]

    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=3)

    def stats(outcome):
        return [
            a.result.model_dump_json() for a in outcome.document.analyses if a.analyzer == "category_stats"
        ]

    assert stats(alone) and stats(alone) == stats(shared)


def test_G106_the_batches_do_not_change_the_result(tmp_path):
    """Batches of any size give the same counts and, to rounding, the same moments."""
    rows = region_rows(9000, seed=106)
    result = scan_csv(tmp_path, "region,price,noise", rows)
    plan = stats_plan(result, "region", "price")

    whole = stats_entry(run_second_pass(result, tmp_path / "data.csv", plan)).result

    for kind, numbers in groups_of(rows).items():
        group = by_label(whole)[kind]
        assert math.isclose(group.sum, float(sum(numbers)), rel_tol=1e-13)
        mean = sum(numbers) / len(numbers)
        spread = sum((x - mean) ** 2 for x in numbers) / len(numbers)
        assert math.isclose(group.std, math.sqrt(float(spread)), rel_tol=1e-10)


def test_G107_a_json_source_is_read_with_its_native_numbers(tmp_path):
    rng = random.Random(107)
    records = []
    for n in range(4000):
        side = n % 3
        record = {"side": f"s{side}", "amount": side * 100 + rng.randint(0, 40)}
        if n % 13 == 0:
            del record["amount"]
        if n % 17 == 0:
            record["side"] = None
        records.append(record)
    source = write_json(tmp_path, "records.json", records)
    result = scan(source, workers=1)

    outcome = run_stats(result, source, "side", "amount")

    item = stats_entry(outcome)
    assert item.status == "complete", (item.reason, item.detail)
    found = item.result
    expected: dict[str, list[int]] = {}
    for record in records:
        if record["side"] is not None and "amount" in record:
            expected.setdefault(record["side"], []).append(record["amount"])
    assert found.source == "source"
    for side, numbers in expected.items():
        group = by_label(found)[side]
        assert (group.count, group.min, group.max) == (len(numbers), min(numbers), max(numbers))
        assert group.sum == sum(numbers)
    assert found.rows == 4000
    assert found.rows == found.counted + sum(found.excluded.model_dump().values())


def test_G108_a_source_that_changed_is_refused(tmp_path):
    result = scan_csv(tmp_path, "region,price,noise", region_rows(3000))
    plan = stats_plan(result, "region", "price")
    source = tmp_path / "data.csv"
    source.write_text(source.read_text(encoding="utf-8") + "north,12.5,50.0\n", encoding="utf-8")

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)


def test_G109_a_scan_that_disagrees_with_the_reading_fails_the_analysis_alone(tmp_path):
    result = scan_csv(tmp_path, "region,price,noise", region_rows(3000))
    price = result.datasets[0].fields[1]
    wrong = price.numeric.value.model_copy(update={"count": price.numeric.value.count - 1})
    tampered = with_field(result, "price", numeric=price.numeric.model_copy(update={"value": wrong}))

    outcome = run_second_pass(tampered, tmp_path / "data.csv", stats_plan(tampered, "region", "price"))

    item = stats_entry(outcome)
    assert item.status == "failed" and item.reason == "scan_mismatch"
    assert item.result is None


# The document -----------------------------------------------------------------------


def test_G110_the_document_follows_its_schema_and_omits_what_is_not_known(tmp_path):
    rows = region_rows(2000, blank_price_every=5) + ["ghost,,", "ghost,,"]
    result = scan_csv(tmp_path, "region,price,noise", rows)
    deep = DeepSettings(stats=StatsSettings(max_categories=6))

    outcome = run_stats(result, tmp_path / "data.csv", "region", "price", deep=deep)

    document = json.loads(deep_document(outcome.document))
    jsonschema.validate(document, deep_schema())
    (entry,) = [a for a in document["analyses"] if a["analyzer"] == "category_stats"]
    groups = entry["result"]["groups"]
    empty = [g for g in groups if g["count"] == 0]
    assert empty, "a category with no number is listed with its rows"
    assert not {"min", "max", "sum", "mean", "std", "median", "quantiles"} & empty[0].keys()
    assert entry["domain"] == "analytical" and entry["partner"] == "column_2"


def test_G111_the_key_follows_what_changes_the_result_and_nothing_else(tmp_path):
    result = scan_csv(tmp_path, "region,price,noise", region_rows(3000))

    def key(deep: DeepSettings) -> str:
        plan = stats_plan(result, "region", "price", deep=deep)
        (candidate,) = [c for c in stats_of(plan) if c.selection.requested]
        return analysis_key(plan.base, candidate)

    base = key(DeepSettings())
    assert key(DeepSettings(stats=StatsSettings(bins=20))) != base
    assert key(DeepSettings(stats=StatsSettings(max_categories=4))) != base
    assert key(DeepSettings(bin_strategy="sample_quantile")) != base
    # The budgets of the exploration and a setting of another analysis are not part of it.
    assert key(DeepSettings(stats=StatsSettings(automatic_stats=1, max_candidates=2))) == base
    assert key(DeepSettings(bins=20)) == base


def test_G112_a_stored_result_is_reused_and_the_settings_are_validated(tmp_path):
    result = scan_csv(tmp_path, "region,price,noise", region_rows(3000))
    plan = stats_plan(result, "region", "price")
    first = run_second_pass(result, tmp_path / "data.csv", plan)

    again = run_second_pass(result, tmp_path / "data.csv", plan, previous=first.document)

    assert again.read_source is False and again.reused == first.executed
    with pytest.raises(ValueError):
        StatsSettings(bins=1)
    with pytest.raises(ValueError):
        StatsSettings(max_categories=1)
    with pytest.raises(ValueError):
        StatsSettings(unknown=1)  # type: ignore[call-arg]


def test_G113_the_cost_is_declared_and_the_columns_it_shares_are_charged_once(tmp_path):
    from tabalyst.scanner.planner.costmodel import (
        COST_MODEL_VERSION,
        NS_PER_CELL,
        cpu_class_for,
    )

    result = scan_csv(tmp_path, "region,price,noise", region_rows(3000))
    request = [
        AnalysisRequest("category_stats", field="region", partner="price"),
        AnalysisRequest("pearson_correlation", field="price", partner="noise"),
    ]

    plan = plan_analyses(
        result, requests=request, automatic=False, registry=default_registry().runnable()
    )

    assert COST_MODEL_VERSION >= 10 and plan.cost_model_version == COST_MODEL_VERSION
    (stats,) = [c for c in stats_of(plan) if c.selection.requested]
    assert stats.costs.cell_ns == NS_PER_CELL["category_stats"]
    assert stats.costs.cpu == cpu_class_for(stats.costs.cell_ns)
    keys = [s.key for s in stats.costs.states]
    assert any(k.startswith("stats:") for k in keys)
    assert any(k.startswith("pearson_feed:") for k in keys)
    assert any(k.startswith("code_feed:") and k.endswith(":category") for k in keys)
    # The batch of the price is the one the correlation reads too.
    (pair,) = [c for c in plan.candidates if c.analyzer == "pearson_correlation" and c.selection.requested]
    shared = {s.key for s in pair.costs.states} & set(keys)
    assert any(k.startswith("pearson_feed:") for k in shared)
    assert plan.budgets.automatic_stats == 2


def test_G114_extremes_that_are_not_the_scans_fail_the_analysis_alone(tmp_path):
    result = scan_csv(tmp_path, "region,price,noise", region_rows(3000))
    price = result.datasets[0].fields[1]
    wrong = price.numeric.value.model_copy(update={"max": price.numeric.value.max + 5})
    tampered = with_field(result, "price", numeric=price.numeric.model_copy(update={"value": wrong}))

    outcome = run_second_pass(
        tampered, tmp_path / "data.csv", stats_plan(tampered, "region", "price")
    )

    item = stats_entry(outcome)
    assert item.status == "failed" and item.reason == "scan_mismatch"
    assert "extremes" in item.detail
