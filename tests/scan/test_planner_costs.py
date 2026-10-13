# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The cost model of the planner against measures, and the budgets it applies
(lot 6b, design 20.2)."""

import gc
import re
import sys
import tracemalloc

import pytest
from planner_helpers import by_analyzer, scan_csv

from tabalyst.scanner import ScanConfig
from tabalyst.scanner.planner import (
    AnalysisRequest,
    AnalyzerRegistry,
    default_budgets,
    plan_analyses,
)
from tabalyst.scanner.planner.analyzer import (
    Analyzer,
    Assessment,
    costs,
    memory,
    set_entry,
    table_entry,
)
from tabalyst.scanner.planner.costmodel import (
    CELL_CLASS_LIMITS,
    COST_MODEL_VERSION,
    DEFAULT_AUTOMATIC_MEMORY_BYTES,
    DEFAULT_MAX_CELLS,
    DEFAULT_MEMORY_BUDGET_BYTES,
    MATCHER_BYTES,
    NS_PER_CELL,
    PARSER_RESERVE_BYTES,
    cell_class,
    cpu_class_for,
)
from tabalyst.scanner.planner.models import State, Utility
from tabalyst.scanner.planner.planner import AUTOMATIC_MIN_UTILITY
from tabalyst.scanner.readers.factory import open_reader

ENTRIES = 50_000


def _measure(build) -> tuple[float, float]:
    """Bytes an entry holds and the peak of building them, per entry."""
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    base = tracemalloc.get_traced_memory()[0]
    held = build()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del held
    return (current - base) / ENTRIES, (peak - base) / ENTRIES


# Sizes -------------------------------------------------------------------------


@pytest.mark.parametrize("length", [8, 12, 24, 64])
def test_the_entry_of_a_set_of_texts_is_bracketed_by_the_model(length):
    def build():
        return {f"{index:08d}".ljust(length, "x") for index in range(ENTRIES)}

    held, peak = _measure(build)
    low, expected, high = set_entry("text", length)

    # Calibrated on CPython 3.12: a set of short texts weighs 15.1% more on 3.11.
    assert low <= held <= expected * 1.2
    assert peak <= high


def test_the_entry_of_a_set_of_integers_is_bracketed_by_the_model():
    held, peak = _measure(lambda: {index * 7919 for index in range(ENTRIES)})
    low, expected, high = set_entry("integer", 0)

    assert low <= held <= expected * 1.15
    assert peak <= high


def test_the_entry_of_a_table_of_counts_matches_the_model_within_a_fifth():
    entries = 1_000

    def build():
        return {f"state_{index:04d}": index for index in range(entries)}

    gc.collect()
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    held = build()
    per_entry = (tracemalloc.get_traced_memory()[0] - base) / entries
    tracemalloc.stop()
    del held

    assert per_entry == pytest.approx(table_entry(len("state_0000")), rel=0.2)


def test_a_compiled_matcher_fits_its_size():
    for pattern in (r"[A-Z]{2}-\d{4}-[A-Z]", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"):
        re.purge()
        gc.collect()
        tracemalloc.start()
        base = tracemalloc.get_traced_memory()[0]
        compiled = re.compile(pattern)
        size = tracemalloc.get_traced_memory()[0] - base
        tracemalloc.stop()
        assert compiled.pattern == pattern
        # Calibrated on CPython 3.12; 3.14 compiles to a program 19% larger.
        assert size <= MATCHER_BYTES * (1.25 if sys.version_info >= (3, 14) else 1)


def test_reading_texts_of_thousands_of_characters_stays_within_the_parser_reserve(tmp_path):
    text = "x" * 4_000
    rows = "\n".join(f"{n},{text}{n}" for n in range(8_000))
    path = tmp_path / "long.csv"
    path.write_text("id,description\n" + rows + "\n", encoding="utf-8", newline="")

    gc.collect()
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    for _ in open_reader(path, ScanConfig(), None):
        pass
    peak = tracemalloc.get_traced_memory()[1] - base
    tracemalloc.stop()

    assert peak < PARSER_RESERVE_BYTES


def test_the_model_charges_the_length_of_the_texts_it_keeps(tmp_path):
    short = scan_csv(tmp_path, "code", [f"A{n:05d}" for n in range(300)], limits={"max_distinct_per_field": 50})
    (tmp_path / "long").mkdir()
    long = scan_csv(
        tmp_path / "long", "code", [f"A{n:05d}" + "x" * 30 for n in range(300)], limits={"max_distinct_per_field": 50}
    )

    small = by_analyzer(plan_analyses(short, automatic=False), "exact_distinct")["code"]
    large = by_analyzer(plan_analyses(long, automatic=False), "exact_distinct")["code"]

    assert large.costs.memory.max - small.costs.memory.max == 300 * 30


# Classes -----------------------------------------------------------------------


def test_cpu_classes_follow_the_nanoseconds_a_cell_adds():
    assert [cpu_class_for(ns) for ns in (1, 100, 101, 600, 601, 2_400, 2_401)] == [
        "very_low", "very_low", "low", "low", "moderate", "moderate", "high",
    ]  # fmt: skip


def test_the_analyses_the_executor_runs_are_costed_with_its_own_measures():
    # Counting a cell after the number detector and the normalization: a
    # length (no number), a counter of integers, a bin of a decimal.
    assert NS_PER_CELL["length_counter"] < NS_PER_CELL["dense_counter"] < NS_PER_CELL["bin"]
    assert [cpu_class_for(NS_PER_CELL[kind]) for kind in ("length_counter", "dense_counter", "bin")] == [
        "low", "moderate", "moderate",
    ]  # fmt: skip


def test_a_class_given_alone_stands_for_the_top_of_its_range():
    assert costs("low", [State(key="s", memory=memory(1))]).cell_ns == 600
    assert costs(130, [State(key="s", memory=memory(1))]).cpu == "low"
    assert costs("high", [State(key="s", memory=memory(1))]).cell_ns == 4 * 2_400


def test_the_common_reading_is_classed_by_its_cells():
    assert [cell_class(cells) for cells in (0, *CELL_CLASS_LIMITS, CELL_CLASS_LIMITS[-1] + 1)] == [
        "very_low", "very_low", "low", "moderate", "high",
    ]  # fmt: skip


def test_the_cost_of_a_pattern_grows_with_its_candidates(tmp_path):
    rows = [f"{prefix}-{n:04d}" for n in range(60) for prefix in ("AB", "7", "x y")]
    result = scan_csv(tmp_path, "code", rows)

    candidate = by_analyzer(plan_analyses(result, automatic=False), "pattern_validation")["code"]

    count = candidate.parameters["patterns"]
    expected = NS_PER_CELL["matcher_base"] + count * NS_PER_CELL["matcher"]
    assert count > 1 and candidate.costs.cell_ns == expected
    assert candidate.costs.cpu == cpu_class_for(expected)


# Budgets -----------------------------------------------------------------------


def test_the_default_budgets_are_the_calibrated_ones():
    budgets = default_budgets()

    assert budgets.memory_bytes == DEFAULT_MEMORY_BUDGET_BYTES == 512 * 1024 * 1024
    assert budgets.automatic_memory_bytes == DEFAULT_AUTOMATIC_MEMORY_BYTES == 128 * 1024 * 1024
    assert budgets.max_cells == DEFAULT_MAX_CELLS == CELL_CLASS_LIMITS[-1]
    assert budgets.automatic_max_cpu == "moderate"
    assert budgets.automatic_memory_bytes < budgets.memory_bytes


def test_the_plan_names_its_cost_model(tmp_path):
    result = scan_csv(tmp_path, "t", ["a", "b"])

    assert plan_analyses(result).cost_model_version == COST_MODEL_VERSION


def _identifiers(tmp_path):
    rows = [f"A{n:07d},B{n:07d}" for n in range(5_000)]
    return scan_csv(tmp_path, "id_a,id_b", rows, limits={"max_distinct_per_field": 50})


def test_what_the_planner_picks_by_itself_stays_within_the_automatic_memory(tmp_path):
    result = _identifiers(tmp_path)
    one = by_analyzer(plan_analyses(result), "exact_distinct")["id_a"].costs.memory.max
    budgets = default_budgets().model_copy(
        update={"automatic_memory_bytes": PARSER_RESERVE_BYTES + one + one // 2}
    )

    plan = plan_analyses(result, budgets=budgets)

    ids = by_analyzer(plan, "exact_distinct")
    assert sorted(c.selection.state for c in ids.values()) == ["rejected", "selected"]
    assert plan.summary.memory.max <= budgets.automatic_memory_bytes
    assert plan.summary.beyond_automatic == []


def test_a_request_may_use_the_hard_budget_and_then_asks_for_a_confirmation(tmp_path):
    result = _identifiers(tmp_path)
    one = by_analyzer(plan_analyses(result), "exact_distinct")["id_a"].costs.memory.max
    budgets = default_budgets().model_copy(
        update={"automatic_memory_bytes": PARSER_RESERVE_BYTES + one // 2}
    )

    plan = plan_analyses(result, requests=[AnalysisRequest("exact_distinct")], budgets=budgets)

    ids = by_analyzer(plan, "exact_distinct")
    assert {c.selection.reason for c in ids.values()} == {"requested"}
    assert plan.summary.memory.max > budgets.automatic_memory_bytes
    assert plan.summary.beyond_automatic == ["memory_over_automatic"]


def test_the_hard_budget_is_never_lifted_by_a_request_or_by_force(tmp_path):
    result = _identifiers(tmp_path)
    one = by_analyzer(plan_analyses(result), "exact_distinct")["id_a"].costs.memory.max
    budgets = default_budgets().model_copy(update={"memory_bytes": PARSER_RESERVE_BYTES + one})

    asked = plan_analyses(result, requests=[AnalysisRequest("exact_distinct")], budgets=budgets)
    forced = plan_analyses(result, forced=True, budgets=budgets)

    for plan in (asked, forced):
        assert plan.summary.memory.max <= budgets.memory_bytes
        states = [c.selection.state for c in by_analyzer(plan, "exact_distinct").values()]
        assert sorted(states) == ["rejected", "selected"]


# Forced plans ------------------------------------------------------------------


def test_a_forced_plan_takes_what_automatic_selection_leaves_out(tmp_path):
    result = scan_csv(tmp_path, "customer_id", [str(n) for n in range(600)], limits={"max_distinct_per_field": 50})

    automatic = plan_analyses(result)
    forced = plan_analyses(result, forced=True)

    histogram = by_analyzer(automatic, "numeric_histogram")["customer_id"]
    assert histogram.utility.score < AUTOMATIC_MIN_UTILITY
    assert histogram.selection.reason == "low_utility"
    chosen = by_analyzer(forced, "numeric_histogram")["customer_id"]
    assert (chosen.selection.state, chosen.selection.reason) == ("selected", "forced")
    assert forced.objective.forced is True and automatic.objective.forced is False


class _Heavy(Analyzer):
    id = "heavy"
    outputs = ("heavy",)
    available = True

    def relevant(self, facts):
        return facts.technical_type == "text"

    def assess(self, facts):
        return Assessment("applicable", method="heavy")

    def estimate(self, facts, assessment):
        return costs("high", [State(key=f"heavy:{facts.where}", memory=memory(10))])

    def utility(self, facts, assessment):
        return Utility(score=60, reasons=["base_value"])


def test_a_forced_plan_goes_beyond_the_cpu_limit_and_says_so(tmp_path):
    result = scan_csv(tmp_path, "t", ["a", "b", "c"])
    registry = AnalyzerRegistry([_Heavy])

    automatic = plan_analyses(result, registry=registry)
    forced = plan_analyses(result, registry=registry, forced=True)

    assert automatic.summary.selected == 0
    assert forced.summary.selected == 1
    assert forced.summary.beyond_automatic == ["cpu_over_automatic"]


def test_a_forced_plan_goes_beyond_the_cell_budget_and_says_so(tmp_path):
    result = _identifiers(tmp_path)
    budgets = default_budgets().model_copy(update={"max_cells": 10})

    automatic = plan_analyses(result, budgets=budgets)
    forced = plan_analyses(result, budgets=budgets, forced=True)

    assert automatic.summary.second_pass_required is False
    assert automatic.summary.beyond_automatic == []
    assert "cells_over_automatic" in forced.summary.beyond_automatic


def test_a_source_too_large_for_an_automatic_reading_is_left_for_force(tmp_path):
    result = _identifiers(tmp_path)
    huge = result.model_copy(
        update={
            "source": result.source.model_copy(
                update={"shape": result.source.shape.model_copy(update={"cells": 10 * CELL_CLASS_LIMITS[-1]})}
            )
        }
    )
    budgets = default_budgets().model_copy(update={"max_cells": None})

    automatic = plan_analyses(huge, budgets=budgets)
    forced = plan_analyses(huge, budgets=budgets, forced=True)

    reading = [c for c in automatic.candidates if c.execution.requires_source and c.applicability.state == "applicable"]
    assert reading and {c.selection.reason for c in reading} == {"cpu_class"}
    assert automatic.summary.beyond_automatic == []
    assert forced.summary.beyond_automatic == ["cpu_over_automatic"]


def test_an_automatic_plan_never_goes_beyond_the_automatic_limits(tmp_path):
    rows = [f"{n},{n * 1.5:.1f},AB-{n:04d},2023-0{1 + n % 9}-1{n % 9}" for n in range(300)]
    result = scan_csv(tmp_path, "customer_id,price,code,day", rows, limits={"max_samples": 20, "max_distinct_per_field": 50})

    plan = plan_analyses(result)

    assert plan.summary.selected > 0
    assert plan.summary.beyond_automatic == []
