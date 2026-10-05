# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pieces shared by the JSON and JSONL readers."""

from __future__ import annotations

import re

from tabalyst.scanner.paths import ITEMS, FieldPath, Key

# A lone surrogate is not valid Unicode and cannot be written as UTF-8.
SURROGATE = re.compile(r"[\ud800-\udfff]")
# Child paths kept by ``Paths``; a larger cache is cleared, so it stays small.
MAX_PATHS = 65_536


class Paths:
    """Child paths already built, by parent path and key, so that every
    occurrence of one path shares one path object: the engine and record
    digests look paths up by identity first, and a new path would hash each
    of its segments."""

    __slots__ = ("_children",)

    def __init__(self) -> None:
        self._children: dict[tuple[int, str | None], tuple] = {}

    def child(self, parent: FieldPath, key: str | None) -> FieldPath:
        """``parent`` followed by the key ``key``, or by items when ``None``."""
        children = self._children
        entry = children.get((id(parent), key))
        # The entry keeps its parent alive, so the identity cannot be reused.
        if entry is not None and entry[0] is parent:
            return entry[1]
        if len(children) >= MAX_PATHS:
            children.clear()
        path = parent + (ITEMS if key is None else Key(key),)
        children[(id(parent), key)] = (parent, path)
        return path
