# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reusable planning and batch execution for Tabalyst Scan (design 16.3)."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from tabalyst.batch import (
    plan_outputs,
    resolve_input_specs,
    validate_outputs,
    write_text_atomic,
)
from tabalyst.config import load_config_layers, settings_from_layer
from tabalyst.errors import InputError, ReportError, TabalystError
from tabalyst.inspector.resolution import check_result, resolve_interpretation
from tabalyst.json_text import dump_json
from tabalyst.option_notices import ignored_options
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.scan_page import scan_page_path, write_scan_page
from tabalyst.scanner import ScanResult, scan
from tabalyst.scanner.config import json_collection_paths, scan_config_from_layer
from tabalyst.scanner.identity import source_format_of
from tabalyst.service import ConfigPath, _config_paths

SCAN_SUFFIX = ".scan.json"


@dataclass(frozen=True)
class ScanJob:
    source: Path
    output: Path | None
    # The web page of the scan, for an explicit ``tabalyst scan`` only (design 16.8).
    page: Path | None = None


@dataclass(frozen=True)
class ScanPlan:
    jobs: tuple[ScanJob, ...]
    # Options that a source cannot use, as (source, sentence).
    warnings: tuple[tuple[Path, str], ...] = ()


@dataclass(frozen=True)
class ScanSuccess:
    job: ScanJob
    result: ScanResult
    warnings: tuple[str, ...] = ()
    # The shared scan document was current and not scanned again.
    reused: bool = False


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
    html: bool = False,
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
    if html:
        jobs = tuple(
            replace(job, page=scan_page_path(job.source, job.output)) for job in jobs
        )
        # A scan in the shared storage is replaced at every run, and so is its page,
        # which is derived from it; the page of a standalone scan follows the
        # document and needs --force like it.
        for stored, replace_it in ((True, True), (False, force)):
            validate_outputs(
                (
                    (job.source, job.page)
                    for job in jobs
                    if job.page is not None and (job.output is None) == stored
                ),
                sources=[*(job.source for job in jobs), *config_paths],
                force=replace_it,
                label="Scan page",
            )
    return ScanPlan(jobs=jobs)


def scan_document(result: ScanResult, *, indent: bool = False) -> str:
    """The JSON text of a scan result, as written by ``tabalyst scan``: compact,
    or indented with ``indent`` (``output.json_indent``)."""
    return dump_json(result.model_dump(mode="json", by_alias=True), indent=indent)


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
    counters: bool = False,
    project_storage: bool = False,
    refresh: bool = True,
    html: bool = False,
) -> BatchScanResult:
    """Scan one or more CSV or JSON files and write one scan document each.

    Configuration layers, from lowest to highest priority: built-in defaults,
    the ``scan`` section of each ``config_path`` file in order, then
    ``delimiter``, ``encoding`` and ``collections``. A JSON, JSONL or NDJSON
    source also takes its Inspect configuration, resolved for that source
    (design inspect 11): a source whose collection cannot be decided fails
    alone. The whole batch is rejected before any scan when an output is
    unsafe; afterwards, a failed source does not stop the others. ``workers``
    and ``counters`` are passed to ``tabalyst.scan()``. With ``project_storage``
    the scan goes to the shared storage and is scanned again unless
    ``refresh`` is false and the stored document is current. With ``html`` the web
    page of each scan is written beside its document (beside the source when the
    scan is in the shared storage): a command that scans by itself does not ask
    for it. A page that cannot be written is a warning, not a failure.
    """
    config_paths = _config_paths(config_path)
    top_level, scan_layer = load_config_layers(config_paths)
    indent = settings_from_layer(top_level).output.json_indent
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
        html=html,
    )
    plan = replace(
        plan,
        warnings=tuple(
            (job.source, notice)
            for job in plan.jobs
            for notice in ignored_options(
                job.source,
                delimiter=delimiter,
                encoding=encoding,
                collections=collections,
            )
        ),
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
            reused = False
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
                    counters=counters,
                    json_indent=indent,
                    refresh=refresh,
                    check=check,
                )
                result = shared.result
                reused = shared.reused
                completed_job = ScanJob(job.source, shared.path)
                warnings += shared.warnings
            else:
                result = scan(
                    job.source,
                    config=job_config,
                    on_progress=forward,
                    workers=workers,
                    counters=counters,
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
                    write_text_atomic(job.output, scan_document(result, indent=indent))
                except OSError as exc:
                    raise ReportError(
                        f"Cannot write scan file {job.output}: {exc}"
                    ) from exc
                completed_job = job
            completed_job = replace(completed_job, page=job.page)
            if job.page is not None:
                emit_progress(
                    on_progress, job.source, ProgressPhase.RENDERING, index=index, total=total
                )
                try:
                    write_scan_page(result, job.page, config_paths)
                except TabalystError as exc:
                    warnings += (f"the page of the scan was not written: {exc}",)
                    completed_job = replace(completed_job, page=None)
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
            successes.append(
                ScanSuccess(
                    job=completed_job,
                    result=result,
                    warnings=warnings,
                    reused=reused,
                )
            )
            emit_progress(
                on_progress,
                job.source,
                ProgressPhase.COMPLETE,
                index=index,
                total=total,
                duration_seconds=result.run.duration_seconds,
            )

    return BatchScanResult(
        plan=plan,
        successes=tuple(successes),
        failures=tuple(failures),
    )
