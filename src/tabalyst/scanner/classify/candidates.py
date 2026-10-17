# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Candidate types a field offers from its detectors, its measures and its technical type.

Gathering only: ranking and conflicts are decided in ``rules.py`` (contract
``docs/dev/report/summary-table.md`` 3.5, steps 3 to 6). The credible detectors
are the ones of ``interpretations.candidates`` (a share of the eligible values
at or above ``detection.minimum_share``), not only ``interpretations.primary``,
which exists only when exactly one detector qualifies.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tabalyst.scanner.classify.models import (
    Basis,
    ClassificationEvidence,
    ClassificationScope,
    EvidenceRole,
)

if TYPE_CHECKING:
    from tabalyst.scanner.classify.names import NameHint
    from tabalyst.scanner.models import FieldResult

# The detectors whose id is the type: they outrank Enum, Text and the numeric
# fallbacks. The detectors ``number``, ``date`` and ``boolean`` are the technical
# type itself, ``enumeration`` is the Enum, and a configured ``pattern:<id>`` is
# not a catalogue type.
DETECTOR_TYPES = {
    "currency": ("numeric", "currency"),
    "percentage": ("numeric", "percentage"),
    "quantity": ("numeric", "quantity"),
    "email": ("contact", "email"),
    "phone": ("contact", "phone"),
    "postal_code": ("geographic", "postal_code"),
    "url": ("web_network", "url"),
    "ip_address": ("web_network", "ip_address"),
    "uuid": ("web_network", "uuid"),
}
# Both kinds of date-time are the Datetime type: the time zone is a fact of the
# column, not a second type.
TEMPORAL_TYPES = {
    "date": "date",
    "datetime_naive": "datetime",
    "datetime_aware": "datetime",
    "time": "time",
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """A type the values support, with the facts that support it."""

    family: str
    type: str
    basis: Basis
    evidence: tuple[ClassificationEvidence, ...]

    @property
    def pair(self) -> tuple[str, str]:
        return self.family, self.type


def credible_detectors(field: FieldResult) -> frozenset[str]:
    """Ids of the detectors that reached the minimum share of the eligible values."""
    return frozenset(item.detector for item in field.interpretations.candidates)


def present_scope(count: int) -> ClassificationScope:
    """An exact fact about all the present values."""
    return ClassificationScope(
        population="present_values", of=count, partial=False, accuracy="exact"
    )


def technical_evidence(field: FieldResult) -> ClassificationEvidence:
    """The technical type of the field as supporting evidence."""
    return ClassificationEvidence(
        source="technical_type",
        id=field.technical_type.type,
        role="supports",
        scope=present_scope(field.values.count),
    )


def name_evidence(hint: NameHint, role: EvidenceRole) -> ClassificationEvidence:
    """A name rule as evidence: it belongs to the whole field, not to its values."""
    scope = ClassificationScope(
        population="positions", of=None, partial=False, accuracy="exact"
    )
    return ClassificationEvidence(
        source="name_rule", id=hint.rule, role=role, scope=scope
    )


def detector_evidence(field: FieldResult, detector_id: str) -> ClassificationEvidence:
    """The coverage of a complete detector as evidence.

    An adaptive detector that left values untested only gives a lower bound of
    its matches, so its scope is partial.
    """
    for result in field.detectors:
        if result.id == detector_id and result.status == "complete":
            coverage = result.coverage
            partial = coverage.not_tested > 0
            scope = ClassificationScope(
                population="eligible",
                of=coverage.eligible,
                partial=partial,
                accuracy="lower_bound" if partial else "exact",
            )
            break
    else:  # a credible detector is complete: the scope is then never unknown
        scope = ClassificationScope(
            population="eligible", of=None, partial=False, accuracy="exact"
        )
    return ClassificationEvidence(
        source="detector", id=detector_id, role="supports", scope=scope
    )


def detector_candidates(field: FieldResult, credible: frozenset[str]) -> list[Candidate]:
    """The types of the credible detectors that carry a type, in a fixed order."""
    return [
        Candidate(family, type_, "inferred", (detector_evidence(field, detector_id),))
        for detector_id, (family, type_) in sorted(DETECTOR_TYPES.items())
        if detector_id in credible
    ]


def boolean_candidate(field: FieldResult, credible: frozenset[str]) -> Candidate | None:
    """Boolean: a two-state technical type, or the textual ``boolean`` detector.

    Two categories never make a Boolean by themselves (``M``/``F`` stays Enum).
    """
    evidence: list[ClassificationEvidence] = []
    if field.technical_type.type == "boolean":
        evidence.append(technical_evidence(field))
    if "boolean" in credible:
        evidence.append(detector_evidence(field, "boolean"))
    if not evidence:
        return None
    # The technical type decides when it is boolean; the detector adds to it.
    basis: Basis = "fallback" if field.technical_type.type == "boolean" else "inferred"
    return Candidate("categorical", "boolean", basis, tuple(evidence))


def temporal_candidates(
    field: FieldResult, credible: frozenset[str]
) -> tuple[list[Candidate], list[tuple[str, str]]]:
    """The temporal types of the field and the ones left aside as minorities.

    A technical ``date`` is a Date. Otherwise a credible ``date`` detector reads
    the kinds the Scan measured: the type with the most values is kept, a tie
    leaves several candidates (the caller treats them as a conflict), and the
    other types go to the alternatives. Without a complete measure no type is
    guessed.
    """
    detected = "date" in credible
    if field.technical_type.type == "date":
        evidence = [technical_evidence(field)]
        if detected:
            evidence.append(detector_evidence(field, "date"))
        return [Candidate("temporal", "date", "fallback", tuple(evidence))], []
    if not detected or field.temporal.status != "complete":
        return [], []
    counts: Counter[str] = Counter()
    for kind in field.temporal.value.kinds:
        counts[TEMPORAL_TYPES[kind.kind]] += kind.count
    if not counts:
        return [], []
    top = max(counts.values())
    measure = ClassificationEvidence(
        source="measure",
        id="temporal.kinds",
        role="supports",
        scope=present_scope(field.temporal.value.count),
    )
    detector = detector_evidence(field, "date")
    winners = [
        Candidate("temporal", name, "inferred", (detector, measure))
        for name in sorted(counts)
        if counts[name] == top
    ]
    minorities = [("temporal", name) for name in sorted(counts) if counts[name] != top]
    return winners, minorities
