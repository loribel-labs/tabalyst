# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The character map of a field counted on every original string (design 20.37,
lot C2): the same census as the Scan's, on all the values instead of its samples.

A string is never kept; the tables of characters and emoji are bounded and a
field that passes them is ``limited``, never partly listed.
"""

from __future__ import annotations

from collections.abc import Sequence

from tabalyst.scanner.charactermap import CharacterCensus
from tabalyst.scanner.models import Complete
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import CharacterProfileResult


class CharacterAccumulator:
    """Counts the characters, the case of the ends and the emoji of the original
    content strings of one field."""

    __slots__ = ("cell_ns", "census", "top")

    def __init__(self, top: int, cell_ns: int = 0) -> None:
        # What the plan expects a string to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.top = top
        self.census = CharacterCensus()

    def add_strings(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Account for the distinct content strings of a batch with their counts."""
        self.census.add(raws, counts)

    def result(self, content: int) -> CharacterProfileResult | None:
        """The map, checked against the Scan: the strings read are its content
        strings. ``None`` when a table passed its bound."""
        if self.census.values != content:
            raise ScanMismatch(
                f"content strings: the second pass found {self.census.values}, "
                f"the scan {content}"
            )
        found = self.census.result("exact", self.top)
        if not isinstance(found, Complete):
            return None
        return CharacterProfileResult(**found.value.model_dump())
