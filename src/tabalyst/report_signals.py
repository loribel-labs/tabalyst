# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""KPIs of the overview: the signals and the quality of the columns.

Both are sums over the findings of every column (contract summary-table.md 7.5):
the signals say what the checks found, with the columns behind each figure; the
quality says how many columns have Errors, Issues or nothing. Built with the
Report and stored in the dataset table summary (section 20); the models are in
``summary_models``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from tabalyst.report_finding_details import variant_details
from tabalyst.report_findings import ColumnFindings, FindingList
from tabalyst.report_views import ColumnView
from tabalyst.summary_models import (
    FindingRef,
    QualityColumn,
    QualityView,
    Signal,
    SignalColumn,
    SignalsView,
    Spelling,
    StateCount,
    ValidationList,
)

__all__ = ["quality_view", "signals_view"]

# Signals written as a tile; the others are counted ("+2 additional signals").
SIGNALS_SHOWN = 12
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
# The states of a check that looked at values, whatever it found.
COVERED = ("detected", "none_detected", "partial")


def _list(name: str, lists: Sequence[FindingList]) -> ValidationList:
    counts = {state: 0 for state in STATE_ORDER}
    for listing in lists:
        counts[listing.state] += 1
    return ValidationList(
        name=name,
        with_findings=counts["detected"],
        states=[
            StateCount(state=state, columns=counts[state])
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
                findings=[
                    FindingRef(
                        code=finding.code,
                        cls=finding.cls,
                        count=finding.count,
                        unit=finding.unit,
                        accuracy=finding.accuracy,
                        percent=finding.share.percent if finding.share else None,
                    )
                    for finding in found
                ],
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


def _populations(findings: Sequence[ColumnFindings]) -> dict[tuple[str, str], int]:
    """What each check was run on, summed over the columns it covered, by class and code.

    Why: a share of "the columns that have the finding" would overstate it; the
    denominator is every value the check looked at, finding or not.
    """
    sizes: dict[tuple[str, str], int] = defaultdict(int)
    for item in findings:
        for cls, listing in (("error", item.errors), ("issue", item.issues)):
            for assessment in listing.assessments:
                if assessment.state in COVERED and assessment.eligible is not None:
                    sizes[(cls, assessment.code)] += assessment.eligible
    return sizes


def signals_view(
    columns: Sequence[ColumnView], findings: Sequence[ColumnFindings]
) -> SignalsView:
    """The signals of a dataset: the Errors first, then the Issues, each group by
    the number of columns touched, then by its figure, then by its code."""
    found: dict[tuple[str, str, str], list[tuple[ColumnView, int, bool]]] = defaultdict(list)
    open_population: set[tuple[str, str, str]] = set()
    for column, item in zip(columns, findings, strict=True):
        for finding in (*item.errors.items, *item.issues.items):
            if finding.count is None:
                continue
            key = (finding.cls, finding.code, finding.unit)
            found[key].append((column, finding.count, finding.accuracy == "lower_bound"))
            if finding.population.size is None:
                open_population.add(key)
    sizes = _populations(findings)
    signals = []
    for (cls, code, unit), terms in found.items():
        total = sum(count for _, count, _ in terms)
        largest = max(count for _, count, _ in terms) or 1
        signals.append(
            Signal(
                code=code,
                cls=cls,
                total=total,
                unit=unit,
                lower_bound=any(bound for _, _, bound in terms),
                population=None
                if (cls, code, unit) in open_population
                else sizes.get((cls, code)) or None,
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
