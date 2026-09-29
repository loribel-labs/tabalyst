"""Conservative explicit quarantine; no automatic generation selection/deletion."""

from pathlib import Path

from tabalyst.errors import InputError
from tabalyst.projects._locks import workspace_maintenance
from tabalyst.projects._sync import sync_directory
from tabalyst.projects.identity import is_project_id, new_project_id
from tabalyst.projects.models import ProjectManifest
from tabalyst.projects.store import read_project


def quarantine_uncommitted(location, project_id: str) -> tuple[Path, ...]:
    """Move unselected ULID directories only when no session is active.

    Corrupt manifests fail closed. Unknown names/symlinks stay in place.
    Scans never call this function or delete any old generation.
    """
    directory = location.project_dir(project_id)
    if not directory.is_dir() or directory.is_symlink():
        raise InputError("Project directory is missing or is a symlink")
    with workspace_maintenance(location):
        selected = None
        if location.project_path(project_id).exists():
            document = read_project(location, project_id)
            if isinstance(document, ProjectManifest):
                from tabalyst.projects._generation import verify_generation

                verify_generation(location, document)
                selected = document.generation.id
        moved = []
        quarantine = directory / ".quarantine"
        for category, base in (
            ("staging", directory / ".staging"),
            ("generation", directory / "generations"),
        ):
            if not base.exists():
                continue
            if base.is_symlink():
                raise InputError("Cannot quarantine a symlinked storage directory")
            for entry in sorted(base.iterdir()):
                if (
                    not is_project_id(entry.name)
                    or not entry.is_dir()
                    or entry.is_symlink()
                    or (category == "generation" and entry.name == selected)
                ):
                    continue
                quarantine.mkdir(mode=0o700, exist_ok=True)
                if quarantine.is_symlink():
                    raise InputError("Cannot quarantine into a symlink")
                destination = quarantine / f"{entry.name}-{category}-{new_project_id()}"
                entry.rename(destination)
                moved.append(destination)
            sync_directory(base)
        if moved:
            sync_directory(quarantine)
            sync_directory(directory)
        return tuple(moved)
