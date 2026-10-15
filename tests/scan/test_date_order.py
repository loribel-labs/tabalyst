# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The order of two dates of the same record: the exploration of the sample and the
exact count over every row (design 20.38, lot S3b)."""

import random
from datetime import date, datetime, timedelta

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_json
from second_pass_helpers import deep_csv

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner import AnalysisRequest, default_registry, plan_analyses
from tabalyst.scanner.secondpass import run_second_pass

START = date(2020, 1, 1)


def _rows(count=600, broken=(), same=(), gaps=()):
    """`start` and `end` dates, `end` after `start` but for the rows in `broken`
    (swapped), equal for `same`, with an empty `end` for `gaps`."""
    rng = random.Random(4)
    rows = []
    for i in range(count):
        begin = START + timedelta(days=rng.randrange(1000))
        finish = begin + timedelta(days=1 + rng.randrange(300))
        if i in broken:
            begin, finish = finish, begin
        if i in same:
            finish = begin
        rows.append(f"{begin.isoformat()},{'' if i in gaps else finish.isoformat()},{i}")
    return rows


def _orders(plan):
    return [c for c in plan.candidates if c.analyzer == "date_order"]


def _results(outcome):
    return [a for a in outcome.document.analyses if a.analyzer == "date_order"]


def test_a_pair_where_the_order_nearly_always_holds_is_listed_and_its_breaks_counted_exactly(
    tmp_path,
):
    broken = {10, 200, 450}
    rows = _rows(broken=broken, same={5, 6}, gaps={50})
    _, plan, outcome = deep_csv(tmp_path, "start,end,n", rows)

    [candidate] = _orders(plan)
    [result] = _results(outcome)
    assert candidate.display == "start and end" and candidate.selection.state == "selected"
    found = result.result
    assert (found.broken, found.equal, found.compared) == (3, 2, 599 - 0)
    assert found.excluded.missing == 1 and found.records == 600
    assert [b.record for b in found.listed] == [11, 201, 451]
    assert found.listed[0].first > found.listed[0].second
    assert not found.truncated


def test_a_pair_that_is_not_ordered_is_not_listed(tmp_path):
    rng = random.Random(8)
    rows = [
        f"{(START + timedelta(days=rng.randrange(900))).isoformat()},"
        f"{(START + timedelta(days=rng.randrange(900))).isoformat()}"
        for _ in range(600)
    ]
    result = scan_csv(tmp_path, "start,end", rows)

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    assert _orders(plan) == []
    [block] = plan.relations.orders
    assert block.dates == 2 and block.evaluated == 1 and block.listed == 0


def test_two_columns_of_the_same_dates_have_no_order_to_follow(tmp_path):
    rows = [f"{(START + timedelta(days=i)).isoformat()},{(START + timedelta(days=i)).isoformat()}" for i in range(600)]
    result = scan_csv(tmp_path, "start,end", rows)

    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    assert _orders(plan) == []


def test_a_request_names_the_earlier_column_first(tmp_path):
    rows = _rows(broken={3})
    result = scan_csv(tmp_path, "start,end,n", rows)

    asked = plan_analyses(
        result,
        requests=[AnalysisRequest("date_order", field="end", partner="start")],
        automatic=False,
        registry=default_registry().runnable(),
    )

    [reverse] = [c for c in _orders(asked) if c.display == "end and start"]
    assert reverse.selection.state == "selected"
    outcome = run_second_pass(result, tmp_path / "data.csv", asked)
    [found] = [a for a in _results(outcome) if a.display == "end and start"]
    assert found.result.broken > 500


def test_ambiguous_dates_are_read_in_the_order_the_evidence_of_their_column_gives(tmp_path):
    rows = []
    for i in range(600):
        day = 1 + i % 12
        # `a` is written day-first: 25/03/2020 proves it, so 03/04/2020 is 3 April.
        first = f"{(i % 28) + 1:02d}/{day:02d}/2020"
        second = f"{(i % 28) + 1:02d}/{day:02d}/2021"
        rows.append(f"{first},{second}")
    rows[100] = "03/04/2020,02/04/2020"
    _, _, outcome = deep_csv(tmp_path, "a,b", rows)

    [found] = _results(outcome)
    assert found.result.excluded.ambiguous == 0
    assert found.result.broken == 1 and found.result.listed[0].first == "2020-04-03"


def test_what_is_not_a_date_or_not_of_the_same_kind_is_counted_apart(tmp_path):
    rows = _rows()
    rows[7] = f"{rows[7].split(',')[0]},soon,7"
    result = scan_csv(tmp_path, "start,end,n", rows)
    plan = plan_analyses(
        result,
        requests=[AnalysisRequest("date_order", field="start", partner="end")],
        registry=default_registry().runnable(),
    )

    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    [found] = _results(outcome)
    assert found.result.excluded.not_a_date == 1 and found.result.broken == 0


def test_a_json_source_is_compared_record_by_record(tmp_path):
    rng = random.Random(2)
    records = []
    for i in range(300):
        begin = START + timedelta(days=rng.randrange(900))
        finish = begin + timedelta(days=1 + rng.randrange(200))
        if i == 40:
            begin, finish = finish, begin
        records.append({"start": begin.isoformat(), "end": finish.isoformat(), "n": i})
    path = write_json(tmp_path, "data.json", records)
    result = scan(path, config=ScanConfig.model_validate({}))
    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    outcome = run_second_pass(result, path, plan)

    [found] = _results(outcome)
    assert found.result.broken == 1 and found.result.listed[0].record == 41
    assert found.result.records == 300


def test_a_json_value_that_is_no_string_is_not_a_date_and_a_null_is_missing(tmp_path):
    rng = random.Random(3)
    records = []
    for i in range(300):
        begin = START + timedelta(days=rng.randrange(900))
        records.append(
            {"start": begin.isoformat(), "end": (begin + timedelta(days=30)).isoformat(), "n": i}
        )
    records[10]["end"] = 20200101
    records[11]["end"] = None
    path = write_json(tmp_path, "data.json", records)
    result = scan(path, config=ScanConfig.model_validate({}))
    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    [found] = _results(run_second_pass(result, path, plan))

    assert found.result.excluded.not_a_date == 1 and found.result.excluded.missing == 1
    assert found.result.broken == 0 and found.result.compared == 298


def test_an_excel_source_is_compared_record_by_record(tmp_path):
    xlsxwriter = pytest.importorskip("xlsxwriter")
    path = tmp_path / "data.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Contracts")
    shape = book.add_format({"num_format": "yyyy-mm-dd"})
    sheet.write_row(0, 0, ["start", "end", "n"])
    rng = random.Random(6)
    for i in range(1, 301):
        begin = datetime(2020, 1, 1) + timedelta(days=rng.randrange(900))  # noqa: DTZ001
        finish = begin + timedelta(days=1 + rng.randrange(200))
        if i == 41:
            begin, finish = finish, begin
        sheet.write_datetime(i, 0, begin, shape)
        sheet.write_datetime(i, 1, finish, shape)
        sheet.write(i, 2, i)
    book.close()
    result = scan(path, config=ScanConfig.model_validate({"excel": {"dataset_path": "$.Contracts"}}))
    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    [found] = _results(run_second_pass(result, path, plan))

    assert found.result.broken == 1 and found.result.records == 300


def test_a_sample_keeps_a_row_whose_dates_are_out_of_order(tmp_path):
    from smart_helpers import report

    rows = _rows(count=900, broken={310, 640})
    _, plan, selection, document = report(tmp_path, "start,end,n", rows, 40)

    [target] = [t for t in plan.targets if t.predicate.kind == "date_order"]
    assert target.displays == ["start", "end"] and target.frequency.count == 2
    assert target.evidence == "second_pass" and target.needs == ["scan", "second_pass"]
    assert document.coverage.verification.disagreed == []
    assert [e.id for e in document.targets if e.status == "unresolved"] == []
    kept = {row[2] for row in selection.rows}
    assert kept & {"310", "640"}


def test_no_date_order_target_when_the_order_holds_everywhere(tmp_path):
    from smart_helpers import report

    _, plan, _, _ = report(tmp_path, "start,end,n", _rows(count=900), 40)

    assert [t for t in plan.targets if t.predicate.kind == "date_order"] == []
