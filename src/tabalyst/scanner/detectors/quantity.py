"""Quantity detector (``docs/dev/scan/detectors.md``).

A signed number part, an optional space and a unit, whatever the unit:
``10m``, ``10 Go``, ``1 024 Mo``, ``90 km/h``. The detector checks syntax
only; it does not know units (EF32). Formats replace the unit with
``[unit]`` so that they stay bounded; units are counted in ``details``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from tabalyst.scanner.detectors.amount import (
    NUMBER_PART,
    SPACES,
    AmountAccumulator,
    AmountReader,
)
from tabalyst.scanner.detectors.base import Classification, Detector
from tabalyst.scanner.detectors.currency import CODES
from tabalyst.scanner.detectors.names import NameCounts
from tabalyst.scanner.exposure import ExposureGate

MAX_UNIT_LENGTH = 12
_SIGNS = "°²³"  # degree, superscript two and three
_INNER = "/·"  # slash, middle dot
_ORDINALS = frozenset({"er", "re", "e", "ème", "eme", "nd", "nde", "st", "rd", "th"})
_FIRST = frozenset("+-.0123456789")
_QUANTITY = re.compile(
    rf"(?P<sign>[+-]?)(?P<body>{NUMBER_PART})(?P<space>[{SPACES}]?)"
    r"(?P<unit>[^\s0-9.,+-]\S*)"
)


def is_unit(unit: str) -> bool:
    if not 1 <= len(unit) <= MAX_UNIT_LENGTH:
        return False
    first, last = unit[0], unit[-1]
    if not (first.isalpha() or first == "°") or last in _INNER:
        return False
    if not all(char.isalpha() or char in _SIGNS or char in _INNER for char in unit):
        return False
    # Currency codes belong to the currency detector.
    return unit not in CODES and unit.casefold() not in _ORDINALS


def unit(value: str) -> str | None:
    """The unit of a candidate value, or ``None``."""
    match = _QUANTITY.fullmatch(value)
    return None if match is None or not is_unit(match["unit"]) else match["unit"]


class QuantityDetector(Detector):
    id = "quantity"
    family = "measurement"

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.reader = AmountReader(settings, "invalid_number")
        self.max_tracked = settings.get("max_tracked_units", 10_000)
        self.max_listed = settings.get("max_listed_units", 20)

    def classify(self, value: str) -> Classification | None:
        # Exact cheap rejection by the first and last characters.
        if value[:1] not in _FIRST:
            return None
        last = value[-1]
        if not (last.isalpha() or last in _SIGNS):
            return None
        match = _QUANTITY.fullmatch(value)
        if match is None or not is_unit(match["unit"]):
            return None
        return self.reader.read(
            match["sign"], match["body"], "", match["space"] + "[unit]"
        )

    def accumulator(self) -> QuantityAccumulator:
        return QuantityAccumulator(
            self.reader, NameCounts(self.max_tracked, self.max_listed)
        )


class QuantityAccumulator(AmountAccumulator):
    __slots__ = ("units",)

    def __init__(self, reader: AmountReader, units: NameCounts) -> None:
        super().__init__(reader)
        self.units = units

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        super().add(value, classification, count)
        if classification is not None and classification.state != "invalid":
            self.units.add(unit(value), count)

    def details(self, gate: ExposureGate) -> dict[str, object]:
        # Units are text of the field: they go through the exposure gate.
        return {**super().details(gate), "units": self.units.block(gate)}
