# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Decision of the family and type of a field from the blocks the Scan computed.

A pure function of the facts of the field and of the dataset context, so the
same Scan gives the same result with one or several workers. It decides the
types the values support (detectors, technical type, cardinality), the fallback
of the technical type and the length of a Text, then reads the name of the field
to reinforce, break a tie between or weaken those types, never to create one. A
text or a whole number with an identifier name becomes an ID or a Unique ID
(``identifiers.py``). Contract ``docs/dev/report/summary-table.md`` 3.5, 3.7 and 5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tabalyst.scanner.classify.candidates import (
    Candidate,
    boolean_candidate,
    credible_detectors,
    detector_candidates,
    detector_evidence,
    name_evidence,
    present_scope,
    technical_evidence,
    temporal_candidates,
)
from tabalyst.scanner.classify.catalog import (
    CATALOGUE_VERSION,
    VERSION_NAMES,
    is_catalogued,
)
from tabalyst.scanner.classify.identifiers import field_traits, with_role
from tabalyst.scanner.classify.models import (
    Classification,
    ClassificationAlternative,
    ClassificationEvidence,
    EvidenceRole,
)
from tabalyst.scanner.classify.names import (
    NAME_RULES_VERSION,
    NameHint,
    break_tie,
    field_name_parts,
    name_hints,
)
from tabalyst.scanner.config import ClassificationSettings

if TYPE_CHECKING:
    from tabalyst.scanner.models import (
        DatasetResult,
        DerivedPatterns,
        FieldPatterns,
        FieldResult,
    )

# The technical type is the whole decision of these when no detector competes
# with it.
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
    """What the decision reads besides the field: the Text bounds of the scan and
    the records of its dataset the scan left out (the scope of a Unique ID)."""

    bounds: ClassificationSettings
    excluded_records: int = 0


def classification_versions() -> tuple[int, ...]:
    """Versions of the rules that classify, in the order of ``VERSION_NAMES``.

    Read through this function and not imported as constants, like the versions
    of the pattern discovery, so the identity of a Scan and its warning see one
    value.
    """
    return (CATALOGUE_VERSION, NAME_RULES_VERSION)


def rule_version() -> int:
    """The ``rule_version`` of a classification: one integer for both versions.

    Positional so it can be read back (4002 is catalogue 4, name rules 2) and
    strictly increases whenever either version does. The name rules stay below
    1000 versions.
    """
    return CATALOGUE_VERSION * 1000 + NAME_RULES_VERSION


def version_record() -> dict[str, int]:
    """``classification_versions()`` by name, as the Scan records it."""
    return dict(zip(VERSION_NAMES, classification_versions(), strict=True))


def _result(
    family: str,
    type_: str,
    basis: str,
    state: str,
    evidence: list[ClassificationEvidence],
    alternatives: list[ClassificationAlternative] | None = None,
    traits: list[str] | None = None,
) -> Classification:
    return Classification.model_validate(
        {
            "family": family,
            "type": type_,
            "basis": basis,
            "state": state,
            "traits": traits or [],
            "evidence": evidence,
            "alternatives": alternatives or [],
            "rule_version": rule_version(),
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


def _text(
    field: FieldResult, context: ClassifyContext, traits: list[str]
) -> Classification:
    evidence = [technical_evidence(field)]
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
            [_alternative("text", code, reason) for code in TEXT_TYPES],
            traits,
        )
    evidence.append(
        ClassificationEvidence(
            source="measure",
            id="string_lengths.median_length",
            role="supports",
            scope=present_scope(lengths.value.count),
        )
    )
    return _result(
        "text",
        text_type(lengths.value.median_length, context.bounds),
        "inferred",
        "established",
        evidence,
        traits=traits,
    )


def _alternative(family: str, type_: str, reason: str) -> ClassificationAlternative:
    return ClassificationAlternative(family=family, type=type_, reason=reason)


def _constant(field: FieldResult) -> Candidate | None:
    """One distinct analytical value among at least two present occurrences.

    The distinct count must be exact for the analytical domain: a limited or
    estimated cardinality never proves a constant. The threshold of two is the
    one of the ``constant_column`` observation.
    """
    # Imported here: the Scan models import this package and ``quality`` imports
    # them.
    from tabalyst.scanner.quality import analytical_distinct

    if field.values.count < 2 or analytical_distinct(field) != 1:
        return None
    evidence = ClassificationEvidence(
        source="measure",
        id="values.cardinality",
        role="supports",
        scope=present_scope(field.values.count),
    )
    return Candidate("categorical", "constant", "inferred", (evidence,))


def _context(candidates: list[Candidate]) -> list[ClassificationEvidence]:
    """The facts of candidates that are not the result: context, not support."""
    return [
        item.model_copy(update={"role": "context"})
        for candidate in sorted(candidates, key=lambda item: item.pair)
        for item in candidate.evidence
    ]


def _conflict(
    contenders: list[Candidate],
    numeric: Candidate | None,
    traits: list[str],
    aside: list[tuple[Candidate, str]] | None = None,
) -> Classification:
    """The explicit fallback when credible types cannot be told apart.

    Never the first of the registry. A conflict that includes a numeric
    technical type keeps that type, undetermined (five digits are read by
    ``number`` and by ``postal_code``); a conflict between types of the values
    is ``other/unknown``. Every contender is an alternative and its evidence is
    context, not support. ``aside`` are the types a name already set aside, with
    the reason.
    """
    ordered = sorted(contenders, key=lambda item: item.pair)
    kept_aside = sorted(aside or [], key=lambda item: item[0].pair)
    evidence = _context(ordered) + _context([item for item, _ in kept_aside])
    alternatives = [
        _alternative(item.family, item.type, "conflicting_candidates")
        for item in ordered
    ] + [_alternative(item.family, item.type, why) for item, why in kept_aside]
    family, type_ = numeric.pair if numeric is not None else ("other", "unknown")
    return _result(
        family, type_, "fallback", "undetermined", evidence, alternatives, traits
    )


def _settle(
    contenders: list[Candidate],
    numeric: Candidate | None,
    traits: list[str],
    hints: tuple[NameHint, ...],
) -> Classification:
    """Credible types the values cannot separate, with the name's say.

    A name that leaves one type wins it as a ``candidate``: the result rests on a
    name plus compatible values, not on the values alone. A name that only
    narrows the choice leaves a conflict among what remains, and a name that
    changes nothing leaves the whole conflict.
    """
    by_pair = {item.pair: item for item in contenders}
    verdict = break_tie(list(by_pair), hints)
    aside = [(by_pair[pair], "weakened_by_name") for pair in verdict.removed] + [
        (by_pair[pair], "outranked_by_name") for pair in verdict.outranked
    ]
    if verdict.winner is None:
        remaining = [by_pair[pair] for pair in verdict.remaining]
        return _conflict(
            remaining, numeric if numeric in remaining else None, traits, aside
        )
    winner = by_pair[verdict.winner]
    return _result(
        winner.family,
        winner.type,
        "inferred",
        "candidate",
        list(winner.evidence) + _context([item for item, _ in aside]),
        [_alternative(item.family, item.type, why) for item, why in aside],
        traits,
    )


def _technical_fallback(field: FieldResult, traits: list[str]) -> Classification:
    technical = field.technical_type.type
    if technical == "mixed":
        return _result(
            "other",
            "mixed",
            "fallback",
            "established",
            [technical_evidence(field)],
            traits=traits,
        )
    family, type_ = TECHNICAL_FALLBACKS[technical]
    return _result(
        family,
        type_,
        "fallback",
        "established",
        [technical_evidence(field)],
        traits=traits,
    )


def classify_field(field: FieldResult, context: ClassifyContext) -> Classification:
    """The classification of a field (contract 3.5).

    Without a present value the field is ``other/empty``. The candidates are the
    types the values support: the credible detectors (not only the primary
    interpretation), the technical type and the cardinality. A detector type
    outranks the numeric fallbacks, Enum and Text. Two credible types that
    cannot be told apart are separated by the name of the field when it can;
    otherwise they give the explicit fallback and both are listed in
    ``alternatives``. Without a candidate the technical type decides:
    ``other/mixed``, a numeric type, or a Text by its median length. The name
    never creates a type: it adds evidence to the result and lists the types it
    suggests that the values do not support as ``name_only`` alternatives. The
    one role a name and compatible values do create is the identifier (ID, Unique
    ID), which replaces a Text or an Integer and no other type. The traits
    ``observed_unique`` and ``first_column`` are facts, never a proof of a role.
    """
    hints = name_hints(field_name_parts(field))
    result = with_role(
        _from_values(field, context, hints), hints, field, context.excluded_records
    )
    result = _with_names(result, hints, field)
    traits = [item for item in field_traits(field) if item not in result.traits]
    if traits:
        result = result.model_copy(update={"traits": [*result.traits, *traits]})
    return result


def _from_values(
    field: FieldResult, context: ClassifyContext, hints: tuple[NameHint, ...]
) -> Classification:
    technical = field.technical_type.type
    if technical == "empty" or not field.values.count:
        return _result(
            "other", "empty", "fallback", "established", [technical_evidence(field)]
        )
    credible = credible_detectors(field)
    typed = detector_candidates(field, credible)
    temporal, minorities = temporal_candidates(field, credible)
    typed += temporal
    boolean = boolean_candidate(field, credible)
    if boolean is not None:
        typed.append(boolean)
    numeric = None
    if technical in ("integer", "number"):
        family, type_ = TECHNICAL_FALLBACKS[technical]
        numeric = Candidate(family, type_, "fallback", (technical_evidence(field),))
    constant = _constant(field)
    # A single value is the type of a column nothing else types, and a trait of
    # one that has a type.
    traits = ["constant"] if constant is not None and (typed or numeric) else []

    # A numeric technical type that a specific detector also reads is one more
    # contender, not a loser: only the names can separate them (lot R2).
    contenders = typed + ([numeric] if typed and numeric is not None else [])
    if len(contenders) > 1:
        return _settle(contenders, numeric, traits, hints)

    losers: list[ClassificationAlternative] = []
    enum_credible = "enumeration" in credible
    if contenders:
        winner = contenders[0]
        reason = f"outranked_by_{winner.type}"
    elif numeric is not None:
        winner = numeric
        reason = "numeric_type_kept"
    elif constant is not None:
        winner = constant
        reason = "outranked_by_constant"
    elif enum_credible and technical == "text":
        evidence = [detector_evidence(field, "enumeration")]
        return _result("categorical", "enum", "inferred", "established", evidence)
    elif technical == "text":
        return _text(field, context, traits)
    else:
        return _technical_fallback(field, traits)
    if enum_credible:
        losers.append(_alternative("categorical", "enum", reason))
    losers += [_alternative(f, t, "minority_kind") for f, t in minorities]
    return _result(
        winner.family,
        winner.type,
        winner.basis,
        "established",
        list(winner.evidence),
        losers,
        traits,
    )


def _with_names(
    result: Classification, hints: tuple[NameHint, ...], field: FieldResult
) -> Classification:
    """The result with what the name says about it.

    A hint for the result is evidence that supports or contradicts it and never
    changes the type or the state. A hint for a type the result lists as an
    alternative is context. A supported type that is neither is a ``name_only``
    alternative when the technical type allows it: a name alone creates nothing.
    The identifier hints were read by ``identifiers.with_role``, which recorded
    their evidence and alternatives.
    """
    if (result.family, result.type) == ("other", "empty"):
        return result
    evidence = list(result.evidence)
    alternatives = list(result.alternatives)
    listed = {(item.family, item.type) for item in alternatives}
    technical = field.technical_type.type
    for hint in hints:
        if hint.family == "identifier":
            continue  # the role step already decided and recorded it
        role: EvidenceRole | None = None
        if hint.covers(result.family, result.type):
            role = "supports" if hint.polarity == "supports" else "contradicts"
        elif any(hint.covers(*pair) for pair in listed):
            role = "context"
        elif (
            hint.polarity == "supports"
            and hint.type is not None
            and technical in hint.technical
            and is_catalogued(hint.family, hint.type)
        ):
            alternatives.append(_alternative(hint.family, hint.type, "name_only"))
            listed.add((hint.family, hint.type))
        if role is not None and (item := name_evidence(hint, role)) not in evidence:
            evidence.append(item)
    if len(evidence) == len(result.evidence) and len(alternatives) == len(
        result.alternatives
    ):
        return result
    return result.model_copy(
        update={"evidence": evidence, "alternatives": alternatives}
    )


def pattern_traits(entry: FieldPatterns | None) -> list[str]:
    """The traits ``single_pattern`` and ``multiple_patterns`` of one field.

    Read from ``derived.patterns`` once it is computed (it is computed after the
    fields), without recalculating anything. A single pattern needs a complete
    discovery that left no value outside its patterns.
    """
    if entry is None or entry.status != "complete":
        return []
    count = len(entry.all_patterns())
    if count > 1:
        return ["multiple_patterns"]
    if count == 1 and entry.outside_patterns() == (0, 0):
        return ["single_pattern"]
    return []


def with_pattern_traits(
    datasets: list[DatasetResult], patterns: DerivedPatterns | None
) -> list[DatasetResult]:
    """The datasets with the pattern traits added to their classifications.

    The discovery runs after the fields are built, so its traits come in a
    second step. The datasets are returned as they are when it is off.
    """
    if patterns is None:
        return datasets
    entries = {(item.dataset, item.field): item for item in patterns.fields}
    updated = []
    for dataset in datasets:
        fields = []
        for item in dataset.fields:
            added = pattern_traits(entries.get((dataset.id, item.id)))
            if added:
                classification = item.classification.model_copy(
                    update={"traits": [*item.classification.traits, *added]}
                )
                item = item.model_copy(update={"classification": classification})
            fields.append(item)
        updated.append(dataset.model_copy(update={"fields": fields}))
    return updated
