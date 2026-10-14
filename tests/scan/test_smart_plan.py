# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The weights, the families of targets and the plan of a smart sample (design
20.15, lot 10a)."""

import json
import random

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_text
from second_pass_helpers import deep_csv
from table_helpers import branch_rows, run_tables
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.config import (
    SmartBaseWeights,
    SmartSettings,
    SmartWeights,
    smart_settings,
)
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.plan_service import generate_plans
from tabalyst.report_service import generate_reports
from tabalyst.scanner import scan
from tabalyst.scanner.smart import (
    Smart,
    plan_sampling,
    plan_sampling_document,
    rarity,
    sampling_plan_text,
    weight_of,
)

runner = CliRunner()
WEIGHTS = SmartWeights()


def _targets(plan, family=None, kind=None):
    return [
        t
        for t in plan.targets
        if (family is None or t.family == family)
        and (kind is None or t.predicate.kind == kind)
    ]


# Weights --------------------------------------------------------------------------


def test_a_weight_never_falls_when_the_target_gets_rarer():
    shares = [1.0, 0.5, 0.1, 0.01, 1e-4, 1e-6, 1e-9, 0.0]
    weights = [weight_of("value", share, WEIGHTS).value for share in shares]
    assert weights == sorted(weights)
    assert rarity(1.0, WEIGHTS) == 0.0 and rarity(0.0, WEIGHTS) == 1.0


def test_a_weight_never_falls_when_the_base_rises_and_never_passes_the_cap():
    base = SmartBaseWeights()
    kinds = [
        "bin",
        "signal",
        "extreme",
        "pattern",
        "value",
        "remark",
        "candidate_anomaly",
        "missing",
        "confirmed_issue",
    ]
    at = [weight_of(kind, 0.001, WEIGHTS).value for kind in kinds]
    assert at == sorted(at)
    assert base.confirmed_issue > base.bin
    tight = SmartWeights(cap=7.0)
    capped = weight_of("confirmed_issue", 1e-9, tight)
    assert capped.value == 7.0 and capped.capped is True
    assert weight_of("bin", 0.5, tight).capped is False


def test_a_target_of_unknown_frequency_gets_the_neutral_rarity_and_says_so():
    unknown = weight_of("extreme", None, WEIGHTS)
    assert unknown.rarity == WEIGHTS.unknown_rarity and unknown.version == 1
    assert weight_of("extreme", 0.5, WEIGHTS).value < unknown.value < weight_of("extreme", 1e-6, WEIGHTS).value


def test_the_weights_are_configurable_and_part_of_the_plan(tmp_path):
    result = scan_csv(tmp_path, "k", [f"v{i % 4}" for i in range(80)])
    heavy = SmartSettings(weights=SmartWeights(base=SmartBaseWeights(value=9.0), cap=40.0))

    light = plan_sampling(result)
    plan = plan_sampling(result, settings=heavy)

    assert plan.settings.weights.base.value == 9.0
    assert plan.settings_sha256 == heavy.sha256() != light.settings_sha256
    assert plan.targets[0].weight.base == 9.0 and plan.plan_id != light.plan_id


# Families --------------------------------------------------------------------------


def test_a_column_of_many_values_gets_no_value_target_and_says_why(tmp_path):
    result = scan_csv(tmp_path, "id,k", [f"{i},{i % 3}" for i in range(500)])

    plan = plan_sampling(result)

    by_display = {c.display: c for c in plan.catalogs if c.family == "low_cardinality"}
    assert by_display["id"].reasons == ["high_cardinality"] and by_display["id"].targets == 0
    assert by_display["id"].guarantee == "none"
    assert by_display["k"].guarantee == "catalog_complete" and by_display["k"].targets == 3


def test_a_constant_column_without_missing_cells_has_nothing_to_tell_apart(tmp_path):
    result = scan_csv(tmp_path, "k,n", [f"same,{i}" for i in range(50)])

    plan = plan_sampling(result)

    [catalog] = [c for c in plan.catalogs if c.display == "k"]
    assert catalog.reasons == ["single_value"] and catalog.targets == 0


def test_missing_cells_are_a_target_of_their_own(tmp_path):
    result = scan_csv(tmp_path, "k,n", [f"{'' if i % 10 == 0 else 'ab'[i % 2]},{i}" for i in range(60)])

    plan = plan_sampling(result)

    [missing] = _targets(plan, "low_cardinality", "value_missing")
    assert missing.frequency.count == 6 and missing.frequency.accuracy == "exact"
    assert missing.obligation == "mandatory"


def test_a_complete_enum_leaves_the_other_families_nothing_to_add(tmp_path):
    result = scan_csv(tmp_path, "code,n", [f"{10 + i % 5},{i}" for i in range(400)])

    plan = plan_sampling(result)

    code = next(c.field for c in plan.catalogs if c.display == "code")
    own = [t for t in plan.targets if t.fields == [code]]
    assert {t.family for t in own} == {"low_cardinality"}


def test_numeric_targets_name_the_extremes_zero_signs_and_bins(tmp_path):
    rng = random.Random(3)
    rows = [str(rng.randint(-500, 500)) for _ in range(600)] + ["0"] * 30
    result = scan_csv(tmp_path, "x", rows)

    plan = plan_sampling(result)

    kinds = {t.predicate.kind for t in _targets(plan, "numeric")}
    assert kinds == {"numeric_min", "numeric_max", "numeric_zero", "numeric_sign", "numeric_bin"}
    bins = _targets(plan, "numeric", "numeric_bin")
    assert len(bins) == 10 and {t.predicate.params["of"] for t in bins} == {10}
    assert all(t.frequency.accuracy == "unknown" for t in bins), "no histogram yet"
    assert all(t.evidence == "exact" and t.needs == ["scan"] for t in bins)
    zero = _targets(plan, "numeric", "numeric_zero")[0]
    assert zero.frequency.count >= 30


def test_a_binary_integer_column_gets_no_bins(tmp_path):
    result = scan_csv(tmp_path, "x,y", [f"{i % 2},{i}" for i in range(400)])

    # Without the enumeration of its two values, the extremes are all it has.
    plan = plan_sampling(result, settings=SmartSettings(max_enum_values=1))

    x = [t for t in _targets(plan, "numeric") if t.displays == ["x"]]
    assert {t.predicate.kind for t in x} == {"numeric_min", "numeric_max", "numeric_zero"}
    assert not [t for t in x if t.predicate.kind == "numeric_bin"]


def test_dense_histogram_gives_exact_counts_to_the_bins(tmp_path):
    rows = [f"{i % 1000}" for i in range(2000)]
    result, _, outcome = deep_csv(tmp_path, "x", rows)

    plan = plan_sampling(result, deep=outcome.document)

    bins = _targets(plan, "numeric", "numeric_bin")
    assert [t.frequency.count for t in bins] == [200] * 10
    assert all(t.frequency.accuracy == "exact" and t.evidence == "second_pass" for t in bins)
    assert all(t.needs == ["scan", "second_pass"] for t in bins)


def test_date_targets_name_the_bounds_the_formats_and_the_years(tmp_path):
    rows = [f"{2015 + i % 8}-{1 + i % 12:02d}-{1 + i % 27:02d}" for i in range(500)]
    result = scan_csv(tmp_path, "day", rows)

    plan = plan_sampling(result)

    kinds = {t.predicate.kind for t in _targets(plan, "date")}
    assert {"date_min", "date_max", "date_year"} <= kinds
    years = _targets(plan, "date", "date_year")
    assert len(years) == 8 and sum(t.frequency.count for t in years) == 500
    assert not any(t.predicate.kind == "date_kind" for t in _targets(plan, "date")), "one format"


def test_text_columns_get_pattern_and_length_targets_with_their_basis(tmp_path):
    rng = random.Random(5)
    rows = [
        "".join(rng.choice("ABCDEFGH") for _ in range(2)) + f"{rng.randint(1000, 9999)}"
        for _ in range(800)
    ] + ["x-" + str(i) for i in range(30)]
    result = scan_csv(tmp_path, "ref", rows)

    plan = plan_sampling(result)

    patterns = _targets(plan, "structured_string", "pattern_matches")
    assert len(patterns) >= 2
    assert all(t.frequency.accuracy == "indicator" for t in patterns)
    assert {t.predicate.kind for t in _targets(plan, "structured_string")} >= {
        "pattern_matches",
        "length_min",
        "length_max",
    }
    [catalog] = [c for c in plan.catalogs if c.family == "structured_string"]
    assert catalog.targets > 0 and catalog.guarantee in ("catalog_complete", "known_values_only")


def test_validated_patterns_bring_exact_occurrences(tmp_path):
    rng = random.Random(5)
    rows = [
        "".join(rng.choice("ABCDEFGH") for _ in range(2)) + f"{rng.randint(1000, 9999)}"
        for _ in range(800)
    ] + ["x-" + str(i) for i in range(30)]
    result, _, outcome = deep_csv(tmp_path, "ref", rows)

    plan = plan_sampling(result, deep=outcome.document)

    patterns = _targets(plan, "structured_string", "pattern_matches")
    assert patterns and all(t.frequency.accuracy == "exact" for t in patterns)
    assert all(t.evidence == "second_pass" for t in patterns)
    assert sum(t.frequency.count for t in patterns) <= 830


def test_observations_become_quality_targets_and_some_are_not_evaluable_yet(tmp_path):
    rows = [f"{i},{i}.5" for i in range(300)] + ["abc,x"] * 3 + ["7,7.5"] * 4
    result = scan_csv(tmp_path, "id,amount", rows)

    plan = plan_sampling(result)

    quality = _targets(plan, "quality")
    assert quality, "the Scan finds a mixed column and duplicate rows"
    assert all(t.predicate.kind == "observation" and t.origin for t in quality)
    by_rule = {t.predicate.params["rule"]: t for t in quality}
    duplicates = by_rule["duplicate_rows"]
    assert duplicates.feasibility == "ready" and duplicates.obligation == "optional"
    assert not duplicates.fields and duplicates.frequency.count == 6


def test_a_rule_without_a_test_on_a_row_is_a_target_the_sample_cannot_recognize_yet(
    tmp_path, monkeypatch
):
    from tabalyst.scanner.smart import reasons, targets

    rows = [f"{1000 + i},{i % 3}" for i in range(300)] + ["12,1", "13,2"]
    result = scan_csv(tmp_path, "code,k", rows)
    monkeypatch.setattr(targets, "EVALUABLE_RULES", targets.EVALUABLE_RULES - {"minority_length"})
    monkeypatch.setitem(targets.NOT_EVALUABLE_RULES, "minority_length", "needs_test")
    monkeypatch.setitem(reasons.FEASIBILITY, "needs_test", "the rule has no test on a row yet")

    plan = plan_sampling(result)

    [short] = [t for t in _targets(plan, "quality") if t.predicate.params["rule"] == "minority_length"]
    assert short.feasibility == "not_evaluable" and short.reason == "needs_test"
    assert plan.summary.not_evaluable >= 1
    assert "cannot recognize yet" in sampling_plan_text(plan, "data.csv")


def test_the_remarks_of_the_normalization_and_the_variants_are_targets_a_row_can_show(tmp_path):
    cities = ["Montreal", "montreal", "MONTREAL", "Quebec", "Laval"]
    rows = [f"{1000 + i},{cities[i % 5]},  x{i}  ,a  b" for i in range(300)]
    result = scan_csv(tmp_path, "id,city,pad,gap", rows)

    plan = plan_sampling(result)

    quality: dict[tuple[str, str], list] = {}
    for t in _targets(plan, "quality"):
        if t.fields:
            quality.setdefault((t.displays[0], t.predicate.params["rule"]), []).append(t)
    [trimmed] = quality["pad", "trimmed_cells"]
    [collapsed] = quality["gap", "collapsed_whitespace"]
    [group] = quality["city", "variant_groups"]
    assert trimmed.feasibility == collapsed.feasibility == group.feasibility == "ready"
    assert trimmed.weight.base == SmartBaseWeights().remark
    assert group.weight.base == SmartBaseWeights().signal
    # Two of the three variants are minority: the group holds 60 rows of each.
    assert group.frequency.accuracy == "exact" and group.frequency.count == 120
    assert plan.summary.not_evaluable == 0


def test_empty_cells_of_a_column_of_many_values_are_a_target_of_the_column(tmp_path):
    rows = [f",{i % 3}" if i % 100 == 7 else f"{i},{i % 3}" for i in range(500)]
    result = scan_csv(tmp_path, "id,k", rows)

    plan = plan_sampling(result)

    [target] = [
        t for t in _targets(plan, "quality")
        if t.predicate.params["rule"] == "missing_values"
    ]
    assert target.displays == ["id"]
    assert target.feasibility == "ready" and target.obligation == "optional"
    assert target.frequency.accuracy == "exact" and target.frequency.count == 5
    assert target.weight.base == SmartBaseWeights().missing


def test_a_column_that_already_has_a_target_for_its_empty_cells_gets_no_second_one(tmp_path):
    rows = [f"{i}," if i % 10 == 3 else f"{i},v{i % 4}" for i in range(200)]
    result = scan_csv(tmp_path, "id,k", rows)

    plan = plan_sampling(result)

    assert _targets(plan, "low_cardinality", "value_missing")
    rules = {t.predicate.params["rule"] for t in _targets(plan, "quality")}
    assert "missing_values" not in rules


def test_relations_come_from_the_second_pass_only(tmp_path):
    rows, _ = branch_rows(branches=6, per_branch=80, exception_every=10)
    result = scan_csv(tmp_path, "branch,client", rows)
    outcome = run_tables(result, tmp_path / "data.csv", "branch", "client")

    without = plan_sampling(result)
    with_deep = plan_sampling(result, deep=outcome.document)

    assert not _targets(without, "relations")
    exceptions = _targets(with_deep, "relations")
    assert exceptions and all(t.predicate.kind == "relation_exception" for t in exceptions)
    assert all(t.predicate.source == "second_pass" and t.origin for t in exceptions)
    assert all(len(t.fields) == 2 for t in exceptions)


# The plan --------------------------------------------------------------------------


def test_the_plan_holds_no_value_of_the_data_and_is_the_same_every_time(tmp_path):
    rows = [f"Canary-{i % 5},ZZtop{i % 7}" for i in range(300)]
    result = scan_csv(tmp_path, "who,what", rows)

    first = plan_sampling(result, size=40)
    second = plan_sampling(result, size=40)

    assert first.plan_id == second.plan_id and first == second
    assert "Canary" not in first.model_dump_json() and "ZZtop" not in first.model_dump_json()
    assert plan_sampling(result, size=41).plan_id != first.plan_id
    assert plan_sampling(result, seed=5).method.seed == 5
    assert first.method.seed == result.config.random_seed


def test_the_budget_of_targets_keeps_mandatory_ones_first_and_the_catalogs_honest(tmp_path):
    rows = [f"{'abcdefgh'[i % 8]},{i % 5}" for i in range(400)]
    result = scan_csv(tmp_path, "a,b", rows)

    whole = plan_sampling(result)
    plan = plan_sampling(result, settings=SmartSettings(max_targets=10))

    assert whole.summary.mandatory == 13 and whole.summary.dropped == 0
    assert plan.summary.targets == 10 and plan.summary.dropped == whole.summary.targets - 10
    assert all(t.obligation == "mandatory" for t in plan.targets)
    cut = [c for c in plan.catalogs if "target_budget" in c.reasons]
    assert cut and all(not c.complete for c in cut)
    low = next(f for f in plan.summary.families if f.family == "low_cardinality")
    assert low.targets == 10 and low.dropped == 3


def test_the_reserve_gives_way_to_the_mandatory_targets(tmp_path):
    result = scan_csv(tmp_path, "k", [f"v{i % 20}" for i in range(400)])

    roomy = plan_sampling(result, size=100)
    tight = plan_sampling(result, size=22)
    unsized = plan_sampling(result)

    assert (roomy.reserve.rows_requested, roomy.reserve.rows_granted) == (20, 20)
    assert roomy.reserve.reduced_by_mandatory is False
    assert (tight.reserve.rows_requested, tight.reserve.rows_granted) == (5, 2)
    assert tight.reserve.reduced_by_mandatory is True
    assert unsized.reserve.rows_granted is None and unsized.size.requested is None
    assert roomy.conflict == "mandatory_first"
    assert "below the number of mandatory targets" in sampling_plan_text(
        plan_sampling(result, size=5), "data.csv"
    )


def test_the_candidate_budget_says_when_it_does_not_hold(tmp_path):
    result = scan_csv(tmp_path, "k,n", [f"v{i % 30},{i}" for i in range(600)])

    fits = plan_sampling(result)
    over = plan_sampling(result, settings=SmartSettings(max_candidate_bytes=100))

    assert fits.candidates.fits is True
    assert fits.candidates.per_target_effective == fits.candidates.per_target == 2
    assert over.candidates.fits is False
    assert over.candidates.per_target_effective == 1
    assert over.candidates.budget_bytes == 100


def test_a_stale_second_pass_document_is_ignored_and_reported(tmp_path):
    rows = [f"{i % 1000}" for i in range(2000)]
    (tmp_path / "a").mkdir()
    _, _, outcome = deep_csv(tmp_path / "a", "x", rows)
    other = scan_csv(tmp_path, "x", [f"{i % 900}" for i in range(2000)])

    plan = plan_sampling(other, deep=outcome.document)

    assert plan.enrichment.deep == "stale" and plan.enrichment.used == 0
    assert all(t.frequency.accuracy == "unknown" for t in _targets(plan, "numeric", "numeric_bin"))


def test_a_size_below_one_or_an_unknown_dataset_is_refused(tmp_path):
    result = scan_csv(tmp_path, "k", ["a", "b", "a"])

    with pytest.raises(ConfigurationError, match="at least 1"):
        plan_sampling(result, size=0)
    with pytest.raises(ConfigurationError, match="no dataset named"):
        plan_sampling(result, dataset="nope")


def test_several_datasets_must_be_told_apart(tmp_path):
    source = write_text(
        tmp_path,
        "data.json",
        json.dumps({"a": [{"k": 1}, {"k": 2}], "b": [{"k": 3}, {"k": 4}]}),
    )
    result = scan(source)

    with pytest.raises(ConfigurationError, match="several datasets"):
        plan_sampling(result)
    named = plan_sampling(result, dataset=result.datasets[0].id)
    assert named.dataset == result.datasets[0].id


def test_a_masked_column_gets_no_target_and_says_exposure(tmp_path):
    from planner_helpers import with_field

    result = scan_csv(tmp_path, "k,n", [f"v{i % 4},{i}" for i in range(80)])
    masked = with_field(result, "k", exposure="hide")

    plan = plan_sampling(masked)

    [catalog] = [c for c in plan.catalogs if c.display == "k"]
    assert catalog.reasons == ["exposure"] and catalog.targets == 0
    field = catalog.field
    assert not [t for t in plan.targets if field in t.fields]


def test_a_report_is_not_an_input_to_a_sampling_plan(tmp_path):
    rows = "\n".join(f"{n},{n + 0.5}" for n in range(300))
    source = write_text(tmp_path, "data.csv", "id,price\n" + rows + "\n")
    generate_reports([source], output_dir=tmp_path / "reports", force=True)
    report = next(p for p in (tmp_path / "reports").glob("*.json") if p.name != "executions.json")

    with pytest.raises(InputError, match="plan a sample"):
        plan_sampling_document(report)


# Entry points ---------------------------------------------------------------------


def test_the_service_plans_a_sample_beside_the_analyses_and_writes_nothing(tmp_path):
    source = write_text(
        tmp_path, "data.csv", "k,n\n" + "\n".join(f"{i % 5},{i}" for i in range(120)) + "\n"
    )

    batch = generate_plans([source], smart=Smart(size=30))

    [success] = batch.successes
    assert success.sampling is not None and success.sampling.size.requested == 30
    assert success.sampling.passes.total == 1
    assert success.plan.plan_id, "the plan of analyses is unchanged"
    assert generate_plans([source]).successes[0].sampling is None
    assert not list(tmp_path.glob("*.json")), "a plan writes nothing beside the source"


def test_forcing_the_second_pass_announces_it_unless_its_document_is_current(tmp_path):
    source = write_text(
        tmp_path, "data.csv", "n\n" + "\n".join(str(i * 2) for i in range(300)) + "\n"
    )

    asked = generate_plans([source], forced=True, smart=Smart())

    [success] = asked.successes
    assert success.sampling.enrichment.requested is True
    assert success.sampling.passes.total == 2


def test_scan_plan_smart_prints_the_plan_and_needs_a_plan(tmp_path):
    source = write_text(
        tmp_path, "data.csv", "k,n\n" + "\n".join(f"{i % 3},{i}" for i in range(90)) + "\n"
    )

    shown = runner.invoke(
        app, ["scan", str(source), "--plan", "--smart", "--sample-size", "20", "--no-progress"]
    )
    alone = runner.invoke(app, ["scan", str(source), "--smart"])
    orphan = runner.invoke(app, ["scan", str(source), "--plan", "--sample-size", "20"])

    assert shown.exit_code == 0, shown.output
    assert "Smart sample plan for data.csv" in shown.stdout
    assert "Readings of the source: 1" in shown.stdout
    assert "20 rows asked" in shown.stdout
    assert alone.exit_code == 2 and "go with --plan" in alone.output
    assert orphan.exit_code == 2 and "--sample-size goes with" in orphan.output


# Configuration ---------------------------------------------------------------------


def test_smart_settings_are_read_from_the_configuration_files_and_validated(tmp_path):
    path = tmp_path / "tabalyst.json"
    path.write_text(
        json.dumps({"smart": {"reserve_share": 0.3, "weights": {"cap": 12.0}}}), encoding="utf-8"
    )

    settings = smart_settings([path])

    assert settings.reserve_share == 0.3 and settings.weights.cap == 12.0
    assert settings.max_enum_values == 100 and settings.candidates_per_target == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"smart": {"reserve_share": 2}}), encoding="utf-8")
    with pytest.raises(ConfigurationError):
        smart_settings([bad])


def test_a_catalog_only_counts_the_targets_that_list_values_or_patterns(tmp_path):
    rng = random.Random(8)
    rows = [
        "".join(rng.choice("ABCDEFGH") for _ in range(2)) + f"{rng.randint(1000, 9999)}"
        for _ in range(600)
    ] + ["x-" + str(i) for i in range(20)]
    result = scan_csv(tmp_path, "ref", rows)

    plan = plan_sampling(result, settings=SmartSettings(max_targets=3))

    assert plan.summary.targets == 3 and plan.summary.dropped > 0
    assert all(catalog.targets >= 0 for catalog in plan.catalogs)


def test_tables_of_the_same_columns_for_each_feature_all_give_their_exceptions(tmp_path):
    rows, _ = branch_rows(branches=6, per_branch=80, exception_every=10)
    result = scan_csv(tmp_path, "branch,client", rows)
    outcome = run_tables(
        result, tmp_path / "data.csv", "branch", "client", features=("pattern", "length")
    )

    plan = plan_sampling(result, deep=outcome.document)

    origins = {t.origin for t in _targets(plan, "relations")}
    tables = {a.id for a in outcome.document.analyses if a.analyzer == "category_crosstab"}
    assert len(tables) == 2 and origins == tables


def test_the_length_targets_say_they_count_the_analytical_text(tmp_path):
    result = scan_csv(tmp_path, "t", [" ab", "abcd", "abcdef", "x" * 9] * 40)

    plan = plan_sampling(result, settings=SmartSettings(max_enum_values=1))

    lengths = _targets(plan, "structured_string", "length_min") + _targets(
        plan, "structured_string", "length_max"
    )
    assert lengths and all(t.predicate.params == {"domain": "analytical"} for t in lengths)


def test_a_floor_below_a_millionth_still_tells_a_singleton_from_a_rarer_than_common_value(tmp_path):
    result = scan_csv(tmp_path, "k", [f"v{i % 3}" for i in range(300)] + ["lone"])
    fine = SmartSettings(weights=SmartWeights(floor=1e-9))

    plan = plan_sampling(result, settings=fine)

    [lone] = [t for t in _targets(plan, "low_cardinality") if t.frequency.count == 1]
    assert lone.frequency.share == pytest.approx(1 / 301, rel=1e-9)
    assert 0 < lone.weight.rarity < 1


def test_a_plan_finds_the_stored_second_pass_beside_the_scan(tmp_path):
    source = write_text(
        tmp_path, "data.csv", "n\n" + "\n".join(str(i % 700) for i in range(2000)) + "\n"
    )

    ran = runner.invoke(app, ["scan", str(source), "--deep", "--yes", "--no-progress"])
    batch = generate_plans([source], smart=Smart())

    assert ran.exit_code == 0, ran.output
    [success] = batch.successes
    assert success.sampling.enrichment.deep == "current" and success.sampling.enrichment.used > 0
    assert success.sampling.passes.total == 1
    bins = _targets(success.sampling, "numeric", "numeric_bin")
    assert bins and all(t.frequency.accuracy == "exact" for t in bins)


def test_a_second_pass_on_an_enumerated_column_is_not_announced_for_nothing(tmp_path):
    source = write_text(
        tmp_path, "data.csv", "n\n" + "\n".join(str(i % 20) for i in range(400)) + "\n"
    )

    asked = generate_plans([source], forced=True, smart=Smart())

    [success] = asked.successes
    assert not success.sampling.enrichment.awaiting
    assert success.sampling.passes.total == 1


def test_hashing_every_row_is_part_of_the_estimate_only_when_duplicates_are_a_target(tmp_path):
    from tabalyst.scanner.smart.estimate import digests_rows

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with_copies = scan_csv(tmp_path / "a", "id,k", [f"{i},{i % 3}" for i in range(100)] + ["5,2"])
    without = scan_csv(tmp_path / "b", "id,k", [f"{i},{i % 3}" for i in range(100)])

    assert digests_rows(plan_sampling(with_copies)) is True
    assert digests_rows(plan_sampling(without)) is False


def test_the_digests_the_selection_remembers_are_part_of_the_memory_it_announces(tmp_path):
    from tabalyst.scanner.smart.estimate import DIGEST_BYTES, estimate_selection

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    rows = [f"{i},{i % 3}" for i in range(100)]
    with_copies = scan_csv(tmp_path / "a", "id,k", rows + ["5,2"])
    without = scan_csv(tmp_path / "b", "id,k", rows)

    plan = plan_sampling(with_copies)
    announced = estimate_selection(plan, with_copies).memory_max_bytes

    assert announced == plan.candidates.budget_bytes + 101 * DIGEST_BYTES
    plain = plan_sampling(without)
    assert estimate_selection(plain, without).memory_max_bytes == plain.candidates.budget_bytes
