# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reusable boundary for planning analyses, for the CLI and the Python API.

Planning never prompts and never runs an analysis: it reads a Scan, in memory,
from a document or from the shared cache, and returns the plan (design 20).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from tabalyst.config import deep_settings, smart_settings
from tabalyst.errors import TabalystError
from tabalyst.progress import ProgressCallback
from tabalyst.scan_document import load_document
from tabalyst.scan_service import ScanFailure, ScanJob, generate_scans
from tabalyst.scanner.planner import (
    AnalysisPlan,
    AnalysisRequest,
    AnalyzerRegistry,
    Budgets,
    Confirmation,
    Stratify,
    TimeEstimate,
    combine_confirmations,
    plan_analyses,
    plan_second_pass,
    with_stratification,
)
from tabalyst.scanner.secondpass import deep_path_for, load_deep
from tabalyst.scanner.smart import SamplingPlan, Smart, plan_sampling
from tabalyst.service import ConfigPath, _config_paths


@dataclass(frozen=True)
class PlanSuccess:
    job: ScanJob
    plan: AnalysisPlan
    # The shared scan was current: only the planning ran.
    reused: bool
    estimate: TimeEstimate | None
    confirmation: Confirmation
    warnings: tuple[str, ...] = ()
    # The plan of a smart sample, when it was asked for (design 20.15).
    sampling: SamplingPlan | None = None

    @property
    def requires_confirmation(self) -> bool:
        return self.confirmation.required


@dataclass(frozen=True)
class BatchPlanResult:
    successes: tuple[PlanSuccess, ...]
    failures: tuple[ScanFailure, ...]
    warnings: tuple[tuple[Path, str], ...] = ()
    # One confirmation for the whole batch, with the total (R1).
    confirmation: Confirmation | None = None

    @property
    def requires_confirmation(self) -> bool:
        return self.confirmation is not None and self.confirmation.required


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
    forced: bool = False,
    stratify: Stratify | None = None,
    smart: Smart | None = None,
) -> BatchPlanResult:
    """Plan the analyses of one or more sources.

    The scan comes from the shared storage when it is current for the source, its
    settings and the engine; otherwise the first pass runs and is stored, as
    ``tabalyst scan`` does. The second pass never runs and nothing is asked: the
    result says whether running the plans, together, requires a confirmation
    (``forced`` plans a second pass asked for as a whole). ``stratify`` adds the
    advice on stratified sampling to each plan (design 20.14), and ``smart`` the
    plan of a smart sample (design 20.15), which announces the readings of the
    source it would take: with ``forced``, the second pass is counted among
    them unless its document is current. A failed source does not stop the
    others.
    """
    deep = deep_settings(_config_paths(config_path))
    smart_config = None if smart is None else smart_settings(_config_paths(config_path))
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
            second = plan_second_pass(success.result, forced=forced, deep=deep)
            if stratify is not None:
                second = replace(
                    second,
                    plan=with_stratification(second.plan, success.result, stratify),
                )
            sampling = None
            if smart is not None:
                stored = (
                    None
                    if success.job.output is None
                    else load_deep(deep_path_for(success.job.output))
                )
                sampling = plan_sampling(
                    success.result,
                    deep=stored,
                    dataset=smart.dataset,
                    size=smart.size,
                    seed=smart.seed,
                    settings=smart_config,
                    enrichment=second.plan if forced else None,
                )
        except TabalystError as exc:
            failures.append(ScanFailure(job=success.job, error=exc))
        else:
            successes.append(
                PlanSuccess(
                    success.job,
                    second.plan,
                    success.reused,
                    second.estimate,
                    second.confirmation,
                    success.warnings,
                    sampling,
                )
            )
    return BatchPlanResult(
        successes=tuple(successes),
        failures=tuple(failures),
        warnings=batch.plan.warnings,
        confirmation=combine_confirmations(s.confirmation for s in successes)
        if successes
        else None,
    )
