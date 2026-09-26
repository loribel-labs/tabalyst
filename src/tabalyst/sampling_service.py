"""Reusable planning and batch execution for CSV samples."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tabalyst.config import resolve_config
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError
from tabalyst.report_service import resolve_input_specs
from tabalyst.sampling import (
    SampleMethod,
    SampleResult,
    default_sample_output,
    sample_csv,
    validate_sample_options,
)
from tabalyst.service import ConfigPath, _config_paths


@dataclass(frozen=True)
class SampleJob:
    source: Path
    output: Path


@dataclass(frozen=True)
class SamplePlan:
    jobs: tuple[SampleJob, ...]


@dataclass(frozen=True)
class SampleSuccess:
    job: SampleJob
    result: SampleResult


@dataclass(frozen=True)
class SampleFailure:
    job: SampleJob
    error: TabalystError


@dataclass(frozen=True)
class BatchSampleResult:
    plan: SamplePlan
    successes: tuple[SampleSuccess, ...]
    failures: tuple[SampleFailure, ...]

    @property
    def succeeded(self) -> bool:
        return not self.failures


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def build_sample_plan(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
) -> SamplePlan:
    """Resolve input patterns and reject unsafe output plans before sampling."""

    if output is not None and output_dir is not None:
        raise ConfigurationError("--output and --output-dir cannot be used together.")
    sources = resolve_input_specs(input_specs)
    if output is not None and len(sources) != 1:
        raise ConfigurationError("--output can only be used with one input file.")

    destination = Path(output_dir) if output_dir is not None else None
    if destination is not None and destination.exists() and not destination.is_dir():
        raise ReportError(f"Output directory path is a file: {destination}")
    jobs = tuple(
        SampleJob(
            source=source,
            output=(
                Path(output)
                if output is not None
                else destination / f"{source.stem}.sample.csv"
                if destination is not None
                else default_sample_output(source)
            ),
        )
        for source in sources
    )
    _validate_sample_plan(jobs, force=force)
    return SamplePlan(jobs=jobs)


def _validate_sample_plan(jobs: tuple[SampleJob, ...], *, force: bool) -> None:
    input_paths = {_path_key(job.source) for job in jobs}
    output_owners: dict[str, SampleJob] = {}
    existing: list[Path] = []
    for job in jobs:
        if job.output.suffix.lower() != ".csv":
            raise InputError("--output must be a complete filename ending in .csv")
        if job.output.exists() and job.output.is_dir():
            raise InputError(f"Sample path is a directory: {job.output}")
        key = _path_key(job.output)
        if key in input_paths:
            raise InputError(f"Sample would overwrite an input file: {job.output}")
        previous = output_owners.get(key)
        if previous is not None:
            raise ReportError(
                "Output name collision: "
                f"{previous.source} and {job.source} both map to {job.output}."
            )
        output_owners[key] = job
        if not force and job.output.exists():
            existing.append(job.output)
    if existing:
        lines = "\n".join(f"  {path}" for path in existing)
        raise ReportError(
            "Sample output already exists. Use --force to replace it:\n" + lines
        )


def generate_samples(
    input_specs: Sequence[str | Path],
    *,
    method: SampleMethod | str,
    rows: int | None = None,
    percent: float | None = None,
    field: str | None = None,
    seed: int | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
) -> BatchSampleResult:
    """Plan and execute one or more CSV samples."""

    selected_method = validate_sample_options(
        method, rows=rows, percent=percent, field=field
    )
    config = resolve_config(
        _config_paths(config_path), separator=delimiter, encoding=encoding
    )
    plan = build_sample_plan(
        input_specs, output=output, output_dir=output_dir, force=force
    )
    successes: list[SampleSuccess] = []
    failures: list[SampleFailure] = []
    for job in plan.jobs:
        try:
            result = sample_csv(
                job.source,
                method=selected_method,
                rows=rows,
                percent=percent,
                field=field,
                seed=seed,
                output=job.output,
                delimiter=config.csv.delimiter,
                encoding=config.csv.encoding,
                force=force,
            )
        except TabalystError as exc:
            failures.append(SampleFailure(job=job, error=exc))
        else:
            successes.append(SampleSuccess(job=job, result=result))
    return BatchSampleResult(
        plan=plan,
        successes=tuple(successes),
        failures=tuple(failures),
    )
