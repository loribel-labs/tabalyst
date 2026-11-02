# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests of the help with stratification (plan tests E06 to E08;
design 20.14, STRAT-01 to STRAT-08)."""

import csv
from collections import Counter

import pytest
from planner_helpers import scan_csv

import tabalyst
from tabalyst.errors import InputError
from tabalyst.scanner.planner import Stratify, plan_analyses
from tabalyst.scanner.stratify import SATURATED, saturating_product


def _write(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.mark.scan_json_lot("9")
def test_E06_a_very_unbalanced_proportional_sample_keeps_a_row_of_the_rare_stratum(tmp_path):
    rows = [("big", i) for i in range(990)] + [("rare", i) for i in range(10)]
    source = tmp_path / "unbalanced.csv"
    _write(source, ["kind", "n"], rows)

    result = tabalyst.sample_csv(
        source, method="stratified", field="kind", rows=20, seed=1, output=tmp_path / "s.csv"
    )

    sampled = list(csv.reader((tmp_path / "s.csv").open(encoding="utf-8")))[1:]
    # The rare stratum keeps its minimum of one row; the size stays exact.
    assert Counter(row[0] for row in sampled) == {"big": 19, "rare": 1}
    assert (result.strata_known, result.strata_selected, result.strata_uncovered) == (2, 2, 0)

    # The advice names the smallest size that can hold every stratum, and a size
    # under it is one the sample refuses.
    scan = scan_csv(tmp_path, "kind,n", [f"{k},{n}" for k, n in rows])
    advice = plan_analyses(scan, stratify=Stratify(sample_size=1)).stratification
    kind = next(column for column in advice.columns if column.display == "kind")
    assert kind.uncovered_at_size == 1
    assert "rare_strata" in kind.reasons
    assert kind.size_for_every_stratum == 2


@pytest.mark.scan_json_lot("9")
def test_E07_a_product_of_estimated_cardinalities_is_an_estimate_never_a_certain_bound(tmp_path):
    rows = [f"{i},{i % 3}" for i in range(400)]
    exact = scan_csv(tmp_path, "a,b", rows)
    limited = scan_csv(
        tmp_path, "a,b", rows, limits={"max_distinct_per_field": 20, "max_samples": 20}
    )

    sure = plan_analyses(exact, stratify=Stratify(combinations=(("a", "b"),))).stratification
    unsure = plan_analyses(limited, stratify=Stratify(combinations=(("a", "b"),))).stratification

    certain = sure.combinations[0]
    assert certain.strata_estimate is None and "estimated_strata" not in certain.reasons
    column_a = next(c for c in unsure.columns if c.display == "a")
    assert column_a.strata_basis in ("estimate", "bound")
    guess = unsure.combinations[0]
    # The bound is built from certain maxima (the 400 values a stopped count can
    # still hold, times the 3 of b, capped by the 400 records), never from the
    # estimate, which is apart and labelled.
    assert column_a.strata_bound == 400
    column_b = next(c for c in unsure.columns if c.display == "b")
    assert guess.strata_bound == min(400, column_a.strata_bound * column_b.strata_bound)
    assert "estimated_strata" in guess.reasons or "cardinality_unknown" in guess.reasons


@pytest.mark.scan_json_lot("9")
def test_E08_an_enormous_product_does_not_overflow_and_the_state_cap_stops_the_sample(tmp_path):
    product, saturated = saturating_product([2**40] * 1_000)
    assert saturated and product == SATURATED
    assert saturating_product([2**40] * 1_000 + [0]) == (0, False)

    source = tmp_path / "wide.csv"
    _write(source, ["a", "b"], [(i, i) for i in range(500)])
    with pytest.raises(InputError, match="more than 100 strata"):
        tabalyst.sample_csv(
            source,
            method="stratified",
            field=["a", "b"],
            rows=10,
            output=tmp_path / "out.csv",
            max_strata=100,
        )
    assert not (tmp_path / "out.csv").exists()
