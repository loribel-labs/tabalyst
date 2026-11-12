# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The combinations of missing values of a dataset (design 20.44).

The oracles are built from the rows the generator wrote, never from the
accumulator: a record lacks a value for a column when its cell is empty, and its
combination is the set of the columns of the matrix where it does.
"""

from __future__ import annotations

import json
import random
from collections import Counter

import jsonschema
import pytest
from planner_helpers import by_analyzer, scan_csv
from scan_helpers import write_text
from second_pass_helpers import entry, forced_plan

from tabalyst.config import DeepSettings
from tabalyst.report_deep import result_summary
from tabalyst.report_labels import ANALYSIS_LABELS
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner import AnalysisRequest, plan_analyses
from tabalyst.scanner.secondpass import deep_document, run_second_pass
from tabalyst.scanner.secondpass.matrix import PatternTable
from tabalyst.scanner.secondpass.models import MissingPatternsResult
from tabalyst.scanner.secondpass.schema import deep_schema

RECORDS = 1_003
# Few samples: the Scan does not hold every distinct value, so the source is read.
READ = {"limits": {"max_samples": 50}}
# The columns of the table that lack a value somewhere and are not withheld.
MEMBERS = ["phone", "ref", "note", "spread"]


def _table(records: int = RECORDS, seed: int = 44) -> dict[str, list[str]]:
    """``phone`` and ``ref`` go missing as a block of the file and now and then on
    their own, ``note`` at random, ``spread`` every seventh record, ``id`` never.
    ``email`` is sensitive and masked by default."""
    rng = random.Random(seed)
    columns: dict[str, list[str]] = {
        "id": [], "phone": [], "ref": [], "email": [], "note": [], "spread": []
    }
    for position in range(records):
        block = 100 <= position < 220
        columns["id"].append(str(position + 1))
        columns["phone"].append("" if block or rng.random() < 0.02 else f"555-{position:04d}")
        columns["ref"].append("" if block or rng.random() < 0.03 else f"R{position}")
        columns["email"].append("" if rng.random() < 0.1 else f"u{position}@x.test")
        columns["note"].append("" if rng.random() < 0.25 else rng.choice(("a", "b", "c")))
        columns["spread"].append("" if position % 7 == 0 else str(rng.randint(0, 30)))
    return columns


def _rows(columns: dict[str, list[str]]) -> list[str]:
    return [",".join(values) for values in zip(*columns.values(), strict=True)]


def _oracle(columns: dict[str, list[str]], members: list[str]) -> Counter[frozenset[str]]:
    records = len(next(iter(columns.values())))
    return Counter(
        frozenset(name for name in members if not columns[name][position])
        for position in range(records)
    )


def _deep(tmp_path, columns, deep: DeepSettings | None = None, workers: int = 1):
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = forced_plan(result, deep)
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, settings=deep, workers=workers)
    return result, plan, outcome


def _patterns(outcome) -> MissingPatternsResult:
    found = entry(outcome, "missing_patterns", "$")
    assert found.status == "complete", (found.reason, found.detail)
    assert isinstance(found.result, MissingPatternsResult)
    return found.result


def _by_names(result: MissingPatternsResult) -> dict[frozenset[str], int]:
    names = {column.field: column.display for column in result.columns}
    return {
        frozenset(names[field] for field in pattern.columns): pattern.count
        for pattern in result.listed
    }


def test_each_record_is_counted_once_under_its_exact_set_of_missing_columns(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    result = _patterns(outcome)
    expected = _oracle(columns, MEMBERS)

    assert [column.display for column in result.columns] == MEMBERS
    assert [column.missing for column in result.columns] == [
        sum(1 for value in columns[name] if not value) for name in MEMBERS
    ]
    assert result.records == RECORDS
    assert result.complete_records == expected.pop(frozenset())
    assert result.complete and result.untracked == 0
    assert result.distinct == len(expected)
    assert _by_names(result) == dict(expected)
    assert result.other_patterns == result.other_records == 0


def test_the_most_frequent_combinations_come_first_then_the_smaller_ones(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    listed = _patterns(outcome).listed
    keys = [(-pattern.count, len(pattern.columns)) for pattern in listed]
    assert keys == sorted(keys)
    names = {column.field: column.display for column in _patterns(outcome).columns}
    # The block of the file is the first combination of two columns or more.
    first_pair = next(pattern for pattern in listed if len(pattern.columns) > 1)
    assert {names[field] for field in first_pair.columns} == {"phone", "ref"}
    # Field ids in document order.
    order = {column.field: index for index, column in enumerate(_patterns(outcome).columns)}
    for pattern in listed:
        assert [order[field] for field in pattern.columns] == sorted(
            order[field] for field in pattern.columns
        )


def test_a_short_listing_sums_up_the_combinations_it_leaves_out(tmp_path):
    columns = _table()
    deep = DeepSettings.model_validate({"missing": {"max_patterns_listed": 3}})
    _, _, outcome = _deep(tmp_path, columns, deep)
    result = _patterns(outcome)
    expected = _oracle(columns, MEMBERS)
    expected.pop(frozenset())

    assert len(result.listed) == 3
    assert result.other_patterns == len(expected) - 3
    assert result.other_records == sum(expected.values()) - sum(p.count for p in result.listed)
    assert result.complete


def test_combinations_met_once_the_table_is_full_are_summed_as_untracked(tmp_path):
    columns = _table()
    deep = DeepSettings.model_validate({"missing": {"max_patterns": 2}})
    _, _, outcome = _deep(tmp_path, columns, deep)
    result = _patterns(outcome)

    assert not result.complete and result.distinct == 2
    assert result.untracked > 0
    total = result.complete_records + sum(p.count for p in result.listed)
    assert total + result.other_records + result.untracked == RECORDS
    # The two tracked are the first two met in the file, each counted exactly.
    expected = _oracle(columns, MEMBERS)
    first: list[frozenset[str]] = []
    for position in range(RECORDS):
        key = frozenset(name for name in MEMBERS if not columns[name][position])
        if key and key not in first:
            first.append(key)
    assert set(_by_names(result)) == set(first[:2])
    for key, count in _by_names(result).items():
        assert count == expected[key]


def test_the_table_does_not_depend_on_how_the_records_are_cut_in_batches():
    rng = random.Random(7)
    flags = [[rng.random() > 0.3 for _ in range(500)] for _ in range(4)]
    whole = PatternTable(5)
    whole.add_flags(list(enumerate(flags)), 500)
    cut = PatternTable(5)
    for start in range(0, 500, 37):
        part = [(column, values[start : start + 37]) for column, values in enumerate(flags)]
        cut.add_flags(part, len(part[0][1]))
    one = PatternTable(5)
    for position in range(500):
        pattern = sum(1 << column for column in range(4) if not flags[column][position])
        one.add(pattern, 1)
    for table in (cut, one):
        assert list(table.counts.items()) == list(whole.counts.items())
        assert (table.complete, table.untracked) == (whole.complete, whole.untracked)


def test_the_pairs_of_the_matrix_follow_from_the_combinations(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    combinations = _by_names(_patterns(outcome))
    found = entry(outcome, "missing_matrix", "phone").result
    for partner in found.listed:
        assert partner.both == sum(
            count
            for key, count in combinations.items()
            if {"phone", partner.display} <= key
        )


def test_the_combinations_alone_read_the_source_without_the_matrix(tmp_path):
    columns = _table()
    tmp_path.mkdir(parents=True, exist_ok=True)
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    plan = plan_analyses(
        result, requests=[AnalysisRequest("missing_patterns")], automatic=False
    )
    selected = [c for c in plan.candidates if c.selection.state == "selected"]
    assert [c.analyzer for c in selected] == ["missing_patterns"]
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    assert outcome.read_source
    assert _by_names(_patterns(outcome)) == {
        key: count for key, count in _oracle(columns, MEMBERS).items() if key
    }


def test_the_plan_names_one_candidate_for_the_dataset_and_leaves_wide_ones_out(tmp_path):
    columns = _table()
    result, plan, _ = _deep(tmp_path, columns)
    candidates = by_analyzer(plan, "missing_patterns")
    assert list(candidates) == ["$"]
    candidate = candidates["$"]
    assert candidate.id == "missing_patterns:rows:$"
    assert candidate.method == "pattern_table"
    assert candidate.parameters == {"columns": 4, "max_patterns": 1_000, "max_listed": 200}
    wide = DeepSettings.model_validate({"missing": {"max_columns": 3}})
    refused = by_analyzer(plan_analyses(result, forced=True, deep=wide), "missing_patterns")["$"]
    assert refused.applicability.state == "not_applicable"
    assert refused.applicability.reasons == ["too_many_columns"]


def test_a_dataset_needs_two_columns_that_miss_a_value(tmp_path):
    columns = {"a": ["x" if i % 3 else "" for i in range(200)], "b": ["y"] * 200}
    result = scan_csv(tmp_path, "a,b", _rows(columns), **READ)
    assert by_analyzer(forced_plan(result), "missing_patterns") == {}


def test_the_combinations_stay_out_of_an_automatic_plan(tmp_path):
    columns = _table()
    result = scan_csv(tmp_path, ",".join(columns), _rows(columns), **READ)
    candidate = by_analyzer(plan_analyses(result), "missing_patterns")["$"]
    assert candidate.selection.state != "selected"
    assert candidate.selection.reason == "low_utility"


def test_a_withheld_column_is_in_no_combination(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    result = _patterns(outcome)
    assert "email" not in [column.display for column in result.columns]


def test_json_records_lack_a_value_by_an_absent_key_or_a_null(tmp_path):
    rng = random.Random(3)
    records = []
    for position in range(4_500):
        item: dict[str, object] = {"id": position}
        if position % 5 and not 50 <= position < 150:
            item["a"] = rng.choice(("x", "y"))
        item["b"] = None if position % 4 == 0 or 50 <= position < 150 else rng.choice((1, 2))
        if rng.random() < 0.8:
            item["c"] = "z"
        records.append(item)
    path = write_text(tmp_path, "data.json", json.dumps(records))
    result = scan(path, config=ScanConfig.model_validate(READ))
    outcome = run_second_pass(result, path, forced_plan(result), workers=1)
    found = _patterns(outcome)

    def lacks(item: dict[str, object], name: str) -> bool:
        return item.get(name) is None

    expected = Counter(
        frozenset(name for name in ("a", "b", "c") if lacks(item, name)) for item in records
    )
    assert found.complete_records == expected.pop(frozenset())
    assert _by_names(found) == dict(expected)
    # The keys of the records are counted by another analysis of the same field `$`.
    assert entry(outcome, "structure_variants", "$").status == "complete"


def test_the_combinations_of_an_excel_sheet_are_counted(tmp_path):
    xlsxwriter = pytest.importorskip("xlsxwriter")
    columns = _table()
    names = ["id", "phone", "ref", "note", "spread"]
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
    expected = _oracle(columns, MEMBERS)
    expected.pop(frozenset())
    assert _by_names(_patterns(outcome)) == dict(expected)


def test_a_long_csv_file_adds_up_its_batches(tmp_path):
    rng = random.Random(11)
    records = 9_500
    columns = {
        "a": ["" if rng.random() < 0.2 else "x" for _ in range(records)],
        "b": ["" if rng.random() < 0.3 else "y" for _ in range(records)],
        "c": ["" if position % 7 == 0 else "z" for position in range(records)],
    }
    _, _, outcome = _deep(tmp_path, columns)
    expected = _oracle(columns, ["a", "b", "c"])
    result = _patterns(outcome)
    assert result.complete_records == expected.pop(frozenset())
    assert _by_names(result) == dict(expected)


def test_workers_give_the_same_combinations_as_one_process(tmp_path):
    columns = _table()
    _, _, alone = _deep(tmp_path / "one", columns, workers=1)
    _, _, shared = _deep(tmp_path / "two", columns, workers=2)
    assert _patterns(alone).model_dump(mode="json") == _patterns(shared).model_dump(mode="json")


def test_a_result_is_reused_while_the_scan_and_the_settings_do_not_change(tmp_path):
    columns = _table()
    result, plan, first = _deep(tmp_path, columns)
    again = run_second_pass(result, tmp_path / "data.csv", plan, previous=first.document, workers=1)
    found = entry(first, "missing_patterns", "$")
    assert found.id in again.reused


def test_the_document_validates_and_the_report_names_and_sums_it_up(tmp_path):
    columns = _table()
    _, _, outcome = _deep(tmp_path, columns)
    document = json.loads(deep_document(outcome.document))
    jsonschema.validate(document, deep_schema())
    assert document["format_revision"] == 5
    summary = result_summary(_patterns(outcome))
    assert summary is not None and "combinations" in summary[0]
    assert ANALYSIS_LABELS["missing_patterns"]
