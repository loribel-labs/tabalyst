# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Choosing a collection from the command line.

``--collection`` takes a short form (``Costs``, ``data.items``) or an absolute
path (``'$["Sales Q1"]'``). This module expands the former, writes the shortest
value that names a path, and renders the commands to copy when a source has
several equally plausible collections.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path

from tabalyst.errors import ConfigurationError
from tabalyst.scanner.paths import ITEMS, Items, Key, format_absolute, parse_path

_BARE_KEY = re.compile(r"[A-Za-z0-9_]+")


class UndecidedCollection(ConfigurationError):
    """A source has no collection to analyze, and the command line, the
    configuration and the detection did not decide one.

    ``eligible`` holds the absolute paths the user can choose from when the
    detection found several equally plausible ones, empty otherwise. The
    message stands alone; the command line adds the commands to copy.
    """

    def __init__(
        self, message: str, *, source: Path, eligible: Sequence[str] = ()
    ) -> None:
        super().__init__(message)
        self.source = source
        self.eligible = tuple(eligible)


def expand_collection(value: str) -> str:
    """A ``--collection`` value as an absolute path.

    Without the leading ``$``, the value is the keys leading to the array, so
    ``data.items`` is ``$.data.items[]``, and ``.`` is the root array, ``$[]``;
    a collection is always an array, so ``[]`` is implied. Raises ``ValueError``
    for a value that is not a path.
    """
    if value.startswith("$"):
        return value
    if value == ".":
        return format_absolute((ITEMS,))
    path = parse_path(value, numeric_keys=True)
    if not path or path[-1] != ITEMS:
        path = (*path, ITEMS)
    return format_absolute(path)


def _without_items(path: tuple) -> tuple:
    return path[:-1] if path and isinstance(path[-1], Items) else path


def collection_argument(path: str) -> str:
    """The value of ``--collection`` that names ``path``, as typed in a shell.

    The short form when it expands back to the same path (``Costs``,
    ``Sales.Orders``, ``data.items``); otherwise the absolute path in single
    quotes (``'$["Sales Q1"]'``).
    """
    segments = _without_items(parse_path(path))
    if not segments:
        return "."
    names = [segment.name for segment in segments if isinstance(segment, Key)]
    if len(names) == len(segments) and all(_BARE_KEY.fullmatch(n) for n in names):
        short = ".".join(names)
        if _without_items(parse_path(expand_collection(short))) == segments:
            return short
    return f"'{path}'"


def quoted_source(source: str | Path) -> str:
    text = str(source)
    return f'"{text}"' if " " in text else text


def choice_lines(
    command: str, source: str | Path, paths: Sequence[str], *, noun: str = "collection"
) -> list[str]:
    """The lines that offer to rerun ``command`` once per eligible path, then
    once for all of them, ready to copy."""
    name = quoted_source(source)
    lines = [f"Choose the {noun} to analyze:"]
    lines.extend(
        f"  tabalyst {command} {name} --collection {collection_argument(path)}"
        for path in paths
    )
    if command == "report":
        lines.append(f"Or report every {noun}: tabalyst report {name} --all-collections")
    return lines


def collection_slug(path: str, position: int) -> str:
    """A file-name part for a collection: its keys, lower case, accents removed,
    anything else a hyphen (``$["Sales Q1"]`` is ``sales-q1``). ``position`` is
    the 1-based rank of the collection, for a name with nothing to keep."""
    names = [s.name for s in _without_items(parse_path(path)) if isinstance(s, Key)]
    text = unicodedata.normalize("NFKD", "-".join(names))
    text = "".join(char for char in text if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if slug:
        return slug
    return "root" if not names else f"collection-{position}"
