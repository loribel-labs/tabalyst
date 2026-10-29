# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for Tabalyst Generate."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.terminal import error_exit_code
from tabalyst.errors import TabalystError
from tabalyst.generate_service import (
    GenerateProgress,
    GenerateResult,
    build_generate_plan,
    generate_datasets,
)

PHASE_NAMES = {"rows": "generating rows", "errors": "injecting errors", "publish": "writing files"}
# Below this, a phase is noise in the report.
MIN_REPORTED_SECONDS = 0.05


def format_duration(seconds: float) -> str:
    """A duration for people: tenths of a second under a minute, then minutes and seconds."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, rest = divmod(round(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class GenerateProgressPrinter:
    """One rewritten standard error line per stage, with the time left once it is known."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._stage: str | None = None
        self._stage_start = 0.0
        self._width = 0

    def __call__(self, event: GenerateProgress) -> None:
        if not self.enabled or not event.total:
            return
        if event.stage != self._stage:
            self._stage = event.stage
            self._stage_start = event.elapsed_seconds
        spent = event.elapsed_seconds - self._stage_start
        message = f"{event.stage} {event.done:,}/{event.total:,} ({100 * event.done // event.total}%)"
        if event.done >= event.total:
            message += f" - {format_duration(spent)}"
        elif event.done and spent >= 1:
            message += (f" - {format_duration(spent)}, "
                        f"about {format_duration(spent * (event.total - event.done) / event.done)} left")
        finished = event.done >= event.total
        typer.echo(f"\r{message.ljust(self._width)}", nl=finished, err=True)
        self._width = 0 if finished else max(self._width, len(message))


def timing_report(result: GenerateResult) -> str:
    """The closing line: rows, total time, rate and where the time went."""
    rows = sum(result.row_counts.values()) if len(result.row_counts) == 1 else None
    text = f"Done in {format_duration(result.seconds)}"
    if rows is not None:
        text = f"{rows:,} rows in {format_duration(result.seconds)}"
        if result.seconds > 0:
            text += f" ({rows / result.seconds:,.0f} rows/s)"
    changed = sum(result.anomaly_counts.values())
    if changed:
        text += f", {changed:,} cells changed"
    parts = [f"{PHASE_NAMES[name]} {format_duration(value)}"
             for name, value in result.timings.items()
             if name in PHASE_NAMES and value >= MIN_REPORTED_SECONDS]
    return f"{text}: {', '.join(parts)}" if len(parts) > 1 else text


def generate_command(
    definition: Annotated[
        Path | None,
        typer.Argument(help="Generate definition or package directory."),
    ] = None,
    example: Annotated[
        str | None,
        typer.Option("--example", help="Packaged example: crm, insurance, or computer."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="One CSV file (with --anomaly-profile: the CSV with errors, plus FILE.changes.csv)."),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-d", help="Directory for all artifacts."),
    ] = None,
    rows: Annotated[
        int | None,
        typer.Option("--rows", help="Number of generated rows."),
    ] = None,
    seed: Annotated[
        int | None,
        typer.Option("--seed", help="Root random seed."),
    ] = None,
    as_of_date: Annotated[
        str | None,
        typer.Option("--as-of-date", help="Reference date (YYYY-MM-DD)."),
    ] = None,
    anomaly_profile: Annotated[
        str | None,
        typer.Option("--anomaly-profile", help="Inject errors. Computer: dirty_realistic, dirty_stress, unit_variants, unit_variants_extended."),
    ] = None,
    request: Annotated[
        Path | None,
        typer.Option("--request", help="JSON generation request."),
    ] = None,
    generation_profile: Annotated[
        str | None,
        typer.Option("--generation-profile", help="Catalog selection profile."),
    ] = None,
    output_profile: Annotated[
        str | None,
        typer.Option("--output-profile", help="Output column profile."),
    ] = None,
    market: Annotated[
        str | None,
        typer.Option("--market", help="Offer market: ca or us."),
    ] = None,
    locales: Annotated[
        str | None,
        typer.Option("--locales", help="Computer locales: en, fr or en,fr (default en with -o, en,fr with -d)."),
    ] = None,
    unit_style: Annotated[
        str | None,
        typer.Option("--unit-style", help="Computer values: numeric or localized units."),
    ] = None,
    unit_columns: Annotated[
        str | None,
        typer.Option("--unit-columns", help="Comma-separated Computer measurement columns to format with units."),
    ] = None,
    validate_only: Annotated[
        bool,
        typer.Option("--validate-only", help="Validate a package without writing."),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Replace existing artifacts."),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Hide the progress line. It is also hidden outside a terminal."),
    ] = False,
) -> None:
    """Validate and generate datasets from a definition or package."""
    try:
        plan = build_generate_plan(
            definition, example=example, output=output, output_dir=output_dir,
            rows=rows, seed=seed, as_of_date=as_of_date,
            anomaly_profile=anomaly_profile, force=force, request=request,
            generation_profile=generation_profile, output_profile=output_profile,
            market=market, locales=locales, unit_style=unit_style,
            unit_columns=unit_columns,
            validate_only=validate_only,
        )
        if validate_only:
            typer.echo("Valid Generate package.", err=True)
            return
        result = generate_datasets(
            plan, on_progress=GenerateProgressPrinter(not no_progress and sys.stderr.isatty()),
        )
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc
    for path in result.paths:
        typer.echo(f"Created: {path}", err=True)
    typer.echo(timing_report(result), err=True)
