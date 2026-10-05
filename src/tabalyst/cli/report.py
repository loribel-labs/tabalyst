# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for Tabalyst Report."""

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
    error_text,
)
from tabalyst.errors import TabalystError
from tabalyst.report_service import BatchReportResult, ReportSuccess, generate_reports


def _describe(result: dict) -> str:
    datasets = result["datasets"]
    rows = sum(dataset["summary"]["row_count"] for dataset in datasets)
    columns = sum(dataset["summary"]["column_count"] for dataset in datasets)
    if result["source"]["format"] in ("csv", "excel"):
        return f"{rows:,} rows and {columns} columns"
    noun = "dataset" if len(datasets) == 1 else "datasets"
    return f"{rows:,} records and {columns} fields in {len(datasets)} {noun}"


def _print_success(success: ReportSuccess, *, verbose: bool) -> None:
    typer.echo(f"Analyzed {_describe(success.result)}.", err=True)
    typer.echo(f"Report: {success.job.output.resolve()}", err=True)
    if verbose:
        typer.echo(f"Profile: {success.job.profile_output.resolve()}", err=True)
        history = success.job.execution_output.resolve()
        typer.echo(f"Execution history: {history}", err=True)
        source = success.result["source"]
        if source["encoding"] is not None:
            typer.echo(f"Encoding: {source['encoding']}", err=True)
        if source["delimiter"] is not None:
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
                    source = success.result["source"]
                    details = [_describe(success.result)]
                    if source["encoding"] is not None:
                        details.append(source["encoding"])
                    if source["delimiter"] is not None:
                        details.append(f"delimiter {source['delimiter']!r}")
                    typer.echo("  " + " | ".join(details), err=True)

    for source, warning in batch.plan.warnings:
        typer.echo(f"Warning [{source}]: {warning}", err=True)
    for success in batch.successes:
        for warning in success.warnings:
            typer.echo(f"Warning [{success.job.source}]: {warning}", err=True)
        if success.source_checked is False:
            typer.echo(
                f"Warning [{success.job.source}]: source "
                f"{success.job.scanned.name} not found beside the scan "
                "document; not checked for changes since the scan.",
                err=True,
            )
    for failure in batch.failures:
        typer.echo(
            f"Error [{failure.job.source}]: {error_text(failure.error, 'report')}",
            err=True,
        )

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
            help=(
                "One or more CSV, JSON, JSONL or Excel (.xlsx, .xlsm) files, or "
                "scan documents with --scan, or non-recursive glob patterns."
            ),
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
            help=(
                "Directory for reports named after their source files; "
                "required by --all-collections with several inputs."
            ),
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
    collection: Annotated[
        list[str] | None,
        typer.Option("--collection", help=COLLECTION_HELP),
    ] = None,
    all_collections: Annotated[
        bool,
        typer.Option(
            "--all-collections",
            help=(
                "Report every visible collection of a JSON file or Excel "
                "workbook, as <name>.<collection>.html and .json; needs -d "
                "with several inputs."
            ),
        ),
    ] = False,
    from_scan: Annotated[
        bool,
        typer.Option(
            "--scan",
            help=(
                "Build the reports from scan documents written by tabalyst "
                "scan, without reading the sources again."
            ),
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Replace all existing report artifacts."),
    ] = False,
    details: Annotated[
        bool,
        typer.Option(
            "--details/--no-details",
            help="Generate standalone HTML pages for every column (off by default).",
        ),
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
            collections=collection_paths(collection),
            config_path=config,
            force=force,
            details=details,
            on_progress=progress,
            from_scan=from_scan,
            workers=workers,
            all_collections=all_collections,
        )
    except TabalystError as exc:
        typer.echo(f"Error: {error_text(exc, 'report')}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc

    _print_batch_result(batch, quiet=quiet, verbose=verbose)
    if batch.failures:
        raise typer.Exit(
            batch_exit_code(failure.error for failure in batch.failures)
        )
