"""Reusable planning and batch execution for Tabalyst Inspect (design inspect 13)."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tabalyst.batch import resolve_input_specs, validate_outputs
from tabalyst.config import load_config_layers
from tabalyst.errors import ConfigurationError, TabalystError
from tabalyst.inspector.json_inspect import inspect_source
from tabalyst.inspector.models import InspectDocument
from tabalyst.inspector.persistence import (
    inspect_path,
    read_visible_inspect,
    save_inspection,
)
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.scanner.config import scan_config_from_layer
from tabalyst.service import ConfigPath, _config_paths

INSPECTABLE_SUFFIXES = (".json", ".jsonl", ".ndjson")


@dataclass(frozen=True)
class InspectJob:
    source: Path
    # The visible Inspect file of the source.
    output: Path


@dataclass(frozen=True)
class InspectPlan:
    jobs: tuple[InspectJob, ...]


@dataclass(frozen=True)
class InspectResult:
    """One inspected source: the visible file written and the document in it.

    A kept ``config`` that omits keys shows their defaults in ``document``; the
    file holds it as the user wrote it."""

    job: InspectJob
    document: InspectDocument

    @property
    def source(self) -> Path:
        return self.job.source

    @property
    def path(self) -> Path:
        return self.job.output


@dataclass(frozen=True)
class InspectFailure:
    job: InspectJob
    error: TabalystError


@dataclass(frozen=True)
class BatchInspectResult:
    plan: InspectPlan
    successes: tuple[InspectResult, ...]
    failures: tuple[InspectFailure, ...]

    @property
    def succeeded(self) -> bool:
        return not self.failures


def build_inspect_plan(
    input_specs: Sequence[str | Path],
    *,
    config_paths: Sequence[Path] = (),
) -> InspectPlan:
    """Resolve input patterns and reject unsafe plans before reading anything.

    A source that Inspect does not know rejects the whole batch: nothing is
    silently skipped. An existing Inspect file is not an obstacle, since
    inspecting again is the normal case.
    """
    sources = resolve_input_specs(input_specs)
    for source in sources:
        if source.suffix.lower() not in INSPECTABLE_SUFFIXES:
            raise ConfigurationError(
                "Tabalyst Inspect reads .json, .jsonl and .ndjson files; "
                f"there is no Inspect for {source.name}."
            )
    jobs = tuple(InspectJob(source, inspect_path(source)) for source in sources)
    validate_outputs(
        ((job.source, job.output) for job in jobs),
        sources=[*sources, *config_paths],
        force=True,
        label="Inspect",
    )
    return InspectPlan(jobs=jobs)


def generate_inspections(
    input_specs: Sequence[str | Path],
    *,
    config_path: ConfigPath | None = None,
    reset_config: bool = False,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
) -> BatchInspectResult:
    """Inspect one or more JSON, JSONL or NDJSON files and write one visible
    Inspect file beside each (design inspect 12.2).

    The ``scan`` section of each ``config_path`` file seeds the ``config`` of a
    new file (design 5.3). An existing file keeps its ``config`` unless
    ``reset_config``; one that is not valid is refused unless ``force``. The
    whole batch is rejected before any reading when the plan is unsafe;
    afterwards, a failed source does not stop the others. Only the visible
    files are written, never the storage cache.
    """
    config_paths = _config_paths(config_path)
    _, scan_layer = load_config_layers(config_paths)
    seed = scan_config_from_layer(scan_layer)
    plan = build_inspect_plan(input_specs, config_paths=config_paths)
    successes: list[InspectResult] = []
    failures: list[InspectFailure] = []
    total = len(plan.jobs)

    for index, job in enumerate(plan.jobs, start=1):

        def forward(event: ProgressEvent, *, job_index: int = index) -> None:
            # Completion is reported once the file is written.
            if on_progress is not None and event.phase != ProgressPhase.COMPLETE:
                on_progress(
                    ProgressEvent(
                        source=event.source,
                        phase=event.phase,
                        index=job_index,
                        total=total,
                        detail=event.detail,
                        bytes_read=event.bytes_read,
                        bytes_total=event.bytes_total,
                    )
                )

        try:
            if not force and (job.output.exists() or job.output.is_symlink()):
                # An Inspect file that cannot be kept stops the job before the
                # source is read, not after.
                read_visible_inspect(job.output)
            document = inspect_source(job.source, scan_config=seed, on_progress=forward)
            emit_progress(
                on_progress,
                job.source,
                ProgressPhase.WRITING,
                index=index,
                total=total,
            )
            _, written = save_inspection(
                job.source, document, reset_config=reset_config, force=force
            )
        except TabalystError as exc:
            failures.append(InspectFailure(job=job, error=exc))
            emit_progress(
                on_progress,
                job.source,
                ProgressPhase.FAILED,
                index=index,
                total=total,
                detail=str(exc),
            )
        else:
            successes.append(InspectResult(job=job, document=written))
            emit_progress(
                on_progress, job.source, ProgressPhase.COMPLETE, index=index, total=total
            )

    return BatchInspectResult(
        plan=plan, successes=tuple(successes), failures=tuple(failures)
    )


def inspect(
    source: str | os.PathLike[str],
    *,
    config_path: ConfigPath | None = None,
    reset_config: bool = False,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
) -> InspectResult:
    """Inspect one JSON, JSONL or NDJSON file, as ``tabalyst inspect`` does.

    Writes the visible Inspect file beside the source and returns it with the
    document it holds. Raises the error of the inspection, derived from
    ``tabalyst.TabalystError``, where ``generate_inspections`` reports it.
    """
    batch = generate_inspections(
        [source],
        config_path=config_path,
        reset_config=reset_config,
        force=force,
        on_progress=on_progress,
    )
    if batch.failures:
        raise batch.failures[0].error
    return batch.successes[0]
