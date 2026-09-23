"""Render self-contained analysis results as an interactive HTML report."""

from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from tabalyst._version import get_version
from tabalyst.models import DatasetProfile


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


def load_profile(path: str | Path) -> DatasetProfile:
    """Validate and load the experimental JSON profile format."""
    return DatasetProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))


def render_report(profile: DatasetProfile) -> str:
    """Render exclusively from serialized analysis results; CSV access is unnecessary."""
    resources = files("tabalyst")
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    environment.filters["count"] = lambda number: f"{number:,}"
    environment.filters["number"] = format_number
    environment.filters["seconds"] = format_seconds
    environment.filters["size"] = format_size
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
    }
    semantic_colors = {
        "enum": "var(--d2)",
        "date": "var(--d1)",
        "none": "var(--d3)",
    }
    return template.render(
        report=profile,
        tabalyst_version=get_version(),
        source_stem=Path(profile.source.filename).stem,
        source_suffix=Path(profile.source.filename).suffix,
        numeric_columns=[column for column in profile.columns if column.numeric],
        date_columns=[column for column in profile.columns if column.date_profile],
        string_columns=[column for column in profile.columns if column.string_profile],
        type_colors=type_colors,
        semantic_colors=semantic_colors,
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
    )
