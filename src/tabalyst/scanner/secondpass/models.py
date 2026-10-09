# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The second-pass document and the results it holds (design 20.4, 20.7).

``<stem>.deep.json`` stands beside the Scan and never replaces it. It carries
the identity of the Scan it stands on, the plan that was run, the settings it
used, what the run cost and, for each analysis, its own status and result. A
result names its accuracy: counts per bin and per value are exact, a quantile
read from bins is an estimate with certain bounds (HIST-05, HIST-06).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import Field, model_serializer

from tabalyst.config import DeepSettings
from tabalyst.scanner.models import (
    LengthCount,
    Number,
    ScanModel,
    ValueCount,
    _omit_none,
)
from tabalyst.scanner.planner.models import AnalysisPlan, PlanBase

# ``Any`` in the serializers below: a serialized model is a plain dict whose
# values are JSON data, as in ``scanner/models.py``.
FORMAT = "tabalyst.scan.deep"
FORMAT_VERSION = "0.2.0"
FORMAT_REVISION = 1

# Quantile levels of every histogram, as (numerator, denominator) of the rank
# fraction: 5%, 25%, 50% (the median), 75% and 95%.
QUANTILE_LEVELS: tuple[tuple[int, int], ...] = ((5, 100), (25, 100), (1, 2), (75, 100), (95, 100))
# Values tied for the most frequent that a dense histogram lists.
MAX_MODES = 10

AnalysisStatus = Literal["complete", "limited", "failed", "skipped"]


class Quantile(ScanModel):
    """A quantile by linear interpolation between the two ranks around it
    (``(n - 1) * level``): for the median, the value at the middle rank, or the
    mean of the two central values when the count is even. ``exact`` when the
    counts are per value; ``estimated`` when read from bins, with ``lower`` and
    ``upper`` that the value cannot leave."""

    level: float
    value: Number
    accuracy: Literal["exact", "estimated"]
    lower: Number | None = None
    upper: Number | None = None

    @model_serializer(mode="wrap")
    def _omit_bounds(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("lower", "upper"))


class ValueCountNumber(ScanModel):
    value: int
    count: int


class DenseHistogram(ScanModel):
    """Exact count of every integer of a small domain: the cardinality, the
    mode, the median and every quantile follow from it exactly (HIST-07).
    ``values`` lists the integers that occur, in ascending order."""

    kind: Literal["dense_counts"] = "dense_counts"
    count: int
    min: int
    max: int
    distinct: int
    values: list[ValueCountNumber]
    modes: list[int]
    modes_truncated: bool
    median: Quantile
    quantiles: list[Quantile]


class OutsideBins(ScanModel):
    """Values beyond the bounds of the Scan. A source that is the one the Scan
    read has none; a count here would make the result ``failed``."""

    below: int
    above: int


class BinnedHistogram(ScanModel):
    """Counts per bin, exact for the declared classification (HIST-05): bin
    ``i`` is ``[edges[i], edges[i+1])`` and the last one is closed on the right
    so that the maximum belongs to it. The distribution inside a bin is
    unknown, so the median and quantiles are estimates with their bounds.

    ``strategy`` is the one in force and ``requested_strategy`` the one asked
    for; they differ, with ``reason``, when the sample could not place the
    bounds. ``bounds_source`` says where the inner bounds come from: ``range``
    (equal widths between the exact minimum and maximum), ``rows`` (quantiles
    of the row sample) or ``distinct`` (quantiles of the bottom-k sample).
    ``edges`` are written as numbers; the classification used the exact bounds,
    so an edge that is not representable may be rounded here.
    """

    kind: Literal["bins"] = "bins"
    strategy: Literal["linear", "sample_quantile"]
    requested_strategy: Literal["linear", "sample_quantile"]
    bounds_source: Literal["range", "rows", "distinct"]
    reason: str | None = None
    count: int
    min: Number
    max: Number
    edges: list[Number]
    counts: list[int]
    outside: OutsideBins
    median: Quantile
    quantiles: list[Quantile]

    @model_serializer(mode="wrap")
    def _omit_reason(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("reason",))


class LengthDistribution(ScanModel):
    """Exact count of every length, in characters of the analytical text, of the
    content strings of the field: the domain of ``string_lengths`` in the Scan."""

    kind: Literal["lengths"] = "lengths"
    count: int
    min_length: int
    max_length: int
    mean_length: Number
    median_length: Number
    length_histogram: list[LengthCount]


class DistinctCount(ScanModel):
    """Exact number of distinct original values of a field (EXACT-07), in the
    domain of the Scan's cardinality (design 21): decoded, before any
    normalization. ``values`` is V, the content values the cardinality is taken
    over (empty, blank, marker and null cells are not values), ``redundant`` is
    ``values - distinct``: the occurrences beyond the first of each value, not
    the number of values that occur more than once. ``unique`` is ``distinct ==
    values`` for this domain."""

    kind: Literal["distinct"] = "distinct"
    accuracy: Literal["exact"] = "exact"
    values: int
    distinct: int
    redundant: int
    unique: bool


class DistinctLimited(ScanModel):
    """What a stopped exact count proves (D08): the distinct values met in the
    ``values_read`` values before the memory budget stopped the field. It is a
    lower bound, never the cardinality."""

    kind: Literal["distinct_limited"] = "distinct_limited"
    accuracy: Literal["lower_bound"] = "lower_bound"
    values_read: int
    lower_bound: int


class FrequencyTable(ScanModel):
    """Exact count of every distinct analytical value of a field, each with its
    native type, from the most to the least frequent (ties by text, then by
    type), as the Scan orders its listing. ``modes`` are the values tied for the
    most frequent, ten at most."""

    kind: Literal["frequencies"] = "frequencies"
    count: int
    distinct: int
    values: list[ValueCount]
    modes: list[ValueCount]
    modes_truncated: bool


AnalysisOutput = Annotated[
    DenseHistogram
    | BinnedHistogram
    | LengthDistribution
    | DistinctCount
    | DistinctLimited
    | FrequencyTable,
    Field(discriminator="kind"),
]


class AnalysisResult(ScanModel):
    """One analysis of one field. ``key`` identifies its inputs (design 20.4):
    the Scan, the analyzer and its version, the field, the method and its
    effective parameters, and the domain of the values. A result is reused
    when the key is the same, whatever the budgets. ``reason`` and ``detail``
    explain a status that is not ``complete``; a detail never holds a value
    of the data."""

    id: str
    analyzer: str
    analyzer_version: int
    dataset: str
    field: str
    display: str
    method: str
    parameters: dict[str, int | str]
    domain: Literal["analytical", "original"] = "analytical"
    key: str
    status: AnalysisStatus
    reason: str | None = None
    detail: str | None = None
    result: AnalysisOutput | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("reason", "detail", "result"))


class DeepTimings(ScanModel):
    """Where the seconds of a run went: reading and parsing the source, then the
    analyses; the rest is setup and assembly."""

    reading: float
    analysis: float
    other: float


class DeepRun(ScanModel):
    """What the latest run did. ``source_verified`` says that the digest of the
    reading was compared with the Scan's (PASS2-01); a run that read nothing,
    because every result was reused, has none. ``cells_read`` counts the cells of
    the fields the analyses read, not of the whole source."""

    started_at: datetime
    duration_seconds: float
    timings: DeepTimings
    workers: int
    peak_memory_bytes: int | None
    source_read: bool
    source_verified: bool
    records_read: int
    cells_read: int
    executed: int
    reused: int
    skipped: int


class DeepResult(ScanModel):
    """The second-pass document. It is ``complete`` when every analysis of the
    plan that can run has a complete result, ``partial`` otherwise."""

    format: Literal["tabalyst.scan.deep"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: int = FORMAT_REVISION
    status: Literal["complete", "partial"]
    base: PlanBase
    settings: DeepSettings
    settings_sha256: str
    plan: AnalysisPlan
    run: DeepRun
    analyses: list[AnalysisResult]
