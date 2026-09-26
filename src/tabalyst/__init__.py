"""Public Python interface for Tabalyst."""

from tabalyst._version import __version__
from tabalyst.analysis import analyze_column as analyze_column
from tabalyst.config import AnalysisConfig as AnalysisConfig
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError
from tabalyst.report_service import generate_reports as generate_reports
from tabalyst.reporting import render_report as render_report
from tabalyst.sampling import SampleMethod as SampleMethod
from tabalyst.sampling import SampleResult as SampleResult
from tabalyst.sampling import sample_csv as sample_csv
from tabalyst.sampling_service import generate_samples as generate_samples
from tabalyst.service import analyze
from tabalyst.service import analyze_csv as analyze_csv

__all__ = [
    "ConfigurationError",
    "InputError",
    "ReportError",
    "TabalystError",
    "__version__",
    "analyze",
    "generate_reports",
    "generate_samples",
    "sample_csv",
]

# Alpha compatibility imports remain available, but are not part of the 0.1.0 API.
