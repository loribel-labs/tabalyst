# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Postal code detector (``docs/dev/scan/detectors.md``).

Canadian postal codes (``ca``) and United States ZIP codes (``us``). Syntax
only: codes are never checked against assigned ones (EF32). A postal code is
a quasi-identifier shared by many households, so the detector is not
sensitive.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.exposure import ExposureGate

DEFAULT_REGIONS = ("ca", "us")
# Lengths of the accepted forms: ``99999``, ``A9A9A9``, ``A9A 9A9`` and
# ``99999-9999``.
LENGTHS = frozenset({5, 6, 7, 10})
_DIGITS = frozenset("0123456789")
_LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")

_CA = re.compile(r"[A-Za-z][0-9][A-Za-z] ?[0-9][A-Za-z][0-9]")
_US = re.compile(r"[0-9]{5}(?:-[0-9]{4})?")
# Letters Canada Post uses first, and never uses in the other positions.
_CA_FIRST = frozenset("ABCEGHJKLMNPRSTVXY")
_CA_EXCLUDED = frozenset("DFIOQU")
_FORMAT = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
    "A" * 26 + "a" * 26 + "9" * 10,
)

_BAD_FIRST = Classification("invalid", reason="invalid_first_letter")
_BAD_LETTER = Classification("invalid", reason="invalid_letter")
_ZIP = Classification("matched", format="99999", value="us")
_ZIP4 = Classification("matched", format="99999-9999", value="us")


def _ca(value: str) -> Classification | None:
    if _CA.fullmatch(value) is None:
        return None
    letters = value[0].upper(), value[2].upper(), value[-2].upper()
    if letters[0] not in _CA_FIRST:
        return _BAD_FIRST
    if letters[1] in _CA_EXCLUDED or letters[2] in _CA_EXCLUDED:
        return _BAD_LETTER
    return Classification("matched", format=value.translate(_FORMAT), value="ca")


def _us(value: str) -> Classification | None:
    if _US.fullmatch(value) is None:
        return None
    return _ZIP if len(value) == 5 else _ZIP4


class PostalCodeDetector(Detector):
    id = "postal_code"
    family = "address"

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.regions = tuple(settings.get("regions", DEFAULT_REGIONS))
        self._ca = "ca" in self.regions
        self._us = "us" in self.regions

    def classify(self, value: str) -> Classification | None:
        # Exact cheap rejections, cheaper than a shape signature.
        if len(value) not in LENGTHS:
            return None
        first = value[0]
        if first in _DIGITS:
            return _us(value) if self._us else None
        if first in _LETTERS:
            return _ca(value) if self._ca else None
        return None

    def classify_many(self, values: Sequence[str]) -> list[Classification | None]:
        classify = self.classify
        return [classify(value) if len(value) in LENGTHS else None for value in values]

    def accumulator(self) -> PostalCodeAccumulator:
        return PostalCodeAccumulator(self.regions)


class PostalCodeAccumulator(DetectorAccumulator):
    __slots__ = ("regions",)
    ignores_unmatched = True

    def __init__(self, regions: tuple[str, ...]) -> None:
        self.regions = dict.fromkeys(sorted(regions), 0)

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            self.regions[classification.value] += count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {"regions": dict(self.regions)}
