# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Models of the identifier uniqueness: the facts the rule reads and the object it derives.

Contract: ``docs/dev/report/identifier-uniqueness.md`` (5 for the output, 9 for the input).
"""

from typing import Literal

from pydantic import ConfigDict

from tabalyst.result_model import ResultModel

RULE_VERSION = 1

RowIdentity = Literal["full_decoded_csv_row_v1", "scan_record_v1"]
DistinctSource = Literal["scan.values.cardinality", "deep.exact_distinct"]
DistinctAccuracy = Literal["exact", "estimated", "limited"]
ValueDomain = Literal["analytical", "original"]
DuplicateSource = Literal[
    "scan.records.duplicates", "dedup.report", "deep.duplicate_rows_count"
]
DuplicateAccuracy = Literal["exact", "lower_bound", "disabled"]
ProofOrigin = Literal["colocated", "explicit"]
Status = Literal["complete", "limited", "not_assessed", "failed"]
Interpretation = Literal[
    "raw_unique",
    "unique_after_row_deduplication",
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
    duplicates: tuple[DuplicateEvidence, ...] = ()  # every usable source, Scan first
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
    rejected: tuple[RejectedProof, ...] = ()
    conflict: EvidenceConflict | None = None


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
