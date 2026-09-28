"""Finding, creating and updating the projects of a workspace.

Creating a project and its first scan are one operation (project-storage.md
principle 5): the scan layer that will write ``scan.json`` and
``project.duckdb`` calls ``create_project`` first, then ``record_scan`` when
the scan succeeds.
"""

import contextlib
from datetime import datetime
from pathlib import Path

from tabalyst.projects.identity import new_project_id
from tabalyst.projects.index import find_project, register_project
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.models import ProjectDocument, ProjectSource, utc_now
from tabalyst.projects.store import read_project, write_project


def create_project(
    location: StorageLocation, source: Path, *, now: datetime | None = None
) -> ProjectDocument:
    """Create a project for ``source``, whatever projects it already has.

    The source is not read: the path is only resolved and recorded. The index
    is updated after ``project.json``, so an interrupted creation leaves at
    worst a project the next lookup finds by rebuilding the index.
    """
    resolved = source.resolve()
    moment = now or utc_now()
    document = ProjectDocument(
        project_id=new_project_id(),
        workspace_id=location.workspace_id,
        created_at=moment,
        last_scan_at=moment,
        source=ProjectSource(path=resolved.as_posix(), name=resolved.name),
    )
    try:
        write_project(location, document)
    except BaseException:
        # Leave no empty project directory behind; a non-empty one is not ours.
        with contextlib.suppress(OSError):
            location.project_dir(document.project_id).rmdir()
        raise
    register_project(location, document)
    return document


def open_or_create_project(
    location: StorageLocation, source: Path, *, now: datetime | None = None
) -> ProjectDocument:
    """The project of ``source``, created when it has none."""
    return find_project(location, source) or create_project(
        location, source, now=now
    )


def record_scan(
    location: StorageLocation, project_id: str, *, now: datetime | None = None
) -> ProjectDocument:
    """Record a successful scan: ``last_scan_at`` moves, ``created_at`` does not."""
    document = read_project(location, project_id)
    updated = document.model_copy(
        update={"last_scan_at": now or utc_now()}
    )
    write_project(location, updated)
    return updated
