"""Terminal output shared by the command adapters: progress and exit codes."""

from collections.abc import Iterable
from typing import ClassVar

import typer

from tabalyst.errors import ConfigurationError, InputError, TabalystError
from tabalyst.progress import ProgressEvent, ProgressPhase
from tabalyst.scanner.paths import ITEMS, format_absolute, parse_path

COLLECTION_HELP = (
    "JSON collection: an array path such as '$.data.items[]', or its short "
    "form data.items; repeatable."
)


def collection_paths(values: list[str] | None) -> list[str] | None:
    """``--collection`` values as absolute paths. Without the leading ``$``, the
    value is the keys leading to the array, so ``data.items`` is
    ``$.data.items[]``, and ``.`` is the root array, ``$[]``; a collection is always an array, so ``[]`` is implied."""
    if values is None:
        return None
    paths = []
    for value in values:
        if value.startswith("$"):
            paths.append(value)
            continue
        if value == ".":
            paths.append(format_absolute((ITEMS,)))
            continue
        try:
            path = parse_path(value, numeric_keys=True)
        except ValueError as exc:
            raise typer.BadParameter(str(exc), param_hint="--collection") from exc
        if not path or path[-1] != ITEMS:
            path = (*path, ITEMS)
        paths.append(format_absolute(path))
    return paths


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

    def __call__(self, event: ProgressEvent) -> None:
        if not self.enabled or event.index is None or event.total is None:
            return
        label = self._labels[event.phase]
        message = f"[{event.index}/{event.total}] {event.source.name} - {label}"
        if event.bytes_read is not None and event.bytes_total:
            message += f" {100 * event.bytes_read // event.bytes_total}%"
        padded = message.ljust(self._width)
        finished = event.phase in {ProgressPhase.COMPLETE, ProgressPhase.FAILED}
        typer.echo(f"\r{padded}", nl=finished, err=True)
        self._width = 0 if finished else max(self._width, len(message))
