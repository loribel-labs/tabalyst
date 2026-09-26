"""CLI adapter for CSV sampling."""

from pathlib import Path
from typing import Annotated

import typer

from tabalyst.errors import ConfigurationError, InputError, TabalystError
from tabalyst.sampling import SampleMethod, SampleResult
from tabalyst.sampling_service import generate_samples


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
    if result.seed is not None and result.method in {
        SampleMethod.RANDOM,
        SampleMethod.STRATIFIED,
    }:
        typer.echo(f"Seed:          {result.seed}", err=True)
    typer.echo(f"Output:        {result.output.resolve()}", err=True)


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
        str | None,
        typer.Option("--field", help="Field used for stratified sampling."),
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
) -> None:
    """Create a CSV sample without modifying the source file."""

    try:
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
