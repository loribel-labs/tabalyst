# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""KPIs of the overview: the signals and the quality of the columns.

Both are sums over the findings of every column (contract summary-table.md 7.5):
the signals say what the checks found, with the columns behind each figure; the
quality says how many columns have Errors, Issues or nothing. Computed at render
time, never serialized.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from tabalyst.models import ResultModel
from tabalyst.report_finding_details import Spelling, variant_details
from tabalyst.report_findings import ColumnFindings, Finding, FindingList
from tabalyst.report_labels import (
    LIST_STATE_LABELS,
    SIGNAL_NOTES,
    SIGNAL_TARGETS,
    SIGNAL_TITLES,
    TABLE_AT_LEAST,
    finding_label,
    finding_name,
    finding_noun,
)
from tabalyst.report_views import ColumnView

# Signals written as a tile; the others are counted ("+2 additional signals").
SIGNALS_SHOWN = 6
# Spellings of the first group shown beside a column in the popover of a spelling signal.
SPELLINGS_SHOWN = 3
# The states of a list in the order the checks print them.
STATE_ORDER = (
    "detected",
    "none_detected",
    "partial",
    "not_assessed",
    "failed",
    "not_applicable",
)
INCOMPLETE = ("partial", "not_assessed", "failed")


def finding_text(item: Finding) -> str:
    """A finding in words with its count: ``3 spelling-variant groups``; a lower
    bound is never worded exact."""
    if item.count is None:
        text = finding_name(item.code, item.unit)
    else:
        text = finding_label(item.code, item.count, item.unit)
    return f"{TABLE_AT_LEAST} {text}" if item.accuracy == "lower_bound" else text


class SignalColumn(ResultModel):
    """One column behind a signal, with its figure and its share of the largest."""

    field_id: str
    name: str
    count: int
    relative_percent: float
    # For the spelling variants: the largest group of the column, through the exposure.
    spellings: list[Spelling]


class Signal(ResultModel):
    """The findings of one code summed over the columns that have it. A sum only
    joins findings of one code counted in one unit."""

    code: str
    cls: str
    total: int
    unit: str
    title: str
    subtitle: str
    noun: str
    # The sum is a lower bound when one of its terms is.
    lower_bound: bool
    columns: list[SignalColumn]
    note: str | None
    target: str | None


class SignalsView(ResultModel):
    """The signals of a dataset, the tiles shown first and what is left."""

    shown: list[Signal]
    more: int
    # Columns whose Errors or Issues were not completely looked at.
    incomplete_columns: int


class StateCount(ResultModel):
    state: str
    label: str
    columns: int


class ValidationList(ResultModel):
    """How many columns are in each state of the Errors or of the Issues."""

    name: str
    with_findings: int
    states: list[StateCount]


class QualityColumn(ResultModel):
    """A column of a quality figure, with the findings that put it there."""

    field_id: str
    name: str
    labels: list[str]


class QualityView(ResultModel):
    """The quality of the columns: each column is in exactly one of three groups.

    A column with Errors counts under Errors even when it also has Issues, so the
    three figures add up to the columns.
    """

    columns: int
    with_errors: int
    with_issues: int
    no_finding: int
    errors_percent: float
    issues_percent: float
    clean_percent: float
    error_columns: list[QualityColumn]
    issue_columns: list[QualityColumn]
    clean_columns: list[QualityColumn]
    # The states of every list, whatever the group (a column with both is in both).
    errors: ValidationList
    issues: ValidationList


def _list(name: str, lists: Sequence[FindingList]) -> ValidationList:
    counts = {state: 0 for state in STATE_ORDER}
    for listing in lists:
        counts[listing.state] += 1
    return ValidationList(
        name=name,
        with_findings=counts["detected"],
        states=[
            StateCount(state=state, label=LIST_STATE_LABELS[state], columns=counts[state])
            for state in STATE_ORDER
            if counts[state]
        ],
    )


def _percent(count: int, total: int) -> float:
    return round(100 * count / total, 1) if total else 0.0


def quality_view(
    columns: Sequence[ColumnView], findings: Sequence[ColumnFindings]
) -> QualityView:
    """The columns with Errors, with Issues only, and with no finding."""
    groups: dict[str, list[QualityColumn]] = {"error": [], "issue": [], "clean": []}
    for column, item in zip(columns, findings, strict=True):
        found = [*item.errors.items, *item.issues.items]
        group = "error" if item.errors.items else "issue" if item.issues.items else "clean"
        groups[group].append(
            QualityColumn(
                field_id=column.id,
                name=column.name or column.path,
                labels=[finding_text(finding) for finding in found],
            )
        )
    total = len(columns)
    return QualityView(
        columns=total,
        with_errors=len(groups["error"]),
        with_issues=len(groups["issue"]),
        no_finding=len(groups["clean"]),
        errors_percent=_percent(len(groups["error"]), total),
        issues_percent=_percent(len(groups["issue"]), total),
        clean_percent=_percent(len(groups["clean"]), total),
        error_columns=groups["error"],
        issue_columns=groups["issue"],
        clean_columns=groups["clean"],
        errors=_list("Errors", [item.errors for item in findings]),
        issues=_list("Issues", [item.issues for item in findings]),
    )


def _spellings(column: ColumnView) -> list[Spelling]:
    details = variant_details(column)
    if details is None or not details.groups:
        return []
    return details.groups[0].spellings[:SPELLINGS_SHOWN]


def signals_view(
    columns: Sequence[ColumnView], findings: Sequence[ColumnFindings]
) -> SignalsView:
    """The signals of a dataset: the Errors first, then the Issues, each group by
    the number of columns touched, then by its figure, then by its code."""
    found: dict[tuple[str, str, str], list[tuple[ColumnView, int, bool]]] = defaultdict(list)
    for column, item in zip(columns, findings, strict=True):
        for finding in (*item.errors.items, *item.issues.items):
            if finding.count is None:
                continue
            found[(finding.cls, finding.code, finding.unit)].append(
                (column, finding.count, finding.accuracy == "lower_bound")
            )
    signals = []
    for (cls, code, unit), terms in found.items():
        total = sum(count for _, count, _ in terms)
        largest = max(count for _, count, _ in terms) or 1
        noun = finding_noun(code, unit, total)
        title, subtitle = SIGNAL_TITLES.get(code, (noun[:1].upper() + noun[1:], ""))
        signals.append(
            Signal(
                code=code,
                cls=cls,
                total=total,
                unit=unit,
                title=title,
                subtitle=subtitle,
                noun=noun,
                lower_bound=any(bound for _, _, bound in terms),
                columns=[
                    SignalColumn(
                        field_id=column.id,
                        name=column.name or column.path,
                        count=count,
                        relative_percent=round(100 * count / largest, 1),
                        spellings=(
                            _spellings(column) if code == "categorical.case_variants" else []
                        ),
                    )
                    for column, count, _ in sorted(
                        terms, key=lambda term: (-term[1], term[0].position)
                    )
                ],
                note=SIGNAL_NOTES.get(code),
                target=SIGNAL_TARGETS.get(code),
            )
        )
    signals.sort(
        key=lambda s: (s.cls != "error", -len(s.columns), -s.total, s.code, s.unit)
    )
    incomplete = sum(
        any(listing.state in INCOMPLETE for listing in (item.errors, item.issues))
        for item in findings
    )
    return SignalsView(
        shown=signals[:SIGNALS_SHOWN],
        more=max(0, len(signals) - SIGNALS_SHOWN),
        incomplete_columns=incomplete,
    )
