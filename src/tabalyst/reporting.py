# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Render self-contained analysis results as an interactive HTML report."""

import re
import unicodedata
from functools import cache
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from jinja2 import DictLoader, Environment, StrictUndefined
from markupsafe import Markup, escape

from tabalyst._version import get_version
from tabalyst.errors import InputError
from tabalyst.models import ReportProfile
from tabalyst.report_column_page import Neighbour, column_page
from tabalyst.report_config import ReportConfig
from tabalyst.report_deep import column_analyses, second_pass_view
from tabalyst.report_details import details_withheld, exposed_evidence
from tabalyst.report_finding_details import exposed_variant_groups
from tabalyst.report_insights import (
    FAMILY_ORDER,
    dataset_insights,
    family_title,
    scan_insight,
    shown_cards,
)
from tabalyst.report_labels import (
    ACCURACY_TITLES,
    ACCURACY_WORDS,
    DEEP_REASONS,
    DETAILS_STATES,
    DETAILS_TITLES,
    FAMILY_LABELS,
    MODE_WORDS,
    ORIGIN_WORDS,
    OUTCOME_WORDS,
    PAGE_NO_EXAMPLE,
    PREVIEW_CHECKS_TITLE,
    SIGNAL_CLASS_WORDS,
    TABLE_AT_LEAST,
    TABLE_MORE,
    TYPE_LABELS,
    format_number,
)
from tabalyst.report_profile import build_views
from tabalyst.report_relations import relations_view
from tabalyst.report_sections import (
    cardinality_view,
    character_entries,
    character_view,
    limits_view,
    pattern_entries,
    pattern_view,
    quality_view,
    rows_view,
)
from tabalyst.report_summary import attach_summaries, has_summaries
from tabalyst.report_table import column_table, finding_detail_views
from tabalyst.report_uniqueness import uniqueness_settings
from tabalyst.report_views import (
    ColumnAnalyses,
    ColumnView,
    DatasetView,
    InsightCard,
    LimitView,
    PatternRow,
    QualityItem,
)
from tabalyst.scan_document import load_report
from tabalyst.scan_reuse import read_json_document
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.secondpass.models import DistinctCount

# Sections of the report that are not written: empty set when every section is active.
HIDDEN_SECTIONS: frozenset[str] = frozenset()


def cell_text(values: list[str | None]) -> str:
    """The text of a cell of the row sample: the values of an items path joined,
    a JSON null written ``null``."""
    return ", ".join("null" if value is None else value for value in values)


# Most rows a section prints, whatever the report keeps: the document holds
# them all, the page stays light (HTML-07). A paged table shows 25 at a time.
DISPLAY_LIMITS = {"findings": 500, "patterns": 400, "limits": 500, "rows": 300, "relations": 20, "insights": 25, "special_characters": 20}


def format_seconds(seconds: float) -> str:
    """Display elapsed time with no more than two decimal places."""
    return f"{seconds:.2f}".rstrip("0").rstrip(".")


def format_size(size_bytes: int) -> str:
    """Display source size in KB, switching to MB at one mebibyte."""
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"


# Separators after which a long name may break: snake case, paths and dates.
# One theme token per family (theme.css), so that the bar of the dashboard card and
# its legend read the same colour in both themes.
FAMILY_COLORS = {family: f"var(--fam-{family})" for family in FAMILY_LABELS}
_BREAKS = re.compile(r"(?<=[_./-])")


def breakable(name: str) -> Markup:
    """``name`` escaped, with a line break opportunity after each separator,
    so that a table squeezed for room narrows its column instead of
    scrolling."""
    return Markup("<wbr>").join(escape(part) for part in _BREAKS.split(name))


def load_profile(path: str | Path) -> ReportProfile:
    """Validate and load a report document (format ``tabalyst.report``)."""
    document = read_json_document(Path(path))
    if not isinstance(document, dict):
        raise InputError(f"Not a report: {path}.")
    return load_report(document, Path(path))


def dataset_views(profile: ReportProfile) -> list[DatasetView]:
    """The projections of a report with the facts of their fields, the figures
    derived from them and the findings of the scan, all read from the document
    (``report_views``, ``report_sections``). A document written without its
    summaries gets them first, once (contract summary-table.md 20.4)."""
    if not has_summaries(profile):
        attach_summaries(profile)
    return build_dataset_views(profile)


def build_dataset_views(profile: ReportProfile) -> list[DatasetView]:
    """The views of ``dataset_views`` without the check of the summaries."""
    config = ReportConfig.from_presentation(profile.report.config, profile.config)
    datasets = {dataset.id: dataset for dataset in profile.datasets}
    entries = pattern_entries(profile.derived)
    maps = character_entries(profile.derived)
    deep = column_analyses(profile.analyses)
    views = []
    for projection in profile.report.datasets:
        base = datasets[projection.id]
        fields = {field.id: field for field in base.fields}
        names = {field.id: (field.display, None) for field in base.fields}
        names.update(
            (column.id, (column.name or column.path, column.position))
            for column in projection.columns
        )
        quality = quality_view(profile.observations, projection.id, names)
        limits = limits_view(
            profile.observations,
            profile.diagnostics,
            base,
            {column.id for column in projection.columns},
        )
        # Grouped once: a dataset can have thousands of fields and findings.
        findings: dict[str, list[QualityItem]] = {}
        for item in quality.items:
            findings.setdefault(item.observation.field or "", []).append(item)
        bounded: dict[str, list[LimitView]] = {}
        for item in limits.items:
            bounded.setdefault(item.column_id or "", []).append(item)
        exposure = {column.id: column.exposure for column in projection.columns}
        insights = dataset_insights(profile.analyses, projection.id, exposure)
        # Indexed once: a dataset can have thousands of fields and cards.
        by_field: dict[str, list[InsightCard]] = {}
        for card in insights:
            if card.scope == "dataset":
                continue
            for field_id in card.fields:
                by_field.setdefault(field_id, []).append(card)
        columns = []
        for column in projection.columns:
            field = fields[column.id]
            derived = build_views(field, column.inferred_type, config)
            results = deep.get((projection.id, column.id), ColumnAnalyses())
            exact = (
                results.distinct.distinct
                if isinstance(results.distinct, DistinctCount)
                else None
            )
            columns.append(
                ColumnView(
                    **dict(column),
                    field=field,
                    numeric=derived.numeric,
                    date_profile=derived.date_profile,
                    string_profile=derived.string_profile,
                    distinct=cardinality_view(field, exact),
                    deep=results,
                    insights=_column_insights(
                        by_field.get(column.id, []),
                        column.id,
                        column.name or column.path,
                        field,
                        results,
                        column.exposure,
                    ),
                    quality=findings.get(column.id, []),
                    observations_state=(
                        "unavailable"
                        if not quality.available
                        else "truncated"
                        if quality.truncated
                        else "complete"
                    ),
                    limits=bounded.get(column.id, []),
                    characters=character_view(
                        maps.get((projection.id, column.id)), results.characters
                    ),
                    patterns=pattern_view(
                        field,
                        entries.get((projection.id, column.id)),
                        profile.derived,
                        results.patterns,
                    ),
                )
            )
        views.append(
            DatasetView(
                **{**dict(projection), "columns": columns},
                quality=quality,
                limits=limits,
                rows=rows_view(base),
                patterns_available=bool(entries),
                quality_issue_column_count=sum(c.has_quality_issues for c in columns),
                observation_column_count=sum(c.has_observations for c in columns),
                second_pass=second_pass_view(profile.analyses, projection.id),
                relations=relations_view(profile.analyses, projection.id),
                insights=[card for card in insights if card.scope != "column"],
            )
        )
    return views


def _column_insights(
    cards: list[InsightCard],
    column_id: str,
    display: str,
    field: FieldResult,
    results: ColumnAnalyses,
    exposure: str | None,
) -> list[InsightCard]:
    """The cards of a column: ``cards`` (its own analyses and those of a pair it
    belongs to) and what the report derives from its Scan field."""
    derived = scan_insight(field, display, column_id, results.periods, exposure in ("mask", "hide"))
    return [*cards, derived] if derived is not None else list(cards)


def column_pages(
    profile: ReportProfile,
    report_path: Path,
    views: list[DatasetView] | None = None,
) -> list[tuple[Path, DatasetView, ColumnView]]:
    """Name standalone column pages in source order, across all datasets.
    ``views`` are the ``dataset_views`` of ``profile`` when the caller has them."""
    pages = []
    number = 0
    for dataset in views if views is not None else dataset_views(profile):
        for column in dataset.columns:
            number += 1
            plain = unicodedata.normalize("NFKD", column.name).encode("ascii", "ignore").decode()
            slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:48].rstrip("-")
            slug = slug or "unnamed"
            path = report_path.with_suffix("") / f"col-{number:02d}-{slug}.html"
            pages.append((path, dataset, column))
    return pages


def _neighbour(
    pages: list[tuple[Path, DatasetView, ColumnView]], index: int, other: int
) -> Neighbour | None:
    """The page at ``other`` as a link from the page at ``index``, if it is in the same dataset."""
    if not 0 <= other < len(pages) or pages[other][1].id != pages[index][1].id:
        return None
    path, _, column = pages[other]
    return Neighbour(name=column.name or "(unnamed)", href=quote(path.name))


def column_neighbours(
    pages: list[tuple[Path, DatasetView, ColumnView]],
) -> dict[tuple[str, str], tuple[Neighbour | None, Neighbour | None]]:
    """The previous and the next page of every column page, within its dataset. The pages
    share one directory, so a link is the file name."""
    return {
        (dataset.id, column.id): (
            _neighbour(pages, index, index - 1),
            _neighbour(pages, index, index + 1),
        )
        for index, (_, dataset, column) in enumerate(pages)
    }


@cache
def _macro_template(name: str) -> str:
    """A shared macro file (the insight cards, the tree of patterns), read once for every page of a run."""
    return files("tabalyst").joinpath(f"templates/{name}").read_text(encoding="utf-8")


def _environment() -> Environment:
    environment = Environment(
        autoescape=True,
        undefined=StrictUndefined,
        loader=DictLoader({name: _macro_template(name) for name in ("insights.html", "patterns.html", "characters.html")}),
    )
    environment.filters["count"] = lambda number: f"{number:,}"
    environment.filters["number"] = format_number
    environment.filters["seconds"] = format_seconds
    environment.filters["size"] = format_size
    environment.filters["breakable"] = breakable
    environment.filters["cell_text"] = cell_text
    return environment


def _labels() -> dict[str, object]:
    """The vocabulary every page prints (``report_labels``)."""
    return {
        "acc_words": ACCURACY_WORDS,
        "acc_titles": ACCURACY_TITLES,
        "origin_words": ORIGIN_WORDS,
        "display_limits": DISPLAY_LIMITS,
        "mode_words": MODE_WORDS,
        "outcome_words": OUTCOME_WORDS,
        "deep_reasons": DEEP_REASONS,
        "family_titles": {family: family_title(family) for family in FAMILY_ORDER},
        "type_labels": TYPE_LABELS,
        "table_more": TABLE_MORE,
        "exposed_evidence": exposed_evidence,
        "exposed_variant_groups": exposed_variant_groups,
        "details_withheld": details_withheld,
        "preview_checks_title": PREVIEW_CHECKS_TITLE,
        "signal_class_words": SIGNAL_CLASS_WORDS,
        "hidden_sections": HIDDEN_SECTIONS,
        "table_at_least": TABLE_AT_LEAST,
        "details_states": DETAILS_STATES,
        "details_titles": DETAILS_TITLES,
    }


def _pattern_rows(
    dataset: DatasetView,
) -> list[tuple[ColumnView, PatternRow | None, str]]:
    """One row per pattern of the hierarchy, then the values no pattern holds, with
    the accuracy of the shares (every distinct value, or a sample of them)."""
    rows: list[tuple[ColumnView, PatternRow | None, str]] = []
    for column in dataset.columns:
        entry = column.patterns.entry
        if entry is None:
            continue
        kind = "exact" if entry.population.complete else "sample"
        rows.extend((column, row, kind) for row in column.patterns.rows)
        if column.patterns.outside_distinct:
            rows.append((column, None, kind))
    return rows


def _page_view(
    dataset: DatasetView,
    prefix: str,
    grammar: str,
    column_links: dict[tuple[str, str], str],
) -> dict[str, object]:
    """What the report template reads about one dataset besides the view."""
    pattern_rows = _pattern_rows(dataset)
    pattern_columns = [c for c in dataset.columns if c.patterns.status == "complete"]
    sections = {"overview", "observations", "columns", "transformations"}
    if dataset.limits.present:
        sections.add("limits")
    if pattern_columns:
        sections.add("patterns")
    if any(column.date_profile for column in dataset.columns):
        sections.add("dates")
    return {
        "ds": dataset,
        "table": column_table(dataset),
        "finding_details": {
            (column.id, "variant_groups"): column.summary.finding_details.variants
            for column in dataset.columns
            if column.summary is not None
            and column.summary.finding_details.variants is not None
        },
        "finding_views": finding_detail_views(dataset),
        "insight_cards": shown_cards(dataset.insights, DISPLAY_LIMITS["insights"]),
        # Element ids are prefixed only when the report shows several
        # datasets, so single-dataset reports keep their anchors.
        "px": prefix,
        "sections": sections,
        "numeric_columns": [c for c in dataset.columns if c.numeric],
        "date_columns": [c for c in dataset.columns if c.date_profile],
        "string_columns": [c for c in dataset.columns if c.string_profile],
        "detector_rows": [
            (column, detector)
            for column in dataset.columns
            for detector in column.detectors
        ],
        "variant_rows": [
            (column, group)
            for column in dataset.columns
            for group in column.normalization.variant_groups
        ],
        # The limits section is shown only when something was limited.
        "has_limits": dataset.limits.present,
        "uniqueness_settings": uniqueness_settings(dataset.columns),
        "pattern_columns": pattern_columns,
        "pattern_rows": pattern_rows,
        "pattern_missing": len(dataset.columns) - len(pattern_columns),
        "period_columns": [c for c in dataset.columns if c.deep.periods],
        "pattern_grammar": grammar,
        # The largest sample any column of the dataset keeps in this document.
        "sample_size": max(
            (column.field.values.samples.kept for column in dataset.columns),
            default=0,
        ),
    }


def render_report(
    profile: ReportProfile,
    *,
    column_links: dict[tuple[str, str], str] | None = None,
    views: list[DatasetView] | None = None,
) -> str:
    """Render exclusively from serialized analysis results; CSV access is unnecessary.
    ``views`` are the ``dataset_views`` of ``profile`` when the caller has them."""
    resources = files("tabalyst")
    environment = _environment()
    template = environment.from_string(
        resources.joinpath("templates/report.html").read_text(encoding="utf-8")
    )
    # The semantic colour of each technical type (charter dataviz v1.1). Mixed is a confirmed
    # warning about the data, not brand attention, so it takes the warning gold, not the orange.
    type_colors = {
        "text": "var(--tb-viz-type-text)",
        "mixed": "var(--tb-viz-warning)",
        "integer": "var(--tb-viz-type-integer)",
        "number": "var(--tb-viz-type-number)",
        "boolean": "var(--tb-viz-type-boolean)",
        "date": "var(--tb-viz-type-date)",
        "empty": "var(--tb-viz-type-empty)",
        "complex": "var(--tb-viz-family-other)",
    }
    family_colors = dict(FAMILY_COLORS)
    datasets = views if views is not None else dataset_views(profile)
    several = len(datasets) > 1
    links = column_links or {}
    patterns = profile.derived.patterns if profile.derived else None
    grammar = f"v{patterns.grammar.version}" if patterns else "–"
    pages = [
        _page_view(dataset, f"d{index}-" if several else "", grammar, links)
        for index, dataset in enumerate(datasets, start=1)
    ]
    return template.render(
        report=profile,
        views=pages,
        tabalyst_version=get_version(),
        source_stem=Path(profile.source.name).stem,
        source_suffix=Path(profile.source.name).suffix,
        type_colors=type_colors,
        family_colors=family_colors,
        family_labels=FAMILY_LABELS,
        **_labels(),
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
        column_links=links,
    )


def render_column_report(
    profile: ReportProfile,
    dataset: DatasetView,
    column: ColumnView,
    report_href: str,
    previous: Neighbour | None = None,
    following: Neighbour | None = None,
) -> str:
    """Render a self-contained page from one serialized column profile. ``previous``
    and ``following`` link the pages of the neighbouring columns, when they exist."""
    resources = files("tabalyst")
    template = _environment().from_string(
        resources.joinpath("templates/column.html").read_text(encoding="utf-8")
    )
    rendered = template.render(
        report=profile,
        ds=dataset,
        column=column,
        page=column_page(column, previous, following),
        report_href=report_href,
        tabalyst_version=get_version(),
        diagnostics=[
            item for item in dataset.limits.diagnostics if item.path == column.path
        ],
        family_labels=FAMILY_LABELS,
        no_example=PAGE_NO_EXAMPLE,
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
        **_labels(),
    )
    return re.sub(r"(?m)^[ \t]+$", "", rendered)
