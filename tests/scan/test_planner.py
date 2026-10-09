# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The registry of analyzers and the planner (design 20.5, lot 6a).

The behavior is the decision tree of specification 11.2, the selection of 11.1
and the cost rules of 11.3 to 11.4, tested on small Scans.
"""

import json
from typing import ClassVar

import pytest
from planner_helpers import by_analyzer, scan_csv, unique_state_bytes, with_field
from scan_helpers import write_text
from typer.testing import CliRunner

from tabalyst import generate_reports, generate_scans
from tabalyst.cli import app
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.plan_service import generate_plans, plan_document
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import Disabled
from tabalyst.scanner.planner import (
    AnalysisPlan,
    AnalysisRequest,
    Analyzer,
    AnalyzerRegistry,
    Assessment,
    default_budgets,
    default_registry,
    plan_analyses,
    plan_text,
)
from tabalyst.scanner.planner.analyzer import costs, memory
from tabalyst.scanner.planner.costmodel import (
    INT_OBJECT_BYTES,
    RESULT_BYTES,
    SET_SLOT_BYTES,
)
from tabalyst.scanner.planner.models import State, Utility
from tabalyst.scanner.planner.planner import (
    AUTOMATIC_MIN_UTILITY,
    DEFAULT_MEMORY_BUDGET_BYTES,
    PARSER_RESERVE_BYTES,
)
from tabalyst.scanner.planner.reasons import REASONS, reason_text

runner = CliRunner()
SMALL_K = {"max_samples": 20, "max_distinct_per_field": 50}


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage"))


def _state(plan: AnalysisPlan, analyzer: str, display: str):
    return by_analyzer(plan, analyzer)[display]


# Registry ----------------------------------------------------------------------


class _Fake(Analyzer):
    id: ClassVar[str] = "fake"
    outputs: ClassVar[tuple[str, ...]] = ("fake",)
    available: ClassVar[bool] = True
    cpu = "low"

    def relevant(self, facts):
        return facts.technical_type == "text"

    def assess(self, facts):
        return Assessment("applicable", method="fake")

    def estimate(self, facts, assessment):
        return costs(self.cpu, [State(key=f"fake:{facts.where}", memory=memory(10, 20, 30))])

    def utility(self, facts, assessment):
        return Utility(score=60, reasons=["base_value"])


def test_the_default_registry_lists_the_built_in_analyzers_in_plan_order():
    assert [a.id for a in default_registry()] == [
        "exact_frequencies",
        "numeric_histogram",
        "length_distribution",
        "exact_distinct",
        "pattern_validation",
        "temporal_distribution",
    ]


def test_a_registry_refuses_what_is_not_an_analyzer_and_a_known_id():
    registry = AnalyzerRegistry([_Fake])
    assert "fake" in registry and len(registry) == 1
    with pytest.raises(ValueError, match="already registered"):
        registry.register(_Fake)
    with pytest.raises(TypeError, match="subclass Analyzer"):
        registry.register(object)  # type: ignore[arg-type]

    class Anonymous(_Fake):
        id = ""  # type: ignore[assignment]

    class Mute(_Fake):
        id = "mute"  # type: ignore[assignment]
        outputs = ()  # type: ignore[assignment]

    with pytest.raises(TypeError, match="no id"):
        registry.register(Anonymous)
    with pytest.raises(TypeError, match="no outputs"):
        registry.register(Mute)


def test_the_built_in_analyzers_are_not_executable_yet():
    assert not any(a.available for a in default_registry())


# Decision tree -----------------------------------------------------------------


def test_a_column_without_values_has_no_analysis_to_run(tmp_path):
    result = scan_csv(tmp_path, "a,b", ["1,", "2,", "3,"])

    plan = plan_analyses(result)

    empty = [c for c in plan.candidates if c.display == "b"]
    assert empty, "the empty column is explained, not silently skipped"
    assert {c.applicability.state for c in empty} == {"not_applicable"}
    assert {r for c in empty for r in c.applicability.reasons} == {"no_values"}
    assert all(c.selection.reason == "not_applicable" for c in empty)


def test_a_constant_number_reuses_its_statistics_and_does_not_divide_by_zero(tmp_path):
    result = scan_csv(tmp_path, "n", ["7"] * 10)

    plan = plan_analyses(result)

    histogram = _state(plan, "numeric_histogram", "n")
    assert histogram.selection.state == "already_satisfied"
    assert histogram.selection.reason == "constant_value"
    assert histogram.selection.satisfied_by == "datasets/rows/fields/column_1/numeric"
    assert histogram.costs is None


def test_a_small_integer_domain_uses_dense_counters_shared_with_the_frequencies(tmp_path):
    # 300 distinct values: more than the scan lists as frequencies (100) and than
    # its sample keeps (20), yet few enough for a table or an array of counters.
    rows = [str(1 + index % 300) for index in range(900)]
    result = scan_csv(tmp_path, "qty", rows, limits={"max_samples": 20})

    plan = plan_analyses(result)

    histogram = _state(plan, "numeric_histogram", "qty")
    frequencies = _state(plan, "exact_frequencies", "qty")
    assert (histogram.method, histogram.parameters) == ("dense_counts", {"domain": 300})
    assert (frequencies.method, frequencies.parameters) == ("dense_counts", {"domain": 300})
    assert histogram.selection.state == frequencies.selection.state == "selected"
    # The counters are one state, counted once.
    shared = {s.key for s in histogram.costs.states} & {s.key for s in frequencies.costs.states}
    assert len(shared) == 1
    results = 2 * 1_024
    dense = 300 * 8
    others = sum(
        s.memory.max
        for c in plan.candidates
        if c.selection.state == "selected"
        and (c.analyzer, c.display) not in {("numeric_histogram", "qty"), ("exact_frequencies", "qty")}
        for s in c.costs.states
    )
    assert unique_state_bytes(plan) == dense + results + others


def test_numbers_with_a_wide_range_are_binned_with_a_fixed_memory(tmp_path):
    rows = [f"{index * 1013.37:.2f}" for index in range(200)]
    result = scan_csv(tmp_path, "price", rows)

    histogram = _state(plan_analyses(result), "numeric_histogram", "price")

    assert (histogram.method, histogram.parameters) == ("linear_bins", {"bins": 100})
    assert histogram.costs.memory.max == 100 * 8 + 16 + 1_024


def test_a_column_that_mixes_types_gets_no_typed_analysis(tmp_path):
    rows = [str(index) if index % 3 else f"n/a {index}" for index in range(60)]
    result = scan_csv(tmp_path, "mixed", rows)

    histogram = _state(plan_analyses(result), "numeric_histogram", "mixed")

    assert histogram.applicability.reasons == ["unreliable_type"]
    assert histogram.selection.state == "rejected"


def test_an_identifier_gets_an_exact_distinct_count_and_no_histogram(tmp_path):
    rows = [str(100_000 + index) for index in range(600)]
    result = scan_csv(tmp_path, "customer_id", rows, limits={"max_distinct_per_field": 50})

    plan = plan_analyses(result)

    distinct = _state(plan, "exact_distinct", "customer_id")
    assert distinct.selection.state == "selected"
    assert set(distinct.utility.reasons) >= {"near_unique", "identifier_name", "integer_key"}
    assert (distinct.method, distinct.parameters) == ("compact_set", {"key": "integer"})
    assert distinct.costs.memory.min <= distinct.costs.memory.expected <= distinct.costs.memory.max
    # An integer object and the largest slot of a set (cost model), 600 times.
    assert distinct.costs.memory.max == 600 * (INT_OBJECT_BYTES + SET_SLOT_BYTES[2]) + RESULT_BYTES
    histogram = _state(plan, "numeric_histogram", "customer_id")
    assert histogram.selection.state == "rejected"
    assert histogram.selection.reason == "low_utility"
    assert histogram.utility.reasons == ["identifier_like"]


def test_a_complete_distinct_count_is_already_satisfied(tmp_path):
    result = scan_csv(tmp_path, "customer_id", [f"X{n}" for n in range(30)])

    distinct = _state(plan_analyses(result), "exact_distinct", "customer_id")

    assert distinct.selection.state == "already_satisfied"
    assert distinct.selection.satisfied_by == "datasets/rows/fields/column_1/values/cardinality"


def test_long_texts_have_no_exact_distinct_count(tmp_path):
    rows = [("text " + str(n)) * 30 for n in range(100)]
    result = scan_csv(
        tmp_path, "comment", rows, limits={"max_stored_value_length": 20, "max_distinct_per_field": 50}
    )

    distinct = _state(plan_analyses(result), "exact_distinct", "comment")

    assert distinct.applicability.state == "not_applicable"
    assert distinct.applicability.reasons == ["long_texts_only"]


def test_long_values_are_not_compactable_into_an_exact_set(tmp_path):
    rows = [f"{n:04d}-" + "x" * 80 for n in range(200)]
    result = scan_csv(tmp_path, "note", rows, limits={"max_distinct_per_field": 50})

    distinct = _state(plan_analyses(result), "exact_distinct", "note")

    assert distinct.applicability.reasons == ["not_compactable"]


def test_a_structured_string_gets_its_patterns_validated_on_the_whole_file(tmp_path):
    rows = [f"AB-{index:04d}" for index in range(300)]
    result = scan_csv(tmp_path, "code", rows, limits=SMALL_K)

    candidate = _state(plan_analyses(result), "pattern_validation", "code")

    assert candidate.selection.state == "selected"
    assert candidate.method == "compiled_matcher"
    assert "candidates_unvalidated" in candidate.utility.reasons
    assert candidate.execution.requires_source is True


def test_patterns_of_a_fully_listed_field_need_no_source(tmp_path):
    rows = [f"AB-{index:04d}" for index in range(30)]
    result = scan_csv(tmp_path, "code", rows)

    candidate = _state(plan_analyses(result), "pattern_validation", "code")

    assert candidate.selection.state == "selected"
    assert candidate.execution.requires_source is False
    assert candidate.utility.reasons == ["derivable_from_samples"]


def test_a_sensitive_field_is_never_read_again(tmp_path):
    rows = [f"person{n}@example.org" for n in range(80)]
    result = scan_csv(tmp_path, "email", rows, limits={"max_distinct_per_field": 50})

    plan = plan_analyses(result)

    candidates = [c for c in plan.candidates if c.display == "email"]
    assert candidates
    assert {r for c in candidates for r in c.applicability.reasons} == {"sensitive_exposure"}
    assert plan.summary.selected == 0


@pytest.mark.parametrize(
    ("first", "last", "granularity"),
    [
        ("2024-01-01", "2024-03-30", "day"),
        ("2015-01-01", "2024-12-31", "month"),
    ],
)
def test_dates_are_counted_by_a_granularity_sized_from_their_span(tmp_path, first, last, granularity):
    result = scan_csv(tmp_path, "day", [first, last])

    candidate = _state(plan_analyses(result), "temporal_distribution", "day")

    assert candidate.parameters["granularity"] == granularity
    assert candidate.costs.memory.max == candidate.parameters["periods"] * 8 + 1_024
    assert candidate.selection.state == "selected"


def test_dates_over_decades_are_already_counted_by_year(tmp_path):
    result = scan_csv(tmp_path, "day", ["1900-01-01", "1950-06-15", "2024-12-31"])

    candidate = _state(plan_analyses(result), "temporal_distribution", "day")

    assert candidate.selection.state == "already_satisfied"
    assert candidate.selection.reason == "years_counted"
    assert candidate.selection.satisfied_by == "datasets/rows/fields/column_1/temporal"


def test_a_single_date_is_already_known(tmp_path):
    result = scan_csv(tmp_path, "day", ["2024-05-05"] * 5)

    candidate = _state(plan_analyses(result), "temporal_distribution", "day")

    assert candidate.selection.state == "already_satisfied"
    assert candidate.selection.reason == "constant_value"


def test_a_missing_length_histogram_is_proposed(tmp_path):
    result = scan_csv(tmp_path, "name", [f"name{n}" for n in range(40)])
    result = with_field(result, "name", string_lengths=Disabled())

    candidate = _state(plan_analyses(result), "length_distribution", "name")

    assert candidate.applicability.state == "applicable"
    assert candidate.selection.state == "selected"
    assert candidate.parameters == {"domain": 1_024}


# Selection ---------------------------------------------------------------------


def test_an_explicit_request_is_selected_even_below_the_automatic_utility(tmp_path):
    result = scan_csv(tmp_path, "customer_id", [str(n) for n in range(600)], limits=SMALL_K)
    request = AnalysisRequest("numeric_histogram", field="customer_id")

    plan = plan_analyses(result, requests=[request], automatic=False)

    histogram = _state(plan, "numeric_histogram", "customer_id")
    assert histogram.utility.score < AUTOMATIC_MIN_UTILITY
    assert (histogram.selection.state, histogram.selection.reason) == ("selected", "requested")
    assert histogram.selection.priority == 1
    assert plan.objective.requested[0].candidates == 1
    others = [c for c in plan.candidates if c is not histogram and c.selection.state == "rejected"]
    assert {c.selection.reason for c in others} <= {"not_requested", "not_applicable"}


def test_an_explicit_request_is_chosen_before_the_automatic_analyses(tmp_path):
    rows = [f"{index * 3.5:.1f},{index * 2},{index * 7}" for index in range(100)]
    result = scan_csv(tmp_path, "a,b,c", rows)
    plan = plan_analyses(result, requests=[AnalysisRequest("numeric_histogram", field="c")])

    selected = sorted(
        (c for c in plan.candidates if c.selection.state == "selected"),
        key=lambda c: c.selection.priority,
    )
    assert (selected[0].analyzer, selected[0].display) == ("numeric_histogram", "c")
    assert selected[0].selection.requested is True


def test_a_request_that_does_not_fit_is_rejected_for_budget_not_dropped(tmp_path):
    result = scan_csv(tmp_path, "customer_id", [str(n) for n in range(600)], limits=SMALL_K)
    tiny = default_budgets().model_copy(update={"memory_bytes": PARSER_RESERVE_BYTES})

    plan = plan_analyses(
        result, requests=[AnalysisRequest("exact_distinct")], budgets=tiny
    )

    distinct = _state(plan, "exact_distinct", "customer_id")
    assert (distinct.selection.state, distinct.selection.reason) == ("rejected", "budget")
    assert distinct.selection.requested is True
    assert plan.summary.memory.max <= tiny.memory_bytes
    assert distinct.selection.priority is None


def test_a_request_that_matches_no_field_is_reported_with_zero_candidates(tmp_path):
    result = scan_csv(tmp_path, "name", [f"n{n}" for n in range(20)])

    plan = plan_analyses(result, requests=[AnalysisRequest("temporal_distribution")])

    assert plan.objective.requested[0].candidates == 0


def test_requests_naming_something_unknown_are_a_configuration_error(tmp_path):
    result = scan_csv(tmp_path, "name", ["a", "b"])
    for request in (
        AnalysisRequest("nope"),
        AnalysisRequest("exact_distinct", dataset="missing"),
        AnalysisRequest("exact_distinct", field="missing"),
    ):
        with pytest.raises(ConfigurationError):
            plan_analyses(result, requests=[request])


def test_without_automatic_selection_nothing_is_chosen_unasked(tmp_path):
    rows = [f"{index * 3.5:.1f}" for index in range(100)]
    result = scan_csv(tmp_path, "price", rows)

    plan = plan_analyses(result, automatic=False)

    assert plan.summary.selected == 0
    assert _state(plan, "numeric_histogram", "price").selection.reason == "not_requested"
    assert plan.objective.automatic is False


def test_the_cpu_limit_and_the_cell_budget_stop_only_the_automatic_choice(tmp_path):
    registry = AnalyzerRegistry([_Fake])
    result = scan_csv(tmp_path, "t", ["a", "b", "c"])

    class Heavy(_Fake):
        id = "heavy"  # type: ignore[assignment]
        cpu = "high"

    registry.register(Heavy)
    budgets = default_budgets()
    plan = plan_analyses(result, registry=registry, budgets=budgets)
    assert _state(plan, "fake", "t").selection.reason == "automatic"
    assert _state(plan, "heavy", "t").selection.reason == "cpu_class"
    asked = plan_analyses(result, registry=registry, requests=[AnalysisRequest("heavy")])
    assert _state(asked, "heavy", "t").selection.reason == "requested"

    capped = plan_analyses(
        result, registry=registry, budgets=budgets.model_copy(update={"max_cells": 1})
    )
    assert _state(capped, "fake", "t").selection.reason == "cells_budget"
    assert plan_analyses(
        result,
        registry=registry,
        budgets=budgets.model_copy(update={"max_cells": 1}),
        requests=[AnalysisRequest("fake")],
    ).summary.selected == 1


def test_a_plan_says_whether_its_selection_can_run(tmp_path):
    result = scan_csv(tmp_path, "t", ["a", "b", "c"])
    numbers = scan_csv(tmp_path, "price", [f"{index * 3.5:.1f}" for index in range(100)])

    runnable = plan_analyses(result, registry=AnalyzerRegistry([_Fake]))
    pending = plan_analyses(numbers)

    assert runnable.summary.selected == 1 and runnable.summary.executable is True
    assert pending.summary.selected >= 1 and pending.summary.executable is False


# Plan as a document ------------------------------------------------------------


def _wide(tmp_path):
    rows = [f"{n},{n * 1.5:.1f},AB-{n:04d},2023-0{1 + n % 9}-1{n % 9}" for n in range(300)]
    return scan_csv(tmp_path, "customer_id,price,code,day", rows, limits=SMALL_K)


def test_the_same_scan_gives_the_same_plan_whatever_the_workers(tmp_path):
    rows = "\n".join(f"{n},{n * 1.5:.1f},AB-{n:04d}" for n in range(400))
    source = write_text(tmp_path, "data.csv", "id,price,code\n" + rows + "\n")
    config = ScanConfig.model_validate({"limits": SMALL_K})

    one = plan_analyses(scan(source, config=config, workers=1))
    two = plan_analyses(scan(source, config=config, workers=2))

    assert one.plan_id == two.plan_id
    assert one.model_dump(mode="json") == two.model_dump(mode="json")


def test_a_plan_has_no_date_and_its_id_follows_its_content(tmp_path):
    result = _wide(tmp_path)

    first = plan_analyses(result)
    again = plan_analyses(result)
    smaller = plan_analyses(
        result, budgets=default_budgets().model_copy(update={"memory_bytes": PARSER_RESERVE_BYTES})
    )

    assert first.plan_id == again.plan_id
    assert first.plan_id != smaller.plan_id
    text = first.model_dump_json()
    assert "started_at" not in text and "generated_at" not in text
    assert first.budgets.memory_bytes == DEFAULT_MEMORY_BUDGET_BYTES


def test_a_plan_holds_no_value_of_the_data(tmp_path):
    rows = [f"SECRET-{n:05d},{n}" for n in range(200)]
    result = scan_csv(tmp_path, "token,n", rows, limits=SMALL_K)

    plan = plan_analyses(result)

    assert "SECRET" not in plan.model_dump_json()
    assert "SECRET" not in plan_text(plan, "data.csv")


def test_a_plan_is_valid_json_that_reads_back(tmp_path):
    plan = plan_analyses(_wide(tmp_path))

    document = json.loads(plan.model_dump_json())

    assert AnalysisPlan.model_validate(document) == plan


def test_every_code_a_plan_writes_has_a_sentence(tmp_path):
    plan = plan_analyses(_wide(tmp_path))

    codes = set()
    for candidate in plan.candidates:
        codes |= {candidate.selection.reason, *candidate.applicability.reasons}
        if candidate.utility is not None:
            codes |= set(candidate.utility.reasons)
    assert codes <= set(REASONS)
    assert reason_text("no_such_code") == "no_such_code"


def test_the_summary_counts_the_candidates_by_decision(tmp_path):
    plan = plan_analyses(_wide(tmp_path))
    states = [c.selection.state for c in plan.candidates]

    assert plan.summary.candidates == len(states)
    assert plan.summary.selected == states.count("selected")
    assert plan.summary.already_satisfied == states.count("already_satisfied")
    assert plan.summary.rejected == states.count("rejected")
    assert plan.common.requires_source is plan.summary.second_pass_required
    assert plan.summary.memory.max >= plan.common.memory_bytes
    ids = [c.id for c in plan.candidates]
    assert len(ids) == len(set(ids))


def test_the_text_of_a_plan_names_what_is_selected_and_what_it_costs(tmp_path):
    plan = plan_analyses(_wide(tmp_path))

    text = plan_text(plan, "data.csv")

    assert text.startswith("Plan for data.csv (plan ")
    assert "Selected:" in text
    assert "numeric_histogram" in text
    assert "not available yet" in text
    assert "A second reading of the source is needed" in text


# Documents and commands --------------------------------------------------------


def test_a_scan_document_gives_the_plan_of_its_scan(tmp_path):
    source = write_text(tmp_path, "data.csv", "id,price\n" + "\n".join(f"{n},{n * 1.5:.1f}" for n in range(100)) + "\n")
    generate_scans([source], output_dir=tmp_path / "scans", force=True)

    from_document = plan_document(tmp_path / "scans" / "data.scan.json")
    from_memory = plan_analyses(scan(source))

    assert from_document.base.facts_sha256 == from_memory.base.facts_sha256
    assert from_document.plan_id == from_memory.plan_id


def test_a_report_is_not_an_input_to_plan(tmp_path):
    # More rows than a Report keeps: it holds a reduced row sample.
    rows = "\n".join(f"{n},{n + 0.5}" for n in range(300))
    source = write_text(tmp_path, "data.csv", "id,price\n" + rows + "\n")
    generate_reports([source], output_dir=tmp_path / "reports", force=True)
    report = next(
        p for p in (tmp_path / "reports").glob("*.json") if p.name != "executions.json"
    )

    with pytest.raises(InputError, match="plan analyses"):
        plan_document(report)


def test_planning_reuses_the_stored_scan_and_runs_no_second_pass(tmp_path):
    source = write_text(tmp_path, "data.csv", "id,price\n" + "\n".join(f"{n},{n * 1.5:.1f}" for n in range(50)) + "\n")

    first = generate_plans([source])
    second = generate_plans([source])

    assert [s.reused for s in first.successes] == [False]
    assert [s.reused for s in second.successes] == [True]
    assert first.successes[0].plan.plan_id == second.successes[0].plan.plan_id
    assert not first.failures
    assert not list(tmp_path.glob("*.json")), "a plan writes nothing beside the source"


def test_scan_plan_prints_the_plan_and_writes_no_file_beside_the_source(tmp_path):
    source = write_text(tmp_path, "data.csv", "id,price\n" + "\n".join(f"{n},{n * 1.5:.1f}" for n in range(50)) + "\n")

    result = runner.invoke(app, ["scan", str(source), "--plan", "--no-progress"])

    assert result.exit_code == 0, result.output
    assert "Plan for data.csv" in result.stdout
    assert "Scan: " in result.stderr and "(scanned)" in result.stderr
    assert not list(tmp_path.glob("*.json"))
    again = runner.invoke(app, ["scan", str(source), "--plan", "--no-progress"])
    assert "(reused)" in again.stderr


@pytest.mark.parametrize("option", [["-o", "x.json"], ["-d", "out"], ["--force"], ["--counters"]])
def test_scan_plan_refuses_the_options_that_write(tmp_path, option):
    source = write_text(tmp_path, "data.csv", "id\n1\n")

    result = runner.invoke(app, ["scan", str(source), "--plan", *option])

    assert result.exit_code == 2
    assert "cannot be used with --plan" in result.output


def test_scan_plan_reports_a_missing_source_with_the_scan_exit_code(tmp_path):
    result = runner.invoke(app, ["scan", str(tmp_path / "absent.csv"), "--plan"])

    assert result.exit_code == 4


def test_the_cell_budget_does_not_stop_an_analysis_that_reads_no_source(tmp_path):
    rows = [f"AB-{index:04d}" for index in range(30)]
    result = scan_csv(tmp_path, "code", rows)
    capped = default_budgets().model_copy(update={"max_cells": 1})

    candidate = _state(plan_analyses(result, budgets=capped), "pattern_validation", "code")

    assert candidate.execution.requires_source is False
    assert candidate.selection.state == "selected"


def test_a_frequency_measure_that_is_off_is_not_reported_as_high_cardinality(tmp_path):
    rows = [str(index % 300) for index in range(900)]
    result = scan_csv(tmp_path, "qty", rows, limits={"max_samples": 20})
    result = with_field(result, "qty", values=result.datasets[0].fields[0].values.model_copy(update={"frequencies": Disabled()}))

    candidate = _state(plan_analyses(result), "exact_frequencies", "qty")

    assert candidate.applicability.reasons == ["measure_unavailable"]


def test_a_wide_scan_is_planned_within_the_budget(tmp_path):
    header = ",".join(f"id_{n}" for n in range(300))
    rows = [",".join(f"{n}-{row}" for n in range(300)) for row in range(120)]
    result = scan_csv(tmp_path, header, rows, limits={"max_distinct_per_field": 50})

    plan = plan_analyses(result)

    assert plan.summary.candidates >= 900
    assert plan.summary.memory.max <= plan.budgets.memory_bytes
