"""Normalization version 1 (design section 10).

Normalization applies to ``content`` strings only and never modifies the
source. The analytical value, used by frequency listings, samples, lengths and
statistics, is the output of the enabled ``nfc``, ``trim`` and
``collapse_whitespace`` stages.
"""

from __future__ import annotations

import re
import unicodedata

from tabalyst.scanner.config import NormalizationSettings

VERSION = 1

# Runs of whitespace other than the line breaks of ``str.splitlines``.
_COLLAPSIBLE = re.compile("[^\\S\r\n\v\f\x1c-\x1e\x85  ]+")


def _collapse(value: str) -> str:
    return _COLLAPSIBLE.sub(" ", value)


class Analytical:
    """Callable computing the analytical value of a content string."""

    __slots__ = ("_collapse", "_nfc", "_trim")

    def __init__(self, settings: NormalizationSettings) -> None:
        self._nfc = settings.nfc
        self._trim = settings.trim
        self._collapse = settings.collapse_whitespace

    def __call__(self, value: str) -> str:
        if self._nfc and not value.isascii():
            value = unicodedata.normalize("NFC", value)
        if self._trim:
            value = value.strip()
        if self._collapse:
            value = _collapse(value)
        return value
