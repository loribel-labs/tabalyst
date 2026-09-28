"""``project.json`` (project-storage.md section 5), format revision 1.

Identity and location only. The size, modification time and SHA-256 of the
source stay in ``scan.json``'s ``source`` block (S05), the scan engine and
document versions in its ``engine`` and format fields.
"""

from datetime import UTC, datetime
from pathlib import PurePath, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from tabalyst.projects.identity import is_project_id

FORMAT = "tabalyst.project"
FORMAT_VERSION = "0.1.0a"
FORMAT_REVISION = 1


class ProjectModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectSource(ProjectModel):
    # Absolute, with forward slashes; it only locates the file and is never
    # part of the project's identity (principle 2).
    path: str
    # Basename of ``path``, kept to display the project without ``scan.json``.
    name: str

    @field_validator("path")
    @classmethod
    def _path_is_absolute(cls, value: str) -> str:
        if not (
            PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()
        ):
            raise ValueError("must be an absolute path")
        return value

    @field_validator("name")
    @classmethod
    def _name_is_a_file_name(cls, value: str) -> str:
        if not value or PurePath(value).name != value:
            raise ValueError("must be a file name")
        return value


class ProjectDocument(ProjectModel):
    format: Literal["tabalyst.project"] = FORMAT
    format_version: Literal["0.1.0a"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    project_id: str
    workspace_id: str
    # UTC, whole seconds. ``created_at`` never changes; ``last_scan_at``
    # moves on every successful scan.
    created_at: datetime
    last_scan_at: datetime
    source: ProjectSource

    @field_validator("project_id")
    @classmethod
    def _project_id_form(cls, value: str) -> str:
        if not is_project_id(value):
            raise ValueError("not a project id")
        return value

    @field_validator("created_at", "last_scan_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("must include a time zone")
        return value.astimezone(UTC).replace(microsecond=0)


def utc_now() -> datetime:
    """The current UTC time in whole seconds, as ``project.json`` records it."""
    return datetime.now(UTC).replace(microsecond=0)
