# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The facts of one field that the analyzers read (design 20.5).

``scan_facts`` reads a finished Scan once and gives every analyzer the same
immutable view, so no analyzer walks the document or sees a sampled value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tabalyst.scanner.models import (
    CardinalityComplete,
    CardinalityLimited,
    DatasetResult,
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsFailed,
    FieldPatternsNotApplicable,
    FieldResult,
    ItemsSegment,
    ScanResult,
)


@dataclass(frozen=True, slots=True)
class PatternFacts:
    """The inferred patterns of a field (design 18.12)."""

    status: str
    reason: str | None
    candidates: int
    basis: str | None
    other_distinct: int


@dataclass(frozen=True, slots=True)
class TemporalFacts:
    """The temporal values of a field: their kinds and, for a single date or
    datetime kind, the span in days and whether the Scan already counts years."""

    count: int
    kinds: tuple[str, ...]
    span_days: int | None
    years_counted: bool


@dataclass(frozen=True, slots=True)
class FieldFacts:
    """Everything the planner knows about a field. ``where`` is the location of
    the field in the Scan (``datasets/<id>/fields/<id>``)."""

    dataset: str
    field: str
    display: str
    name: str
    where: str
    values: int
    technical_type: str
    # None, "show", "mask" or "hide": a masked or hidden field is never read again.
    exposure: str | None
    cardinality: str
    distinct: int | None
    distinct_lower_bound: int | None
    distinct_estimate: float | None
    frequencies: str
    frequencies_distinct: int | None
    frequencies_truncated: bool
    numeric: str
    numeric_min: float | None
    numeric_max: float | None
    # Numbers the scan counted for the field, and whether its path repeats in a
    # record (items of an array), which no pair of columns may use.
    numeric_count: int
    repeated: bool
    lengths: str
    min_length: int | None
    mean_length: float | None
    max_length: int | None
    long_text_occurrences: int
    samples_listed: int
    # Every distinct original value is listed with its exact count.
    samples_all: bool
    temporal: TemporalFacts | None
    temporal_status: str
    patterns: PatternFacts | None

    @property
    def withheld(self) -> bool:
        """Whether exposure keeps the values of the field out of the document."""
        return self.exposure in ("mask", "hide")

    @property
    def long_texts_only(self) -> bool:
        """Whether every stored value is a long text, which has no distinct
        count or histogram of its own (LONG-05)."""
        return self.long_text_occurrences > 0 and self.samples_listed == 0


def _temporal(field: FieldResult) -> tuple[str, TemporalFacts | None]:
    envelope = field.temporal
    if envelope.status != "complete":
        return envelope.status, None
    stats = envelope.value
    kinds = tuple(kind.kind for kind in stats.kinds)
    span: int | None = None
    years = False
    if len(stats.kinds) == 1 and stats.kinds[0].kind in ("date", "datetime_naive", "datetime_aware"):
        kind = stats.kinds[0]
        try:
            span = (
                datetime.fromisoformat(kind.max).date()
                - datetime.fromisoformat(kind.min).date()
            ).days
        except ValueError:
            span = None
        years = kind.years is not None
    return "complete", TemporalFacts(stats.count, kinds, span, years)


def _patterns(
    index: dict[tuple[str, str], FieldPatterns],
    dataset: str,
    field: str,
) -> PatternFacts | None:
    entry = index.get((dataset, field))
    if entry is None:
        return None
    if isinstance(entry, FieldPatternsComplete):
        basis = entry.candidates[0].coverage.basis if entry.candidates else None
        return PatternFacts(
            "complete", None, len(entry.candidates), basis, entry.other.distinct
        )
    assert isinstance(entry, (FieldPatternsNotApplicable, FieldPatternsFailed))
    return PatternFacts(entry.status, entry.reason, 0, None, 0)


def _facts(
    dataset: DatasetResult,
    field: FieldResult,
    index: dict[tuple[str, str], FieldPatterns],
) -> FieldFacts:
    cardinality = field.values.cardinality
    distinct: int | None = None
    lower: int | None = None
    estimate: float | None = None
    if isinstance(cardinality, CardinalityComplete):
        distinct = cardinality.value
    elif isinstance(cardinality, CardinalityLimited):
        lower = cardinality.lower_bound
        if cardinality.estimate is not None:
            estimate = cardinality.estimate.value
    frequencies = field.values.frequencies
    numeric = field.numeric
    lengths = field.string_lengths
    samples = field.values.samples
    temporal_status, temporal = _temporal(field)
    return FieldFacts(
        dataset=dataset.id,
        field=field.id,
        display=field.display,
        name=field.name,
        where=f"datasets/{dataset.id}/fields/{field.id}",
        values=field.values.count,
        technical_type=field.technical_type.type,
        exposure=field.exposure,
        cardinality=cardinality.status,
        distinct=distinct,
        distinct_lower_bound=lower,
        distinct_estimate=estimate,
        frequencies=frequencies.status,
        frequencies_distinct=(
            frequencies.value.distinct if frequencies.status == "complete" else None
        ),
        frequencies_truncated=(
            frequencies.value.truncated if frequencies.status == "complete" else False
        ),
        numeric=numeric.status,
        numeric_min=numeric.value.min if numeric.status == "complete" else None,
        numeric_max=numeric.value.max if numeric.status == "complete" else None,
        numeric_count=numeric.value.count if numeric.status == "complete" else 0,
        repeated=any(isinstance(segment, ItemsSegment) for segment in field.path),
        lengths=lengths.status,
        min_length=lengths.value.min_length if lengths.status == "complete" else None,
        mean_length=float(lengths.value.mean_length) if lengths.status == "complete" else None,
        max_length=lengths.value.max_length if lengths.status == "complete" else None,
        long_text_occurrences=(
            0 if samples.long_texts is None else samples.long_texts.occurrences
        ),
        samples_listed=len(samples.listed),
        samples_all=(
            samples.selection == "all"
            and samples.kept == samples.of
            and samples.long_texts is None
        ),
        temporal=temporal,
        temporal_status=temporal_status,
        patterns=_patterns(index, dataset.id, field.id),
    )


def scan_facts(scan: ScanResult) -> list[FieldFacts]:
    """The facts of every field of the Scan, in document order."""
    index = (
        {}
        if scan.derived is None or scan.derived.patterns is None
        else {
            (entry.dataset, entry.field): entry for entry in scan.derived.patterns.fields
        }
    )
    return [
        _facts(dataset, field, index)
        for dataset in scan.datasets
        for field in dataset.fields
    ]
