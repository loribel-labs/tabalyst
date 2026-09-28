"""Reading and writing ``project.json`` and listing the projects of a workspace."""

import json
from pathlib import Path

from pydantic import ValidationError

from tabalyst.batch import write_text_atomic
from tabalyst.config import validation_message
from tabalyst.errors import InputError
from tabalyst.projects.identity import is_project_id
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.models import (
    FORMAT,
    FORMAT_REVISION,
    FORMAT_VERSION,
    ProjectDocument,
)


def project_document_text(document: ProjectDocument) -> str:
    text = json.dumps(document.model_dump(mode="json"), indent=2, ensure_ascii=False)
    return text + "\n"


def write_project(location: StorageLocation, document: ProjectDocument) -> Path:
    """Write ``project.json`` atomically (O17) and return its path."""
    if document.workspace_id != location.workspace_id:
        raise ValueError(
            f"Project {document.project_id} belongs to workspace "
            f"{document.workspace_id!r}, not {location.workspace_id!r}."
        )
    path = location.project_path(document.project_id)
    write_text_atomic(path, project_document_text(document))
    return path


def read_project(location: StorageLocation, project_id: str) -> ProjectDocument:
    """The ``project.json`` of a project, validated.

    Raises ``InputError`` when the project does not exist or its file is not
    a valid project document of this workspace.
    """
    path = location.project_path(project_id)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputError(f"Project {project_id} not found: no {path}.") from exc
    except OSError as exc:
        raise InputError(f"Cannot read project document {path}: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InputError(
            f"Not a project document: {path} is not valid UTF-8 JSON ({exc})."
        ) from exc
    if not isinstance(document, dict) or document.get("format") != FORMAT:
        raise InputError(f"Not a project document: {path}.")
    version = (document.get("format_version"), document.get("format_revision"))
    if version != (FORMAT_VERSION, FORMAT_REVISION):
        raise InputError(
            f"Unsupported project document {path}: format {version[0]} revision "
            f"{version[1]}; this version of Tabalyst reads format "
            f"{FORMAT_VERSION} revision {FORMAT_REVISION}."
        )
    try:
        result = ProjectDocument.model_validate(document)
    except ValidationError as exc:
        raise InputError(
            f"Invalid project document {path}: {validation_message(exc)}"
        ) from exc
    # The directory name is the identity: a copied or renamed file must not
    # pass for another project.
    if result.project_id != project_id or result.workspace_id != location.workspace_id:
        raise InputError(
            f"Invalid project document {path}: it describes project "
            f"{result.project_id} of workspace {result.workspace_id!r}."
        )
    return result


def list_projects(location: StorageLocation) -> list[ProjectDocument]:
    """The valid projects of the workspace, ordered by project id.

    Entries that are not project directories (the index file, temporary
    files) and directories whose ``project.json`` is missing or invalid, such
    as an interrupted creation, are skipped.
    """
    try:
        names = sorted(entry.name for entry in location.projects_dir.iterdir())
    except FileNotFoundError:
        return []
    documents = []
    for name in names:
        if not is_project_id(name):
            continue
        try:
            documents.append(read_project(location, name))
        except InputError:
            continue
    return documents
