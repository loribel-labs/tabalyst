"""Whether a project's scan still describes its source (project-storage.md S09).

The comparison is the one of the report's staleness rule (O12,
``tabalyst.scan_reuse.compare_source``); only the location differs: the source
is found through the path in ``project.json``, and the facts it is compared
with are those of the project's ``scan.json`` (S05). What to do with a stale
project is not decided here (D04).
"""

from dataclasses import dataclass
from pathlib import Path

from tabalyst.errors import InputError
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.models import ProjectManifest
from tabalyst.projects.store import read_project
from tabalyst.scan_reuse import SourceCheck, compare_source, load_scan


@dataclass(frozen=True)
class ProjectFreshness:
    project_id: str
    # The source as located by ``project.json``.
    source: Path
    check: SourceCheck


def project_freshness(location: StorageLocation, project_id: str) -> ProjectFreshness:
    """Compare a project's source with the facts its ``scan.json`` recorded.

    Raises ``InputError`` when the project or its scan document is missing or
    invalid, or when the source exists but cannot be read.
    """
    document = read_project(location, project_id)
    if isinstance(document, ProjectManifest):
        from tabalyst.projects._generation import open_generation

        with open_generation(location, project_id) as pinned:
            return ProjectFreshness(
                project_id, Path(pinned.project.source.path), pinned.freshness()
            )
    scan_path = location.scan_path(project_id)
    if not scan_path.is_file():
        raise InputError(
            f"Project {project_id} has no scan document: no {scan_path}. "
            "Scan the source again to complete the project."
        )
    result = load_scan(scan_path)
    source = Path(document.source.path)
    return ProjectFreshness(
        project_id=project_id,
        source=source,
        check=compare_source(source, result.source),
    )
