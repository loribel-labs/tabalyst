# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Builds the facts the uniqueness rule reads from the Scan, the second pass and a Dedup proof.

Nothing here reads the source: only documents the Report already holds and, at most, one small
Dedup report (contract 6, 7 and 9.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path

from tabalyst.errors import InputError
from tabalyst.identifier_uniqueness.models import (
    DistinctEvidence,
    DuplicateEvidence,
    DuplicateSource,
    IdentifierUniqueness,
    ProofOrigin,
    RejectedProof,
    RowIdentity,
    UniquenessFacts,
)
from tabalyst.identifier_uniqueness.rule import assess_identifier_uniqueness
from tabalyst.models import AnalysesBlock
from tabalyst.report_classification import (
    analytical_stages_unchanged,
    distinct_count,
    refine,
)
from tabalyst.scanner.classify.identifiers import ID, UNIQUE_ID, under_array
from tabalyst.scanner.models import (
    CardinalityLimited,
    Complete,
    DatasetResult,
    FieldResult,
    Limited,
    ScanResult,
)
from tabalyst.scanner.planner.models import PlanBase
from tabalyst.scanner.quality import analytical_distinct

_IDENTIFIER_ROLES = (ID, UNIQUE_ID)


@dataclass(frozen=True)
class UniquenessSources:
    """Where a Report finds what the uniqueness of its identifier columns needs beyond the Scan."""

    # The Scan the second pass must stand on (``None``: not checked).
    base: PlanBase | None = None
    # The file or folder named by ``--dedup-report``.
    dedup_report: Path | None = None
    # The folder searched for the colocated ``<stem>.dedup.json``.
    source_dir: Path | None = None
    # Proofs already read, by dataset: one Dedup report serves every identifier column of it.
    proofs: dict[str, DuplicateEvidence | RejectedProof | None] = dataclass_field(
        default_factory=dict, compare=False, repr=False
    )


def identifier_uniqueness_of(
    scan: ScanResult,
    dataset: str,
    field_id: str,
    analyses: AnalysesBlock | None,
    sources: UniquenessSources,
) -> IdentifierUniqueness | None:
    """The derived uniqueness of a column, or ``None`` when it is not an identifier."""
    facts = facts_from_scan(
        scan,
        dataset,
        field_id,
        analyses=analyses,
        base=sources.base,
        dedup_report=sources.dedup_report,
        source_dir=sources.source_dir,
        proofs=sources.proofs,
    )
    return None if facts is None else assess_identifier_uniqueness(facts)


def check_dedup_option(option: Path, source_format: str, source_name: str) -> None:
    """Refuse a ``--dedup-report`` the source cannot use (a project rule: no option is ignored).

    Raises ``InputError`` for a source that is not a CSV (only Dedup, which reads CSV, writes such
    a report) and for a file or folder that does not exist or, for a folder, holds no
    ``<source stem>.dedup.json``.
    """
    if source_format != "csv":
        raise InputError(
            f"--dedup-report cannot be used with {source_name}: a Dedup report proves "
            "the copies of the rows of a CSV file."
        )
    from tabalyst.identifier_uniqueness.proof import find_dedup_report

    find_dedup_report(
        option if option.is_dir() else option.parent, option, stem=Path(source_name).stem
    )


def facts_from_scan(
    scan: ScanResult,
    dataset: str,
    field_id: str,
    *,
    analyses: AnalysesBlock | None = None,
    base: PlanBase | None = None,
    dedup_report: Path | None = None,
    source_dir: Path | None = None,
    proofs: dict[str, DuplicateEvidence | RejectedProof | None] | None = None,
) -> UniquenessFacts | None:
    """The facts of one column of one dataset, or ``None`` when it is not an identifier.

    The column is an identifier when the Report's classification (the Scan's, refined by the
    second pass) says so and it is not under a JSON array. ``dedup_report`` is the file or folder
    the user named and ``source_dir`` the folder searched for the colocated ``<stem>.dedup.json``
    (a CSV source only). ``base`` tells which Scan the second pass must stand on. ``proofs``
    memoizes the Dedup proof by dataset across the columns of one Report.
    """
    target = next((item for item in scan.datasets if item.id == dataset), None)
    field = None if target is None else next((f for f in target.fields if f.id == field_id), None)
    if target is None or field is None:
        return None
    classification = refine(
        field,
        analyses,
        dataset=dataset,
        base=base,
        excluded_records=scan.scope.records_excluded,
    )
    if (classification.family, classification.type) not in _IDENTIFIER_ROLES or under_array(field):
        return None
    records = target.record_count
    present = field.values.count
    duplicates = [_scan_duplicates(scan, target)]
    rejected: tuple[RejectedProof, ...] = ()
    if proofs is not None and dataset in proofs:
        proof = proofs[dataset]
    else:
        proof = _dedup_proof(scan, dataset, dedup_report, source_dir)
        if proofs is not None:
            proofs[dataset] = proof
    if isinstance(proof, DuplicateEvidence):
        duplicates.append(proof)
    elif proof is not None:
        rejected = (proof,)
    return UniquenessFacts(
        dataset=dataset,
        eligible=True,
        records=records,
        present=present,
        missing=records - present,
        scope_complete=_scope_complete(scan, target),
        source_sha256=scan.source.sha256,
        distinct=_distinct(field, analyses, dataset, base),
        duplicates=tuple(duplicates),
        rejected=rejected,
    )


def _scope_complete(scan: ScanResult, dataset: DatasetResult) -> bool:
    """Contract 6.3: a complete scan without excluded records that read every record counted."""
    if scan.status != "complete" or scan.scope.records_excluded != 0:
        return False
    return len(scan.datasets) != 1 or dataset.record_count == scan.scope.records_read


def _row_identity(scan: ScanResult) -> RowIdentity:
    return "full_decoded_csv_row_v1" if scan.source.format == "csv" else "scan_record_v1"


def _scan_duplicates(scan: ScanResult, dataset: DatasetResult) -> DuplicateEvidence:
    """``E`` as the Scan counted it: exact, a lower bound, or absent (contract 6.2)."""
    count = dataset.records.duplicates.count
    identity = _row_identity(scan)
    source: DuplicateSource = "scan.records.duplicates"
    if isinstance(count, Complete):
        return DuplicateEvidence(
            # ``IntMeasure`` is built by a function, which mypy cannot narrow.
            value=count.value,  # type: ignore[attr-defined]
            source=source, accuracy="exact", identity=identity
        )
    if isinstance(count, Limited):
        return DuplicateEvidence(
            value=count.lower_bound or 0, source=source, accuracy="lower_bound", identity=identity
        )
    return DuplicateEvidence(value=None, source=source, accuracy="disabled", identity=identity)


def _distinct(
    field: FieldResult,
    analyses: AnalysesBlock | None,
    dataset: str,
    base: PlanBase | None,
) -> DistinctEvidence | None:
    """``D`` in the order of contract 6.1: the Scan, then the second pass, then what is partial."""
    exact = analytical_distinct(field)
    if exact is not None:
        return DistinctEvidence(
            value=exact,
            source="scan.values.cardinality",
            accuracy="exact",
            domain="analytical",
            stages_changed_values=False,
        )
    count = distinct_count(field, analyses, dataset, base)
    if count is not None and count.values == field.values.count:
        return DistinctEvidence(
            value=count.distinct,
            source="deep.exact_distinct",
            accuracy="exact",
            domain="original",
            stages_changed_values=not analytical_stages_unchanged(field),
        )
    return _partial_distinct(field)


def _partial_distinct(field: FieldResult) -> DistinctEvidence | None:
    """An estimate or a bound of ``D``: it never counts as ``D`` but explains why there is none."""
    measure = field.values.cardinality
    if isinstance(measure, CardinalityLimited) and measure.estimate is not None:
        return DistinctEvidence(
            value=round(measure.estimate.value),
            source="scan.values.cardinality",
            accuracy="estimated",
            domain="original",
            stages_changed_values=False,
        )
    if isinstance(measure, Limited):
        return DistinctEvidence(
            value=measure.lower_bound,
            source="scan.values.cardinality",
            accuracy="limited",
            domain="original",
            stages_changed_values=False,
        )
    return None


def _dedup_proof(
    scan: ScanResult,
    dataset: str,
    option: Path | None,
    source_dir: Path | None,
) -> DuplicateEvidence | RejectedProof | None:
    """The Dedup report to try (contract 7.1), read and checked; ``None`` when there is none."""
    if scan.source.format != "csv" or (option is None and source_dir is None):
        return None
    # Imported here: the proof reads Dedup documents, and Dedup imports ``service``, which
    # builds the Report that imports this module.
    from tabalyst.identifier_uniqueness.proof import find_dedup_report, load_dedup_proof

    anchor = source_dir
    if anchor is None:
        assert option is not None
        anchor = option if option.is_dir() else option.parent
    stem = Path(scan.source.name).stem
    path = find_dedup_report(anchor, option, stem=stem)
    if path is None:
        return None
    origin: ProofOrigin = "explicit" if option is not None else "colocated"
    return load_dedup_proof(path, scan=scan, dataset=dataset, origin=origin)
