"""Reusable planning and batch execution for Tabalyst Report."""

import glob
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tabalyst.config import resolve_config
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError
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


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def resolve_input_specs(input_specs: Sequence[str | Path]) -> list[Path]:
    """Resolve explicit files and shell-independent, non-recursive glob patterns."""
    if not input_specs:
        raise ConfigurationError("At least one input file is required.")

    sources: list[Path] = []
    known: set[str] = set()
    for value in input_specs:
        text = os.fspath(value)
        if "**" in text:
            raise ConfigurationError(
                f"Recursive input patterns are not supported yet: {text}"
            )
        if glob.has_magic(text):
            matches = sorted(
                (Path(match) for match in glob.glob(text) if Path(match).is_file()),
                key=_path_key,
            )
            if not matches:
                raise InputError(f'Input pattern matched no files: "{text}"')
        else:
            path = Path(text)
            if not path.exists():
                raise InputError(f"Input file does not exist: {path}")
            if not path.is_file():
                raise InputError(f"Input path is not a file: {path}")
            matches = [path]

        for path in matches:
            key = _path_key(path)
            if key not in known:
                sources.append(path)
                known.add(key)
    return sources


def build_report_plan(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
) -> ReportPlan:
    """Resolve all report paths and reject the whole batch on unsafe plans."""
    if output is not None and output_dir is not None:
        raise ConfigurationError("--output and --output-dir cannot be used together.")

    sources = resolve_input_specs(input_specs)
    if output is not None and len(sources) != 1:
        raise ConfigurationError("--output can only be used with one input file.")

    destination = Path(output_dir) if output_dir is not None else None
    if destination is not None and destination.exists() and not destination.is_dir():
        raise ReportError(f"Output directory path is a file: {destination}")

    jobs = tuple(
        ReportJob(
            source=source,
            output=(
                Path(output)
                if output is not None
                else destination / f"{source.stem}.html"
                if destination is not None
                else source.with_suffix(".html")
            ),
        )
        for source in sources
    )
    _validate_report_plan(jobs, force=force)
    return ReportPlan(jobs=jobs)


def _validate_report_plan(jobs: tuple[ReportJob, ...], *, force: bool) -> None:
    input_owners = {_path_key(job.source): job.source for job in jobs}
    output_owners: dict[str, ReportJob] = {}
    existing: list[Path] = []

    for job in jobs:
        if job.output.suffix.lower() != ".html":
            raise InputError("--output must be a complete filename ending in .html")
        if job.output.exists() and job.output.is_dir():
            raise InputError(f"Report path is a directory: {job.output}")

        execution_key = _path_key(job.execution_output)
        for artifact in (job.output, job.profile_output):
            key = _path_key(artifact)
            if key == execution_key:
                raise ReportError(
                    f"Report artifact conflicts with execution history: {artifact}"
                )
            if key in input_owners:
                raise InputError(f"Report would overwrite an input file: {artifact}")
            previous = output_owners.get(key)
            if previous is not None:
                raise ReportError(
                    "Output name collision: "
                    f"{previous.source} and {job.source} both map to {artifact}."
                )
            output_owners[key] = job
            if not force and artifact.exists():
                existing.append(artifact)

    if existing:
        lines = "\n".join(f"  {path}" for path in existing)
        raise ReportError(
            "Report output already exists. Use --force to replace it:\n" + lines
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
