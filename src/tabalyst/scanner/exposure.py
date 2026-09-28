"""Exposure gate of sensitive values (design 12.8).

A field is sensitive when a sensitive detector matched at least one of its
values, or failed on it: a failure cannot prove that nothing matched. Every
value-bearing block of a sensitive field goes through one gate at
finalization, configured by ``exposure.sensitive_values``:

- ``mask`` replaces each uppercase letter with ``A``, every other letter with
  ``a`` and each digit with ``9``, keeps other characters and does not
  compress runs. Equal masks merge before listings are selected, so
  frequencies, samples and variant groups describe the masked values.
- ``hide`` removes the values from every listing and keeps the counts.
- ``show`` exposes the values unchanged.
"""

from __future__ import annotations

import string
from collections.abc import Iterable
from typing import Literal

ExposureMode = Literal["mask", "hide", "show"]

_ASCII_MASK = str.maketrans(
    {
        **dict.fromkeys(string.digits, "9"),
        **dict.fromkeys(string.ascii_uppercase, "A"),
        **dict.fromkeys(string.ascii_lowercase, "a"),
    }
)


def _symbol(char: str) -> str:
    if char.isdigit():
        return "9"
    if char.isalpha():
        return "A" if char.isupper() else "a"
    return char


# Characters of ``_MASK``; a larger table is cleared, so it stays small.
_MAX_SYMBOLS = 65_536


class _Symbols(dict):
    """``str.translate`` table of ``_symbol``, filled as characters are met."""

    def __missing__(self, ordinal: int) -> str:
        if len(self) >= _MAX_SYMBOLS:
            self.clear()
        symbol = self[ordinal] = _symbol(chr(ordinal))
        return symbol


_MASK = _Symbols()


def mask(value: str) -> str:
    """The masked form of ``value``: ``SECRET-1111`` becomes ``AAAAAA-9999``."""
    if value.isascii():
        return value.translate(_ASCII_MASK)
    return value.translate(_MASK)


class ExposureGate:
    """How the values of one field are exposed; ``SHOW`` for fields that are
    not sensitive."""

    __slots__ = ("mode",)

    def __init__(self, mode: ExposureMode) -> None:
        self.mode = mode

    @property
    def hides(self) -> bool:
        return self.mode == "hide"

    def value(self, text: str) -> str | None:
        """One value, or ``None`` when hidden."""
        if self.mode == "show":
            return text
        return mask(text) if self.mode == "mask" else None

    def examples(self, values: list[str]) -> list[str]:
        """Distinct examples, masks deduplicated in first-seen order."""
        if self.mode == "show":
            return values
        if self.mode == "hide":
            return []
        return list(dict.fromkeys(map(mask, values)))

    def counts(self, items: Iterable[tuple[str, int]]) -> dict[str, int]:
        """Values with counts, equal masks merged in first-seen order; empty
        when hidden."""
        if self.mode == "hide":
            return {}
        exposed = self.value
        merged: dict[str, int] = {}
        for text, count in items:
            key = exposed(text)
            merged[key] = merged.get(key, 0) + count
        return merged

    def typed_counts(
        self, items: Iterable[tuple[tuple[str, str], int]]
    ) -> dict[tuple[str, str], int]:
        """Like ``counts`` for ``(native type, text)`` values."""
        if self.mode == "show":
            return dict(items)
        if self.mode == "hide":
            return {}
        merged: dict[tuple[str, str], int] = {}
        for (native_type, text), count in items:
            key = (native_type, mask(text))
            merged[key] = merged.get(key, 0) + count
        return merged


SHOW = ExposureGate("show")
