"""Atomic visibility, real OS locks, pinned readers and conservative recovery."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tabalyst.errors import InputError
from tabalyst.project_scan_service import scan_project
from tabalyst.projects import (
    StorageLocation,
    _publication,
    _staging,
    _sync,
    create_project,
    find_project,
    list_projects,
    read_index,
    read_project,
    record_scan,
    write_project,
)
from tabalyst.projects._generation import open_generation
from tabalyst.projects._locks import (
    ProjectBusyError,
    workspace_maintenance,
    workspace_writer,
)
from tabalyst.projects._publication import UnknownProjectOutcomeError
from tabalyst.projects._recovery import quarantine_uncommitted
from tabalyst.projects._staging import _file_hash
from tabalyst.projects.identity import new_project_id
from tabalyst.projects.index import source_key
from tabalyst.projects.models import GenerationBinding
from tabalyst.scan_reuse import SourceState

MOMENT = datetime(2026, 9, 28, tzinfo=UTC)


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "data.csv"
    source.write_bytes(b"id\n1\n2\n")
    return StorageLocation(tmp_path / "storage"), source


def assert_selected(location, project, records=2):
    assert read_project(location, project.project_id) == project
    with open_generation(location, project.project_id) as pinned:
        assert pinned.project == project
        assert pinned.connection.execute(
            "SELECT count(*) FROM data.records"
        ).fetchone() == (records,)


def test_manifest_binds_closed_artifacts_and_scoped_data(setup):
    location, source = setup
    result = scan_project(source, location=location, now=MOMENT)
    assert result.project.format_revision == 2
    assert result.project.generation.scan_sha256 == _file_hash(result.scan_path)
    assert result.project.generation.database_sha256 == _file_hash(result.database_path)
    assert not result.database_path.with_suffix(".duckdb.wal").exists()
    assert_selected(location, result.project)
    assert result.directory_sync_supported == (os.name == "posix")


def test_first_scan_is_invisible_until_manifest_commit(setup, monkeypatch):
    location, source = setup
    original = _sync.replace_manifest

    def check(path, text):
        assert list_projects(location) == []
        assert find_project(location, source) is None
        assert read_index(location) is None
        assert not path.exists()
        assert len(list(path.parent.glob("generations/*/project.duckdb"))) == 1
        original(path, text)

    monkeypatch.setattr(_sync, "replace_manifest", check)
    result = scan_project(source, location=location)
    assert_selected(location, result.project)


def test_reader_pins_old_generation_during_rescan_and_blocks_maintenance(setup):
    location, source = setup
    first = scan_project(source, location=location, now=MOMENT)
    with open_generation(location, first.project.project_id) as old:
        source.write_bytes(b"id\n1\n2\n3\n")
        second = scan_project(source, location=location, now=MOMENT + timedelta(days=1))
        assert old.generation_id == first.project.generation.id
        assert old.result.scope.records_analyzed == 2
        assert old.connection.execute(
            "SELECT count(*) FROM data.records"
        ).fetchone() == (2,)
        assert old.freshness().state is SourceState.STALE
        assert_selected(location, second.project, records=3)
        with pytest.raises(ProjectBusyError):
            quarantine_uncommitted(location, first.project.project_id)
    quarantined = quarantine_uncommitted(location, first.project.project_id)
    assert len(quarantined) == 1
    assert not first.database_path.exists()
    assert_selected(location, second.project, records=3)


@pytest.mark.parametrize(
    "boundary",
    [
        "scan",
        "insert",
        "finalize",
        "serialize",
        "commit",
        "checkpoint",
        "close",
        "file_sync",
        "directory_sync",
        "generation_rename",
        "manifest_replace",
    ],
)
@pytest.mark.parametrize("rescan", [False, True])
def test_failure_before_manifest_keeps_old_or_invisible(
    setup, monkeypatch, boundary, rescan
):
    location, source = setup
    first = scan_project(source, location=location, now=MOMENT) if rescan else None
    old_manifest = (
        location.project_path(first.project.project_id).read_bytes() if first else None
    )

    def fail(*args, **kwargs):
        raise OSError("injected boundary failure")

    targets = {
        "scan": (_staging, "scan"),
        "insert": (_staging._Buffer, "flush"),
        "finalize": (_staging._Sink, "finalize"),
        "serialize": (_staging, "scan_document"),
        "file_sync": (_sync, "sync_file"),
        "directory_sync": (_sync, "sync_directory"),
        "generation_rename": (_publication, "rename_generation"),
        "manifest_replace": (_sync, "replace_manifest"),
    }
    if boundary in targets:
        monkeypatch.setattr(*targets[boundary], fail)
    else:
        connect = _staging.duckdb.connect

        class FailingConnection:
            def __init__(self, connection):
                self.connection = connection

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def execute(self, query, *args, **kwargs):
                if query in {"commit": "COMMIT", "checkpoint": "CHECKPOINT"}.get(
                    boundary, ()
                ):
                    fail()
                return self.connection.execute(query, *args, **kwargs)

            def close(self):
                self.connection.close()
                if boundary == "close":
                    fail()

        monkeypatch.setattr(
            _staging.duckdb,
            "connect",
            lambda *a, **kw: FailingConnection(connect(*a, **kw)),
        )
    with pytest.raises(OSError, match="injected"):
        scan_project(source, location=location, now=MOMENT + timedelta(days=1))
    monkeypatch.undo()
    if first is not None:
        assert (
            location.project_path(first.project.project_id).read_bytes() == old_manifest
        )
        assert_selected(location, first.project)
    else:
        assert list_projects(location) == []
        assert find_project(location, source) is None
        assert not list(location.projects_dir.rglob("project.json"))
        assert read_index(location) is None


def test_index_failure_after_commit_returns_success_and_repairs(setup, monkeypatch):
    location, source = setup

    def fail(*args):
        raise OSError("index disk full")

    monkeypatch.setattr(_publication, "register_project", fail)
    result = scan_project(source, location=location)
    assert result.warnings and "index needs repair" in result.warnings[0]
    assert_selected(location, result.project)
    assert not location.index_path.exists()
    monkeypatch.undo()
    assert find_project(location, source) == result.project
    assert read_index(location).projects == {
        source_key(source): result.project.project_id
    }


@pytest.mark.parametrize("rescan", [False, True])
def test_error_after_replace_is_committed_success(setup, monkeypatch, rescan):
    location, source = setup
    if rescan:
        scan_project(source, location=location)
    original = _sync.replace_manifest

    def fail_after(path, text):
        original(path, text)
        raise OSError("post-replace synchronization failure")

    monkeypatch.setattr(_sync, "replace_manifest", fail_after)
    result = scan_project(source, location=location)
    assert result.warnings and "committed" in result.warnings[0]
    assert_selected(location, result.project)


def test_unreadable_outcome_is_unknown_and_artifacts_are_preserved(setup, monkeypatch):
    location, source = setup

    def corrupt_and_fail(path, text):
        path.write_bytes(b"{")
        raise OSError("uncertain replacement")

    monkeypatch.setattr(_sync, "replace_manifest", corrupt_and_fail)
    with pytest.raises(UnknownProjectOutcomeError, match="outcome unknown"):
        scan_project(source, location=location)
    assert len(list(location.projects_dir.glob("*/generations/*/project.duckdb"))) == 1
    assert list_projects(location) == []


@pytest.mark.parametrize("existing_scan", [False, True])
def test_legacy_rebuild_preserves_identity_and_creation(setup, existing_scan):
    location, source = setup
    legacy = create_project(location, source, now=MOMENT)
    if existing_scan:
        from tabalyst.scan_service import scan_document
        from tabalyst.scanner import scan

        location.scan_path(legacy.project_id).write_text(
            scan_document(scan(source)), encoding="utf-8"
        )
    with (
        pytest.raises(InputError, match="Legacy"),
        open_generation(location, legacy.project_id),
    ):
        pass
    result = scan_project(source, location=location, now=MOMENT + timedelta(days=1))
    assert result.project.project_id == legacy.project_id
    assert result.project.created_at == MOMENT
    assert result.reopened
    assert_selected(location, result.project)


def test_failed_legacy_rebuild_preserves_original(setup):
    location, source = setup
    legacy = create_project(location, source, now=MOMENT)
    before = location.project_path(legacy.project_id).read_bytes()
    source.write_bytes(b"a,b\n1\n")
    with pytest.raises(InputError):
        scan_project(source, location=location)
    assert location.project_path(legacy.project_id).read_bytes() == before


@pytest.mark.parametrize(
    "corruption", ["manifest", "scan", "database", "missing", "revision", "binding"]
)
def test_corrupt_selected_generation_never_falls_back(setup, corruption):
    location, source = setup
    first = scan_project(source, location=location)
    second = scan_project(source, location=location)
    if corruption == "manifest":
        location.project_path(second.project.project_id).write_bytes(b"{")
    elif corruption == "scan":
        second.scan_path.write_bytes(b"{}")
    elif corruption == "database":
        second.database_path.write_bytes(b"broken")
    elif corruption == "missing":
        second.database_path.unlink()
    else:
        document = json.loads(
            location.project_path(second.project.project_id).read_bytes()
        )
        if corruption == "revision":
            document["format_revision"] = 99
        else:
            document["generation"]["id"] = new_project_id()
        location.project_path(second.project.project_id).write_text(
            json.dumps(document), encoding="utf-8"
        )
    with pytest.raises(InputError), open_generation(location, second.project.project_id):
        pass
    assert first.database_path.exists()
    with pytest.raises(InputError):
        quarantine_uncommitted(location, second.project.project_id)


def test_explicit_rescan_repairs_artifacts_with_missing_index(setup):
    location, source = setup
    first = scan_project(source, location=location)
    first.database_path.write_bytes(b"broken")
    location.index_path.unlink()
    with pytest.raises(InputError):
        find_project(location, source)
    second = scan_project(source, location=location)
    assert second.project.project_id == first.project.project_id
    assert_selected(location, second.project)


def test_missing_source_opens_committed_generation_and_cannot_rebuild(setup):
    location, source = setup
    result = scan_project(source, location=location)
    source.unlink()
    with open_generation(location, result.project.project_id) as pinned:
        assert pinned.freshness().state is SourceState.MISSING
    with pytest.raises(InputError):
        scan_project(source, location=location)
    assert_selected(location, result.project)


def test_all_legacy_mutators_respect_writer_and_cannot_republish_v2(setup):
    location, source = setup
    result = scan_project(source, location=location)
    with pytest.raises(InputError, match="atomically"):
        record_scan(location, result.project.project_id)
    with pytest.raises(InputError, match="atomic generation"):
        write_project(location, result.project)
    old = result.project.model_dump(exclude={"generation"})
    old["format_revision"] = 1
    from tabalyst.projects.models import ProjectDocument

    with pytest.raises(InputError, match="overwrite"):
        write_project(location, ProjectDocument.model_validate(old))
    with workspace_writer(location), ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(create_project, location, source)
        with pytest.raises(ProjectBusyError):
            future.result(timeout=5)
    assert_selected(location, result.project)


def test_quarantine_orphans_preserves_selected_and_unknown_files(setup):
    location, source = setup
    result = scan_project(source, location=location)
    orphan = location.generation_dir(result.project.project_id, new_project_id())
    orphan.mkdir()
    (orphan / "evidence").write_bytes(b"preserve")
    stage = location.staging_dir(result.project.project_id, new_project_id())
    stage.mkdir()
    (stage / "unknown").write_bytes(b"keep")
    unrelated = stage.parent / "not-a-generation"
    unrelated.mkdir()
    moved = quarantine_uncommitted(location, result.project.project_id)
    assert len(moved) == 2
    assert sorted(p.read_bytes() for q in moved for p in q.iterdir()) == [
        b"keep",
        b"preserve",
    ]
    assert unrelated.exists()
    assert_selected(location, result.project)


def test_busy_writer_in_another_process_and_death_releases_lock(setup, tmp_path):
    location, source = setup
    ready = tmp_path / "ready"
    code = """
from pathlib import Path
import sys
from tabalyst.projects import StorageLocation
from tabalyst.projects._locks import workspace_writer
with workspace_writer(StorageLocation(Path(sys.argv[1]))):
    Path(sys.argv[2]).write_bytes(b'ready')
    sys.stdin.read()
"""
    process = child(code, location.root, ready)
    try:
        wait_ready(process, ready)
        with pytest.raises(ProjectBusyError):
            scan_project(source, location=location)
        other = source.with_name("other.csv")
        other.write_bytes(b"id\n1\n")
        with pytest.raises(ProjectBusyError):
            scan_project(other, location=location)
        with pytest.raises(ProjectBusyError), workspace_maintenance(location):
            pass
    finally:
        process.kill()
        process.wait(timeout=5)
        process.communicate(timeout=5)
    assert_selected(location, scan_project(source, location=location).project)


def child(code, *arguments):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.Popen(
        [sys.executable, "-c", code, *map(str, arguments)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )


def wait_ready(process, ready):
    import time

    deadline = time.monotonic() + 15
    while not ready.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            process.kill()
            _, error = process.communicate(timeout=5)
            pytest.fail(f"Child did not reach boundary: {error.decode()}")
        time.sleep(0.01)


@pytest.mark.parametrize("rescan", [False, True])
@pytest.mark.parametrize("position", ["before", "after"])
def test_process_killed_around_commit_has_old_or_new_visibility(
    setup, tmp_path, rescan, position
):
    location, source = setup
    first = scan_project(source, location=location) if rescan else None
    ready = tmp_path / "ready"
    code = """
from pathlib import Path
import sys
from tabalyst.project_scan_service import scan_project
from tabalyst.projects import StorageLocation, _sync
original = _sync.replace_manifest
def boundary(path, text):
    if sys.argv[4] == 'after':
        original(path, text)
    Path(sys.argv[3]).write_bytes(b'ready')
    sys.stdin.read()
    if sys.argv[4] == 'before':
        original(path, text)
_sync.replace_manifest = boundary
scan_project(Path(sys.argv[2]), location=StorageLocation(Path(sys.argv[1])))
"""
    process = child(code, location.root, source, ready, position)
    try:
        wait_ready(process, ready)
    finally:
        process.kill()
        process.communicate(timeout=5)
    if position == "before":
        if first:
            assert_selected(location, first.project)
        else:
            assert list_projects(location) == []
            assert find_project(location, source) is None
    else:
        documents = list_projects(location)
        assert len(documents) == 1
        if first:
            assert documents[0].generation.id != first.project.generation.id
        assert_selected(location, documents[0])
        assert find_project(location, source) == documents[0]
    assert_selected(location, scan_project(source, location=location).project)


def test_generation_binding_rejects_paths_and_bad_hashes():
    for identifier in ("../outside", "not-a-ulid"):
        with pytest.raises(ValueError):
            GenerationBinding(
                id=identifier, scan_sha256="0" * 64, database_sha256="1" * 64
            )
    with pytest.raises(ValueError):
        GenerationBinding(
            id=new_project_id(), scan_sha256="A" * 64, database_sha256="1" * 64
        )
