"""Render self-contained analysis results as an interactive HTML report."""

from collections import Counter
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from tabalyst.execution_log import tabalyst_version
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
    return template.render(
        report=profile,
        tabalyst_version=tabalyst_version(),
        types=Counter(column.inferred_type for column in profile.columns),
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
    )
