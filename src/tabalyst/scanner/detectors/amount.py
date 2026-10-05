# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Number parts of amounts, percentages and quantities, shared by the
``currency``, ``percentage`` and ``quantity`` detectors
(``docs/dev/scan/detectors.md``, section Amounts).

The number part is read by the rules of the number detector, with the
detector's own conventions, but the sign is written outside it and no
exponent is accepted. A part that has the shape of a number (digits, ``.``,
``,`` and spaces) but that the number detector does not read makes the value
``invalid``, unless it is made of digits only (``01``): such values carry no
number syntax, so identifier codes are never reported as invalid.
"""

from __future__ import annotations

from collections.abc import Mapping

from tabalyst.scanner.detectors.base import AmbiguityAccumulator, Classification
from tabalyst.scanner.detectors.number import NumberDetector

# Spaces accepted between a number and its marker or unit, and as thousands
# separators by the number detector.
SPACES = "   "
# An amount-shaped number part: starts with a digit or ``.`` and a digit,
# ends with a digit or ``.``.
NUMBER_PART = rf"(?=\.?[0-9])[0-9.](?:[0-9.,{SPACES}]*[0-9.])?"


class AmountReader:
    """Reads number parts under the conventions of one detector's settings."""

    __slots__ = ("conventions", "invalid", "number", "resolution")

    def __init__(self, settings: Mapping[str, object], reason: str) -> None:
        self.conventions = tuple(settings.get("conventions", ("dot", "comma")))
        self.resolution = settings.get("ambiguous_convention")
        self.number = NumberDetector(
            {"conventions": self.conventions, "ambiguous_convention": self.resolution}
        )
        self.invalid = Classification("invalid", reason=reason)

    def read(
        self, sign: str, body: str, prefix: str, suffix: str
    ) -> Classification | None:
        """Classify a signed number part; the format is ``prefix``, the
        number's format and ``suffix``. ``None`` (not matched) for digits
        only that the number detector rejects, such as ``01``."""
        found = self.number.classify(sign + body)
        if found is None:
            return None if body.isdigit() else self.invalid
        if found.state == "ambiguous":
            return found
        return Classification(
            "matched",
            format=f"{prefix}{found.format}{suffix}",
            value=found.value,
            candidates=found.candidates,
            convention=found.convention,
        )

    def accumulator(self) -> AmbiguityAccumulator:
        return AmountAccumulator(self)


class AmountAccumulator(AmbiguityAccumulator):
    """The ``ambiguity`` block of the number part (design 12.6)."""

    __slots__ = ()

    def __init__(self, reader: AmountReader) -> None:
        resolution = (
            None
            if reader.resolution is None
            else {"convention": reader.resolution, "source": "config"}
        )
        # Evidence only means something when both readings exist.
        conventions = reader.conventions
        super().__init__(list(conventions) if len(conventions) == 2 else [], resolution)
