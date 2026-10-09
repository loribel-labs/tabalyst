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


def test_dates_and_types_are_tested_as_the_first_pass_counted_them(tmp_path):
    _, plan, _, document = report(tmp_path, "day,aware,naive,slash,mixed,n", dated_rows(), 60)

    _assert_faithful(document)
    kinds = {t.predicate.kind for t in plan.targets}
    assert {"date_min", "date_max", "date_year"} <= kinds
    rules = {t.predicate.params["rule"] for t in plan.targets if t.predicate.kind == "observation"}
    assert {"ambiguous_dates", "mixed_types"} <= rules
