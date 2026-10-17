# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rows of the Columns table: what each of the eight cells prints.

Assembles the views of the other modules (classification, Overview, findings,
Details) at render time; the template prints a row and computes nothing
(contract summary-table.md 7.3). Nothing is serialized.
"""

from __future__ import annotations

from typing import Literal

from tabalyst.models import ResultModel
from tabalyst.report_details import Details, details_for
from tabalyst.report_finding_details import VariantDetails, variant_details
from tabalyst.report_findings import (
    ColumnFindings,
    FindingList,
    MissingFinding,
    column_findings,
)
from tabalyst.report_labels import (
    CAVEAT_STATES,
    FAMILY_LABELS,
    LIST_STATE_LABELS,
    LIST_STATE_TITLES,
    plural,
    type_label,
)
from tabalyst.report_overview import overview_text
from tabalyst.report_signals import (
    QualityView,
    SignalsView,
    finding_text,
    quality_view,
    signals_view,
)
from tabalyst.report_views import ColumnView, DatasetView

# Finding labels written in a cell; the rest is counted ("+3 more"). The preview
# that lists them all is lot R9b (decision 7).
LABELS_SHOWN = 2

Flag = Literal["issue", "obs"]


class FindingsCell(ResultModel):
    """The Errors or the Issues of a row: the state of the list, the labels of its
    findings and what the checks that found nothing did not cover."""

    state: str
    state_label: str
    state_title: str
    labels: list[str]
    shown: list[str]
    more: int
    # "1 check partially assessed": only on a list that found something, whose
    # state would otherwise hide a check that did not cover everything.
    caveat: str | None
    caveat_title: str | None
    # Sort key: the number of findings.
    order: int


class MissingCell(ResultModel):
    """Positions with no present value, as the Missing view states them."""

    count: int
    percent: float | None
    state: str


class ColumnRow(ResultModel):
    """One row of the table. Its identity is the dataset id plus the field id,
    never the displayed name (RF-02, CA-03)."""

    dataset_id: str
    field_id: str
    name: str
    path: str
    position: int
    family: str
    family_label: str
    # ``family/type``: the type alone is not unique across families (CA-02).
    type_key: str
    type_label: str
    overview: str
    missing: MissingCell
    errors: FindingsCell
    issues: FindingsCell
    details: Details
    # The groups of spelling variants behind the Issue of the same name, for the hover.
    variants: VariantDetails | None
    flags: list[Flag]

    @property
    def flag_text(self) -> str:
        return " ".join(self.flags)


class ColumnTable(ResultModel):
    """The rows of a dataset and the counts of the segment above them."""

    rows: list[ColumnRow]
    issue_count: int
    observation_count: int
    signals: SignalsView
    quality: QualityView


def _caveat(listing: FindingList) -> tuple[str | None, str | None]:
    """The checks of a list that found something but did not complete."""
    if listing.state != "detected":
        return None, None
    found = {item.code for item in listing.items}
    incomplete = [
        item
        for item in listing.assessments
        if item.state in CAVEAT_STATES and item.code not in found
    ]
    if not incomplete:
        return None, None
    words = []
    for state, phrase in CAVEAT_STATES.items():
        count = sum(item.state == state for item in incomplete)
        if count:
            words.append(f"{plural(count, 'check', 'checks')} {phrase}")
    codes = ", ".join(sorted({item.code for item in incomplete}))
    return ", ".join(words), codes


def _cell(listing: FindingList) -> FindingsCell:
    labels = [finding_text(item) for item in listing.items]
    caveat, title = _caveat(listing)
    return FindingsCell(
        state=listing.state,
        state_label=LIST_STATE_LABELS[listing.state],
        state_title=LIST_STATE_TITLES[listing.state],
        labels=labels,
        shown=labels[:LABELS_SHOWN],
        more=max(0, len(labels) - LABELS_SHOWN),
        caveat=caveat,
        caveat_title=title,
        order=len(labels),
    )


def _missing(missing: MissingFinding) -> MissingCell:
    # Two decimals like ``ColumnProfile.missing_percent``: the figure of the JSON.
    percent = missing.share.percent
    return MissingCell(
        count=missing.count,
        percent=None if percent is None else round(percent, 2),
        state=missing.state,
    )


def column_row(
    column: ColumnView,
    dataset_id: str,
    findings: ColumnFindings | None = None,
) -> ColumnRow:
    """The row of a column. ``findings`` replaces ``column_findings(column)``."""
    found = findings or column_findings(column)
    classification = column.classification
    flags: list[Flag] = []
    if found.errors.items or found.issues.items:
        flags.append("issue")
    if column.has_observations:
        flags.append("obs")
    return ColumnRow(
        dataset_id=dataset_id,
        field_id=column.id,
        name=column.name,
        path=column.path,
        position=column.position,
        family=classification.family,
        family_label=FAMILY_LABELS[classification.family],
        type_key=f"{classification.family}/{classification.type}",
        type_label=type_label(classification.family, classification.type),
        overview=overview_text(column),
        missing=_missing(found.missing),
        errors=_cell(found.errors),
        issues=_cell(found.issues),
        details=details_for(column),
        variants=variant_details(column),
        flags=flags,
    )


def column_table(dataset: DatasetView) -> ColumnTable:
    """The table of a dataset, one row per column in the order of the report."""
    findings = [column_findings(column) for column in dataset.columns]
    rows = [
        column_row(column, dataset.id, found)
        for column, found in zip(dataset.columns, findings, strict=True)
    ]
    return ColumnTable(
        rows=rows,
        issue_count=sum("issue" in row.flags for row in rows),
        observation_count=sum("obs" in row.flags for row in rows),
        signals=signals_view(dataset.columns, findings),
        quality=quality_view(dataset.columns, findings),
    )
