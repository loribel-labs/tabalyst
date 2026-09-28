"""``projects/index.json``: the lookup from a source path to its project.

The index is a convenience, never an authority (project-storage.md S08): it
is rebuilt from the ``project.json`` files, so a missing, corrupt or stale
index degrades to a rebuild, never to wrong data.
"""

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from tabalyst.batch import path_key, write_text_atomic
from tabalyst.errors import InputError
from tabalyst.projects.identity import is_project_id
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.models import ProjectDocument
from tabalyst.projects.store import list_projects, read_project

FORMAT = "tabalyst.project-index"
FORMAT_VERSION = "0.1.0a"
FORMAT_REVISION = 1


class ProjectIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["tabalyst.project-index"] = FORMAT
    format_version: Literal["0.1.0a"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    # ``source_key`` of the resolved source path -> project id.
    projects: dict[str, str] = {}

    @field_validator("projects")
    @classmethod
    def _ids(cls, value: dict[str, str]) -> dict[str, str]:
        if not all(is_project_id(project_id) for project_id in value.values()):
            raise ValueError("not a project id")
        return value


def source_key(source: Path) -> str:
    """The key of a source path in the index."""
    return path_key(source)


def document_key(document: ProjectDocument) -> str:
    """The key of a project's stored source path.

    ``project.json`` holds an already resolved path, so no file access is
    needed; it equals ``source_key`` of the same file.
    """
    return os.path.normcase(str(Path(document.source.path)))


def read_index(location: StorageLocation) -> ProjectIndex | None:
    """The index, or ``None`` when it is missing or unusable."""
    try:
        document = json.loads(location.index_path.read_text(encoding="utf-8"))
        return ProjectIndex.model_validate(document)
    except (OSError, ValueError):
        return None


def write_index(location: StorageLocation, index: ProjectIndex) -> None:
    text = json.dumps(index.model_dump(mode="json"), indent=2, ensure_ascii=False)
    write_text_atomic(location.index_path, text + "\n")


def rebuild_index(location: StorageLocation) -> ProjectIndex:
    """Rebuild the index from the ``project.json`` files and store it.

    Several projects for one path keep the most recently created (ids break
    ties). The file is written only when it changes, and never for an empty
    workspace.
    """
    documents = sorted(
        list_projects(location), key=lambda item: (item.created_at, item.project_id)
    )
    entries = {document_key(document): document.project_id for document in documents}
    index = ProjectIndex(projects=entries)
    existing = read_index(location)
    if existing != index and (entries or existing is not None):
        write_index(location, index)
    return index


def register_project(location: StorageLocation, document: ProjectDocument) -> None:
    """Add a project, which replaces any other project of the same path."""
    index = read_index(location)
    if index is None:
        index = rebuild_index(location)
    key = document_key(document)
    if index.projects.get(key) != document.project_id:
        index.projects[key] = document.project_id
        write_index(location, index)


def find_project(location: StorageLocation, source: Path) -> ProjectDocument | None:
    """The project of a source path, or ``None`` when it has none.

    An index entry is trusted only after its ``project.json`` confirms the
    path. Any other outcome rebuilds the index once and answers from it.
    """
    key = source_key(source)
    index = read_index(location)
    project_id = index.projects.get(key) if index is not None else None
    if project_id is not None:
        try:
            document = read_project(location, project_id)
        except InputError:
            pass
        else:
            if document_key(document) == key:
                return document
    project_id = rebuild_index(location).projects.get(key)
    if project_id is None:
        return None
    return read_project(location, project_id)
