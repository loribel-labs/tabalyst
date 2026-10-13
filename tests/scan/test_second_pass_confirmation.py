# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Estimate, confirmation and gate of a second pass (lot 6b, rule R1, design 20.3)."""

import json

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_text
from typer.testing import CliRunner

from tabalyst import generate_scans
from tabalyst.cli import app
from tabalyst.cli.confirm import (
    EXIT_CONFIRMATION_REQUIRED,
    Decision,
    confirm_second_pass,
    is_interactive,
)
from tabalyst.plan_service import generate_plans
from tabalyst.scanner.planner import (
    AnalysisRequest,
    Confirmation,
    TimeEstimate,
    combine_confirmations,
    confirmation_for,
    default_budgets,
    estimate_time,
    plan_analyses,
    plan_second_pass,
)
from tabalyst.scanner.planner.costmodel import (
    DEFAULT_CONFIRM_SECONDS,
    PARSER_RESERVE_BYTES,
)
from tabalyst.scanner.planner.reasons import REASONS

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage"))


def _identifiers(tmp_path):
    rows = [f"A{n:07d},B{n:07d}" for n in range(5_000)]
    return scan_csv(tmp_path, "id_a,id_b", rows, limits={"max_distinct_per_field": 50})


def _slower(result, reading: float):
    timings = result.run.timings.model_copy(update={"reading": reading})
    return result.model_copy(update={"run": result.run.model_copy(update={"timings": timings})})


# Estimate ----------------------------------------------------------------------


def test_no_time_is_estimated_when_no_selected_analysis_reads_the_source(tmp_path):
    result = scan_csv(tmp_path, "state", [f"state_{n % 17:02d}" for n in range(500)])
    plan = plan_analyses(result)

    assert plan.common.requires_source is False
    assert estimate_time(plan, result) is None
    assert confirmation_for(plan, None).required is False


def test_the_estimate_is_a_range_that_follows_the_reading_of_the_first_pass(tmp_path):
    result = _identifiers(tmp_path)
    plan = plan_analyses(result)

    quick = estimate_time(plan, _slower(result, 2.0))
    slow = estimate_time(plan, _slower(result, 200.0))

    assert 0 < quick.low_seconds < quick.high_seconds
    assert slow.high_seconds > 20 * quick.high_seconds
    assert slow.high_seconds >= 200.0
    assert slow.low_seconds < 200.0


def test_the_estimate_is_not_part_of_the_plan(tmp_path):
    result = _identifiers(tmp_path)

    first = plan_analyses(result)
    second = plan_analyses(_slower(result, 500.0))

    assert first.plan_id == second.plan_id
    assert "seconds" not in json.dumps(first.model_dump(mode="json"))


# Confirmation ------------------------------------------------------------------


def test_what_the_planner_picks_by_itself_never_asks_for_a_confirmation(tmp_path):
    result = _slower(_identifiers(tmp_path), 0.5)

    second = plan_second_pass(result)

    assert second.plan.summary.beyond_automatic == []
    assert second.requires_confirmation is False
    assert second.confirmation.reasons == ()


def test_a_long_estimate_asks_for_a_confirmation_by_its_upper_bound(tmp_path):
    result = _identifiers(tmp_path)
    plan = plan_analyses(result)

    below = confirmation_for(plan, TimeEstimate(10, DEFAULT_CONFIRM_SECONDS - 1))
    above = confirmation_for(plan, TimeEstimate(10, DEFAULT_CONFIRM_SECONDS))

    assert below.required is False
    assert above.required is True
    assert above.reasons == ("time_over_threshold",)


def test_a_slow_source_makes_a_default_second_pass_ask(tmp_path):
    result = _slower(_identifiers(tmp_path), 400.0)

    second = plan_second_pass(result)

    assert second.requires_confirmation is True
    assert second.confirmation.reasons == ("time_over_threshold",)
    assert second.estimate.high_seconds >= DEFAULT_CONFIRM_SECONDS


def test_a_forced_plan_or_a_request_over_the_automatic_memory_asks_and_says_why(tmp_path):
    result = _identifiers(tmp_path)
    # Room for the reading and nothing more: only what is asked or forced goes on.
    budgets = default_budgets().model_copy(update={"automatic_memory_bytes": PARSER_RESERVE_BYTES})

    automatic = plan_second_pass(result, budgets=budgets)
    forced = plan_second_pass(result, forced=True, budgets=budgets)
    asked = plan_second_pass(
        result, requests=[AnalysisRequest("exact_distinct")], budgets=budgets
    )

    assert automatic.requires_confirmation is False
    for second in (forced, asked):
        assert second.requires_confirmation is True
        assert second.confirmation.reasons == ("memory_over_automatic",)
        assert second.confirmation.memory_max_bytes == second.plan.summary.memory.max


def test_every_reason_of_a_confirmation_has_a_sentence():
    for code in (
        "memory_over_automatic",
        "cells_over_automatic",
        "cpu_over_automatic",
        "time_over_threshold",
    ):
        assert REASONS[code] != code


def test_a_batch_asks_once_with_the_total(tmp_path):
    each = Confirmation(False, (), 100, TimeEstimate(40, 70))
    other = Confirmation(False, (), 300, TimeEstimate(30, 60))

    together = combine_confirmations([each, other])

    assert together.estimate == TimeEstimate(70, 130)
    assert together.memory_max_bytes == 300
    assert together.required is True
    assert together.reasons == ("time_over_threshold",)
    assert combine_confirmations([each]).required is False


def test_a_batch_keeps_the_reasons_of_its_files_once(tmp_path):
    memory = Confirmation(True, ("memory_over_automatic",), 900, None)
    twice = combine_confirmations([memory, memory])

    assert twice.reasons == ("memory_over_automatic",)
    assert combine_confirmations([]).required is False


# Gate --------------------------------------------------------------------------


def _needed(reason: str = "memory_over_automatic") -> Confirmation:
    return Confirmation(True, (reason,), 600 * 1024 * 1024, TimeEstimate(100, 400))


def test_nothing_is_asked_when_nothing_needs_confirming(capsys):
    def never(text):
        raise AssertionError("asked")

    decision = confirm_second_pass(
        Confirmation(False, (), 0, None), interactive=True, ask=never
    )

    assert decision is Decision.PROCEED
    assert capsys.readouterr().err == ""


def test_yes_goes_ahead_without_asking_even_outside_a_terminal(capsys):
    decision = confirm_second_pass(_needed(), assume_yes=True, interactive=False)

    assert decision is Decision.PROCEED
    assert capsys.readouterr().err == ""


def test_in_a_terminal_the_estimate_is_shown_and_the_answer_decides(capsys):
    asked = []

    def answer(text):
        asked.append(text)
        return True

    assert confirm_second_pass(_needed(), interactive=True, ask=answer) is Decision.PROCEED
    assert confirm_second_pass(_needed(), interactive=True, ask=lambda text: False) is Decision.DECLINED
    shown = capsys.readouterr().err
    assert "Estimated time: 2 min to 7 min" in shown
    assert "above what an automatic choice may take" in shown
    assert len(asked) == 1


def test_outside_a_terminal_nothing_is_asked_and_the_operation_is_refused(capsys):
    def never(text):
        raise AssertionError("asked")

    decision = confirm_second_pass(_needed(), interactive=False, ask=never)

    assert decision is Decision.REFUSED
    assert "--yes" in capsys.readouterr().err
    assert EXIT_CONFIRMATION_REQUIRED == 3


def test_the_default_answer_is_no(monkeypatch):
    seen = {}

    def fake(text, default, err):
        seen["default"] = default
        return False

    monkeypatch.setattr("tabalyst.cli.confirm.typer.confirm", fake)

    assert confirm_second_pass(_needed(), interactive=True) is Decision.DECLINED
    assert seen["default"] is False


def test_a_terminal_needs_both_input_and_error_output(monkeypatch):
    for stdin, stderr, expected in [(True, True, True), (True, False, False), (False, True, False)]:
        monkeypatch.setattr("sys.stdin", type("In", (), {"isatty": lambda self, v=stdin: v})())
        monkeypatch.setattr("sys.stderr", type("Err", (), {"isatty": lambda self, v=stderr: v})())
        assert is_interactive() is expected


# The command and the service ---------------------------------------------------


def test_scan_plan_deep_shows_the_forced_plan_and_the_confirmation_it_would_ask(tmp_path):
    rows = "\n".join(f"A{n:07d},{n * 1.5:.1f}" for n in range(3_000))
    source = write_text(tmp_path, "ids.csv", "id,price\n" + rows + "\n")

    plain = runner.invoke(app, ["scan", str(source), "--plan"])
    deep = runner.invoke(app, ["scan", str(source), "--plan", "--deep"])

    assert plain.exit_code == 0 and deep.exit_code == 0
    assert "Estimated time:" in plain.stdout
    assert "Running it would not ask for a confirmation." in plain.stdout
    assert "forced" in deep.stdout
    assert "forced" not in plain.stdout


def test_yes_only_goes_with_deep_and_without_plan(tmp_path):
    source = write_text(tmp_path, "t.csv", "t\na\n")

    alone = runner.invoke(app, ["scan", str(source), "--plan", "--yes"])
    planned = runner.invoke(app, ["scan", str(source), "--plan", "--deep", "--yes"])

    assert alone.exit_code == planned.exit_code == 2
    assert "--yes" in alone.output and "--yes" in planned.output


def test_several_sources_give_one_confirmation_for_all_of_them(tmp_path):
    first = write_text(tmp_path, "one.csv", "id\n" + "\n".join(f"A{n:06d}" for n in range(2_000)) + "\n")
    second = write_text(tmp_path, "two.csv", "id\n" + "\n".join(f"B{n:06d}" for n in range(2_000)) + "\n")

    batch = generate_plans([first, second], forced=True)
    shown = runner.invoke(app, ["scan", str(first), str(second), "--plan", "--deep"])

    assert len(batch.successes) == 2
    assert batch.confirmation.memory_max_bytes == max(
        s.confirmation.memory_max_bytes for s in batch.successes
    )
    assert batch.requires_confirmation is False
    assert "All together:" in shown.stdout


def test_planning_never_runs_a_pass_or_asks(tmp_path):
    source = write_text(tmp_path, "ids.csv", "id\n" + "\n".join(f"A{n:06d}" for n in range(500)) + "\n")
    generate_scans([source], project_storage=True)

    batch = generate_plans([source], forced=True)

    assert batch.successes[0].reused is True
    assert batch.successes[0].plan.objective.forced is True
