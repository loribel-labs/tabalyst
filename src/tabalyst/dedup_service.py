# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Plan and run a batch of Dedup sources: the boundary of the CLI and the Python API (design dedup 4.3, 13)."""

import dataclasses
import os
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from tabalyst.batch import path_key
from tabalyst.dedup.batch_report import (
    BatchOutputs,
    BatchReport,
    BatchSource,
    BatchStatus,
    Counters,
    SourceRecords,
    Tally,
    Totals,
    generator,
    is_batch_report,
    relative_path,
    write_batch_report,
)
from tabalyst.dedup.cache import Verification, ownership_test
from tabalyst.dedup.discovery import (
    BatchPlan,
    ExclusionReason,
    PlannedSource,
    plan_batch,
)
from tabalyst.dedup.failures import DedupReportError, FailureReason
from tabalyst.dedup.pipeline import process_source
from tabalyst.dedup.report import CompleteReport, FailedReport
from tabalyst.dedup.settings import DedupSettings, resolve_dedup_settings
from tabalyst.errors import InputError, ReportError, TabalystError
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.service import ConfigPath

STAGE = "Dedup"
ResultStatus = Literal["DONE", "SKIPPED", "FAILED"]
ResultReason = FailureReason | Literal["already_processed", "output_refused"]


@dataclass(frozen=True)
class DedupResult:
    """What became of one source (design dedup 4.3).

    ``files`` are the CSV files this run created; a ``SKIPPED`` source created none,
    and its ``report`` is the one that was already there (``verification`` says how
    far the decision checked it). ``report_path`` is ``None`` when no report was
    written or read. A ``FAILED`` source has its ``error``: ``reason`` is the stable
    code of the failure, or ``output_refused`` when a check just before the run
    refused an output (the source was then left untouched and has no report).
    """

    source: Path
    status: ResultStatus
    reason: ResultReason | None = None
    files: tuple[Path, ...] = ()
    report: CompleteReport | FailedReport | None = None
    report_path: Path | None = None
    verification: Verification | None = None
    error: TabalystError | None = None
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class BatchDedupResult:
    """The result of a batch: one entry per eligible source, in the order of the plan.

    ``plan.excluded`` lists the files a pattern found and Dedup skipped. ``failures``
    are the ``FAILED`` entries of ``results``, each with its ``error``; one failing
    source never stops the others. ``batch_report`` is the path of the report written
    (``None`` when this invocation writes none, design dedup 13.1, or when it could not
    be written: ``batch_report_error`` says so).
    """

    plan: BatchPlan
    results: tuple[DedupResult, ...]
    failures: tuple[DedupResult, ...]
    batch_report: Path | None
    batch_report_error: ReportError | None = None
    duration_seconds: float = 0.0

    @property
    def excluded(self) -> tuple[tuple[Path, ExclusionReason], ...]:
        """The files found and skipped, each with its reason."""
        return self.plan.excluded

    @property
    def succeeded(self) -> bool:
        """Whether no source failed and the batch report, if any, was written."""
        return not self.failures and self.batch_report_error is None


# ----------------------------------------------------------------- planning


def build_dedup_plan(
    input_specs: Sequence[str | Path],
    settings: DedupSettings,
    *,
    literal: bool = False,
) -> BatchPlan:
    """Resolve the inputs and refuse an unsafe batch before any work (design dedup 7).

    The ownership of the outputs that exist is read from their reports. A
    ``dedup.summary.json`` that is not a Tabalyst Dedup batch report is refused
    without ``settings.force`` (design dedup 13.1), a directory or a source of the
    batch never. Nothing is created or written.
    """
    plan = plan_batch(
        input_specs,
        settings,
        is_owned=ownership_test(verify_content=settings.verify_content),
        literal=literal,
    )
    _check_batch_report(plan, settings)
    return plan


def _check_batch_report(plan: BatchPlan, settings: DedupSettings) -> None:
    path = plan.batch_report
    if not plan.writes_batch_report or not os.path.lexists(path):
        return
    if path.is_dir():
        raise InputError(f"Dedup batch report path is a directory: {path}")
    if path_key(path) in {path_key(item.source) for item in plan.eligible}:
        raise InputError(f"Dedup batch report would overwrite an input file: {path}")
    if not settings.force and not is_batch_report(path):
        raise ReportError(
            "dedup.summary.json already exists and is not a Tabalyst Dedup batch "
            f"report. Use --force to allow replacing it:\n  {path}"
        )


# ---------------------------------------------------------------- execution


def execute_dedups(
    input_specs: Sequence[str | Path],
    settings: DedupSettings,
    *,
    on_progress: ProgressCallback | None = None,
) -> BatchDedupResult:
    """Plan and run a batch with options that are already resolved.

    This is what ``generate_dedups`` and the command line share. A refusal of the
    plan raises before any file is read; after that no source can stop another.
    """
    plan = build_dedup_plan(input_specs, settings)
    return run_dedup_plan(plan, settings, input_specs, on_progress=on_progress)


def run_dedup_plan(
    plan: BatchPlan,
    settings: DedupSettings,
    input_specs: Sequence[str | Path],
    *,
    on_progress: ProgressCallback | None = None,
) -> BatchDedupResult:
    """Run the eligible sources of ``plan`` one at a time, then write the batch report.

    Each source is independent (design dedup 11.1): its outcome, a failure included,
    is an entry of the result. The events of progress carry the position of the
    source in the batch (``index`` from 1, ``total``).
    """
    started = time.perf_counter()
    total = len(plan.eligible)
    results = tuple(
        _run_source(planned, settings, index, total, on_progress)
        for index, planned in enumerate(plan.eligible, start=1)
    )
    batch_report: Path | None = None
    batch_report_error: ReportError | None = None
    duration = time.perf_counter() - started
    if plan.writes_batch_report:
        try:
            write_batch_report(
                plan.batch_report,
                _batch_report(plan, results, settings, input_specs, duration),
            )
            batch_report = plan.batch_report
        except (OSError, ValidationError) as exc:
            batch_report_error = ReportError("The batch report cannot be written.")
            batch_report_error.__cause__ = exc
    return BatchDedupResult(
        plan=plan,
        results=results,
        failures=tuple(item for item in results if item.status == "FAILED"),
        batch_report=batch_report,
        batch_report_error=batch_report_error,
        duration_seconds=duration,
    )


def _run_source(
    planned: PlannedSource,
    settings: DedupSettings,
    index: int,
    total: int,
    on_progress: ProgressCallback | None,
) -> DedupResult:
    started = time.perf_counter()
    source = planned.source
    try:
        outcome = process_source(
            source,
            settings,
            destination=planned.names["report"].parent,
            on_progress=_positioned(on_progress, index, total),
        )
    except (InputError, ReportError) as exc:
        # The plan was safe, so a refusal here means the outputs changed since: this
        # source fails, nothing of it was written, and the batch goes on.
        result = DedupResult(source, "FAILED", "output_refused", error=exc)
    except Exception as exc:  # noqa: BLE001 - one source never stops the others
        # The text of the exception is not kept: it may hold a cell.
        failure = DedupReportError(
            "An unexpected error stopped the run.", reason="unexpected_error"
        )
        failure.__cause__ = exc
        result = DedupResult(source, "FAILED", "unexpected_error", error=failure)
    else:
        result = DedupResult(
            source,
            outcome.status,
            outcome.reason,
            files=outcome.files,
            report=outcome.report,
            report_path=outcome.report_path,
            verification=outcome.verification,
            error=outcome.error,
        )
    result = dataclasses.replace(
        result, duration_seconds=time.perf_counter() - started
    )
    _announce(result, index, total, on_progress)
    return result


def _positioned(
    callback: ProgressCallback | None, index: int, total: int
) -> ProgressCallback | None:
    """Give every event of a source its position in the batch (design dedup 4.3)."""
    if callback is None:
        return None

    def forward(event: ProgressEvent) -> None:
        callback(
            dataclasses.replace(
                event, index=index, total=total, stage=event.stage or STAGE
            )
        )

    return forward


def _announce(
    result: DedupResult, index: int, total: int, on_progress: ProgressCallback | None
) -> None:
    """Close the events of a source: complete (processed or reused) or failed."""
    if result.status == "FAILED":
        phase, detail = ProgressPhase.FAILED, str(result.reason)
    elif result.status == "SKIPPED":
        phase = ProgressPhase.COMPLETE
        detail = f"already processed, verified by {result.verification}"
    else:
        phase, detail = ProgressPhase.COMPLETE, "processed"
    emit_progress(
        on_progress,
        result.source,
        phase,
        index=index,
        total=total,
        detail=detail,
        duration_seconds=result.duration_seconds,
        stage=STAGE,
    )


# ------------------------------------------------------------- batch report


def _batch_report(
    plan: BatchPlan,
    results: Sequence[DedupResult],
    settings: DedupSettings,
    input_specs: Sequence[str | Path],
    duration_seconds: float,
) -> BatchReport:
    base = plan.batch_report.parent
    entries = [_entry(result, base) for result in results]
    entries += [
        BatchSource(
            file=relative_path(path, base),
            status="EXCLUDED",
            reason=reason,
            verification=None,
            report=None,
            records=None,
            csv_files_created=0,
        )
        for path, reason in plan.excluded
    ]
    done = [item for item in results if item.status == "DONE"]
    skipped = [item for item in results if item.status == "SKIPPED"]
    failed = [item for item in results if item.status == "FAILED"]
    status: BatchStatus = (
        "complete" if not failed else "failed" if len(failed) == len(results) else "partial"
    )
    return BatchReport(
        generator=generator(),
        status=status,
        inputs=[relative_path(os.fspath(spec), base) for spec in input_specs],
        output_dir=(
            relative_path(settings.output_dir, base)
            if settings.output_dir is not None
            else None
        ),
        counters=Counters(
            found=len(results) + len(plan.excluded),
            eligible=len(results),
            excluded=len(plan.excluded),
            done=len(done),
            skipped=len(skipped),
            failed=len(failed),
        ),
        totals=Totals(processed=_tally(done), reused=_tally(skipped)),
        outputs=BatchOutputs(
            csv_files_created=sum(len(item.files) for item in results),
            reports_available=sum(1 for item in results if item.report_path),
            reports_updated=sum(
                1 for item in results if item.report_path and item.status != "SKIPPED"
            ),
        ),
        duration_seconds=duration_seconds,
        sources=entries,
        diagnostics=[note for item in failed if (note := _diagnostic(item, base))],
    )


def _entry(result: DedupResult, base: Path) -> BatchSource:
    return BatchSource(
        file=relative_path(result.source, base),
        status=result.status,
        reason=result.reason,
        verification=result.verification,
        report=(
            relative_path(result.report_path, base) if result.report_path else None
        ),
        records=_records(result.report),
        csv_files_created=len(result.files),
    )


def _records(report: CompleteReport | FailedReport | None) -> SourceRecords | None:
    if not isinstance(report, CompleteReport):
        return None
    counts = report.records
    return SourceRecords(
        total=counts.total,
        distinct=counts.distinct,
        extra_copies=counts.extra_copies,
        duplicate_groups=counts.duplicate_groups,
    )


def _tally(results: Sequence[DedupResult]) -> Tally:
    counts = [item.report.records for item in results if isinstance(item.report, CompleteReport)]
    return Tally(
        sources=len(results),
        records=sum(item.total for item in counts),
        extra_copies=sum(item.extra_copies for item in counts),
        duplicate_groups=sum(item.duplicate_groups for item in counts),
    )


def _diagnostic(result: DedupResult, base: Path) -> str | None:
    """A note for a failure that left the source without a trustworthy report.

    The names of the sources are relative, and no message of an error is copied: a
    refusal names absolute paths.
    """
    name = relative_path(result.source, base)
    if result.reason == "output_refused":
        return (
            f"{name}: an output was refused just before the run (it changed "
            "after the plan); nothing was written."
        )
    if result.report_path is None:
        return f"{name}: the failed report could not be written."
    return None


# --------------------------------------------------------------- public API


def dedup_csv(
    source: str | Path,
    *,
    output_dir: str | Path | None = None,
    max_rows: int | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    memory_budget_mb: int | None = None,
    temp_dir: str | Path | None = None,
    force: bool = False,
    verify_content: bool = False,
    on_progress: ProgressCallback | None = None,
) -> DedupResult:
    """Deduplicate one CSV file exactly (design dedup 4.3).

    Writes up to three CSV files and a JSON report beside the source, or in
    ``output_dir``: nothing is written when the source was already processed and is
    unchanged (``status "SKIPPED"``). The path is a file, never a pattern. Never asks a
    question. An unusable option or a refused output raises before any work; a source
    that fails raises the ``TabalystError`` of its failure, after its failed report is
    written when it can be.
    """
    settings = resolve_dedup_settings(
        config_path,
        delimiter=delimiter,
        encoding=encoding,
        max_rows=max_rows,
        memory_budget_mb=memory_budget_mb,
        temp_dir=temp_dir,
        output_dir=output_dir,
        force=force,
        verify_content=verify_content,
    )
    plan = build_dedup_plan([source], settings, literal=True)
    result = _run_source(plan.eligible[0], settings, 1, 1, on_progress)
    if result.error is not None:
        raise result.error
    return result


def generate_dedups(
    input_specs: Sequence[str | Path],
    *,
    output_dir: str | Path | None = None,
    max_rows: int | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    memory_budget_mb: int | None = None,
    temp_dir: str | Path | None = None,
    force: bool = False,
    verify_content: bool = False,
    on_progress: ProgressCallback | None = None,
) -> BatchDedupResult:
    """Plan and run the deduplication of one or more CSV files (design dedup 4.3).

    The inputs are files and non-recursive patterns. Derived files (the outputs of Dedup
    and of ``sample``) found by a pattern are skipped, an unchanged source that is
    already processed is not read again, and a source that fails does not stop the
    others: it is in ``failures``. A batch that is refused (an invalid option, an output
    that collides or is foreign) raises before any work. Never asks a question.
    ``dedup.summary.json`` is written unless the only input is one file without wildcard.
    """
    settings = resolve_dedup_settings(
        config_path,
        delimiter=delimiter,
        encoding=encoding,
        max_rows=max_rows,
        memory_budget_mb=memory_budget_mb,
        temp_dir=temp_dir,
        output_dir=output_dir,
        force=force,
        verify_content=verify_content,
    )
    return execute_dedups(input_specs, settings, on_progress=on_progress)
