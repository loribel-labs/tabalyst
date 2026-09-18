"""Render self-contained analysis results as an interactive HTML report."""

from collections import Counter
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from tabalyst.models import DatasetProfile


def load_profile(path: str | Path) -> DatasetProfile:
    """Validate and load the experimental JSON profile format."""
    return DatasetProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))


def render_report(profile: DatasetProfile) -> str:
    """Render exclusively from serialized analysis results; CSV access is unnecessary."""
    resources = files("tabalyst")
    environment = Environment(autoescape=True, undefined=StrictUndefined)
    environment.filters["count"] = lambda number: f"{number:,}"
    environment.filters["number"] = lambda number: f"{number:,.4g}"
    template = environment.from_string(
        resources.joinpath("templates/report.html").read_text(encoding="utf-8")
    )
    return template.render(
        report=profile,
        types=Counter(column.inferred_type for column in profile.columns),
        theme_css=resources.joinpath("static/theme.css").read_text(encoding="utf-8"),
        report_js=resources.joinpath("static/report.js").read_text(encoding="utf-8"),
    )
