# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What the page of one column prints beyond the stored summary: its findings with their
details, remarks, checks, formats and shape block.

Assembles members built with the document (``summary``) and the views of the column into
the blocks of the page; the template prints them and computes nothing (contract
column-page.md 4, 6). The models are never serialized.
"""

from __future__ import annotations

from tabalyst.report_labels import (
    PAGE_DATE_ORDERS,
    PAGE_SHAPE,
    PAGE_SHAPE_KIND,
    values_lead,
)
from tabalyst.report_overview import overview_sentence
from tabalyst.report_preview import CheckLine, FindingPreview, check_lines
from tabalyst.report_table import FindingDetailView, column_finding_views, page_findings
from tabalyst.report_uniqueness import UniquenessView, page_type_name, uniqueness_view
from tabalyst.report_views import ColumnView, QualityItem
from tabalyst.result_model import ResultModel
from tabalyst.summary_models import VariantDetails


class PageFinding(ResultModel):
    """An Error or an Issue of the column with the detail that explains it."""

    preview: FindingPreview
    detail: FindingDetailView | None
    variants: VariantDetails | None
    # Set on the raw repetition finding: it points to the decomposition of the block.
    uniqueness_link: bool = False


class PageRemark(ResultModel):
    """An informational observation that no finding tells already."""

    item: QualityItem
    detail: FindingDetailView | None


class FormatRow(ResultModel):
    """A format of the column, printed once: how it is read and how many values have it."""

    format: str
    read: str
    count: int
    percent: float


class ShapeBlock(ResultModel):
    """The title of the Shape block, by the technical type of the column."""

    nav: str
    title: str
    lead: str


class Neighbour(ResultModel):
    """The page of the previous or the next column."""

    name: str
    href: str


class ColumnPage(ResultModel):
    """The blocks of a column page that the stored summary does not hold as they are."""

    sentence: str
    errors: int
    issues: int
    findings: list[PageFinding]
    remarks: list[PageRemark]
    # The checks that ran and found nothing, once each.
    checks: list[CheckLine]
    formats: list[FormatRow]
    shape: ShapeBlock | None
    values_lead: str
    uniqueness: UniquenessView | None = None
    # Replaces the usual type name where the uniqueness was assessed.
    type_name: str | None = None
    previous: Neighbour | None = None
    next: Neighbour | None = None


def _formats(column: ColumnView) -> list[FormatRow]:
    """Each format once: the date profile when the column has one (it adds the day-month
    order), else what the detectors recognized."""
    if column.date_profile is not None and column.date_profile.formats:
        return [
            FormatRow(
                format=item.format,
                read=PAGE_DATE_ORDERS.get(item.order or "", ""),
                count=item.count,
                percent=item.percent,
            )
            for item in column.date_profile.formats
        ]
    seen: set[str] = set()
    rows = []
    for detector in column.detectors:
        for item in detector.formats:
            if item.format in seen:
                continue
            seen.add(item.format)
            rows.append(
                FormatRow(
                    format=item.format,
                    read=detector.id.replace("_", " "),
                    count=item.count,
                    percent=item.percent,
                )
            )
    return rows


def _shape(column: ColumnView) -> ShapeBlock | None:
    if not (column.numeric or column.date_profile or column.string_profile or column.insights):
        return None
    nav, title, lead = PAGE_SHAPE[PAGE_SHAPE_KIND.get(column.inferred_type, "other")]
    return ShapeBlock(nav=nav, title=title, lead=lead)


def column_page(
    column: ColumnView,
    previous: Neighbour | None = None,
    following: Neighbour | None = None,
) -> ColumnPage:
    """The page of ``column``, from its stored summary and its views."""
    summary = column.summary
    if summary is None:
        raise ValueError(
            f"Column {column.id!r} has no summary: build the Report with its summaries."
        )
    errors, issues = page_findings(column)
    details = column_finding_views(column)
    by_id = {item.observation.id: item for item in column.quality}
    told: set[str] = set()
    findings = []
    found = summary.findings
    uniqueness = uniqueness_view(summary.identifier_uniqueness)
    for listing, cell in ((found.errors, errors), (found.issues, issues)):
        # The previews follow the order of the items of their list.
        for finding, preview in zip(listing.items, cell.previews):
            observation = next((by_id[b] for b in finding.basis if b in by_id), None)
            rule = observation.observation.rule if observation else None
            if observation:
                told.add(observation.observation.id)
            findings.append(
                PageFinding(
                    preview=preview,
                    detail=details.get(rule) if rule else None,
                    variants=summary.finding_details.variants if rule == "variant_groups" else None,
                    uniqueness_link=uniqueness is not None
                    and uniqueness.case != "A"
                    and preview.code == "identifier.repetition",
                )
            )
    remarks = [
        PageRemark(item=item, detail=details.get(item.observation.rule))
        for item in column.quality
        if item.observation.status == "informational" and item.observation.id not in told
    ]
    checks: list[CheckLine] = []
    for listing in (summary.findings.errors, summary.findings.issues):
        for line in check_lines(listing):
            if line.state == "none_detected" and all(line.code != c.code for c in checks):
                checks.append(line)
    return ColumnPage(
        sentence=overview_sentence(summary.overview),
        errors=len(errors.previews),
        issues=len(issues.previews),
        findings=findings,
        remarks=remarks,
        checks=checks,
        formats=_formats(column),
        shape=_shape(column),
        values_lead=values_lead(
            len(summary.values.values),
            summary.values.sampled_distinct_count,
            summary.values.selection,
            column.distinct_count,
        ),
        uniqueness=uniqueness,
        type_name=page_type_name(uniqueness),
        previous=previous,
        next=following,
    )
