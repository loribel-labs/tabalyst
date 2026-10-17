# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Previews of the findings of a cell: what a finding is, what it counts, its examples.

The examples go through the exposure of their column when the Report is built
(``expose_examples``) and are stored with the finding; the preview is written from
the finding alone when a page is rendered (contract summary-table.md 18, 20). An
absent piece of information is left out, never invented (RF-17).
"""

from __future__ import annotations

from typing import Literal

from tabalyst.report_details import exposed_evidence
from tabalyst.report_finding_details import variant_details
from tabalyst.report_findings import (
    Assessment,
    Finding,
    FindingList,
    detector_of,
)
from tabalyst.report_labels import (
    ASSESSMENT_LABELS,
    ASSESSMENT_REASONS,
    FINDING_LIMITS,
    FINDING_NATURES,
    PREVIEW_ACCURACY,
    PREVIEW_DOWNGRADED,
    PREVIEW_EXAMPLES_NOTES,
    TABLE_AT_LEAST,
    UNIT_NOUNS,
    finding_label,
    finding_name,
    plural,
    population_phrase,
)
from tabalyst.report_views import ColumnView
from tabalyst.result_model import ResultModel
from tabalyst.scanner.classify.catalog import FINDING_CODES
from tabalyst.scanner.exposure import ExposureMode
from tabalyst.scanner.models import DetectorComplete
from tabalyst.summary_models import Example, ExamplesState

# Examples written in a preview (RF-17: two or three, a recommendation of the interface).
EXAMPLES_SHOWN = 2

# The detector and the state whose evidence illustrates a finding. ``semantic.invalid``
# reads the detector that is in ``basis``.
_EVIDENCE: dict[str, tuple[str | None, Literal["invalid", "ambiguous"]]] = {
    "temporal.invalid_calendar": ("date", "invalid"),
    "temporal.ambiguous_date": ("date", "ambiguous"),
    "number.ambiguous": ("number", "ambiguous"),
    "semantic.invalid": (None, "invalid"),
}


class CheckLine(ResultModel):
    """How far the check of one finding went on a column: what it looked for, its state
    and, in words, how many values it covered or why it did not run."""

    code: str
    name: str
    state: str
    state_label: str
    detail: str | None


class FindingPreview(ResultModel):
    """The preview of one finding. Every field but the title may be absent."""

    code: str
    cls: Literal["error", "issue"]
    title: str
    nature: str | None
    unit: str
    count_text: str | None
    population: str | None
    share: str | None
    accuracy: str
    accuracy_note: str
    examples: list[str]
    examples_state: ExamplesState
    examples_note: str | None
    limits: list[str]


def percent_text(percent: float) -> str:
    """A percentage with at most two decimals; a positive one below 0.01 is never
    written 0.

    >>> percent_text(0.004)
    '<0.01%'
    >>> percent_text(12.5)
    '12.5%'
    """
    if percent <= 0:
        return "0%"
    if percent < 0.01:
        return "<0.01%"
    return f"{percent:.2f}".rstrip("0").rstrip(".") + "%"


def _evidence_values(column: ColumnView, finding: Finding) -> list[str] | None:
    """The first distinct values the detector behind the finding set aside, as the
    document holds them; ``None`` when the Scan keeps none for this finding."""
    if finding.code not in _EVIDENCE:
        return None
    detector_id, state = _EVIDENCE[finding.code]
    if detector_id is None and finding.basis:
        detector_id = finding.basis[0]
    detector = None if detector_id is None else detector_of(column.field, detector_id)
    if not isinstance(detector, DetectorComplete):
        return None
    return list(getattr(detector.evidence, state))


def preview_examples(
    column: ColumnView, finding: Finding
) -> tuple[list[str], ExamplesState]:
    """At most ``EXAMPLES_SHOWN`` values that illustrate the finding, through the
    exposure of the column, and how they were exposed.

    ``hidden`` and ``masked`` say that the values are withheld or masked; ``none``
    that the Scan keeps no value for this finding.
    """
    values: list[str] | None
    if finding.code == "categorical.case_variants":
        details = variant_details(column)
        if details is None:
            return [], "none"
        if details.state == "hidden":
            return [], "hidden"
        spellings = details.groups[0].spellings if details.groups else []
        listed = [item.value for item in spellings[:EXAMPLES_SHOWN]]
        if not listed:
            return [], "none"
        return listed, "masked" if details.state == "masked" else "shown"
    mode: ExposureMode = column.exposure or "show"
    values = _evidence_values(column, finding)
    if values is None:
        return [], "none"
    # A hidden column's Scan keeps no evidence at all: the absence is the exposure's.
    if mode == "hide":
        return [], "hidden"
    shown = exposed_evidence(column, values)[:EXAMPLES_SHOWN]
    if not shown:
        return [], "none"
    return shown, "masked" if mode == "mask" else "shown"


def _assessment_of(finding: Finding, assessments: list[Assessment]) -> Assessment | None:
    return next((item for item in assessments if item.code == finding.code), None)


def expose_examples(column: ColumnView, finding: Finding) -> Finding:
    """The finding with the examples its preview shows, through the exposure of its
    column, and how they were exposed. Done once, when the Report is built."""
    values, state = preview_examples(column, finding)
    return finding.model_copy(
        update={
            "examples": [Example(value=value) for value in values],
            "examples_state": state,
        }
    )


def finding_preview(
    column: ColumnView, finding: Finding, assessments: list[Assessment]
) -> FindingPreview:
    """The preview of a finding of a column. ``assessments`` are the checks of the
    list the finding is in, to say how much of the eligible values were covered."""
    return preview_of(expose_examples(column, finding), assessments)


def preview_of(finding: Finding, assessments: list[Assessment]) -> FindingPreview:
    """The preview of a finding whose examples were exposed when the Report was
    built; nothing is read but the finding and its checks."""
    unit = finding.unit
    accuracy_word, accuracy_note = PREVIEW_ACCURACY[finding.accuracy]
    if finding.count is None:
        count_text = None
        title = finding_name(finding.code, unit)
    else:
        lower = finding.accuracy == "lower_bound"
        count_text = f"{TABLE_AT_LEAST} {finding.count:,}" if lower else f"{finding.count:,}"
        title = finding_label(finding.code, finding.count, unit)
        if lower:
            title = f"{TABLE_AT_LEAST} {title}"
    population = finding.population
    size = population.size
    population_text = None if size is None else population_phrase(population.kind, size)
    share_text = None
    if finding.share is not None and finding.share.percent is not None:
        denominator = population_phrase(population.kind, finding.share.denominator)
        share_text = (
            f"{percent_text(finding.share.percent)} "
            f"({finding.share.numerator:,} of {denominator})"
        )
    examples = [item.value for item in finding.examples]
    state: ExamplesState = finding.examples_state or "none"
    limits: list[str] = []
    if finding.code in FINDING_LIMITS:
        limits.append(FINDING_LIMITS[finding.code])
    entry = FINDING_CODES[finding.code]
    if entry.cls == "error" and finding.cls == "issue":
        limits.append(PREVIEW_DOWNGRADED)
    check = _assessment_of(finding, assessments)
    if (
        check is not None
        and check.eligible is not None
        and check.tested is not None
        and check.tested < check.eligible
    ):
        limits.append(
            f"The check covered {check.tested:,} of {check.eligible:,} eligible values."
        )
    cls: Literal["error", "issue"] = "error" if finding.cls == "error" else "issue"
    return FindingPreview(
        code=finding.code,
        cls=cls,
        title=title,
        nature=FINDING_NATURES.get(finding.code),
        unit=UNIT_NOUNS[unit][1],
        count_text=count_text,
        population=population_text,
        share=share_text,
        accuracy=accuracy_word,
        accuracy_note=accuracy_note,
        examples=examples,
        examples_state=state,
        examples_note=PREVIEW_EXAMPLES_NOTES.get(state),
        limits=limits,
    )


def _check_detail(check: Assessment) -> str | None:
    """What the check covered, or why it did not run, in words."""
    parts: list[str] = []
    if check.eligible is not None and check.tested is not None:
        if check.tested < check.eligible:
            parts.append(
                f"{plural(check.tested, 'value', 'values')} tested of "
                f"{plural(check.eligible, 'eligible value', 'eligible values')}"
            )
        else:
            parts.append(
                f"every one of the {plural(check.eligible, 'eligible value', 'eligible values')} "
                "was tested"
            )
    if check.reason:
        parts.append(ASSESSMENT_REASONS.get(check.reason, check.reason.replace("_", " ")))
    return "; ".join(parts) if parts else None


def check_lines(listing: FindingList, *, incomplete_only: bool = False) -> list[CheckLine]:
    """The checks of a list, the ones that apply to the column, in catalogue order.

    ``incomplete_only`` keeps those that did not complete (partial, not assessed,
    failed). A check with a finding is still a check: the list says what was looked at.
    """
    lines = []
    for check in listing.assessments:
        if check.state == "not_applicable":
            continue
        if incomplete_only and check.state not in ("partial", "not_assessed", "failed"):
            continue
        lines.append(
            CheckLine(
                code=check.code,
                name=finding_name(check.code, FINDING_CODES[check.code].unit),
                state=check.state,
                state_label=ASSESSMENT_LABELS.get(check.state, "Detected"),
                detail=_check_detail(check),
            )
        )
    return lines
