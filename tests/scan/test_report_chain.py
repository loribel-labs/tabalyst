# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second pass inside the Report: modes, confirmation, scan documents without
a source (design 20.1, 20.3, 18.2; rule R1)."""

import functools
import json
import shutil

import jsonschema
import pytest
from scan_helpers import write_json, write_text
from typer.testing import CliRunner

from tabalyst import generate_reports, report_chain, report_service
from tabalyst.cli import app
from tabalyst.deep_store import ConfirmationRequired
from tabalyst.report_schema import report_schema
from tabalyst.scan_document import load_base
from tabalyst.scanner.readers import factory
from tabalyst.scanner.secondpass import executor
from tabalyst.service import analyze, analyze_scan
from tabalyst.source_guard import StaleSource

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _customers(directory, name="customers.csv", rows=1_200):
    lines = ["id,code,amount,signed"]
    for n in range(rows):
        lines.append(
            f"C{n:06d},AB{n % 900 + 100},{(n * 37) % 997}.{n % 100:02d},"
            f"2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}"
        )
    return write_text(directory, name, "\n".join(lines) + "\n")


def _costly(monkeypatch):
    """A second pass whose estimate always passes the threshold of rule R1."""
    original = report_chain.plan_second_pass
    monkeypatch.setattr(
        report_chain, "plan_second_pass", functools.partial(original, threshold_seconds=0.0)
    )
    combine = report_service.combine_confirmations
    monkeypatch.setattr(
        report_service, "combine_confirmations", functools.partial(combine, threshold_seconds=0.0)
    )


def _readings(monkeypatch):
    opened = []

    def counting(path, config, on_bytes):
        opened.append(path)
        return factory.open_reader(path, config, on_bytes)

    monkeypatch.setattr(executor, "open_reader", counting)
    return opened


def _document(path):
    return json.loads(path.read_text(encoding="utf-8"))


# Modes -------------------------------------------------------------------------


def test_the_report_with_its_analyses_is_a_valid_document_the_base_loader_reads(tmp_path):
    source = _customers(tmp_path)
    assert runner.invoke(app, ["report", str(source)]).exit_code == 0
    path = tmp_path / "customers.json"

    document = _document(path)

    jsonschema.Draft202012Validator(report_schema()).validate(document)
    assert "analyses" in document
    assert load_base(path).datasets[0].fields  # the loader ignores `analyses`


def test_a_configuration_can_turn_the_second_pass_off_for_a_script(tmp_path, monkeypatch):
    source = _customers(tmp_path)
    off = write_json(tmp_path, "off.json", {"deep": {"mode": "off"}})
    opened = _readings(monkeypatch)

    result = runner.invoke(app, ["report", str(source), "-c", str(off)])

    assert result.exit_code == 0, result.output
    analyses = _document(tmp_path / "customers.json")["analyses"]
    assert analyses == {"mode": "off", "outcome": "disabled", "reason": "deep.mode is off"}
    assert opened == [] and "off (deep.mode is off)" in result.output


def test_a_tiny_enumeration_leaves_nothing_for_the_second_pass(tmp_path):
    source = write_text(tmp_path, "tiny.csv", "color\nred\nblue\nred\ngreen\nblue\n")

    result = runner.invoke(app, ["report", str(source)])

    assert result.exit_code == 0, result.output
    analyses = _document(tmp_path / "tiny.json")["analyses"]
    assert analyses["outcome"] in ("nothing_selected", "ran")
    assert "Second pass (automatic)" in result.output


def test_an_automatic_second_pass_that_fails_does_not_fail_the_report(tmp_path, monkeypatch):
    source = _customers(tmp_path)

    def stale(*args, **kwargs):
        raise StaleSource("the source changed while the report was made")

    monkeypatch.setattr("tabalyst.report_chain.run_second_pass", stale)

    result = runner.invoke(app, ["report", str(source)])

    assert result.exit_code == 0, result.output
    analyses = _document(tmp_path / "customers.json")["analyses"]
    assert analyses["outcome"] == "failed" and "changed" in analyses["reason"]
    assert (tmp_path / "customers.html").exists()
    assert "Warning" in result.output and "second pass was left out" in result.output


def test_a_forced_second_pass_that_fails_fails_the_report(tmp_path, monkeypatch):
    source = _customers(tmp_path)

    def stale(*args, **kwargs):
        raise StaleSource("the source changed while the report was made")

    monkeypatch.setattr("tabalyst.report_chain.run_second_pass", stale)

    result = runner.invoke(app, ["report", str(source), "--deep"])

    assert result.exit_code != 0
    assert not (tmp_path / "customers.html").exists()


# Forcing and confirming (rule R1) ------------------------------------------------


def test_a_costly_forced_second_pass_outside_a_terminal_stops_with_exit_code_3(
    tmp_path, monkeypatch
):
    source = _customers(tmp_path)
    _costly(monkeypatch)
    opened = _readings(monkeypatch)

    result = runner.invoke(app, ["report", str(source), "--deep"], input="")

    assert result.exit_code == 3
    assert "--yes" in result.output
    assert opened == [] and not (tmp_path / "customers.html").exists()


def test_yes_starts_a_costly_forced_second_pass(tmp_path, monkeypatch):
    source = _customers(tmp_path)
    _costly(monkeypatch)

    result = runner.invoke(app, ["report", str(source), "--deep", "--yes"])

    assert result.exit_code == 0, result.output
    analyses = _document(tmp_path / "customers.json")["analyses"]
    assert analyses["mode"] == "forced" and analyses["outcome"] == "ran"
    assert "Second pass (forced)" in result.output


def test_a_cheap_forced_second_pass_asks_nothing(tmp_path):
    source = _customers(tmp_path)

    result = runner.invoke(app, ["report", str(source), "--deep"], input="")

    assert result.exit_code == 0, result.output
    assert _document(tmp_path / "customers.json")["analyses"]["mode"] == "forced"


def test_a_terminal_answer_of_no_starts_nothing(tmp_path, monkeypatch):
    source = _customers(tmp_path)
    _costly(monkeypatch)
    monkeypatch.setattr("tabalyst.cli.confirm.is_interactive", lambda: True)

    result = runner.invoke(app, ["report", str(source), "--deep"], input="n\n")

    assert result.exit_code == 3 and "Nothing was started" in result.output
    assert not (tmp_path / "customers.html").exists()


def test_a_batch_asks_once_with_the_total(tmp_path, monkeypatch):
    first = _customers(tmp_path, "one.csv")
    second = _customers(tmp_path, "two.csv")
    _costly(monkeypatch)
    asked = []

    batch = generate_reports(
        [first, second],
        output_dir=tmp_path / "out",
        deep=True,
        confirm=lambda confirmation: asked.append(confirmation) or True,
    )

    assert batch.succeeded and len(asked) == 1
    assert asked[0].required and asked[0].estimate is not None


def test_the_api_never_prompts_and_says_what_is_needed(tmp_path, monkeypatch):
    source = _customers(tmp_path)
    _costly(monkeypatch)
    opened = _readings(monkeypatch)

    with pytest.raises(ConfirmationRequired) as raised:
        generate_reports([source], output_dir=tmp_path / "out", deep=True)
    again = generate_reports([source], output_dir=tmp_path / "out", deep=True, confirmed=True)

    assert raised.value.confirmation.required
    assert again.succeeded and len(opened) == 1
    # `analyze` is the same: a forced costly pass needs `confirmed`. A source whose
    # results are stored needs nothing: it is not read again.
    other = _customers(tmp_path, "other.csv", rows=1_100)
    with pytest.raises(ConfirmationRequired):
        analyze(other, tmp_path / "x" / "other.html", deep=True)
    analyze(other, tmp_path / "x" / "other.html", deep=True, confirmed=True)
    analyze(source, tmp_path / "y" / "customers.html", deep=True)


def test_the_configuration_can_force_the_second_pass_like_the_option(tmp_path, monkeypatch):
    source = _customers(tmp_path)
    force = write_json(tmp_path, "force.json", {"deep": {"mode": "force"}})
    _costly(monkeypatch)

    refused = runner.invoke(app, ["report", str(source), "-c", str(force)], input="")
    allowed = runner.invoke(app, ["report", str(source), "-c", str(force), "--yes"])

    assert refused.exit_code == 3
    assert allowed.exit_code == 0, allowed.output
    assert _document(tmp_path / "customers.json")["analyses"]["mode"] == "forced"


# Scan documents ----------------------------------------------------------------


def _scanned(tmp_path):
    source = _customers(tmp_path)
    target = tmp_path / "customers.scan.json"
    result = runner.invoke(app, ["scan", str(source), "-o", str(target)])
    assert result.exit_code == 0, result.output
    return source, target


def test_a_report_of_a_scan_document_reads_no_source_and_names_what_it_left_out(
    tmp_path, monkeypatch
):
    _, target = _scanned(tmp_path)
    opened = _readings(monkeypatch)

    result = runner.invoke(app, ["report", "--scan", str(target)])

    assert result.exit_code == 0, result.output
    analyses = _document(tmp_path / "customers.json")["analyses"]
    assert analyses["outcome"] in ("unavailable", "ran")
    deep = analyses["deep"]
    left = [a for a in deep["analyses"] if a["status"] == "skipped"]
    assert left and all(a["reason"] == "source_not_read" for a in left)
    assert opened == [] and deep["run"]["source_read"] is False
    assert "scan document" in analyses["reason"] and "left out" in result.output


def test_a_report_of_a_scan_document_without_its_source_is_still_written(tmp_path):
    source, target = _scanned(tmp_path)
    moved = tmp_path / "moved"
    moved.mkdir()
    shutil.move(str(target), moved / target.name)
    source.unlink()

    result = runner.invoke(app, ["report", "--scan", str(moved / target.name)])

    assert result.exit_code == 0, result.output
    analyses = _document(moved / "customers.json")["analyses"]
    assert analyses["deep"]["run"]["source_read"] is False
    assert (moved / "customers.html").exists()


def test_deep_reads_the_source_beside_a_scan_document(tmp_path, monkeypatch):
    _, target = _scanned(tmp_path)
    opened = _readings(monkeypatch)

    result = runner.invoke(app, ["report", "--scan", str(target), "--deep"])

    assert result.exit_code == 0, result.output
    analyses = _document(tmp_path / "customers.json")["analyses"]
    assert analyses["mode"] == "forced" and analyses["outcome"] == "ran"
    assert len(opened) == 1 and (tmp_path / "customers.deep.json").exists()


def test_deep_without_the_source_of_a_scan_document_fails_clearly(tmp_path):
    source, target = _scanned(tmp_path)
    source.unlink()

    result = runner.invoke(app, ["report", "--scan", str(target), "--deep"])

    assert result.exit_code == 4
    assert "not found beside it" in result.output
    assert not (tmp_path / "customers.html").exists()


def test_a_stored_second_pass_document_serves_a_report_of_a_scan_document(
    tmp_path, monkeypatch
):
    source, target = _scanned(tmp_path)
    assert runner.invoke(app, ["scan", str(source), "--deep", "-o", str(target), "--force"]).exit_code == 0
    opened = _readings(monkeypatch)

    result = runner.invoke(app, ["report", "--scan", str(target)])

    assert result.exit_code == 0, result.output
    analyses = _document(tmp_path / "customers.json")["analyses"]
    assert analyses["outcome"] in ("reused", "ran") and opened == []
    assert analyses["deep"]["run"]["reused"] >= 1


# Python API --------------------------------------------------------------------


def test_analyze_scan_holds_what_the_scan_alone_answers(tmp_path):
    _, target = _scanned(tmp_path)

    profile = analyze_scan(target)

    assert profile.analyses is not None
    assert profile.analyses.deep is not None and profile.analyses.deep.run.source_read is False


# What the stored document keeps ------------------------------------------------


def _stored_documents(tmp_path):
    return sorted((tmp_path.parent / f"{tmp_path.name}-home").rglob("deep.json"))


def test_an_automatic_report_keeps_the_results_a_forced_run_stored(tmp_path):
    source = _customers(tmp_path)
    assert runner.invoke(app, ["scan", str(source), "--deep", "--yes"]).exit_code == 0
    stored = json.loads(_stored_documents(tmp_path)[0].read_text(encoding="utf-8"))
    forced = {a["id"] for a in stored["analyses"] if a["status"] == "complete"}
    # A source that changes the plan of the automatic pass: one more column to count.
    other = write_text(tmp_path, "customers.csv", source.read_text(encoding="utf-8"))
    assert other == source

    result = runner.invoke(app, ["report", str(source)])

    assert result.exit_code == 0, result.output
    kept = json.loads(_stored_documents(tmp_path)[0].read_text(encoding="utf-8"))
    assert forced <= {a["id"] for a in kept["analyses"] if a["status"] == "complete"}


def test_a_report_of_a_scan_document_writes_no_second_pass_file(tmp_path):
    _, target = _scanned(tmp_path)

    assert runner.invoke(app, ["report", "--scan", str(target)]).exit_code == 0
    profile = analyze_scan(target)

    assert profile.analyses is not None
    assert not (tmp_path / "customers.deep.json").exists()


def test_a_run_with_another_plan_keeps_the_complete_results_it_did_not_select(tmp_path):
    from planner_helpers import scan_csv
    from second_pass_helpers import forced_plan

    from tabalyst.config import DeepSettings
    from tabalyst.deep_store import write_deep
    from tabalyst.scanner.secondpass import load_deep, run_second_pass

    rows = [f"{n * 1.37:.2f},C{n:05d}" for n in range(600)]
    scanned = scan_csv(tmp_path, "price,code", rows)
    plan = forced_plan(scanned)
    first = run_second_pass(scanned, tmp_path / "data.csv", plan)
    path = tmp_path / "data.deep.json"
    assert write_deep(path, first, None, shared=False)
    coarse = forced_plan(scanned, DeepSettings(bins=10))
    histograms = [c for c in coarse.candidates if c.analyzer == "numeric_histogram"]
    narrow = coarse.model_copy(update={"candidates": histograms})

    second = run_second_pass(
        scanned,
        tmp_path / "data.csv",
        narrow,
        settings=DeepSettings(bins=10),
        previous=first.document,
    )
    assert second.executed
    written = write_deep(path, second, first.document, shared=False)

    stored = load_deep(path)
    assert stored is not None
    assert {a.id for a in first.document.analyses if a.status == "complete"} <= {
        a.id for a in stored.analyses
    }
    assert written
