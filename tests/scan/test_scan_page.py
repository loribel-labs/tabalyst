# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The web page of an explicit ``tabalyst scan`` (design 16.8, lot 10b): written
for the command, never for a scan another command makes by itself."""

import pytest
from scan_helpers import write_text
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.errors import ReportError
from tabalyst.sampling_service import generate_samples
from tabalyst.scan_service import generate_scans

runner = CliRunner()


@pytest.fixture(autouse=True)
def _storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage"))


def _source(tmp_path):
    rows = "\n".join(f"{'ab'[i % 2]},{i}" for i in range(200))
    return write_text(tmp_path, "data.csv", "kind,n\n" + rows + "\n")


def _pages(directory):
    return sorted(path.name for path in directory.rglob("*.html"))


def test_an_explicit_scan_writes_its_page_beside_the_source(tmp_path):
    source = _source(tmp_path)

    done = runner.invoke(app, ["scan", str(source)])

    assert done.exit_code == 0, done.output
    assert _pages(tmp_path) == ["data.scan.html"]
    assert "Page:" in done.output
    page = (tmp_path / "data.scan.html").read_text(encoding="utf-8")
    assert "<html" in page and "data.csv" in page


def test_the_page_follows_the_name_of_the_scan_document(tmp_path):
    source = _source(tmp_path)

    done = runner.invoke(app, ["scan", str(source), "-o", str(tmp_path / "out" / "x.scan.json")])

    assert done.exit_code == 0, done.output
    assert _pages(tmp_path) == ["x.scan.html"] and (tmp_path / "out" / "x.scan.html").exists()


def test_no_html_writes_no_page(tmp_path):
    source = _source(tmp_path)

    done = runner.invoke(app, ["scan", str(source), "--no-html"])

    assert done.exit_code == 0 and _pages(tmp_path) == []


def test_a_scan_another_command_makes_by_itself_writes_no_page(tmp_path):
    source = _source(tmp_path)

    generate_samples([source], method="smart", rows=20)
    planned = runner.invoke(app, ["scan", str(source), "--plan"])
    assert planned.exit_code == 0, planned.output

    # The only page is the sample's own, not the page of the scan it made.
    assert _pages(tmp_path) == ["data.sample.html"]


def test_the_api_writes_a_page_only_when_asked(tmp_path):
    source = _source(tmp_path)

    quiet = generate_scans([source], project_storage=True)
    assert quiet.successes[0].job.page is None and _pages(tmp_path) == []

    asked = generate_scans([source], project_storage=True, html=True)
    assert asked.successes[0].job.page == tmp_path / "data.scan.html"
    assert _pages(tmp_path) == ["data.scan.html"]


def test_the_page_of_a_stored_scan_is_replaced_at_every_scan(tmp_path):
    source = _source(tmp_path)
    (tmp_path / "data.scan.html").write_text("old", encoding="utf-8")

    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0

    assert (tmp_path / "data.scan.html").read_text(encoding="utf-8") != "old"


def test_the_page_of_a_standalone_scan_needs_force_like_its_document(tmp_path):
    source = _source(tmp_path)
    scan = tmp_path / "out" / "x.scan.json"
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "x.scan.html").write_text("mine", encoding="utf-8")

    refused = runner.invoke(app, ["scan", str(source), "-o", str(scan)])
    assert refused.exit_code != 0 and not scan.exists()
    assert (tmp_path / "out" / "x.scan.html").read_text(encoding="utf-8") == "mine"

    replaced = runner.invoke(app, ["scan", str(source), "-o", str(scan), "--force"])
    assert replaced.exit_code == 0
    assert (tmp_path / "out" / "x.scan.html").read_text(encoding="utf-8") != "mine"


def test_a_page_that_cannot_be_written_is_a_warning_and_the_scan_stands(tmp_path, monkeypatch):
    source = _source(tmp_path)

    def refuse(*args, **kwargs):
        raise ReportError("disk full")

    monkeypatch.setattr("tabalyst.scan_service.write_scan_page", refuse)

    batch = generate_scans([source], project_storage=True, html=True)

    [success] = batch.successes
    assert success.job.page is None
    assert any("page of the scan was not written" in warning for warning in success.warnings)


def test_a_second_pass_scan_writes_its_page_again_with_the_results(tmp_path):
    # A column of codes is eligible for patterns, whose validation waits for the
    # second pass.
    rows = "\n".join(f"K-{i % 7},{i}" for i in range(200))
    source = write_text(tmp_path, "data.csv", "kind,n\n" + rows + "\n")
    page = tmp_path / "data.scan.html"
    marker = "second pass did not run this analysis"

    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0
    without = page.read_text(encoding="utf-8").count(marker)

    done = runner.invoke(app, ["scan", str(source), "--deep", "--yes", "--force"])

    assert done.exit_code == 0, done.output
    assert without > 0
    assert page.read_text(encoding="utf-8").count(marker) < without
