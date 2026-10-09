# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests of the Pearson correlation over every row (plan tests E01 and
E02; design 20.12, specification REL-07 to REL-09)."""

import json

import pytest
from pair_helpers import correlated_rows, exact_pair, pair_entry, run_pairs
from planner_helpers import scan_csv

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
