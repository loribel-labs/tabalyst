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
from tabalyst.models import ColumnProfile, DatasetProfile, ReportProfile

# Plain names of the scan measures a limit can stop (design 8 and 11).
MEASURE_LABELS = {
    "structure.paths": "Paths",
    "records.duplicates.count": "Duplicate records",
    "values.cardinality": "Distinct values",
    "values.frequencies": "Value frequencies",
    "numeric.median": "Median",
    "normalization.variant_groups": "Variant groups",
    "normalization.stages.raw.cardinality": "Distinct raw values",
    "normalization.stages.nfc.cardinality": "Distinct after Unicode composition",
    "normalization.stages.trim.cardinality": "Distinct after trimming",
    "normalization.stages.collapse_whitespace.cardinality": (
        "Distinct after whitespace collapsing"
    ),
    "normalization.stages.casefold.cardinality": "Distinct after case folding",
    "normalization.stages.strip_accents.cardinality": "Distinct after accent removal",
}
# Settings behind each limit reason.
REASON_SETTINGS = {
    "distinct_limit": "scan.limits.max_distinct_per_field",
    "global_budget": "scan.limits.max_tracked_values",
    "value_too_long": "scan.limits.max_stored_value_length",
    "record_budget": "scan.limits.max_tracked_records",
    "field_limit": "scan.limits.max_fields",
}


def format_number(number: float) -> str:
    """Keep ordinary values readable and compact only genuinely large magnitudes."""
    if abs(number) > 10**10:
        return f"{number:.4e}"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


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
    """Validate and load the experimental JSON profile format."""
    return ReportProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))


def column_pages(
    profile: ReportProfile, report_path: Path
) -> list[tuple[Path, DatasetProfile, ColumnProfile]]:
    """Name standalone column pages in source order, across all datasets."""
    pages = []
    number = 0
    for dataset in profile.datasets:
        for column in dataset.columns:
            number += 1
            plain = unicodedata.normalize("NFKD", column.name).encode("ascii", "ignore").decode()
            slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")[:48].rstrip("-")
            slug = slug or "unnamed"
            path = report_path.with_suffix("") / f"col-{number:02d}-{slug}.html"
            pages.append((path, dataset, column))
    return pages


def render_report(profile: ReportProfile, *, column_links: dict[tuple[str, str], str] | None = None) -> str:
    """Render exclusively from serialized analysis results; CSV access is unnecessary."""
    resources = files("tabalyst")
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    environment.filters["count"] = lambda number: f"{number:,}"
    environment.filters["number"] = format_number
    environment.filters["seconds"] = format_seconds
    environment.filters["size"] = format_size
    environment.filters["breakable"] = breakable
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
    several = len(profile.datasets) > 1
    views = [
        {
            "ds": dataset,
            # Element ids are prefixed only when the report shows several
            # datasets, so single-dataset reports keep their anchors.
            "px": f"d{index}-" if several else "",
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
            "has_limits": bool(
                dataset.limits.measures
                or dataset.limits.diagnostics
                or dataset.limits.untracked_observations
                or dataset.limits.depth_truncated_observations
            ),
        }
        for index, dataset in enumerate(profile.datasets, start=1)
    ]
    return template.render(
        report=profile,
        views=views,
        tabalyst_version=get_version(),
        source_stem=Path(profile.source.filename).stem,
        source_suffix=Path(profile.source.filename).suffix,
        type_colors=type_colors,
        semantic_colors=semantic_colors,
        measure_labels=MEASURE_LABELS,
        reason_settings=REASON_SETTINGS,
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
        column_links=column_links or {},
    )


def render_column_report(
    profile: ReportProfile,
    dataset: DatasetProfile,
    column: ColumnProfile,
    report_href: str,
) -> str:
    """Render a self-contained page from one serialized column profile."""
    resources = files("tabalyst")
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    environment.filters["count"] = lambda number: f"{number:,}"
    environment.filters["number"] = format_number
    template = environment.from_string(
        resources.joinpath("templates/column.html").read_text(encoding="utf-8")
    )
    rendered = template.render(
        report=profile,
        ds=dataset,
        column=column,
        report_href=report_href,
        tabalyst_version=get_version(),
        limits=[item for item in dataset.limits.measures if item.column_id == column.id],
        issues=[item for item in dataset.issues if column.id in item.column_ids],
        diagnostics=[
            item for item in dataset.limits.diagnostics if item.path == column.path
        ],
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
    )
    return re.sub(r"(?m)^[ \t]+$", "", rendered)
