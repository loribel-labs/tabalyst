# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tabalyst command-line application."""

from typing import Annotated

import typer

from tabalyst import __version__
from tabalyst.cli.cache import cache_app
from tabalyst.cli.inspect import inspect_command
from tabalyst.cli.report import report_command
from tabalyst.cli.sample import sample_command
from tabalyst.cli.scan import scan_command

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Tools for unfamiliar data.",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show the installed Tabalyst version and exit.",
            is_eager=True,
            callback=_version_callback,
        ),
    ] = False,
) -> None:
    """Understand, explore, clean, and validate structured data."""


app.command("inspect")(inspect_command)
app.command("report")(report_command)
app.command("sample")(sample_command)
app.command("scan")(scan_command)
app.add_typer(cache_app, name="cache")


def main() -> None:
    """Run the Tabalyst command-line application.

    Windows wildcard expansion is left to Tabalyst: its own pattern resolver
    skips the Inspect files that a shell-expanded ``*.json`` would pass as
    explicit paths.
    """
    app(windows_expand_args=False)
