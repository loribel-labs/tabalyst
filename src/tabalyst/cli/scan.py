"""CLI adapter for Tabalyst Scan."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.terminal import (
    COLLECTION_HELP,
    ProgressPrinter,
    batch_exit_code,
    collection_paths,
    error_exit_code,
)
from tabalyst.errors import TabalystError
from tabalyst.scan_service import BatchScanResult, ScanSuccess, generate_scans


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def _counts(success: ScanSuccess) -> tuple[str, str, str]:
    result = success.result
    fields = sum(len(dataset.fields) for dataset in result.datasets)
    return (
        _plural(result.scope.records_analyzed, "record"),
        _plural(len(result.datasets), "dataset"),
        _plural(fields, "field"),
    )


def _print_success(success: ScanSuccess, *, verbose: bool) -> None:
    records, datasets, fields = _counts(success)
    typer.echo(f"Scanned {records}: {datasets}, {fields}.", err=True)
    typer.echo(f"Scan: {success.job.output.resolve()}", err=True)
    if verbose:
        result = success.result
        typer.echo(f"Format: {result.source.format}", err=True)
        if result.source.encoding is not None:
            typer.echo(f"Encoding: {result.source.encoding}", err=True)
        if result.source.excel is not None:
            typer.echo(f"Table: {result.source.excel.dataset_path}", err=True)
        if result.source.csv is not None:
            typer.echo(f"Delimiter: {result.source.csv.delimiter!r}", err=True)
        typer.echo(f"Status: {result.status}", err=True)
        typer.echo(f"Diagnostics: {len(result.diagnostics)}", err=True)
        typer.echo(f"Duration: {result.duration_seconds:.2f} s", err=True)


def _print_partial(success: ScanSuccess) -> None:
    scope = success.result.scope
    reasons = ", ".join(
        f"{reason}: {count:,}" for reason, count in sorted(scope.exclusions.items())
    )
    typer.echo(
        f"Warning [{success.job.source}]: partial scan, "
        f"{_plural(scope.records_excluded, 'record')} excluded ({reasons}).",
        err=True,
    )


def _print_batch_result(
    batch: BatchScanResult, *, quiet: bool, verbose: bool
) -> None:
    if not quiet:
        if len(batch.plan.jobs) == 1 and batch.successes:
            _print_success(batch.successes[0], verbose=verbose)
        else:
            for success in batch.successes:
                typer.echo(
                    f"Scan: {success.job.source} -> {success.job.output.resolve()}",
                    err=True,
                )
                if verbose:
                    records, datasets, fields = _counts(success)
                    typer.echo(
                        f"  {records} | {datasets} | {fields} | "
                        f"{success.result.source.format} | "
                        f"{success.result.status}",
                        err=True,
                    )

    for success in batch.successes:
        if success.result.status == "partial":
            _print_partial(success)
        for warning in success.warnings:
            typer.echo(f"Warning [{success.job.source}]: {warning}", err=True)
    for failure in batch.failures:
        typer.echo(f"Error [{failure.job.source}]: {failure.error}", err=True)

    if len(batch.plan.jobs) > 1 and (not quiet or batch.failures):
        typer.echo(
            f"{len(batch.successes)} succeeded, {len(batch.failures)} failed",
            err=True,
        )


def scan_command(
    inputs: Annotated[
        list[str],
        typer.Argument(
            metavar="INPUT...",
            help="One or more CSV or JSON files, or non-recursive glob patterns.",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Explicit scan filename ending in .json, for a single input.",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-d",
            help="Directory for scans named after their source files.",
        ),
    ] = None,
    config: Annotated[
        list[Path] | None,
        typer.Option(
            "--config",
            "-c",
            help="JSON configuration file; repeat to merge several, in order.",
        ),
    ] = None,
    collection: Annotated[
        list[str] | None,
        typer.Option(
            "--collection",
            help=COLLECTION_HELP,
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
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Replace existing scan files."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress success messages."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detected source details."),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Disable interactive progress."),
    ] = False,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers",
            min=1,
            help=(
                "Processes that analyze values: 1 for one process. By default, "
                "files of 16 MiB or more use one per spare processor."
            ),
        ),
    ] = None,
) -> None:
    """Scan CSV and JSON files into a complete JSON description of their data."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together.")

    progress = ProgressPrinter(
        enabled=not quiet and not no_progress and sys.stderr.isatty()
    )
    try:
        batch = generate_scans(
            inputs,
            output=output,
            output_dir=output_dir,
            config_path=config,
            delimiter=delimiter,
            encoding=encoding,
            collections=collection_paths(collection),
            force=force,
            on_progress=progress,
            workers=workers,
            project_storage=True,
        )
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc

    _print_batch_result(batch, quiet=quiet, verbose=verbose)
    if batch.failures:
        raise typer.Exit(
            batch_exit_code(failure.error for failure in batch.failures)
        )
