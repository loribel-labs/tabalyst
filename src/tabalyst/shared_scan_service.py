"""The current project scan shared by Scan and Report CSV commands."""

from dataclasses import dataclass
from pathlib import Path

from tabalyst.config import merge_settings
from tabalyst.errors import InputError
from tabalyst.project_scan_service import scan_project
from tabalyst.projects._locks import workspace_reader
from tabalyst.projects._publication import publish_selected_scan
from tabalyst.projects._retention import remove_superseded_generation
from tabalyst.projects._staging import _file_hash
from tabalyst.projects.index import (
    document_key,
    find_project,
    read_index,
    source_key,
)
from tabalyst.projects.location import StorageLocation
from tabalyst.projects.models import ProjectManifest
from tabalyst.projects.store import read_project
from tabalyst.scan_reuse import SourceState, _sha256, compare_source, load_scan
from tabalyst.scanner import ScanConfig, ScanResult
from tabalyst.scanner.config import config_sha256, scan_config_from_layer


@dataclass(frozen=True)
class SharedScan:
    result: ScanResult
    path: Path
    reused: bool
    project_id: str
    warnings: tuple[str, ...] = ()


def _find_project(location: StorageLocation, source: Path):
    index = read_index(location)
    project_id = index.projects.get(source_key(source)) if index else None
    if project_id is not None:
        try:
            project = read_project(location, project_id)
        except InputError:
            pass
        else:
            if document_key(project) == source_key(source):
                return project
    return find_project(location, source)


def current_scan(
    source: Path,
    config: ScanConfig,
    *,
    location: StorageLocation | None = None,
    workers: int | None = None,
    on_progress=None,
    refresh: bool = False,
    scan_layer: dict | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
) -> SharedScan:
    """Reuse a verified current scan, or publish a replacement generation.

    ``refresh`` makes the Scan command run again even when the source is fresh.
    Report only scans when source bytes or effective Scan settings differ.
    """
    source = source.resolve()
    location = location or StorageLocation.local()
    previous = _find_project(location, source)
    effective = config
    if isinstance(previous, ProjectManifest) and not refresh:
        with workspace_reader(location):
            selected = read_project(location, previous.project_id)
            if not isinstance(selected, ProjectManifest):
                raise InputError("Project has no committed scan generation")
            if selected.source.path != source.as_posix():
                raise InputError("Project source binding differs from the requested file")
            scan_path = location.scan_path(selected.project_id, selected.generation.id)
            database_path = location.database_path(
                selected.project_id, selected.generation.id
            )
            try:
                if (
                    _file_hash(scan_path) != selected.generation.scan_sha256
                    or _file_hash(database_path) != selected.generation.database_sha256
                ):
                    raise InputError("Committed project artifact hash mismatch")
            except OSError as exc:
                raise InputError(f"Cannot read committed project artifacts: {exc}") from exc
            result = load_scan(scan_path)
            if config_sha256(result.config) != result.config_sha256:
                raise InputError("Committed scan configuration fingerprint is invalid")
            check = compare_source(source, result.source)
            fingerprint_matches = False
            if check.state is SourceState.FRESH:
                try:
                    fingerprint_matches = _sha256(source) == result.source.sha256
                except OSError as exc:
                    raise InputError(f"Cannot hash source {source}: {exc}") from exc
            if scan_layer is not None:
                recorded = result.config.model_dump(mode="json", by_alias=True)
                effective = scan_config_from_layer(
                    merge_settings(recorded, scan_layer),
                    delimiter=delimiter,
                    encoding=encoding,
                )
            if (
                check.state is SourceState.FRESH
                and fingerprint_matches
                and result.config_sha256 == config_sha256(effective)
            ):
                return SharedScan(
                    result, scan_path, True, previous.project_id
                )
    if isinstance(previous, ProjectManifest):
        published = publish_selected_scan(
            location,
            previous.project_id,
            expected_generation_id=previous.generation.id,
            expected_source=source,
            config=effective,
            on_progress=on_progress,
            workers=workers,
        )
    else:
        published = scan_project(
            source,
            location=location,
            on_progress=on_progress,
            workers=workers,
            config=effective,
        )
    warnings = list(published.warnings)
    if isinstance(previous, ProjectManifest):
        warning = remove_superseded_generation(
            location,
            previous.project_id,
            previous.generation.id,
            published.project.generation.id,
        )
        if warning is not None:
            warnings.append(warning)
    return SharedScan(
        published.result,
        published.scan_path,
        False,
        published.project.project_id,
        tuple(warnings),
    )
