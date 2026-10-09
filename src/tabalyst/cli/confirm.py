# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Confirmation of a costly operation before it starts (rule R1, design 20.3)."""

import sys
from collections.abc import Callable
from enum import StrEnum

import typer

from tabalyst.scanner.planner import Confirmation
from tabalyst.scanner.planner.render import confirmation_lines

# A confirmation was needed and could not be asked: nothing was started.
EXIT_CONFIRMATION_REQUIRED = 3


class Decision(StrEnum):
    PROCEED = "proceed"
    DECLINED = "declined"
    # Not a terminal and no ``--yes``: nothing is asked, the command stops.
    REFUSED = "refused"


def is_interactive() -> bool:
    """Whether both ends of the command are a terminal, so a question can be
    asked and answered. A script, a pipe or a CI never is."""
    return sys.stdin.isatty() and sys.stderr.isatty()


def confirm_second_pass(
    confirmation: Confirmation,
    *,
    assume_yes: bool = False,
    interactive: bool | None = None,
    ask: Callable[[str], bool] | None = None,
) -> Decision:
    """Decide whether a costly operation starts.

    Nothing to confirm, or ``--yes``: it proceeds without a word. In a terminal
    the estimate is shown and the user is asked, the default answer being no.
    Outside a terminal nothing is asked: the operation is refused, with the
    estimate and how to allow it. ``--force`` has no part here: it only allows
    overwriting an output.
    """
    if not confirmation.required or assume_yes:
        return Decision.PROCEED
    interactive = is_interactive() if interactive is None else interactive
    for line in confirmation_lines(confirmation):
        typer.echo(line, err=True)
    if not interactive:
        typer.echo(
            "Nothing was started. Outside a terminal this needs --yes to run.", err=True
        )
        return Decision.REFUSED
    ask = ask or (lambda text: typer.confirm(text, default=False, err=True))
    return Decision.PROCEED if ask("Start it?") else Decision.DECLINED
