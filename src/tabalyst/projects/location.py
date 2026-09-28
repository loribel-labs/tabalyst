"""Where project storage lives (project-storage.md S01, S03).

The layout under a storage root is the same in local and SaaS mode::

    <root>/workspaces/<workspace_id>/projects/<project_id>/

Only the root differs. Locally it is the user data directory of the platform,
or the directory named by ``TABALYST_HOME``, which tests and a server can use
to relocate storage.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from tabalyst.errors import ConfigurationError, InputError
from tabalyst.projects.identity import is_project_id

ROOT_ENVIRONMENT_VARIABLE = "TABALYST_HOME"
LOCAL_WORKSPACE = "local"

PROJECT_FILE_NAME = "project.json"
INDEX_FILE_NAME = "index.json"


def local_storage_root() -> Path:
    """The storage root of local mode.

    ``TABALYST_HOME`` when set and not empty, otherwise the platform's user
    data directory: ``Tabalyst`` under ``%LOCALAPPDATA%`` on Windows,
    ``~/Library/Application Support/Tabalyst`` on macOS and
    ``$XDG_DATA_HOME/tabalyst`` (``~/.local/share/tabalyst``) elsewhere.
    """
    override = os.environ.get(ROOT_ENVIRONMENT_VARIABLE, "").strip()
    if override:
        return Path(override).expanduser().resolve()
    name = "Tabalyst" if sys.platform in ("win32", "darwin") else "tabalyst"
    return Path(platformdirs.user_data_dir(name, appauthor=False))


def _valid_workspace_id(value: str) -> bool:
    return bool(value) and all(
        character.isascii() and (character.isalnum() or character in "-_")
        for character in value
    )


@dataclass(frozen=True)
class StorageLocation:
    """A storage root and a workspace; every project path derives from them."""

    root: Path
    workspace_id: str = LOCAL_WORKSPACE

    def __post_init__(self) -> None:
        if not _valid_workspace_id(self.workspace_id):
            raise ConfigurationError(
                f"Invalid workspace id {self.workspace_id!r}: use letters, "
                "digits, hyphens and underscores."
            )

    @classmethod
    def local(cls) -> "StorageLocation":
        return cls(local_storage_root(), LOCAL_WORKSPACE)

    @property
    def projects_dir(self) -> Path:
        return self.root / "workspaces" / self.workspace_id / "projects"

    @property
    def index_path(self) -> Path:
        return self.projects_dir / INDEX_FILE_NAME

    def project_dir(self, project_id: str) -> Path:
        if not is_project_id(project_id):
            raise InputError(f"Not a project id: {project_id!r}.")
        return self.projects_dir / project_id

    def project_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / PROJECT_FILE_NAME
