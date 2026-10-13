# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Report runs the second pass by itself (plan tests A13 and A14; design
20.1 and 18.2)."""

import json

import pytest
from scan_helpers import write_json, write_text
from typer.testing import CliRunner

from tabalyst import generate_reports
from tabalyst.cli import app
from tabalyst.scanner.readers import factory
from tabalyst.scanner.secondpass import executor

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


def _customers(tmp_path, rows=1_500):
    lines = ["id,code,amount,signed"]
    for n in range(rows):
        lines.append(f"C{n:06d},AB{n % 900 + 100},{(n * 37) % 997}.{n % 100:02d},2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}")
    return write_text(tmp_path, "customers.csv", "\n".join(lines) + "\n")


def _count_readings(monkeypatch):
    """The sources the second pass opens."""
    opened = []

    def counting(path, config, on_bytes):
        opened.append(path)
        return factory.open_reader(path, config, on_bytes)

    monkeypatch.setattr(executor, "open_reader", counting)
    return opened


@pytest.mark.scan_json_lot("7c")
def test_A13_a_report_from_a_source_scans_plans_and_reads_again_by_itself(
    tmp_path, monkeypatch
):
    source = _customers(tmp_path)
    opened = _count_readings(monkeypatch)

    # No option, no answer to give: the command is not interactive here.
    result = runner.invoke(app, ["report", str(source)], input="")

    assert result.exit_code == 0, result.output
    document = json.loads((tmp_path / "customers.json").read_text(encoding="utf-8"))
    analyses = document["analyses"]
    assert analyses["mode"] == "auto" and analyses["outcome"] == "ran"
    deep = analyses["deep"]
    # One reading for the second pass, verified against the digest of the Scan.
    assert len(opened) == 1 and deep["run"]["source_verified"] is True
    assert deep["status"] == "complete" and deep["run"]["executed"] >= 3
    assert {a["analyzer"] for a in deep["analyses"]} >= {
        "numeric_histogram",
        "pattern_validation",
        "temporal_distribution",
    }
    assert all(a["status"] == "complete" for a in deep["analyses"])
    # The report says what it did, and the HTML shows it.
    assert "Second pass (automatic)" in result.output
    assert "second-pass" in (tmp_path / "customers.html").read_text(encoding="utf-8")


@pytest.mark.scan_json_lot("7c")
def test_A13_the_python_api_does_the_same_without_a_question(tmp_path):
    source = _customers(tmp_path)

    batch = generate_reports([source], output_dir=tmp_path / "out")

    assert batch.succeeded
    assert batch.successes[0].result["analyses"]["outcome"] == "ran"


@pytest.mark.scan_json_lot("7c")
def test_A14_a_change_of_presentation_alone_reads_nothing_again(tmp_path, monkeypatch):
    source = _customers(tmp_path)
    plain = write_json(tmp_path, "plain.json", {})
    presented = write_json(
        tmp_path, "presented.json", {"report": {"value_examples": {"inline_display_size": 1}}}
    )
    first = generate_reports(
        [source], output=tmp_path / "a" / "customers.html", config_path=plain, force=True
    )
    assert first.succeeded
    stored = next((tmp_path.parent / f"{tmp_path.name}-home").rglob("deep.json"))
    before = stored.read_bytes()
    opened = _count_readings(monkeypatch)

    def refuse(*args, **kwargs):
        raise AssertionError("the source was scanned again")

    monkeypatch.setattr("tabalyst.shared_scan_service.scan", refuse)
    second = generate_reports(
        [source],
        output=tmp_path / "b" / "customers.html",
        config_path=presented,
        force=True,
    )

    assert second.succeeded
    analyses = second.successes[0].result["analyses"]
    assert analyses["outcome"] == "reused" and analyses["deep"]["run"]["source_read"] is False
    assert opened == [] and stored.read_bytes() == before
