# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The help with stratification: the arithmetic, the classic sample with several
columns and a ceiling of strata, and the advice of the plan (design 20.14, lot 9)."""

import csv
import json
import random

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_text
from typer.testing import CliRunner

import tabalyst
from tabalyst.cli import app
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.scanner.planner import Stratify, plan_analyses, plan_text
from tabalyst.scanner.stratify import (
    SATURATED,
    allocate_strata,
    saturating_product,
    size_for_every_stratum,
)

runner = CliRunner()


def _write(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def _advice(result, **kwargs):
    return plan_analyses(result, stratify=Stratify(**kwargs)).stratification


def _column(advice, display):
    return next(column for column in advice.columns if column.display == display)


# The arithmetic ---------------------------------------------------------------


def test_a_product_that_fits_is_exact_and_one_that_does_not_saturates():
    assert saturating_product([12, 8, 6]) == (576, False)
    assert saturating_product([200, 2_000, 30]) == (12_000_000, False)
    assert saturating_product([SATURATED, 2]) == (SATURATED, True)
    assert saturating_product([]) == (1, False)


def test_a_saturated_product_stays_saturated_and_a_zero_still_wins():
    assert saturating_product([2**62, 2, 2, 5]) == (SATURATED, True)
    assert saturating_product([2**62, 2, 2, 0]) == (0, False)
    assert saturating_product([3, 4], cap=11) == (11, True)
    assert saturating_product([3, 4], cap=12) == (12, False)


def test_a_negative_cardinality_is_refused():
    with pytest.raises(ValueError):
        saturating_product([3, -1])


def test_the_allocation_keeps_the_classic_rounding_and_the_total():
    counts = {"a": 7, "b": 2, "c": 1}

    allocated = allocate_strata(counts, 5)

    assert allocated == {"a": 4, "b": 1, "c": 0}
    assert sum(allocated.values()) == 5
    assert allocate_strata({"x": 3}, 0) == {"x": 0}
    assert allocate_strata({}, 4) == {}


def test_the_allocation_breaks_ties_by_the_text_of_the_key():
    assert allocate_strata({"b": 1, "a": 1}, 1) == {"a": 1, "b": 0}


def test_the_size_for_every_stratum_makes_the_rarest_quota_reach_one():
    assert size_for_every_stratum(10, 1000) == 100
    assert size_for_every_stratum(3, 10) == 4
    allocated = allocate_strata({"big": 990, "rare": 10}, 100)
    assert allocated["rare"] == 1
    with pytest.raises(ValueError):
        size_for_every_stratum(0, 10)


# The sample ---------------------------------------------------------------------


def test_strata_of_several_columns_are_tuples_that_never_collide(tmp_path):
    source = tmp_path / "keys.csv"
    _write(source, ["a", "b"], [("x|y", "z"), ("x", "y|z")] * 5)

    result = tabalyst.sample_csv(
        source, method="stratified", field=["a", "b"], rows=4, seed=1, output=tmp_path / "s.csv"
    )

    assert result.strata_known == 2
    assert result.fields == ("a", "b") and result.field == "a, b"
    assert result.sample_rows == 4


def test_a_stratified_sample_counts_the_strata_it_leaves_without_rows(tmp_path):
    source = tmp_path / "bal.csv"
    rows = [("a", 0)] * 50 + [("b", 0)] * 49 + [("c", 0)]
    _write(source, ["k", "n"], rows)

    result = tabalyst.sample_csv(
        source, method="stratified", field="k", rows=10, seed=2, output=tmp_path / "s.csv"
    )

    assert (result.strata_known, result.strata_selected, result.strata_uncovered) == (3, 2, 1)


def test_other_methods_report_no_balance(tmp_path):
    source = tmp_path / "plain.csv"
    _write(source, ["k"], [("a",)] * 5)

    result = tabalyst.sample_csv(source, method="first", rows=2, output=tmp_path / "s.csv")

    assert (result.strata_known, result.strata_selected, result.strata_uncovered) == (None, None, None)
    assert result.fields == ()


def test_the_ceiling_of_strata_stops_the_scan_before_memory_grows_and_names_the_way_out(tmp_path):
    source = tmp_path / "many.csv"
    _write(source, ["id"], [(i,) for i in range(50)])

    with pytest.raises(InputError, match=r"more than 10 strata.*--max-strata"):
        tabalyst.sample_csv(
            source, method="stratified", field="id", rows=5, max_strata=10, output=tmp_path / "s.csv"
        )

    tabalyst.sample_csv(
        source, method="stratified", field="id", rows=5, max_strata=50, output=tmp_path / "s.csv"
    )


@pytest.mark.parametrize(
    ("field", "message"),
    [(["a", "a"], "named twice"), ([""], "cannot be empty"), (["nope"], "does not exist")],
)
def test_a_bad_stratification_field_is_refused(tmp_path, field, message):
    source = tmp_path / "bad.csv"
    _write(source, ["a", "b"], [(1, 2)] * 3)

    with pytest.raises(InputError, match=message):
        tabalyst.sample_csv(
            source, method="stratified", field=field, rows=1, output=tmp_path / "s.csv"
        )


def test_fields_are_refused_with_another_method_and_a_zero_ceiling_too(tmp_path):
    source = tmp_path / "x.csv"
    _write(source, ["a"], [(1,)] * 3)

    with pytest.raises(InputError, match="only be used with stratified"):
        tabalyst.sample_csv(source, method="first", field=["a"], rows=1, output=tmp_path / "s.csv")
    with pytest.raises(InputError, match="at least 1"):
        tabalyst.sample_csv(
            source, method="stratified", field="a", rows=1, max_strata=0, output=tmp_path / "s.csv"
        )


def test_the_cli_takes_several_fields_and_prints_the_balance(tmp_path):
    source = tmp_path / "cli.csv"
    _write(source, ["a", "b"], [(i % 2, i % 3) for i in range(60)])

    result = runner.invoke(
        app,
        ["sample", str(source), "--sample-method", "stratified", "--field", "a", "--field", "b",
         "--rows", "12", "--seed", "1", "-o", str(tmp_path / "s.csv")],
    )

    assert result.exit_code == 0, result.output
    assert "Field:         a, b" in result.output
    assert "Strata:        6 known, 6 sampled, 0 without rows" in result.output


# The advice of the plan ---------------------------------------------------------


def test_a_plan_without_the_request_has_no_advice_and_keeps_its_identity(tmp_path):
    result = scan_csv(tmp_path, "k,n", [f"{i % 3},{i}" for i in range(60)])

    plain = plan_analyses(result)
    advised = plan_analyses(result, stratify=Stratify())

    assert plain.stratification is None and "stratification" not in plain.model_dump(mode="json")
    assert advised.stratification is not None
    assert advised.candidates == plain.candidates and advised.plan_id != plain.plan_id


def test_the_advice_is_deterministic_and_holds_no_value_of_the_data(tmp_path):
    rows = [f"{random.Random(i).choice(['Quebec', 'Ontario'])},v{i}" for i in range(80)]
    result = scan_csv(tmp_path, "region,token", rows)

    first = plan_analyses(result, stratify=Stratify(combinations=(("region", "token"),)))
    second = plan_analyses(result, stratify=Stratify(combinations=(("region", "token"),)))

    assert first.plan_id == second.plan_id
    text = json.dumps(first.stratification.model_dump(mode="json"))
    assert "Quebec" not in text and "Ontario" not in text and "v1" not in text


def test_identifiers_constants_and_near_unique_columns_are_not_keys(tmp_path):
    rows = [f"{i},same,{i % 79},{i % 4}" for i in range(80)]
    result = scan_csv(tmp_path, "client_id,flag,spread,quarter", rows)

    advice = _advice(result)

    assert _column(advice, "client_id").reasons == ["identifier"]
    assert _column(advice, "flag").reasons == ["single_value"]
    assert _column(advice, "spread").reasons == ["near_unique"]
    quarter = _column(advice, "quarter")
    assert quarter.candidate and quarter.strata == 4 and quarter.strata_basis == "exact"
    assert quarter.smallest_share == 0.25 and quarter.size_for_every_stratum == 4


def test_a_missing_value_is_a_stratum_of_its_own(tmp_path):
    rows = [f"{'a' if i % 3 else ''},{i % 2}" for i in range(60)]
    result = scan_csv(tmp_path, "k,p", rows)

    advice = _advice(result)

    column = _column(advice, "k")
    assert column.strata == 2 and column.missing_share == pytest.approx(1 / 3, abs=1e-6)
    assert advice.limits.missing == "own_stratum"


def test_the_classic_allocation_is_simulated_to_count_strata_without_a_row(tmp_path):
    rows = ["big"] * 95 + ["mid"] * 4 + ["rare"]
    result = scan_csv(tmp_path, "k", rows)

    advice = _advice(result, sample_size=10)

    column = _column(advice, "k")
    # 10 rows: big 9.5, mid 0.4 and rare 0.1; the last row goes to big.
    assert column.uncovered_at_size == 2 and "rare_strata" in column.reasons
    assert advice.sample_size == 10
    assert _column(_advice(result), "k").uncovered_at_size is None


def test_a_complete_row_sample_gives_the_exact_number_of_combinations(tmp_path):
    rows = [f"{i % 3},{i % 3}" for i in range(60)]
    result = scan_csv(tmp_path, "a,b", rows)

    advice = _advice(result, combinations=(("a", "b"),))

    entry = advice.combinations[0]
    assert entry.strata_bound == 9 and entry.observed == 3 and entry.observed_exact
    assert entry.sample_scope == "all_rows" and entry.risk == "low"


def test_many_possible_strata_raise_the_risk_and_suggest_a_way_out(tmp_path):
    rows = [f"{i % 400},{i % 397},{i % 7}" for i in range(2000)]
    result = scan_csv(tmp_path, "a,b,c", rows)

    advice = _advice(result, combinations=(("a", "b"), ("a", "b", "c")), max_states=1_000)

    entry = advice.combinations[0]
    assert entry.risk in ("high", "excessive") and "bound_exceeds_states" in entry.reasons
    assert entry.suggestions == ["reduce_fields", "set_explicit_limit", "use_smart"]
    assert entry.widest_field is not None
    assert "stratify by fewer" in plan_text(plan_analyses(result, stratify=Stratify(
        combinations=(("a", "b"),), max_states=1_000)), "x.csv")


def test_a_bad_combination_is_a_configuration_error(tmp_path):
    result = scan_csv(tmp_path, "a,b", [f"{i % 2},{i % 3}" for i in range(40)])

    for combination, message in [
        (("a", "nope"), "No dataset has every field"),
        (("a",), "at least two"),
        (("a", "a"), "named twice"),
    ]:
        with pytest.raises(ConfigurationError, match=message):
            _advice(result, combinations=(combination,))
    with pytest.raises(ConfigurationError, match="at least 1"):
        _advice(result, sample_size=0)


def test_scan_plan_prints_the_advice_and_refuses_it_without_a_plan(tmp_path):
    source = write_text(
        tmp_path, "data.csv", "k,n\n" + "\n".join(f"{i % 3},{i % 4}" for i in range(60)) + "\n"
    )

    shown = runner.invoke(
        app,
        ["scan", str(source), "--plan", "--stratify-by", "k,n", "--sample-size", "20", "--no-progress"],
    )
    alone = runner.invoke(app, ["scan", str(source), "--stratify"])
    orphan = runner.invoke(app, ["scan", str(source), "--plan", "--sample-size", "20"])

    assert shown.exit_code == 0, shown.output
    assert "Stratification (a recommendation" in shown.stdout and "k + n" in shown.stdout
    assert alone.exit_code == 2 and "go with --plan" in alone.output
    assert orphan.exit_code == 2 and "--sample-size goes with" in orphan.output
