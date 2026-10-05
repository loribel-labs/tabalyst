# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for Tabalyst Inspect."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.terminal import ProgressPrinter, batch_exit_code, error_exit_code
from tabalyst.errors import TabalystError
from tabalyst.inspect_service import (
    BatchInspectResult,
    InspectResult,
    generate_inspections,
)
from tabalyst.inspector.choices import choice_lines

_BASES = {
    "root_array": "the root array",
    "jsonl_records": "the lines of the file",
    "only_eligible_candidate": "the only eligible collection",
    "dominant_candidate": "much larger than {over}",
    "ambiguous": "several collections are equally plausible",
    "no_eligible_candidate": "no eligible collection",
    "candidates_truncated": "too many collections to compare",
}


def _selection(success: InspectResult) -> str:
    selection = success.document.detection.selection
    basis = _BASES[selection.basis].format(over=selection.over)
    return f"Selection: {selection.path or 'none'} ({basis})"


def _configured(success: InspectResult) -> str | None:
    """The collection of ``config`` when it is not the one just selected,
    as an existing file keeps its own."""
    chosen = success.document.config.structure.dataset_path
    if chosen is None or chosen == success.document.detection.selection.path:
        return None
    return f"Configured collection: {chosen} (kept from the existing file)"


def _choices(success: InspectResult) -> list[str]:
    """Ready-to-run report commands, one per eligible collection, when the
    detection could not choose between them."""
    detection = success.document.detection
    if detection.selection.basis != "ambiguous":
        return []
    return choice_lines(
        "report",
        success.source,
        [candidate.path for candidate in detection.candidates if candidate.eligible],
        noun="table" if success.document.inspect.kind == "excel" else "collection",
    )


def _print_success(success: InspectResult, *, verbose: bool) -> None:
    typer.echo(f"Inspect: {success.path.resolve()}", err=True)
    typer.echo(_selection(success), err=True)
    configured = _configured(success)
    if configured is not None:
        typer.echo(configured, err=True)
    if verbose:
        detection = success.document.detection
        typer.echo(f"Format: {success.document.source.format}", err=True)
        typer.echo(f"Candidates: {len(detection.candidates)}", err=True)
        for candidate in detection.candidates:
            noun = "element" if candidate.elements == 1 else "elements"
            reason = (
                "" if candidate.eligible else f", {candidate.ineligible_reason}"
            )
            typer.echo(
                f"  {candidate.path} ({candidate.elements:,} {noun}{reason})",
                err=True,
            )


def _print_batch_result(
    batch: BatchInspectResult, *, quiet: bool, verbose: bool
) -> None:
    if not quiet:
        if len(batch.plan.jobs) == 1 and batch.successes:
            _print_success(batch.successes[0], verbose=verbose)
        else:
            for success in batch.successes:
                typer.echo(
                    f"Inspect: {success.source} -> {success.path.resolve()}", err=True
                )
                typer.echo(f"  {_selection(success)}", err=True)
                configured = _configured(success)
                if configured is not None:
                    typer.echo(f"  {configured}", err=True)

    for success in batch.successes:
        for warning in success.document.warnings:
            if warning.level == "warning" or verbose:
                typer.echo(f"Warning [{success.source}]: {warning.message}", err=True)
        for line in _choices(success):
            typer.echo(line, err=True)
    for failure in batch.failures:
        typer.echo(f"Error [{failure.job.source}]: {failure.error}", err=True)

    if len(batch.plan.jobs) > 1 and (not quiet or batch.failures):
        typer.echo(
            f"{len(batch.successes)} succeeded, {len(batch.failures)} failed",
            err=True,
        )


def inspect_command(
    inputs: Annotated[
        list[str],
        typer.Argument(
            metavar="INPUT...",
            help=(
                "One or more JSON, JSONL, NDJSON or Excel (.xlsx, .xlsm) files, "
                "or non-recursive glob patterns."
            ),
        ),
    ],
    config: Annotated[
        list[Path] | None,
        typer.Option(
            "--config",
            "-c",
            help="JSON configuration file; repeat to merge several, in order.",
        ),
    ] = None,
    reset_config: Annotated[
        bool,
        typer.Option(
            "--reset-config",
            help="Replace the config of an existing Inspect file by the detected one.",
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Replace an existing Inspect file that cannot be kept.",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress success messages."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="List every candidate collection."),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Disable interactive progress."),
    ] = False,
) -> None:
    """Describe JSON, JSONL and Excel files and propose how to read them."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together.")

    progress = ProgressPrinter(
        enabled=not quiet and not no_progress and sys.stderr.isatty()
    )
    try:
        batch = generate_inspections(
            inputs,
            config_path=config,
            reset_config=reset_config,
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
