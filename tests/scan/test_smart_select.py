# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The tests of the targets on a row and the bounded selection of a smart sample
(design 20.16, lot 10b)."""

from smart_helpers import (
    NORMAL,
    RICH_HEADER,
    SINGLETONS,
    dated_rows,
    region_rows,
    report,
    rich_rows,
    run,
)

from tabalyst.scanner.smart.evaluate import _DuplicateTests


def _assert_faithful(document):
    """The tests agree with the Scan: nothing could not be tested, every count
    the plan holds exactly is found again, and every target is seen in the source."""
    unresolved = [(e.id, e.reason) for e in document.targets if e.status == "unresolved"]
    assert unresolved == []
    assert document.coverage.verification.disagreed == []
    assert [e.id for e in document.targets if e.reason == "not_observed"] == []


def test_every_value_of_an_exhaustive_catalog_is_in_a_large_enough_sample(tmp_path):
    _, _, selection = run(tmp_path, "region,n", region_rows(), 60)

    found = {row[0] for row in selection.rows}
    assert len(selection.rows) == 60
    assert found == set(NORMAL) | set(SINGLETONS)
    assert selection.header == ["region", "n"]
    assert selection.outcome.mandatory_total == selection.outcome.mandatory_covered == 23
    assert not selection.unresolved


def test_every_target_the_plan_counts_exactly_is_found_as_many_times_in_the_source(tmp_path):
    _, plan, selection, document = report(tmp_path, RICH_HEADER, rich_rows(), 80)

    _assert_faithful(document)
    assert document.coverage.verification.checked > 100
    assert len(selection.rows) == 80
    kinds = {t.predicate.kind for t in plan.targets}
    assert {
        "value_equals",
        "pattern_matches",
        "numeric_bin",
        "length_min",
        "relation_exception",
        "observation",
    } <= kinds


def test_decimal_extremes_beyond_their_float_stay_in_the_first_and_last_bins(tmp_path):
    # 0.1 lies below its float64 and 999.356 above it: the bins of the sample
    # stand on the edges of the second pass, widened around the written extremes,
    # so the rows of the minimum and of the maximum are counted in the outer bins.
    rows = []
    for i in range(600):
        amount = f"{1 + (i * 7919) % 998}.{i % 1000:03d}"
        if i % 50 < 4:
            amount = ("0.1", "999.356")[i % 2]
        rows.append(f"{amount},{('north', 'south', 'east')[i % 3]}")
    _, plan, _, document = report(tmp_path, "amount,group", rows, 60)

    bins = {t.id for t in plan.targets if t.predicate.kind == "numeric_bin"}
    entries = {e.id: e for e in document.targets if e.id in bins}
    assert len(entries) == 10
    assert all(e.expected is not None and e.agrees for e in entries.values())
    _assert_faithful(document)


def test_dates_and_types_are_tested_as_the_first_pass_counted_them(tmp_path):
    _, plan, _, document = report(tmp_path, "day,aware,naive,slash,mixed,n", dated_rows(), 60)

    _assert_faithful(document)
    kinds = {t.predicate.kind for t in plan.targets}
    assert {"date_min", "date_max", "date_year"} <= kinds
    rules = {t.predicate.params["rule"] for t in plan.targets if t.predicate.kind == "observation"}
    assert {"ambiguous_dates", "mixed_types"} <= rules


def _empties_and_copies() -> list[str]:
    """Identifiers with a few blanks in them and rows copied from far away."""
    rows = [f"{i},{i % 7},v{i % 3}" for i in range(4000)]
    for i in (1234, 2890):
        rows[i] = f",{i % 7},v{i % 3}"
    rows.extend(rows[i] for i in (10, 2222, 3333))
    return rows


def test_empty_cells_of_a_column_of_many_values_and_duplicate_rows_are_found_in_a_small_sample(
    tmp_path,
):
    _, plan, selection, document = report(tmp_path, "id,n,k", _empties_and_copies(), 30)

    _assert_faithful(document)
    entries = {e.id: e for e in document.targets}
    [blank] = [t for t in plan.targets if t.predicate.params.get("rule") == "missing_values"]
    [copies] = [t for t in plan.targets if t.predicate.params.get("rule") == "duplicate_rows"]
    assert entries[blank.id].status == entries[copies.id].status == "covered"
    assert (entries[blank.id].expected, entries[copies.id].expected) == (2, 3)
    assert all(entries[t.id].agrees for t in (blank, copies))
    assert any(not row[0] for row in selection.rows)
    assert len(selection.rows) == 30


def test_a_file_without_a_repeated_row_has_no_duplicate_target(tmp_path):
    _, plan, selection = run(tmp_path, "id,n,k", [f"{i},{i % 7},v{i % 3}" for i in range(600)], 20)

    rules = {t.predicate.params.get("rule") for t in plan.targets}
    assert "duplicate_rows" not in rules
    assert len(selection.rows) == 20


def test_the_duplicate_test_stops_storing_at_its_limit_like_the_scan():
    tests = _DuplicateTests(limit=2)
    tests.targets = (5,)

    found = tests.covers([["a"], ["b"], ["c"], ["a"], ["c"], ["b"]])

    assert found == [(), (), (), (5,), (), (5,)]
