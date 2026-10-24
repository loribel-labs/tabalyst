# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Identifier role (ID, Unique ID) and the traits that never prove it.

A field is an ID only when an identifier name rule fires and its values are
compatible; the role replaces a Text or an Integer and no other type. It is a
Unique ID when, besides, every position of the scanned scope has a value and the
exact analytical distinct count equals the present values (contract
``docs/dev/report/summary-table.md`` 3.4, 3.7 to 3.9). Uniqueness and first
position are traits: without an identifier name they leave a column outside
Identifier.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tabalyst.scanner.classify.candidates import name_evidence, technical_evidence
from tabalyst.scanner.classify.models import (
    Classification,
    ClassificationAlternative,
    ClassificationEvidence,
    ClassificationScope,
    ScopePopulation,
)

if TYPE_CHECKING:
    from tabalyst.scanner.classify.names import NameHint
    from tabalyst.scanner.models import FieldResult

ID: tuple[str, str] = ("identifier", "id")
UNIQUE_ID: tuple[str, str] = ("identifier", "unique_id")
UUID: tuple[str, str] = ("web_network", "uuid")
# Only these technical types can carry the role, with every value inside the
# family of the technical type and two present values at least (3.7).
IDENTIFIABLE_TYPES = ("text", "integer")
MINIMUM_VALUES = 2


def _hint_polarity(hints: tuple[NameHint, ...], polarity: str) -> NameHint | None:
    """The identifier hint of a polarity (the registry keeps one per candidate)."""
    return next(
        (h for h in hints if h.covers(*ID) and h.polarity == polarity), None
    )


def _compatible(field: FieldResult) -> bool:
    technical = field.technical_type
    return (
        technical.type in IDENTIFIABLE_TYPES
        and technical.outside_count == 0
        and field.values.count >= MINIMUM_VALUES
    )


def _replaceable(result: Classification) -> bool:
    """The types a role may replace: a Text of any length, a plain Integer.

    An Integer that a detector also reads (five digits, a postal code) is
    undetermined and the name settles it. A type of a detector, Enum, Constant,
    Number, a temporal type, Boolean or Other keep their type: an identifier
    never overrides a more specific one (3.5 step 5, CA-07). An Integer with a
    single value keeps its ``constant`` trait and no role.
    """
    if "constant" in result.traits:
        return False
    return result.family == "text" or (result.family, result.type) == (
        "numeric",
        "integer",
    )


def observed_unique(field: FieldResult) -> bool:
    """Whether the exact analytical distinct count equals the present values.

    A single value is not uniqueness. A limited or estimated cardinality, or one
    the analytical stages (NFC, trim, whitespace) make smaller, is not.
    """
    # Imported here: the Scan models import this package and ``quality`` imports
    # them.
    from tabalyst.scanner.quality import analytical_distinct

    count = field.values.count
    return count >= MINIMUM_VALUES and analytical_distinct(field) == count


def _first_column(field: FieldResult) -> bool:
    """The first column of a table (CSV, Excel), numbered from 1."""
    from tabalyst.scanner.models import ColumnSegment

    first = field.path[0] if field.path else None
    return isinstance(first, ColumnSegment) and first.column == 1


def field_traits(field: FieldResult) -> list[str]:
    """The traits ``observed_unique`` and ``first_column``, in that order."""
    traits = []
    if observed_unique(field):
        traits.append("observed_unique")
    if _first_column(field):
        traits.append("first_column")
    return traits


def under_array(field: FieldResult) -> bool:
    """Whether the field sits under a JSON array, so one record holds several of its values."""
    from tabalyst.scanner.models import ItemsSegment

    return any(isinstance(item, ItemsSegment) for item in field.path)


def _scope(
    field: FieldResult, population: ScopePopulation, excluded: int
) -> ClassificationScope:
    """What the uniqueness covers: the scanned records, partial when some were left out."""
    size = (
        field.presence.parent_count
        if population == "positions"
        else field.values.count
    )
    return ClassificationScope(
        population=population, of=size, partial=excluded > 0, accuracy="exact"
    )


def positions_complete(field: FieldResult) -> bool:
    """The conditions of Unique ID about the positions of the field (3.8): not
    under a JSON array and every position of the scanned scope holds a value."""
    return (
        not under_array(field)
        and field.missing.count == 0
        # A record without the field is a missing position even when the
        # configuration does not count ``absent`` as missing.
        and field.presence.absent in (0, None)
    )


def _is_unique(field: FieldResult) -> bool:
    """The conditions of Unique ID other than the role itself (3.8)."""
    return positions_complete(field) and observed_unique(field)


def unique_evidence(
    field: FieldResult, excluded: int, cardinality: str = "values.cardinality"
) -> list[ClassificationEvidence]:
    """The two measures that prove a Unique ID, with the scope they cover.

    ``cardinality`` names the measure of the distinct count: the Scan's, or the
    second pass's when the Report refines the classification.
    """
    return [
        ClassificationEvidence(
            source="measure",
            id=cardinality,
            role="supports",
            scope=_scope(field, "present_values", excluded),
        ),
        ClassificationEvidence(
            source="measure",
            id="missing.count",
            role="supports",
            scope=_scope(field, "positions", excluded),
        ),
    ]


def _alternative(pair: tuple[str, str], reason: str) -> ClassificationAlternative:
    return ClassificationAlternative(family=pair[0], type=pair[1], reason=reason)


def with_role(
    result: Classification,
    hints: tuple[NameHint, ...],
    field: FieldResult,
    excluded: int,
) -> Classification:
    """The classification with the identifier role the name and the values give.

    ``excluded`` is the number of records of the dataset left out of the scan:
    the scope of a Unique ID says it. A name that suggests the role without the
    values or a more specific type allowing it is a ``name_only`` alternative
    (``uuid_name`` on a UUID). A weakening name (``customer_id_length``) removes
    the role.
    """
    supports = _hint_polarity(hints, "supports")
    if (
        supports is None
        or _hint_polarity(hints, "weakens") is not None
        or (result.family, result.type) == ("other", "empty")
    ):
        return result
    if not (_compatible(field) and _replaceable(result)):
        if field.technical_type.type not in supports.technical:
            return result
        reason = "uuid_name" if (result.family, result.type) == UUID else "name_only"
        return result.model_copy(
            update={
                "alternatives": [*result.alternatives, _alternative(ID, reason)],
            }
        )
    pair = UNIQUE_ID if _is_unique(field) else ID
    evidence = [
        technical_evidence(field),
        *(
            item.model_copy(update={"role": "context"})
            for item in result.evidence
            if item.source != "technical_type"
        ),
        name_evidence(supports, "supports"),
    ]
    if pair == UNIQUE_ID:
        evidence += unique_evidence(field, excluded)
    alternatives = list(result.alternatives)
    if (result.family, result.type) not in {
        (item.family, item.type) for item in alternatives
    }:
        alternatives.append(
            _alternative((result.family, result.type), "replaced_by_role")
        )
    return Classification(
        family=pair[0],
        type=pair[1],
        basis="inferred",
        state="candidate",
        traits=list(result.traits),
        evidence=evidence,
        alternatives=alternatives,
        rule_version=result.rule_version,
    )


__all__ = [
    "ID",
    "MINIMUM_VALUES",
    "UNIQUE_ID",
    "field_traits",
    "observed_unique",
    "positions_complete",
    "unique_evidence",
    "with_role",
]
