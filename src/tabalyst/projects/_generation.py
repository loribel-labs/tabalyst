"""Pinned read-only generation sessions, verified before any data access."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import duckdb

from tabalyst.errors import InputError
from tabalyst.projects._codec import DatabaseValidationError
from tabalyst.projects._locks import workspace_reader
from tabalyst.projects._query_budget import (
    QueryBudget,
    apply_spill_limit,
    query_directory,
)
from tabalyst.projects._staging import _file_hash
from tabalyst.projects._validation import validate_staging
from tabalyst.projects.models import ProjectManifest
from tabalyst.projects.store import read_project
from tabalyst.scan_reuse import compare_source, load_scan
from tabalyst.scanner import ScanResult


@dataclass(frozen=True)
class PinnedGeneration:
    project: ProjectManifest
    result: ScanResult
    scan_path: Path
    database_path: Path
    # Privileged local SQL; consumers use _queries for exposure-aware values.
    connection: duckdb.DuckDBPyConnection

    @property
    def generation_id(self) -> str:
        return self.project.generation.id

    def freshness(self):
        return compare_source(Path(self.project.source.path), self.result.source)


@contextmanager
def open_generation(location, project_id: str, *, budget: QueryBudget | None = None):
    if not location.project_path(project_id).is_file():
        raise InputError(f"Project {project_id} not found")
    with workspace_reader(location):
        document = read_project(location, project_id)  # exactly once; pin it
        if not isinstance(document, ProjectManifest):
            raise InputError(
                "Legacy revision-1 project is scan-only; explicitly rebuild from source"
            )
        budget = budget or QueryBudget()
        with query_directory(
            location.project_dir(project_id), document.generation.id
        ) as scratch:
            config = budget.config(scratch / "spill")
            result, scan_path, database_path = verify_generation(
                location, document, database_config=config
            )
            try:
                connection = duckdb.connect(
                    str(database_path), read_only=True, config=config
                )
            except (OSError, ValueError, duckdb.Error) as exc:
                raise InputError(
                    f"Cannot open committed project {project_id}: {exc}"
                ) from exc
            try:
                apply_spill_limit(connection, config["max_temp_directory_size"])
                yield PinnedGeneration(
                    document, result, scan_path, database_path, connection
                )
            finally:
                connection.close()


def verify_generation(location, document, *, database_config=None):
    """Verify a pinned manifest under an already-held reader/maintenance lock."""
    if database_config is None:
        # Maintenance verifies the selected generation without opening a
        # reader session; it must use the same bounded, private spill policy.
        with query_directory(
            location.project_dir(document.project_id), document.generation.id
        ) as scratch:
            return verify_generation(
                location,
                document,
                database_config=QueryBudget().config(scratch / "spill"),
            )
    generation = document.generation
    project_id = document.project_id
    scan_path = location.scan_path(project_id, generation.id)
    database_path = location.database_path(project_id, generation.id)
    try:
        if (
            _file_hash(scan_path) != generation.scan_sha256
            or _file_hash(database_path) != generation.database_sha256
        ):
            raise DatabaseValidationError("Committed generation artifact hash mismatch")
        result = load_scan(scan_path)
        validate_staging(
            database_path,
            scan_path,
            result,
            project_id=project_id,
            workspace_id=document.workspace_id,
            generation_id=generation.id,
            database_config=database_config,
        )
    except (OSError, ValueError, duckdb.Error) as exc:
        raise InputError(f"Cannot open committed project {project_id}: {exc}") from exc
    return result, scan_path, database_path
