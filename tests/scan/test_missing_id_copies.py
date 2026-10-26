# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The analyzer ``missing_id_copies``: the copies of the rows that have no ID, per identifier column
(Unique ID lot 10, design 20.43).

It reads the file on its own with the light mode of the engine of Dedup, keeps a table of the rows
that lack a value only, and is chosen by the planner beside an exact count of the copies and of the
distinct IDs of the column.
"""

import csv
import json

import pytest

from tabalyst import scan
from tabalyst.config import CopySettings, DeepSettings
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.planner import (
    AnalysisRequest,
    default_budgets,
    default_registry,
    plan_analyses,
)
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.document import analysis_key
from tabalyst.scanner.secondpass.models import MissingIdCopiesResult
from tabalyst.source_guard import StaleSource

ANALYZER = "missing_id_copies"
COPIES = "duplicate_rows_count"


def write_csv(directory, name, rows, header):
    path = directory / name
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def rows_with_blanks(total=3_000, blank=60, blank_copies=20, copies=100):
    """``total`` rows with their own ID, ``blank`` without one (``blank_copies`` of them repeated)
    and ``copies`` repeats of rows that have one."""
    base = [(f"K{i:06d}", f"a{i}", f"b{i}") for i in range(total)]
    empty = [("", f"n{i}", f"b{i}") for i in range(blank)]
    return base + empty + [empty[i % blank] for i in range(blank_copies)] + base[:copies]


def scanned(source, **limits):
    config = ScanConfig.model_validate({"limits": limits}) if limits else None
    return scan(source, config=config)


def planned(result, **options):
    return plan_analyses(result, registry=default_registry().runnable(), **options)


def candidate(plan, analyzer=ANALYZER):
    found = [c for c in plan.candidates if c.analyzer == analyzer]
    assert len(found) == 1
    return found[0]


def counted(source, result=None, **options):
    """The result of the count, run through the second pass."""
    result = scanned(source) if result is None else result
    plan = planned(result, requests=[AnalysisRequest(ANALYZER)], **options)
    outcome = run_second_pass(result, source, plan, settings=options.get("deep"))
    entry = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    return entry, outcome


# ------------------------------------------------------------------ assess and plan


def test_a_file_whose_identifier_lacks_a_value_has_a_candidate(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(), ["id", "a", "b"])

    chosen = candidate(planned(scanned(source)))

    assert chosen.applicability.state == "applicable"
    assert chosen.method == "extra_copies_without_id"
    assert json.loads(chosen.parameters["columns"]) == [["column_1", 1]]
    assert chosen.parameters["max_rows"] == DeepSettings().copies.max_rows


def test_a_file_without_a_missing_id_has_nothing_to_count(tmp_path):
    rows = [(f"K{i}", f"a{i % 5}", "b") for i in range(500)]
    source = write_csv(tmp_path, "t.csv", rows + rows[:50], ["id", "a", "b"])

    chosen = candidate(planned(scanned(source)))

    assert chosen.applicability.reasons == ["no_missing_id_candidate"]


def test_it_is_chosen_by_itself_beside_an_exact_count_and_a_known_distinct_count(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(), ["id", "a", "b"])
    result = scanned(source)
    assert result.datasets[0].records.duplicates.count.status == "complete"

    chosen = candidate(planned(result))

    assert chosen.selection.state == "selected"
    assert chosen.selection.reason == "automatic"
    assert chosen.utility.reasons == ["identifier_missing_copies"]


def test_it_follows_the_count_of_the_copies_chosen_for_the_same_file(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(total=4_000), ["id", "a", "b"])
    result = scanned(source, max_tracked_records=1_000)
    assert result.datasets[0].records.duplicates.count.status == "limited"

    plan = planned(result)

    assert candidate(plan, COPIES).selection.state == "selected"
    assert candidate(plan).selection.state == "selected"


def test_it_waits_for_an_exact_total_of_the_copies(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(total=4_000), ["id", "a", "b"])
    result = scanned(source, max_tracked_records=1_000)
    # The count of the copies is asked to stay out by a table that cannot fit the automatic memory.
    budgets = default_budgets().model_copy(update={"automatic_memory_bytes": 1 << 20})

    plan = planned(result, budgets=budgets)

    assert candidate(plan, COPIES).selection.reason == "budget"
    assert (candidate(plan).selection.state, candidate(plan).selection.reason) == (
        "rejected",
        "copies_unknown",
    )


def test_a_valid_dedup_proof_gives_the_total_the_count_needs(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(total=4_000), ["id", "a", "b"])
    result = scanned(source, max_tracked_records=1_000)

    plan = planned(result, proved_copies=frozenset({"rows"}))

    assert candidate(plan, COPIES).selection.reason == "copies_proved"
    assert candidate(plan).selection.state == "selected"


def test_without_any_count_of_the_copies_there_is_nothing_to_subtract_from(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(), ["id", "a", "b"])
    config = ScanConfig.model_validate({"records": {"duplicates": False}})
    result = scan(source, config=config)
    assert result.datasets[0].records.duplicates.count.status == "disabled"

    chosen = candidate(planned(result))

    assert chosen.applicability.reasons == ["duplicates_disabled"]


def test_the_table_estimated_is_that_of_the_rows_without_an_id_not_of_the_file(tmp_path):
    few = write_csv(tmp_path, "few.csv", rows_with_blanks(total=20_000, blank=30, blank_copies=5, copies=0), ["id", "a", "b"])
    many = write_csv(tmp_path, "many.csv", rows_with_blanks(total=20_000, blank=8_000, blank_copies=0, copies=0), ["id", "a", "b"])
    budgets = default_budgets()

    small = candidate(planned(scanned(few), budgets=budgets)).costs.memory.max
    large = candidate(planned(scanned(many), budgets=budgets)).costs.memory.max

    assert small < large


def test_a_second_run_reads_nothing_when_the_result_is_stored(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(), ["id", "a", "b"])
    result = scanned(source)
    plan = planned(result, requests=[AnalysisRequest(ANALYZER)])

    first = run_second_pass(result, source, plan)
    second = run_second_pass(result, source, plan, previous=first.document)

    assert first.read_source is True
    assert second.read_source is False and second.reused


def test_the_columns_and_the_version_are_part_of_the_key(tmp_path):
    from tabalyst.dedup.calculation import MISSING_CALCULATION_VERSION

    source = write_csv(tmp_path, "t.csv", rows_with_blanks(), ["id", "a", "b"])
    plan = planned(scanned(source))
    chosen = candidate(plan)
    other = chosen.model_copy(update={"parameters": {**chosen.parameters, "columns": "[]"}})
    older = chosen.model_copy(update={"analyzer_version": MISSING_CALCULATION_VERSION + 1})

    assert chosen.analyzer_version == MISSING_CALCULATION_VERSION
    assert len({analysis_key(plan.base, c) for c in (chosen, other, older)}) == 3


# --------------------------------------------------------------------------- execution


def test_the_count_equals_the_copies_among_the_rows_without_an_id(tmp_path):
    rows = rows_with_blanks(blank=60, blank_copies=20, copies=100)
    source = write_csv(tmp_path, "t.csv", rows, ["id", "a", "b"])

    entry, outcome = counted(source)

    result = entry.result
    assert isinstance(result, MissingIdCopiesResult)
    assert entry.status == "complete" and result.accuracy == "exact"
    (column,) = result.columns
    assert column.field == "column_1"
    assert (column.rows_without_id, column.distinct_rows_without_id) == (80, 60)
    assert column.extra_copies_without_id == 20
    assert result.records == len(rows)
    assert result.source_sha256 == scanned(source).source.sha256
    assert outcome.document.run.source_verified is True


def test_one_reading_counts_every_identifier_column_that_lacks_a_value(tmp_path):
    rows = [
        (f"K{i}" if i % 10 else "", f"P{i}" if i % 7 else "", f"v{i % 3}") for i in range(300)
    ]
    rows += rows[:40]
    source = write_csv(tmp_path, "t.csv", rows, ["customer_id", "policy_id", "kind"])
    result = scanned(source)
    plan = planned(result, requests=[AnalysisRequest(ANALYZER)])

    chosen = candidate(plan)
    outcome = run_second_pass(result, source, plan)

    names = [name for name, _ in json.loads(chosen.parameters["columns"])]
    entry = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    assert [c.field for c in entry.result.columns] == names
    assert len(names) >= 1


def test_a_ceiling_leaves_a_lower_bound_that_is_reused_at_the_same_ceiling(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(total=500, blank=300), ["id", "a", "b"])
    result = scanned(source)
    deep = DeepSettings(copies=CopySettings(max_rows=600))
    plan = planned(result, requests=[AnalysisRequest(ANALYZER)], deep=deep)

    first = run_second_pass(result, source, plan, settings=deep)
    second = run_second_pass(result, source, plan, settings=deep, previous=first.document)

    stopped = next(a for a in first.document.analyses if a.analyzer == ANALYZER)
    assert (stopped.status, stopped.reason) == ("limited", "row_limit")
    assert stopped.result.accuracy == "lower_bound" and stopped.result.source_sha256 is None
    assert second.read_source is False
    assert next(a for a in second.document.analyses if a.analyzer == ANALYZER) == stopped


def test_a_count_that_contradicts_the_scan_fails_alone(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(), ["id", "a", "b"])
    result = scanned(source)
    # The Scan says a blank more than the file holds.
    field = result.datasets[0].fields[0]
    forged = field.model_copy(
        update={"values": field.values.model_copy(update={"count": field.values.count - 1})}
    )
    dataset = result.datasets[0].model_copy(update={"fields": [forged, *result.datasets[0].fields[1:]]})
    tampered = result.model_copy(update={"datasets": [dataset]})
    plan = planned(tampered, requests=[AnalysisRequest(ANALYZER)])

    outcome = run_second_pass(tampered, source, plan)

    entry = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    assert (entry.status, entry.reason) == ("failed", "scan_mismatch")


def test_a_file_that_is_not_the_one_the_scan_read_is_refused(tmp_path):
    source = write_csv(tmp_path, "t.csv", rows_with_blanks(), ["id", "a", "b"])
    result = scanned(source)
    plan = planned(result, requests=[AnalysisRequest(ANALYZER)])
    with source.open("a", encoding="utf-8", newline="") as stream:
        stream.write("K999999,a,b\r\n")

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)
