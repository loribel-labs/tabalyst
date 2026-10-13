# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A plan as text for ``tabalyst scan --plan`` (design 20.5)."""

from __future__ import annotations

from collections import Counter

from tabalyst.scanner.planner.models import AnalysisPlan, Candidate, Memory
from tabalyst.scanner.planner.reasons import STRATIFICATION, reason_text
from tabalyst.scanner.planner.secondpass import Confirmation, TimeEstimate
from tabalyst.scanner.planner.stratmodels import Stratification


def size_text(count: int) -> str:
    """A byte count in the largest binary unit below 1,024 of it."""
    if count < 1024:
        return f"{count} B"
    value = float(count)
    for unit in ("KiB", "MiB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value / 1024:.1f} GiB"


def duration_text(seconds: float) -> str:
    """A duration as seconds, minutes or hours, rounded for a message."""
    if seconds < 1:
        return "under a second"
    if seconds < 90:
        return f"{round(seconds)} s"
    if seconds < 5400:
        return f"{round(seconds / 60)} min"
    return f"{seconds / 3600:.1f} h"


def estimate_text(estimate: TimeEstimate) -> str:
    """A time estimate as a range of rounded durations."""
    low, high = duration_text(estimate.low_seconds), duration_text(estimate.high_seconds)
    return high if low == high else f"{low} to {high}"


def confirmation_lines(confirmation: Confirmation) -> list[str]:
    """What a run of the plan would cost and whether it would ask first (R1)."""
    lines: list[str] = []
    if confirmation.estimate is not None:
        lines.append(
            f"Estimated time: {estimate_text(confirmation.estimate)} "
            "(a guide from the first pass, not a promise)."
        )
    if confirmation.required:
        why = "; ".join(reason_text(code) for code in confirmation.reasons)
        lines.append(f"Running it would ask for a confirmation first: {why}.")
    else:
        lines.append("Running it would not ask for a confirmation.")
    return lines


def _memory(memory: Memory) -> str:
    return (
        f"{size_text(memory.min)} to {size_text(memory.max)}, "
        f"about {size_text(memory.expected)}"
    )


def _line(candidate: Candidate) -> str:
    method = "" if candidate.method is None else f" [{candidate.method}]"
    where = f"{candidate.dataset} / {candidate.display}"
    return f"{candidate.analyzer}{method}: {where}"


def _strata(count: int | None, basis: str | None) -> str:
    if count is None:
        return "unknown"
    mark = {"estimate": "about ", "bound": "at most "}.get(basis or "", "")
    return f"{mark}{count:,}"


def stratification_lines(advice: Stratification) -> list[str]:
    """The advice on stratified sampling as text (design 20.14): the columns
    that make good keys, then each combination asked for."""
    limits = advice.limits
    lines = ["Stratification (a recommendation from the scan, not a fact of the data):"]
    good = [c for c in advice.columns if c.candidate]
    lines.append(f"  {len(good)} of {len(advice.columns)} columns can be a key by themselves.")
    for column in good:
        notes = "; ".join(STRATIFICATION[r] for r in column.reasons)
        rare = (
            ""
            if column.smallest_share is None
            else f", rarest {column.smallest_share:.2%}, every stratum kept from "
            f"{column.size_for_every_stratum:,} rows"
        )
        absent = (
            ""
            if column.uncovered_at_size is None
            else f", {column.uncovered_at_size} without a row at {advice.sample_size:,} rows"
        )
        lines.append(
            f"    {column.dataset} / {column.display}: "
            f"{_strata(column.strata, column.strata_basis)} strata{rare}{absent}"
            + (f" ({notes})" if notes else "")
        )
    for entry in advice.combinations:
        lines += [
            "",
            f"  {entry.dataset} / {' + '.join(entry.displays)}: risk {entry.risk}",
            "    combinations: "
            + (
                f"at least {entry.strata_bound:,} (saturated)"
                if entry.saturated
                else f"at most {entry.strata_bound:,}"
            )
            + (
                f", estimated {entry.strata_estimate:,}"
                if entry.strata_estimate is not None
                else ""
            ),
        ]
        if entry.observed is not None:
            kind = "exactly" if entry.observed_exact else "at least"
            lines.append(
                f"    row sample: {kind} {entry.observed:,} in {entry.sample_rows:,} rows"
            )
        if entry.mean_quota is not None:
            lines.append(f"    mean rows per stratum: {entry.mean_quota:g}")
        lines += [f"    - {STRATIFICATION[r]}" for r in entry.reasons]
        lines += [f"    * {STRATIFICATION[s]}" for s in entry.suggestions]
    lines.append(
        f"  Limits: {limits.max_strata_per_column} strata per column, "
        f"{limits.max_states:,} states in a sample; a missing value is a stratum of its own."
    )
    return lines


def plan_text(
    plan: AnalysisPlan, source: str, confirmation: Confirmation | None = None
) -> str:
    """The plan of ``source`` as lines of text: what is selected, what is
    already answered, what was left out and why, and the cost. With a
    ``confirmation``, the estimated time and whether a run would ask first."""
    summary = plan.summary
    lines = [
        f"Plan for {source} (plan {plan.plan_id[:12]}, planner {plan.planner_version}).",
        (
            f"{summary.candidates} candidates: {summary.selected} selected, "
            f"{summary.already_satisfied} already answered by the scan, "
            f"{summary.rejected} left out."
        ),
    ]
    selected = sorted(
        (c for c in plan.candidates if c.selection.state == "selected"),
        key=lambda c: c.selection.priority or 0,
    )
    if selected:
        lines += ["", "Selected:"]
        for candidate in selected:
            memory = candidate.costs.memory.max if candidate.costs else 0
            cpu = candidate.costs.cpu if candidate.costs else "-"
            how = (
                "asked for"
                if candidate.selection.requested
                else candidate.selection.reason
            )
            note = "" if candidate.execution.available else ", not available yet"
            lines.append(
                f"  {candidate.selection.priority}. {_line(candidate)} "
                f"(up to {size_text(memory)}, CPU {cpu}, {how}{note})"
            )
    left_out = [
        c
        for c in plan.candidates
        if c.selection.state == "rejected" and c.selection.reason != "not_applicable"
    ]
    if left_out:
        lines += ["", "Left out:"]
        lines += [
            f"  {_line(c)}: {reason_text(c.selection.reason)}" for c in left_out
        ]
    inapplicable = Counter(
        reason
        for c in plan.candidates
        if c.applicability.state == "not_applicable"
        for reason in c.applicability.reasons
    )
    if inapplicable:
        lines += ["", "Not applicable:"]
        lines += [
            f"  {count} x {reason_text(reason)}"
            for reason, count in sorted(inapplicable.items())
        ]
    lines.append("")
    if summary.second_pass_required:
        cells = plan.common.cells
        lines.append(
            "A second reading of the source is needed"
            + ("" if cells is None else f" ({cells:,} cells, CPU {plan.common.cpu})")
            + f". Memory: {_memory(summary.memory)}."
        )
    else:
        lines.append("No second reading of the source is needed.")
    waiting = sum(
        1
        for c in plan.candidates
        if c.selection.state == "selected" and not c.execution.available
    )
    if waiting == summary.selected and waiting:
        lines.append("None of the selected analyses can run in this version.")
    elif waiting:
        lines.append(
            f"{waiting} of the selected analyses cannot run in this version; "
            "tabalyst scan --deep runs the others."
        )
    if confirmation is not None:
        lines += confirmation_lines(confirmation)
    if plan.stratification is not None:
        lines += ["", *stratification_lines(plan.stratification)]
    return "\n".join(lines)
