"""Reusable planning and batch execution for Tabalyst Scan (design 16.3)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from tabalyst.batch import (
    plan_outputs,
    resolve_input_specs,
    validate_outputs,
    write_text_atomic,
)
from tabalyst.config import load_config_layers
from tabalyst.errors import InputError, ReportError, TabalystError
from tabalyst.inspector.resolution import check_result, resolve_interpretation
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.scanner import ScanResult, scan
from tabalyst.scanner.config import json_collection_paths, scan_config_from_layer
from tabalyst.scanner.identity import source_format_of
from tabalyst.service import ConfigPath, _config_paths

SCAN_SUFFIX = ".scan.json"


@dataclass(frozen=True)
class ScanJob:
    source: Path
    output: Path | None


@dataclass(frozen=True)
class ScanPlan:
    jobs: tuple[ScanJob, ...]


@dataclass(frozen=True)
class ScanSuccess:
    job: ScanJob
    result: ScanResult
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScanFailure:
    job: ScanJob
    error: TabalystError


@dataclass(frozen=True)
class BatchScanResult:
    plan: ScanPlan
    successes: tuple[ScanSuccess, ...]
    failures: tuple[ScanFailure, ...]

    @property
    def succeeded(self) -> bool:
        return not self.failures


def default_scan_output(source: Path) -> Path:
    """Return the conventional scan filename beside a source file."""
    return source.with_name(f"{source.stem}{SCAN_SUFFIX}")


def build_scan_plan(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
    config_paths: Sequence[Path] = (),
    project_storage: bool = False,
) -> ScanPlan:
    """Resolve input patterns and reject unsafe output plans before scanning."""
    if project_storage and output is None and output_dir is None:
        # The scan goes to the shared storage, whatever the format.
        jobs = tuple(ScanJob(source, None) for source in resolve_input_specs(input_specs))
    else:
        jobs = tuple(
            ScanJob(source=source, output=target)
            for source, target in plan_outputs(
                input_specs,
                output=output,
                output_dir=output_dir,
                output_name=lambda source: default_scan_output(source).name,
            )
        )
    for job in jobs:
        if job.output is not None and job.output.suffix.lower() != ".json":
            raise InputError("--output must be a complete filename ending in .json")
    validate_outputs(
        ((job.source, job.output) for job in jobs if job.output is not None),
        sources=[*(job.source for job in jobs), *config_paths],
        force=force,
        label="Scan",
    )
    return ScanPlan(jobs=jobs)


def scan_document(result: ScanResult) -> str:
    """The JSON text of a scan result, as written by ``tabalyst scan``."""
    document = result.model_dump(mode="json", by_alias=True)
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def generate_scans(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    config_path: ConfigPath | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
    workers: int | None = None,
    project_storage: bool = False,
) -> BatchScanResult:
    """Scan one or more CSV or JSON files and write one scan document each.

    Configuration layers, from lowest to highest priority: built-in defaults,
    the ``scan`` section of each ``config_path`` file in order, then
    ``delimiter``, ``encoding`` and ``collections``. A JSON, JSONL or NDJSON
    source also takes its Inspect configuration, resolved for that source
    (design inspect 11): a source whose collection cannot be decided fails
    alone. The whole batch is rejected before any scan when an output is
    unsafe; afterwards, a failed source does not stop the others. ``workers``
    is passed to ``tabalyst.scan()``.
    """
    config_paths = _config_paths(config_path)
    _, scan_layer = load_config_layers(config_paths)
    config = scan_config_from_layer(
        scan_layer,
        delimiter=delimiter,
        encoding=encoding,
        collections=json_collection_paths(collections),
    )
    plan = build_scan_plan(
        input_specs,
        output=output,
        output_dir=output_dir,
        force=force,
        config_paths=config_paths,
        project_storage=project_storage,
    )
    successes: list[ScanSuccess] = []
    failures: list[ScanFailure] = []
    total = len(plan.jobs)

    for index, job in enumerate(plan.jobs, start=1):

        def forward(event: ProgressEvent, *, job_index: int = index) -> None:
            # Completion is reported once the document is written.
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
            warnings: tuple[str, ...] = ()
            job_config = config
            check = None
            if source_format_of(job.source) != "csv":
                interpretation = resolve_interpretation(
                    job.source,
                    scan_layer=scan_layer,
                    collections=collections,
                    delimiter=delimiter,
                    encoding=encoding,
                )
                job_config = interpretation.config
                warnings = interpretation.notices
                check = partial(check_result, interpretation)

            if job.output is None:
                from tabalyst.shared_scan_service import current_scan

                shared = current_scan(
                    job.source,
                    job_config,
                    on_progress=forward,
                    workers=workers,
                    refresh=True,
                    check=check,
                )
                result = shared.result
                completed_job = ScanJob(job.source, shared.path)
                warnings += shared.warnings
            else:
                result = scan(
                    job.source, config=job_config, on_progress=forward, workers=workers
                )
                if check is not None:
                    warnings += check(result)
                emit_progress(
                    on_progress,
                    job.source,
                    ProgressPhase.WRITING,
                    index=index,
                    total=total,
                )
                try:
                    write_text_atomic(job.output, scan_document(result))
                except OSError as exc:
                    raise ReportError(
                        f"Cannot write scan file {job.output}: {exc}"
                    ) from exc
                completed_job = job
        except TabalystError as exc:
            failures.append(ScanFailure(job=job, error=exc))
            emit_progress(
                on_progress,
                job.source,
                ProgressPhase.FAILED,
                index=index,
                total=total,
                detail=str(exc),
            )
        else:
            successes.append(ScanSuccess(job=completed_job, result=result, warnings=warnings))
            emit_progress(
                on_progress, job.source, ProgressPhase.COMPLETE, index=index, total=total
            )

    return BatchScanResult(
        plan=plan,
        successes=tuple(successes),
        failures=tuple(failures),
    )
