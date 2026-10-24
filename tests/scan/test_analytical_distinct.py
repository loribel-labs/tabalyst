# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The analyzer ``analytical_distinct``: the exact count of the distinct values after NFC, trim and
whitespace, for a field whose Scan stopped counting (Unique ID lot 7, design 20.41)."""

import csv
import json
import unicodedata

import pytest

from tabalyst import scan
from tabalyst.scanner import ScanConfig
from tabalyst.scanner.planner import (
    AnalysisRequest,
    default_registry,
    plan_analyses,
)
from tabalyst.scanner.quality import analytical_distinct
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.analytical import AnalyticalSet
from tabalyst.scanner.secondpass.exactset import ExactPool
from tabalyst.scanner.secondpass.models import AnalyticalDistinctCount, DistinctLimited
from tabalyst.source_guard import StaleSource

ANALYZER = "analytical_distinct"
LOW = {"max_distinct_per_field": 200, "max_samples": 100}


def analytical(value):
    """The analytical text by plain Python (the oracle): NFC, trim, runs of spaces as one."""
    return " ".join(unicodedata.normalize("NFC", value).strip().split())


def write_csv(directory, name, rows, header=("code", "n")):
    path = directory / name
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


def messy_rows(total=3_000, copies=100):
    """Identifiers some of which carry spaces, and ``copies`` that repeat one only under trim."""
    rows = []
    for i in range(total):
        value = f"ID{i}"
        if i % 7 == 0:
            value = f"  {value}  "
        if i % 11 == 0:
            value = value.replace("ID", "I  D")
        rows.append((value, str(i)))
    rows += [(f" ID{i} ", "again") for i in range(1, copies + 1) if i % 7 and i % 11]
    return rows


def scanned(source, **limits):
    config = ScanConfig.model_validate({"limits": limits}) if limits else None
    return scan(source, config=config)


def request(result, deep=None, **options):
    return plan_analyses(
        result,
        requests=[AnalysisRequest(ANALYZER)],
        registry=default_registry().runnable(),
        deep=deep,
        **options,
    )


def candidate(plan, field="column_1"):
    found = [c for c in plan.candidates if c.analyzer == ANALYZER and c.field == field]
    assert len(found) == 1
    return found[0]


def counted(source, result, **options):
    outcome = run_second_pass(result, source, request(result), **options)
    item = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    return outcome, item


def test_the_count_equals_the_scan_that_kept_its_table(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows())
    whole = scanned(source)
    limited = scanned(source, **LOW)
    assert analytical_distinct(limited.datasets[0].fields[0]) is None
    expected = analytical_distinct(whole.datasets[0].fields[0])
    assert expected == len({analytical(code) for code, _ in messy_rows()})

    _, item = counted(source, limited)

    assert item.status == "complete" and item.domain == "analytical"
    assert isinstance(item.result, AnalyticalDistinctCount)
    assert item.result.distinct == expected
    assert item.result.values == len(messy_rows())
    assert item.result.redundant == item.result.values - expected
    assert item.result.unique is False
    assert item.result.stages == ["nfc", "trim", "collapse_whitespace"]


def test_a_unique_analytical_column_says_so(tmp_path):
    rows = [(f" K{i:05d}" if i % 2 else f"K{i:05d} ", str(i)) for i in range(1_000)]
    source = write_csv(tmp_path, "u.csv", rows)
    result = scanned(source, **LOW)

    _, item = counted(source, result)

    assert item.result.unique is True and item.result.distinct == 1_000


def test_two_spellings_of_one_letter_are_one_analytical_value(tmp_path):
    composed, decomposed = "café", "café"
    rows = [(f"{composed if i % 2 else decomposed}{i % 300}", str(i)) for i in range(2_000)]
    source = write_csv(tmp_path, "n.csv", rows)
    limited = scanned(source, **LOW)
    stages = limited.datasets[0].fields[0].normalization.stages
    assert next(s.changed for s in stages if s.stage == "nfc")

    _, item = counted(source, limited)

    assert item.result.distinct == 300
    assert item.result.distinct == analytical_distinct(scanned(source).datasets[0].fields[0])


def test_the_analyzer_is_satisfied_by_a_scan_that_kept_its_table(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows())

    chosen = candidate(request(scanned(source)))

    assert chosen.selection.state == "already_satisfied"
    assert chosen.selection.reason == "distinct_exact"
    assert chosen.selection.satisfied_by == "datasets/rows/fields/column_1/values/cardinality"


def test_no_stage_that_changed_a_value_leaves_the_original_count_to_do(tmp_path):
    rows = [(f"K{i:05d}", str(i)) for i in range(1_000)]
    source = write_csv(tmp_path, "c.csv", rows)

    chosen = candidate(request(scanned(source, **LOW)))

    assert chosen.selection.state == "rejected"
    assert chosen.applicability.reasons == ["stages_unchanged"]


def test_the_analyzer_is_never_chosen_by_itself(tmp_path):
    result = scanned(write_csv(tmp_path, "m.csv", messy_rows()), **LOW)

    automatic = plan_analyses(result, registry=default_registry().runnable())
    forced = plan_analyses(result, forced=True, registry=default_registry().runnable())

    assert candidate(automatic).selection.reason == "low_utility"
    assert candidate(request(result)).selection.reason == "requested"
    assert candidate(forced).selection.reason == "forced"


def test_the_plan_charges_a_set_of_its_own_beside_the_original_one(tmp_path):
    result = scanned(write_csv(tmp_path, "m.csv", messy_rows()), **LOW)
    forced = plan_analyses(result, forced=True, registry=default_registry().runnable())

    keys = {
        analyzer: {
            state.key
            for found in forced.candidates
            if found.analyzer == analyzer and found.field == "column_1" and found.costs
            for state in found.costs.states
            if state.key.startswith("exact_set:")
        }
        for analyzer in ("exact_distinct", ANALYZER)
    }
    assert len(keys["exact_distinct"]) == len(keys[ANALYZER]) == 1
    assert keys["exact_distinct"] != keys[ANALYZER]


def test_the_original_and_the_analytical_counts_run_side_by_side(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows())
    result = scanned(source, **LOW)
    plan = plan_analyses(result, forced=True, registry=default_registry().runnable())

    outcome = run_second_pass(result, source, plan)

    by_id = {
        a.analyzer: a
        for a in outcome.document.analyses
        if a.analyzer in ("exact_distinct", ANALYZER) and a.field == "column_1"
    }
    rows = messy_rows()
    assert by_id["exact_distinct"].result.distinct == len({code for code, _ in rows})
    assert by_id[ANALYZER].result.distinct == len({analytical(code) for code, _ in rows})
    assert by_id[ANALYZER].result.distinct < by_id["exact_distinct"].result.distinct


def test_a_json_integer_is_never_the_same_value_as_its_text(tmp_path):
    records = [{"k": f" {i} " if i % 2 else str(i)} for i in range(400)]
    records += [{"k": i} for i in range(400)]
    source = tmp_path / "k.json"
    source.write_text(json.dumps(records), encoding="utf-8")
    limited = scanned(source, **LOW)
    result = limited.datasets[0].fields[0]
    assert analytical_distinct(result) is None

    plan = plan_analyses(
        limited,
        requests=[AnalysisRequest(ANALYZER)],
        registry=default_registry().runnable(),
    )
    outcome = run_second_pass(limited, source, plan)

    item = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    whole = analytical_distinct(scanned(source).datasets[0].fields[0])
    assert whole == 800
    assert item.result.distinct == whole


def test_the_result_does_not_depend_on_the_number_of_workers(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows(total=6_000))
    result = scanned(source, **LOW)

    one = counted(source, result, workers=1)[1].result
    several = counted(source, result, workers=4)[1].result

    assert one == several


def test_a_memory_ceiling_leaves_a_bound_never_a_count(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows(total=4_000))
    result = scanned(source, **LOW)
    plan = request(result)
    chosen = candidate(plan)
    assert chosen.costs is not None
    states = [
        state.model_copy(update={"memory": state.memory.model_copy(update={"max": 20_000})})
        if state.key.startswith("exact_set:")
        else state
        for state in chosen.costs.states
    ]
    tight = chosen.model_copy(update={"costs": chosen.costs.model_copy(update={"states": states})})
    # The pool is the one of the exact sets of the run: leave out those of other analyses.
    kept = [
        tight if c.id == chosen.id else c
        for c in plan.candidates
        if c.analyzer not in ("residual_values", "duplicates_report", "exact_distinct")
    ]
    plan = plan.model_copy(update={"candidates": kept})

    outcome = run_second_pass(result, source, plan)

    item = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    assert item.status == "limited" and item.reason == "memory_budget"
    assert isinstance(item.result, DistinctLimited)
    assert item.result.lower_bound <= len({analytical(code) for code, _ in messy_rows(total=4_000)})


def test_the_stored_result_is_reused_without_reading_the_source_again(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows())
    result = scanned(source, **LOW)
    plan = request(result)
    first = run_second_pass(result, source, plan)

    again = run_second_pass(result, source, plan, previous=first.document)

    assert again.read_source is False and again.reused == first.executed


def test_a_source_changed_since_the_scan_stops_the_pass(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows())
    result = scanned(source, **LOW)
    plan = request(result)
    source.write_bytes(source.read_bytes().replace(b"ID5,", b"ID6,", 1))

    with pytest.raises(StaleSource):
        run_second_pass(result, source, plan)


def test_a_scan_that_disagrees_with_the_reading_fails_the_analysis_alone(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows())
    result = scanned(source, **LOW)
    field = result.datasets[0].fields[0]
    stages = [
        stage.model_copy(update={"changed": 0}) if stage.stage == "trim" else stage
        for stage in field.normalization.stages
    ]
    forged = field.model_copy(
        update={"normalization": field.normalization.model_copy(update={"stages": stages})}
    )
    dataset = result.datasets[0]
    result = result.model_copy(
        update={
            "datasets": [dataset.model_copy(update={"fields": [forged, *dataset.fields[1:]]})]
        }
    )

    _, item = counted(source, result)

    assert item.status == "failed" and item.reason == "scan_mismatch"
    assert item.result is None


def test_an_analytical_set_adds_each_text_once_whatever_the_raw_spellings():
    found = AnalyticalSet(ExactPool(1 << 30))

    found.add_texts([" a", "a ", "b"], ["a", "a", "b"], [2, 3, 1])

    assert found.distinct() == 2 and found.values == 6 and found.changed == 5


def test_a_jsonl_source_counts_its_strings_after_trim(tmp_path):
    records = [{"k": f" ID{i % 700} " if i % 3 else f"ID{i % 700}"} for i in range(2_000)]
    source = tmp_path / "k.jsonl"
    source.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    limited = scanned(source, **LOW)
    assert analytical_distinct(limited.datasets[0].fields[0]) is None
    plan = plan_analyses(
        limited,
        requests=[AnalysisRequest(ANALYZER)],
        registry=default_registry().runnable(),
    )

    outcome = run_second_pass(limited, source, plan)

    item = next(a for a in outcome.document.analyses if a.analyzer == ANALYZER)
    assert item.status == "complete" and item.result.distinct == 700


def test_counters_of_the_scan_that_exceed_the_reading_fail_the_analysis(tmp_path):
    source = write_csv(tmp_path, "m.csv", messy_rows())
    result = scanned(source, **LOW)
    field = result.datasets[0].fields[0]
    stages = [
        stage.model_copy(update={"changed": field.strings.content})
        if stage.stage == "trim"
        else stage
        for stage in field.normalization.stages
    ]
    forged = field.model_copy(
        update={"normalization": field.normalization.model_copy(update={"stages": stages})}
    )
    dataset = result.datasets[0]
    result = result.model_copy(
        update={"datasets": [dataset.model_copy(update={"fields": [forged, *dataset.fields[1:]]})]}
    )

    _, item = counted(source, result)

    assert item.status == "failed" and item.reason == "scan_mismatch"
