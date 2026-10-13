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
from tabalyst.scanner.config import ScalarType
from tabalyst.scanner.models import (
    CharacterMap,
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
FORMAT_REVISION = 3

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
    ``max_values``, design 20.19). ``log`` places the inner bounds at equal
    ratios between the exact minimum and maximum of positive numbers (design
    20.24).
    ``edges`` are written as numbers; the classification used the exact bounds,
    so an edge that is not representable may be rounded here.
    """

    kind: Literal["bins"] = "bins"
    strategy: Literal["linear", "sample_quantile", "log"]
    requested_strategy: Literal["linear", "sample_quantile", "log"]
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


class ShapeMoments(ScanModel):
    """The asymmetry (``skewness``, the third standardized moment of the
    population) and the ``excess_kurtosis`` (the fourth, minus 3) of the numbers,
    from centered sums merged by batch in float64 (``precision``): a relative
    error of a few units in 1e-12, not an exact fraction. Absent, with a
    ``reason``, when they are undefined (``no_variance``, ``too_few_values``) or
    a number is beyond float64 (``not_representable``)."""

    precision: Literal["float64"] = "float64"
    skewness: float | None = None
    excess_kurtosis: float | None = None
    reason: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("skewness", "excess_kurtosis", "reason"))


class TukeyCount(ScanModel):
    """Numbers beyond a fence: those that are for every fence the estimated
    quartiles allow (``certain``) and those that are for at least one of them
    (``possible``). They are equal when the quartiles are exact."""

    certain: int
    possible: int


class TukeyFence(ScanModel):
    """The fences ``low`` and ``high`` at ``factor`` interquartile ranges beyond
    the first and the third quartile, and the numbers strictly below the first
    and strictly above the second. With estimated quartiles the fences written
    are those of the estimates."""

    factor: float
    low: Number
    high: Number
    below: TukeyCount
    above: TukeyCount


class Tukey(ScanModel):
    """The outliers of Tukey: the quartiles ``q1`` and ``q3``, their
    interquartile range and the numbers beyond the fences at 1.5 (mild) and 3
    (far) ranges. ``exact`` when the numbers were counted in a table, ``bounds``
    when they went on in bins and the counts are bracketed."""

    accuracy: Literal["exact", "bounds"]
    q1: Quantile
    q3: Quantile
    iqr: Number
    fences: list[TukeyFence]


class PlacesCount(ScanModel):
    """Numbers written with ``places`` digits after the decimal point."""

    places: int
    count: int


class DecimalScale(ScanModel):
    """How many decimals the numbers are written with, exactly: ``places`` lists
    each count of decimals that occurs, from 0 (an integer or a number written
    without a point), ``trailing_zero`` counts the numbers whose last written
    decimal is a 0 (``12.50``) and ``mixed`` says that decimal numbers are
    written with different counts of decimals (a precision that varies)."""

    places: list[PlacesCount]
    max_places: int
    trailing_zero: int
    mixed: bool


class ShapeResult(ScanModel):
    """The shape of the numbers of a column beyond its histogram (design 20.24):
    the asymmetry and the kurtosis, the outliers of Tukey, the decimals they are
    written with and two other views of their spread, ``log`` (bins of equal
    ratio, only for positive numbers: ``log_reason`` says why it is absent) and
    ``equal_count`` (bins whose bounds are quantiles of the Scan's samples, which
    fall back to equal widths, with a reason, when the samples cannot place
    them). Counts per bin are exact over the whole source.

    ``storage`` is ``table`` when every distinct number was counted (``accuracy``
    ``exact``: exact quartiles and counts of outliers), ``grid`` beyond
    ``max_values`` (``exact_counts``: the quartiles are estimates with certain
    bounds). ``distinct`` exists with the table only."""

    kind: Literal["numeric_shape"] = "numeric_shape"
    accuracy: Literal["exact", "exact_counts"]
    storage: Literal["table", "grid"]
    count: int
    distinct: int | None = None
    moments: ShapeMoments
    tukey: Tukey
    scale: DecimalScale
    log: BinnedHistogram | None = None
    log_reason: str | None = None
    equal_count: BinnedHistogram

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("distinct", "log", "log_reason"))


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


class PatternDistinct(ScanModel):
    """Distinct values of a pattern or of a node: ``exact`` when the Scan holds
    the whole distribution or the set of the distinct values fit its budget,
    ``at_least`` otherwise. A bound is never presented as exact (FR-014)."""

    count: int
    accuracy: Literal["exact", "at_least"]


class PatternNodeCount(ScanModel):
    """A pattern or a node of the discovery counted over every occurrence.

    ``occurrences`` include those of the nodes below; ``rest`` is what this node
    reads and none of its nodes does (all of ``occurrences`` for a leaf), so that
    ``rest`` plus the occurrences of ``nodes`` is ``occurrences``. ``render`` is
    that of the Scan."""

    id: str
    render: str
    occurrences: int
    distinct: PatternDistinct
    rest: int
    nodes: list[PatternNodeCount] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler) -> dict[str, Any]:
        data = handler(self)
        if not data.get("nodes"):
            data.pop("nodes", None)
        return data


class PatternCountCell(ScanModel):
    value: str
    occurrences: int


class PatternTableCount(ScanModel):
    """The values of a facet of a family counted over every occurrence, the
    cells the discovery listed and the values it never saw. At most ``capacity``
    cells are kept, the most frequent; the others are summed in ``others`` and
    ``saturated`` says that the table is limited (TR-003). For the table of
    ``lengths`` the cells are combinations of lengths."""

    facet: str
    capacity: int
    cells: list[PatternCountCell]
    others: int
    saturated: bool


class PatternNewVariants(ScanModel):
    """Occurrences of a known family that the discovery never saw: a set of
    lengths of its variable tokens (``length``), or a value of a segment that one
    of its facets reads (``segment``). Neither is an error or an unknown
    structure (FR-015)."""

    length: int
    segment: int


class PatternFamilyCount(ScanModel):
    """A family counted over every occurrence. ``occurrences`` are those of its
    ``patterns``, of the combinations of lengths that its table of ``lengths``
    holds and its new variants of length."""

    id: str
    occurrences: int
    distinct: PatternDistinct
    patterns: list[PatternNodeCount]
    tables: list[PatternTableCount]
    new_variants: PatternNewVariants


class PatternExclusions(ScanModel):
    """Values the inference leaves out and the validation therefore does not
    test: strings longer than ``scan.pattern_inference.max_value_length``, strings
    of more than 32 tokens, and values that are not strings (JSON numbers and
    booleans)."""

    non_string: int
    too_long: int
    too_complex: int


class PatternCounts(ScanModel):
    """The hierarchy of patterns of a field counted over every occurrence (design
    20.9, PAT-21 to PAT-27), in the original domain. ``values`` is the content
    values of the field (empty cells and null markers are the Scan's
    ``missing``); they add up: ``matched + unknown_structure + excluded =
    values``, with ``matched`` the sum of the families. A value that no family
    reads is an observation of structure, never an error (PAT-10). The counts
    are exact; ``computed_from`` says whether the source was read (``source``)
    or the exact counts of a Scan that holds every distinct value were enough
    (``samples``); the result is the same."""

    kind: Literal["pattern_counts"] = "pattern_counts"
    accuracy: Literal["exact"] = "exact"
    computed_from: Literal["source", "samples"]
    grammar_version: int
    algorithm_version: int
    values: int
    matched: int
    families: list[PatternFamilyCount]
    unknown_structure: int
    excluded: PatternExclusions

    def all_patterns(self) -> list[PatternNodeCount]:
        """The patterns counted, in the order of the document of the Scan (the families
        in order, each with its patterns), nodes included in their pattern."""
        return [pattern for family in self.families for pattern in family.patterns]

    def outside_patterns(self) -> int:
        """The occurrences that no pattern holds: those of no family, and those of a
        family that none of its patterns holds (its table of lengths and its new
        variants of length). With the occurrences of the patterns and the excluded
        values they add up to ``values``."""
        in_patterns = sum(pattern.occurrences for pattern in self.all_patterns())
        return self.values - sum(self.excluded.model_dump().values()) - in_patterns


class DateResolution(ScanModel):
    """The order the ambiguous dates of a field were read in: ``source`` is
    ``evidence`` when the unambiguous dates of the field read in only one order
    (``25/03/2020`` is day-month and none is month-day), whatever their
    separator and with or without year-first dates. ``evidence`` counts those
    unambiguous dates by order (``DMY``, ``MDY``). The ambiguous dates, which the
    Scan counts and does not place, that this reading made valid are the
    ``resolved`` count of the result."""

    order: Literal["DMY", "MDY"]
    source: Literal["evidence"] = "evidence"
    evidence: dict[str, int]


class NumberResolution(ScanModel):
    """The convention the ambiguous numbers of a field were read in: ``source``
    is ``evidence`` when the unambiguous numbers written with the same marker
    read in only one convention (``1.234,5`` is ``comma`` and none is ``dot``).
    ``evidence`` counts those unambiguous numbers by convention, as the Scan's
    detector counted them. The values this reading made numbers (ambiguous ones
    and, under ``comma``, ``d.ddd`` as thousands) are the ``resolved`` count of
    the result."""

    convention: Literal["dot", "comma"]
    source: Literal["evidence"] = "evidence"
    evidence: dict[str, int]


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
    or of another kind). ``periods`` lists the non-empty periods in order. With a
    ``resolution`` the ambiguous dates were read in its order and placed with the
    others: ``resolved`` is their number, ``ambiguous`` the ones left (0), and
    ``count`` is the Scan's plus ``resolved``."""

    kind: Literal["periods"] = "periods"
    accuracy: Literal["exact"] = "exact"
    granularity: Literal["day", "month", "year"]
    temporal_kind: Literal["date", "datetime_naive", "datetime_aware"]
    zone: Literal["as_written"] = "as_written"
    values: int
    count: int
    ambiguous: int
    resolved: int
    unplaced: int
    first: str
    last: str
    periods: list[PeriodCount]
    resolution: DateResolution | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("resolution",))


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
    (``exact_counts``).

    With a ``resolution`` the ambiguous numbers were read in its convention and
    counted with the others: ``resolved`` is the number of values it made
    numbers (the ambiguous ones, and under ``comma`` the ``d.ddd`` read as
    thousands, which the Scan counted as parsed), ``parsed`` includes them and
    ``ambiguous`` is the ones left (0)."""

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
    resolved: int = 0
    resolution: NumberResolution | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("other", "percent_range", "resolution"))


class ReasonCount(ScanModel):
    """Occurrences of ``invalid`` values for one reason of the detector."""

    reason: str
    count: int


class PartCount(ScanModel):
    """Values placed in one part of the calendar: ``value`` is the day of the
    week (0 for Monday to 6) or the hour (0 to 23), according to the list that
    holds it."""

    value: int
    count: int


class AmbiguousReading(ScanModel):
    """What the ambiguous dates would be if every one were read in the order
    ``order``: only the month and the day change between the readings, so the
    year-months and the days of the week are counted."""

    order: Literal["DMY", "MDY"]
    placed: int
    year_months: list[PeriodCount]
    weekdays: list[PartCount]
    after_as_of: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("after_as_of",))


class AmbiguitySimulation(ScanModel):
    """The ``ambiguous`` dates, which the Scan counts and never places, read
    under each order that makes them ambiguous. Nothing is applied: it measures
    what the choice of ``ambiguous_order`` would change."""

    ambiguous: int
    readings: list[AmbiguousReading]


class PartsResult(ScanModel):
    """The parts of the calendar dates of a field (design 20.25): the
    year-month, the day of the week and, for datetimes and times, the hour,
    always counted by the date or the hour as written (the offset of an aware
    datetime is not converted), exactly. The counts per year and per month of the
    year are sums of the year-months and are not repeated.

    ``values`` are the content values, of which ``count`` are dates of
    ``temporal_kind`` (as many as the Scan counted), ``ambiguous`` have a day and
    month order the Scan could not resolve (counted, never placed), ``invalid``
    have the shape of a date that does not hold, by reason in
    ``invalid_reasons``, and ``unplaced`` are the rest; they add up. ``resolved``
    is the number of ambiguous dates that ``resolution`` made valid: they are in
    ``count``, and ``ambiguous`` is what is left.
    ``year_months`` lists the months that occur, in order (``YYYY-MM``),
    ``weekdays`` (7) every day of the week and ``hours`` those that occur (a time
    has hours only). ``after_as_of`` counts the dates after ``as_of`` when it is
    set. ``simulation`` exists when there are ambiguous dates."""

    kind: Literal["datetime_parts"] = "datetime_parts"
    accuracy: Literal["exact"] = "exact"
    temporal_kind: Literal["date", "datetime_naive", "datetime_aware", "time"]
    zone: Literal["as_written"] = "as_written"
    values: int
    count: int
    ambiguous: int
    resolved: int
    invalid: int
    unplaced: int
    scan_not_tested: int
    invalid_reasons: list[ReasonCount]
    year_months: list[PeriodCount] | None = None
    weekdays: list[PartCount] | None = None
    hours: list[PartCount] | None = None
    as_of: str | None = None
    after_as_of: int | None = None
    simulation: AmbiguitySimulation | None = None
    resolution: DateResolution | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            ("year_months", "weekdays", "hours", "as_of", "after_as_of", "simulation", "resolution"),
        )


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


class RankEstimate(ScanModel):
    """The Spearman rank correlation of a pair, read from a grid of ``bins`` bins
    per column cut at quantiles of what the Scan kept (design 20.22): an
    estimate, with the ``lower`` and ``upper`` bounds that hold whatever order
    the values have inside their bins. ``bins_first`` and ``bins_second`` are
    the bins that hold a row; ``edges_first`` and ``edges_second`` say where the
    edges of each column come from (``rows``: the row sample, ``distinct``: the
    distinct values the Scan kept, ``range``: equal widths, the Scan kept too
    little). Without a coefficient the ``reason`` says why: never 0."""

    kind: Literal["spearman_binned"] = "spearman_binned"
    accuracy: Literal["estimated"] = "estimated"
    bins: int
    bins_first: int
    bins_second: int
    edges_first: Literal["rows", "distinct", "range"]
    edges_second: Literal["rows", "distinct", "range"]
    defined: bool
    coefficient: float | None = None
    lower: float | None = None
    upper: float | None = None
    reason: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("coefficient", "lower", "upper", "reason"))


class PearsonResult(ScanModel):
    """Pearson correlation of two numeric columns over every row where both
    have a number (REL-07 to REL-09). ``rows`` are the rows examined, ``pairs``
    those that count (``pairwise_complete``) and ``excluded`` the others, so that
    ``rows`` is ``pairs`` plus the three exclusions. The means and spreads are
    those of the common rows, not the Scan's. Without ``min_pairs`` common rows,
    or when a column does not vary over them, there is no ``coefficient`` and
    the ``reason`` says why: never 0. The counts are exact; the coefficient is
    computed in float64 (``precision``), from stable co-moments. It measures a
    linear association, not a cause (REL-10). ``slope`` and ``intercept`` are
    the line of the second column on the first through the same co-moments
    (defined with the coefficient), ``r_squared`` the share of the variance of
    the second column it explains, and ``rank`` the rank correlation, when asked
    for. ``source`` says whether the rows were read from the source or are the
    complete sample of the Scan."""

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
    slope: float | None = None
    intercept: float | None = None
    r_squared: float | None = None
    rank: RankEstimate | None = None

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
                "slope",
                "intercept",
                "r_squared",
                "rank",
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

    kind: Literal["pattern", "length", "prefix", "value"]
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
    of them in ``cells`` cells, the ``listed`` largest with their examples.
    ``complete`` says that every cell is listed; otherwise the list stops at the
    bound of the settings (``max_exception_cells``) and ``cells`` tells how many
    there are."""

    count: int
    cells: int
    complete: bool = True
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


class ProvidedRule(ScanModel):
    """A rule a user gave, checked against the table (design 20.22): the rows of
    the category named ``category_label`` take the class named ``class_label``.
    Unlike a candidate rule it is not learned and needs no support: ``support``
    is the classified rows of the category, ``confidence`` the share of them in
    the class, ``exceptions`` the others, and ``counter_examples`` the cells
    that break it with their first rows. ``status`` is ``holds`` when no row
    breaks it, ``violated`` otherwise, ``no_rows`` when the category has no
    classified row and ``unknown_category`` or ``unknown_class`` when a label is
    not on the axis of the table (``category`` and ``column`` are then absent)."""

    provenance: Literal["provided"] = "provided"
    status: Literal["holds", "violated", "no_rows", "unknown_category", "unknown_class"]
    category_label: str
    class_label: str
    category: int | None = None
    column: int | None = None
    support: int = 0
    confidence: float | None = None
    exceptions: int = 0
    counter_examples: list[ExceptionCell] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("category", "column", "confidence"))


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
    provided_rules: list[ProvidedRule] | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("provided_rules",))


class StatsExclusions(ScanModel):
    """The rows left out of the numbers by category. ``category_missing`` has a
    number and no category, ``value_missing`` a category and no number (the row
    has none, it is not a number, or the number does not fit a float64) and
    ``both_missing`` neither."""

    category_missing: int
    value_missing: int
    both_missing: int


class StatsBins(ScanModel):
    """The bins every category is counted in. Bin ``i`` is ``[edges[i],
    edges[i + 1])`` and the last one is closed on the right so that the maximum
    belongs to it; the edges are the same for every category, so the histograms
    compare. ``strategy`` is the one in force and ``requested_strategy`` the one
    asked for; they differ, with ``reason``, when the sample could not place the
    edges. ``bounds_source`` says where they come from (``range``, ``rows`` or
    ``distinct``, as for ``BinnedHistogram``). A number goes to a bin by
    comparison of float64 values."""

    strategy: Literal["linear", "sample_quantile"]
    requested_strategy: Literal["linear", "sample_quantile"]
    bounds_source: Literal["range", "rows", "distinct"]
    reason: str | None = None
    edges: list[Number]

    @model_serializer(mode="wrap")
    def _omit_reason(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("reason",))


class StatsSummary(ScanModel):
    """The numbers of a population of rows: ``count`` numbers, and when there is
    one their extremes, ``sum``, ``mean``, population standard deviation and the
    counts of positive, negative and zero numbers, which add up to ``count``.
    ``counts`` holds one counter per bin of ``StatsResult.bins`` (they add up to
    ``count``) and ``quantiles`` are read from them: estimates with ``lower`` and
    ``upper`` bounds the true value cannot leave, tightened by the extremes."""

    count: int
    min: Number | None = None
    max: Number | None = None
    sum: float | None = None
    mean: float | None = None
    std: float | None = None
    positive: int = 0
    negative: int = 0
    zero: int = 0
    counts: list[int]
    median: Quantile | None = None
    quantiles: list[Quantile] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        data = _omit_none(handler(self), ("min", "max", "sum", "mean", "std", "median"))
        if not data.get("quantiles"):
            data.pop("quantiles", None)
        return data


class StatsGroup(StatsSummary):
    """The numbers of one category, in the order of the axis. ``rows`` are all
    its rows: ``count`` of them have a number, ``value_missing`` do not."""

    rows: int
    value_missing: int


class StatsAssociation(ScanModel):
    """How much of the variance of the number the categories explain (design
    20.23): the correlation ratio ``eta_squared`` and the same corrected for the
    bias that grows with the number of ``groups`` (``epsilon_squared``, not below
    0), over the ``n`` numbers of the named categories (``other`` takes no part).
    ``score`` is the square root of the corrected ratio. Without them the
    ``reason`` says why: never 0."""

    defined: bool
    n: int
    groups: int
    eta_squared: float | None = None
    epsilon_squared: float | None = None
    score: float | None = None
    reason: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("eta_squared", "epsilon_squared", "score", "reason"))


class StatsResult(ScanModel):
    """The numbers of a column described for each value of a category, over every
    row. The counts are exact; the minimum, maximum, sum, mean and spread are
    computed in float64 from the numbers as float64 (``precision``), the sum from
    correctly rounded partial sums and the spread from stable moments. ``rows`` is
    ``counted`` (a category and a number) plus the ``excluded`` rows, and the
    groups add up to ``counted``. It shows an association between two columns,
    not a cause. ``source`` says whether the rows were read from the source or are
    the complete sample of the Scan."""

    kind: Literal["category_stats"] = "category_stats"
    accuracy: Literal["exact_counts"] = "exact_counts"
    precision: Literal["float64"] = "float64"
    source: Literal["source", "samples"]
    categories: TableAxis
    rows: int
    counted: int
    excluded: StatsExclusions
    bins: StatsBins
    overall: StatsSummary
    groups: list[StatsGroup]
    association: StatsAssociation


class DriftSlice(ScanModel):
    """One tenth of the records, in file order. ``records`` of them start at
    ``first_record``; ``values`` have a value for the field and ``missing`` do not
    (they add up). ``new_values`` counts the distinct values that appear for the
    first time in the slice, when the values are followed."""

    first_record: int
    records: int
    values: int
    missing: int
    new_values: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("new_values",))


class DriftCategory(ScanModel):
    """A value followed by slice: its exact ``count`` in each of the ten slices
    (``counts``) and the first slice, numbered from 0, where it appears."""

    value: str
    type: ScalarType
    count: int
    counts: list[int]
    first_slice: int


class DriftValues(ScanModel):
    """The ``distinct`` values of the field followed by slice: the most frequent
    ones are ``listed`` with their counts per slice and the others are summed up
    in ``other``. ``association`` is Cramér's V of the slice against the value
    over every value, not only the listed ones."""

    distinct: int
    listed: list[DriftCategory]
    other: list[int]
    association: TableAssociation


class PositionDriftResult(ScanModel):
    """A field followed by position in the file (design 20.30): the records cut in
    ten slices of the same size, in file order, and for each the records, the
    values and the missing ones, exactly. ``missing_association`` is Cramér's V of
    the slice against the presence of a value: it is what tells a column that is
    missing more in one part of the file from a constant share. ``followed`` holds
    the values themselves when the field has few enough distinct ones; without it
    only the presence is followed. It shows that a column changes along the file,
    not why."""

    kind: Literal["position_drift"] = "position_drift"
    accuracy: Literal["exact"] = "exact"
    records: int
    values: int
    missing: int
    slices: list[DriftSlice]
    missing_association: TableAssociation
    followed: DriftValues | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("followed",))


class MissingPartner(ScanModel):
    """A column that lacks a value in some of the records where another one does:
    the records where it lacks one (``missing``, as the Scan counts them for a
    column that does not repeat) and the records where both do (``both``)."""

    field: str
    display: str
    missing: int
    both: int


class MissingMatrixResult(ScanModel):
    """The columns that lack a value together with one column (design 20.31).

    ``records`` of the dataset have no value for the column in ``missing`` cases;
    among the ``columns`` of the dataset that miss a value, ``partners`` lack one in
    at least one of the same records. They are listed by the share of the records
    that lack a value in either where both do (Jaccard, the most together first),
    ``max_listed`` at most; ``truncated`` says that more exist. The counts are
    exact for every pair, listed or not. It shows that values go missing together,
    not why."""

    kind: Literal["missing_matrix"] = "missing_matrix"
    accuracy: Literal["exact"] = "exact"
    records: int
    missing: int
    columns: int
    partners: int
    truncated: bool
    listed: list[MissingPartner]


class ArrayProfileResult(ScanModel):
    """The lengths of the arrays of a field, exactly (design 20.33).

    ``arrays`` occurrences of the field are arrays, ``empty`` of them have no item
    and ``items`` is the sum of their lengths. ``length_histogram`` counts every
    length that occurs; the quantiles follow from it, so they are exact."""

    kind: Literal["array_profile"] = "array_profile"
    accuracy: Literal["exact"] = "exact"
    arrays: int
    empty: int
    items: int
    min_length: int
    max_length: int
    mean_length: Number
    quantiles: list[Quantile]
    length_histogram: list[LengthCount]


class StructureVariant(ScanModel):
    """A set of keys that ``count`` objects have: ``keys`` of them are present
    and ``absent`` names the keys of the object field that this set lacks (the
    first ones, in order of first appearance); ``absent_total`` counts them all."""

    count: int
    keys: int
    absent: list[str]
    absent_total: int


class StructureResult(ScanModel):
    """The sets of keys of the objects of a field (design 20.33).

    Of the ``objects`` the field holds, ``distinct`` sets of keys were tracked,
    each counted exactly from its first occurrence. ``complete`` says that no
    object had a set beyond ``max_variants``: otherwise ``untracked`` objects have
    a set that is not counted, and ``distinct`` is a lower bound. The ``listed``
    sets are the most frequent ones and ``other_objects`` the objects of the
    tracked sets that are not listed. ``key_names`` lists the keys in order of first
    appearance, ``keys`` counts them all, and ``always`` counts those present in
    every object. It shows that objects differ in their keys, not why."""

    kind: Literal["structure_variants"] = "structure_variants"
    accuracy: Literal["exact"] = "exact"
    objects: int
    keys: int
    always: int
    key_names: list[str]
    key_names_truncated: bool
    distinct: int
    complete: bool
    untracked: int
    listed: list[StructureVariant]
    other_objects: int


class TextBucket(ScanModel):
    """The texts whose measure is from ``low`` to ``high``, both included."""

    low: int
    high: int
    count: int


class TextProfileResult(ScanModel):
    """The words, the lines and the digits of the texts of a field, exactly (design
    20.34).

    A word is a run of characters that are not white space (``str.split``) and a
    line is one that ``str.splitlines`` cuts; a digit is a decimal digit of Unicode
    (category ``Nd``). ``word_buckets`` and ``line_buckets`` count the texts by
    powers of two (0, 1, 2 to 3, 4 to 7, and so on) and ``digit_buckets`` by tenth
    of the characters that are digits: the first count is the texts without any, the
    next ten the shares up to a tenth, two tenths, and so on up to all. The text
    itself is never kept."""

    kind: Literal["text_profile"] = "text_profile"
    accuracy: Literal["exact"] = "exact"
    texts: int
    characters: int
    words: int
    min_words: int
    max_words: int
    mean_words: Number
    lines: int
    max_lines: int
    multi_line: int
    digits: int
    digit_share: Number
    word_buckets: list[TextBucket]
    line_buckets: list[TextBucket]
    digit_buckets: list[int]


class RepeatedText(ScanModel):
    """A text found ``count`` times, known by its digest alone."""

    digest: str
    count: int


class FingerprintResult(ScanModel):
    """The distinct values of a field counted by a 128-bit fingerprint, for
    values too long for an exact set (design 20.34).

    Two values are one when their digests are, which an accident is as unlikely
    as 2**-128 per pair, so the count is ``fingerprint_based`` and not exact. The
    digest is the one the Scan gives its long texts (BLAKE2b, 128 bits, native type
    then text), so a listed digest names an entry of the Scan's sample. ``repeated``
    counts the distinct values found more than once, ``repeated_occurrences`` their
    occurrences, and ``listed`` the most repeated ones, never the text."""

    kind: Literal["fingerprint_distinct"] = "fingerprint_distinct"
    accuracy: Literal["fingerprint_based"] = "fingerprint_based"
    algorithm: str
    bits: int
    values: int
    distinct: int
    redundant: int
    unique: bool
    repeated: int
    repeated_occurrences: int
    listed: list[RepeatedText]
    truncated: bool


class FormCount(ScanModel):
    """A form (a mask, or a class) and the values that take it."""

    form: str
    count: int


class FormClasses(ScanModel):
    """The values of a sensitive field by class of what the detector reads:
    ``ip_address`` or ``phone``. A class that fewer than ``min_count`` values take
    is part of ``other``. ``unclassified`` counts the values the detector did not
    read."""

    detector: Literal["ip_address", "phone"]
    listed: list[FormCount]
    other: int
    unclassified: int


class FormsResult(ScanModel):
    """What the second pass counts of a sensitive field whose values the exposure
    keeps out of the document (design 20.35, decision O61): the masks the values
    take, with their exact counts, and their class for an address or a phone
    number. Never a value, and no figure about fewer than ``min_count`` of them: a
    mask or a class below it is summed up in ``other_forms``, ``other_values`` and
    ``other``. ``forms`` counts the distinct masks when ``complete``; with more
    than ``max_tracked`` of them the count of the masks tracked is a lower bound
    and ``untracked`` values take another one."""

    kind: Literal["sensitive_forms"] = "sensitive_forms"
    accuracy: Literal["exact"] = "exact"
    exposure: Literal["mask"] = "mask"
    values: int
    forms: int
    complete: bool
    untracked: int
    min_count: int
    listed: list[FormCount]
    other_forms: int
    other_values: int
    classes: FormClasses | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("classes",))


class CharacterProfileResult(CharacterMap):
    """The character map of a field counted on every string, exactly (design
    20.37): the members of ``CharacterMap`` with ``basis`` ``exact``. It replaces the
    map of the Scan, which counts the stored samples."""

    kind: Literal["character_profile"] = "character_profile"
    basis: Literal["exact"] = "exact"  # type: ignore[assignment]  # narrows the Scan's


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
    | ShapeResult
    | PartsResult
    | ResidualResult
    | DuplicateResult
    | DuplicatesLimited
    | PearsonResult
    | CrosstabResult
    | StatsResult
    | PositionDriftResult
    | MissingMatrixResult
    | ArrayProfileResult
    | StructureResult
    | TextProfileResult
    | FingerprintResult
    | FormsResult
    | CharacterProfileResult,
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
