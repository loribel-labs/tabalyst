"""UUID detector (``docs/dev/scan/detectors.md``).

Hyphenated, braced and URN forms of RFC 9562. The version and variant are
counted, never validated: every 128-bit value written in these forms is a
UUID. A UUID identifies a record, not a person, so the detector is not
sensitive.
"""

from __future__ import annotations

import re
from collections import Counter

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.exposure import ExposureGate

# Lengths of the accepted forms: hyphenated, braced and ``urn:uuid:``.
LENGTHS = frozenset({36, 38, 45})
_URN = "urn:uuid:"
_LAYOUT = re.compile(
    r"[A-Za-z0-9]{8}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{12}"
)
_HEX = re.compile(r"[0-9A-Fa-f-]+")
_RFC_VARIANT = frozenset("89ab")
_RFC_VERSIONS = frozenset("12345678")
_NIL = "00000000-0000-0000-0000-000000000000"
_MAX = "ffffffff-ffff-ffff-ffff-ffffffffffff"

_BAD_HEX = Classification("invalid", reason="invalid_hex_digit")


def _version(uuid: str) -> str:
    """The ``versions`` key of a lowercase hyphenated UUID."""
    if uuid == _NIL:
        return "nil"
    if uuid == _MAX:
        return "max"
    version = uuid[14]
    if uuid[19] in _RFC_VARIANT and version in _RFC_VERSIONS:
        return version
    return "other"


class UuidDetector(Detector):
    id = "uuid"
    family = "identifier"

    def classify(self, value: str) -> Classification | None:
        # Exact cheap rejection, cheaper than a shape signature.
        length = len(value)
        if length not in LENGTHS:
            return None
        if length == 36:
            form, uuid = "hyphenated", value
        elif length == 38:
            if value[0] != "{" or value[-1] != "}":
                return None
            form, uuid = "braced", value[1:-1]
        else:
            if value[:9].lower() != _URN:
                return None
            form, uuid = "urn", value[9:]
        if _LAYOUT.fullmatch(uuid) is None:
            return None
        if _HEX.fullmatch(uuid) is None:
            return _BAD_HEX
        lower = uuid.lower()
        if uuid == lower:
            case = ""
        elif uuid == uuid.upper():
            case = "_upper"
        else:
            case = "_mixed"
        return Classification("matched", format=form + case, value=_version(lower))

    def accumulator(self) -> UuidAccumulator:
        return UuidAccumulator()


class UuidAccumulator(DetectorAccumulator):
    __slots__ = ("versions",)
    ignores_unmatched = True

    def __init__(self) -> None:
        self.versions: Counter[str] = Counter()

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            self.versions[classification.value] += count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {"versions": dict(sorted(self.versions.items()))}
