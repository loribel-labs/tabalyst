"""Reusable planning and batch execution for Tabalyst Report."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tabalyst.batch import path_key, plan_outputs, validate_outputs
from tabalyst.config import load_config_layers, settings_from_layer
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError
from tabalyst.execution_log import EXECUTION_LOG_NAME
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.report_config import resolve_report_config
from tabalyst.scan_reuse import read_scan_document, source_name
from tabalyst.service import (
    ConfigPath,
    _analyze_resolved,
    _config_paths,
    _report_scan_resolved,
)


@dataclass(frozen=True)
class ReportJob:
    # The source, or the scan document when reusing a scan.
    source: Path
    output: Path
    # The source of a scan document, looked for beside it.
    scanned: Path | None = None
    # Why a scan document cannot be reported, found while planning: the job
    # fails without stopping the batch.
    error: TabalystError | None = None

    @property
    def profile_output(self) -> Path:
        return self.output.with_suffix(".json")

    @property
    def execution_output(self) -> Path:
        return self.output.parent / EXECUTION_LOG_NAME


@dataclass(frozen=True)
class ReportPlan:
    jobs: tuple[ReportJob, ...]


@dataclass(frozen=True)
class ReportSuccess:
    job: ReportJob
    result: dict[str, Any]
    # Reports of scan documents: whether the source was found beside the
    # document and checked for staleness.
    source_checked: bool | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportFailure:
    job: ReportJob
    error: TabalystError


@dataclass(frozen=True)
class BatchReportResult:
    plan: ReportPlan
    successes: tuple[ReportSuccess, ...]
    failures: tuple[ReportFailure, ...]

    @property
    def succeeded(self) -> bool:
        return not self.failures


def report_name(source: Path) -> str:
    """``data.html`` for ``data.csv``; ``data.report.html`` for ``data.json``,
    whose profile ``data.report.json`` must not replace the source."""
    if source.suffix.lower() == ".json":
        return f"{source.stem}.report.html"
    return f"{source.stem}.html"


def build_report_plan(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
    from_scan: bool = False,
) -> ReportPlan:
    """Resolve all report paths and reject the whole batch on unsafe plans.

    With ``from_scan``, the inputs are scan documents: reports are named after
    the source each one records, and must not replace that source either. A
    document that cannot be read is named after its own file and fails alone.
    """
    names: dict[str, str | TabalystError] = {}

    def recorded(scan_path: Path) -> str | TabalystError:
        key = path_key(scan_path)
        if key not in names:
            try:
                names[key] = source_name(read_scan_document(scan_path))
            except TabalystError as exc:
                names[key] = exc
        return names[key]

    def scan_report_name(scan_path: Path) -> str:
        name = recorded(scan_path)
        if isinstance(name, str):
            return report_name(Path(name))
        stem = scan_path.name.removesuffix(".json").removesuffix(".scan")
        return f"{stem}.html"

    def scan_job(source: Path, target: Path) -> ReportJob:
        name = recorded(source)
        if isinstance(name, str):
            return ReportJob(source=source, output=target, scanned=source.parent / name)
        return ReportJob(source=source, output=target, error=name)

    jobs = tuple(
        scan_job(source, target)
        if from_scan
        else ReportJob(source=source, output=target)
        for source, target in plan_outputs(
            input_specs,
            output=output,
            output_dir=output_dir,
            output_name=scan_report_name if from_scan else report_name,
        )
    )
    _validate_report_plan(jobs, force=force)
    return ReportPlan(jobs=jobs)


def _validate_report_plan(jobs: tuple[ReportJob, ...], *, force: bool) -> None:
    for job in jobs:
        if job.output.suffix.lower() != ".html":
            raise InputError("--output must be a complete filename ending in .html")
        execution_key = path_key(job.execution_output)
        for artifact in (job.output, job.profile_output):
            if path_key(artifact) == execution_key:
                raise ReportError(
                    f"Report artifact conflicts with execution history: {artifact}"
                )
    validate_outputs(
        (
            (job.source, artifact)
            for job in jobs
            for artifact in (job.output, job.profile_output)
        ),
        sources=(
            path
            for job in jobs
            for path in (job.source, job.scanned)
            if path is not None
        ),
        force=force,
        label="Report",
    )


def generate_reports(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    separator: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
    details: bool = False,
    on_progress: ProgressCallback | None = None,
    from_scan: bool = False,
    workers: int | None = None,
) -> BatchReportResult:
    """Plan and execute one or more reports without depending on the CLI.

    With ``from_scan``, the inputs are scan documents written by
    ``tabalyst scan``: each report is built from its document without reading
    the source again, after the staleness checks of ``tabalyst.scan_reuse``.
    Otherwise ``workers`` is passed to ``tabalyst.scan()``.
    Set ``details=True`` to write a standalone HTML page for each column.
    """
    if from_scan and (separator is not None or encoding is not None):
        raise ConfigurationError(
            "--delimiter and --encoding cannot be used with --scan: the scan "
            "document records how its source was read."
        )
    if from_scan and workers is not None:
        raise ConfigurationError(
            "--workers cannot be used with --scan: the report reads the scan "
            "document, not its source."
        )
    plan = build_report_plan(
        input_specs,
        output=output,
        output_dir=output_dir,
        force=force,
        from_scan=from_scan,
    )
    config_paths = _config_paths(config_path)
    if from_scan:
        top_level, scan_layer = load_config_layers(config_paths)
        settings = settings_from_layer(top_level)
    else:
        config = resolve_report_config(
            config_paths,
            separator=separator,
            encoding=encoding,
        )
        _, report_scan_layer = load_config_layers(config_paths)
    successes: list[ReportSuccess] = []
    failures: list[ReportFailure] = []
    total = len(plan.jobs)

    for index, job in enumerate(plan.jobs, start=1):
        def forward(event: ProgressEvent, *, job_index: int = index) -> None:
            if on_progress is not None:
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

        checked = None
        warnings: tuple[str, ...] = ()
        try:
            if job.error is not None:
                raise job.error
            if from_scan:
                result, checked = _report_scan_resolved(
                    job.source,
                    job.output,
                    settings,
                    scan_layer,
                    config_paths,
                    force=force,
                    details=details,
                    on_progress=forward,
                )
            else:
                result, warnings = _analyze_resolved(
                    job.source,
                    job.output,
                    config,
                    config_paths,
                    force=force,
                    details=details,
                    on_progress=forward,
                    workers=workers,
                    scan_layer=report_scan_layer,
                    separator=separator,
                    encoding=encoding,
                )
        except TabalystError as exc:
            failures.append(ReportFailure(job=job, error=exc))
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
                ReportSuccess(
                    job=job,
                    result=result,
                    source_checked=checked,
                    warnings=warnings,
                )
            )

    return BatchReportResult(
        plan=plan,
        successes=tuple(successes),
        failures=tuple(failures),
    )
