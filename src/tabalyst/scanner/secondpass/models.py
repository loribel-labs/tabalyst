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
    NumericStats,
    ScanModel,
    ValueCount,
    _omit_none,
)
from tabalyst.scanner.planner.models import AnalysisPlan, PlanBase

# ``Any`` in the serializers below: a serialized model is a plain dict whose
# values are JSON data, as in ``scanner/models.py``.
FORMAT = "tabalyst.scan.deep"
FORMAT_VERSION = "0.2.0"
FORMAT_REVISION = 2

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
    of the row sample), ``distinct`` (quantiles of the bottom-k sample) or
    ``grid`` (the multiples of a power of two of the values with a unit beyond
    ``max_values``, design 20.19).
    ``edges`` are written as numbers; the classification used the exact bounds,
    so an edge that is not representable may be rounded here.
    """

    kind: Literal["bins"] = "bins"
    strategy: Literal["linear", "sample_quantile"]
    requested_strategy: Literal["linear", "sample_quantile"]
    bounds_source: Literal["range", "rows", "distinct", "grid"]
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


class PatternTally(ScanModel):
    """Occurrences read by one candidate pattern of the Scan, exclusively: each
    value counts for the most specific candidate that reads it (PAT-08)."""

    id: str
    render: str
    occurrences: int


class PatternExclusions(ScanModel):
    """Values the inference leaves out and the validation therefore does not
    test: strings longer than ``scan.pattern_inference.max_value_length``, strings
    of more than 32 tokens, and values that are not strings (JSON numbers and
    booleans)."""

    non_string: int
    too_long: int
    too_complex: int


class PatternOverlapCount(ScanModel):
    """Occurrences that every pattern of ``patterns`` reads (they are counted
    for one of them only, in ``candidates``)."""

    patterns: list[str]
    occurrences: int


class PatternCounts(ScanModel):
    """The inferred patterns of a field counted over every occurrence (PAT-07 to
    PAT-09), in the original domain. ``values`` is the content values of the
    field (empty cells and null markers are the Scan's ``missing``); they add up:
    ``matched + other + excluded = values``, with ``matched`` the sum of the
    candidates. A value that no candidate reads is an observation of structure,
    never an error (PAT-10). ``computed_from`` says whether the source was read
    (``source``) or the exact counts of a Scan that holds every distinct value
    were enough (``samples``); the result is the same."""

    kind: Literal["pattern_counts"] = "pattern_counts"
    accuracy: Literal["exact"] = "exact"
    computed_from: Literal["source", "samples"]
    grammar_version: int
    values: int
    matched: int
    candidates: list[PatternTally]
    other: int
    excluded: PatternExclusions
    overlaps: list[PatternOverlapCount]


class PeriodCount(ScanModel):
    """Values placed in one period: ``period`` is ``YYYY-MM-DD``, ``YYYY-MM`` or
    ``YYYY`` according to the granularity."""

    period: str
    count: int


class PeriodCounts(ScanModel):
    """Exact count of the dates of a field per calendar day, month or year
    (TIME-01, TIME-02). A value is placed by the calendar date it is written
    with: the offset of an aware datetime is not converted, so a change of
    daylight saving time moves nothing. ``count`` values are placed, as many as
    the Scan counted of this ``temporal_kind``; ``ambiguous`` are the ones whose
    day and month order the Scan could not resolve, counted and never placed
    (TIME-03); ``unplaced`` is every other content value (not a date, invalid,
    or of another kind). ``periods`` lists the non-empty periods in order."""

    kind: Literal["periods"] = "periods"
    accuracy: Literal["exact"] = "exact"
    granularity: Literal["day", "month", "year"]
    temporal_kind: Literal["date", "datetime_naive", "datetime_aware"]
    zone: Literal["as_written"] = "as_written"
    values: int
    count: int
    ambiguous: int
    unplaced: int
    first: str
    last: str
    periods: list[PeriodCount]


class MeasureLevel(ScanModel):
    """The numbers of one population of values with a unit or a marker: the
    whole field, one marker, or the markers beyond ``max_groups``.

    ``numeric`` has the members of the ``numeric`` block of the Scan, computed
    the same way, with ``coverage`` the share of the content values of the
    field. Its median is exact when the numbers were counted in a table, and
    ``limited`` (``max_values``) when they went on in bins, whose ``histogram``
    then holds the estimate. ``distinct`` (numbers that differ) and ``modes``
    (ten at most) exist only with the table."""

    count: int
    distinct: int | None = None
    numeric: NumericStats
    modes: list[Number] | None = None
    modes_truncated: bool | None = None
    histogram: Annotated[DenseHistogram | BinnedHistogram, Field(discriminator="kind")]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("distinct", "modes", "modes_truncated"))


class MeasureGroup(MeasureLevel):
    """The numbers written with one marker or unit."""

    marker: str


class MeasureOther(MeasureLevel):
    """The numbers of the ``markers`` beyond the groups, together. Mixing units
    makes their numbers a count more than a quantity."""

    markers: int


class MarkerCount(ScanModel):
    """One marker or unit: ``count`` values are written with it, ``parsed`` of
    them have a number (the others are ambiguous), ``share`` is ``count`` over
    every value written with a marker."""

    value: str
    count: int
    parsed: int
    share: float


class RareMarkers(ScanModel):
    """The markers each written in less than ``share_below`` of the values
    with a marker, and the values written with them."""

    share_below: float
    markers: int
    count: int


class MarkerLayout(ScanModel):
    """How the values with a marker are written: the marker ``before`` or
    ``after`` the number, with a space between them (``spaced``) or not."""

    before: int
    after: int
    spaced: int
    unspaced: int


class MarkerEnumeration(ScanModel):
    """The markers or units as an enumeration of the values written with one
    (parsed or ambiguous): exact counts of every marker, ``listed`` by
    decreasing count then text (``truncated`` beyond 1,000), the ``modes`` and
    the share of the first one."""

    kind: Literal["currency", "percent", "unit"]
    count: int
    distinct: int
    listed: list[MarkerCount]
    truncated: bool
    modes: list[str]
    dominant_share: float
    rare: RareMarkers
    layout: MarkerLayout


class PercentRange(ScanModel):
    """The parsed percentages below 0, from 0 to 100, and above 100: a share
    above 100 is a fact of the data, never an error."""

    below: int
    within: int
    above: int


class MeasureResult(ScanModel):
    """The numbers of the values with a currency marker, a percent sign or a
    unit, extracted as the ``detector`` of the Scan reads them (design 20.19).

    ``values`` are the content values of the field: ``parsed`` have a number,
    ``ambiguous`` a number part the configuration cannot read one way (counted
    and never placed), ``invalid`` the shape of a value that does not hold, and
    ``unparsed`` the rest; they add up. ``scan_not_tested`` are the values the
    Scan's detector did not test (adaptive detection) and this pass read.

    ``overall`` gives the metrics of a numeric field for every parsed value,
    ``groups`` the same for each marker, the most frequent first, and ``other``
    for the markers beyond ``max_groups``. ``homogeneous`` is false when the
    numbers mix markers: no conversion is made, so their overall metrics add
    quantities that differ. ``storage`` is ``table`` when every number was
    counted exactly (``accuracy`` ``exact``), ``grid`` when the distinct numbers
    passed ``max_values`` and every group went on in bins: counts, sums and
    extremes stay exact, the quantiles are estimates with certain bounds
    (``exact_counts``)."""

    kind: Literal["measures"] = "measures"
    accuracy: Literal["exact", "exact_counts"]
    storage: Literal["table", "grid"]
    computed_from: Literal["source", "samples"]
    detector: Literal["currency", "percentage", "quantity"]
    values: int
    parsed: int
    ambiguous: int
    invalid: int
    unparsed: int
    scan_not_tested: int
    homogeneous: bool
    overall: MeasureLevel
    groups: list[MeasureGroup]
    other: MeasureOther | None = None
    markers: MarkerEnumeration
    percent_range: PercentRange | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("other", "percent_range"))


class ResidualValue(ScanModel):
    """A value a pattern or a detector leaves out, with the occurrences counted
    since its first appearance (so exact) and, when the source was read, the
    record of the first one."""

    value: str
    count: int
    first_record: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("first_record",))


class ReasonCount(ScanModel):
    """Occurrences of ``invalid`` values for one reason of the detector."""

    reason: str
    count: int


class ResidualTable(ScanModel):
    """What one source leaves out in one state (design 20.20): the values no
    candidate pattern reads (``other``), or the values of a detector that are
    ``invalid`` or ``not_matched``.

    ``occurrences`` is exact. ``listed`` holds the most frequent tracked values;
    ``distinct`` counts the tracked ones and is the distinct count when
    ``complete``. Values beyond ``max_tracked`` are only counted in
    ``untracked`` (occurrences), and a value longer than ``max_value_length`` in
    ``too_long``; both make ``complete`` false. ``truncated`` says that more
    tracked values exist than are listed. ``reasons`` split the occurrences of
    an ``invalid`` state."""

    source: Literal["pattern", "detector"]
    detector: str | None = None
    state: Literal["other", "invalid", "not_matched"]
    occurrences: int
    distinct: int
    complete: bool
    untracked: int
    too_long: int
    truncated: bool
    listed: list[ResidualValue]
    reasons: list[ReasonCount] | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("detector", "reasons"))


class PatternProfile(ScanModel):
    """A candidate pattern of the Scan, seen over every occurrence: how often it
    reads a value, one value it reads (the first one met) with its first record
    when the source was read, and the distinct values it reads (``exact``, or
    ``at_least`` when the sets could not be held)."""

    id: str
    render: str
    occurrences: int
    distinct: int
    distinct_accuracy: Literal["exact", "at_least"]
    example: str | None = None
    first_record: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("example", "first_record"))


class ResidualDetector(ScanModel):
    """What a replayed detector made of the strings of the field, beside what the
    Scan counted: ``scan_not_tested`` values were not tested by the Scan
    (adaptive detection) and were read here."""

    detector: str
    eligible: int
    matched: int
    ambiguous: int
    invalid: int
    not_matched: int
    scan_not_tested: int


class ResidualResult(ScanModel):
    """The values that patterns and detectors leave out, and the patterns over
    every occurrence (design 20.20). ``records`` says that the first record of
    each value is given, which needs the source. ``accuracy`` is ``exact`` when
    every table is ``complete`` and every pattern distinct count ``exact``, and
    ``exact_counts`` when occurrences are exact but a list is bounded."""

    kind: Literal["residual_values"] = "residual_values"
    accuracy: Literal["exact", "exact_counts"]
    computed_from: Literal["source", "samples"]
    records: bool
    values: int
    tables: list[ResidualTable]
    patterns: list[PatternProfile] | None = None
    pattern_excluded: PatternExclusions | None = None
    detectors: list[ResidualDetector]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("patterns", "pattern_excluded"))


class DuplicateValue(ScanModel):
    """A value, or a combination of values, found more than once: all its
    ``count`` occurrences (exact: it was tracked from its second sighting, with
    the first one counted) and, when the source was read, the record of the
    first. A combination is written as its values in the order of ``columns``."""

    value: str | list[str]
    count: int
    first_record: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("first_record",))


class RepeatedValues(ScanModel):
    """The values found more than once: how many (``distinct``) and their
    ``occurrences`` in all, exactly. Up to ``max_tracked`` of them are tracked
    with their count and listed, the most repeated first (``truncated`` when
    more are tracked than listed); the occurrences of the others are only
    counted in ``untracked``, which makes ``complete`` false."""

    distinct: int
    occurrences: int
    tracked: int
    untracked: int
    complete: bool
    truncated: bool
    listed: list[DuplicateValue]


class DuplicateResult(ScanModel):
    """The repeated values of a field, or of a combination of columns (design
    20.21). ``values`` are the values read (for a combination, the rows where
    every column has a value, and ``incomplete`` those where one lacks);
    ``distinct`` is exact, ``redundant`` is ``values - distinct`` and ``unique``
    says that nothing repeats. ``records`` says that the first record of each
    value is given, which needs the source. A value is identified by a 128-bit
    digest when the source is read: two values collide with a probability under
    one in 10^20 for a billion values."""

    kind: Literal["duplicates"] = "duplicates"
    accuracy: Literal["exact", "exact_counts"]
    computed_from: Literal["source", "samples"]
    records: bool
    columns: list[str] | None = None
    values: int
    incomplete: int | None = None
    distinct: int
    redundant: int
    unique: bool
    repeated: RepeatedValues

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("columns", "incomplete"))


class DuplicatesLimited(ScanModel):
    """What a stopped search for repeated values proves (D08): in the
    ``values_read`` values met before the memory budget stopped it, at least
    ``distinct`` distinct values and ``repeated`` repeated ones. Never a
    count."""

    kind: Literal["duplicates_limited"] = "duplicates_limited"
    accuracy: Literal["lower_bound"] = "lower_bound"
    values_read: int
    distinct: int
    repeated: int


class PearsonExclusions(ScanModel):
    """The rows a pair leaves out, because a value is missing: ``first_missing``
    has a number in the second column only, ``second_missing`` in the first only,
    ``both_missing`` in neither. A value is missing when the row has none, or
    it is not a number, or the number does not fit a float64."""

    first_missing: int
    second_missing: int
    both_missing: int


class PearsonResult(ScanModel):
    """Pearson correlation of two numeric columns over every row where both
    have a number (REL-07 to REL-09). ``rows`` are the rows examined, ``pairs``
    those that count (``pairwise_complete``) and ``excluded`` the others, so that
    ``rows`` is ``pairs`` plus the three exclusions. The means and spreads are
    those of the common rows, not the Scan's. Without ``min_pairs`` common rows,
    or when a column does not vary over them, there is no ``coefficient`` and
    the ``reason`` says why: never 0. The counts are exact; the coefficient is
    computed in float64 (``precision``), from stable co-moments. It measures a
    linear association, not a cause (REL-10). ``source`` says whether the rows
    were read from the source or are the complete sample of the Scan."""

    kind: Literal["pearson"] = "pearson"
    accuracy: Literal["exact_counts"] = "exact_counts"
    precision: Literal["float64"] = "float64"
    rule: Literal["pairwise_complete"] = "pairwise_complete"
    source: Literal["source", "samples"]
    min_pairs: int
    rows: int
    pairs: int
    excluded: PearsonExclusions
    defined: bool
    coefficient: float | None = None
    reason: str | None = None
    mean_first: float | None = None
    mean_second: float | None = None
    std_first: float | None = None
    std_second: float | None = None
    covariance: float | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            (
                "coefficient",
                "reason",
                "mean_first",
                "mean_second",
                "std_first",
                "std_second",
                "covariance",
            ),
        )


class TableClass(ScanModel):
    """A row or a column of a table: a category value or a class of a feature.
    ``label`` is what a reader sees (the value, a pattern rendering, a length, a
    prefix), ``other`` the class of everything the named ones do not take, and
    ``type`` the native type of a category of a JSON file that is not a string."""

    id: str
    label: str
    kind: Literal["value", "other"] = "value"
    type: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("type",))


class TableAxis(ScanModel):
    """One axis of a table: the field it reads, the ``domain`` of the values it
    reads (design 21) and its classes in the order of the counts."""

    field: str
    display: str
    domain: Literal["analytical", "original"]
    classes: list[TableClass]


class TableFeature(ScanModel):
    """The feature of the second column that makes the classes (REL-01):
    ``prefix_length`` is the number of characters of a prefix."""

    kind: Literal["pattern", "length", "prefix"]
    version: int
    prefix_length: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("prefix_length",))


class TableExclusions(ScanModel):
    """The rows left out of the table. ``category_missing`` has no category,
    ``feature_missing`` no value in the second column, ``both_missing`` neither,
    and ``unclassified`` a value the feature does not classify (not a string,
    longer than the patterns read)."""

    category_missing: int
    feature_missing: int
    both_missing: int
    unclassified: int


class CategorySummary(ScanModel):
    """A category against the classes. ``rows`` are all its rows, ``classified``
    those in the table, and ``coverage`` their share: a category whose values are
    mostly missing says little. ``dominant`` is the index of the class that holds
    most of it (a tie goes to the first class listed) and ``purity`` its share of
    the classified rows; the other rows are its ``exceptions`` (REL-13)."""

    rows: int
    classified: int
    feature_missing: int
    unclassified: int
    coverage: float | None = None
    dominant: int | None = None
    dominant_count: int
    purity: float | None = None
    exceptions: int

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("coverage", "dominant", "purity"))


class PurityFigure(ScanModel):
    """``dominant`` rows out of ``total``, and their share."""

    dominant: int
    total: int
    value: float | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("value",))


class TablePurity(ScanModel):
    """The purity of the table in the direction category to class (``forward``)
    and class to category (``reverse``), which is another figure (REL-13), and
    the ``baseline``: the share of the most frequent class, which a rule that
    always answered it would reach."""

    forward: PurityFigure
    reverse: PurityFigure
    baseline: float | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("baseline",))


class TableAssociation(ScanModel):
    """Cramér's V of the table over the rows and columns that have a count (the
    ``effective`` ones; the others stay in the table), or the ``reason`` there is
    none: never 0 for lack of data (REL-14). ``corrected`` is the bias-corrected
    V. A score is ``stable`` unless the expected counts are low (``low_share`` of
    the cells under 5, or one under 1) on the axes that hold at least 5 rows; the
    ``sparse`` axes, with fewer, only count here. An unstable score is never to be
    read as strong."""

    defined: bool
    n: int
    effective_categories: int
    effective_classes: int
    chi_square: float | None = None
    degrees: int | None = None
    cramers_v: float | None = None
    corrected: float | None = None
    low_share: float | None = None
    stable: bool | None = None
    sparse: int = 0
    reason: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            ("chi_square", "degrees", "cramers_v", "corrected", "low_share", "stable", "reason"),
        )


class ExceptionExample(ScanModel):
    """A row of an exception: its record and the value of the second column,
    cut at 64 characters."""

    record: int
    value: str


class ExceptionCell(ScanModel):
    """A cell that is not the dominant class of its category, with the exact
    ``count`` of its rows and the first of them in source order."""

    category: int
    column: int
    count: int
    examples: list[ExceptionExample]


class TableExceptions(ScanModel):
    """The rows outside the dominant class of their category (REL-15): ``count``
    of them in ``cells`` cells, the ``listed`` largest with their examples."""

    count: int
    cells: int
    listed: list[ExceptionCell]


class CandidateRule(ScanModel):
    """A relation learned from the data: rows of ``category`` take the class
    ``column`` with ``confidence`` over ``support`` classified rows, ``exceptions``
    excepted. It is a candidate and never a rule of the data: a rule a user
    approves is another thing, with its own provenance (REL-15)."""

    status: Literal["candidate"] = "candidate"
    provenance: Literal["learned"] = "learned"
    category: int
    column: int
    support: int
    confidence: float
    exceptions: int


class CrosstabResult(ScanModel):
    """The table of the rows of each category by class of a feature of another
    column, over every row (REL-11 to REL-15). The counts are exact; ``rows`` is
    ``counted`` (the table) plus the ``excluded`` rows, and the margins add up to
    ``counted``. Purity and Cramér's V are computed from the counts in float64.
    It shows an association between two columns, not a cause. ``source`` says
    whether the rows were read from the source or are the complete sample of the
    Scan."""

    kind: Literal["crosstab"] = "crosstab"
    accuracy: Literal["exact_counts"] = "exact_counts"
    precision: Literal["float64"] = "float64"
    source: Literal["source", "samples"]
    feature: TableFeature
    categories: TableAxis
    classes: TableAxis
    rows: int
    counted: int
    excluded: TableExclusions
    counts: list[list[int]]
    row_totals: list[int]
    column_totals: list[int]
    by_category: list[CategorySummary]
    purity: TablePurity
    association: TableAssociation
    exceptions: TableExceptions
    rules: list[CandidateRule]


AnalysisOutput = Annotated[
    DenseHistogram
    | BinnedHistogram
    | LengthDistribution
    | DistinctCount
    | DistinctLimited
    | FrequencyTable
    | PatternCounts
    | PeriodCounts
    | MeasureResult
    | ResidualResult
    | DuplicateResult
    | DuplicatesLimited
    | PearsonResult
    | CrosstabResult,
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
    # The second field of an analysis of a pair.
    partner: str | None = None
    display: str
    method: str
    parameters: dict[str, int | str]
    domain: Literal["analytical", "original", "mixed"] = "analytical"
    key: str
    status: AnalysisStatus
    reason: str | None = None
    detail: str | None = None
    result: AnalysisOutput | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("partner", "reason", "detail", "result"))


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
