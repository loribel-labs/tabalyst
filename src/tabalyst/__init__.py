"""Public Python interface for Tabalyst."""

from tabalyst._version import __version__
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError
from tabalyst.report_config import ReportConfig as ReportConfig
from tabalyst.report_service import generate_reports as generate_reports
from tabalyst.reporting import render_report as render_report
from tabalyst.sampling import SampleMethod as SampleMethod
from tabalyst.sampling import SampleResult as SampleResult
from tabalyst.sampling import sample_csv as sample_csv
from tabalyst.sampling_service import generate_samples as generate_samples
from tabalyst.scan_service import generate_scans as generate_scans
from tabalyst.scanner import ScanConfig as ScanConfig
from tabalyst.scanner import ScanResult as ScanResult
from tabalyst.scanner import scan as scan
from tabalyst.service import analyze
from tabalyst.service import analyze_csv as analyze_csv
from tabalyst.service import analyze_scan as analyze_scan

__all__ = [
    "ConfigurationError",
    "InputError",
    "ReportError",
    "ScanConfig",
    "ScanResult",
    "TabalystError",
    "__version__",
    "analyze",
    "generate_reports",
    "generate_samples",
    "generate_scans",
    "sample_csv",
    "scan",
]
