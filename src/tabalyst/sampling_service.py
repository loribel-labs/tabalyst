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
from tabalyst.progress import ProgressCallback
from tabalyst.sampling import (
    DEFAULT_MAX_STRATA,
    SampleMethod,
    SampleResult,
    default_sample_output,
    sample_csv,
    stratification_fields,
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


def _refuse_excessive_stratification(
    sources: Sequence[Path],
    fields: Sequence[str],
    *,
    config_path: ConfigPath | None,
    delimiter: str | None,
    encoding: str | None,
) -> None:
    """Stop a stratified sample whose strata a stored Scan already shows to be
    excessive (D23, STRAT-07), before the source is read for it.

    Only a current stored Scan is used: none is ever made for this. A product of
    cardinalities that is a bound proves a risk, not an explosion, so an explicit
    ``--max-strata`` allows the run (and the runtime cap stays). Raises
    ``InputError`` naming the advice.
    """
    from tabalyst.config import load_config_layers
    from tabalyst.errors import ConfigurationError
    from tabalyst.scanner.config import scan_config_from_layer
    from tabalyst.scanner.planner import Stratify, advise_stratification
    from tabalyst.scanner.planner.reasons import reason_text
    from tabalyst.shared_scan_service import stored_scan

    _, layer = load_config_layers(_config_paths(config_path))
    config = scan_config_from_layer(layer, delimiter=delimiter, encoding=encoding)
    for source in sources:
        scan = stored_scan(source, config)
        if scan is None or len(scan.datasets) != 1:
            continue
        try:
            advice = advise_stratification(scan, Stratify(combinations=(tuple(fields),) if len(fields) > 1 else ()))
        except ConfigurationError:
            continue
        if len(fields) > 1:
            [combination] = advice.combinations
            if combination.risk != "excessive":
                continue
            strata = f"up to {combination.strata_bound:,}{'+' if combination.saturated else ''}"
            codes = combination.reasons + combination.suggestions
        else:
            column = next((c for c in advice.columns if fields[0] in (c.display, c.field)), None)
            limit = advice.limits.max_states
            if column is None or column.strata_basis != "exact" or (column.strata or 0) <= limit:
                continue
            strata = f"{column.strata:,}"
            codes = column.reasons
        why = "; ".join(reason_text(code) for code in codes)
        raise InputError(
            f"{source.name}: stratifying by {', '.join(fields)} makes {strata} strata, "
            f"more than the {advice.limits.max_states:,} a sample may hold ({why}). "
            "Nothing was read. Use fewer or less detailed fields, tabalyst sample "
            "--sample-method smart, or pass --max-strata to run it anyway."
        )


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
    field: str | Sequence[str] | None = None,
    seed: int | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
    max_strata: int | None = None,
    confirmed: bool = False,
    html: bool = True,
    on_progress: ProgressCallback | None = None,
) -> BatchSampleResult:
    """Plan and execute one or more CSV samples.

    A smart sample (design 20.16) scans the file first, or reuses its current
    Scan, and never prompts: it raises ``SelectionConfirmationRequired`` before
    reading any source again when the batch needs a confirmation and ``confirmed``
    is false (rule R1). It also writes the web page of its report unless ``html``
    is false; the other methods ignore ``html``.
    """

    explicit_limit = max_strata is not None
    max_strata = DEFAULT_MAX_STRATA if max_strata is None else max_strata
    selected_method = validate_sample_options(
        method, rows=rows, percent=percent, field=field, max_strata=max_strata
    )
    if selected_method is SampleMethod.SMART:
        from tabalyst.smart_service import execute_smart_samples, prepare_smart_samples

        preparation = prepare_smart_samples(
            input_specs,
            rows=rows,
            percent=percent,
            seed=seed,
            output=output,
            output_dir=output_dir,
            delimiter=delimiter,
            encoding=encoding,
            config_path=config_path,
            force=force,
            html=html,
            on_progress=on_progress,
        )
        return execute_smart_samples(
            preparation, confirmed=confirmed, on_progress=on_progress
        )
    config = resolve_config(
        _config_paths(config_path), separator=delimiter, encoding=encoding
    )
    plan = build_sample_plan(
        input_specs, output=output, output_dir=output_dir, force=force
    )
    if selected_method is SampleMethod.STRATIFIED and not explicit_limit:
        _refuse_excessive_stratification(
            [job.source for job in plan.jobs],
            stratification_fields(field),
            config_path=config_path,
            delimiter=delimiter,
            encoding=encoding,
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
                max_strata=max_strata,
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
