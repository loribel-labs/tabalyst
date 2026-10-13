# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Phone number detector (``docs/dev/scan/detectors.md``).

North American Numbering Plan (``nanp``: Canada, the United States and the
other NANP countries) and France (``fr``). Syntax only: numbers are never
checked against assigned ranges (EF32). Phone numbers identify people, so the
detector is sensitive: its fields are masked by default (design 12.8).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.detectors.keys import from_pairs, keys_block
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

# Meaning of each level of the keys: the region, then the area code of a North
# American number or the zone of a French one.
KEY_LEVELS = ("region", "area")

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


# The classes of a phone number (design 20.35): the zone of a French number, which
# tells a region (1 to 5) or a mobile (6, 7) or a special line (8, 9), and for a
# North American number whether it is toll free, premium or geographic. The
# area code of a North American number is never part of a class.
_NANP_TOLL_FREE = frozenset({"800", "833", "844", "855", "866", "877", "888"})
PHONE_CLASSES = (
    *(f"fr_0{zone}" for zone in range(1, 10)),
    "nanp_geographic",
    "nanp_toll_free",
    "nanp_premium",
)


def phone_class(value: str, region: str) -> str | None:
    """The class of a number the detector matched in ``region`` (``fr`` or
    ``nanp``), one of ``PHONE_CLASSES``, or ``None`` for a text it does not read."""
    if region == "fr":
        found = _FR_NATIONAL.fullmatch(value) or _FR_INTERNATIONAL.fullmatch(value)
        return None if found is None else f"fr_0{found['zone']}"
    if region == "nanp":
        found = _NANP.fullmatch(value)
        if found is None:
            return None
        area = found["area"] or found["parenthesized"]
        if area in _NANP_TOLL_FREE:
            return "nanp_toll_free"
        return "nanp_premium" if area == "900" else "nanp_geographic"
    return None


class PhoneDetector(Detector):
    id = "phone"
    version = 2
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

    def classify_many(self, values: Sequence[str]) -> list[Classification | None]:
        classify = self.classify
        return [
            classify(value)
            if MIN_LENGTH <= len(value) <= MAX_LENGTH
            and value[0] in _FIRST
            and "0" <= value[-1] <= "9"
            else None
            for value in values
        ]

    def accumulator(self) -> PhoneAccumulator:
        return PhoneAccumulator(self.regions)


class PhoneAccumulator(DetectorAccumulator):
    __slots__ = ("areas", "regions")
    ignores_unmatched = True

    def __init__(self, regions: tuple[str, ...]) -> None:
        self.regions = dict.fromkeys(sorted(regions), 0)
        # Per region, the area code (``nanp``) or the zone (``fr``) of the
        # numbers; a few hundred keys at most, so no limit is needed.
        self.areas: dict[str, dict[str, int]] = {region: {} for region in self.regions}

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            region: str = classification.value  # type: ignore[assignment]
            self.regions[region] += count
            digits = value.translate(_SYNTAX)
            # The last digits are the same whatever the prefix and the trunk
            # zero: ``(514) 555-0123`` and ``+1 514 555 0123`` count together.
            area = digits[-10:-7] if region == "nanp" else "0" + digits[-9]
            areas = self.areas[region]
            areas[area] = areas.get(area, 0) + count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        roots = from_pairs({region: seen for region, seen in self.areas.items() if seen})
        return {
            "regions": dict(self.regions),
            "keys": keys_block(roots, KEY_LEVELS, gate),
        }
