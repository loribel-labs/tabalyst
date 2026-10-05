# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from tabalyst.errors import InputError
from tabalyst.progress import ProgressPhase
from tabalyst.project_scan_service import scan_project
from tabalyst.projects import (
    StorageLocation,
    find_project,
    list_projects,
    project_freshness,
    read_project,
)
from tabalyst.scan_reuse import SourceState
from tabalyst.scan_service import scan_document
from tabalyst.scanner import scan

ROWS = "id,city\n1,Paris\n2,Nice\n"
FIRST = datetime(2026, 9, 28, 12, 0, 0, tzinfo=UTC)
SECOND = FIRST + timedelta(hours=1)


@pytest.fixture
def location(tmp_path):
    return StorageLocation(tmp_path / "storage")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "data" / "customers.csv"
    path.parent.mkdir()
    path.write_text(ROWS, encoding="utf-8")
    return path


def _files(directory):
    return sorted(entry.name for entry in directory.iterdir())


def test_the_first_scan_creates_the_project_and_writes_scan_json(location, source):
    outcome = scan_project(source, location=location, now=FIRST)

    project_dir = location.project_dir(outcome.project.project_id)
    assert not outcome.reopened
    assert outcome.scan_path == location.scan_path(
        outcome.project.project_id, outcome.project.generation.id
    )
    assert _files(project_dir) == [".staging", "generations", "project.json"]
    assert outcome.database_path.is_file()
    assert not (project_dir / "scan.json").exists()
    document = json.loads(outcome.scan_path.read_text("utf-8"))
    assert document["format"] == "tabalyst.scan"
    assert document["source"]["name"] == "customers.csv"
    assert read_project(location, outcome.project.project_id) == outcome.project


def test_scan_json_is_the_document_tabalyst_scan_writes(location, source):
    outcome = scan_project(source, location=location)

    written = json.loads(outcome.scan_path.read_text("utf-8"))
    direct = json.loads(scan_document(scan(source)))
    for document in (written, direct):
        document.pop("duration_seconds", None)
        document.pop("engine", None)
        document.pop("started_at", None)
    assert written == direct


def test_a_rescan_reopens_the_project_and_replaces_scan_json(location, source):
    first = scan_project(source, location=location, now=FIRST)
    source.write_text(ROWS + "3,Lyon\n", encoding="utf-8")

    second = scan_project(source, location=location, now=SECOND)

    assert second.reopened
    assert second.project.project_id == first.project.project_id
    assert second.project.created_at == FIRST
    assert second.project.last_scan_at == SECOND
    assert len(list_projects(location)) == 1
    assert second.scan_path != first.scan_path
    assert first.scan_path.is_file()
    written = json.loads(second.scan_path.read_text("utf-8"))
    assert written["source"]["size_bytes"] == source.stat().st_size
    assert _files(location.project_dir(first.project.project_id)) == [
        ".staging",
        "generations",
        "project.json",
    ]


def test_the_source_is_never_written_to(location, source):
    before = (source.read_bytes(), source.stat().st_mtime_ns)

    scan_project(source, location=location)

    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    assert _files(source.parent) == ["customers.csv"]


def test_a_failed_first_scan_leaves_no_project(location, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")

    with pytest.raises(InputError):
        scan_project(broken, location=location)

    assert list_projects(location) == []
    assert not list(location.projects_dir.rglob("project.json"))
    assert not location.index_path.exists()
    # The index entry left behind heals by itself.
    assert find_project(location, broken) is None


def test_a_failed_rescan_keeps_the_previous_scan(location, source):
    first = scan_project(source, location=location, now=FIRST)
    before = first.scan_path.read_bytes()
    source.write_text('id\n1\n"unterminated\n', encoding="utf-8")

    with pytest.raises(InputError):
        scan_project(source, location=location, now=SECOND)

    assert first.scan_path.read_bytes() == before
    kept = read_project(location, first.project.project_id)
    assert kept.last_scan_at == FIRST
    assert _files(location.project_dir(first.project.project_id)) == [
        ".staging",
        "generations",
        "project.json",
    ]


def test_a_missing_source_is_an_input_error(location, tmp_path):
    with pytest.raises(InputError, match="does not exist"):
        scan_project(tmp_path / "gone.csv", location=location)

    assert not location.projects_dir.exists()


def test_scan_settings_apply(location, tmp_path):
    source = tmp_path / "semicolon.csv"
    source.write_text("id;city\n1;Paris\n", encoding="utf-8")

    outcome = scan_project(source, location=location, delimiter=";")

    assert [field.name for field in outcome.result.datasets[0].fields] == [
        "id",
        "city",
    ]


def test_progress_ends_with_one_complete_event(location, source):
    events = []

    scan_project(source, location=location, on_progress=events.append)

    phases = [event.phase for event in events]
    assert phases[-1] is ProgressPhase.COMPLETE
    assert phases.count(ProgressPhase.COMPLETE) == 1
    assert ProgressPhase.WRITING in phases
    assert all(event.index == 1 and event.total == 1 for event in events)


def test_progress_reports_a_failure(location, tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    events = []

    with pytest.raises(InputError):
        scan_project(broken, location=location, on_progress=events.append)

    assert events[-1].phase is ProgressPhase.FAILED


# Freshness ------------------------------------------------------------------


def test_a_project_is_fresh_after_its_scan(location, source):
    outcome = scan_project(source, location=location)

    freshness = project_freshness(location, outcome.project.project_id)

    assert freshness.check.state is SourceState.FRESH
    assert freshness.source == source.resolve()


def test_a_changed_source_makes_the_project_stale(location, source):
    outcome = scan_project(source, location=location)
    source.write_text(ROWS + "3,Lyon\n", encoding="utf-8")

    freshness = project_freshness(location, outcome.project.project_id)

    assert freshness.check.state is SourceState.STALE
    assert "customers.csv has" in freshness.check.reason


def test_a_touched_source_keeps_the_project_fresh(location, source):
    outcome = scan_project(source, location=location)
    stat = source.stat()
    os.utime(source, (stat.st_atime, stat.st_mtime + 10))

    freshness = project_freshness(location, outcome.project.project_id)

    assert freshness.check.state is SourceState.FRESH


def test_a_missing_source_is_missing_not_stale(location, source):
    outcome = scan_project(source, location=location)
    source.unlink()

    freshness = project_freshness(location, outcome.project.project_id)

    assert freshness.check.state is SourceState.MISSING


def test_freshness_follows_the_path_of_project_json(
    location, source, tmp_path, monkeypatch
):
    outcome = scan_project(source, location=location)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "customers.csv").write_text("other\n", encoding="utf-8")
    monkeypatch.chdir(elsewhere)

    freshness = project_freshness(location, outcome.project.project_id)

    assert freshness.source == source.resolve()
    assert freshness.check.state is SourceState.FRESH


def test_a_project_without_scan_json_cannot_be_checked(location, source):
    outcome = scan_project(source, location=location)
    outcome.scan_path.unlink()

    with pytest.raises(InputError, match="Cannot open committed"):
        project_freshness(location, outcome.project.project_id)
