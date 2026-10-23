# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""One source from the decision to the published CSV and report (design dedup 4.3, 11.1)."""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tabalyst.dedup import writer
from tabalyst.dedup.analysis import DedupAnalysis, analyze_dedup
from tabalyst.dedup.cache import (
    Verification,
    assess,
    decide_skip,
    refuse_unsafe_outputs,
)
from tabalyst.dedup.discovery import managed_names
from tabalyst.dedup.failures import DedupInputError, DedupReportError, FailureReason
from tabalyst.dedup.publish import publish_set, retire_outputs
from tabalyst.dedup.report import (
    CompleteReport,
    FailedReport,
    complete_report,
    failed_report,
    planned_inventory,
    recovery_report,
    write_report,
)
from tabalyst.dedup.settings import DedupSettings
from tabalyst.progress import ProgressCallback

SkipReason = Literal["already_processed"]


@dataclass(frozen=True)
class SourceOutcome:
    """What happened to one source.

    A failure expected for a source (invalid CSV, row limit, storage, changed source)
    is an outcome with ``status "FAILED"``, its ``reason`` and the ``error`` to raise,
    not an exception. ``files`` are the CSV published by the run and ``report`` the
    document written beside them (``None`` if even a failed report could not be
    written). A ``"SKIPPED"`` source (``reason "already_processed"``) was not touched:
    ``report`` is the one that was already there and ``verification`` says how far
    the decision went (``"metadata"`` or ``"digest"``); ``verification`` is ``None``
    for any other status.
    """

    source: Path
    status: Literal["DONE", "SKIPPED", "FAILED"]
    reason: FailureReason | SkipReason | None = None
    files: tuple[Path, ...] = ()
    analysis: DedupAnalysis | None = None
    error: DedupInputError | DedupReportError | None = None
    report: CompleteReport | FailedReport | None = None
    report_path: Path | None = None
    verification: Verification | None = None


def process_source(
    source: str | Path,
    settings: DedupSettings,
    *,
    destination: Path,
    on_progress: ProgressCallback | None = None,
) -> SourceOutcome:
    """Decide, analyze, write, publish and report one source.

    A name that is the source, a directory, or an existing file that no Dedup report
    proves is its own is refused by an exception before anything is written (design
    dedup 7.4). Then the source is skipped when its result is current (11.2), unless
    ``settings.force``. Otherwise the outputs are staged and published by the protocol
    of 11.5: the report ends as ``complete`` only once the whole set is in place, and
    the outputs of an earlier run that the new set does not hold are deleted. A source
    that fails gets its earlier outputs deleted and a failed report, both best effort
    (the primary failure is never replaced by a failure to report it). An interruption
    leaves a recovery report, which the next run uses to prove its ownership.
    """
    path = Path(source)
    started = time.perf_counter()
    names = managed_names(path, destination)
    previous = assess(names, verify_content=settings.verify_content)
    refuse_unsafe_outputs(path, names, previous, force=settings.force)
    analysis: DedupAnalysis | None = None
    staged: writer.StagedOutputs | None = None
    try:
        writer.remove_stale_temporaries(path, destination)
        if not settings.force:
            decision = decide_skip(
                path, settings, names, previous, on_progress=on_progress
            )
            if decision is not None:
                return SourceOutcome(
                    path,
                    "SKIPPED",
                    "already_processed",
                    report=decision.report,
                    report_path=names["report"],
                    verification=decision.verification,
                )
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
        files = publish_set(
            staged,
            names=names,
            previous=previous,
            recovery=recovery_report(
                path.name,
                settings,
                previous=list(previous.owned.values()),
                planned=planned_inventory(staged),
                analysis=analysis,
            ),
            report=report,
            write=write_report,
        )
    except (DedupInputError, DedupReportError) as exc:
        return _failed(path, settings, names, analysis, exc)
    except Exception as exc:  # noqa: BLE001 - any failure of a source is that source's outcome
        # The text of the exception is not kept: it may hold a cell.
        failure = DedupReportError(
            "An unexpected error stopped the run.", reason="unexpected_error"
        )
        failure.__cause__ = exc
        return _failed(path, settings, names, analysis, failure)
    finally:
        if staged is not None:
            staged.discard()
    return SourceOutcome(
        path,
        "DONE",
        files=files,
        analysis=analysis,
        report=report,
        report_path=names["report"],
    )


def _failed(
    path: Path,
    settings: DedupSettings,
    names: Mapping[str, Path],
    analysis: DedupAnalysis | None,
    error: DedupInputError | DedupReportError,
) -> SourceOutcome:
    """Retire the earlier outputs, then replace the report by a failed one (D2, DD-10).

    The failed report replaces the report only once no owned output is left: with an
    owned CSV still in place it would make that file foreign. If an output cannot go,
    or the report cannot be written, the recovery report or the earlier report stays
    and the error that is raised stays the primary one.
    """
    report_path = names["report"]
    report = failed_report(path, settings, error)
    written: Path | None = None
    try:
        current = assess(names)
        retired = retire_outputs(
            names=names,
            current=current,
            recovery=lambda: recovery_report(
                path.name,
                settings,
                previous=list(current.owned.values()),
                planned=[],
                analysis=analysis,
            ),
            write=write_report,
        )
        # A report that turned foreign during the run is replaced only if --force says so.
        if retired and (settings.force or report_path not in current.foreign):
            write_report(report_path, report)
            written = report_path
    except Exception:  # noqa: BLE001 - best effort: the primary failure is what is raised
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
