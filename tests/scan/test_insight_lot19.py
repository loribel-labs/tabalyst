# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 19: a column followed by position and the columns that miss a value
together (design 20.30 and 20.31).

The oracles below are built from the rows the generator wrote, never from the
accumulators: the slices are cut on the record number, and a record lacks a value
for a column when its cell is empty.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from itertools import pairwise

import jsonschema
import pytest
from planner_helpers import by_analyzer, scan_csv
from scan_helpers import write_text
from second_pass_helpers import entry, forced_plan

from tabalyst.config import DeepSettings
from tabalyst.report_deep import result_summary
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.secondpass import deep_document, run_second_pass
from tabalyst.scanner.secondpass.drift import DriftAccumulator, slice_bounds
from tabalyst.scanner.secondpass.parallel import part_name
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.routing import FieldRoute
from tabalyst.scanner.secondpass.schema import deep_schema

SLICES = 10
RECORDS = 1_003
# Few samples: the Scan does not hold every distinct value, so nothing is
# answered from them and the source is read.
READ = {"limits": {"max_samples": 50}}


def _slice(position: int, records: int = RECORDS) -> int:
    return position * SLICES // records


def _table(records: int = RECORDS, seed: int = 19) -> dict[str, list[str]]:
    """Columns as written, with the faults the analyses must find.

    ``region`` changes along the file (a code appears late, another leaves),
    ``phone``, ``ref`` and ``email`` go missing in the same records (a block of the
    file), ``note`` goes missing at random and ``id`` never does. ``email`` is a
    sensitive column, masked by default."""
    rng = random.Random(seed)
    ids, region, phone, ref, email, note, spread = [], [], [], [], [], [], []
    for position in range(records):
        ids.append(str(position + 1))
        region.append("QC" if position < 300 else rng.choice(("QC", "ON", "ON", "BC")))
        if position >= 800:
            region[-1] = "NS"
        together = 100 <= position < 220
        phone.append("" if together or rng.random() < 0.02 else f"555-{position:04d}")
        ref.append("" if together or rng.random() < 0.03 else f"R{position}")
        email.append("" if together or rng.random() < 0.03 else f"u{position}@x.test")
        note.append("" if rng.random() < 0.25 else rng.choice(("a", "b", "c")))
        spread.append("" if position % 7 == 0 else str(rng.randint(0, 30)))
    return {
        "id": ids,
        "region": region,
        "phone": phone,
        "ref": ref,
        "email": email,
        "note": note,
        "spread": spread,
    }


def _rows(columns: dict[str, list[str]]) -> list[str]:
    return [",".join(values) for values in zip(*columns.values(), strict=True)]


def _deep(tmp_path, columns, deep: DeepSettings | None = None, **settings):
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **{**READ, **settings})
    plan = forced_plan(result, deep)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, settings=deep)
    return result, plan, outcome


def _drift(outcome, display: str):
    found = entry(outcome, "position_drift", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _matrix(outcome, display: str):
    found = entry(outcome, "missing_matrix", display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def test_slices_are_cut_on_the_record_number_whatever_the_size_of_the_file():
    for records in (100, 101, 109, 1_003, 4_096):
        bounds = slice_bounds(records)
        assert bounds[0] == 0 and bounds[-1] == records
        for position in range(records):
            index = position * SLICES // records
            assert bounds[index] <= position < bounds[index + 1]


def test_drift_counts_the_records_values_and_missing_of_every_slice(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    for display in ("phone", "note", "spread"):
        result = _drift(outcome, display)
        values = columns[display]
        expected = Counter(_slice(p) for p, v in enumerate(values) if v)
        records = Counter(_slice(p) for p in range(RECORDS))
        assert [s.records for s in result.slices] == [records[i] for i in range(SLICES)]
        assert [s.values for s in result.slices] == [expected[i] for i in range(SLICES)]
        assert all(s.records == s.values + s.missing for s in result.slices)
        assert result.records == RECORDS
        assert result.values == sum(1 for v in values if v)
        assert result.missing == sum(1 for v in values if not v)
        assert result.slices[0].first_record == 1
        assert sum(s.records for s in result.slices) == RECORDS


def test_drift_finds_the_slice_where_a_block_of_the_file_goes_missing(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    result = _drift(outcome, "phone")
    # Positions 100 to 219 lack a phone: slices 0 and 2 (every slice has 100 or 101).
    assert result.slices[1].missing >= 100
    assert result.missing_association.defined
    assert result.missing_association.corrected > 0.3
    flat = _drift(outcome, "note")
    assert flat.missing_association.corrected < 0.2


def test_drift_follows_the_values_and_the_slice_where_each_first_appears(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    result = _drift(outcome, "region")
    followed = result.followed
    assert followed is not None and followed.distinct == 4
    by_value = {item.value: item for item in followed.listed}
    for value, item in by_value.items():
        per_slice = Counter(_slice(p) for p, v in enumerate(columns["region"]) if v == value)
        assert item.counts == [per_slice[i] for i in range(SLICES)]
        assert item.count == sum(item.counts)
        assert item.first_slice == min(per_slice)
    assert by_value["QC"].first_slice == 0
    assert by_value["NS"].first_slice == _slice(800)
    assert sum(s.new_values for s in result.slices) == 4
    assert result.slices[0].new_values == 1
    assert followed.association.defined and followed.association.corrected > 0.3


def test_drift_lists_the_most_frequent_values_and_sums_up_the_others(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns, DeepSettings.model_validate({"drift": {"max_listed": 2}}))
    followed = _drift(outcome, "region").followed
    assert followed is not None
    assert len(followed.listed) == 2
    shown = {item.value for item in followed.listed}
    rest = [
        sum(1 for p, v in enumerate(columns["region"]) if _slice(p) == i and v not in shown)
        for i in range(SLICES)
    ]
    assert followed.other == rest
    assert followed.distinct == 4


def test_drift_follows_only_the_presence_of_a_column_with_many_values(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns, DeepSettings.model_validate({"drift": {"max_tracked": 20}}))
    result = _drift(outcome, "spread")
    assert result.followed is None
    assert all(s.new_values is None for s in result.slices)
    assert result.missing == sum(1 for v in columns["spread"] if not v)


def test_drift_leaves_out_a_column_that_has_nothing_to_follow(tmp_path):
    columns = _table()
    result, plan, _ = _deep(tmp_path, columns)
    assert by_analyzer(plan, "position_drift")["id"].applicability.state == "not_applicable"
    assert by_analyzer(plan, "position_drift")["id"].applicability.reasons == ["nothing_to_follow"]
    assert result.datasets[0].record_count == RECORDS


def test_drift_needs_enough_records_to_cut_in_ten(tmp_path):
    columns = {"a": ["x" if i % 3 else "" for i in range(60)], "b": ["y"] * 60}
    result = scan_csv(tmp_path, "a,b", _rows(columns), **READ)
    plan = forced_plan(result)
    assert by_analyzer(plan, "position_drift")["a"].applicability.reasons == ["too_few_records"]


def test_a_batch_that_crosses_the_end_of_a_slice_is_cut_there(tmp_path):
    accumulator = DriftAccumulator(RECORDS, track=False, limit=0, max_listed=0)
    # A batch of 250 records starting 20 before the end of the first slice.
    start = accumulator.bounds[1] - 20 + 1
    parts = accumulator.segments(start, 250)
    assert parts[0] == (0, 20)
    assert parts[-1][1] == 250
    assert all(before[1] == after[0] for before, after in pairwise(parts))
    for low, high in parts:
        assert len({accumulator.slice_of(start + k) for k in range(low, high)}) == 1


def test_drift_does_not_depend_on_how_the_records_are_cut_in_batches(tmp_path):
    columns = _table()
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    field = next(f for f in result.datasets[0].fields if f.display == "region")
    cells = CellReader(result.config)
    found = []
    for size in (RECORDS, 97, 1):
        route = FieldRoute(cells.for_field(field), None, None)
        route.drift = DriftAccumulator(RECORDS, track=True, limit=4, max_listed=12)
        for first in range(0, RECORDS, size):
            route.strings(columns["region"][first : first + size], first + 1)
        found.append(route.drift.result(field, RECORDS).model_dump(mode="json"))
    assert found[0] == found[1] == found[2]


def test_matrix_counts_the_records_that_lack_a_value_in_two_columns(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    names = ["phone", "ref", "note", "spread"]
    for name in names:
        result = _matrix(outcome, name)
        mine = {p for p, v in enumerate(columns[name]) if not v}
        assert result.missing == len(mine)
        assert result.records == RECORDS
        assert result.columns == len(names)
        for partner in result.listed:
            theirs = {p for p, v in enumerate(columns[partner.display]) if not v}
            assert partner.both == len(mine & theirs)
            assert partner.missing == len(theirs)
            assert partner.field


def test_matrix_ranks_the_columns_that_go_missing_together_first(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    result = _matrix(outcome, "phone")
    assert result.listed[0].display == "ref"
    shares = [p.both / (result.missing + p.missing - p.both) for p in result.listed]
    assert shares == sorted(shares, reverse=True)
    assert result.partners == len(result.listed) == 3
    assert not result.truncated


def test_matrix_lists_at_most_the_partners_asked_for_and_says_so(tmp_path):
    columns = _table()
    deep = DeepSettings.model_validate({"missing": {"max_listed": 1}})
    _, _, outcome = _deep(tmp_path, columns, deep)
    result = _matrix(outcome, "phone")
    assert [p.display for p in result.listed] == ["ref"]
    assert result.partners == 3 and result.truncated


def test_matrix_leaves_out_the_columns_that_miss_nothing_and_the_wide_datasets(tmp_path):
    columns = _table()
    result, plan, _ = _deep(tmp_path / "a", columns)
    members = by_analyzer(plan, "missing_matrix")
    assert set(members) == {"phone", "ref", "note", "spread"}
    wide = DeepSettings.model_validate({"missing": {"max_columns": 3}})
    plan = plan_analyses(result, forced=True, deep=wide)
    refused = by_analyzer(plan, "missing_matrix")
    assert {c.applicability.state for c in refused.values()} == {"not_applicable"}
    assert {tuple(c.applicability.reasons) for c in refused.values()} == {("too_many_columns",)}


def test_matrix_needs_two_columns_that_miss_a_value(tmp_path):
    columns = {"a": ["x" if i % 3 else "" for i in range(200)], "b": ["y"] * 200}
    result = scan_csv(tmp_path, "a,b", _rows(columns), **READ)
    assert by_analyzer(forced_plan(result), "missing_matrix") == {}


def test_matrix_and_drift_read_json_records_with_absent_keys_and_nulls(tmp_path):
    rng = random.Random(3)
    records = []
    for position in range(400):
        item: dict[str, object] = {"id": position}
        if position % 5 and not (50 <= position < 150):
            item["a"] = "x" if rng.random() < 0.5 else "y"
        if position % 4 and not (50 <= position < 150):
            item["b"] = rng.choice((1, 2, 3))
        else:
            item["b"] = None
        records.append(item)
    path = write_text(tmp_path, "data.json", json.dumps(records))
    result = scan(path, config=ScanConfig.model_validate(READ))
    plan = forced_plan(result)
    outcome = run_second_pass(result, path, plan, workers=1)
    a = _matrix(outcome, "a")
    lacks_a = {p for p, item in enumerate(records) if "a" not in item}
    lacks_b = {p for p, item in enumerate(records) if item["b"] is None}
    assert a.missing == len(lacks_a)
    partner = next(p for p in a.listed if p.display == "b")
    assert partner.both == len(lacks_a & lacks_b)
    drift = _drift(outcome, "a")
    expected = Counter(_slice(p, 400) for p in range(400) if "a" in records[p])
    assert [s.values for s in drift.slices] == [expected[i] for i in range(SLICES)]


def test_results_are_the_same_in_workers_and_in_the_process(tmp_path):
    columns = _table()
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result)
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=2)
    for analyzer in ("position_drift", "missing_matrix"):
        mine = {e.display: e.result.model_dump(mode="json") for e in alone.document.analyses if e.analyzer == analyzer}
        theirs = {e.display: e.result.model_dump(mode="json") for e in shared.document.analyses if e.analyzer == analyzer}
        assert mine == theirs and mine


def test_a_source_that_changed_fails_the_check_against_the_scan(tmp_path):
    columns = _table()
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result)
    other = dict(columns)
    other["note"] = ["a"] * RECORDS
    write_text(tmp_path, "data.csv", ",".join(other) + "\n" + "\n".join(_rows(other)) + "\n")
    from tabalyst.source_guard import StaleSource

    with pytest.raises(StaleSource):
        run_second_pass(result, tmp_path / "data.csv", plan, workers=1)


def test_exposure_keeps_a_withheld_column_out_of_both_analyses(tmp_path):
    columns = _table()
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result)
    drift = by_analyzer(plan, "position_drift")["email"]
    assert drift.applicability.reasons == ["sensitive_exposure"]
    assert "email" not in by_analyzer(plan, "missing_matrix")


def test_the_document_validates_against_its_schema_and_the_summary_reads(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    document = json.loads(deep_document(outcome.document))
    jsonschema.validate(document, deep_schema())
    kinds = {a.result.kind for a in outcome.document.analyses if a.result is not None}
    assert {"position_drift", "missing_matrix"} <= kinds
    for found in outcome.document.analyses:
        if found.analyzer in ("position_drift", "missing_matrix"):
            assert result_summary(found.result)


def test_a_result_is_reused_while_the_scan_and_the_settings_do_not_change(tmp_path):
    columns = _table()
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result)
    first = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    again = run_second_pass(
        result, tmp_path / "data.csv", plan, previous=first.document, workers=1
    )
    assert not again.read_source
    assert set(again.reused) >= {
        e.id for e in first.document.analyses if e.analyzer in ("position_drift", "missing_matrix")
    }


def test_both_analyses_stay_out_of_an_automatic_plan(tmp_path):
    columns = _table()
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = plan_analyses(result)
    for analyzer in ("position_drift", "missing_matrix"):
        chosen = [
            c for c in plan.candidates if c.analyzer == analyzer and c.selection.state == "selected"
        ]
        assert chosen == []
        rejected = {c.selection.reason for c in plan.candidates if c.analyzer == analyzer}
        assert "low_utility" in rejected
    assert part_name(DriftAccumulator(RECORDS, track=False, limit=0, max_listed=0)) == "drift"


def test_matrix_and_drift_read_the_rows_of_an_excel_sheet(tmp_path):
    xlsxwriter = pytest.importorskip("xlsxwriter")
    columns = _table()
    names = ["id", "region", "phone", "ref", "note", "spread"]
    path = tmp_path / "data.xlsx"
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Rows")
    for column, name in enumerate(names):
        sheet.write(0, column, name)
    for row in range(RECORDS):
        for column, name in enumerate(names):
            if columns[name][row]:
                sheet.write(row + 1, column, columns[name][row])
    book.close()
    config = ScanConfig.model_validate({**READ, "excel": {"dataset_path": "$.Rows"}})
    result = scan(path, config=config)
    outcome = run_second_pass(result, path, forced_plan(result), workers=1)

    found = _matrix(outcome, "phone")
    mine = {p for p, v in enumerate(columns["phone"]) if not v}
    partner = next(item for item in found.listed if item.display == "ref")
    assert found.missing == len(mine)
    assert partner.both == len(mine & {p for p, v in enumerate(columns["ref"]) if not v})
    drift = _drift(outcome, "phone")
    expected = Counter(_slice(p) for p, v in enumerate(columns["phone"]) if v)
    assert [s.values for s in drift.slices] == [expected[i] for i in range(SLICES)]


def test_the_second_pass_table_names_both_analyses():
    from tabalyst.report_labels import ANALYSIS_LABELS

    assert ANALYSIS_LABELS["position_drift"] and ANALYSIS_LABELS["missing_matrix"]


def test_matrix_adds_up_the_batches_of_a_long_csv_file(tmp_path):
    rng = random.Random(11)
    records = 9_500
    columns = {
        "a": ["" if rng.random() < 0.2 else "x" for _ in range(records)],
        "b": ["" if rng.random() < 0.3 else "y" for _ in range(records)],
        "c": ["" if position % 7 == 0 else "z" for position in range(records)],
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, "a,b,c", _rows(columns), **READ)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result), workers=1)

    found = _matrix(outcome, "a")
    lacks = {name: {p for p, v in enumerate(values) if not v} for name, values in columns.items()}
    assert found.missing == len(lacks["a"])
    for partner in found.listed:
        assert partner.both == len(lacks["a"] & lacks[partner.display])
    drift = _drift(outcome, "a")
    assert [s.records for s in drift.slices] == [
        sum(1 for p in range(records) if _slice(p, records) == i) for i in range(SLICES)
    ]
    assert sum(s.missing for s in drift.slices) == len(lacks["a"])


def test_matrix_adds_up_the_buffers_of_a_long_json_source(tmp_path):
    rng = random.Random(5)
    records = [
        {"id": n, **({} if rng.random() < 0.2 else {"a": "x"}), "b": None if rng.random() < 0.3 else 1}
        for n in range(4_500)
    ]
    path = write_text(tmp_path, "data.json", json.dumps(records))
    result = scan(path, config=ScanConfig.model_validate(READ))
    outcome = run_second_pass(result, path, forced_plan(result), workers=1)

    found = _matrix(outcome, "a")
    lacks_a = {p for p, item in enumerate(records) if "a" not in item}
    lacks_b = {p for p, item in enumerate(records) if item["b"] is None}
    assert found.missing == len(lacks_a)
    assert next(p for p in found.listed if p.display == "b").both == len(lacks_a & lacks_b)


def test_drift_is_left_out_when_the_scan_excluded_records(tmp_path):
    rows = [f"{n},{'' if n % 5 == 0 else 'x'}" for n in range(300)]
    rows.insert(100, "only-one-field")
    result = scan_csv(tmp_path, "id,tag", rows, **READ, errors={"policy": "tolerant"})

    plan = forced_plan(result)

    assert result.scope.records_excluded == 1
    assert by_analyzer(plan, "position_drift")["tag"].applicability.reasons == ["records_excluded"]
    # A single column misses a value, so there is no pair for the matrix.
    assert "tag" not in by_analyzer(plan, "missing_matrix")
