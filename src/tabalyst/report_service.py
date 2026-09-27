"""Reusable planning and batch execution for Tabalyst Report."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tabalyst.batch import path_key, plan_outputs, validate_outputs
from tabalyst.config import resolve_config
from tabalyst.errors import InputError, ReportError, TabalystError
from tabalyst.execution_log import EXECUTION_LOG_NAME
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.service import ConfigPath, _analyze_resolved, _config_paths


@dataclass(frozen=True)
class ReportJob:
    source: Path
    output: Path

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


def build_report_plan(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
) -> ReportPlan:
    """Resolve all report paths and reject the whole batch on unsafe plans."""
    jobs = tuple(
        ReportJob(source=source, output=target)
        for source, target in plan_outputs(
            input_specs,
            output=output,
            output_dir=output_dir,
            output_name=lambda source: f"{source.stem}.html",
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
        sources=(job.source for job in jobs),
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
    on_progress: ProgressCallback | None = None,
) -> BatchReportResult:
    """Plan and execute one or more reports without depending on the CLI."""
    plan = build_report_plan(
        input_specs,
        output=output,
        output_dir=output_dir,
        force=force,
    )
    config_paths = _config_paths(config_path)
    config = resolve_config(
        config_paths,
        separator=separator,
        encoding=encoding,
    )
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
                    )
                )

        try:
            result = _analyze_resolved(
                job.source,
                job.output,
                config,
                config_paths,
                force=force,
                on_progress=forward,
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
            successes.append(ReportSuccess(job=job, result=result))

    return BatchReportResult(
        plan=plan,
        successes=tuple(successes),
        failures=tuple(failures),
    )
