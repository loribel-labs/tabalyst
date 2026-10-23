# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Terminal output shared by the command adapters: progress and exit codes."""

from collections.abc import Iterable
from typing import ClassVar

import typer

from tabalyst.errors import ConfigurationError, InputError, TabalystError
from tabalyst.inspector.choices import (
    UndecidedCollection,
    choice_lines,
    expand_collection,
)
from tabalyst.progress import ProgressEvent, ProgressPhase
from tabalyst.scanner.readers.excel_common import EXCEL_SUFFIXES

COLLECTION_HELP = (
    "JSON collection: an array path such as '$.data.items[]', or its short "
    "form data.items; repeatable. Excel table: a sheet or table path such as "
    "'$.Sales' or '$.Sales.Orders', or its short form Sales; once."
)


def plural(count: int, word: str) -> str:
    """``count`` and ``word`` in the plural unless the count is one; a word ending
    in ``is`` (analysis) becomes ``es``."""
    if word.endswith("is"):
        word = word[:-2] + ("is" if count == 1 else "es")
        return f"{count:,} {word}"
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def collection_paths(values: list[str] | None) -> list[str] | None:
    """``--collection`` values as absolute paths (see ``expand_collection``)."""
    if values is None:
        return None
    paths = []
    for value in values:
        try:
            paths.append(expand_collection(value))
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--collection") from exc
    return paths


def error_text(error: TabalystError, command: str) -> str:
    """The message of an error, with the commands to copy when a source has
    several equally plausible collections."""
    if isinstance(error, UndecidedCollection) and error.eligible:
        noun = "table" if error.source.suffix.lower() in EXCEL_SUFFIXES else "collection"
        lines = choice_lines(command, error.source, error.eligible, noun=noun)
        return "\n".join([str(error), *lines])
    return str(error)


def error_exit_code(error: TabalystError) -> int:
    if isinstance(error, ConfigurationError):
        return 2
    if isinstance(error, InputError):
        return 4
    return 1


def batch_exit_code(errors: Iterable[TabalystError]) -> int:
    """Exit code of a batch with failures: the most general failure wins."""
    codes = {error_exit_code(error) for error in errors}
    if 1 in codes:
        return 1
    if 2 in codes:
        return 2
    return 4


class ProgressPrinter:
    """One rewritten standard error line per file, finished by its outcome."""

    _labels: ClassVar[dict[ProgressPhase, str]] = {
        ProgressPhase.READING: "Reading",
        ProgressPhase.ANALYZING: "Analyzing",
        ProgressPhase.RENDERING: "Rendering",
        ProgressPhase.WRITING: "Writing",
        ProgressPhase.COMPLETE: "Complete",
        ProgressPhase.FAILED: "Failed",
    }

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._width = 0

    def _label(self, event: ProgressEvent) -> str:
        """The phase of an event, with the detail the line shows (reading only)."""
        label = self._labels[event.phase]
        if event.detail and event.phase == ProgressPhase.READING:
            label = f"{label} ({event.detail})"
        return label

    def __call__(self, event: ProgressEvent) -> None:
        if not self.enabled or event.index is None or event.total is None:
            return
        label = self._label(event)
        if event.stage is not None:
            label = f"{event.stage} : {label}"
        message = f"[{event.index}/{event.total}] {event.source.name} - {label}"
        if event.bytes_read is not None and event.bytes_total:
            message += f" {100 * event.bytes_read // event.bytes_total}%"
        if event.duration_seconds is not None:
            if event.stage is not None:
                message += f" ({event.duration_seconds:.1f}s)"
            else:
                message += f" - {event.duration_seconds:.2f}s"
        padded = message.ljust(self._width)
        finished = event.phase in {ProgressPhase.COMPLETE, ProgressPhase.FAILED}
        typer.echo(f"\r{padded}", nl=finished, err=True)
        self._width = 0 if finished else max(self._width, len(message))
