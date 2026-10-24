# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second pass: replay of the first pass's reading, the document, the keys,
the service and the command (lot 7a, design 20.4 and 20.7)."""

import json
import random
import subprocess
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import jsonschema
import pytest
from planner_helpers import scan_csv, with_field
from scan_helpers import write_json, write_text
from second_pass_helpers import deep_csv, entry, forced_plan
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.config import DeepSettings, deep_settings, load_config_layers
from tabalyst.deep_service import (
    ConfirmationRequired,
    execute_deep,
    generate_deep,
    prepare_deep,
)
from tabalyst.errors import ConfigurationError
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.models import Complete, Disabled, NumericStats
from tabalyst.scanner.planner.analyzers.patterns import PatternValidation
from tabalyst.scanner.secondpass import (
    EXECUTABLE,
    analysis_key,
    deep_document,
    deep_path_for,
    load_deep,
    pending_candidates,
    run_second_pass,
)
from tabalyst.scanner.secondpass import models as deep_models
from tabalyst.scanner.secondpass.accumulators import BinAccumulator
from tabalyst.scanner.secondpass.bins import BinEdges, linear_edges, quantile_edges
from tabalyst.scanner.secondpass.schema import (
    SCHEMA_FILE,
    deep_schema,
    deep_schema_text,
)
from tabalyst.source_guard import StalePlan

pytestmark = pytest.mark.scan_json_lot("7a")

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "examples" / "datasets"
runner = CliRunner()


def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))


# Replay of the first pass's reading -----------------------------------------------


def test_the_numbers_of_a_text_field_are_read_as_the_scan_read_them(tmp_path):
    rows = ['"1,234.50"', '"2,000.00"', "10.5", "999", "NA", '""', "  42  ", "3e2", "0.000001"] * 20
    result, _, outcome = deep_csv(
        tmp_path, "amount", rows, values={"null_markers": ["NA"]}, deep=DeepSettings(bins=10)
    )

    histogram = entry(outcome, "numeric_histogram", "amount")

    # The check against the Scan's own count would have failed the analysis.
    assert histogram.status == "complete", histogram.detail
    assert histogram.result.count == result.datasets[0].fields[0].numeric.value.count == 140


def test_the_lengths_are_those_of_the_analytical_text_of_the_scan(tmp_path):
    texts = ["abc", "  abc  ", "a  b", "é", "é", " x", "NA", '""', "long text here"] * 7
    source = write_text(tmp_path, "data.csv", "t\n" + "\n".join(texts) + "\n")
    scanned = scan(source, config=ScanConfig.model_validate({"values": {"null_markers": ["NA"]}}))
    field = scanned.datasets[0].fields[0]
    off = with_field(scanned, "t", string_lengths=Disabled())

    outcome = run_second_pass(off, source, forced_plan(off))

    lengths = entry(outcome, "length_distribution", "t")
    assert lengths.status == "complete", lengths.detail
    assert lengths.result.model_dump(exclude={"kind"}) == field.string_lengths.value.model_dump()


def test_a_dense_histogram_of_a_field_that_holds_a_decimal_fails_alone(tmp_path):
    rows = [str(n % 40) for n in range(100)] + ["2.5"]
    _, _, outcome = deep_csv(tmp_path, "n", rows)

    failed = entry(outcome, "numeric_histogram", "n")

    assert failed.status == "failed" and failed.reason == "scan_mismatch"
    assert "non_integral_value" in failed.detail
    assert outcome.document.status == "partial"


def test_a_count_that_disagrees_with_the_scan_fails_that_analysis_only(tmp_path):
    result = scan_csv(tmp_path, "age,price", [f"{20 + n % 50},{n * 1.5:.1f}" for n in range(200)])
    field = result.datasets[0].fields[0]
    forged = field.numeric.value.model_copy(update={"count": field.numeric.value.count + 1})
    tampered = with_field(result, "age", numeric=Complete[NumericStats](value=forged))
    plan = forced_plan(tampered)

    outcome = run_second_pass(tampered, tmp_path / "data.csv", plan)

    assert entry(outcome, "numeric_histogram", "age").reason == "scan_mismatch"
    assert entry(outcome, "numeric_histogram", "price").status == "complete"


def test_an_analysis_that_raises_fails_alone_without_its_message(tmp_path, monkeypatch):
    def broken(self, number, count):
        raise RuntimeError("secret value 123456")

    monkeypatch.setattr(BinAccumulator, "add", broken)

    # The shape of the numbers counts in bins too: it would fail its route with the histogram.
    result = scan_csv(tmp_path, "age,price", [f"{20 + n % 50},{n * 1.5:.1f}" for n in range(200)])
    plan = forced_plan(result)
    plan = plan.model_copy(
        update={"candidates": [c for c in plan.candidates if c.analyzer != "numeric_shape"]}
    )
    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    price = entry(outcome, "numeric_histogram", "price")
    assert price.status == "failed" and price.reason == "analysis_error"
    assert price.detail == "RuntimeError" and "secret" not in outcome.document.model_dump_json()
    assert entry(outcome, "numeric_histogram", "age").status == "complete"


@pytest.mark.parametrize(
    "name", ["basic.csv", "insurance-customers.csv", "orders.json", "web-events.jsonl"]
)
def test_the_examples_replay_without_a_disagreement_with_their_scans(name):
    scanned = scan(INPUT / name, workers=1)
    plan = forced_plan(scanned)

    outcome = run_second_pass(scanned, INPUT / name, plan)

    failed = [(a.id, a.reason, a.detail) for a in outcome.document.analyses if a.status != "complete"]
    assert not failed
    assert outcome.document.run.source_verified is outcome.read_source


def test_a_workbook_replays_like_its_scan():
    config = ScanConfig.model_validate({"excel": {"dataset_path": "$.Orders"}})
    scanned = scan(INPUT / "sales.xlsx", config=config, workers=1)

    outcome = run_second_pass(scanned, INPUT / "sales.xlsx", forced_plan(scanned))

    assert outcome.document.analyses
    assert all(a.status == "complete" for a in outcome.document.analyses)


def test_json_numbers_and_numeric_strings_are_counted_together(tmp_path):
    records = [{"n": n % 30, "p": n * 1.25 if n % 2 else f"{n * 1.25:.2f}"} for n in range(300)]
    source = write_json(tmp_path, "records.json", records)
    scanned = scan(source, workers=1)

    outcome = run_second_pass(scanned, source, forced_plan(scanned))

    dense = entry(outcome, "numeric_histogram", "n")
    assert dense.status == "complete" and dense.result.count == 300
    assert {item.value for item in dense.result.values} == set(range(30))


def test_the_second_pass_does_not_depend_on_the_workers_of_the_first(tmp_path):
    rows = [f"{n % 70},{n * 0.7:.1f}" for n in range(3000)]
    one = scan_csv(tmp_path, "a,b", rows)
    two = scan(tmp_path / "data.csv", workers=2)

    first = run_second_pass(one, tmp_path / "data.csv", forced_plan(one))
    second = run_second_pass(two, tmp_path / "data.csv", forced_plan(two))

    assert [a.model_dump() for a in first.document.analyses] == [
        a.model_dump() for a in second.document.analyses
    ]
    assert first.document.run.workers == 1


def test_two_runs_give_the_same_analyses(tmp_path):
    result = scan_csv(tmp_path, "x", [f"{n * 0.3:.1f}" for n in range(500)])
    plan = forced_plan(result)

    first = run_second_pass(result, tmp_path / "data.csv", plan)
    again = run_second_pass(result, tmp_path / "data.csv", plan)

    assert first.document.analyses == again.document.analyses


# Bins -------------------------------------------------------------------------------


def test_a_value_on_an_edge_that_a_float_cannot_hold_is_placed_exactly():
    edges = BinEdges(linear_edges(Fraction(0), Fraction(1), 3))

    # 1/3 is not representable: Decimal('0.333...') and the float of 1/3 are neighbours.
    assert edges.index(Decimal("0.3333333333333333")) == 0
    assert edges.index(Decimal("0.33333333333333333333333333333333333")) == 0
    assert edges.index(Decimal("0.3333333333333333333333333333333334")) == 1
    assert edges.index(Decimal(1)) == 2 and edges.index(Decimal("1.0000001")) == 3
    assert edges.index(Decimal("-0.1")) == -1 and edges.index(10**400) == 3


def test_a_random_stream_lands_in_the_bins_an_exact_search_gives_it():
    rng = random.Random(3)
    edges = BinEdges(linear_edges(Fraction(-7, 3), Fraction(1000, 7), 61))
    for _ in range(4000):
        number = Decimal(f"{rng.uniform(-2.3, 142.0):.{rng.randint(0, 12)}f}")
        exact = Fraction(number)
        expected = max(i for i in range(61) if edges.edges[i] <= exact)
        assert edges.index(number) == expected


def test_quantile_edges_merge_ties_and_refuse_a_sample_without_spread():
    sample = [Fraction(n) for n in [1, 1, 1, 1, 2, 2, 2, 3, 9, 9]]

    edges = quantile_edges(Fraction(0), Fraction(10), 5, sample)

    assert edges == [0, 1, 2, 3, 9, 10] or edges == [Fraction(v) for v in edges]
    assert edges == sorted(set(edges))
    assert quantile_edges(Fraction(0), Fraction(10), 5, [Fraction(0)] * 10) is None
    assert quantile_edges(Fraction(0), Fraction(10), 5, []) is None


# Keys and documents -------------------------------------------------------------------


def _selected(plan):
    return [c for c in plan.candidates if c.selection.state == "selected"]


def test_a_key_follows_the_bins_and_the_scan_and_not_the_budget(tmp_path):
    result = scan_csv(tmp_path, "x", [f"{n * 0.3:.1f}" for n in range(500)])
    keys = {}
    for bins in (20, 30):
        plan = forced_plan(result, DeepSettings(bins=bins))
        (candidate,) = [c for c in _selected(plan) if c.analyzer == "numeric_histogram"]
        keys[bins] = analysis_key(plan.base, candidate)
    plan = forced_plan(result, DeepSettings(bins=20))
    (candidate,) = [c for c in _selected(plan) if c.analyzer == "numeric_histogram"]
    small = plan.budgets.model_copy(update={"memory_bytes": 1})
    other = scan_csv(tmp_path, "x", [f"{n * 0.4:.1f}" for n in range(500)])
    (other_candidate,) = [
        c
        for c in _selected(forced_plan(other, DeepSettings(bins=20)))
        if c.analyzer == "numeric_histogram"
    ]

    assert keys[20] != keys[30]
    assert analysis_key(plan.base, candidate) == keys[20]
    assert small != plan.budgets
    assert analysis_key(forced_plan(other, DeepSettings(bins=20)).base, other_candidate) != keys[20]


def test_a_stored_document_that_is_not_ours_is_ignored_not_migrated(tmp_path):
    result = scan_csv(tmp_path, "x", [str(n % 30) for n in range(200)])
    document = run_second_pass(result, tmp_path / "data.csv", forced_plan(result)).document
    text = deep_document(document)
    good = write_text(tmp_path, "good.deep.json", text)

    assert load_deep(good) == document
    assert load_deep(tmp_path / "missing.json") is None
    assert load_deep(write_text(tmp_path, "garbage.json", "{not json")) is None
    assert load_deep(write_text(tmp_path, "list.json", "[1]")) is None
    older = json.loads(text) | {"format_revision": 0}
    assert load_deep(write_json(tmp_path, "old.json", older)) is None
    broken = json.loads(text) | {"analyses": "no"}
    assert load_deep(write_json(tmp_path, "broken.json", broken)) is None


def test_a_plan_of_another_scan_is_refused_even_when_nothing_is_to_be_read(tmp_path):
    (tmp_path / "other").mkdir()
    first = scan_csv(tmp_path, "x", [str(n % 30) for n in range(200)])
    second = scan_csv(tmp_path / "other", "x", [str(n % 31) for n in range(200)])
    plan = forced_plan(first)
    stored = run_second_pass(first, tmp_path / "data.csv", plan).document

    with pytest.raises(StalePlan):
        run_second_pass(second, tmp_path / "other" / "data.csv", plan, previous=stored)


def test_a_document_of_another_source_is_not_reused(tmp_path):
    (tmp_path / "other").mkdir()
    first = scan_csv(tmp_path, "x", [str(n % 30) for n in range(200)])
    second = scan_csv(tmp_path / "other", "x", [str(n % 31) for n in range(200)])
    stored = run_second_pass(first, tmp_path / "data.csv", forced_plan(first)).document
    plan = forced_plan(second)

    # The histogram, the shape of the numbers and the column followed by position.
    assert len(pending_candidates(plan, stored)) == 3
    outcome = run_second_pass(second, tmp_path / "other" / "data.csv", plan, previous=stored)
    assert outcome.reused == () and outcome.read_source


def test_the_document_validates_against_its_committed_schema(tmp_path):
    rows = [f"{n % 70},{n * 0.7:.1f},w{n}" for n in range(500)]
    result = scan_csv(tmp_path, "a,b,w", rows)
    result = with_field(result, "w", string_lengths=Disabled())
    document = run_second_pass(result, tmp_path / "data.csv", forced_plan(result)).document

    jsonschema.Draft202012Validator(deep_schema()).validate(
        json.loads(deep_document(document))
    )

    committed = ROOT / "src" / "tabalyst" / "schemas" / SCHEMA_FILE
    assert committed.read_text(encoding="utf-8") == deep_schema_text()
    outcome = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_schema.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert outcome.returncode == 0, outcome.stdout + outcome.stderr
    assert deep_models.FORMAT == "tabalyst.scan.deep" and deep_models.FORMAT_REVISION == 4


def test_only_the_analyzers_the_executor_runs_are_named_executable():
    from tabalyst.scanner.planner import default_registry

    assert EXECUTABLE == {a.id for a in default_registry().runnable()}


# Settings -----------------------------------------------------------------------------


def test_the_deep_settings_are_validated_and_do_not_change_the_scan(tmp_path):
    good = write_json(tmp_path, "good.json", {"deep": {"bins": 40, "bin_strategy": "sample_quantile"}})
    unknown = write_json(tmp_path, "unknown.json", {"deep": {"bin": 4}})
    low = write_json(tmp_path, "low.json", {"deep": {"bins": 1}})

    assert deep_settings([good]) == DeepSettings(bins=40, bin_strategy="sample_quantile")
    assert deep_settings([]) == DeepSettings()
    for bad in (unknown, low):
        with pytest.raises(ConfigurationError):
            load_config_layers([bad])
    assert DeepSettings(bins=40).sha256() != DeepSettings().sha256()


# Service and command --------------------------------------------------------------------


def _ids(tmp_path, count=2_000):
    lines = ["n", *[str(1000 + n) for n in range(count)]]
    return write_text(tmp_path, "ids.csv", "\n".join(lines) + "\n")


def _require_confirmation(monkeypatch):
    """Make every second pass cross the time threshold, as a long one would."""
    from tabalyst import deep_service

    real = deep_service.plan_second_pass
    combine = deep_service.combine_confirmations

    def plan(*args, **kwargs):
        return real(*args, threshold_seconds=0.0, **kwargs)

    def together(items):
        return combine(items, threshold_seconds=0.0)

    monkeypatch.setattr(deep_service, "plan_second_pass", plan)
    monkeypatch.setattr(deep_service, "combine_confirmations", together)


def test_the_api_never_prompts_and_asks_for_an_explicit_confirmation(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    _require_confirmation(monkeypatch)
    source = _ids(tmp_path)

    prepared = prepare_deep([source])
    with pytest.raises(ConfirmationRequired) as refused:
        execute_deep(prepared)
    with pytest.raises(ConfirmationRequired):
        generate_deep([source])

    assert prepared.requires_confirmation
    assert "time_over_threshold" in refused.value.confirmation.reasons
    assert not prepared.jobs[0].deep_path.exists()
    done = execute_deep(prepared, confirmed=True)
    assert len(done.successes) == 1 and prepared.jobs[0].deep_path.exists()


def test_a_run_with_everything_stored_never_asks_whatever_the_estimate(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    source = _ids(tmp_path)
    generate_deep([source])
    _require_confirmation(monkeypatch)

    prepared = prepare_deep([source])

    assert prepared.jobs[0].pending == 0
    assert prepared.requires_confirmation is False
    assert execute_deep(prepared).successes[0].outcome.read_source is False


def test_the_progress_of_the_second_pass_is_named_while_the_bytes_are_read(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    monkeypatch.setattr("tabalyst.progress._BYTE_PROGRESS_MIN_STEP", 1)
    prepared = prepare_deep([_ids(tmp_path, count=5_000)])
    events = []

    execute_deep(prepared, on_progress=events.append)

    reading = [e for e in events if e.phase.value == "reading" and e.bytes_read]
    assert len(reading) > 2 and {e.detail for e in reading} == {"second pass"}


def test_what_a_field_remembers_is_what_the_planner_charges_for(tmp_path):
    from tabalyst.scanner.planner.costmodel import REPLAY_MEMO_ENTRIES
    from tabalyst.scanner.secondpass.replay import CellReader
    from tabalyst.scanner.secondpass.routing import FieldRoute

    assert FieldRoute(CellReader(ScanConfig()), None, None).memo_entries == REPLAY_MEMO_ENTRIES


def test_the_command_runs_the_second_pass_and_names_it(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    source = _ids(tmp_path)

    first = runner.invoke(app, ["scan", str(source), "--deep"])
    again = runner.invoke(app, ["scan", str(source), "--deep"])

    assert first.exit_code == 0, first.output
    assert "(scanned)" in first.output and "reading the source again for 2 analyses" in first.output
    # The four-digit ids are eligible for patterns: their validation is the third
    # analysis, computed from the samples without reading the source.
    assert "Second pass:" in first.output and "3 computed, 0 reused" in first.output
    assert again.exit_code == 0
    assert "(reused)" in again.output and "every result is already stored" in again.output
    assert "0 computed, 3 reused, unchanged" in again.output


def test_the_command_has_nothing_to_add_when_the_scan_answers_everything(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    source = write_text(tmp_path, "t.csv", "t\n" + "\n".join("abc" for _ in range(50)) + "\n")

    result = runner.invoke(app, ["scan", str(source), "--deep"])

    assert result.exit_code == 0 and "nothing to add" in result.output


def test_a_costly_second_pass_outside_a_terminal_stops_with_exit_code_3(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    _require_confirmation(monkeypatch)
    source = _ids(tmp_path)

    refused = runner.invoke(app, ["scan", str(source), "--deep"])
    allowed = runner.invoke(app, ["scan", str(source), "--deep", "--yes"])

    assert refused.exit_code == 3
    assert "Nothing was started" in refused.output and "--yes" in refused.output
    assert allowed.exit_code == 0 and "Second pass:" in allowed.output


def test_a_terminal_asks_and_a_no_stops_with_exit_code_3(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    _require_confirmation(monkeypatch)
    monkeypatch.setattr("tabalyst.cli.confirm.is_interactive", lambda: True)
    source = _ids(tmp_path)

    declined = runner.invoke(app, ["scan", str(source), "--deep"], input="n\n")
    accepted = runner.invoke(app, ["scan", str(source), "--deep"], input="y\n")

    assert declined.exit_code == 3 and "Start it?" in declined.output
    assert "Nothing was started" in declined.output
    assert accepted.exit_code == 0 and "Second pass:" in accepted.output


def test_several_sources_are_asked_once_and_one_failure_stops_only_itself(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    _require_confirmation(monkeypatch)
    first = write_text(tmp_path, "one.csv", "n\n" + "\n".join(str(n) for n in range(100, 600)) + "\n")
    second = write_text(tmp_path, "two.csv", "n\n" + "\n".join(str(n) for n in range(100, 700)) + "\n")
    prepared = prepare_deep([first, second])
    assert prepared.confirmation.reasons == ("time_over_threshold",)
    first.write_text("n\n" + "\n".join(str(n + 1) for n in range(100, 600)) + "\n", encoding="utf-8", newline="")
    assert first.stat().st_size == prepared.jobs[0].scan.result.source.size_bytes

    result = execute_deep(prepared, confirmed=True)

    assert [s.job.source for s in result.successes] == [second]
    assert [f.job.source for f in result.failures] == [first]


def test_the_command_exits_4_when_the_source_changed_after_its_scan(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    source = _ids(tmp_path)
    runner.invoke(app, ["scan", str(source)])
    deep_calls = []

    from tabalyst import deep_service

    real = deep_service.run_second_pass

    def change_then_run(scan_result, path, plan, **kwargs):
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("1000", "2000"), encoding="utf-8", newline="")
        deep_calls.append(path)
        return real(scan_result, path, plan, **kwargs)

    monkeypatch.setattr(deep_service, "run_second_pass", change_then_run)

    result = runner.invoke(app, ["scan", str(source), "--deep"])

    assert deep_calls and result.exit_code == 4
    assert "discarded" in result.output and "Second pass:" not in result.output


def test_a_chosen_scan_file_gets_its_second_pass_beside_it(tmp_path):
    source = _ids(tmp_path)
    target = tmp_path / "out" / "ids.scan.json"

    result = runner.invoke(app, ["scan", str(source), "--deep", "-o", str(target)])

    assert result.exit_code == 0, result.output
    assert target.exists() and (tmp_path / "out" / "ids.deep.json").exists()
    assert deep_path_for(target).name == "ids.deep.json"


def test_the_plan_of_a_forced_run_says_what_cannot_run_yet(tmp_path, monkeypatch):
    _home(monkeypatch, tmp_path)
    lines = ["customer_id,quantity", *[f"C{n:06d},{n % 50}" for n in range(2_000)]]
    source = write_text(tmp_path, "customers.csv", "\n".join(lines) + "\n")
    only = write_text(
        tmp_path, "codes.csv", "\n".join(["customer_id", *[f"C{n:06d}" for n in range(2_000)]]) + "\n"
    )

    # Every analyzer has an executor since lot 7c: one without stands in for a
    # future analysis the plan names but this version cannot run.
    runnable = runner.invoke(app, ["scan", str(_ids(tmp_path)), "--plan", "--deep"])
    monkeypatch.setattr(PatternValidation, "available", False)
    mixed = runner.invoke(app, ["scan", str(source), "--plan", "--deep"])
    waiting = runner.invoke(app, ["scan", str(only), "--plan", "--deep"])

    assert mixed.exit_code == waiting.exit_code == runnable.exit_code == 0
    assert "cannot run in this version" in mixed.stdout
    assert "tabalyst scan --deep runs the others" in mixed.stdout
    assert "None of the selected analyses can run in this version." in waiting.stdout
    assert "in this version" not in runnable.stdout
