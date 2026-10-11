# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reusable boundary of the second pass, for the CLI and the Python API
(design 20, rule R1).

``prepare_deep`` scans the sources (or reuses their current Scan) and plans the
second pass of each as if it were forced; it asks nothing and reads no source
again. ``execute_deep`` runs those plans. It never prompts: a batch that needs a
confirmation runs only when the caller says it was given (``confirmed``).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from tabalyst.batch import validate_outputs
from tabalyst.config import DeepSettings, load_config_layers, settings_from_layer
from tabalyst.deep_store import ConfirmationRequired, write_deep
from tabalyst.errors import TabalystError
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.scan_service import ScanFailure, ScanSuccess, generate_scans
from tabalyst.scanner.planner import (
    Confirmation,
    SecondPassPlan,
    combine_confirmations,
    default_registry,
    plan_second_pass,
)
from tabalyst.scanner.secondpass import (
    DeepResult,
    SecondPassOutcome,
    deep_path_for,
    load_deep,
    reading_candidates,
    run_second_pass,
)
from tabalyst.service import ConfigPath, _config_paths


@dataclass(frozen=True)
class DeepJob:
    """One source with its Scan, the plan of its second pass and the document
    it writes."""

    scan: ScanSuccess
    second: SecondPassPlan
    deep_path: Path
    # The stored document of this Scan, whose results a run keeps.
    previous: DeepResult | None = None

    @property
    def pending(self) -> int:
        """Analyses a run has to compute from the source; 0 when the stored
        results and the Scan are enough and the source need not be read."""
        return len(reading_candidates(self.second.plan, self.previous))

    @property
    def source(self) -> Path:
        return self.scan.job.source


@dataclass(frozen=True)
class DeepPreparation:
    """The sources ready for a second pass. ``confirmation`` is one for the whole
    batch, with the total (R1); ``failures`` are the sources whose Scan failed."""

    jobs: tuple[DeepJob, ...]
    failures: tuple[ScanFailure, ...]
    settings: DeepSettings
    warnings: tuple[tuple[Path, str], ...] = ()
    confirmation: Confirmation | None = None
    # The documents go to the shared storage, whose writes are exclusive.
    shared: bool = False
    indent: bool = False
    # The ``workers`` the Scans were asked for; the second pass honors it.
    workers: int | None = None

    @property
    def requires_confirmation(self) -> bool:
        return self.confirmation is not None and self.confirmation.required


@dataclass(frozen=True)
class DeepSuccess:
    job: DeepJob
    outcome: SecondPassOutcome
    # False when the stored document already said the same.
    written: bool


@dataclass(frozen=True)
class DeepFailure:
    job: DeepJob
    error: TabalystError


@dataclass(frozen=True)
class BatchDeepResult:
    preparation: DeepPreparation
    successes: tuple[DeepSuccess, ...]
    failures: tuple[DeepFailure, ...]


def prepare_deep(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    config_path: ConfigPath | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
    workers: int | None = None,
    counters: bool = False,
    project_storage: bool = True,
    html: bool = False,
) -> DeepPreparation:
    """Scan the sources, or reuse the current stored Scan of each, and plan the
    second pass of every Scan as a forced one, with the analyzers that have an
    executor. Writes the Scans like ``generate_scans``, and nothing else.

    ``output`` and ``output_dir`` name the Scan as for ``tabalyst scan``; the
    second-pass document goes beside it (``deep_path_for``). A source whose
    Scan fails is reported in ``failures`` and does not stop the others.
    """
    config_paths = _config_paths(config_path)
    top_level, _ = load_config_layers(config_paths)
    top = settings_from_layer(top_level)
    batch = generate_scans(
        input_specs,
        output=output,
        output_dir=output_dir,
        config_path=config_path,
        delimiter=delimiter,
        encoding=encoding,
        collections=collections,
        force=force,
        on_progress=on_progress,
        workers=workers,
        counters=counters,
        project_storage=project_storage,
        refresh=False,
        html=html,
    )
    failures = list(batch.failures)
    jobs: list[DeepJob] = []
    registry = default_registry().runnable()
    for success in batch.successes:
        try:
            second = plan_second_pass(
                success.result, forced=True, registry=registry, deep=top.deep.settings()
            )
        except TabalystError as exc:
            failures.append(ScanFailure(job=success.job, error=exc))
            continue
        assert success.job.output is not None
        deep_path = deep_path_for(success.job.output)
        jobs.append(DeepJob(success, second, deep_path, load_deep(deep_path)))
    validate_outputs(
        ((job.source, job.deep_path) for job in jobs),
        sources=[*(job.source for job in jobs), *config_paths],
        force=True,
        label="Second pass",
    )
    return DeepPreparation(
        jobs=tuple(jobs),
        failures=tuple(failures),
        settings=top.deep.settings(),
        warnings=batch.plan.warnings,
        # Only the sources with something left to compute count: a run that
        # reads nothing never asks, whatever the size of the file.
        confirmation=(
            combine_confirmations(job.second.confirmation for job in jobs if job.pending)
            if jobs
            else None
        ),
        shared=output is None and output_dir is None,
        indent=top.output.json_indent,
        workers=workers,
    )


def _write(
    job: DeepJob,
    outcome: SecondPassOutcome,
    preparation: DeepPreparation,
    previous: DeepResult | None,
) -> bool:
    return write_deep(
        job.deep_path,
        outcome,
        previous,
        shared=preparation.shared,
        indent=preparation.indent,
    )


def execute_deep(
    preparation: DeepPreparation,
    *,
    confirmed: bool = False,
    on_progress: ProgressCallback | None = None,
) -> BatchDeepResult:
    """Run the second pass of every prepared source, one after the other, and
    write a document for each. Raises ``ConfirmationRequired`` when the batch
    needs a confirmation and ``confirmed`` is false; a source that fails (a
    changed source, a source that cannot be read again) does not stop the
    others, and its document is not written (design 20.6)."""
    if preparation.requires_confirmation and not confirmed:
        assert preparation.confirmation is not None
        raise ConfirmationRequired(preparation.confirmation)
    successes: list[DeepSuccess] = []
    failures: list[DeepFailure] = []
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
                        detail=event.detail
                        or ("second pass" if event.phase == ProgressPhase.READING else None),
                        bytes_read=event.bytes_read,
                        bytes_total=event.bytes_total,
                    )
                )

        try:
            previous = job.previous
            outcome = run_second_pass(
                job.scan.result,
                job.source,
                job.second.plan,
                settings=preparation.settings,
                previous=previous,
                on_progress=forward,
                workers=preparation.workers,
            )
            emit_progress(
                on_progress, job.source, ProgressPhase.WRITING, index=index, total=total
            )
            written = _write(job, outcome, preparation, previous)
        except TabalystError as exc:
            failures.append(DeepFailure(job, exc))
            emit_progress(
                on_progress,
                job.source,
                ProgressPhase.FAILED,
                index=index,
                total=total,
                detail=str(exc),
            )
        else:
            successes.append(DeepSuccess(job, outcome, written))
            emit_progress(
                on_progress,
                job.source,
                ProgressPhase.COMPLETE,
                index=index,
                total=total,
                duration_seconds=outcome.document.run.duration_seconds,
            )
    return BatchDeepResult(preparation, tuple(successes), tuple(failures))


def generate_deep(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    config_path: ConfigPath | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
    force: bool = False,
    on_progress: ProgressCallback | None = None,
    workers: int | None = None,
    counters: bool = False,
    project_storage: bool = True,
    confirmed: bool = False,
) -> BatchDeepResult:
    """Scan, plan and run the second pass of one or more sources.

    The options are those of ``prepare_deep``. It never prompts: it raises
    ``ConfirmationRequired`` before reading any source again when the batch needs
    a confirmation and ``confirmed`` is false (rule R1).
    """
    preparation = prepare_deep(
        input_specs,
        output=output,
        output_dir=output_dir,
        config_path=config_path,
        delimiter=delimiter,
        encoding=encoding,
        collections=collections,
        force=force,
        on_progress=on_progress,
        workers=workers,
        counters=counters,
        project_storage=project_storage,
    )
    return execute_deep(preparation, confirmed=confirmed, on_progress=on_progress)
