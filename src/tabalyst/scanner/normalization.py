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


def _collapse(value: str) -> str:
    return _COLLAPSIBLE.sub(" ", value)


def _strip_accents(value: str) -> str:
    """NFD, removal of combining marks (category ``Mn``), then NFC."""
    decomposed = unicodedata.normalize("NFD", value)
    return unicodedata.normalize(
        "NFC",
        "".join(char for char in decomposed if unicodedata.category(char) != "Mn"),
    )


class Normalizer:
    """Runs the enabled stages on a content string.

    A disabled stage passes its input through unchanged and never counts as a
    change, so it influences nothing (CA16).
    """

    __slots__ = ("_casefold", "_collapse", "_nfc", "_strip_accents", "_trim", "enabled")

    def __init__(self, settings: NormalizationSettings) -> None:
        self.enabled = tuple(getattr(settings, stage) for stage in STAGES)
        (
            self._nfc,
            self._trim,
            self._collapse,
            self._casefold,
            self._strip_accents,
        ) = self.enabled

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
            collapsed = _collapse(value)
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
            stripped = _strip_accents(value)
            if stripped != value:
                value = stripped
                changes |= 16
        return (nfc, trimmed, analytical, folded, value), changes
