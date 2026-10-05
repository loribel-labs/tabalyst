# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Explicit private maintenance of owned disposable query directories.

Local OS locks protect cooperating sessions, not hostile filesystem writers.
Never infer ownership from a name/PID or recursively delete a cache root.
"""

import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

from tabalyst.projects._locks import workspace_maintenance
from tabalyst.projects._sync import sync_directory
from tabalyst.projects.identity import is_project_id, new_project_id
from tabalyst.projects.location import StorageLocation

MARKER = ".tabalyst-query.json"
_SPILL = re.compile(r"duckdb_temp_(?:storage-\d+\.tmp|block-[\w-]+\.block)\Z")


@dataclass(frozen=True)
class CacheEntry:
    path: str  # relative to the chosen project
    status: str
    reason: str | None = None
    logical_bytes: int = 0
    removed_bytes: int = 0
    # Private comparison evidence, never trusted without fresh inventory.
    signature: tuple = field(default=(), repr=False)


@dataclass(frozen=True)
class CacheInventory:
    workspace_id: str
    project_id: str
    root: str
    entries: tuple[CacheEntry, ...]


def _safe_stat(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("link_or_reparse_point")
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise ValueError("multiple_file_links")
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise ValueError("unsupported_file_kind")
    return info


def _identity(info):
    return (info.st_dev, info.st_ino)


def _project_directory(location, project_id):
    directory = location.project_dir(project_id).absolute()
    root = location.root.absolute()
    # Check every storage component, not just the final target.
    for path in [root, *reversed(directory.parents[:3]), directory]:
        if not stat.S_ISDIR(_safe_stat(path).st_mode):
            raise ValueError("not_a_directory")
    if not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError("outside_storage_root")
    return directory


def _marker_bytes(location, project_id, generation_id, query_id):
    return json.dumps(
        {
            "format": "tabalyst.query-cache",
            "revision": 1,
            "workspace_id": location.workspace_id,
            "project_id": project_id,
            "generation_id": generation_id,
            "query_id": query_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _query_parents(path, directory):
    cache = directory / "cache"
    generation = path.parent
    if generation.parent != cache or not is_project_id(generation.name):
        raise ValueError("invalid_query_path")
    identities = []
    for parent in (cache, generation):
        info = _safe_stat(parent)
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("not_a_directory")
        identities.append(_identity(info))
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("outside_project")
    return tuple(identities)


def _inspect(path, directory, location, project_id):
    relative = path.relative_to(directory).as_posix()
    try:
        parents = _query_parents(path, directory)
        folder = _safe_stat(path)
        if not stat.S_ISDIR(folder.st_mode):
            raise ValueError("not_a_directory")
        query_id = path.name.removeprefix("query-")
        generation_id = path.parent.name
        if not path.name.startswith("query-") or not is_project_id(query_id):
            raise ValueError("unknown_query_directory")
        marker = path / MARKER
        info = _safe_stat(marker)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
            raise ValueError("invalid_marker")
        with marker.open("rb") as stream:
            payload = stream.read(4097)
        expected = _marker_bytes(location, project_id, generation_id, query_id)
        # Strict canonical marker: rejects extra keys, bool revisions and duplicates.
        if payload != expected:
            raise ValueError("invalid_or_unsupported_marker")
        files = []
        directories = []
        for entry in sorted(path.iterdir()):
            child = _safe_stat(entry)
            if entry.name == "spill" and stat.S_ISDIR(child.st_mode):
                directories.append(("spill", _identity(child)))
                for spill in sorted(entry.iterdir()):
                    spill_info = _safe_stat(spill)
                    if not stat.S_ISREG(spill_info.st_mode) or not _SPILL.fullmatch(
                        spill.name
                    ):
                        raise ValueError("unknown_contents")
                    files.append((spill.relative_to(path).as_posix(), spill_info))
            elif entry.name in (
                MARKER,
                "values.duckdb",
                "values.duckdb.wal",
            ) and stat.S_ISREG(child.st_mode):
                files.append((entry.name, child))
            else:
                raise ValueError("unknown_contents")
        signature = (
            _identity(folder),
            payload,
            tuple(directories),
            tuple(
                (
                    name,
                    _identity(item),
                    item.st_size,
                    item.st_mtime_ns,
                    item.st_ctime_ns,
                )
                for name, item in files
            ),
            parents,
        )
        return CacheEntry(
            relative,
            "candidate",
            logical_bytes=sum(item.st_size for _, item in files),
            signature=signature,
        )
    except FileNotFoundError:
        return CacheEntry(relative, "skipped", "missing_or_unmarked")
    except ValueError as exc:
        return CacheEntry(relative, "skipped", str(exc))
    except OSError as exc:
        return CacheEntry(relative, "error", type(exc).__name__)


def inventory_query_caches(location, project_id):
    """Read metadata only; return an advisory immutable dry-run plan."""
    entries = []
    try:
        directory = _project_directory(location, project_id)
        cache = directory / "cache"
        if not stat.S_ISDIR(_safe_stat(cache).st_mode):
            raise ValueError("not_a_directory")
        for generation in sorted(cache.iterdir()):
            try:
                if not stat.S_ISDIR(
                    _safe_stat(generation).st_mode
                ) or not is_project_id(generation.name):
                    raise ValueError("unknown_generation_directory")
                entries.extend(
                    _inspect(p, directory, location, project_id)
                    for p in sorted(generation.iterdir())
                )
            except ValueError as exc:
                entries.append(
                    CacheEntry(
                        generation.relative_to(directory).as_posix(),
                        "skipped",
                        str(exc),
                    )
                )
            except OSError as exc:
                entries.append(
                    CacheEntry(
                        generation.relative_to(directory).as_posix(),
                        "error",
                        type(exc).__name__,
                    )
                )
    except FileNotFoundError:
        # Missing project/cache is an empty inventory; no directory is created.
        pass
    except ValueError as exc:
        entries.append(CacheEntry("cache", "skipped", str(exc)))
    except OSError as exc:
        entries.append(CacheEntry("cache", "error", type(exc).__name__))
    return CacheInventory(
        location.workspace_id, project_id, str(location.root.absolute()), tuple(entries)
    )


def _remove_candidate(location, project_id, entry):
    removed = 0
    try:
        directory = _project_directory(location, project_id)
    except (OSError, ValueError) as exc:
        return CacheEntry(entry.path, "error", type(exc).__name__)
    path = directory / entry.path
    fresh = _inspect(path, directory, location, project_id)
    if fresh.status != "candidate" or fresh.signature != entry.signature:
        return CacheEntry(entry.path, "skipped", "changed_since_inventory")
    marker = path / MARKER
    payload = entry.signature[1]
    try:
        # Delete only the inventoried regular files, marker last. No rmtree.
        for name, identity, size, modified, changed in sorted(
            entry.signature[3], key=lambda item: item[0] == MARKER
        ):
            _project_directory(location, project_id)
            if _query_parents(path, directory) != entry.signature[4]:
                raise ValueError("parent_replaced")
            if _identity(_safe_stat(path)) != entry.signature[0]:
                raise ValueError("target_replaced")
            target = path / name
            if target.parent != path:
                spill_identity = dict(entry.signature[2])["spill"]
                if _identity(_safe_stat(target.parent)) != spill_identity:
                    raise ValueError("spill_replaced")
            info = _safe_stat(target)
            if (_identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns) != (
                identity,
                size,
                modified,
                changed,
            ):
                raise ValueError("file_changed")
            if name == MARKER:
                if (path / "spill").exists():
                    (path / "spill").rmdir()
                if {p.name for p in path.iterdir()} != {MARKER}:
                    raise ValueError("contents_changed")
            target.unlink()
            removed += size
        path.rmdir()
        return CacheEntry(
            entry.path,
            "removed",
            logical_bytes=entry.logical_bytes,
            removed_bytes=removed,
        )
    except (OSError, ValueError) as exc:
        # Retain retry classification on an ordinary final-rmdir failure.
        if path.exists() and not marker.exists():
            try:
                _project_directory(location, project_id)
                if (
                    _query_parents(path, directory) == entry.signature[4]
                    and _identity(_safe_stat(path)) == entry.signature[0]
                ):
                    descriptor = os.open(
                        marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                    )
                    with os.fdopen(descriptor, "wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    removed -= len(payload)
            except (OSError, ValueError):
                pass
        return CacheEntry(
            entry.path, "error", type(exc).__name__, entry.logical_bytes, removed
        )


def clean_query_caches(location, project_id, *, plan):
    """Explicitly execute unchanged planned candidates under exclusive ownership."""
    binding = (location.workspace_id, project_id, str(location.root.absolute()))
    if (
        not isinstance(plan, CacheInventory)
        or (plan.workspace_id, plan.project_id, plan.root) != binding
    ):
        raise ValueError("Cache plan belongs to another project/storage root")
    # Validate storage parents before acquiring locks through those paths.
    try:
        _project_directory(location, project_id)
    except FileNotFoundError:
        return inventory_query_caches(location, project_id)
    with workspace_maintenance(location):
        fresh = inventory_query_caches(location, project_id)
        planned = {
            entry.path: entry for entry in plan.entries if entry.status == "candidate"
        }
        results = []
        for entry in fresh.entries:
            previous = planned.get(entry.path)
            if (
                entry.status == "candidate"
                and previous is not None
                and entry.signature == previous.signature
            ):
                results.append(_remove_candidate(location, project_id, entry))
            elif entry.status == "candidate":
                results.append(
                    CacheEntry(
                        entry.path,
                        "skipped",
                        "new_or_changed_since_plan",
                        entry.logical_bytes,
                    )
                )
            else:
                results.append(entry)
        return CacheInventory(*binding, tuple(results))


def create_query_directory(project_dir, generation_id):
    """Create and mark a fresh directory before any query payload is written."""
    if not is_project_id(generation_id):
        raise ValueError("Invalid generation id")
    project_dir = Path(project_dir).absolute()
    if (
        project_dir.parent.name != "projects"
        or project_dir.parents[2].name != "workspaces"
    ):
        raise ValueError("Invalid project storage layout")
    location = StorageLocation(project_dir.parents[3], project_dir.parents[1].name)
    _project_directory(location, project_dir.name)
    cache = project_dir / "cache"
    generation = cache / generation_id
    for parent in (cache, generation):
        parent.mkdir(mode=0o700, exist_ok=True)
        if not stat.S_ISDIR(_safe_stat(parent).st_mode):
            raise ValueError("Invalid cache parent")
    query_id = new_project_id()
    path = generation / f"query-{query_id}"
    path.mkdir(mode=0o700)
    descriptor = os.open(path / MARKER, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(_marker_bytes(location, project_dir.name, generation_id, query_id))
        stream.flush()
        os.fsync(stream.fileno())
    sync_directory(path)
    return path, location


def dispose_query_directory(path, location):
    """Normal owner teardown; called only after all query handles close."""
    directory = path.parents[2]
    entry = _inspect(path, directory, location, directory.name)
    if entry.status != "candidate":
        raise OSError(f"Preserved query cache: {entry.reason}")
    result = _remove_candidate(location, directory.name, entry)
    if result.status != "removed":
        raise OSError(f"Preserved query cache: {result.reason}")
