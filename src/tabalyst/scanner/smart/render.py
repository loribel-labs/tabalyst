# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A sampling plan as text for ``tabalyst scan --plan --smart`` (design 20.15)."""

from __future__ import annotations

from tabalyst.scanner.planner.render import size_text
from tabalyst.scanner.smart.models import SamplingPlan, Target
from tabalyst.scanner.smart.reasons import SIZE, catalog_text, pass_text

TOP_TARGETS = 10

FAMILY_NAMES = {
    "low_cardinality": "Low cardinality",
    "structured_string": "Structured strings",
    "numeric": "Numeric",
    "date": "Dates",
    "quality": "Quality",
    "relations": "Relations",
}


def _frequency(count: int | None, share: float | None, accuracy: str) -> str:
    if accuracy == "unknown" or share is None:
        return "frequency unknown"
    mark = {"indicator": "about ", "lower_bound": "at least "}.get(accuracy, "")
    rows = "" if count is None else f"{count:,} {'row' if count == 1 else 'rows'}, "
    return f"{rows}{mark}{share:.4%}"


def _label(target: Target) -> str:
    """The kind of a target, with the rule of an observation."""
    rule = target.predicate.params.get("rule")
    return f"{target.predicate.kind}:{rule}" if rule is not None else target.predicate.kind


def sampling_plan_text(plan: SamplingPlan, name: str) -> str:
    """The plan as lines for a terminal. Targets are named by the columns they
    concern and the kind of predicate, never by a value of the data."""
    summary = plan.summary
    lines = [
        f"Smart sample plan for {name} (dataset {plan.dataset}, {plan.size.records:,} rows)",
        "",
        (
            "A smart sample covers diversity and rare cases; its proportions are not "
            "those of the population. The targets are those the Scan and the stored "
            "second pass know: other cases may exist."
        ),
        "",
        f"Targets: {summary.targets} ({summary.mandatory} mandatory, "
        f"{summary.optional} optional)"
        + (f", {summary.not_evaluable} the sample cannot recognize yet" if summary.not_evaluable else "")
        + (f", {summary.dropped} left out by the limits of the plan (budget of targets, groups of typos)" if summary.dropped else "")
        + ".",
    ]
    for family in summary.families:
        lines.append(
            f"  {FAMILY_NAMES[family.family]}: {family.targets} targets, "
            f"{family.mandatory} mandatory"
            + (f", {family.dropped} left out" if family.dropped else "")
        )
    incomplete = [c for c in plan.catalogs if c.targets and not c.complete]
    if incomplete:
        lines += ["", "Columns whose values are only partly known:"]
        for catalog in incomplete:
            why = "; ".join(catalog_text(code) for code in catalog.reasons)
            lines.append(f"  {catalog.display} ({FAMILY_NAMES[catalog.family]}): {why}")
    heaviest = [t for t in plan.targets if t.feasibility == "ready"]
    heaviest = sorted(heaviest, key=lambda t: (-t.weight.value, t.id))[:TOP_TARGETS]
    if heaviest:
        lines += ["", "Heaviest targets:"]
        for target in heaviest:
            lines.append(
                f"  {target.weight.value:g}  {', '.join(target.displays) or target.dataset}: "
                f"{_label(target)}"
                f" ({_frequency(target.frequency.count, target.frequency.share, target.frequency.accuracy)})"
            )
    size = plan.size
    lines += [""]
    asked = "no size asked" if size.requested is None else f"{size.requested:,} rows asked"
    lines.append(
        f"Size: {asked}; {size.mandatory_bound:,} rows are enough for the mandatory "
        f"targets one by one; beyond {size.useful_maximum:,} rows only the reserve grows."
    )
    if size.requested is not None and size.requested < size.mandatory_bound:
        lines.append(SIZE["below_mandatory"].capitalize() + ".")
    reserve = plan.reserve
    if reserve.rows_granted is not None:
        lines.append(
            f"Reserve of ordinary rows: {reserve.share:.0%}, {reserve.rows_granted:,} rows"
            + (" (reduced to keep the mandatory targets)" if reserve.reduced_by_mandatory else "")
            + "."
        )
    else:
        lines.append(f"Reserve of ordinary rows: {reserve.share:.0%} of the size asked.")
    candidates = plan.candidates
    held = (
        ""
        if candidates.bytes_expected is None
        else f", about {size_text(candidates.bytes_expected)} of source text"
    )
    lines.append(
        f"Candidate rows kept in memory: up to {candidates.rows:,}{held}"
        + ("" if candidates.fits else f" (over the budget of {size_text(candidates.budget_bytes)}: "
           f"{candidates.per_target_effective} per target)")
        + "."
    )
    lines += ["", f"Readings of the source: {plan.passes.total}"]
    for step in plan.passes.steps:
        mark = "needed" if step.needed else "not needed"
        lines.append(f"  {step.name} ({mark}): {pass_text(step.reason)}")
    enrichment = plan.enrichment
    if enrichment.awaiting:
        lines.append(
            "A second pass would add targets for: "
            + ", ".join(
                f"{FAMILY_NAMES[a.family]} ({a.analyses} analyses)" for a in enrichment.awaiting
            )
            + ". The sample then reads the source once more."
        )
    return "\n".join(lines)
