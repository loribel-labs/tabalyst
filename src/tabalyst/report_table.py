# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rows of the Summary table: what each of the eight cells prints.

Assembles the summary stored with each column (classification, Overview, findings,
Details) into the cells; the template prints a row and computes nothing (contract
summary-table.md 7.3, 20). The words of a cell are written here from the stored
codes and numbers; the rows themselves are not serialized.
"""

from __future__ import annotations

from tabalyst.report_labels import (
    CAVEAT_STATES,
    FAMILY_LABELS,
    LIST_STATE_LABELS,
    LIST_STATE_TITLES,
    plural,
    type_label,
)
from tabalyst.report_preview import (
    CheckLine,
    FindingPreview,
    check_lines,
    preview_of,
)
from tabalyst.report_views import ColumnView, DatasetView
from tabalyst.result_model import ResultModel
from tabalyst.summary_models import (
    ColumnSummary,
    Details,
    FindingList,
    Flag,
    MissingFinding,
    QualityView,
    SignalsView,
    VariantDetails,
    finding_text,
)

# Finding labels written in a cell; the rest is in the preview of "+3 more"
# (decision 7, lot R9b).
LABELS_SHOWN = 2

class FindingsCell(ResultModel):
    """The Errors or the Issues of a row: the state of the list, the labels of its
    findings and what the checks that found nothing did not cover."""

    state: str
    state_label: str
    state_title: str
    labels: list[str]
    # The preview of every finding of the list, in the order of the labels: the
    # first ``LABELS_SHOWN`` are written in the cell, the others behind "+N more".
    previews: list[FindingPreview]
    # "1 check partially assessed": only on a list that found something, whose
    # state would otherwise hide a check that did not cover everything.
    caveat: str | None
    # The checks it speaks of, and (for a list that found nothing) every check
    # that applies, so that its state can be explained.
    caveat_checks: list[CheckLine]
    checks: list[CheckLine]
    # Sort key: the number of findings.
    order: int

    @property
    def shown(self) -> list[FindingPreview]:
        return self.previews[:LABELS_SHOWN]

    @property
    def rest(self) -> list[FindingPreview]:
        return self.previews[LABELS_SHOWN:]


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
    error_count: int
    issue_count: int
    observation_count: int
    signals: SignalsView
    quality: QualityView


def _caveat(listing: FindingList) -> tuple[str | None, list[CheckLine]]:
    """The checks of a list that found something but did not complete."""
    if listing.state != "detected":
        return None, []
    found = {item.code for item in listing.items}
    incomplete = [
        item
        for item in listing.assessments
        if item.state in CAVEAT_STATES and item.code not in found
    ]
    if not incomplete:
        return None, []
    words = []
    for state, phrase in CAVEAT_STATES.items():
        count = sum(item.state == state for item in incomplete)
        if count:
            words.append(f"{plural(count, 'check', 'checks')} {phrase}")
    lines = [
        line
        for line in check_lines(listing, incomplete_only=True)
        if line.code not in found
    ]
    return ", ".join(words), lines


def _cell(listing: FindingList) -> FindingsCell:
    labels = [finding_text(item) for item in listing.items]
    caveat, caveat_checks = _caveat(listing)
    return FindingsCell(
        state=listing.state,
        state_label=LIST_STATE_LABELS[listing.state],
        state_title=LIST_STATE_TITLES[listing.state],
        labels=labels,
        previews=[preview_of(item, listing.assessments) for item in listing.items],
        caveat=caveat,
        caveat_checks=caveat_checks,
        checks=[] if listing.items else check_lines(listing),
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


def _summary(column: ColumnView) -> ColumnSummary:
    if column.summary is None:
        raise ValueError(
            f"Column {column.id!r} has no summary: build the Report with its summaries."
        )
    return column.summary


def column_row(column: ColumnView, dataset_id: str) -> ColumnRow:
    """The row of a column, written from its stored summary."""
    summary = _summary(column)
    classification = column.classification
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
        overview=summary.overview.text,
        missing=_missing(summary.findings.missing),
        errors=_cell(summary.findings.errors),
        issues=_cell(summary.findings.issues),
        details=summary.details,
        variants=summary.variants,
        flags=list(summary.flags),
    )


def page_findings(column: ColumnView) -> tuple[FindingsCell, FindingsCell]:
    """The Errors and the Issues of one column for its own page, with the previews
    the table prints."""
    found = _summary(column).findings
    return _cell(found.errors), _cell(found.issues)


def column_table(dataset: DatasetView) -> ColumnTable:
    """The table of a dataset, one row per column in the order of the report."""
    table = dataset.table
    if table is None:
        raise ValueError(
            f"Dataset {dataset.id!r} has no table summary: build the Report with its summaries."
        )
    return ColumnTable(
        rows=[column_row(column, dataset.id) for column in dataset.columns],
        error_count=table.error_count,
        issue_count=table.issue_count,
        observation_count=table.observation_count,
        signals=table.signals,
        quality=table.quality,
    )
