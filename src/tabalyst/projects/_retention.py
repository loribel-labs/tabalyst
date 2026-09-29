"""Remove a superseded project generation after successful publication."""

import stat
from pathlib import Path

from tabalyst.projects._cache import _remove_candidate, inventory_query_caches
from tabalyst.projects._locks import ProjectBusyError, workspace_maintenance
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.models import ProjectManifest
from tabalyst.projects.store import read_project


def _regular_file(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not (
        getattr(info, "st_file_attributes", 0) & 0x400
    )


def remove_superseded_generation(
    location: StorageLocation,
    project_id: str,
    previous_id: str,
    selected_id: str,
) -> str | None:
    """Remove only the previously selected pair and its owned cache.

    A reader or an unexpected file leaves the old generation intact. The new
    manifest has already committed, so failures become explicit warnings.
    """
    try:
        with workspace_maintenance(location):
            project = read_project(location, project_id)
            if (
                not isinstance(project, ProjectManifest)
                or project.generation.id != selected_id
            ):
                return "A newer project generation was selected; old scan retained."
            project_dir = location.project_dir(project_id).resolve()
            old_dir = location.generation_dir(project_id, previous_id)
            if not old_dir.exists():
                return None
            if (
                old_dir.resolve() != project_dir / "generations" / previous_id
                or not stat.S_ISDIR(old_dir.lstat().st_mode)
            ):
                return "Unexpected old generation path; old scan retained."
            contents = {path.name for path in old_dir.iterdir()}
            if contents != {"scan.json", "project.duckdb"} or not all(
                _regular_file(old_dir / name) for name in contents
            ):
                return "Unexpected old generation contents; old scan retained."
            inventory = inventory_query_caches(location, project_id)
            prefix = f"cache/{previous_id}/"
            for entry in inventory.entries:
                if entry.path.startswith(prefix):
                    if entry.status != "candidate":
                        return "Old query cache contains unknown files; old scan retained."
                    removed = _remove_candidate(location, project_id, entry)
                    if removed.status != "removed":
                        return "Old query cache could not be removed; old scan retained."
            cache_generation = project_dir / "cache" / previous_id
            if cache_generation.exists():
                cache_generation.rmdir()
            (old_dir / "scan.json").unlink()
            (old_dir / "project.duckdb").unlink()
            old_dir.rmdir()
    except (OSError, ValueError, ProjectBusyError) as exc:
        return f"Old generation retained: {exc}"
    return None
