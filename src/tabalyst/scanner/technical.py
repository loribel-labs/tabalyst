"""Technical type (design 9.7): a port of the current inference.

Each analyzable value belongs to one family. Native integers, numbers and
booleans count directly. A string is ``date`` when the date detector matches
it as a calendar date or finds it ambiguous, ``boolean`` when it is ``true``
or ``false`` ignoring case, ``integer`` or ``number`` when the number detector
matches it (``number`` when ambiguous), and ``text`` otherwise. Families are
tried in order ``integer`` (integers), ``number`` (integers and numbers),
``date``, ``boolean`` and ``text``; the first whose share reaches
``types.minimum_confidence`` wins, otherwise ``mixed``.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction

from tabalyst.scanner.detectors.base import Classification
from tabalyst.scanner.detectors.number import is_integer_format
from tabalyst.scanner.models import TechnicalType

FAMILIES = ("integer", "number", "date", "boolean", "text")
_BOOLEAN_WORDS = frozenset({"true", "false"})


def string_family(
    text: str,
    classifications: tuple[object, ...],
    date_index: int | None,
    number_index: int | None,
) -> str:
    if date_index is not None:
        found = classifications[date_index]
        if isinstance(found, Classification) and (
            found.state == "ambiguous"
            or (found.state == "matched" and type(found.value) is date)
        ):
            return "date"
    if len(text) <= 5 and text.casefold() in _BOOLEAN_WORDS:
        return "boolean"
    if number_index is not None:
        found = classifications[number_index]
        if isinstance(found, Classification):
            if found.state == "matched":
                return "integer" if is_integer_format(found.format) else "number"
            if found.state == "ambiguous":
                return "number"
    return "text"


def technical_type(families: dict[str, int], threshold: Fraction) -> TechnicalType:
    total = sum(families.values())
    if not total:
        return TechnicalType(type="empty", confidence=None, counts={}, outside_count=0)
    counts = {family: families[family] for family in FAMILIES if families.get(family)}
    integers = families.get("integer", 0)
    accepted = (
        ("integer", integers),
        ("number", integers + families.get("number", 0)),
        ("date", families.get("date", 0)),
        ("boolean", families.get("boolean", 0)),
        ("text", families.get("text", 0)),
    )
    for family, count in accepted:
        if Fraction(count, total) >= threshold:
            return TechnicalType(
                type=family,
                confidence=round(count / total, 4),
                counts=counts,
                outside_count=total - count,
            )
    return TechnicalType(
        type="mixed",
        confidence=round(max(count for _, count in accepted) / total, 4),
        counts=counts,
        outside_count=None,
    )
