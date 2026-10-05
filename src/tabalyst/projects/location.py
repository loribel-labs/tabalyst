# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Where project storage lives (project-storage.md S01, S03).

The layout under a storage root is the same in local and SaaS mode::

    <root>/workspaces/<workspace_id>/projects/<project_id>/

Only the root differs. Locally it is the user data directory of the platform,
or the directory named by ``TABALYST_HOME``, which tests and a server can use
to relocate storage.
"""

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from tabalyst.batch import path_key
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.projects.identity import is_project_id

ROOT_ENVIRONMENT_VARIABLE = "TABALYST_HOME"
LOCAL_WORKSPACE = "local"

PROJECT_FILE_NAME = "project.json"
SCAN_FILE_NAME = "scan.json"
INSPECT_FILE_NAME = "inspect.json"
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
        return self.workspace_dir / "projects"

    def _shared_source_dir(self, source: Path) -> Path:
        key = path_key(source.resolve()).encode("utf-8", "surrogatepass")
        return self.workspace_dir / "scans" / hashlib.sha256(key).hexdigest()

    def shared_scan_path(self, source: Path) -> Path:
        """The scan-only document for a resolved source, independent of DuckDB projects."""
        return self._shared_source_dir(source) / SCAN_FILE_NAME

    def shared_inspect_path(self, source: Path) -> Path:
        """The automatic Inspect cache of a source, beside its shared scan document."""
        return self._shared_source_dir(source) / INSPECT_FILE_NAME

    @property
    def workspace_dir(self) -> Path:
        return self.root / "workspaces" / self.workspace_id

    @property
    def writer_lock_path(self) -> Path:
        return self.workspace_dir / ".writer.lock"

    @property
    def maintenance_lock_path(self) -> Path:
        return self.workspace_dir / ".maintenance.lock"

    @property
    def index_path(self) -> Path:
        return self.projects_dir / INDEX_FILE_NAME

    def project_dir(self, project_id: str) -> Path:
        if not is_project_id(project_id):
            raise InputError(f"Not a project id: {project_id!r}.")
        return self.projects_dir / project_id

    def project_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / PROJECT_FILE_NAME

    def generation_dir(self, project_id: str, generation_id: str) -> Path:
        if not is_project_id(generation_id):
            raise InputError(f"Not a generation id: {generation_id!r}.")
        return self.project_dir(project_id) / "generations" / generation_id

    def staging_dir(self, project_id: str, generation_id: str) -> Path:
        if not is_project_id(generation_id):
            raise InputError(f"Not a generation id: {generation_id!r}.")
        return self.project_dir(project_id) / ".staging" / generation_id

    def scan_path(self, project_id: str, generation_id: str | None = None) -> Path:
        """Legacy path, or an explicitly pinned generation. Never resolves a manifest."""
        parent = (
            self.project_dir(project_id)
            if generation_id is None
            else self.generation_dir(project_id, generation_id)
        )
        return parent / SCAN_FILE_NAME

    def database_path(self, project_id: str, generation_id: str) -> Path:
        return self.generation_dir(project_id, generation_id) / "project.duckdb"
