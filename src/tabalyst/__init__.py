# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Public Python interface for Tabalyst.

The names below load on first use (PEP 562): a scan worker imports modules of
``tabalyst`` and must not pay for the report, the planner and the services.
"""

from typing import TYPE_CHECKING

from tabalyst._version import __version__
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError

if TYPE_CHECKING:
    from tabalyst.config import DeepSettings as DeepSettings
    from tabalyst.config import PearsonSettings as PearsonSettings
    from tabalyst.dedup_service import BatchDedupResult as BatchDedupResult
    from tabalyst.dedup_service import DedupResult as DedupResult
    from tabalyst.dedup_service import dedup_csv as dedup_csv
    from tabalyst.dedup_service import generate_dedups as generate_dedups
    from tabalyst.deep_service import execute_deep as execute_deep
    from tabalyst.deep_service import generate_deep as generate_deep
    from tabalyst.deep_service import prepare_deep as prepare_deep
    from tabalyst.deep_store import ConfirmationRequired as ConfirmationRequired
    from tabalyst.generate_service import ComputerPlan as ComputerPlan
    from tabalyst.generate_service import GeneratePlan as GeneratePlan
    from tabalyst.generate_service import GenerateResult as GenerateResult
    from tabalyst.generate_service import ValidationResult as ValidationResult
    from tabalyst.generate_service import build_generate_plan as build_generate_plan
    from tabalyst.generate_service import generate_datasets as generate_datasets
    from tabalyst.generate_service import (
        validate_generate_package as validate_generate_package,
    )
    from tabalyst.inspect_service import InspectResult as InspectResult
    from tabalyst.inspect_service import generate_inspections as generate_inspections
    from tabalyst.inspect_service import inspect as inspect
    from tabalyst.plan_service import generate_plans as generate_plans
    from tabalyst.plan_service import plan_document as plan_document
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
    from tabalyst.scanner.planner import AnalysisPlan as AnalysisPlan
    from tabalyst.scanner.planner import AnalysisRequest as AnalysisRequest
    from tabalyst.scanner.planner import SecondPassPlan as SecondPassPlan
    from tabalyst.scanner.planner import Stratify as Stratify
    from tabalyst.scanner.planner import plan_analyses as plan_analyses
    from tabalyst.scanner.planner import plan_second_pass as plan_second_pass
    from tabalyst.scanner.secondpass import DeepResult as DeepResult
    from tabalyst.scanner.secondpass import run_second_pass as run_second_pass
    from tabalyst.scanner.smart import SamplingPlan as SamplingPlan
    from tabalyst.scanner.smart import Smart as Smart
    from tabalyst.scanner.smart import plan_sampling as plan_sampling
    from tabalyst.service import analyze as analyze
    from tabalyst.service import analyze_csv as analyze_csv
    from tabalyst.service import analyze_scan as analyze_scan
    from tabalyst.smart_service import (
        SelectionConfirmationRequired as SelectionConfirmationRequired,
    )
    from tabalyst.smart_service import execute_smart_samples as execute_smart_samples
    from tabalyst.smart_service import prepare_smart_samples as prepare_smart_samples
    from tabalyst.source_guard import SourceNotReadable as SourceNotReadable
    from tabalyst.source_guard import StalePlan as StalePlan
    from tabalyst.source_guard import StaleSource as StaleSource

# Public name -> module that defines it; resolved by ``__getattr__``.
_LAZY: dict[str, str] = {
    "DeepSettings": "tabalyst.config",
    "PearsonSettings": "tabalyst.config",
    "execute_deep": "tabalyst.deep_service",
    "generate_deep": "tabalyst.deep_service",
    "prepare_deep": "tabalyst.deep_service",
    "ConfirmationRequired": "tabalyst.deep_store",
    "BatchDedupResult": "tabalyst.dedup_service",
    "DedupResult": "tabalyst.dedup_service",
    "dedup_csv": "tabalyst.dedup_service",
    "generate_dedups": "tabalyst.dedup_service",
    "ComputerPlan": "tabalyst.generate_service",
    "GeneratePlan": "tabalyst.generate_service",
    "GenerateResult": "tabalyst.generate_service",
    "ValidationResult": "tabalyst.generate_service",
    "build_generate_plan": "tabalyst.generate_service",
    "generate_datasets": "tabalyst.generate_service",
    "validate_generate_package": "tabalyst.generate_service",
    "InspectResult": "tabalyst.inspect_service",
    "generate_inspections": "tabalyst.inspect_service",
    "inspect": "tabalyst.inspect_service",
    "generate_plans": "tabalyst.plan_service",
    "plan_document": "tabalyst.plan_service",
    "ReportConfig": "tabalyst.report_config",
    "generate_reports": "tabalyst.report_service",
    "render_report": "tabalyst.reporting",
    "SampleMethod": "tabalyst.sampling",
    "SampleResult": "tabalyst.sampling",
    "sample_csv": "tabalyst.sampling",
    "generate_samples": "tabalyst.sampling_service",
    "generate_scans": "tabalyst.scan_service",
    "ScanConfig": "tabalyst.scanner",
    "ScanResult": "tabalyst.scanner",
    "scan": "tabalyst.scanner",
    "AnalysisPlan": "tabalyst.scanner.planner",
    "AnalysisRequest": "tabalyst.scanner.planner",
    "SecondPassPlan": "tabalyst.scanner.planner",
    "Stratify": "tabalyst.scanner.planner",
    "plan_analyses": "tabalyst.scanner.planner",
    "plan_second_pass": "tabalyst.scanner.planner",
    "DeepResult": "tabalyst.scanner.secondpass",
    "run_second_pass": "tabalyst.scanner.secondpass",
    "SamplingPlan": "tabalyst.scanner.smart",
    "Smart": "tabalyst.scanner.smart",
    "plan_sampling": "tabalyst.scanner.smart",
    "analyze": "tabalyst.service",
    "analyze_csv": "tabalyst.service",
    "analyze_scan": "tabalyst.service",
    "SelectionConfirmationRequired": "tabalyst.smart_service",
    "execute_smart_samples": "tabalyst.smart_service",
    "prepare_smart_samples": "tabalyst.smart_service",
    "SourceNotReadable": "tabalyst.source_guard",
    "StalePlan": "tabalyst.source_guard",
    "StaleSource": "tabalyst.source_guard",
}


def __getattr__(name: str) -> object:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_LAZY})


__all__ = [
    "AnalysisPlan",
    "AnalysisRequest",
    "BatchDedupResult",
    "ComputerPlan",
    "ConfigurationError",
    "ConfirmationRequired",
    "DedupResult",
    "DeepResult",
    "DeepSettings",
    "GeneratePlan",
    "GenerateResult",
    "InputError",
    "InspectResult",
    "PearsonSettings",
    "ReportError",
    "SamplingPlan",
    "ScanConfig",
    "ScanResult",
    "SecondPassPlan",
    "SelectionConfirmationRequired",
    "Smart",
    "SourceNotReadable",
    "StalePlan",
    "StaleSource",
    "Stratify",
    "TabalystError",
    "ValidationResult",
    "__version__",
    "analyze",
    "build_generate_plan",
    "dedup_csv",
    "execute_deep",
    "execute_smart_samples",
    "generate_datasets",
    "generate_dedups",
    "generate_deep",
    "generate_inspections",
    "generate_plans",
    "generate_reports",
    "generate_samples",
    "generate_scans",
    "inspect",
    "plan_analyses",
    "plan_document",
    "plan_sampling",
    "plan_second_pass",
    "prepare_deep",
    "prepare_smart_samples",
    "run_second_pass",
    "sample_csv",
    "scan",
    "validate_generate_package",
]
