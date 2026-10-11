# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for Tabalyst Generate."""

from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.terminal import error_exit_code
from tabalyst.errors import TabalystError
from tabalyst.generate_service import build_generate_plan, generate_datasets


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
        typer.Option("--output", "-o", help="One clean CSV file."),
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
        typer.Option("--anomaly-profile", help="Selected anomaly profile."),
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
        typer.Option("--locales", help="Computer locales: en,fr."),
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
        result = generate_datasets(plan)
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc
    for path in result.paths:
        typer.echo(f"Created: {path}", err=True)
