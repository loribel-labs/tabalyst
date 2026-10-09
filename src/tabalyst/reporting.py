# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Render self-contained analysis results as an interactive HTML report."""

import re
import unicodedata
from collections import defaultdict
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined
from markupsafe import Markup, escape

from tabalyst._version import get_version
from tabalyst.errors import InputError
from tabalyst.models import ReportProfile
from tabalyst.report_config import ReportConfig
from tabalyst.report_labels import (
    ACCURACY_TITLES,
    ACCURACY_WORDS,
    ORIGIN_WORDS,
)
from tabalyst.report_profile import build_views
from tabalyst.report_sections import (
    cardinality_view,
    limits_view,
    pattern_entries,
    pattern_view,
    quality_view,
    rows_view,
)
from tabalyst.report_views import (
    ColumnView,
    DatasetView,
    LimitView,
    QualityItem,
)
from tabalyst.scan_document import load_report
from tabalyst.scan_reuse import read_json_document
from tabalyst.scanner.models import PatternCandidate


def format_number(number: float) -> str:
    """Keep ordinary values readable and compact only genuinely large magnitudes.
    An integer is always written with all its digits (F06); only a float, which
    already is an approximation, is shortened."""
    if isinstance(number, int):
        return f"{number:,}"
    if abs(number) > 10**10:
        return f"{number:.4e}"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def cell_text(values: list[str | None]) -> str:
    """The text of a cell of the row sample: the values of an items path joined,
    a JSON null written ``null``."""
    return ", ".join("null" if value is None else value for value in values)


# Most rows a section prints, whatever the report keeps: the document holds
# them all, the page stays light (HTML-07). A paged table shows 25 at a time.
DISPLAY_LIMITS = {"findings": 500, "patterns": 400, "limits": 500, "rows": 300}


def format_seconds(seconds: float) -> str:
    """Display elapsed time with no more than two decimal places."""
    return f"{seconds:.2f}".rstrip("0").rstrip(".")


def format_size(size_bytes: int) -> str:
    """Display source size in KB, switching to MB at one mebibyte."""
    if size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"


# Separators after which a long name may break: snake case, paths and dates.
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
    (``report_views``, ``report_sections``)."""
    config = ReportConfig.from_presentation(profile.report.config, profile.config)
    datasets = {dataset.id: dataset for dataset in profile.datasets}
    entries = pattern_entries(profile.derived)
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
        columns = []
        for column in projection.columns:
            field = fields[column.id]
            derived = build_views(field, column.inferred_type, config)
            columns.append(
                ColumnView(
                    **dict(column),
                    field=field,
                    numeric=derived.numeric,
                    date_profile=derived.date_profile,
                    string_profile=derived.string_profile,
                    distinct=cardinality_view(field),
                    quality=findings.get(column.id, []),
                    limits=bounded.get(column.id, []),
                    patterns=pattern_view(
                        field, entries.get((projection.id, column.id)), profile.derived
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
            )
        )
    return views


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


def _environment() -> Environment:
    environment = Environment(autoescape=True, undefined=StrictUndefined)
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
    }


def _pattern_rows(
    dataset: DatasetView,
) -> list[tuple[ColumnView, PatternCandidate | None, str]]:
    """One row per inferred candidate, then the values no candidate takes, with
    the accuracy of the shares (every distinct value, or a sample of them)."""
    rows: list[tuple[ColumnView, PatternCandidate | None, str]] = []
    for column in dataset.columns:
        entry = column.patterns.entry
        if entry is None:
            continue
        kind = "exact" if entry.population.complete else "sample"
        rows.extend((column, candidate, kind) for candidate in entry.candidates)
        if entry.other.distinct:
            rows.append((column, None, kind))
    return rows


def _page_view(dataset: DatasetView, prefix: str, grammar: str) -> dict[str, object]:
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
        "pattern_columns": pattern_columns,
        "pattern_rows": pattern_rows,
        "pattern_missing": len(dataset.columns) - len(pattern_columns),
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
    type_colors = {
        "text": "var(--d2)",
        "mixed": "var(--attn)",
        "integer": "var(--d3)",
        "number": "var(--d1)",
        "boolean": "var(--ok)",
        "date": "var(--d1)",
        "empty": "var(--line-strong)",
        "complex": "var(--text-3)",
    }
    # Other interpretations (email, phone, patterns...) share one color.
    semantic_colors = defaultdict(
        lambda: "var(--ok)",
        {"enumeration": "var(--d2)", "date": "var(--d1)", "none": "var(--d3)"},
    )
    datasets = views if views is not None else dataset_views(profile)
    several = len(datasets) > 1
    patterns = profile.derived.patterns if profile.derived else None
    grammar = f"v{patterns.grammar.version}" if patterns else "–"
    pages = [
        _page_view(dataset, f"d{index}-" if several else "", grammar)
        for index, dataset in enumerate(datasets, start=1)
    ]
    return template.render(
        report=profile,
        views=pages,
        tabalyst_version=get_version(),
        source_stem=Path(profile.source.name).stem,
        source_suffix=Path(profile.source.name).suffix,
        type_colors=type_colors,
        semantic_colors=semantic_colors,
        **_labels(),
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
        column_links=column_links or {},
    )


def render_column_report(
    profile: ReportProfile,
    dataset: DatasetView,
    column: ColumnView,
    report_href: str,
) -> str:
    """Render a self-contained page from one serialized column profile."""
    resources = files("tabalyst")
    template = _environment().from_string(
        resources.joinpath("templates/column.html").read_text(encoding="utf-8")
    )
    rendered = template.render(
        report=profile,
        ds=dataset,
        column=column,
        report_href=report_href,
        tabalyst_version=get_version(),
        diagnostics=[
            item for item in dataset.limits.diagnostics if item.path == column.path
        ],
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
        **_labels(),
    )
    return re.sub(r"(?m)^[ \t]+$", "", rendered)
