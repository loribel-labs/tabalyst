# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Project storage: identity, location, ``project.json`` and freshness.

Internal for now: not part of the public ``tabalyst`` API. See
``docs/dev/scan/project-storage.md``.
"""

from tabalyst.projects.catalog import (
    create_project,
    open_or_create_project,
    record_scan,
)
from tabalyst.projects.freshness import ProjectFreshness, project_freshness
from tabalyst.projects.identity import is_project_id, new_project_id
from tabalyst.projects.index import (
    ProjectIndex,
    find_project,
    read_index,
    rebuild_index,
)
from tabalyst.projects.location import (
    LOCAL_WORKSPACE,
    StorageLocation,
    local_storage_root,
)
from tabalyst.projects.models import ProjectDocument, ProjectSource
from tabalyst.projects.store import list_projects, read_project, write_project

__all__ = [
    "LOCAL_WORKSPACE",
    "ProjectDocument",
    "ProjectFreshness",
    "ProjectIndex",
    "ProjectSource",
    "StorageLocation",
    "create_project",
    "find_project",
    "is_project_id",
    "list_projects",
    "local_storage_root",
    "new_project_id",
    "open_or_create_project",
    "project_freshness",
    "read_index",
    "read_project",
    "rebuild_index",
    "record_scan",
    "write_project",
]
