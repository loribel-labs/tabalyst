# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reusable planning and batch execution for CSV samples."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tabalyst.batch import plan_outputs, validate_outputs
from tabalyst.config import resolve_config
from tabalyst.errors import InputError, TabalystError
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


def build_sample_plan(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
) -> SamplePlan:
    """Resolve input patterns and reject unsafe output plans before sampling."""
    jobs = tuple(
        SampleJob(source=source, output=target)
        for source, target in plan_outputs(
            input_specs,
            output=output,
            output_dir=output_dir,
            output_name=lambda source: default_sample_output(source).name,
        )
    )
    for job in jobs:
        if job.output.suffix.lower() != ".csv":
            raise InputError("--output must be a complete filename ending in .csv")
    validate_outputs(
        ((job.source, job.output) for job in jobs),
        sources=(job.source for job in jobs),
        force=force,
        label="Sample",
    )
    return SamplePlan(jobs=jobs)


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
