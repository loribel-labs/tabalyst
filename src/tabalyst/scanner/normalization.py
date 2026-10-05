# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Normalization version 1 (design section 10).

Normalization applies to ``content`` strings only and never modifies the
source. Stages run in a fixed order and each can be disabled. The analytical
value, used by frequency listings, samples, lengths and statistics, is the
output of the enabled ``nfc``, ``trim`` and ``collapse_whitespace`` stages; the
comparison key, which groups variants, is the output of every enabled stage.
"""

from __future__ import annotations

import re
import unicodedata

from tabalyst.scanner.config import NormalizationSettings

VERSION = 1

STAGES = ("nfc", "trim", "collapse_whitespace", "casefold", "strip_accents")
# Index in ``STAGES`` of the last stage of the analytical value.
ANALYTICAL_STAGE = 2
KEY_STAGE = len(STAGES) - 1

# Runs of whitespace other than the line breaks of ``str.splitlines``.
_COLLAPSIBLE = re.compile("[^\\S\r\n\v\f\x1c-\x1e\x85  ]+")


def collapse(value: str) -> str:
    """Every run of whitespace other than line breaks as one space."""
    return _COLLAPSIBLE.sub(" ", value)


# Characters kept by ``_MARKS``; a larger table is cleared, so it stays small.
_MAX_MARKS = 65_536


class _CombiningMarks(dict):
    """``str.translate`` table deleting combining marks (category ``Mn``) and
    keeping every other character, filled as characters are met."""

    def __missing__(self, ordinal: int) -> int | None:
        if len(self) >= _MAX_MARKS:
            self.clear()
        kept = None if unicodedata.category(chr(ordinal)) == "Mn" else ordinal
        self[ordinal] = kept
        return kept


_MARKS = _CombiningMarks()


def strip_accents(value: str) -> str:
    """NFD, removal of combining marks (category ``Mn``), then NFC."""
    decomposed = unicodedata.normalize("NFD", value)
    return unicodedata.normalize("NFC", decomposed.translate(_MARKS))


class Normalizer:
    """Runs the enabled stages on a content string.

    A disabled stage passes its input through unchanged and never counts as a
    change, so it influences nothing (CA16).
    """

    __slots__ = (
        "_casefold",
        "_collapse",
        "_nfc",
        "_strip_accents",
        "_trim",
        "accents",
        "casefold",
        "enabled",
        "fast",
        "nfc",
    )

    def __init__(self, settings: NormalizationSettings) -> None:
        self.enabled = tuple(getattr(settings, stage) for stage in STAGES)
        (
            self._nfc,
            self._trim,
            self._collapse,
            self._casefold,
            self._strip_accents,
        ) = self.enabled
        self.nfc = self._nfc
        self.casefold = self._casefold
        self.accents = self._strip_accents
        # Batches normalize printable strings inline when both whitespace
        # stages run (``ValueMeasures.add_strings``).
        self.fast = self._trim and self._collapse

    def analytical(self, value: str) -> str:
        """Output of the enabled ``nfc``, ``trim`` and ``collapse_whitespace``."""
        return self.run(value)[0][ANALYTICAL_STAGE]

    def run(self, value: str) -> tuple[tuple[str, ...], int]:
        """Output of each stage, in ``STAGES`` order, and the changes: bit ``i``
        is set when stage ``i`` modified the output of the previous stage."""
        changes = 0
        if (
            self._nfc
            and not value.isascii()
            and not unicodedata.is_normalized("NFC", value)
        ):
            value = unicodedata.normalize("NFC", value)
            changes = 1
        nfc = value
        if self._trim:
            stripped = value.strip()
            if stripped != value:
                value = stripped
                changes |= 2
        trimmed = value
        if self._collapse:
            collapsed = collapse(value)
            if collapsed != value:
                value = collapsed
                changes |= 4
        analytical = value
        if self._casefold:
            folded = value.casefold()
            if folded != value:
                value = folded
                changes |= 8
        folded = value
        if self._strip_accents and not value.isascii():
            stripped = strip_accents(value)
            if stripped != value:
                value = stripped
                changes |= 16
        return (nfc, trimmed, analytical, folded, value), changes
