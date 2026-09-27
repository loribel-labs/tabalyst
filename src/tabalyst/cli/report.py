"""CLI adapter for Tabalyst Report."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.terminal import ProgressPrinter, batch_exit_code, error_exit_code
from tabalyst.errors import TabalystError
from tabalyst.report_service import BatchReportResult, ReportSuccess, generate_reports


def _print_success(success: ReportSuccess, *, verbose: bool) -> None:
    summary = success.result["summary"]
    typer.echo(
        f"Analyzed {summary['row_count']:,} rows and "
        f"{summary['column_count']} columns.",
        err=True,
    )
    typer.echo(f"Report: {success.job.output.resolve()}", err=True)
    if verbose:
        typer.echo(f"Profile: {success.job.profile_output.resolve()}", err=True)
        history = success.job.execution_output.resolve()
        typer.echo(f"Execution history: {history}", err=True)
        source = success.result["source"]
        typer.echo(f"Encoding: {source['encoding']}", err=True)
        typer.echo(f"Delimiter: {source['delimiter']!r}", err=True)


def _print_batch_result(
    batch: BatchReportResult,
    *,
    quiet: bool,
    verbose: bool,
) -> None:
    if not quiet:
        if len(batch.plan.jobs) == 1 and batch.successes:
            _print_success(batch.successes[0], verbose=verbose)
        else:
            for success in batch.successes:
                typer.echo(
                    f"Report: {success.job.source} -> "
                    f"{success.job.output.resolve()}",
                    err=True,
                )
                if verbose:
                    summary = success.result["summary"]
                    typer.echo(
                        f"  {summary['row_count']:,} rows | "
                        f"{summary['column_count']} columns | "
                        f"{success.result['source']['encoding']} | "
                        f"delimiter {success.result['source']['delimiter']!r}",
                        err=True,
                    )

    for failure in batch.failures:
        typer.echo(f"Error [{failure.job.source}]: {failure.error}", err=True)

    if len(batch.plan.jobs) > 1 and (not quiet or batch.failures):
        typer.echo(
            f"{len(batch.successes)} succeeded, {len(batch.failures)} failed",
            err=True,
        )


def report_command(
    inputs: Annotated[
        list[str],
        typer.Argument(
            metavar="INPUT...",
            help="One or more CSV files or non-recursive glob patterns.",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Explicit HTML filename for a single input.",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-d",
            help="Directory for reports named after their source files.",
        ),
    ] = None,
    delimiter: Annotated[
        str | None,
        typer.Option("--delimiter", help="Override the one-character CSV delimiter."),
    ] = None,
    encoding: Annotated[
        str | None,
        typer.Option("--encoding", help="Override the CSV text encoding."),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="JSON configuration file."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Replace all existing report artifacts."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress success messages."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detected input details."),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="Disable interactive file and phase progress.",
        ),
    ] = False,
) -> None:
    """Analyze and profile datasets with Tabalyst Report."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together.")

    progress = ProgressPrinter(
        enabled=not quiet and not no_progress and sys.stderr.isatty()
    )
    try:
        batch = generate_reports(
            inputs,
            output=output,
            output_dir=output_dir,
            separator=delimiter,
            encoding=encoding,
            config_path=config,
            force=force,
            on_progress=progress,
        )
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc

    _print_batch_result(batch, quiet=quiet, verbose=verbose)
    if batch.failures:
        raise typer.Exit(
            batch_exit_code(failure.error for failure in batch.failures)
        )
