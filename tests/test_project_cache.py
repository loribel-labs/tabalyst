"""Owned disposable caches, real lock/termination boundaries and safe retries."""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_project_generations import child, wait_ready
from test_project_queries import publish, walk

from tabalyst.projects import StorageLocation, _cache
from tabalyst.projects._cache import (
    MARKER,
    clean_query_caches,
    create_query_directory,
    inventory_query_caches,
)
from tabalyst.projects._generation import open_generation
from tabalyst.projects._locks import (
    ProjectBusyError,
    workspace_reader,
    workspace_writer,
)
from tabalyst.projects._queries import materialize_values
from tabalyst.projects._query_budget import query_directory
from tabalyst.projects.identity import new_project_id


@pytest.fixture
def storage(tmp_path):
    location = StorageLocation(tmp_path / "storage")
    project_id = new_project_id()
    location.project_dir(project_id).mkdir(parents=True)
    return location, project_id, new_project_id()


def abandoned(storage):
    location, project_id, generation_id = storage
    path, _ = create_query_directory(location.project_dir(project_id), generation_id)
    (path / "values.duckdb").write_bytes(b"private payload")
    (path / "values.duckdb.wal").write_bytes(b"wal")
    (path / "spill").mkdir()
    (path / "spill" / "duckdb_temp_storage-0.tmp").write_bytes(b"spill")
    return path


def plan(storage):
    return inventory_query_caches(*storage[:2])


def execute(storage, preview=None):
    return clean_query_caches(*storage[:2], plan=preview or plan(storage))


def hashes(directory):
    return {
        p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file() and "cache" not in p.relative_to(directory).parts
    }


def test_missing_cache_is_empty_and_inventory_does_not_create(storage):
    assert plan(storage).entries == ()
    assert not (storage[0].project_dir(storage[1]) / "cache").exists()
    assert execute(storage).entries == ()


def test_marked_inventory_removal_and_empty_repeat(storage):
    path = abandoned(storage)
    preview = plan(storage)
    (entry,) = preview.entries
    assert entry.status == "candidate"
    assert entry.logical_bytes == sum(
        p.stat().st_size for p in path.rglob("*") if p.is_file()
    )
    assert path.exists()  # inventory/dry-run is read-only
    (removed,) = execute(storage, preview).entries
    assert removed.status == "removed"
    assert removed.removed_bytes == entry.logical_bytes
    assert not path.exists()
    assert execute(storage).entries == ()


@pytest.mark.parametrize(
    "kind",
    [
        "legacy",
        "unknown_file",
        "unknown_directory",
        "spill_file",
        "invalid",
        "revision",
        "project",
        "workspace",
        "generation",
        "extra",
        "bool",
        "duplicate",
        "large",
        "hardlink",
    ],
)
def test_unowned_unknown_or_invalid_contents_are_preserved(storage, kind, tmp_path):
    path = abandoned(storage)
    marker = path / MARKER
    if kind == "legacy":
        marker.unlink()
    elif kind == "unknown_file":
        (path / "notes").write_text("keep")
    elif kind == "unknown_directory":
        (path / "other").mkdir()
    elif kind == "spill_file":
        (path / "spill" / "notes").write_text("keep")
    elif kind == "hardlink":
        os.link(path / "values.duckdb", tmp_path / "linked")
    else:
        data = json.loads(marker.read_bytes())
        if kind == "invalid":
            marker.write_bytes(b"not JSON")
        elif kind == "large":
            marker.write_bytes(b"x" * 4097)
        elif kind == "duplicate":
            marker.write_bytes(marker.read_bytes()[:-1] + b',"revision":1}')
        else:
            key = {
                "project": "project_id",
                "workspace": "workspace_id",
                "generation": "generation_id",
            }.get(kind, kind)
            data[key] = (
                True if kind == "bool" else (2 if kind == "revision" else "different")
            )
            if kind == "bool":
                data["revision"] = True
                del data["bool"]
            marker.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")))
    before = {p: p.read_bytes() for p in path.rglob("*") if p.is_file()}
    (result,) = execute(storage).entries
    assert result.status == "skipped"
    assert all(p.read_bytes() == data for p, data in before.items())


@pytest.mark.parametrize(
    "level", ["project", "cache", "generation", "query", "spill", "file", "marker"]
)
def test_symlinks_are_never_followed(storage, tmp_path, level):
    path = abandoned(storage)
    directory = storage[0].project_dir(storage[1])
    target = {
        "project": directory,
        "cache": path.parents[1],
        "generation": path.parent,
        "query": path,
        "spill": path / "spill",
        "file": path / "values.duckdb",
        "marker": path / MARKER,
    }[level]
    saved = tmp_path / "outside"
    target.rename(saved)
    try:
        target.symlink_to(saved, target_is_directory=saved.is_dir())
    except OSError:
        saved.rename(target)
        pytest.skip("Symlink creation unavailable")
    before = (
        {p: p.read_bytes() for p in saved.rglob("*") if p.is_file()}
        if saved.is_dir()
        else {saved: saved.read_bytes()}
    )
    preview = plan(storage)
    assert preview.entries[0].status == "skipped"
    if level == "project":
        with pytest.raises(ValueError):
            execute(storage, preview)
    else:
        assert execute(storage, preview).entries[0].status == "skipped"
    assert all(p.read_bytes() == data for p, data in before.items())


@pytest.mark.skipif(os.name != "nt", reason="Windows junction")
def test_windows_junction_is_preserved(storage, tmp_path):
    path = abandoned(storage)
    outside = tmp_path / "outside"
    (path / "spill").rename(outside)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(path / "spill"), str(outside)],
        check=True,
        capture_output=True,
    )
    assert execute(storage).entries[0].status == "skipped"
    assert (outside / "duckdb_temp_storage-0.tmp").read_bytes() == b"spill"


@pytest.mark.parametrize(
    "level", ["project", "cache", "generation", "query", "spill", "file", "marker"]
)
def test_reparse_attribute_is_rejected_at_every_level(storage, monkeypatch, level):
    path = abandoned(storage)
    directory = storage[0].project_dir(storage[1])
    target = {
        "project": directory,
        "cache": path.parents[1],
        "generation": path.parent,
        "query": path,
        "spill": path / "spill",
        "file": path / "values.duckdb",
        "marker": path / MARKER,
    }[level]
    original = Path.lstat

    def lstat(p, *args, **kwargs):
        info = original(p, *args, **kwargs)
        if p == target:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", lstat)
    assert plan(storage).entries[0].status == "skipped"
    assert (path / "values.duckdb").read_bytes() == b"private payload"


def test_marker_publication_failure_does_not_yield_query_payload(storage, monkeypatch):
    def fail(_):
        raise OSError("injected synchronization failure")

    monkeypatch.setattr(_cache, "sync_directory", fail)
    with (
        pytest.raises(OSError, match="synchronization"),
        query_directory(storage[0].project_dir(storage[1]), storage[2]),
    ):
        pytest.fail("query must not start")
    assert plan(storage).entries[0].status == "candidate"
    assert execute(storage).entries[0].status == "removed"


def test_interruption_before_marker_preserves_unclassified_directory(
    storage, monkeypatch
):
    original = _cache.os.open

    def fail(path, *args, **kwargs):
        if Path(path).name == MARKER:
            raise OSError("marker failure")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(_cache.os, "open", fail)
        with pytest.raises(OSError, match="marker failure"):
            create_query_directory(storage[0].project_dir(storage[1]), storage[2])
    (result,) = execute(storage).entries
    assert result.status == "skipped" and result.reason == "missing_or_unmarked"


def test_failed_target_does_not_hide_other_cleanup_results(storage, monkeypatch):
    first, second = abandoned(storage), abandoned(storage)
    original = Path.unlink

    def fail(path, *args, **kwargs):
        if path == first / "values.duckdb":
            raise PermissionError("injected")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail)
    assert {e.status for e in execute(storage).entries} == {"removed", "error"}
    assert first.exists() and not second.exists()


@pytest.mark.parametrize("mutation", ["grow", "replace", "new"])
def test_execution_does_not_trust_stale_plan(storage, mutation):
    path = abandoned(storage)
    preview = plan(storage)
    if mutation == "grow":
        (path / "values.duckdb").write_bytes(b"larger new payload")
    elif mutation == "replace":
        path.rename(path.with_name("preserved"))
        path.mkdir()
        (path / MARKER).write_bytes((path.with_name("preserved") / MARKER).read_bytes())
    else:
        added = abandoned(storage)
    results = execute(storage, preview).entries
    assert any(e.status == "skipped" for e in results)
    if mutation != "new":
        assert path.exists()
    else:
        assert not path.exists() and added.exists()


def test_cross_project_plan_rejected(storage):
    abandoned(storage)
    with pytest.raises(ValueError, match="another project"):
        clean_query_caches(storage[0], new_project_id(), plan=plan(storage))


@pytest.mark.parametrize("ownership", [workspace_reader, workspace_writer])
def test_live_sessions_block_mutation(storage, ownership):
    path = abandoned(storage)
    preview = plan(storage)
    with ownership(storage[0]), pytest.raises(ProjectBusyError):
        execute(storage, preview)
    assert path.exists()
    assert execute(storage, preview).entries[0].status == "removed"


@pytest.mark.parametrize("failure", ["payload", "marker", "rmdir"])
def test_partial_failures_report_bytes_and_remain_retryable(
    storage, monkeypatch, failure
):
    path = abandoned(storage)
    real_unlink, real_rmdir = Path.unlink, Path.rmdir

    def unlink(p, *args, **kwargs):
        if p == path / ("values.duckdb" if failure == "payload" else MARKER):
            raise PermissionError("injected")
        return real_unlink(p, *args, **kwargs)

    def rmdir(p):
        if p == path:
            raise PermissionError("injected")
        return real_rmdir(p)

    with monkeypatch.context() as context:
        context.setattr(
            Path,
            "rmdir" if failure == "rmdir" else "unlink",
            rmdir if failure == "rmdir" else unlink,
        )
        (result,) = execute(storage).entries
    assert result.status == "error" and result.removed_bytes > 0
    assert (path / MARKER).is_file()
    assert execute(storage).entries[0].status == "removed"


def test_normal_teardown_preserves_unexpected_contents(storage):
    with (
        pytest.raises(OSError, match="Preserved query cache"),
        query_directory(storage[0].project_dir(storage[1]), storage[2]) as path,
    ):
        (path / "notes").write_text("keep")
    assert (path / "notes").read_text() == "keep"
    assert execute(storage).entries[0].status == "skipped"


def test_killed_query_is_reclaimable_and_live_materializer_blocks(tmp_path):
    location, _, _, outcome = publish(tmp_path, "v\n A \na\n")
    ready = tmp_path / "ready"
    process = child(
        """
from pathlib import Path
import sys
from tabalyst.projects import StorageLocation
from tabalyst.projects._generation import open_generation
from tabalyst.projects._queries import materialize_values
with open_generation(StorageLocation(Path(sys.argv[1])), sys.argv[2]) as pinned:
    with materialize_values(pinned, 'rows', 'column_1'):
        Path(sys.argv[3]).write_text('ready')
        sys.stdin.read()
""",
        location.root,
        outcome.project.project_id,
        ready,
    )
    try:
        wait_ready(process, ready)
        preview = inventory_query_caches(location, outcome.project.project_id)
        assert len(preview.entries) == 2
        with pytest.raises(ProjectBusyError):
            clean_query_caches(location, outcome.project.project_id, plan=preview)
    finally:
        process.kill()
        process.wait(timeout=5)
        process.communicate(timeout=5)
    before = hashes(location.projects_dir)
    result = clean_query_caches(
        location,
        outcome.project.project_id,
        plan=inventory_query_caches(location, outcome.project.project_id),
    )
    assert all(e.status == "removed" for e in result.entries)
    assert hashes(location.projects_dir) == before


@pytest.mark.parametrize("exposure", ["mask", "hide", "show"])
def test_rebuild_without_source_preserves_cursors_and_persistent_bytes(
    tmp_path, exposure
):
    location, source, _, outcome = publish(
        tmp_path,
        "v\nA@b.com\na@b.com\n a@b.com \nc@b.com\n",
        settings={"exposure": {"sensitive_values": exposure}},
        value_limit=2,
    )
    source.unlink()
    before = hashes(location.projects_dir)

    def pages(cursor=None):
        with (
            open_generation(location, outcome.project.project_id) as pinned,
            materialize_values(pinned, "rows", "column_1") as query,
        ):
            first = query.frequencies_page(size=1)
            _, frequencies = walk(query.frequencies_page, size=1, status="limited")
            _, groups = walk(query.groups_page, size=1, status="limited")
            variants = [
                (
                    g.key,
                    walk(
                        lambda key=g.key, **kw: query.variants_page(key, **kw),
                        status="limited",
                    )[1],
                )
                for g in groups
            ]
            if cursor or first.next_cursor:
                following = query.frequencies_page(
                    cursor=cursor or first.next_cursor, size=1
                )
            else:
                following = None
            return first, following, frequencies, groups, variants

    original = pages()
    stale = (location, outcome.project.project_id, new_project_id())
    abandoned(stale)
    assert (
        clean_query_caches(
            location,
            outcome.project.project_id,
            plan=inventory_query_caches(location, outcome.project.project_id),
        )
        .entries[0]
        .status
        == "removed"
    )
    assert pages(original[0].next_cursor) == original
    assert hashes(location.projects_dir) == before
