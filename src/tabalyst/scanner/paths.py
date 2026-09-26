"""Field paths: canonical segments, reversible display syntax and CSV labels.

A path is a tuple of segments relative to the record root (design section 4).
The canonical JSON form is the list of segments; the display syntax is a
readable, reversible label usable in configuration and on the command line.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Key:
    """Member of an object."""

    name: str


@dataclass(frozen=True, slots=True)
class Items:
    """Any element of an array; indices are not distinguished."""


@dataclass(frozen=True, slots=True)
class Column:
    """CSV column at a 1-based position."""

    position: int


Segment = Key | Items | Column
FieldPath = tuple[Segment, ...]

ITEMS = Items()
ROOT: FieldPath = ()
ROOT_DISPLAY = "$"

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DECODER = json.JSONDecoder()


def segment_to_json(segment: Segment) -> dict[str, object]:
    if isinstance(segment, Key):
        return {"key": segment.name}
    if isinstance(segment, Items):
        return {"items": True}
    return {"column": segment.position}


def path_to_json(path: FieldPath) -> list[dict[str, object]]:
    return [segment_to_json(segment) for segment in path]


def _key_display(name: str, *, leading: bool) -> str:
    if _IDENTIFIER.fullmatch(name):
        return name if leading else f".{name}"
    return f"[{json.dumps(name, ensure_ascii=False)}]"


def _segments_display(path: FieldPath, *, leading: bool) -> str:
    parts = []
    for segment in path:
        if isinstance(segment, Key):
            parts.append(_key_display(segment.name, leading=leading))
        elif isinstance(segment, Items):
            parts.append("[]")
        else:
            raise TypeError("CSV column segments have labels, not a display syntax")
        leading = False
    return "".join(parts)


def format_absolute(path: FieldPath) -> str:
    """Display an absolute path, such as a dataset identifier: ``$.customers[]``."""
    return ROOT_DISPLAY + _segments_display(path, leading=False)


def format_relative(path: FieldPath) -> str:
    """Display a field path relative to its record: ``orders[].amount``, or ``$``."""
    if not path:
        return ROOT_DISPLAY
    return _segments_display(path, leading=True)


def parse_path(text: str) -> FieldPath:
    """Parse the absolute (``$...``) or relative display syntax into segments."""
    position = 0
    segments: list[Segment] = []
    if text.startswith(ROOT_DISPLAY):
        position = 1
    elif text:
        identifier = _IDENTIFIER.match(text)
        if identifier is not None:
            segments.append(Key(identifier.group()))
            position = identifier.end()
        elif not text.startswith("["):
            raise ValueError(f"Invalid path {text!r} at position 0")
    else:
        raise ValueError("A path cannot be empty; use '$' for the record root")

    while position < len(text):
        if text.startswith(".", position):
            identifier = _IDENTIFIER.match(text, position + 1)
            if identifier is None:
                raise ValueError(
                    f"Invalid path {text!r}: expected a key at position {position + 1}"
                )
            segments.append(Key(identifier.group()))
            position = identifier.end()
        elif text.startswith("[]", position):
            segments.append(ITEMS)
            position += 2
        elif text.startswith('["', position):
            try:
                name, end = _DECODER.raw_decode(text, position + 1)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid path {text!r}: bad quoted key at position {position}"
                ) from exc
            if not text.startswith("]", end):
                raise ValueError(
                    f"Invalid path {text!r}: expected ']' at position {end}"
                )
            segments.append(Key(name))
            position = end + 1
        else:
            raise ValueError(f"Invalid path {text!r} at position {position}")
    return tuple(segments)


def column_labels(headers: Sequence[str]) -> list[str]:
    """Header name when non-blank and unique, otherwise ``name#position``."""
    counts = Counter(headers)
    return [
        name if name.strip() and counts[name] == 1 else f"{name}#{position}"
        for position, name in enumerate(headers, start=1)
    ]
