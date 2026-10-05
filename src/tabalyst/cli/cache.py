# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for disposable project cache cleanup."""

from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cache_service import cache_info, clean_cache
from tabalyst.cli.terminal import error_exit_code
from tabalyst.errors import TabalystError

cache_app = typer.Typer(help="Manage disposable project caches.")


def _count(value: int, singular: str) -> str:
    if value == 1:
        return f"{value} {singular}"
    plural = singular.removesuffix("y") + "ies" if singular.endswith("y") else singular + "s"
    return f"{value} {plural}"


@cache_app.command("info")
def info_command(
    source: Annotated[
        Path | None,
        typer.Argument(help="CSV file whose project cache should be inspected."),
    ] = None,
) -> None:
    """Show the size and directory count of all caches or one source cache."""
    try:
        result = cache_info(source)
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc
    typer.echo(
        f"Cache: {_count(result.directories, 'directory')} in "
        f"{_count(result.projects, 'project')} "
        f"({result.logical_bytes:,} bytes)."
    )
    for warning in result.skipped:
        typer.echo(f"Retained: {warning}")


@cache_app.command("clean")
def clean_command(
    source: Annotated[
        Path | None,
        typer.Argument(help="CSV file whose project cache should be cleaned."),
    ] = None,
) -> None:
    """Clean all project caches, or the cache for one source file."""
    try:
        result = clean_cache(source)
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc
    typer.echo(
        f"Cleaned {_count(result.removed, 'cache directory')} in "
        f"{_count(result.projects, 'project')} "
        f"({result.removed_bytes:,} bytes).",
        err=True,
    )
    for warning in result.skipped:
        typer.echo(f"Warning: retained {warning}", err=True)
