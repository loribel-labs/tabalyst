# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second pass inside Tabalyst Report (design 20.1, rule R1).

``tabalyst report`` lets the planner decide whether a second pass has a benefit
and a low cost, and what it holds; ``--deep`` forces it. This module plans that
pass for a finished Scan, runs it and gives the ``analyses`` member the Report
embeds. The renderer stays pure: it reads that member and never reads a source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from tabalyst.config import DeepMode, DeepSettings
from tabalyst.deep_store import ConfirmationRequired, write_deep
from tabalyst.errors import TabalystError
from tabalyst.models import AnalysesBlock, AnalysesMode
from tabalyst.progress import ProgressCallback, ProgressPhase, emit_progress
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.planner import (
    Confirmation,
    SecondPassPlan,
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
from tabalyst.source_guard import SourceNotReadable

# Why an analysis that needs the source was left out of a Report.
SOURCE_NOT_READ = "source_not_read"
SOURCE_UNAVAILABLE = "source_unavailable"

REASONS = {
    SOURCE_NOT_READ: (
        "this report was built from a scan document, which reads no source: "
        "run tabalyst report --deep to read it"
    ),
    SOURCE_UNAVAILABLE: "the source of the scan document was not found beside it",
}


@dataclass(frozen=True)
class ChainPlan:
    """The second pass of one Report: how it was decided, the plan, the stored
    results it keeps and where the source is, if it may be read."""

    mode: AnalysesMode
    # None when the mode is ``off``: nothing is planned.
    second: SecondPassPlan | None
    previous: DeepResult | None
    deep_path: Path
    source: Path | None
    # The reason the source is not read (``SOURCE_NOT_READ`` or
    # ``SOURCE_UNAVAILABLE``); None when it is.
    skip_reading: str | None
    # The documents beside the shared Scan are written under the workspace lock.
    shared: bool
    indent: bool
    settings: DeepSettings
    # Worker processes of the run (``None``: as many as the size of the source
    # calls for); the ``--workers`` of the command applies to both passes.
    workers: int | None = None

    @property
    def pending(self) -> int:
        """Analyses to compute from the source: 0 when the stored results and the
        Scan are enough, and whatever the mode when the source is not read."""
        if self.second is None or self.skip_reading is not None:
            return 0
        return len(reading_candidates(self.second.plan, self.previous))

    @property
    def confirmation(self) -> Confirmation | None:
        """What a forced pass must have confirmed (R1); none for an automatic
        one, which never goes beyond a limit, and none when nothing is read."""
        if self.second is None or self.mode != "forced" or not self.pending:
            return None
        return self.second.confirmation


def chain_mode(mode: DeepMode, *, deep: bool) -> AnalysesMode:
    """How the second pass of a Report is decided: ``--deep`` forces it whatever
    the configuration says; ``deep.mode`` ``off`` and ``force`` otherwise."""
    if deep:
        return "forced"
    return {"auto": "auto", "force": "forced", "off": "off"}[mode]


def plan_chain(
    scan: ScanResult,
    *,
    scan_path: Path,
    source: Path | None,
    mode: AnalysesMode,
    settings: DeepSettings,
    reads_source: bool,
    shared: bool,
    indent: bool,
    workers: int | None = None,
) -> ChainPlan:
    """Plan the second pass of a Report, running nothing.

    ``reads_source`` is false for a Report built from a scan document without
    ``--deep``: it promises not to read the source. ``source`` is None when the
    document's source is not beside it. A forced second pass that cannot read the
    source is an error, never a silent omission (specification 18.2).
    """
    deep_path = deep_path_for(scan_path)
    if mode == "off":
        return ChainPlan(
            mode, None, None, deep_path, source, None, shared, indent, settings, workers
        )
    skip_reading: str | None = None
    if source is None:
        skip_reading = SOURCE_UNAVAILABLE
    elif not reads_source:
        skip_reading = SOURCE_NOT_READ
    if skip_reading == SOURCE_UNAVAILABLE and mode == "forced":
        raise SourceNotReadable(
            "--deep needs to read the source of the scan document, which was not "
            "found beside it. The report was not written. Restore the source "
            "next to the document or report the source itself."
        )
    second = plan_second_pass(
        scan,
        forced=mode == "forced",
        registry=default_registry().runnable(),
        deep=settings,
    )
    return ChainPlan(
        mode,
        second,
        load_deep(deep_path),
        deep_path,
        source,
        skip_reading,
        shared,
        indent,
        settings,
        workers,
    )


def require_confirmation(chain: ChainPlan, *, confirmed: bool) -> None:
    """Raise ``ConfirmationRequired`` when a forced second pass must be
    confirmed and was not (rule R1): the API never prompts."""
    confirmation = chain.confirmation
    if confirmation is not None and confirmation.required and not confirmed:
        raise ConfirmationRequired(confirmation)


def _outcome_of(outcome: SecondPassOutcome) -> str:
    """The word for what a run did: it computed something, reused what was
    stored, left analyses out, or had nothing to do."""
    if outcome.executed:
        return "ran"
    if outcome.reused:
        return "reused"
    if outcome.skipped:
        return "unavailable"
    return "nothing_selected"


def run_chain(
    chain: ChainPlan,
    scan: ScanResult,
    *,
    on_progress: ProgressCallback | None = None,
    progress_source: Path | None = None,
) -> AnalysesBlock:
    """Run the second pass of a Report and write its document beside the Scan.

    An automatic pass that meets an error (a source that changed or went away
    since the Scan) gives ``failed`` and the Report goes without it: it was an
    extra, not what was asked for. A forced pass raises."""
    if chain.second is None:
        return AnalysesBlock(
            mode=chain.mode, outcome="disabled", reason="deep.mode is off"
        )
    plan = chain.second.plan
    source = chain.source if chain.source is not None else chain.deep_path
    where = progress_source or source
    selected = sum(1 for c in plan.candidates if c.selection.state == "selected")
    deep_started = perf_counter()
    if selected:
        emit_progress(
            on_progress,
            where,
            ProgressPhase.ANALYZING,
            detail=f"second pass: {selected} analyses",
        )
    try:
        outcome = run_second_pass(
            scan,
            source,
            plan,
            settings=chain.settings,
            previous=chain.previous,
            skip_reading=chain.skip_reading,
            on_progress=on_progress,
            workers=chain.workers,
        )
        # A report that reads no source writes no file beside the scan document.
        if chain.skip_reading is None:
            write_deep(
                chain.deep_path,
                outcome,
                chain.previous,
                shared=chain.shared,
                indent=chain.indent,
            )
    except TabalystError as exc:
        if chain.mode == "forced":
            raise
        return AnalysesBlock(mode=chain.mode, outcome="failed", reason=str(exc))
    if selected:
        emit_progress(
            on_progress,
            where,
            ProgressPhase.COMPLETE,
            duration_seconds=perf_counter() - deep_started,
            stage="Scan Deep",
        )
    reason = REASONS[chain.skip_reading] if chain.skip_reading and outcome.skipped else None
    return AnalysesBlock(
        mode=chain.mode,
        outcome=_outcome_of(outcome),  # type: ignore[arg-type]
        reason=reason,
        deep=outcome.document,
    )
