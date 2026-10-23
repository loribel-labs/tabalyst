# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""One source from the first pass to the published CSV and report (design dedup 4.3, 11.1)."""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tabalyst.dedup import writer
from tabalyst.dedup.analysis import DedupAnalysis, analyze_dedup
from tabalyst.dedup.discovery import managed_names
from tabalyst.dedup.failures import DedupInputError, DedupReportError, FailureReason
from tabalyst.dedup.publish import publish_csv
from tabalyst.dedup.report import (
    CompleteReport,
    FailedReport,
    complete_report,
    failed_report,
    write_report,
)
from tabalyst.dedup.settings import DedupSettings
from tabalyst.progress import ProgressCallback


@dataclass(frozen=True)
class SourceOutcome:
    """What happened to one source.

    A failure expected for a source (invalid CSV, row limit, storage, changed source)
    is an outcome with ``status "FAILED"``, its ``reason`` and the ``error`` to raise,
    not an exception. ``files`` are the CSV published by the run and ``report`` the
    document written beside them (``None`` if even a failed report could not be written).
    """

    source: Path
    status: Literal["DONE", "FAILED"]
    reason: FailureReason | None = None
    files: tuple[Path, ...] = ()
    analysis: DedupAnalysis | None = None
    error: DedupInputError | DedupReportError | None = None
    report: CompleteReport | FailedReport | None = None
    report_path: Path | None = None


def process_source(
    source: str | Path,
    settings: DedupSettings,
    *,
    destination: Path,
    on_progress: ProgressCallback | None = None,
) -> SourceOutcome:
    """Analyze ``source``, write its outputs, publish them and then its report.

    The JSON report is written last, atomically: a report on disk means that the CSV
    it lists were published. A source that fails gets a failed report, written on a
    best-effort basis (the primary failure is never replaced by a failure to report it).
    Without the cache and the ownership of lot 7, every call processes the source and
    does not delete the outputs of an earlier run that this one no longer produces.
    """
    path = Path(source)
    started = time.perf_counter()
    report_path = managed_names(path, destination)["report"]
    analysis: DedupAnalysis | None = None
    staged: writer.StagedOutputs | None = None
    try:
        writer.remove_stale_temporaries(path, destination)
        analysis = analyze_dedup(
            path,
            csv=settings.csv,
            max_rows=settings.max_rows,
            memory_budget_mb=settings.memory_budget_mb,
            temp_dir=settings.temp_dir,
            on_progress=on_progress,
            measure_memory=settings.verbose,
        )
        staged = writer.write_outputs(
            path,
            analysis,
            csv=settings.csv,
            destination=destination,
            on_progress=on_progress,
        )
        report = complete_report(
            path.name,
            analysis,
            staged,
            settings,
            duration_seconds=time.perf_counter() - started,
        )
        files = publish_csv(staged)
        try:
            write_report(report_path, report)
        except OSError as exc:
            # CSV without the report that proves them would be unowned files.
            for published in files:
                published.unlink(missing_ok=True)
            raise DedupReportError(
                "The report cannot be written.", reason="output_unwritable"
            ) from exc
    except (DedupInputError, DedupReportError) as exc:
        return _failed(path, settings, report_path, analysis, exc)
    except Exception as exc:  # noqa: BLE001 - any failure of a source is that source's outcome
        # The text of the exception is not kept: it may hold a cell.
        failure = DedupReportError(
            "An unexpected error stopped the run.", reason="unexpected_error"
        )
        failure.__cause__ = exc
        return _failed(path, settings, report_path, analysis, failure)
    finally:
        if staged is not None:
            staged.discard()
    return SourceOutcome(
        path,
        "DONE",
        files=files,
        analysis=analysis,
        report=report,
        report_path=report_path,
    )


def _failed(
    path: Path,
    settings: DedupSettings,
    report_path: Path,
    analysis: DedupAnalysis | None,
    error: DedupInputError | DedupReportError,
) -> SourceOutcome:
    report = failed_report(path, settings, error)
    written: Path | None = report_path
    try:
        write_report(report_path, report)
    except OSError:
        # Best effort (design dedup 12.4): the error that is raised stays the primary one.
        written = None
    return SourceOutcome(
        path,
        "FAILED",
        error.reason,
        analysis=analysis,
        error=error,
        report=report if written else None,
        report_path=written,
    )
