"""Public cleanup of disposable project query caches."""

from dataclasses import dataclass
from pathlib import Path

from tabalyst.errors import InputError
from tabalyst.projects._cache import clean_query_caches, inventory_query_caches
from tabalyst.projects._locks import ProjectBusyError
from tabalyst.projects.identity import is_project_id
from tabalyst.projects.index import (
    document_key,
    find_project,
    read_index,
    source_key,
)
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.store import read_project


@dataclass(frozen=True)
class CacheCleanResult:
    projects: int
    removed: int
    removed_bytes: int
    skipped: tuple[str, ...]


@dataclass(frozen=True)
class CacheInfo:
    projects: int
    directories: int
    logical_bytes: int
    skipped: tuple[str, ...]


def _selected_projects(
    source: str | Path | None = None,
    *,
    location: StorageLocation | None = None,
) -> tuple[StorageLocation, list]:
    location = location or StorageLocation.local()
    if source is None:
        try:
            directories = sorted(location.projects_dir.iterdir())
        except FileNotFoundError:
            directories = []
        projects = []
        for directory in directories:
            if is_project_id(directory.name):
                try:
                    projects.append(read_project(location, directory.name))
                except InputError:
                    continue
    else:
        key = source_key(Path(source))
        index = read_index(location)
        project_id = index.projects.get(key) if index else None
        try:
            selected = read_project(location, project_id) if project_id else None
        except InputError:
            selected = None
        if selected is None or document_key(selected) != key:
            selected = find_project(location, Path(source))
        if selected is None:
            raise InputError(f"No Tabalyst project for source: {source}")
        projects = [selected]
    return location, projects


def cache_info(
    source: str | Path | None = None,
    *,
    location: StorageLocation | None = None,
) -> CacheInfo:
    """Summarize owned disposable cache files without modifying them."""
    location, projects = _selected_projects(source, location=location)
    directories = 0
    logical_bytes = 0
    skipped = []
    for project in projects:
        inventory = inventory_query_caches(location, project.project_id)
        for entry in inventory.entries:
            if entry.status == "candidate":
                directories += 1
                logical_bytes += entry.logical_bytes
            else:
                skipped.append(f"{project.project_id}/{entry.path}: {entry.reason}")
    return CacheInfo(len(projects), directories, logical_bytes, tuple(skipped))


def clean_cache(
    source: str | Path | None = None,
    *,
    location: StorageLocation | None = None,
) -> CacheCleanResult:
    """Clean owned disposable cache files for one source or all projects."""
    location, projects = _selected_projects(source, location=location)
    removed = 0
    removed_bytes = 0
    skipped = []
    for project in projects:
        plan = inventory_query_caches(location, project.project_id)
        try:
            result = clean_query_caches(location, project.project_id, plan=plan)
        except ProjectBusyError as exc:
            skipped.append(f"{project.project_id}/cache: {exc}")
            continue
        for entry in result.entries:
            if entry.status == "removed":
                removed += 1
                removed_bytes += entry.removed_bytes
            elif entry.status in ("skipped", "error"):
                skipped.append(f"{project.project_id}/{entry.path}: {entry.reason}")
    return CacheCleanResult(len(projects), removed, removed_bytes, tuple(skipped))
