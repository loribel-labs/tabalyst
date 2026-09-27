"""Phone number detector (``docs/dev/scan/detectors.md``).

North American Numbering Plan (``nanp``: Canada, the United States and the
other NANP countries) and France (``fr``). Syntax only: numbers are never
checked against assigned ranges (EF32). Phone numbers identify people, so the
detector is sensitive: its fields are masked by default (design 12.8).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.exposure import ExposureGate

DEFAULT_REGIONS = ("nanp", "fr")
# Shortest and longest accepted forms: ``0612345678`` and
# ``0033 (0) 6 12 34 56 78``.
MIN_LENGTH = 10
MAX_LENGTH = 22
# Digits of the accepted forms: 10 (national) to 14 (``0033 (0)`` and nine).
MIN_DIGITS = 10
MAX_DIGITS = 14
_FIRST = frozenset("+(0123456789")
_SYNTAX = str.maketrans("", "", " .-()+")
_DIGIT = re.compile(r"[0-9]")

_NANP = re.compile(
    r"(?:(?P<prefix>\+1|1)[ .-]?)?"
    r"(?:\((?P<parenthesized>[0-9]{3})\) ?|(?P<area>[0-9]{3})[ .-]?)"
    r"(?P<exchange>[0-9]{3})[ .-]?[0-9]{4}"
)
_FR_PAIRS = r"(?P<sep>[ .-]?)[0-9]{2}(?:(?P=sep)[0-9]{2}){3}"
_FR_NATIONAL = re.compile(rf"0(?P<zone>[0-9]){_FR_PAIRS}")
_FR_INTERNATIONAL = re.compile(
    rf"(?P<prefix>\+33|0033)[ .-]?(?P<trunk>\(0\) ?)?(?P<zone>[0-9]){_FR_PAIRS}"
)
# The international prefix followed by a national number with its trunk 0.
_FR_KEPT_TRUNK = re.compile(rf"(?:\+33|0033)[ .-]?0[0-9]{_FR_PAIRS}")

_BAD_AREA = Classification("invalid", reason="invalid_area_code")
_BAD_EXCHANGE = Classification("invalid", reason="invalid_exchange_code")
_KEPT_TRUNK = Classification("invalid", reason="invalid_trunk_prefix")
_BAD_ZONE = Classification("invalid", reason="invalid_leading_digit")


def _format(value: str, literal: int) -> str:
    """The value with every digit after ``literal`` characters as ``9``."""
    return value[:literal] + _DIGIT.sub("9", value[literal:])


def _nanp(value: str) -> Classification | None:
    found = _NANP.fullmatch(value)
    if found is None:
        return None
    area = found["area"] or found["parenthesized"]
    if area[0] in "01":
        return _BAD_AREA
    if found["exchange"][0] in "01":
        return _BAD_EXCHANGE
    literal = found.end("prefix") if found["prefix"] else 0
    return Classification("matched", format=_format(value, literal), value="nanp")


def _fr(value: str) -> Classification | None:
    found = _FR_NATIONAL.fullmatch(value)
    if found is not None:
        literal = 1
    else:
        found = _FR_INTERNATIONAL.fullmatch(value)
        if found is None:
            return _KEPT_TRUNK if _FR_KEPT_TRUNK.fullmatch(value) else None
        literal = found.end("trunk") if found["trunk"] else found.end("prefix")
    if found["zone"] == "0":
        return _BAD_ZONE
    return Classification("matched", format=_format(value, literal), value="fr")


_REGIONS = {"nanp": _nanp, "fr": _fr}


class PhoneDetector(Detector):
    id = "phone"
    family = "contact"
    sensitive = True

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.regions = tuple(settings.get("regions", DEFAULT_REGIONS))
        self._readers = tuple(_REGIONS[region] for region in self.regions)

    def classify(self, value: str) -> Classification | None:
        # Exact cheap rejections, cheaper than a shape signature.
        if (
            not MIN_LENGTH <= len(value) <= MAX_LENGTH
            or value[0] not in _FIRST
            or not "0" <= value[-1] <= "9"
        ):
            return None
        digits = value.translate(_SYNTAX)
        if not (
            MIN_DIGITS <= len(digits) <= MAX_DIGITS
            and digits.isascii()
            and digits.isdigit()
        ):
            return None
        invalid = None
        for reader in self._readers:
            found = reader(value)
            if found is not None:
                if found.state == "matched":
                    return found
                invalid = invalid or found
        if invalid is not None and len(digits) == len(value):
            return None  # digits only carry no phone syntax
        return invalid

    def accumulator(self) -> PhoneAccumulator:
        return PhoneAccumulator(self.regions)


class PhoneAccumulator(DetectorAccumulator):
    __slots__ = ("regions",)

    def __init__(self, regions: tuple[str, ...]) -> None:
        self.regions = dict.fromkeys(sorted(regions), 0)

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            self.regions[classification.value] += count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {"regions": dict(self.regions)}
