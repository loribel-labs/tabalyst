# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reusable boundary of the smart sample, for the CLI and the Python API (design
20.16, rule R1).

``prepare_smart_samples`` scans the sources (or reuses their current Scan), reads
a second-pass document when it is current, plans the sample and estimates what the
selection would cost; it asks nothing and reads no source again.
``execute_smart_samples`` runs those plans. It never prompts: a batch that needs a
confirmation runs only when the caller says it was given (``confirmed``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from tabalyst.batch import validate_outputs, write_text_atomic
from tabalyst.config import (
    CsvConfig,
    load_config_layers,
    settings_from_layer,
    smart_settings,
)
from tabalyst.deep_store import ConfirmationRequired
from tabalyst.errors import InputError, ReportError, TabalystError
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.sample_page import render_sample_page, sample_page_path
from tabalyst.sampling import SampleMethod, SampleResult, SmartSummary, write_sample_csv
from tabalyst.sampling_service import (
    BatchSampleResult,
    SampleFailure,
    SampleJob,
    SamplePlan,
    SampleSuccess,
    build_sample_plan,
)
from tabalyst.scan_service import ScanSuccess, generate_scans
from tabalyst.scanner.planner import Confirmation, combine_confirmations
from tabalyst.scanner.secondpass import DeepResult, deep_path_for, load_deep
from tabalyst.scanner.smart import SamplingPlan, plan_sampling
from tabalyst.scanner.smart.estimate import estimate_selection
from tabalyst.scanner.smart.execute import select_rows
from tabalyst.scanner.smart.result import (
    SampleDocument,
    build_document,
    sample_document_text,
)
from tabalyst.service import ConfigPath, _config_paths

REPORT_SUFFIX = ".json"


class SelectionConfirmationRequired(ConfirmationRequired):
    """The selection of a smart sample exceeds a limit that a run needs confirming
    (rule R1) and no confirmation was given. Nothing was started."""

    def __init__(self, confirmation: Confirmation) -> None:
        super().__init__(confirmation)
        reasons = ", ".join(confirmation.reasons)
        start = "The smart sample needs a confirmation before it starts"
        self.args = (f"{start} ({reasons}). Nothing was started.",)


def sample_report_path(output: Path) -> Path:
    """Where the report of a smart sample goes: beside the CSV file, with the same
    name and the extension ``.json``."""
    return output.with_suffix(REPORT_SUFFIX)


@dataclass(frozen=True)
class SmartJob:
    """One source with its Scan, its plan and what the selection would cost."""

    job: SampleJob
    report: Path
    page: Path | None
    scan: ScanSuccess
    plan: SamplingPlan
    deep: DeepResult | None
    percent: float | None
    confirmation: Confirmation


@dataclass(frozen=True)
class SmartPreparation:
    """The sources ready for a smart sample. ``confirmation`` is one for the whole
    batch, with the total (R1); ``failures`` are the sources whose Scan or plan
    failed."""

    plan: SamplePlan
    jobs: tuple[SmartJob, ...]
    failures: tuple[SampleFailure, ...]
    confirmation: Confirmation | None
    indent: bool

    @property
    def requires_confirmation(self) -> bool:
        return self.confirmation is not None and self.confirmation.required


def _size(records: int, rows: int | None, percent: float | None) -> int:
    if (rows is None) == (percent is None):
        raise InputError("Specify exactly one of --rows or --percent.")
    if rows is not None:
        if rows <= 0:
            raise InputError("--rows must be greater than 0.")
        size = rows
    else:
        assert percent is not None
        if percent <= 0 or percent > 100:
            raise InputError("--percent must be greater than 0 and at most 100.")
        size = math.ceil(records * percent / 100)
    if size > records:
        raise InputError(
            f"Requested sample size ({size:,}) exceeds available rows ({records:,})."
        )
    return size


def prepare_smart_samples(
    input_specs: Sequence[str | Path],
    *,
    rows: int | None = None,
    percent: float | None = None,
    seed: int | None = None,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
    html: bool = True,
    on_progress: ProgressCallback | None = None,
) -> SmartPreparation:
    """Scan the sources, or reuse the current stored Scan of each, and plan the
    smart sample of every one. Writes the Scans like ``tabalyst scan`` would to the
    shared storage, and nothing else; a source that fails is reported in
    ``failures`` and does not stop the others.

    Raises ``InputError`` for a size that is not valid, and the errors of
    ``build_sample_plan`` for outputs that are not safe.
    """
    if (rows is None) == (percent is None):
        raise InputError("Specify exactly one of --rows or --percent.")
    config_paths = _config_paths(config_path)
    plan = build_sample_plan(input_specs, output=output, output_dir=output_dir, force=force)
    reports = {job.source: sample_report_path(job.output) for job in plan.jobs}
    validate_outputs(
        ((job.source, reports[job.source]) for job in plan.jobs),
        sources=[*(job.source for job in plan.jobs), *config_paths],
        force=force,
        label="Sample report",
    )
    for job in plan.jobs:
        if reports[job.source] == job.output:
            raise InputError("A sample and its report cannot have the same filename.")
    pages = {job.source: sample_page_path(reports[job.source]) if html else None for job in plan.jobs}
    if html:
        validate_outputs(
            ((job.source, pages[job.source]) for job in plan.jobs if pages[job.source] is not None),
            sources=[*(job.source for job in plan.jobs), *config_paths],
            force=force,
            label="Sample page",
        )
    settings = smart_settings(config_paths)
    top_level, _ = load_config_layers(config_paths)
    indent = settings_from_layer(top_level).output.json_indent
    batch = generate_scans(
        [job.source for job in plan.jobs],
        config_path=config_path,
        delimiter=delimiter,
        encoding=encoding,
        on_progress=on_progress,
        project_storage=True,
        refresh=False,
    )
    by_source = {job.source: job for job in plan.jobs}
    jobs: list[SmartJob] = []
    failures: list[SampleFailure] = [
        SampleFailure(job=by_source[failure.job.source], error=failure.error)
        for failure in batch.failures
    ]
    for success in batch.successes:
        job = by_source[success.job.source]
        try:
            if success.result.source.format != "csv":
                raise InputError("A smart sample reads CSV files only.")
            if len(success.result.datasets) != 1:
                raise InputError("The Scan of a CSV file has one dataset; this one has more.")
            size = _size(success.result.datasets[0].record_count, rows, percent)
            stored = (
                None if success.job.output is None else load_deep(deep_path_for(success.job.output))
            )
            sampling = plan_sampling(
                success.result,
                deep=stored,
                size=size,
                seed=seed,
                settings=settings,
                scan_stored=success.reused,
            )
            confirmation = estimate_selection(sampling, success.result)
        except TabalystError as exc:
            failures.append(SampleFailure(job=job, error=exc))
            continue
        jobs.append(
            SmartJob(job, reports[job.source], pages[job.source], success, sampling, stored, percent, confirmation)
        )
    return SmartPreparation(
        plan=plan,
        jobs=tuple(jobs),
        failures=tuple(failures),
        confirmation=combine_confirmations(item.confirmation for item in jobs) if jobs else None,
        indent=indent,
    )


def _summary(document: SampleDocument, reserve_rows: int, duration: float) -> SmartSummary:
    coverage = document.coverage
    return SmartSummary(
        targets=coverage.defined,
        evaluable=coverage.evaluable,
        covered=coverage.covered,
        weighted_share=coverage.weighted.share,
        mandatory=coverage.mandatory.defined,
        mandatory_covered=coverage.mandatory.covered,
        reserve_rows=reserve_rows,
        passes=document.run.passes.total,
        scan_ran=document.run.passes.scan,
        duration_seconds=duration,
    )


def _run(job: SmartJob, preparation: SmartPreparation, on_progress: ProgressCallback | None) -> SampleSuccess:
    started_at = datetime.now(UTC)
    clock = perf_counter()
    scan = job.scan.result
    selection = select_rows(scan, job.job.source, job.plan, deep=job.deep, on_progress=on_progress)
    emit_progress(on_progress, job.job.source, ProgressPhase.WRITING)
    csv_config = CsvConfig(encoding=scan.config.csv.encoding, delimiter=scan.config.csv.delimiter)
    write_sample_csv(job.job.output, selection.header, selection.rows, job.job.source, csv_config)
    document = build_document(
        scan,
        job.plan,
        selection,
        percent=job.percent,
        output_name=job.job.output.name,
        encoding=csv_config.encoding,
        delimiter=csv_config.delimiter,
        started_at=started_at,
        duration_seconds=perf_counter() - clock,
        scan_ran=not job.scan.reused,
    )
    try:
        write_text_atomic(job.report, sample_document_text(document, indent=preparation.indent))
    except OSError as exc:
        # A sample whose coverage nobody can read is not left behind.
        job.job.output.unlink(missing_ok=True)
        raise ReportError(f"Cannot write sample report {job.report}: {exc}") from exc
    if job.page is not None:
        try:
            write_text_atomic(job.page, render_sample_page(document))
        except OSError as exc:
            job.job.output.unlink(missing_ok=True)
            job.report.unlink(missing_ok=True)
            raise ReportError(f"Cannot write sample page {job.page}: {exc}") from exc
    dataset = scan.datasets[0]
    size = len(selection.rows)
    result = SampleResult(
        source=job.job.source,
        output=job.job.output,
        method=SampleMethod.SMART,
        source_rows=dataset.record_count,
        sample_rows=size,
        sample_rate=(size / dataset.record_count * 100) if dataset.record_count else 0.0,
        field=None,
        seed=job.plan.method.seed,
        encoding=csv_config.encoding,
        delimiter=csv_config.delimiter,
        report=job.report,
        page=job.page,
        smart=_summary(document, selection.outcome.reserve_rows, document.run.duration_seconds),
    )
    return SampleSuccess(job=job.job, result=result)


def execute_smart_samples(
    preparation: SmartPreparation,
    *,
    confirmed: bool = False,
    on_progress: ProgressCallback | None = None,
) -> BatchSampleResult:
    """Run the smart sample of every prepared source, one after the other, and
    write the CSV file and the report of each. Raises
    ``SelectionConfirmationRequired`` before reading any source when the batch
    needs a confirmation and ``confirmed`` is false; a source that fails (a
    changed source, one that cannot be read again) does not stop the others, and
    nothing is written for it (design 20.6)."""
    if preparation.requires_confirmation and not confirmed:
        assert preparation.confirmation is not None
        raise SelectionConfirmationRequired(preparation.confirmation)
    successes: list[SampleSuccess] = []
    failures = list(preparation.failures)
    total = len(preparation.jobs)
    for index, job in enumerate(preparation.jobs, start=1):

        def forward(event: ProgressEvent, *, number: int = index) -> None:
            if on_progress is not None and event.phase != ProgressPhase.COMPLETE:
                on_progress(
                    ProgressEvent(
                        source=event.source,
                        phase=event.phase,
                        index=number,
                        total=total,
                        detail=event.detail,
                        bytes_read=event.bytes_read,
                        bytes_total=event.bytes_total,
                    )
                )

        try:
            success = _run(job, preparation, forward)
        except TabalystError as exc:
            failures.append(SampleFailure(job=job.job, error=exc))
            emit_progress(
                on_progress, job.job.source, ProgressPhase.FAILED, index=index, total=total, detail=str(exc)
            )
        else:
            successes.append(success)
            emit_progress(
                on_progress,
                job.job.source,
                ProgressPhase.COMPLETE,
                index=index,
                total=total,
                duration_seconds=success.result.smart.duration_seconds if success.result.smart else None,
            )
    return BatchSampleResult(
        plan=preparation.plan, successes=tuple(successes), failures=tuple(failures)
    )
