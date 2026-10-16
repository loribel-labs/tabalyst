# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Decision of the family and type of a field from the blocks the Scan computed.

A pure function of the facts of the field and of the dataset context, so the
same Scan gives the same result with one or several workers. This foundation
decides the fallback of the technical type and the length of a Text; the types
carried by detectors, names and identifiers come in later lots (contract
``docs/dev/report/summary-table.md`` 3.5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tabalyst.scanner.classify.catalog import CATALOGUE_VERSION, VERSION_NAMES
from tabalyst.scanner.classify.models import (
    Classification,
    ClassificationAlternative,
    ClassificationEvidence,
    ClassificationScope,
)
from tabalyst.scanner.config import ClassificationSettings

if TYPE_CHECKING:
    from tabalyst.scanner.models import FieldResult

# The technical type is the whole decision of these: the detectors refine them
# in a later lot.
TECHNICAL_FALLBACKS = {
    "integer": ("numeric", "integer"),
    "number": ("numeric", "number"),
    "boolean": ("categorical", "boolean"),
    "date": ("temporal", "date"),
}
TEXT_TYPES = (
    "text_very_short",
    "text_short",
    "text_medium",
    "text_long",
    "text_very_long",
)


@dataclass(frozen=True, slots=True)
class ClassifyContext:
    """What the decision reads besides the field: the Text bounds of the scan."""

    bounds: ClassificationSettings


def classification_versions() -> tuple[int, ...]:
    """Versions of the rules that classify, in the order of ``VERSION_NAMES``.

    Read through this function and not imported as constants, like the versions
    of the pattern discovery, so the identity of a Scan and its warning see one
    value.
    """
    return (CATALOGUE_VERSION,)


def version_record() -> dict[str, int]:
    """``classification_versions()`` by name, as the Scan records it."""
    return dict(zip(VERSION_NAMES, classification_versions(), strict=True))


def _scope(present: int, *, partial: bool = False) -> ClassificationScope:
    return ClassificationScope(
        population="present_values", of=present, partial=partial, accuracy="exact"
    )


def _technical(field: FieldResult) -> ClassificationEvidence:
    technical = field.technical_type
    return ClassificationEvidence(
        source="technical_type",
        id=technical.type,
        role="supports",
        scope=_scope(field.values.count),
    )


def _result(
    family: str,
    type_: str,
    basis: str,
    state: str,
    evidence: list[ClassificationEvidence],
    alternatives: list[ClassificationAlternative] | None = None,
) -> Classification:
    return Classification.model_validate(
        {
            "family": family,
            "type": type_,
            "basis": basis,
            "state": state,
            "traits": [],
            "evidence": evidence,
            "alternatives": alternatives or [],
            "rule_version": CATALOGUE_VERSION,
        }
    )


# Stands in a field until its blocks are validated and it is classified.
PENDING_CLASSIFICATION = _result("other", "unknown", "fallback", "undetermined", [])


def text_type(median: float, bounds: ClassificationSettings) -> str:
    """The Text type of a median length: a median of 5.5 is Short, 20.5 Medium."""
    if median <= bounds.very_short_max_length:
        return TEXT_TYPES[0]
    if median <= bounds.short_max_length:
        return TEXT_TYPES[1]
    if median <= bounds.medium_max_length:
        return TEXT_TYPES[2]
    if median <= bounds.long_max_length:
        return TEXT_TYPES[3]
    return TEXT_TYPES[4]


def _text(field: FieldResult, context: ClassifyContext) -> Classification:
    evidence = [_technical(field)]
    lengths = field.string_lengths
    if lengths.status != "complete" or not lengths.value.count:
        # The maximum never replaces the median (contract 3.6): the length of
        # the Text stays undetermined and says why.
        reason = f"string_lengths_{lengths.status}"
        return _result(
            "text",
            "text",
            "fallback",
            "undetermined",
            evidence,
            [
                ClassificationAlternative(family="text", type=code, reason=reason)
                for code in TEXT_TYPES
            ],
        )
    evidence.append(
        ClassificationEvidence(
            source="measure",
            id="string_lengths.median_length",
            role="supports",
            scope=_scope(lengths.value.count),
        )
    )
    return _result(
        "text",
        text_type(lengths.value.median_length, context.bounds),
        "inferred",
        "established",
        evidence,
    )


def classify_field(field: FieldResult, context: ClassifyContext) -> Classification:
    """The classification of a field.

    Without a present value the field is ``other/empty``; a ``mixed`` technical
    type is ``other/mixed``; a ``text`` is classified by the exact median of its
    analytical lengths. The other technical types give their fallback type.
    """
    technical = field.technical_type.type
    if technical == "empty" or not field.values.count:
        return _result("other", "empty", "fallback", "established", [_technical(field)])
    if technical == "mixed":
        return _result("other", "mixed", "fallback", "established", [_technical(field)])
    if technical == "text":
        return _text(field, context)
    family, type_ = TECHNICAL_FALLBACKS[technical]
    return _result(family, type_, "fallback", "established", [_technical(field)])
