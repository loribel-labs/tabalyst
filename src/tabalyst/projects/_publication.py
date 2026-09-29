"""Atomic immutable-generation publication, internal until the product API lot."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tabalyst.errors import InputError, ReportError
from tabalyst.progress import ProgressPhase, emit_progress
from tabalyst.projects import _sync
from tabalyst.projects._locks import workspace_writer
from tabalyst.projects._staging import build_staging
from tabalyst.projects.identity import new_project_id
from tabalyst.projects.index import _find_project, register_project
from tabalyst.projects.models import (
    GenerationBinding,
    ProjectManifest,
    ProjectSource,
    utc_now,
)
from tabalyst.projects.store import project_document_text, read_project
from tabalyst.scanner import ScanResult


class UnknownProjectOutcomeError(ReportError):
    """The manifest cannot establish whether a replacement committed."""


@dataclass(frozen=True)
class PublishedGeneration:
    project: ProjectManifest
    result: ScanResult
    scan_path: Path
    database_path: Path
    reopened: bool
    warnings: tuple[str, ...]
    directory_sync_supported: bool


def rename_generation(stage: Path, target: Path) -> None:
    # Cooperating writers are serialized. Never overwrite an existing ULID.
    if target.exists():
        raise FileExistsError(f"Generation already exists: {target}")
    stage.rename(target)


def _commit_manifest(location, document, previous) -> tuple[str, ...]:
    try:
        _sync.replace_manifest(
            location.project_path(document.project_id), project_document_text(document)
        )
    except Exception as exc:
        try:
            current = read_project(location, document.project_id)
        except InputError as read_error:
            if (
                previous is None
                and not location.project_path(document.project_id).exists()
            ):
                raise exc
            raise UnknownProjectOutcomeError(
                f"Project {document.project_id}: outcome unknown, reopen for recovery; "
                "the manifest cannot be read. Generation artifacts are preserved."
            ) from read_error
        if (
            isinstance(current, ProjectManifest)
            and current.generation.id == document.generation.id
        ):
            return (f"Generation committed; post-commit synchronization failed: {exc}",)
        if current == previous:
            raise
        raise UnknownProjectOutcomeError(
            f"Project {document.project_id}: outcome unknown, reopen for recovery; "
            "the manifest differs from both expected states. Artifacts are preserved."
        ) from exc
    return ()


def publish_scan(
    source,
    location,
    config,
    *,
    workers=None,
    now: datetime | None = None,
    on_progress=None,
    memory_limit="256MiB",
    spill_limit="1GiB",
    value_limit=10000,
) -> PublishedGeneration:
    if type(value_limit) is not int or not 1 <= value_limit <= 10000:
        raise ValueError("Stored distinct value limit must be between 1 and 10000")
    with workspace_writer(location):
        previous = _find_project(location, source, validate=False)
        moment = now or utc_now()
        project_id = previous.project_id if previous is not None else new_project_id()
        generation_id = new_project_id()
        directory = location.project_dir(project_id)
        directory.mkdir(mode=0o700, parents=True, exist_ok=previous is not None)
        stages = directory / ".staging"
        generations = directory / "generations"
        stages.mkdir(mode=0o700, exist_ok=True)
        generations.mkdir(mode=0o700, exist_ok=True)
        stage = location.staging_dir(project_id, generation_id)
        target = location.generation_dir(project_id, generation_id)
        staged = build_staging(
            source,
            stage,
            project_id=project_id,
            generation_id=generation_id,
            workspace_id=location.workspace_id,
            config=config,
            workers=workers,
            on_progress=on_progress,
            memory_limit=memory_limit,
            spill_limit=spill_limit,
            value_limit=value_limit,
        )
        emit_progress(on_progress, source, ProgressPhase.WRITING)
        _sync.sync_file(staged.scan_path)
        _sync.sync_file(staged.database_path)
        directory_sync = _sync.sync_directory(stage)
        _sync.sync_directory(stages)
        rename_generation(stage, target)
        _sync.sync_directory(generations)
        _sync.sync_directory(stages)
        _sync.sync_directory(directory)
        _sync.sync_directory(location.projects_dir)
        _sync.sync_directory(location.workspace_dir)
        document = ProjectManifest(
            project_id=project_id,
            workspace_id=location.workspace_id,
            created_at=previous.created_at if previous is not None else moment,
            last_scan_at=now or utc_now(),
            source=previous.source
            if previous is not None
            else ProjectSource(path=source.resolve().as_posix(), name=source.name),
            generation=GenerationBinding(
                id=generation_id,
                scan_sha256=staged.scan_sha256,
                database_sha256=staged.database_sha256,
            ),
        )
        warnings = list(_commit_manifest(location, document, previous))
        try:
            register_project(location, document)
        except Exception as exc:  # noqa: BLE001 - every index failure is post-commit
            warnings.append(f"Generation committed; project index needs repair: {exc}")
        return PublishedGeneration(
            document,
            staged.result,
            location.scan_path(project_id, generation_id),
            location.database_path(project_id, generation_id),
            previous is not None,
            tuple(warnings),
            directory_sync,
        )
