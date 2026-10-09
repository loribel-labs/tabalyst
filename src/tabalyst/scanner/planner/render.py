# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A plan as text for ``tabalyst scan --plan`` (design 20.5)."""

from __future__ import annotations

from collections import Counter

from tabalyst.scanner.planner.models import AnalysisPlan, Candidate, Memory
from tabalyst.scanner.planner.reasons import reason_text


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


def _memory(memory: Memory) -> str:
    return (
        f"{size_text(memory.min)} to {size_text(memory.max)}, "
        f"about {size_text(memory.expected)}"
    )


def _line(candidate: Candidate) -> str:
    method = "" if candidate.method is None else f" [{candidate.method}]"
    where = f"{candidate.dataset} / {candidate.display}"
    return f"{candidate.analyzer}{method}: {where}"


def plan_text(plan: AnalysisPlan, source: str) -> str:
    """The plan of ``source`` as lines of text: what is selected, what is
    already answered, what was left out and why, and the cost."""
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
            how = "asked for" if candidate.selection.requested else "automatic"
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
        if not summary.executable:
            lines.append(
                "The second pass is not available in this version: the plan "
                "only shows what it would do."
            )
    else:
        lines.append("No second reading of the source is needed.")
    return "\n".join(lines)
