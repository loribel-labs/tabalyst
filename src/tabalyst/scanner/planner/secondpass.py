# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Time estimate and confirmation of a second pass (design 20.3, rule R1).

The plan holds nothing measured. What depends on the machine, the time the
second pass may take, is estimated here from the first pass of the Scan and
feeds messages and one threshold; it is never an input of the selection.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from tabalyst.config import DeepSettings
from tabalyst.scanner.models import ScanResult
from tabalyst.scanner.planner.costmodel import (
    DEFAULT_CONFIRM_SECONDS,
    READING_CELLS_PER_SECOND,
    READING_LOW_SHARE,
)
from tabalyst.scanner.planner.facts import scan_facts
from tabalyst.scanner.planner.models import AnalysisPlan, Budgets
from tabalyst.scanner.planner.planner import AnalysisRequest, plan_analyses
from tabalyst.scanner.planner.registry import AnalyzerRegistry

TIME_REASON = "time_over_threshold"
# The first pass reads on the machine that plans, so its reading phase tells
# how fast that machine is; the factor is held between these bounds.
MACHINE_FACTOR = (0.25, 4.0)
# The analysis work is modeled, not observed: a range around the model.
WORK_RANGE = (0.5, 2.0)


@dataclass(frozen=True, slots=True)
class TimeEstimate:
    """Seconds a second pass may take, as a range. It is a message, not a
    promise: compression, disk cache, width of the records and the format
    change it (COST-03)."""

    low_seconds: float
    high_seconds: float


@dataclass(frozen=True, slots=True)
class Confirmation:
    """Whether a second pass must be confirmed before it starts, and why
    (R1). ``reasons`` are codes of ``reasons.CONFIRMATION``."""

    required: bool
    reasons: tuple[str, ...]
    memory_max_bytes: int
    estimate: TimeEstimate | None


@dataclass(frozen=True, slots=True)
class SecondPassPlan:
    """A plan with what running it would cost and whether it must be
    confirmed. The API returns this and runs nothing: it executes only with an
    explicit parameter."""

    plan: AnalysisPlan
    confirmation: Confirmation

    @property
    def estimate(self) -> TimeEstimate | None:
        return self.confirmation.estimate

    @property
    def requires_confirmation(self) -> bool:
        return self.confirmation.required


def estimate_time(plan: AnalysisPlan, scan: ScanResult) -> TimeEstimate | None:
    """The time of the second pass of ``plan``, or ``None`` when no selected
    analysis reads the source.

    The reading costs what the first pass spent reading, at most (it also
    hashed and built records) and at least its parsing share; the analyses add
    the nanoseconds the cost model gives to each cell they read, scaled by how
    fast the first pass read compared with the reference machine.
    """
    if not plan.common.requires_source:
        return None
    reading = scan.run.timings.reading
    cells = plan.common.cells or 0
    modeled = cells / READING_CELLS_PER_SECOND
    low_factor, high_factor = MACHINE_FACTOR
    speed = (
        1.0 if reading <= 0 or modeled <= 0 else min(high_factor, max(low_factor, reading / modeled))
    )
    values = {(facts.dataset, facts.field): facts.values for facts in scan_facts(scan)}
    nanoseconds = sum(
        values.get((candidate.dataset, candidate.field), 0) * candidate.costs.cell_ns
        for candidate in plan.candidates
        if candidate.selection.state == "selected"
        and candidate.execution.requires_source
        and candidate.costs is not None
    )
    work = nanoseconds / 1e9 * speed
    share = READING_LOW_SHARE if scan.source.format == "csv" else 1.0
    low_work, high_work = WORK_RANGE
    return TimeEstimate(
        low_seconds=reading * share + work * low_work,
        high_seconds=reading + work * high_work,
    )


def confirmation_for(
    plan: AnalysisPlan,
    estimate: TimeEstimate | None,
    *,
    threshold_seconds: float = DEFAULT_CONFIRM_SECONDS,
) -> Confirmation:
    """The confirmation a plan needs: it exceeds an automatic limit, or its
    time may pass the threshold. What the planner picks by itself never does
    the first, and a plan that reads no source never does the second."""
    reasons = list(plan.summary.beyond_automatic)
    if estimate is not None and estimate.high_seconds >= threshold_seconds:
        reasons.append(TIME_REASON)
    return Confirmation(
        required=bool(reasons),
        reasons=tuple(reasons),
        memory_max_bytes=plan.summary.memory.max,
        estimate=estimate,
    )


def combine_confirmations(
    items: Iterable[Confirmation],
    *,
    threshold_seconds: float = DEFAULT_CONFIRM_SECONDS,
) -> Confirmation:
    """One confirmation for a batch, with the total (R1): the times add up,
    since the files are read one after the other, and the memory is the
    largest of them. Every file may be under the threshold and the batch over
    it."""
    reasons: list[str] = []
    memory = 0
    estimates: list[TimeEstimate] = []
    for item in items:
        memory = max(memory, item.memory_max_bytes)
        for reason in item.reasons:
            if reason != TIME_REASON and reason not in reasons:
                reasons.append(reason)
        if item.estimate is not None:
            estimates.append(item.estimate)
    total = (
        TimeEstimate(
            sum(e.low_seconds for e in estimates), sum(e.high_seconds for e in estimates)
        )
        if estimates
        else None
    )
    if total is not None and total.high_seconds >= threshold_seconds:
        reasons.append(TIME_REASON)
    return Confirmation(
        required=bool(reasons),
        reasons=tuple(reasons),
        memory_max_bytes=memory,
        estimate=total,
    )


def plan_second_pass(
    scan: ScanResult,
    *,
    requests: Sequence[AnalysisRequest] = (),
    automatic: bool = True,
    forced: bool = False,
    budgets: Budgets | None = None,
    registry: AnalyzerRegistry | None = None,
    deep: DeepSettings | None = None,
    threshold_seconds: float = DEFAULT_CONFIRM_SECONDS,
) -> SecondPassPlan:
    """Plan the second pass of a finished Scan with its estimate and its
    confirmation. Runs nothing, asks nothing and writes nothing."""
    plan = plan_analyses(
        scan,
        requests=requests,
        automatic=automatic,
        forced=forced,
        budgets=budgets,
        registry=registry,
        deep=deep,
    )
    estimate = estimate_time(plan, scan)
    return SecondPassPlan(
        plan, confirmation_for(plan, estimate, threshold_seconds=threshold_seconds)
    )
