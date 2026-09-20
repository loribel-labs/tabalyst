"""Public Python interface for Tabalyst."""

from tabalyst._version import __version__
from tabalyst.analysis import analyze_column as analyze_column
from tabalyst.config import AnalysisConfig as AnalysisConfig
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError
from tabalyst.reporting import render_report as render_report
from tabalyst.service import analyze
from tabalyst.service import analyze_csv as analyze_csv

__all__ = [
    "ConfigurationError",
    "InputError",
    "ReportError",
    "TabalystError",
    "__version__",
    "analyze",
]

# Alpha compatibility imports remain available, but are not part of the 0.1.0 API.
