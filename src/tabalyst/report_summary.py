# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Builds the summary of each column and the table summary of each dataset.

Runs once when the Report document is built (contract summary-table.md 20): the
findings, the Overview, the Details and the spelling variants of a column, with
the exposure applied, then the signals and the quality of the dataset. The pages
only read what is stored.
"""

from __future__ import annotations

from collections.abc import Sequence

from tabalyst.models import ColumnProfile, ReportProfile
from tabalyst.report_details import STATES, details_for, exposed_values
from tabalyst.report_finding_details import variant_details
from tabalyst.report_findings import column_findings
from tabalyst.report_overview import overview_for
from tabalyst.report_preview import expose_examples
from tabalyst.report_signals import quality_view, signals_view
from tabalyst.report_views import ColumnView
from tabalyst.summary_models import (
    ColumnFindings,
    ColumnSummary,
    FindingList,
    Flag,
    TableSummary,
)


def _exposed(column: ColumnView, listing: FindingList) -> FindingList:
    return listing.model_copy(
        update={"items": [expose_examples(column, item) for item in listing.items]}
    )


def column_summary(column: ColumnView) -> ColumnSummary:
    """Everything the Summary table and the previews say about a column."""
    found = column_findings(column)
    findings = ColumnFindings(
        field=found.field,
        missing=found.missing,
        errors=_exposed(column, found.errors),
        issues=_exposed(column, found.issues),
    )
    flags: list[Flag] = []
    if findings.errors.items:
        flags.append("error")
    if findings.errors.items or findings.issues.items:
        flags.append("issue")
    if column.has_observations:
        flags.append("obs")
    return ColumnSummary(
        findings=findings,
        overview=overview_for(column),
        details=details_for(column),
        values=exposed_values(column),
        variants=variant_details(column),
        flags=flags,
    )


def table_summary(
    columns: Sequence[ColumnView], summaries: Sequence[ColumnSummary]
) -> TableSummary:
    """The counts and the KPIs above the Summary table of a dataset."""
    findings = [summary.findings for summary in summaries]
    return TableSummary(
        error_count=sum("error" in summary.flags for summary in summaries),
        issue_count=sum("issue" in summary.flags for summary in summaries),
        observation_count=sum("obs" in summary.flags for summary in summaries),
        signals=signals_view(columns, findings),
        quality=quality_view(columns, findings),
    )


def _current(column: ColumnProfile) -> bool:
    """Whether the summary of a column was built for the exposure it declares."""
    # Why: a summary holds values already through an exposure; one built for another
    # exposure would print values the column no longer allows.
    return (
        column.summary is not None
        and column.summary.details.state == STATES[column.exposure or "show"]
    )


def has_summaries(profile: ReportProfile) -> bool:
    """Whether every column and every dataset of the Report carries a summary built
    for the exposure of its column."""
    return all(
        dataset.table is not None and all(_current(column) for column in dataset.columns)
        for dataset in profile.report.datasets
    )


def attach_summaries(profile: ReportProfile) -> ReportProfile:
    """Fill the summary of every column and the table summary of every dataset of
    ``profile``, in place, from the views of the document, and return it."""
    # Imported here: ``reporting`` renders what this module builds.
    from tabalyst.reporting import build_dataset_views

    views = {view.id: view for view in build_dataset_views(profile)}
    for dataset in profile.report.datasets:
        view = views[dataset.id]
        summaries = [column_summary(column) for column in view.columns]
        for column, summary in zip(dataset.columns, summaries, strict=True):
            column.summary = summary
        dataset.table = table_summary(view.columns, summaries)
    return profile
