# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for CSV sampling."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.confirm import (
    EXIT_CONFIRMATION_REQUIRED,
    Decision,
    confirm_second_pass,
)
from tabalyst.cli.terminal import ProgressPrinter
from tabalyst.errors import ConfigurationError, InputError, TabalystError
from tabalyst.sampling import DEFAULT_MAX_STRATA, SampleMethod, SampleResult
from tabalyst.sampling_service import BatchSampleResult, generate_samples
from tabalyst.smart_service import execute_smart_samples, prepare_smart_samples


def _print_result(result: SampleResult) -> None:
    typer.echo("Sample created successfully.", err=True)
    typer.echo("", err=True)
    typer.echo(f"Source:        {result.source}", err=True)
    typer.echo(f"Method:        {result.method.value}", err=True)
    if result.field is not None:
        typer.echo(f"Field:         {result.field}", err=True)
    typer.echo(f"Source rows:   {result.source_rows:,}", err=True)
    typer.echo(f"Sample rows:   {result.sample_rows:,}", err=True)
    typer.echo(f"Sample rate:   {result.sample_rate:.2f}%", err=True)
    if result.strata_known is not None:
        typer.echo(
            f"Strata:        {result.strata_known:,} known, "
            f"{result.strata_selected:,} sampled, "
            f"{result.strata_uncovered:,} without rows",
            err=True,
        )
    if result.seed is not None and result.method in {
        SampleMethod.RANDOM,
        SampleMethod.STRATIFIED,
    }:
        typer.echo(f"Seed:          {result.seed}", err=True)
    smart = result.smart
    if smart is not None:
        share = "n/a" if smart.weighted_share is None else f"{smart.weighted_share:.1%}"
        typer.echo(
            f"Targets:       {smart.covered:,} of {smart.evaluable:,} covered "
            f"(weighted {share}); {smart.targets:,} defined",
            err=True,
        )
        typer.echo(
            f"Mandatory:     {smart.mandatory_covered:,} of {smart.mandatory:,} covered",
            err=True,
        )
        typer.echo(
            f"Reserve:       {smart.reserve_rows:,} ordinary rows; the proportions "
            "are not those of the population",
            err=True,
        )
        typer.echo(
            f"Readings:      {smart.passes} of the source "
            f"({'first pass and selection' if smart.scan_ran else 'selection only'})",
            err=True,
        )
    typer.echo(f"Output:        {result.output.resolve()}", err=True)
    if result.report is not None:
        typer.echo(f"Report:        {result.report.resolve()}", err=True)
    if result.page is not None:
        typer.echo(f"Page:          {result.page.resolve()}", err=True)


def _run_smart(
    inputs: list[str],
    *,
    rows: int | None,
    percent: float | None,
    seed: int | None,
    output: Path | None,
    output_dir: Path | None,
    config: Path | None,
    delimiter: str | None,
    encoding: str | None,
    force: bool,
    yes: bool,
    html: bool,
) -> BatchSampleResult:
    """A smart sample: the Scan first unless the stored one is current, then the
    selection, asking first when the rule R1 says so."""
    progress = ProgressPrinter(enabled=sys.stderr.isatty())
    preparation = prepare_smart_samples(
        inputs,
        rows=rows,
        percent=percent,
        seed=seed,
        output=output,
        output_dir=output_dir,
        config_path=config,
        delimiter=delimiter,
        encoding=encoding,
        force=force,
        html=html,
        on_progress=progress,
    )
    for job in preparation.jobs:
        how = "reused" if job.scan.reused else "scanned"
        typer.echo(
            f"Scan: {job.scan.job.output} ({how}); {job.plan.passes.total} "
            f"reading{'s' if job.plan.passes.total > 1 else ''} of {job.job.source.name} "
            f"in all, {len(job.plan.targets):,} targets",
            err=True,
        )
    if preparation.jobs:
        assert preparation.confirmation is not None
        decision = confirm_second_pass(preparation.confirmation, assume_yes=yes)
        if decision is Decision.DECLINED:
            typer.echo("Nothing was started.", err=True)
        if decision is not Decision.PROCEED:
            raise typer.Exit(EXIT_CONFIRMATION_REQUIRED)
    return execute_smart_samples(preparation, confirmed=True, on_progress=progress)


def sample_command(
    inputs: Annotated[
        list[str],
        typer.Argument(
            metavar="INPUT...",
            help="One or more CSV files or non-recursive glob patterns.",
        ),
    ],
    method: Annotated[
        SampleMethod,
        typer.Option("--sample-method", help="Sampling strategy."),
    ],
    rows: Annotated[
        int | None,
        typer.Option("--rows", help="Number of data rows to select."),
    ] = None,
    percent: Annotated[
        float | None,
        typer.Option("--percent", help="Percentage of data rows to select."),
    ] = None,
    field: Annotated[
        list[str] | None,
        typer.Option(
            "--field",
            help="Field used for stratified sampling; repeat it to stratify "
            "by the combinations of several fields.",
        ),
    ] = None,
    max_strata: Annotated[
        int | None,
        typer.Option(
            "--max-strata",
            help=(
                "Most strata a stratified sample may hold; more stop it "
                f"(default {DEFAULT_MAX_STRATA:,}). Given explicitly, it also allows "
                "a run that a stored Scan shows may make too many strata."
            ),
        ),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", help="Seed for reproducible random selection."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output CSV filename."),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-d",
            help="Directory for samples named after their source files.",
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="JSON configuration file."),
    ] = None,
    delimiter: Annotated[
        str | None,
        typer.Option("--delimiter", help="One-character CSV delimiter."),
    ] = None,
    encoding: Annotated[
        str | None,
        typer.Option("--encoding", help="CSV text encoding."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Replace an existing sample file."),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help=(
                "With --sample-method smart, start a costly selection without "
                "asking. Outside a terminal, a costly selection needs it (exit code 3)."
            ),
        ),
    ] = False,
    no_html: Annotated[
        bool,
        typer.Option(
            "--no-html",
            help="With --sample-method smart, write the JSON report but not its web page.",
        ),
    ] = False,
) -> None:
    """Create a CSV sample without modifying the source file."""

    if yes and method is not SampleMethod.SMART:
        raise typer.BadParameter("--yes only goes with --sample-method smart.")
    if no_html and method is not SampleMethod.SMART:
        raise typer.BadParameter("--no-html only goes with --sample-method smart.")
    try:
        if method is SampleMethod.SMART:
            batch = _run_smart(
                inputs,
                rows=rows,
                percent=percent,
                seed=seed,
                output=output,
                output_dir=output_dir,
                config=config,
                delimiter=delimiter,
                encoding=encoding,
                force=force,
                yes=yes,
                html=not no_html,
            )
        else:
            batch = generate_samples(
                inputs,
                method=method,
                rows=rows,
                percent=percent,
                field=field,
                seed=seed,
                output=output,
                output_dir=output_dir,
                config_path=config,
                delimiter=delimiter,
                encoding=encoding,
                force=force,
                max_strata=max_strata,
            )
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        if isinstance(exc, ConfigurationError):
            code = 2
        elif isinstance(exc, InputError):
            code = 4
        else:
            code = 1
        raise typer.Exit(code) from exc

    for index, success in enumerate(batch.successes):
        if index:
            typer.echo("", err=True)
        _print_result(success.result)
    for failure in batch.failures:
        typer.echo(f"Error [{failure.job.source}]: {failure.error}", err=True)
    if len(batch.plan.jobs) > 1:
        typer.echo(
            f"{len(batch.successes)} succeeded, {len(batch.failures)} failed",
            err=True,
        )
    if batch.failures:
        code = (
            4
            if all(isinstance(item.error, InputError) for item in batch.failures)
            else 1
        )
        raise typer.Exit(code)
