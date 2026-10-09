# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the exact distinct count and the exact frequencies (lot 7b):
D06, D07 and the executor half of D08, with the original domain of JSON values
and the frequencies against an oracle."""

import json
import tracemalloc
from collections import Counter

import pytest
from planner_helpers import by_analyzer, scan_csv
from scan_helpers import write_text
from second_pass_helpers import deep_csv, entry, forced_plan

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import CardinalityLimited
from tabalyst.scanner.planner import default_registry
from tabalyst.scanner.planner.costmodel import EXACT_SET_STATE_PREFIX
from tabalyst.scanner.secondpass import EXECUTABLE, run_second_pass
from tabalyst.scanner.secondpass.exactset import ExactPool, ExactSet

LIMITED = {"max_distinct_per_field": 50}


def _distinct(outcome, display):
    return entry(outcome, "exact_distinct", display)


def _field(result, display):
    return next(f for d in result.datasets for f in d.fields if f.display == display)


def _plan_with_grant(plan, grant):
    """The plan with every exact set given ``grant`` bytes, as a plan made
    for a smaller budget (or from a model that under-charged) would."""
    candidates = []
    for candidate in plan.candidates:
        if candidate.analyzer == "exact_distinct" and candidate.costs is not None:
            states = [
                state.model_copy(
                    update={"memory": state.memory.model_copy(update={"max": grant})}
                )
                if state.key.startswith(EXACT_SET_STATE_PREFIX)
                else state
                for state in candidate.costs.states
            ]
            candidate = candidate.model_copy(
                update={"costs": candidate.costs.model_copy(update={"states": states})}
            )
        candidates.append(candidate)
    return plan.model_copy(update={"candidates": candidates})


# D06 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7b")
def test_D06_ids_of_8_10_and_12_characters_with_leading_zeros_count_their_raw_values(tmp_path):
    rows = []
    for n in range(900):
        rows.append(
            f"{n % 700:08d},K{n % 650:09X},{'ab' if n % 2 else 'AB'}{n % 800:010d}"
        )
    result, _, outcome = deep_csv(tmp_path, "digits,hex,mixed", rows, limits=LIMITED)

    for column, display in enumerate(("digits", "hex", "mixed")):
        raw = [row.split(",")[column] for row in rows]
        assert isinstance(_field(result, display).values.cardinality, CardinalityLimited)
        found = _distinct(outcome, display)
        assert found.status == "complete" and found.domain == "original"
        assert found.result.kind == "distinct" and found.result.accuracy == "exact"
        assert found.result.distinct == len(set(raw))
        assert found.result.values == len(raw)
        assert found.result.redundant == len(raw) - len(set(raw))
        assert found.result.unique is False


@pytest.mark.scan_json_lot("7b")
def test_D06_a_leading_zero_a_case_or_a_blank_makes_another_value(tmp_path):
    base = [f"{n:06d}" for n in range(200)]
    rows = [*base, "7", "007", "0007", "ab", "AB", "Ab", "x", "x ", " x", "x  y", "x y"]
    result, _, outcome = deep_csv(tmp_path, "v", rows, limits=LIMITED)

    found = _distinct(outcome, "v").result
    # Surrounding blanks stay in the original domain; the analytical text of
    # "x ", " x" and "x" is the same, the original values are three.
    assert found.distinct == len(set(rows))
    assert found.values == len(rows)
    assert isinstance(_field(result, "v").values.cardinality, CardinalityLimited)


@pytest.mark.scan_json_lot("7b")
def test_D06_unique_is_true_only_when_distinct_equals_the_values(tmp_path):
    rows = [f"U{n:07d}" for n in range(400)]
    _, _, outcome = deep_csv(tmp_path, "id", rows, limits=LIMITED)

    found = _distinct(outcome, "id").result
    assert (found.values, found.distinct, found.redundant, found.unique) == (400, 400, 0, True)


@pytest.mark.scan_json_lot("7b")
def test_D06_empty_blank_and_marker_cells_are_not_values(tmp_path):
    cells = [f"U{n:05d}" if n % 5 else ("" if n % 10 else "N/A") for n in range(500)]
    cells += [" ", "   "]
    result, _, outcome = deep_csv(
        tmp_path,
        "id,k",
        [f"{cell},k" for cell in cells],
        limits=LIMITED,
        values={"null_markers": ["N/A"]},
    )

    contents = [cell for cell in cells if cell.strip() and cell != "N/A"]
    found = _distinct(outcome, "id").result
    assert found.values == len(contents) == _field(result, "id").values.count
    assert found.distinct == len(set(contents))


# D07 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7b")
def test_D07_a_late_value_outside_the_compact_key_is_counted_not_merged(tmp_path):
    late = [
        "é-1",  # not ASCII
        "١٢٣",  # Arabic-Indic digits: digits for Python, not the digits 123
        "123",  # the same digits as the early ones, once
        " 123",  # blanks around digits
        "1" * 20,  # more digits than a compact key holds
        "😀",  # outside the BMP
        "a" + "\t" + "b",
        "Z" * 60,
    ]
    rows = [f"{n:010d}" for n in range(500)] + late + late
    result, _, outcome = deep_csv(tmp_path, "id", rows, limits=LIMITED)

    found = _distinct(outcome, "id")
    assert found.status == "complete"
    assert found.result.distinct == len(set(rows)) and found.result.values == len(rows)
    assert isinstance(_field(result, "id").values.cardinality, CardinalityLimited)


@pytest.mark.scan_json_lot("7b")
def test_D07_a_raw_value_longer_than_its_analytical_text_stays_exact_within_the_margin(tmp_path):
    padded = [" " * 20 + f"K{n:05d}" + " " * 20 for n in range(120)]
    rows = [f"K{n:05d}" for n in range(300)] + padded
    result, _, outcome = deep_csv(tmp_path, "id,k", [f"{row},k" for row in rows], limits=LIMITED)

    found = _distinct(outcome, "id")
    assert found.status == "complete"
    assert found.result.distinct == len(set(rows)) == 420
    # The Scan's lengths are analytical: the plan could not see the padding.
    assert _field(result, "id").string_lengths.value.max_length <= 6


@pytest.mark.scan_json_lot("7b")
def test_D07_padding_the_plan_could_not_see_is_a_limit_never_an_undercount(tmp_path):
    padded = [" " * 450 + f"K{n:05d}" + " " * 450 for n in range(600)]
    rows = [f"K{n:05d}" for n in range(300)] + padded
    _, _, outcome = deep_csv(tmp_path, "id,k", [f"{row},k" for row in rows], limits=LIMITED)

    found = _distinct(outcome, "id")
    assert found.status == "limited" and found.reason == "memory_budget"
    assert found.result.kind == "distinct_limited"
    assert found.result.lower_bound <= len(set(rows))


@pytest.mark.scan_json_lot("7b")
def test_D07_when_a_late_value_exhausts_the_budget_the_field_stops_and_says_so(tmp_path):
    digits = [f"{n:010d}" for n in range(2_000)]
    rows = digits + ["P" + "x" * 40 + f"{n:05d}" for n in range(3_000)]
    result, plan, _ = deep_csv(tmp_path, "id", rows, limits=LIMITED)
    # A grant that holds the digits as the executor would, but not the texts that
    # arrive after them: measured on a set of those digits.
    probe = ExactSet(ExactPool(1 << 40))
    probe.add_strings(digits, [1] * len(digits))
    tight = _plan_with_grant(plan, probe.used + 8_192)

    outcome = run_second_pass(result, tmp_path / "data.csv", tight)

    found = _distinct(outcome, "id")
    assert found.status == "limited" and found.reason == "memory_budget"
    assert found.result.kind == "distinct_limited" and found.result.accuracy == "lower_bound"
    assert 2_000 <= found.result.values_read < len(rows)
    assert found.result.lower_bound <= len(set(rows))


# D08, the executor half ---------------------------------------------------------


@pytest.mark.scan_json_lot("7b")
def test_D08_a_memory_limit_met_while_counting_is_limited_and_never_exact(tmp_path):
    rows = [f"A{n:08d},{n % 90},{n * 1.5:.1f}" for n in range(4_000)]
    result, plan, _ = deep_csv(tmp_path, "id,small,price", rows, limits=LIMITED)
    tight = _plan_with_grant(plan, 20_000)

    outcome = run_second_pass(result, tmp_path / "data.csv", tight)

    found = _distinct(outcome, "id")
    assert found.status == "limited" and found.reason == "memory_budget"
    assert "distinct" not in found.result.model_dump()
    assert found.result.lower_bound >= 1
    assert found.result.values_read <= len(rows)
    assert outcome.document.status == "partial"
    # The analyses that share the reading go on, and the digest is checked.
    assert entry(outcome, "numeric_histogram", "price").status == "complete"
    assert outcome.document.run.source_verified


@pytest.mark.scan_json_lot("7b")
def test_D08_a_field_that_fits_is_exact_and_a_limited_one_frees_its_memory(tmp_path):
    rows = [f"A{n:08d}" for n in range(4_000)]
    result, plan, _ = deep_csv(tmp_path, "id", rows, limits=LIMITED)
    tight = _plan_with_grant(plan, 20_000)

    tracemalloc.start()
    run_second_pass(result, tmp_path / "data.csv", tight)
    _, limited_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    tracemalloc.start()
    run_second_pass(result, tmp_path / "data.csv", plan)
    _, whole_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert limited_peak < whole_peak


# Original values of JSON ---------------------------------------------------------


def _json_scan(tmp_path, records):
    source = write_text(tmp_path, "data.json", json.dumps(records))
    return scan(source, config=ScanConfig.model_validate({"limits": LIMITED})), source


@pytest.mark.scan_json_lot("7b")
def test_D06_json_values_keep_their_native_type_in_the_original_domain(tmp_path):
    records = []
    for n in range(200):
        records.append({"v": n})
        records.append({"v": str(n)})
        records.append({"v": f"{n:05d}"})
        records.append({"v": float(n) + 0.5})
        records.append({"v": n % 2 == 0})
        records.append({"v": None})
    result, source = _json_scan(tmp_path, records)
    plan = forced_plan(result)

    outcome = run_second_pass(result, source, plan)

    distinct = [a for a in outcome.document.analyses if a.analyzer == "exact_distinct"]
    assert len(distinct) == 1 and distinct[0].status == "complete"
    expected = len(
        {
            (type(r["v"]).__name__, r["v"])
            for r in records
            if r["v"] is not None
        }
    )
    assert distinct[0].result.distinct == expected
    assert distinct[0].result.values == len(records) - 200
    assert distinct[0].result.values == _field(result, distinct[0].display).values.count


# exact_frequencies -------------------------------------------------------------


@pytest.mark.scan_json_lot("7b")
def test_D06_frequencies_match_an_oracle_and_keep_7_007_and_the_integer_apart(tmp_path):
    values = [f"{n % 150:03d}" for n in range(900)] + ["7"] * 40 + ["007"] * 25 + ["x y"] * 3
    rows = [f"{cell},k" for cell in [*values, "", "  "]]
    result, _, outcome = deep_csv(
        tmp_path, "code,k", rows, limits={"max_listed_frequencies": 10, "max_samples": 20}
    )

    found = entry(outcome, "exact_frequencies", "code")
    assert found.status == "complete" and found.domain == "analytical"
    oracle = Counter(values)
    table = found.result
    assert table.count == len(values) and table.distinct == len(oracle)
    ranked = sorted(oracle.items(), key=lambda item: (-item[1], item[0]))
    assert [(v.value, v.count) for v in table.values] == ranked
    assert {v.type for v in table.values} == {"string"}
    assert oracle["7"] == 40 and oracle["007"] > 25
    # The listing of the Scan is the head of the whole table.
    scanned = _field(result, "code").values.frequencies.value.listed
    assert [(v.value, v.type, v.count) for v in table.values[: len(scanned)]] == [
        (v.value, v.type, v.count) for v in scanned
    ]
    assert table.modes[0].count == table.values[0].count


@pytest.mark.scan_json_lot("7b")
def test_D06_frequencies_of_json_values_separate_the_native_types(tmp_path):
    records = []
    for n in range(300):
        records.append({"v": n % 60})
        records.append({"v": str(n % 60)})
        records.append({"v": (n % 60) + 0.25})
    source = write_text(tmp_path, "data.json", json.dumps(records))
    result = scan(
        source,
        config=ScanConfig.model_validate(
            {"limits": {"max_listed_frequencies": 5, "max_samples": 20}}
        ),
    )
    plan = forced_plan(result)

    outcome = run_second_pass(result, source, plan)

    found = [a for a in outcome.document.analyses if a.analyzer == "exact_frequencies"]
    assert len(found) == 1 and found[0].status == "complete"
    table = found[0].result
    assert table.distinct == 180
    assert {(v.type) for v in table.values} == {"integer", "string", "number"}
    assert sum(v.count for v in table.values) == 900


@pytest.mark.scan_json_lot("7b")
def test_D06_a_source_with_more_values_than_the_scan_found_fails_the_frequencies(tmp_path):
    rows = [f"{n % 200:03d}" for n in range(800)]
    result, _, _ = deep_csv(
        tmp_path, "code", rows, limits={"max_listed_frequencies": 10, "max_samples": 20}
    )
    lie = next(f for d in result.datasets for f in d.fields)
    frequencies = lie.values.frequencies.model_copy(
        update={"value": lie.values.frequencies.value.model_copy(update={"distinct": 150})}
    )
    values = lie.values.model_copy(update={"frequencies": frequencies})
    forged = result.model_copy(
        update={
            "datasets": [
                result.datasets[0].model_copy(
                    update={"fields": [lie.model_copy(update={"values": values})]}
                )
            ]
        }
    )

    outcome = run_second_pass(forged, tmp_path / "data.csv", forced_plan(forged))

    found = entry(outcome, "exact_frequencies", "code")
    assert found.status == "failed" and found.reason == "scan_mismatch"


# Plan and executor agree -----------------------------------------------------------


@pytest.mark.scan_json_lot("7b")
def test_D03_the_executable_analyzers_are_the_available_ones():
    available = {analyzer.id for analyzer in default_registry().runnable()}
    assert EXECUTABLE == available
    assert {"exact_distinct", "exact_frequencies"} <= available


@pytest.mark.scan_json_lot("7b")
def test_D03_distinct_frequencies_and_a_histogram_share_one_reading(tmp_path, monkeypatch):
    rows = [f"I{n:07d},{n % 40:03d},{n * 1.1:.1f}" for n in range(1_500)]
    scanned = scan_csv(
        tmp_path,
        "id,code,price",
        rows,
        limits={**LIMITED, "max_listed_frequencies": 10, "max_samples": 20},
    )
    plan = forced_plan(scanned)
    opened = []
    from tabalyst.scanner.readers import factory
    from tabalyst.scanner.secondpass import executor

    def counting(path, config, on_bytes):
        opened.append(path)
        return factory.open_reader(path, config, on_bytes)

    monkeypatch.setattr(executor, "open_reader", counting)

    outcome = run_second_pass(scanned, tmp_path / "data.csv", plan)

    kinds = {a.analyzer for a in outcome.document.analyses}
    assert {"exact_distinct", "exact_frequencies", "numeric_histogram"} <= kinds
    assert len(opened) == 1
    assert all(a.status == "complete" for a in outcome.document.analyses)
    assert by_analyzer(plan, "exact_distinct")["id"].costs.cpu in ("low", "moderate")


# Memory ------------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7b")
def test_D08_the_set_of_a_field_stays_under_the_firm_bound_of_its_plan(tmp_path):
    rows = [f"B{n * 7919 % 10**9:09d}" if n % 2 else f"A{n:011d}" for n in range(60_000)]
    result, plan, _ = deep_csv(tmp_path, "id", rows, limits={"max_distinct_per_field": 100})
    candidate = by_analyzer(plan, "exact_distinct")["id"]
    bound = max(s.memory.max for s in candidate.costs.states if s.key.startswith(EXACT_SET_STATE_PREFIX))

    tracemalloc.start()
    tracemalloc.reset_peak()
    base = tracemalloc.get_traced_memory()[0]
    outcome = run_second_pass(result, tmp_path / "data.csv", plan)
    peak = tracemalloc.get_traced_memory()[1] - base
    tracemalloc.stop()

    found = _distinct(outcome, "id")
    assert found.status == "complete" and found.result.distinct == len(set(rows))
    assert peak < bound + 24 * 1024 * 1024
