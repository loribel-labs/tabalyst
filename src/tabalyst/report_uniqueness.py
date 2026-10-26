# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The words and rows that print the identifier uniqueness of a column and of a dataset.

Reads the stored ``identifier_uniqueness`` member only (contract identifier-uniqueness.md 8):
it decides nothing, the case A to E comes from its codes. The models are never serialized.
"""

from __future__ import annotations

from typing import Literal

from tabalyst.identifier_uniqueness.models import IdentifierUniqueness
from tabalyst.identifier_uniqueness.near_unique import (
    ABSOLUTE_CAP,
    MIN_POPULATION,
    RELATIVE_DIVISOR,
)
from tabalyst.report_labels import (
    UNIQUENESS_ACCURACY,
    UNIQUENESS_CARDINALITY_SOURCES,
    UNIQUENESS_CASES,
    UNIQUENESS_IDENTITIES,
    UNIQUENESS_MISSING_SOURCES,
    UNIQUENESS_NEAR_BOUNDS,
    UNIQUENESS_NEAR_CAVEAT,
    UNIQUENESS_NEAR_TITLES,
    UNIQUENESS_NEAR_TOO_SMALL,
    UNIQUENESS_ORIGINS,
    UNIQUENESS_PROOF_SOURCES,
    UNIQUENESS_REASONS,
    UNIQUENESS_REJECTIONS,
    UNIQUENESS_STATUS_WORDS,
    UNIQUENESS_TITLES,
)
from tabalyst.report_views import ColumnView
from tabalyst.result_model import ResultModel

Case = Literal["A", "B", "C", "D", "E"]


class UniquenessRow(ResultModel):
    """A figure of the block; ``None`` is printed as not established, never as 0."""

    label: str
    figure: int | None


class UniquenessNear(ResultModel):
    """The non-binding near-unique reading under the figures of case C."""

    signal: str
    title: str
    text: str
    caveat: str | None


class UniquenessView(ResultModel):
    """The block of a column page and the short line of the Summary."""

    case: Case
    title: str
    text: str
    # The qualification the Summary prints; ``None`` unless the rule concluded.
    short: str | None
    status: str
    status_word: str
    caveat: str | None
    rows: list[UniquenessRow]
    near: UniquenessNear | None
    evidence: list[str]
    rejected: list[str]


class UniquenessSettings(ResultModel):
    """What the Analysis settings say of the uniqueness of a dataset's identifiers."""

    rule_version: int
    columns: int
    lines: list[str]


def _n(value: int) -> str:
    return f"{value:,}"


def _plural(n: int, one: str, many: str) -> str:
    return f"{_n(n)} {one if n == 1 else many}"


def uniqueness_case(item: IdentifierUniqueness) -> Case:
    """The case A to E of the specification 11.2 for a stored object.

    A column that lacks a value is case E whatever the rule concluded among the records that have
    one: the figures are printed with it (lot 10)."""
    if item.reason == "missing_ids":
        return "E"
    if item.interpretation == "raw_unique":
        return "A"
    if item.interpretation == "unique_after_row_deduplication":
        return "B"
    if item.interpretation == "repeated_between_distinct_records":
        return "C"
    return "D"


def _text(case: Case, item: IdentifierUniqueness) -> str:
    scope, why = item.scope, item.explanation
    if case == "A":
        return f"Unique across all {_n(scope.source_records)} source records. No missing IDs."
    if case == "B":
        copies = why.duplicate_row_extra_copies or 0
        distinct = scope.distinct_records or 0
        return (
            f"{_plural(copies, 'repeated ID occurrence is', 'repeated ID occurrences are')} fully "
            f"explained by {_plural(copies, 'exact duplicate row', 'exact duplicate rows')}. "
            f"No ID conflicts remain among {_n(distinct)} distinct records."
        )
    if case == "C":
        explained = why.id_repetitions_explained or 0
        residual = why.id_repetitions_residual or 0
        total = explained + residual
        return (
            f"{_plural(total, 'repetition', 'repetitions')}: {_n(explained)} explained by exact "
            f"duplicate rows, {_n(residual)} remain between distinct records."
        )
    if case == "E":
        return _missing_text(item)
    if item.status == "failed":
        return (
            "The measures of this column contradict each other. "
            "No conclusion about uniqueness after deduplication."
        )
    return (
        "The exact number of distinct IDs or duplicate rows is unavailable. "
        "No conclusion about uniqueness after deduplication."
    )


def _missing_text(item: IdentifierUniqueness) -> str:
    """Case E: the records without an ID, and, when the copies were counted, what is left of the
    repetitions among the rows that have one (cahier 5.4)."""
    scope, why = item.scope, item.explanation
    base = "Uniqueness after deduplication cannot be established: some records have no ID."
    if item.interpretation not in ("unique_among_present_ids", "repeated_between_distinct_records"):
        return base
    copies = why.id_repetitions_explained or 0
    residual = why.id_repetitions_residual or 0
    present = scope.eligible_id_values
    rows = present - copies
    head = (
        f"{_plural(scope.missing_id_positions, 'record has', 'records have')} no ID. "
        f"Among the {_plural(present, 'record', 'records')} that "
        f"{'has' if present == 1 else 'have'} one, "
        f"{_plural(copies, 'is an exact copy of a row', 'are exact copies of rows')}. "
    )
    if residual == 0:
        return head + f"No ID repeats between the {_n(rows)} distinct rows that have one."
    return head + (
        f"{_plural(residual, 'ID repetition remains', 'ID repetitions remain')} between "
        f"the {_n(rows)} distinct rows that have one."
    )


def _short(case: Case, item: IdentifierUniqueness) -> str | None:
    if item.status != "complete":
        return None
    if case in ("A", "B"):
        return UNIQUENESS_TITLES[UNIQUENESS_CASES[case]]
    if case == "C":
        residual = item.explanation.id_repetitions_residual or 0
        return (
            f"{_plural(residual, 'ID repetition', 'ID repetitions')} "
            f"{'remains' if residual == 1 else 'remain'} between distinct records"
        )
    return None


def _near(item: IdentifierUniqueness) -> UniquenessNear | None:
    """The near-unique reading, which only the case C stores (contract 14)."""
    near = item.near_unique
    if near is None:
        return None
    repetitions = _plural(near.residual_repetitions, "repetition", "repetitions")
    records = _n(near.distinct_records)
    if near.signal == "population_too_small":
        text = (
            f"{repetitions} among {records} distinct records: "
            + UNIQUENESS_NEAR_TOO_SMALL.format(minimum=_n(MIN_POPULATION))
        )
        caveat = None
    else:
        bound = (
            UNIQUENESS_NEAR_BOUNDS[near.limiting_bound].format(
                divisor=_n(RELATIVE_DIVISOR), cap=_n(ABSOLUTE_CAP)
            )
            if near.limiting_bound
            else ""
        )
        verdict = "within" if near.signal == "near_unique" else "above"
        text = (
            f"{repetitions} among {records} distinct records, {verdict} the tolerance of "
            f"{_n(near.tolerance)} (set by {bound})."
        )
        caveat = UNIQUENESS_NEAR_CAVEAT
    return UniquenessNear(
        signal=near.signal,
        title=UNIQUENESS_NEAR_TITLES[near.signal],
        text=text,
        caveat=caveat,
    )


def _evidence(item: IdentifierUniqueness) -> list[str]:
    lines = []
    cardinality = item.evidence.id_cardinality
    if cardinality:
        lines.append(
            "Distinct IDs: "
            f"{UNIQUENESS_ACCURACY[cardinality.accuracy]}, from "
            f"{UNIQUENESS_CARDINALITY_SOURCES[cardinality.source]}, "
            f"{cardinality.domain} values."
        )
    counted = item.evidence.missing_id_copies
    rows = item.evidence.duplicate_rows
    if rows:
        line = (
            "Duplicate rows: "
            f"{UNIQUENESS_ACCURACY[rows.accuracy]}, from {UNIQUENESS_PROOF_SOURCES[rows.source]}, "
            f"comparing {UNIQUENESS_IDENTITIES[rows.identity]}."
        )
        if rows.report:
            line += f" Report {rows.report.name}, {UNIQUENESS_ORIGINS[rows.report.origin]}."
        lines.append(line)
    if counted:
        lines.append(
            "Copies of rows without an ID: "
            f"{UNIQUENESS_ACCURACY[counted.accuracy]}, from "
            f"{UNIQUENESS_MISSING_SOURCES[counted.source]}, "
            f"comparing {UNIQUENESS_IDENTITIES[counted.identity]}."
        )
    return lines


def _rejected(item: IdentifierUniqueness) -> list[str]:
    return [
        f"A Dedup report was not used: {UNIQUENESS_REJECTIONS[proof.reason]}."
        for proof in item.evidence.rejected
    ]


def uniqueness_view(item: IdentifierUniqueness | None) -> UniquenessView | None:
    """The block of one column, from its stored object; ``None`` outside identifiers."""
    if item is None:
        return None
    case = uniqueness_case(item)
    scope, why = item.scope, item.explanation
    caveat = None
    if item.status != "complete" and item.reason:
        counted = item.reason == "missing_ids" and item.explanation.id_repetitions_residual is not None
        caveat = UNIQUENESS_REASONS["missing_ids_counted" if counted else item.reason]
    failed = item.status == "failed"
    return UniquenessView(
        case=case,
        title=UNIQUENESS_TITLES[UNIQUENESS_CASES[case]],
        text=_text(case, item),
        short=_short(case, item),
        status=item.status,
        status_word=UNIQUENESS_STATUS_WORDS[item.status],
        caveat=caveat,
        rows=[]
        if failed
        else [
            UniquenessRow(label="Source records", figure=scope.source_records),
            UniquenessRow(label="Distinct IDs", figure=item.raw.id_distinct),
            UniquenessRow(label="Repeated ID occurrences, all rows", figure=item.raw.id_redundant),
            UniquenessRow(
                label="Explained by exact duplicate rows", figure=why.id_repetitions_explained
            ),
            *(
                [
                    UniquenessRow(
                        label="Copies of rows without an ID",
                        figure=why.duplicate_row_extra_copies_without_id,
                    )
                ]
                if why.duplicate_row_extra_copies_without_id is not None
                else []
            ),
            UniquenessRow(label="Distinct rows", figure=scope.distinct_records),
            UniquenessRow(
                label="Left between distinct records", figure=why.id_repetitions_residual
            ),
        ],
        near=_near(item),
        evidence=_evidence(item),
        rejected=_rejected(item),
    )


def page_type_name(view: UniquenessView | None) -> str | None:
    """The type name of an identifier whose uniqueness was assessed, so that the page never
    says Unique ID of a column with exact row copies (contract 8, language rule); ``None``
    leaves the usual name."""
    if view is None or view.case not in ("A", "B", "C"):
        return None
    return view.title if view.case in ("A", "B") else "ID"


def uniqueness_settings(columns: list[ColumnView]) -> UniquenessSettings | None:
    """The proofs behind the uniqueness of the identifier columns of a dataset, as the
    Analysis settings print them; ``None`` when no column has one."""
    items = [
        c.summary.identifier_uniqueness
        for c in columns
        if c.summary is not None and c.summary.identifier_uniqueness is not None
    ]
    if not items:
        return None
    lines = []
    sources = {
        UNIQUENESS_PROOF_SOURCES[i.evidence.duplicate_rows.source]
        for i in items
        if i.evidence.duplicate_rows and i.evidence.duplicate_rows.accuracy == "exact"
    }
    if sources:
        lines.append("Exact duplicate rows read from " + " and ".join(sorted(sources)) + ".")
    elif not all(i.interpretation == "raw_unique" for i in items):
        lines.append("No exact count of duplicate rows was available.")
    reports = {
        (r.name, UNIQUENESS_ORIGINS[r.origin])
        for i in items
        if i.evidence.duplicate_rows and (r := i.evidence.duplicate_rows.report)
    }
    lines += [f"Dedup report {name}, {origin}." for name, origin in sorted(reports)]
    refused = sorted({p.reason for i in items for p in i.evidence.rejected})
    lines += [f"A Dedup report was not used: {UNIQUENESS_REJECTIONS[r]}." for r in refused]
    models = sorted({i.near_unique.model_version for i in items if i.near_unique})
    if models:
        lines.append(
            "Near-unique reading, model version " + " and ".join(map(str, models)) + "."
        )
    if any(i.evidence.missing_id_copies for i in items):
        lines.append("Copies of the rows without an ID counted by the second pass.")
    lines.append("The qualification reads no data and does not run Dedup.")
    return UniquenessSettings(
        rule_version=items[0].rule_version, columns=len(items), lines=lines
    )
