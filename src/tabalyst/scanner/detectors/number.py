"""Number detector (design 12.10): the strict rule, then decimal conventions.

The strict rule of the current engine applies first: optional sign, digits
without leading zeros, optional dot decimal, optional exponent. A strict
integer matches under any convention; strict decimals and exponents belong to
the ``dot`` convention. Values the strict rule rejects are read under each
enabled convention, with digits on both sides of the decimal separator and
thousands grouped by three with one separator:

- ``dot``: decimal ``.``, thousands ``,`` or a space (U+0020, U+00A0, U+202F);
- ``comma``: decimal ``,``, thousands ``.`` or a space.

A value read differently by two conventions, such as ``1,234``, is ambiguous
unless ``ambiguous_convention`` resolves it. Formats are named like
spreadsheet number formats: ``0``, ``0.0``, ``0E0``, ``#,##0.0``, ``0,0``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal

from tabalyst.scanner.detectors.base import (
    AmbiguityAccumulator,
    Classification,
    Detector,
)
from tabalyst.scanner.measures import UNCONVERTIBLE, decimal_or_unconvertible

_STRICT_INTEGER = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
_STRICT_NUMBER = re.compile(
    r"[+-]?(?:(?:0|[1-9][0-9]*)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)
_SPACES = "   "
_CONVENTIONS = {"dot": (".", "," + _SPACES), "comma": (",", "." + _SPACES)}

# Characters of every accepted value: an exact, cheap rejection.
_CHARACTERS = re.compile("[-+.]?[0-9.][0-9.,eE+   -]*")
# The first character of every value that ``_CHARACTERS`` accepts.
_FIRST = frozenset("+-.0123456789")

INTEGER_FORMATS = frozenset(
    {"0"} | {f"#{separator}##0" for separator in ",." + _SPACES}
)


def _convention_pattern(decimal: str, thousands: str) -> re.Pattern[str]:
    return re.compile(
        r"(?P<sign>[+-]?)(?:"
        rf"(?P<grouped>[1-9][0-9]{{0,2}}(?P<t>[{re.escape(thousands)}])[0-9]{{3}}"
        r"(?:(?P=t)[0-9]{3})*)"
        r"|(?P<plain>0|[1-9][0-9]*))"
        rf"(?:{re.escape(decimal)}(?P<fraction>[0-9]+))?"
    )


_PATTERNS = {
    name: _convention_pattern(decimal, thousands)
    for name, (decimal, thousands) in _CONVENTIONS.items()
}


def _integer(text: str) -> int | Decimal:
    try:
        return int(text)
    except ValueError:  # beyond the digits Python converts
        return decimal_or_unconvertible(text)


def _read(convention: str, text: str) -> tuple[object, str] | None:
    """Value and format of ``text`` under one convention, when it has a
    separator of that convention."""
    match = _PATTERNS[convention].fullmatch(text)
    if match is None:
        return None
    grouped, fraction = match["grouped"], match["fraction"]
    if grouped is None and fraction is None:
        return None  # a strict integer
    decimal = _CONVENTIONS[convention][0]
    if grouped is not None:
        digits = grouped.replace(match["t"], "")
        label = f"#{match['t']}##0"
    else:
        digits = match["plain"]
        label = "0"
    if fraction is None:
        return _integer(match["sign"] + digits), label
    number = decimal_or_unconvertible(f"{match['sign']}{digits}.{fraction}")
    return number, f"{label}{decimal}0"


def is_integer_format(format_name: str | None) -> bool:
    return format_name in INTEGER_FORMATS


class NumberDetector(Detector):
    id = "number"
    family = "number"
    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.conventions = tuple(settings.get("conventions", ("dot", "comma")))
        self.dot = "dot" in self.conventions
        self.comma = "comma" in self.conventions
        self.resolution = settings.get("ambiguous_convention")

    def classify(self, value: str) -> Classification | None:
        if _CHARACTERS.fullmatch(value) is None:
            return None
        if _STRICT_INTEGER.fullmatch(value):
            return Classification("matched", format="0", value=_integer(value))
        if self.dot and _STRICT_NUMBER.fullmatch(value):
            # The strict rule wins. A decimal point is evidence of the dot
            # convention only when no other convention reads the value.
            # With one dot, the comma convention reads a strict decimal only
            # as a thousands group: three digits after the dot.
            evidence = "." in value and not (
                self.comma
                and value[-4:-3] == "."
                and _read("comma", value) is not None
            )
            return Classification(
                "matched",
                format="0E0" if "e" in value or "E" in value else "0.0",
                value=decimal_or_unconvertible(value),
                convention="dot" if evidence else None,
            )
        readings = {
            convention: reading
            for convention in self.conventions
            if (reading := _read(convention, value)) is not None
        }
        if not readings:
            return None
        if len(readings) == 1:
            ((convention, (number, label)),) = readings.items()
            return Classification(
                "matched", format=label, value=number, convention=convention
            )
        values = {
            number if number is UNCONVERTIBLE else Decimal(number)
            for number, _ in readings.values()
        }
        if len(values) == 1:
            number, label = readings[self.conventions[0]]
            return Classification("matched", format=label, value=number)
        candidates = tuple(sorted(label for _, label in readings.values()))
        if self.resolution is not None:
            number, label = readings[self.resolution]
            return Classification(
                "matched", format=label, value=number, candidates=candidates
            )
        return Classification("ambiguous", candidates=candidates)

    def classify_many(self, values: Sequence[str]) -> list[Classification | None]:
        """``classify`` of each value: values that cannot start a number are
        rejected, and strict integers of ASCII digits read, without a call."""
        classify = self.classify
        first = _FIRST
        results: list[Classification | None] = []
        append = results.append
        for value in values:
            if value[:1] not in first:
                append(None)
            elif (
                value.isdigit()
                and value.isascii()
                and (value[0] != "0" or len(value) == 1)
            ):
                append(Classification("matched", "0", (), None, _integer(value)))
            else:
                append(classify(value))
        return results

    def accumulator(self) -> AmbiguityAccumulator:
        resolution = (
            None
            if self.resolution is None
            else {"convention": self.resolution, "source": "config"}
        )
        # Evidence only means something when both readings exist.
        readings = list(self.conventions) if len(self.conventions) == 2 else []
        return AmbiguityAccumulator(readings, resolution)
