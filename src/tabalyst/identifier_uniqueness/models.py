# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Models of the identifier uniqueness: the facts the rule reads and the object it derives.

Contract: ``docs/dev/report/identifier-uniqueness.md`` (5 for the output, 9 for the input).
"""

from typing import Any, Literal

from pydantic import ConfigDict, model_serializer

from tabalyst.result_model import ResultModel

RULE_VERSION = 1
# Version of the near-uniqueness model (contract 14): changes with any constant or formula of it.
NEAR_UNIQUE_VERSION = 1

NearUniqueSignal = Literal["near_unique", "not_near_unique", "population_too_small"]
ToleranceBound = Literal["relative", "root", "cap"]
RowIdentity = Literal["full_decoded_csv_row_v1", "scan_record_v1"]
DistinctSource = Literal[
    "scan.values.cardinality", "deep.exact_distinct", "deep.analytical_distinct"
]
DistinctAccuracy = Literal["exact", "estimated", "limited"]
ValueDomain = Literal["analytical", "original"]
DuplicateSource = Literal[
    "scan.records.duplicates", "dedup.report", "deep.duplicate_rows_count"
]
DuplicateAccuracy = Literal["exact", "lower_bound", "disabled"]
MissingCopiesSource = Literal["deep.missing_id_copies"]
MissingCopiesAccuracy = Literal["exact", "lower_bound"]
ProofOrigin = Literal["colocated", "explicit"]
Status = Literal["complete", "limited", "not_assessed", "failed"]
Interpretation = Literal[
    "raw_unique",
    "unique_after_row_deduplication",
    "unique_among_present_ids",
    "repeated_between_distinct_records",
    "not_assessed",
]
Reason = Literal[
    "missing_ids",
    "too_few_records",
    "too_few_distinct_records",
    "scope_partial",
    "distinct_estimated",
    "distinct_not_exact",
    "distinct_unavailable",
    "duplicates_limited",
    "duplicates_disabled",
    "inconsistent_measures",
    "evidence_conflict",
    "computation_error",
]
RejectionReason = Literal[
    "dedup_unreadable",
    "dedup_not_complete",
    "dedup_source_mismatch",
    "dedup_not_csv",
    "dedup_dialect_mismatch",
    "dedup_identity_unsupported",
    "dedup_total_mismatch",
    "dedup_invariants_broken",
]


def _without_none(data: dict[str, Any], name: str) -> dict[str, Any]:
    """``data`` without the member ``name`` when it is ``null`` (a member that applies to some columns)."""
    if data.get(name) is None:
        data.pop(name, None)
    return data


class FrozenModel(ResultModel):
    """A model that refuses undeclared members and cannot change once built."""

    model_config = ConfigDict(frozen=True)


# ------------------------------------------------------------------ input


class DedupReportRef(FrozenModel):
    """Which Dedup report supplied a count; only a file name, never a path."""

    name: str
    format_revision: int
    settings_identity: str
    content_sha256: str
    origin: ProofOrigin


class RejectedProof(FrozenModel):
    """A proof that was read and refused, kept as a diagnostic."""

    source: Literal["dedup.report"]
    reason: RejectionReason


class DistinctEvidence(FrozenModel):
    """The distinct values of the identifier column (``D``)."""

    value: int | None
    source: DistinctSource
    accuracy: DistinctAccuracy
    domain: ValueDomain
    # An analytical stage altered a value, so a count of the original values is not ``D``.
    stages_changed_values: bool


class DuplicateEvidence(FrozenModel):
    """The extra copies of whole rows (``E``) from one source."""

    value: int | None  # a lower bound when ``accuracy`` is ``lower_bound``
    source: DuplicateSource
    accuracy: DuplicateAccuracy
    identity: RowIdentity
    report: DedupReportRef | None = None


class MissingCopiesEvidence(FrozenModel):
    """The extra copies of the rows that have no ID (``E_missing``) from the second pass.

    Only a copy of a row whose ID is absent is counted, so ``E - E_missing`` is the copies of the rows
    that have an ID (``E_present``). A lower bound is never ``E_missing``.
    """

    value: int | None  # a lower bound when ``accuracy`` is ``lower_bound``
    source: MissingCopiesSource
    accuracy: MissingCopiesAccuracy
    identity: RowIdentity


class UniquenessFacts(FrozenModel):
    """Everything the rule reads for one column of one dataset."""

    dataset: str
    eligible: bool  # identifier role, not under an array
    records: int  # N
    present: int  # P
    missing: int  # M
    scope_complete: bool
    source_sha256: str
    distinct: DistinctEvidence | None
    # The other exact counts of the distinct values, which must agree with ``distinct``.
    distinct_alternatives: tuple[DistinctEvidence, ...] = ()
    duplicates: tuple[DuplicateEvidence, ...] = ()  # every usable source, Scan first
    missing_copies: MissingCopiesEvidence | None = None  # only with missing IDs (lot 10)
    rejected: tuple[RejectedProof, ...] = ()


# ----------------------------------------------------------------- output


class UniquenessScope(FrozenModel):
    """What the figures count."""

    dataset: str
    population: Literal["source_records"] = "source_records"
    source_records: int
    distinct_records: int | None
    eligible_id_values: int
    missing_id_positions: int
    id_value_domain: ValueDomain | None
    row_identity: RowIdentity | None
    complete: bool


class UniquenessBlock(FrozenModel):
    """Uniqueness of the identifier over a set of rows; ``null`` is never ``0``."""

    unique: bool | None
    id_distinct: int | None
    id_redundant: int | None


class UniquenessExplanation(FrozenModel):
    """The repetitions explained by row copies and those left between distinct records."""

    duplicate_row_extra_copies: int | None
    id_repetitions_explained: int | None
    id_repetitions_residual: int | None
    # The copies of rows whose ID is absent, set aside from ``explained``. Written only for a column
    # that lacks a value and whose copies were counted: elsewhere the member does not apply.
    duplicate_row_extra_copies_without_id: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _without_none(handler(self), "duplicate_row_extra_copies_without_id")


class CardinalityEvidence(FrozenModel):
    """Where ``D`` comes from."""

    source: DistinctSource
    accuracy: DistinctAccuracy
    domain: ValueDomain


class DuplicateRowsEvidence(FrozenModel):
    """Where ``E`` comes from."""

    source: DuplicateSource
    accuracy: DuplicateAccuracy
    identity: RowIdentity
    report: DedupReportRef | None = None


class MissingCopiesRowsEvidence(FrozenModel):
    """Where ``E_missing`` comes from."""

    source: MissingCopiesSource
    accuracy: MissingCopiesAccuracy
    identity: RowIdentity


class ConflictValue(FrozenModel):
    """One exact value of a measure two sources disagree on."""

    source: str
    value: int | None


class EvidenceConflict(FrozenModel):
    """The exact values that disagree, for the diagnosis."""

    measure: Literal["duplicate_rows", "id_cardinality"]
    values: tuple[ConflictValue, ...]


class UniquenessEvidence(FrozenModel):
    """The provenance of the measures."""

    id_cardinality: CardinalityEvidence | None
    duplicate_rows: DuplicateRowsEvidence | None
    source_sha256: str
    # The count of the copies of the rows without an ID, only for a column that lacks a value.
    missing_id_copies: MissingCopiesRowsEvidence | None = None
    rejected: tuple[RejectedProof, ...] = ()
    conflict: EvidenceConflict | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _without_none(handler(self), "missing_id_copies")


class NearUnique(FrozenModel):
    """A non-binding reading of the residual repetitions of an identifier (contract 14).

    It never says the column is unique: ``unique`` stays false and the repetitions stay
    listed. ``tolerance`` is the most extra occurrences of an ID among the distinct rows that
    the model still calls few, and ``limiting_bound`` the term of the model that sets it.
    """

    model_version: int = NEAR_UNIQUE_VERSION
    signal: NearUniqueSignal
    residual_repetitions: int  # R_residual
    distinct_records: int  # U
    tolerance: int
    limiting_bound: ToleranceBound | None


class IdentifierUniqueness(FrozenModel):
    """The derived uniqueness of one identifier column (contract 5)."""

    rule_version: int = RULE_VERSION
    status: Status
    interpretation: Interpretation
    reason: Reason | None
    scope: UniquenessScope
    raw: UniquenessBlock
    after_row_deduplication: UniquenessBlock
    explanation: UniquenessExplanation
    evidence: UniquenessEvidence
    # Only for ``repeated_between_distinct_records``; ``null`` everywhere else.
    near_unique: NearUnique | None = None
