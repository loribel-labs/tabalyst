"""CLI adapter for Tabalyst Report."""

from pathlib import Path
from typing import Annotated

import typer

from tabalyst.errors import ConfigurationError, InputError, TabalystError
from tabalyst.execution_log import EXECUTION_LOG_NAME
from tabalyst.service import analyze


def _error_exit_code(error: TabalystError) -> int:
    if isinstance(error, ConfigurationError):
        return 2
    if isinstance(error, InputError):
        return 4
    return 1


def _print_success(result: dict, output: Path, *, verbose: bool) -> None:
    summary = result["summary"]
    typer.echo(
        f"Analyzed {summary['row_count']:,} rows and "
        f"{summary['column_count']} columns.",
        err=True,
    )
    typer.echo(f"Report: {output.resolve()}", err=True)
    if verbose:
        typer.echo(f"Profile: {output.with_suffix('.json').resolve()}", err=True)
        history = (output.parent / EXECUTION_LOG_NAME).resolve()
        typer.echo(f"Execution history: {history}", err=True)
        source = result["source"]
        typer.echo(f"Encoding: {source['encoding']}", err=True)
        typer.echo(f"Delimiter: {source['delimiter']!r}", err=True)


def report_command(
    input_path: Annotated[
        Path,
        typer.Argument(
            metavar="INPUT",
            help="Structured data file to analyze (CSV in this release).",
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Complete HTML report filename.",
        ),
    ],
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
        typer.Option("--force", "-f", help="Replace existing report artifacts."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress success messages."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detected input details."),
    ] = False,
) -> None:
    """Analyze and profile a dataset, then generate an HTML report."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together.")

    try:
        result = analyze(
            input_path,
            output,
            separator=delimiter,
            encoding=encoding,
            config_path=config,
            force=force,
        )
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(_error_exit_code(exc)) from exc

    if not quiet:
        _print_success(result, output, verbose=verbose)
