# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The chart pages of a Report (``docs/dev/report/chart-pages.md``): what each page
draws, read from the report JSON alone, and the library the pages load.

Pure: no file, no source. ``reporting.render_chart_page`` prints what this module
builds and ``static/charts.js`` draws it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import quote

from tabalyst.models import ReportProfile
from tabalyst.report_insights import block_line, missing_blocks
from tabalyst.report_views import InsightLine
from tabalyst.scanner.secondpass.models import MissingPatternsResult


@dataclass(frozen=True, slots=True)
class Library:
    """A script the detail pages load from a CDN, pinned to one published file:
    ``integrity`` is the SRI hash of that file, so it cannot be swapped."""

    name: str
    version: str
    url: str
    integrity: str


# Moving to an embedded copy changes this constant and the templates, nothing else
# (chart-pages.md 5). The hash was computed from the published file.
ECHARTS = Library(
    name="Apache ECharts",
    version="6.1.0",
    url="https://cdn.jsdelivr.net/npm/echarts@6.1.0/dist/echarts.min.js",
    integrity="sha384-C2iskrW/uPW46KzOjrvJIQo4YkV8lkD+QS0CrDN18IIPIpT/g2USu8bTP3nvmIAD",
)

# The patterns the plot draws; the table lists every pattern the result lists.
DRAWN = 20
# The file of each topic, stable once released.
CHART_FILES = {"missing": "charts-missing.html"}
TOPIC_TITLES = {"missing": "Missing values"}
# Why a dataset has no section on a chart page, in words.
LEFT_OUT_REASONS = {
    "no_missing_values": "fewer than two columns lack a value",
    "too_many_columns": "more columns lack a value than deep.missing.max_columns allows",
    "withheld_columns": "a column that lacks values is withheld by the exposure setting",
    "analysis_failed": "the second pass did not count the combinations",
}
_HIDDEN = {"mask", "hide"}


@dataclass(frozen=True, slots=True)
class ColumnRow:
    """A column that lacks values: the set size of the plot, with the link to its
    column page."""

    field: str
    display: str
    position: int
    missing: int
    share: str
    href: str | None


@dataclass(frozen=True, slots=True)
class PatternRow:
    """A listed pattern: the exact set of columns some records lack a value in."""

    names: tuple[str, ...]
    size: int
    count: int
    share: str


@dataclass(frozen=True, slots=True)
class MissingSection:
    """The combinations of missing values of one dataset, as its section of
    ``charts-missing.html`` prints and draws them. ``data`` is what ``charts.js``
    reads: the columns in document order, their counts, and each listed pattern as
    its count and the positions of its columns."""

    dataset: str
    result: MissingPatternsResult
    lacking: int
    columns: list[ColumnRow]
    patterns: list[PatternRow]
    lines: list[InsightLine]
    data: dict[str, object] = field(default_factory=dict)

    @property
    def drawn(self) -> int:
        """The patterns the plot draws at first."""
        return min(DRAWN, len(self.patterns))


@dataclass(frozen=True, slots=True)
class LeftOut:
    """A dataset without a section on a chart page, and why (a key of ``LEFT_OUT_REASONS``)."""

    topic: str
    dataset: str
    reason: str

    @property
    def words(self) -> str:
        """The reason in words."""
        return LEFT_OUT_REASONS[self.reason]


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "0%"


def _reason(profile: ReportProfile, dataset: str) -> str:
    """Why a dataset has no combinations, from the plan of the second pass."""
    deep = profile.analyses.deep if profile.analyses is not None else None
    if deep is None:
        return "analysis_failed"
    for candidate in deep.plan.candidates:
        if candidate.analyzer == "missing_patterns" and candidate.dataset == dataset:
            if "too_many_columns" in candidate.applicability.reasons:
                return "too_many_columns"
            return "analysis_failed"
    return "no_missing_values"


def missing_sections(
    profile: ReportProfile,
    column_links: Mapping[tuple[str, str], str] | None = None,
) -> tuple[list[MissingSection], list[LeftOut]]:
    """The sections of ``charts-missing.html``, one per dataset with combinations
    counted, in the order of the report, and the datasets left out with their reason.

    ``column_links`` maps a dataset and a field id to the href of its column page,
    relative to the folder of the detail pages. A result that names a column the
    report withholds is left out whole: its counts would describe that column.
    """
    links = column_links or {}
    found: dict[str, MissingPatternsResult] = {}
    deep = profile.analyses.deep if profile.analyses is not None else None
    for item in deep.analyses if deep is not None else []:
        if item.analyzer != "missing_patterns" or item.status not in ("complete", "limited"):
            continue
        if isinstance(item.result, MissingPatternsResult):
            found[item.dataset] = item.result
    sections: list[MissingSection] = []
    left: list[LeftOut] = []
    for dataset in profile.datasets:
        exposure = {field.id: field.exposure for field in dataset.fields}
        result = found.get(dataset.id)
        if result is None:
            left.append(LeftOut("missing", dataset.id, _reason(profile, dataset.id)))
            continue
        if any(exposure.get(column.field) in _HIDDEN for column in result.columns):
            left.append(LeftOut("missing", dataset.id, "withheld_columns"))
            continue
        sections.append(_section(dataset.id, result, links))
    return sections, left


def _section(
    dataset: str, result: MissingPatternsResult, links: Mapping[tuple[str, str], str]
) -> MissingSection:
    position = {column.field: index for index, column in enumerate(result.columns)}
    names = {column.field: column.display for column in result.columns}
    columns = sorted(
        (
            ColumnRow(
                field=column.field,
                display=column.display,
                position=position[column.field],
                missing=column.missing,
                share=_share(column.missing, result.records),
                href=links.get((dataset, column.field)),
            )
            for column in result.columns
        ),
        key=lambda row: (-row.missing, position[row.field]),
    )
    patterns = [
        PatternRow(
            names=tuple(names[name] for name in pattern.columns),
            size=len(pattern.columns),
            count=pattern.count,
            share=_share(pattern.count, result.records),
        )
        for pattern in result.listed
    ]
    data: dict[str, object] = {
        "records": result.records,
        "columns": [column.display for column in result.columns],
        "missing": [column.missing for column in result.columns],
        "patterns": [
            [pattern.count, [position[name] for name in pattern.columns]]
            for pattern in result.listed
        ],
        "drawn": DRAWN,
    }
    return MissingSection(
        dataset=dataset,
        result=result,
        lacking=result.records - result.complete_records,
        columns=columns,
        patterns=patterns,
        lines=[block_line(block) for block in missing_blocks(result)],
        data=data,
    )


def column_charts(
    sections: list[MissingSection], dataset: str, field_id: str
) -> list[tuple[str, str]]:
    """The chart pages that name a column, as ``(title, href)`` from a page of the
    same folder: ``charts-missing.html#<dataset>`` for a column that lacks values."""
    return [
        (TOPIC_TITLES["missing"], f"{CHART_FILES['missing']}#{quote(section.dataset, safe='')}")
        for section in sections
        if section.dataset == dataset
        and any(column.field == field_id for column in section.result.columns)
    ]
