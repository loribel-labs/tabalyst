# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for Tabalyst Report."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.confirm import (
    EXIT_CONFIRMATION_REQUIRED,
    Decision,
    confirm_second_pass,
)
from tabalyst.cli.terminal import (
    COLLECTION_HELP,
    ProgressPrinter,
    batch_exit_code,
    collection_paths,
    error_exit_code,
    error_text,
    plural,
)
from tabalyst.deep_store import ConfirmationRequired
from tabalyst.errors import TabalystError
from tabalyst.report_service import BatchReportResult, ReportSuccess, generate_reports
from tabalyst.scanner.planner import Confirmation


def _describe(result: dict) -> str:
    datasets = result["report"]["datasets"]
    rows = sum(dataset["summary"]["row_count"] for dataset in datasets)
    columns = sum(dataset["summary"]["column_count"] for dataset in datasets)
    if result["source"]["format"] in ("csv", "excel"):
        return f"{rows:,} rows and {columns} columns"
    noun = "dataset" if len(datasets) == 1 else "datasets"
    return f"{rows:,} records and {columns} fields in {len(datasets)} {noun}"


def second_pass_line(result: dict) -> str | None:
    """What the second pass did for a report, in a sentence: named whether the
    planner chose it or the user forced it, with what it computed, reused and left
    out (rule R1). ``None`` for a profile that has no ``analyses``."""
    block = result.get("analyses")
    if block is None:
        return None
    how = {"auto": "automatic", "forced": "forced", "off": "off"}[block["mode"]]
    outcome = block["outcome"]
    if outcome == "disabled":
        return "Second pass: off (deep.mode is off), no analysis added."
    if outcome == "failed":
        return f"Second pass ({how}): left out, {block['reason']}"
    document = block.get("deep")
    if document is None or outcome == "nothing_selected":
        return f"Second pass ({how}): nothing to add, the scan already answers what it could."
    run = document["run"]
    parts = [f"{run['executed']} computed", f"{run['reused']} reused"]
    if run["skipped"]:
        reason = block.get("reason")
        parts.append(f"{run['skipped']} left out" + (f" ({reason})" if reason else ""))
    total = run["executed"] + run["reused"] + run["skipped"]
    return f"Second pass ({how}): {plural(total, 'analysis')}, {', '.join(parts)}."


def _print_success(success: ReportSuccess, *, verbose: bool) -> None:
    typer.echo(f"Analyzed {_describe(success.result)}.", err=True)
    typer.echo(f"Report: {success.job.output.resolve()}", err=True)
    line = second_pass_line(success.result)
    if line is not None:
        typer.echo(line, err=True)
    if verbose:
        typer.echo(f"Profile: {success.job.profile_output.resolve()}", err=True)
        history = success.job.execution_output.resolve()
        typer.echo(f"Execution history: {history}", err=True)
        source = success.result["source"]
        if source["encoding"] is not None:
            typer.echo(f"Encoding: {source['encoding']}", err=True)
        if source["csv"] is not None:
            typer.echo(f"Delimiter: {source['csv']['delimiter']!r}", err=True)


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
                line = second_pass_line(success.result)
                if line is not None:
                    typer.echo(f"  {line}", err=True)
                if verbose:
                    source = success.result["source"]
                    details = [_describe(success.result)]
                    if source["encoding"] is not None:
                        details.append(source["encoding"])
                    if source["csv"] is not None:
                        details.append(f"delimiter {source['csv']['delimiter']!r}")
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
    deep: Annotated[
        bool,
        typer.Option(
            "--deep",
            help=(
                "Force the second pass: read each source again for the exact "
                "analyses the scan lacks. Without it the report adds only what the "
                "planner finds useful and cheap. Asks first when it is costly."
            ),
        ),
    ] = False,
    dedup_report: Annotated[
        Path | None,
        typer.Option(
            "--dedup-report",
            help=(
                "A Dedup report (.dedup.json), or the folder holding the one of each "
                "source, that proves the copies of rows behind the uniqueness of "
                "identifier columns. CSV sources only. Without it, the report beside "
                "each source is tried."
            ),
        ),
    ] = None,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help=(
                "Start a costly forced second pass without asking. Outside a "
                "terminal, a costly forced second pass needs it (exit code 3)."
            ),
        ),
    ] = False,
) -> None:
    """Analyze and profile datasets with Tabalyst Report."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together.")

    progress = ProgressPrinter(
        enabled=not quiet and not no_progress and sys.stderr.isatty()
    )
    decisions: list[Decision] = []

    def confirm(confirmation: Confirmation) -> bool:
        decisions.append(confirm_second_pass(confirmation, assume_yes=yes))
        return decisions[-1] is Decision.PROCEED

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
            deep=deep,
            confirm=confirm,
            dedup_report=dedup_report,
        )
    except ConfirmationRequired as exc:
        if decisions and decisions[-1] is Decision.DECLINED:
            typer.echo("Nothing was started.", err=True)
        raise typer.Exit(EXIT_CONFIRMATION_REQUIRED) from exc
    except TabalystError as exc:
        typer.echo(f"Error: {error_text(exc, 'report')}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc

    _print_batch_result(batch, quiet=quiet, verbose=verbose)
    if batch.failures:
        raise typer.Exit(
            batch_exit_code(failure.error for failure in batch.failures)
        )
