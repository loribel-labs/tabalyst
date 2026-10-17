# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Details of a column: representative values and complementary measures.

Computed at render time from the column view (contract summary-table.md 7.2).
Every value of the source goes through the exposure of the column, here again
whatever the document holds; nothing is serialized.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from tabalyst.models import ResultModel
from tabalyst.report_labels import (
    DETAILS_MEASURES,
    DETAILS_NOTES,
    format_number,
    plural,
)
from tabalyst.report_views import ColumnView
from tabalyst.scanner.exposure import ExposureGate, ExposureMode

DetailsState = Literal["shown", "masked", "hidden"]
DetailsAccuracy = Literal["exact", "lower_bound"]
# Detector keys listed at most (domains, area codes): a short reading aid.
KEYS_LISTED = 5
STATES: dict[ExposureMode, DetailsState] = {"show": "shown", "mask": "masked", "hide": "hidden"}
SHAPED_TYPES = ("email", "phone", "postal_code", "url", "ip_address", "uuid")


class DetailExample(ResultModel):
    """A value of the source, already through the exposure, with its count."""

    value: str
    count: int
    share: float | None = None
    # The value was cut at the length the scan stores: not the whole value.
    truncated: bool = False


class DetailMeasure(ResultModel):
    """A complementary measure. ``label`` is the words, or the text listed (a
    format, a key) when the measure is a count of it."""

    name: str
    label: str
    value: int | float | str
    accuracy: DetailsAccuracy = "exact"


class Details(ResultModel):
    """What the Details cell of a column holds."""

    state: DetailsState
    examples: list[DetailExample]
    # Whether the examples are every distinct value of the column. A masked or
    # hidden list is never exhaustive: its forms are not the original values.
    exhaustive: bool
    # Distinct values the examples are taken from, when known and meaningful.
    total: int | None = None
    total_accuracy: DetailsAccuracy = "exact"
    note: str | None = None
    measures: list[DetailMeasure]


def details_link(
    column_links: Mapping[tuple[str, str], str] | None, dataset_id: str, column_id: str
) -> str | None:
    """The page of a column, or ``None`` when ``--details`` did not write it
    (CA-28: no link to a missing page)."""
    if not column_links:
        return None
    return column_links.get((dataset_id, column_id)) or None


def _gate(column: ColumnView) -> ExposureGate:
    mode: ExposureMode = column.exposure or "show"
    return ExposureGate(mode)


def _examples(column: ColumnView, gate: ExposureGate) -> list[DetailExample]:
    """The first values of the profile, as many as the cell of the old table
    showed, through the gate (masks merged, nothing when hidden). The gate is
    applied again on purpose: the document may hold raw values."""
    taken = column.value_profile.values[: len(column.examples)]
    present = column.field.values.count
    cut = {item.value for item in taken if item.truncated}
    kept = gate.counts((item.value, item.count) for item in taken)
    return [
        DetailExample(
            value=value,
            count=count,
            share=count / present if present else None,
            truncated=value in cut,
        )
        for value, count in kept.items()
    ]


def _measure(
    name: str,
    value: float | str,
    accuracy: DetailsAccuracy = "exact",
    label: str | None = None,
) -> DetailMeasure:
    return DetailMeasure(
        name=name, label=label or DETAILS_MEASURES[name], value=value, accuracy=accuracy
    )


def _text_measures(column: ColumnView) -> list[DetailMeasure]:
    profile = column.string_profile
    if profile is None:
        return []
    if profile.fixed_length is not None:
        return [_measure("fixed_length", profile.fixed_length)]
    return [
        _measure("minimum_length", profile.minimum_length),
        _measure("maximum_length", profile.maximum_length),
        _measure("mean_length", profile.mean_length),
    ]


def _temporal_measures(column: ColumnView) -> list[DetailMeasure]:
    profile = column.date_profile
    if profile is None:
        return []
    found = [
        _measure("format", item.count, label=item.format) for item in profile.formats
    ]
    if profile.resolved_ambiguous_order:
        found.append(_measure("resolved_order", profile.resolved_ambiguous_order))
    return found


def _keys(detector_details: Mapping[str, object]) -> list[DetailMeasure]:
    """The first keys the detector published (domains, area codes)."""
    block = detector_details.get("keys")
    if not isinstance(block, dict) or block.get("status") not in ("complete", "limited"):
        return []
    entries = block.get("keys")
    if not isinstance(entries, list):
        return []
    accuracy: DetailsAccuracy = (
        "exact" if block.get("status") == "complete" else "lower_bound"
    )
    return [
        _measure("key", int(entry["occurrences"]), accuracy, label=str(entry["key"]))
        for entry in entries[:KEYS_LISTED]
        if isinstance(entry, dict) and "key" in entry and "occurrences" in entry
    ]


def _shaped_measures(column: ColumnView, shown: bool) -> list[DetailMeasure]:
    kind = column.classification.type
    detector = next((item for item in column.detectors if item.id == kind), None)
    if detector is None:
        return []
    partial = detector.adaptive is not None or bool(
        detector.coverage and detector.coverage.not_tested
    )
    accuracy: DetailsAccuracy = "lower_bound" if partial else "exact"
    found = [_measure("matched_percent", detector.matched_percent, accuracy)]
    found.extend(
        _measure("format", item.count, accuracy, label=item.format)
        for item in detector.formats
    )
    # Keys are values of the source: listed only when the column is shown.
    if shown:
        found.extend(_keys(detector.details))
    return found


def _mixed_measures(column: ColumnView) -> list[DetailMeasure]:
    return [
        _measure("representation", count, label=name)
        for name, count in sorted(column.type_counts.items())
        if count
    ]


def _measures(column: ColumnView, shown: bool) -> list[DetailMeasure]:
    family = column.classification.family
    kind = column.classification.type
    if family == "numeric":
        stats = column.numeric
        return [] if stats is None else [_measure("mean", stats.mean)]
    if family == "temporal":
        return _temporal_measures(column)
    if family == "text":
        return _text_measures(column)
    if kind == "mixed":
        return _mixed_measures(column)
    if kind in SHAPED_TYPES:
        return _shaped_measures(column, shown)
    return []


def _distinct_total(column: ColumnView) -> tuple[int | None, DetailsAccuracy]:
    view = column.distinct
    if view.kind == "not_counted" or view.value is None:
        return None, "exact"
    return view.value, "exact" if view.kind == "exact" else "lower_bound"


def _listing_note(examples: int, total: int | None, accuracy: DetailsAccuracy) -> str:
    """Why the list is not the whole column, never worded as exhaustive."""
    if not examples:
        return DETAILS_NOTES["none"]
    if total is None:
        return DETAILS_NOTES["sample"]
    prefix = "at least " if accuracy == "lower_bound" else ""
    listed = plural(examples, "value", "values")
    return f"{listed} of {prefix}{format_number(total)} distinct values; {DETAILS_NOTES['sample']}"


def details_for(column: ColumnView) -> Details:
    """The Details of a column. Alert examples are not here: they belong to the
    preview of the alert (RF-18)."""
    gate = _gate(column)
    state = STATES[gate.mode]
    examples = _examples(column, gate)
    total: int | None = None
    accuracy: DetailsAccuracy = "exact"
    exhaustive = False
    if state == "shown":
        total, accuracy = _distinct_total(column)
        exhaustive = (
            column.value_profile.selection == "complete"
            and accuracy == "exact"
            and total is not None
            and len(examples) == total
        )
        note = None if exhaustive else _listing_note(len(examples), total, accuracy)
    else:
        note = DETAILS_NOTES[state]
    return Details(
        state=state,
        examples=examples,
        exhaustive=exhaustive,
        total=total,
        total_accuracy=accuracy,
        note=note,
        measures=_measures(column, state == "shown"),
    )
