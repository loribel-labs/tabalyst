# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""One source from the first pass to the published CSV (design dedup 4.3, 11.1)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tabalyst.dedup import writer
from tabalyst.dedup.analysis import DedupAnalysis, analyze_dedup
from tabalyst.dedup.failures import DedupInputError, DedupReportError, FailureReason
from tabalyst.dedup.publish import publish_csv
from tabalyst.dedup.settings import DedupSettings
from tabalyst.progress import ProgressCallback


@dataclass(frozen=True)
class SourceOutcome:
    """What happened to one source.

    A failure expected for a source (invalid CSV, row limit, storage, changed source)
    is an outcome with ``status "FAILED"``, its ``reason`` and the ``error`` to raise,
    not an exception. ``files`` are the CSV published by the run.
    """

    source: Path
    status: Literal["DONE", "FAILED"]
    reason: FailureReason | None = None
    files: tuple[Path, ...] = ()
    analysis: DedupAnalysis | None = None
    error: DedupInputError | DedupReportError | None = None


def process_source(
    source: str | Path,
    settings: DedupSettings,
    *,
    destination: Path,
    on_progress: ProgressCallback | None = None,
) -> SourceOutcome:
    """Analyze ``source``, write its outputs and publish them in ``destination``.

    Without the report and the cache of lots 6 and 7, every call processes the
    source; a source without duplicate group produces no file.
    """
    path = Path(source)
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
        files = publish_csv(staged)
    except (DedupInputError, DedupReportError) as exc:
        return SourceOutcome(
            path, "FAILED", exc.reason, analysis=analysis, error=exc
        )
    except Exception as exc:  # noqa: BLE001
        # Any other failure of a source is reported as one, without its text: it may hold a cell.
        failure = DedupReportError(
            "An unexpected error stopped the run.", reason="unexpected_error"
        )
        failure.__cause__ = exc
        return SourceOutcome(
            path, "FAILED", failure.reason, analysis=analysis, error=failure
        )
    finally:
        if staged is not None:
            staged.discard()
    return SourceOutcome(path, "DONE", files=files, analysis=analysis)
