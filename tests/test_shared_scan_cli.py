"""The public Scan/Report project handoff and cache commands."""

import hashlib
import json
import os

from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.project_scan_service import scan_project
from tabalyst.projects._cache import create_query_directory
from tabalyst.projects._generation import open_generation
from tabalyst.projects.index import find_project
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.store import read_project

runner = CliRunner()


def _project(location, source):
    result = find_project(location, source)
    assert result is not None
    return result


def test_scan_and_report_share_scan_only_document_then_replace_stale_scan(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    source = tmp_path / "data.csv"
    source.write_text("id,city\n1,Paris\n", encoding="utf-8")
    location = StorageLocation.local()

    scanned = runner.invoke(app, ["scan", str(source)])
    assert scanned.exit_code == 0, scanned.output
    scan_path = location.shared_scan_path(source)
    assert scan_path.is_file()
    assert not location.projects_dir.exists()
    assert not (tmp_path / "data.scan.json").exists()
    first_bytes = scan_path.read_bytes()

    report = runner.invoke(app, ["report", str(source)])
    assert report.exit_code == 0, report.output
    assert scan_path.read_bytes() == first_bytes

    before = source.stat()
    source.write_text("id,city\n1,Lyon \n", encoding="utf-8")
    os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert source.stat().st_size == before.st_size
    refreshed = runner.invoke(app, ["report", str(source), "--force"])
    assert refreshed.exit_code == 0, refreshed.output
    assert scan_path.read_bytes() != first_bytes
    assert not location.projects_dir.exists()
    document = json.loads(scan_path.read_text())
    assert document["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()


def test_report_creates_only_a_scan_document_for_new_csv(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    source = tmp_path / "fresh.csv"
    source.write_text("id\n1\n", encoding="utf-8")
    location = StorageLocation.local()

    report = runner.invoke(app, ["report", str(source)])

    assert report.exit_code == 0, report.output
    assert location.shared_scan_path(source).is_file()
    assert not location.projects_dir.exists()


def test_cache_info_and_clean_select_source_or_all(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    sources = []
    location = StorageLocation.local()
    for name in ("a", "b"):
        source = tmp_path / f"{name}.csv"
        source.write_text("x\n1\n", encoding="utf-8")
        project = scan_project(source, location=location).project
        create_query_directory(
            location.project_dir(project.project_id), project.generation.id
        )
        sources.append(source)

    info = runner.invoke(app, ["cache", "info"])
    assert info.exit_code == 0, info.output
    assert "2 directories in 2 projects" in info.stdout

    one = runner.invoke(app, ["cache", "clean", str(sources[0])])
    assert one.exit_code == 0, one.output
    assert "1 cache directory in 1 project" in one.stderr
    assert "1 directory in 2 projects" in runner.invoke(
        app, ["cache", "info"]
    ).stdout

    all_result = runner.invoke(app, ["cache", "clean"])
    assert all_result.exit_code == 0, all_result.output
    assert "1 cache directory in 2 projects" in all_result.stderr
    assert "0 directories in 2 projects" in runner.invoke(
        app, ["cache", "info"]
    ).stdout


def test_report_preserves_recorded_csv_settings_when_reusing(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    source = tmp_path / "semicolon.csv"
    source.write_text("id;city\n1;Paris\n", encoding="utf-8")
    assert runner.invoke(app, ["scan", str(source), "--delimiter", ";"]).exit_code == 0
    location = StorageLocation.local()
    scan_path = location.shared_scan_path(source)
    first_bytes = scan_path.read_bytes()

    report = runner.invoke(app, ["report", str(source)])
    assert report.exit_code == 0, report.output
    assert scan_path.read_bytes() == first_bytes
    profile = json.loads((tmp_path / "semicolon.json").read_text())
    assert profile["source"]["delimiter"] == ";"

    settings = tmp_path / "config.json"
    settings.write_text(json.dumps({"scan": {"csv": {"delimiter": ";"}}}))
    configured = runner.invoke(
        app, ["report", str(source), "--config", str(settings), "--force"]
    )
    assert configured.exit_code == 0, configured.output
    assert scan_path.read_bytes() == first_bytes


def test_default_scan_does_not_modify_existing_duckdb_generation(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    source = tmp_path / "data.csv"
    source.write_text("x\n1\n", encoding="utf-8")
    location = StorageLocation.local()
    first = scan_project(source, location=location).project
    with open_generation(location, first.project_id):
        source.write_text("x\n2\n", encoding="utf-8")
        result = runner.invoke(app, ["scan", str(source)])
        assert result.exit_code == 0, result.output
        assert location.shared_scan_path(source).is_file()
        assert read_project(location, first.project_id).generation.id == first.generation.id
        assert location.scan_path(first.project_id, first.generation.id).exists()


def test_a_stored_scan_of_an_older_format_is_replaced_not_refused(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    source = tmp_path / "data.csv"
    source.write_text("id,city\n1,Paris\n", encoding="utf-8")
    location = StorageLocation.local()
    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0
    scan_path = location.shared_scan_path(source)
    document = json.loads(scan_path.read_text(encoding="utf-8"))
    document["format_revision"] -= 1
    scan_path.write_text(json.dumps(document), encoding="utf-8")

    report = runner.invoke(app, ["report", str(source)])

    assert report.exit_code == 0, report.output
    stored = json.loads(scan_path.read_text(encoding="utf-8"))
    assert stored["format_revision"] == document["format_revision"] + 1
