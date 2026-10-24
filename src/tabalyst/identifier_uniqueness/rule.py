# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The pure rule that qualifies the uniqueness of an identifier column (contract 2 to 4).

It reads ``UniquenessFacts`` only: no file, no worker, exact integers, deterministic.
"""

from tabalyst.identifier_uniqueness.models import (
    CardinalityEvidence,
    ConflictValue,
    DuplicateEvidence,
    DuplicateRowsEvidence,
    EvidenceConflict,
    IdentifierUniqueness,
    Interpretation,
    Reason,
    Status,
    UniquenessBlock,
    UniquenessEvidence,
    UniquenessExplanation,
    UniquenessFacts,
    UniquenessScope,
)

_UNKNOWN = UniquenessBlock(unique=None, id_distinct=None, id_redundant=None)
_NO_EXPLANATION = UniquenessExplanation(
    duplicate_row_extra_copies=None,
    id_repetitions_explained=None,
    id_repetitions_residual=None,
)


def assess_identifier_uniqueness(facts: UniquenessFacts) -> IdentifierUniqueness | None:
    """Separate the ID repetitions explained by copied rows from the residual ones.

    Returns ``None`` for a column that is not eligible (contract 3). Contradictory
    evidence gives a ``failed`` object and an unexpected error ``computation_error``;
    nothing is ever raised, so the Report is still written.
    """
    if not facts.eligible:
        return None
    try:
        return _assess(facts)
    except Exception:  # noqa: BLE001 - the Report must survive a rule that breaks
        return _failed(facts, "computation_error")


def _assess(facts: UniquenessFacts) -> IdentifierUniqueness:
    n, p, m = facts.records, facts.present, facts.missing
    exact = [s for s in facts.duplicates if s.accuracy == "exact" and s.value is not None]
    bounds = [
        s for s in facts.duplicates if s.accuracy == "lower_bound" and s.value is not None
    ]
    d = _usable_distinct(facts)

    # A broken invariant is reported whatever else is missing (contract 4).
    if len({s.value for s in exact}) > 1:
        return _failed(facts, "evidence_conflict", conflict=_conflict(exact))
    e = exact[0].value if exact else None
    floor = max((s.value for s in bounds if s.value is not None), default=None)
    if _inconsistent(n, p, m, d, e, floor):
        return _failed(facts, "inconsistent_measures")

    selected = _selected(facts, exact, bounds)
    scope_distinct = n - e if e is not None else None

    def result(
        status: Status,
        interpretation: Interpretation,
        reason: Reason | None,
        *,
        raw: UniquenessBlock = _UNKNOWN,
        after: UniquenessBlock = _UNKNOWN,
        explanation: UniquenessExplanation = _NO_EXPLANATION,
        distinct_records: int | None = scope_distinct,
    ) -> IdentifierUniqueness:
        return _build(
            facts,
            status,
            interpretation,
            reason,
            raw=raw,
            after=after,
            explanation=explanation,
            distinct_records=distinct_records,
            selected=selected,
        )

    distinct = facts.distinct
    if distinct is None or distinct.value is None:
        return result("not_assessed", "not_assessed", "distinct_unavailable")
    if distinct.accuracy != "exact":
        return result("limited", "not_assessed", "distinct_estimated")
    if d is None:
        return result("limited", "not_assessed", "distinct_not_exact")
    if not facts.scope_complete:
        return result("limited", "not_assessed", "scope_partial")
    if m > 0:
        return result("limited", "not_assessed", "missing_ids")
    if n < 2:
        return result("limited", "not_assessed", "too_few_records")

    raw = UniquenessBlock(unique=d == n, id_distinct=d, id_redundant=n - d)
    if d == n:
        # A copied row repeats its ID, so no copy exists and no duplicate count is needed.
        return result(
            "complete",
            "raw_unique",
            None,
            raw=raw,
            after=UniquenessBlock(unique=True, id_distinct=d, id_redundant=0),
            explanation=UniquenessExplanation(
                duplicate_row_extra_copies=0,
                id_repetitions_explained=0,
                id_repetitions_residual=0,
            ),
            distinct_records=n,
        )
    if e is None:
        if bounds:
            return result("limited", "not_assessed", "duplicates_limited", raw=raw)
        return result("not_assessed", "not_assessed", "duplicates_disabled", raw=raw)

    distinct_rows = n - e
    residual = distinct_rows - d
    explanation = UniquenessExplanation(
        duplicate_row_extra_copies=e,
        id_repetitions_explained=e,
        id_repetitions_residual=residual,
    )
    if distinct_rows < 2:
        return result(
            "limited",
            "not_assessed",
            "too_few_distinct_records",
            raw=raw,
            after=UniquenessBlock(unique=None, id_distinct=d, id_redundant=residual),
            explanation=explanation,
        )
    return result(
        "complete",
        "unique_after_row_deduplication" if residual == 0 else "repeated_between_distinct_records",
        None,
        raw=raw,
        after=UniquenessBlock(unique=residual == 0, id_distinct=d, id_redundant=residual),
        explanation=explanation,
    )


def _usable_distinct(facts: UniquenessFacts) -> int | None:
    """``D`` when it is exact and comparable to the analytical values (contract 6.1)."""
    distinct = facts.distinct
    if distinct is None or distinct.value is None or distinct.accuracy != "exact":
        return None
    if distinct.domain == "original" and distinct.stages_changed_values:
        return None
    return distinct.value


def _inconsistent(
    n: int, p: int, m: int, d: int | None, e: int | None, floor: int | None
) -> bool:
    """Whether the measures break an invariant of contract 2."""
    if n < 0 or not 0 <= p <= n or m != n - p:
        return True
    if d is not None and not 0 <= d <= p:
        return True
    for copies in (e, floor):
        if copies is None:
            continue
        if not 0 <= copies <= n:
            return True
        # With no missing ID a copied row repeats its ID: E cannot exceed R_raw.
        if m == 0 and d is not None and copies > n - d:
            return True
    return e is not None and floor is not None and e < floor


def _selected(
    facts: UniquenessFacts,
    exact: list[DuplicateEvidence],
    bounds: list[DuplicateEvidence],
) -> DuplicateEvidence | None:
    """The source of ``E`` shown as evidence: exact first, then the highest bound, then what exists."""
    if exact:
        return exact[0]
    if bounds:
        return max(bounds, key=lambda source: source.value or 0)
    return facts.duplicates[0] if facts.duplicates else None


def _conflict(sources: list[DuplicateEvidence]) -> EvidenceConflict:
    return EvidenceConflict(
        measure="duplicate_rows",
        values=tuple(ConflictValue(source=s.source, value=s.value) for s in sources),
    )


def _failed(
    facts: UniquenessFacts, reason: Reason, *, conflict: EvidenceConflict | None = None
) -> IdentifierUniqueness:
    return _build(
        facts,
        "failed",
        "not_assessed",
        reason,
        raw=_UNKNOWN,
        after=_UNKNOWN,
        explanation=_NO_EXPLANATION,
        distinct_records=None,
        selected=None,
        conflict=conflict,
    )


def _build(
    facts: UniquenessFacts,
    status: Status,
    interpretation: Interpretation,
    reason: Reason | None,
    *,
    raw: UniquenessBlock,
    after: UniquenessBlock,
    explanation: UniquenessExplanation,
    distinct_records: int | None,
    selected: DuplicateEvidence | None,
    conflict: EvidenceConflict | None = None,
) -> IdentifierUniqueness:
    distinct = facts.distinct
    return IdentifierUniqueness(
        status=status,
        interpretation=interpretation,
        reason=reason,
        scope=UniquenessScope(
            dataset=facts.dataset,
            source_records=facts.records,
            distinct_records=distinct_records,
            eligible_id_values=facts.present,
            missing_id_positions=facts.missing,
            id_value_domain=distinct.domain if distinct is not None else None,
            row_identity=selected.identity if selected is not None else None,
            complete=facts.scope_complete,
        ),
        raw=raw,
        after_row_deduplication=after,
        explanation=explanation,
        evidence=UniquenessEvidence(
            id_cardinality=None
            if distinct is None
            else CardinalityEvidence(
                source=distinct.source, accuracy=distinct.accuracy, domain=distinct.domain
            ),
            duplicate_rows=None
            if selected is None
            else DuplicateRowsEvidence(
                source=selected.source,
                accuracy=selected.accuracy,
                identity=selected.identity,
                report=selected.report,
            ),
            source_sha256=facts.source_sha256,
            rejected=facts.rejected,
            conflict=conflict,
        ),
    )
