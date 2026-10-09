# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reusable boundary for planning analyses, for the CLI and the Python API.

Planning never prompts and never runs an analysis: it reads a Scan, in memory,
from a document or from the shared cache, and returns the plan (design 20).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tabalyst.errors import TabalystError
from tabalyst.progress import ProgressCallback
from tabalyst.scan_document import load_document
from tabalyst.scan_service import ScanFailure, ScanJob, generate_scans
from tabalyst.scanner.planner import (
    AnalysisPlan,
    AnalysisRequest,
    AnalyzerRegistry,
    Budgets,
    plan_analyses,
)
from tabalyst.service import ConfigPath


@dataclass(frozen=True)
class PlanSuccess:
    job: ScanJob
    plan: AnalysisPlan
    # The shared scan was current: only the planning ran.
    reused: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatchPlanResult:
    successes: tuple[PlanSuccess, ...]
    failures: tuple[ScanFailure, ...]
    warnings: tuple[tuple[Path, str], ...] = ()


def plan_document(
    document: Path | str | dict,
    *,
    requests: Sequence[AnalysisRequest] = (),
    automatic: bool = True,
    budgets: Budgets | None = None,
    registry: AnalyzerRegistry | None = None,
) -> AnalysisPlan:
    """Plan the analyses of a scan document, given as a path or a JSON object.

    Raises ``InputError`` for a Report, which keeps fewer sample values than its
    Scan and cannot be planned from (design 19.4).
    """
    loaded = load_document(document)
    loaded.require_complete_samples("plan analyses")
    return plan_analyses(
        loaded.base,
        requests=requests,
        automatic=automatic,
        budgets=budgets,
        registry=registry,
    )


def generate_plans(
    input_specs: Sequence[str | Path],
    *,
    config_path: ConfigPath | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
    on_progress: ProgressCallback | None = None,
    workers: int | None = None,
) -> BatchPlanResult:
    """Plan the analyses of one or more sources.

    The scan comes from the shared storage when it is current for the source, its
    settings and the engine; otherwise the first pass runs and is stored, as
    ``tabalyst scan`` does. The second pass never runs. A failed source does not
    stop the others.
    """
    batch = generate_scans(
        input_specs,
        config_path=config_path,
        delimiter=delimiter,
        encoding=encoding,
        collections=collections,
        on_progress=on_progress,
        workers=workers,
        project_storage=True,
        refresh=False,
    )
    successes: list[PlanSuccess] = []
    failures = list(batch.failures)
    for success in batch.successes:
        try:
            plan = plan_analyses(success.result)
        except TabalystError as exc:
            failures.append(ScanFailure(job=success.job, error=exc))
        else:
            successes.append(
                PlanSuccess(success.job, plan, success.reused, success.warnings)
            )
    return BatchPlanResult(
        successes=tuple(successes),
        failures=tuple(failures),
        warnings=batch.plan.warnings,
    )
