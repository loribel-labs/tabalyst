"""Currency amount detector (``docs/dev/scan/detectors.md``).

An amount needs a currency marker, a symbol or an ISO 4217 code, before or
after its number part: a bare number is the number detector's, not evidence
of money. The number part follows the number detector (``amount.py``).
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
from tabalyst.scanner.exposure import ExposureGate

SYMBOLS = ("CA$", "C$", "US$", "$", "€", "£", "¥")
# ISO 4217 list one on 2026-01-01, without funds, precious metals, ``XXX``
# and ``XTS``, plus codes replaced since 2023 but still found in data (ANG,
# BGN, HRK, SLL, ZWL).
_CODES = """
    AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND
    BOB BRL BSD BTN BWP BYN BZD CAD CDF CHF CLP CNY COP CRC CUP CVE CZK DJF
    DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD
    HNL HRK HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW
    KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU
    MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR
    PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD
    SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU
    UZS VED VES VND VUV WST XAF XCD XCG XOF XPF YER ZAR ZMW ZWG ZWL
"""
CODES = frozenset(_CODES.split())

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_SYMBOL_CHARACTERS = "$€£¥"
_MARKER = "|".join(re.escape(symbol) for symbol in SYMBOLS) + "|[A-Z]{3}"
_SPACE = f"[{SPACES}]?"
_PREFIX = re.compile(
    rf"(?P<sign>[+-]?)(?P<marker>{_MARKER})(?P<space>{_SPACE})"
    rf"(?P<inner>[+-]?)(?P<body>{NUMBER_PART})"
)
_SUFFIX = re.compile(
    rf"(?P<sign>[+-]?)(?P<body>{NUMBER_PART})(?P<space>{_SPACE})(?P<marker>{_MARKER})"
)
# Exact cheap rejection: a candidate starts or ends with a marker, a sign or
# an accounting parenthesis.
_FIRST = frozenset("+-(" + _SYMBOL_CHARACTERS + _UPPER)
_LAST = frozenset(")" + _SYMBOL_CHARACTERS + _UPPER)


def split(value: str) -> tuple[str, str, str, str, str] | None:
    """``(sign, marker, body, prefix, suffix)`` of a candidate, where
    ``prefix`` and ``suffix`` are the format's affixes, or ``None``."""
    negative = value[0] == "(" and value[-1] == ")"
    text = value[1:-1] if negative else value
    if not text:
        return None
    match = None
    if text[0] in _FIRST:
        match = _PREFIX.fullmatch(text)
    if match is not None:
        sign, inner = match["sign"], match["inner"]
        if sign and inner:
            return None
        sign = sign or inner
        prefix, suffix = match["marker"] + match["space"], ""
    else:
        if text[-1] not in _LAST or (match := _SUFFIX.fullmatch(text)) is None:
            return None
        sign = match["sign"]
        prefix, suffix = "", match["space"] + match["marker"]
    marker = match["marker"]
    if len(marker) == 3 and marker[-1] != "$" and marker not in CODES:
        return None
    if negative:
        if sign:
            return None
        sign = "-"
    return sign, marker, match["body"], prefix, suffix


def marker(value: str) -> str | None:
    """The currency marker of a candidate value, or ``None``."""
    parts = split(value)
    return None if parts is None else parts[1]


class CurrencyDetector(Detector):
    id = "currency"
    family = "monetary"

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.reader = AmountReader(settings, "invalid_amount")

    def classify(self, value: str) -> Classification | None:
        if value[:1] not in _FIRST and value[-1:] not in _LAST:
            return None
        parts = split(value)
        if parts is None:
            return None
        sign, _, body, prefix, suffix = parts
        return self.reader.read(sign, body, prefix, suffix)

    def accumulator(self) -> CurrencyAccumulator:
        return CurrencyAccumulator(self.reader)


class CurrencyAccumulator(AmountAccumulator):
    __slots__ = ("currencies",)

    def __init__(self, reader: AmountReader) -> None:
        super().__init__(reader)
        self.currencies: dict[str, int] = {}

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        super().add(value, classification, count)
        if classification is not None and classification.state != "invalid":
            name = marker(value)
            self.currencies[name] = self.currencies.get(name, 0) + count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        # Markers come from a fixed list: they carry no value of the field.
        return {
            **super().details(gate),
            "currencies": dict(sorted(self.currencies.items())),
        }
