# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Finalized, immutable scan results (design sections 8 and 16).

Blocks introduced by later lots are absent until their lot, then always
present, with an envelope status when they do not apply.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from tabalyst.scanner.config import MissingCategory, ScalarType, ScanConfig
from tabalyst.scanner.observations import DatasetKind, NativeType

T = TypeVar("T")

FORMAT = "tabalyst.scan"
FORMAT_VERSION = "0.2.0"
FORMAT_REVISION = 2


class ScanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Measure envelopes -----------------------------------------------------------


class Complete(ScanModel, Generic[T]):
    status: Literal["complete"] = "complete"
    value: T


# ``Any``: a serialized model is a plain dict whose values are JSON data.
def _omit_none(data: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """Drop the optional members that carry no information (absent is not
    ``null``: the contract names them only when they are known)."""
    for name in names:
        if data.get(name, 0) is None:
            del data[name]
    return data


class Limited(ScanModel):
    status: Literal["limited"] = "limited"
    reason: str
    limit: int
    lower_bound: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unproven_bound(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("lower_bound",))


class NotApplicable(ScanModel):
    status: Literal["not_applicable"] = "not_applicable"
    reason: str


class Disabled(ScanModel):
    status: Literal["disabled"] = "disabled"


class Failed(ScanModel):
    status: Literal["failed"] = "failed"
    reason: str
    diagnostic: int


def measure(value_type: Any) -> Any:
    """Envelope of a limitable measure whose complete value is ``value_type``."""
    return Annotated[
        Complete[value_type] | Limited | NotApplicable | Disabled | Failed,
        Field(discriminator="status"),
    ]


IntMeasure = measure(int)

# Accuracy of a value or of the identity of the values it counts (design 18.1):
# ``exact``, ``estimated`` by a named method, ``fingerprint_based`` (equality of
# a digest, not of the whole value) or ``unknown``.
Accuracy = Literal["exact", "estimated", "fingerprint_based", "unknown"]


class CardinalityEstimate(ScanModel):
    """KMV estimate of the distinct original values (design 18.5).

    ``value`` is held within the certain bounds of the envelope;
    ``unclamped_value`` is the raw estimator, present only when a bound
    changed it. ``theta_hex`` (the sample threshold) is absent for a sensitive
    field: it is the priority of one of its values.
    """

    accuracy: Literal["estimated"] = "estimated"
    method: Literal["kmv"]
    value: float
    unclamped_value: float | None = None
    relative_standard_error: float
    k: int
    theta_hex: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("unclamped_value", "theta_hex"))


class CardinalityComplete(Complete[int]):
    """Exact distinct count of the original values (design 9.1)."""

    accuracy: Accuracy
    domain: str
    identity_accuracy: Accuracy


class CardinalityLimited(Limited):
    """Distinct count that stopped being tracked (design 9.1).

    ``upper_bound`` is the certain maximum (the analyzed values);
    ``threshold_reached_at_record`` and ``overflow_detected_at_record`` are the
    records where the table reached its limit T and where T + 1 values were
    proven, for the reason ``distinct_limit`` only.
    """

    domain: str
    identity_accuracy: Accuracy
    upper_bound: int | None = None
    threshold_reached_at_record: int | None = None
    overflow_detected_at_record: int | None = None
    estimate: CardinalityEstimate | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            (
                "lower_bound",
                "upper_bound",
                "threshold_reached_at_record",
                "overflow_detected_at_record",
                "estimate",
            ),
        )


Cardinality = Annotated[
    CardinalityComplete | CardinalityLimited | NotApplicable | Disabled | Failed,
    Field(discriminator="status"),
]


# Paths ------------------------------------------------------------------------


class KeySegment(ScanModel):
    key: str


class ItemsSegment(ScanModel):
    items: Literal[True] = True


class ColumnSegment(ScanModel):
    column: int


PathSegment = KeySegment | ItemsSegment | ColumnSegment


# Fields -----------------------------------------------------------------------


class Presence(ScanModel):
    parent_type: Literal["object", "array", "record"]
    parent_count: int
    present: int
    absent: int | None


class StringCategories(ScanModel):
    count: int
    empty: int
    blank: int
    marker: int
    content: int


class MissingComponents(ScanModel):
    absent: int | None
    null: int
    empty: int
    blank: int
    marker: int


class Missing(ScanModel):
    count: int
    definition: list[MissingCategory]
    components: MissingComponents


class ArrayStats(ScanModel):
    count: int
    empty: int
    min_length: int
    max_length: int
    total_items: int


class ValueCount(ScanModel):
    """An analytical value in its canonical text, with its native type."""

    value: str
    type: ScalarType
    count: int


class ValueAt(ScanModel):
    value: str
    type: ScalarType
    record: int


class Frequencies(ScanModel):
    distinct: int
    listed: list[ValueCount]
    truncated: bool


class SampleEntry(ValueCount):
    """A sampled original value with its exact count (design 18.9).

    ``id`` numbers the entry in the listing of the Scan and stays the same in a
    Report that keeps a subset of it.
    """

    id: int
    count_accuracy: Accuracy
    identity_accuracy: Accuracy


class SampleHash(ScanModel):
    """Priority function of a bottom-k sample (design 18.3)."""

    algorithm: str
    version: int
    bits: int
    seed: int


class Samples(ScanModel):
    """Distinct original values with their exact counts (design 18.9).

    ``all`` lists every distinct value, in first-seen order; ``bottom_k`` the
    ones of smallest priority, in ascending priority, and names ``k``, the
    ``hash`` and the ``threshold`` (the largest priority kept, as hexadecimal
    digits; absent while no value was dropped and for a sensitive field).

    ``kept`` values are listed out of the ``of`` the scan sampled: a Scan has
    ``kept == of`` unless exposure withheld values (``mask`` merges, ``hide``
    lists none); a Report keeps fewer (design 19.4) and says so here."""

    selection: Literal["all", "bottom_k"]
    kept: int
    of: int
    listed: list[SampleEntry]
    k: int | None = None
    hash: SampleHash | None = None
    threshold: str | None = None

    @model_serializer(mode="wrap")
    def _omit_bottom_k(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("k", "hash", "threshold"))


class FieldValues(ScanModel):
    count: int
    cardinality: Cardinality
    frequencies: measure(Frequencies)
    samples: Samples
    first: ValueAt | None
    last: ValueAt | None


class StringCharacteristics(ScanModel):
    non_ascii: int
    with_line_breaks: int
    with_control_characters: int
    with_surrounding_whitespace: int
    with_repeated_whitespace: int
    uppercase: int
    lowercase: int
    mixed_case: int
    no_letters: int


class LengthCount(ScanModel):
    length: int
    count: int


class StringLengths(ScanModel):
    count: int
    min_length: int
    max_length: int
    mean_length: int | float
    median_length: int | float
    length_histogram: list[LengthCount]


Number = int | float


class NumericStats(ScanModel):
    count: int
    native_count: int
    text_count: int
    min: Number
    max: Number
    sum: Number
    mean: Number
    population_variance: Number
    population_std: Number
    positive: int
    negative: int
    zero: int
    integral_decimals: int
    median: measure(Number)


class BooleanCounts(ScanModel):
    true: int
    false: int


StageName = Literal[
    "raw", "nfc", "trim", "collapse_whitespace", "casefold", "strip_accents"
]


class NormalizationStage(ScanModel):
    """``changed`` and ``cardinality`` are ``null`` for a disabled stage and
    ``changed`` for ``raw``."""

    stage: StageName
    enabled: bool
    changed: int | None
    cardinality: IntMeasure | None


class Variant(ScanModel):
    """A raw string variant of a comparison key."""

    value: str
    count: int


class VariantGroup(ScanModel):
    """A comparison key with at least two distinct raw variants; ``count`` and
    ``distinct`` cover every variant, ``variants`` the most frequent ones."""

    key: str
    count: int
    distinct: int
    variants: list[Variant]
    truncated: bool


class VariantGroups(ScanModel):
    groups: int
    listed: list[VariantGroup]
    truncated: bool


class Normalization(ScanModel):
    version: int
    stages: list[NormalizationStage]
    variant_groups: measure(VariantGroups)


TemporalKindName = Literal["date", "datetime_naive", "datetime_aware", "time"]


class YearCount(ScanModel):
    year: int
    count: int


class TemporalKind(ScanModel):
    """Values of one kind; ``min`` and ``max`` are ISO strings. Aware values
    compare as instants; naive and aware values are never compared."""

    kind: TemporalKindName
    count: int
    min: str
    max: str
    years: list[YearCount] | None


class TemporalStats(ScanModel):
    """Temporal values of the date detector; ``ambiguous`` values are counted
    and excluded (design 9.6)."""

    count: int
    ambiguous: int
    kinds: list[TemporalKind]


TechnicalTypeName = Literal[
    "integer", "number", "date", "boolean", "text", "mixed", "empty"
]


class TechnicalType(ScanModel):
    """Port of the current type inference (design 9.7): ``confidence`` is the
    accepted share, ``null`` without values; ``outside_count`` is ``null`` for
    ``mixed``."""

    type: TechnicalTypeName
    confidence: float | None
    counts: dict[str, int]
    outside_count: int | None


class Coverage(ScanModel):
    """Design 12.2: ``tested = eligible - not_tested`` and ``tested = matched +
    ambiguous + invalid + not_matched``. ``share_tested`` is ``null`` when no
    value was tested."""

    eligible: int
    tested: int
    matched: int
    ambiguous: int
    invalid: int
    not_matched: int
    not_tested: int
    share_tested: float | None
    share_eligible: float


class FormatCount(ScanModel):
    format: str
    count: int


class Evidence(ScanModel):
    """First distinct analytical values of each state, bounded by
    ``limits.max_evidence_examples``."""

    matched: list[str]
    ambiguous: list[str]
    invalid: list[str]
    not_matched: list[str]


class _Detector(ScanModel):
    id: str
    version: int


class Adaptive(ScanModel):
    """Design 13: the detector reacted to ``warmup_reactions`` of the first
    ``skipped_after`` distinct values of the field, none or at most
    ``detection.rare_share`` of them, so later values other than probes were
    not tested. ``diagnostic`` points to the warning raised when a probe
    reacted after a warm-up without any reaction."""

    skipped_after: int
    warmup_reactions: int
    not_tested: int
    diagnostic: int | None


class DetectorComplete(_Detector):
    status: Literal["complete"] = "complete"
    coverage: Coverage
    formats: list[FormatCount]
    evidence: Evidence
    details: dict[str, Any]
    adaptive: Adaptive | None


class DetectorNotApplicable(_Detector):
    status: Literal["not_applicable"] = "not_applicable"
    reason: str


class DetectorDisabled(_Detector):
    status: Literal["disabled"] = "disabled"


class DetectorFailed(_Detector):
    """A failure is never reported as values that did not match (CA19)."""

    status: Literal["failed"] = "failed"
    reason: str
    diagnostic: int


DetectorResult = Annotated[
    DetectorComplete | DetectorNotApplicable | DetectorDisabled | DetectorFailed,
    Field(discriminator="status"),
]


class InterpretationCandidate(ScanModel):
    detector: str
    matched: int
    share_eligible: float


class Interpretations(ScanModel):
    """Detectors whose ``share_eligible`` reaches ``detection.minimum_share``;
    ``primary`` only when exactly one qualifies (design 12.4)."""

    primary: str | None
    candidates: list[InterpretationCandidate]


class FieldResult(ScanModel):
    id: str
    path: list[PathSegment]
    display: str
    name: str
    parent: str | None
    collection: str | None
    first_record: int | None
    occurrences: int
    presence: Presence
    native_types: dict[NativeType, int]
    strings: StringCategories
    missing: Missing
    arrays: ArrayStats | None
    values: FieldValues
    string_characteristics: StringCharacteristics
    string_lengths: measure(StringLengths)
    numeric: measure(NumericStats)
    booleans: measure(BooleanCounts)
    temporal: measure(TemporalStats)
    normalization: Normalization
    technical_type: TechnicalType
    detectors: list[DetectorResult]
    interpretations: Interpretations
    sensitive: bool
    # The exposure applied to the values of a sensitive field (design 12.8).
    exposure: Literal["mask", "hide", "show"] | None


# Datasets and scan ----------------------------------------------------------


class Structure(ScanModel):
    paths: IntMeasure
    untracked_observations: int
    depth_truncated_observations: int
    max_depth_seen: int


class RecordList(ScanModel):
    count: int
    # Record indices of the first ones, up to ``limits.max_listed_records``.
    records: list[int]


class DuplicateRecords(ScanModel):
    # Records equal to an earlier record of the dataset, beyond its first
    # occurrence; limited with reason ``record_budget``.
    count: IntMeasure
    records: list[int]


class PreviewRecord(ScanModel):
    record: int
    # Values per field id, as canonical text, through the field's exposure.
    # A JSON null is null; a cell holding a hidden value is null; a field
    # absent from the record has no key.
    values: dict[str, list[str | None] | None]


class Records(ScanModel):
    with_missing: RecordList
    empty: RecordList
    duplicates: DuplicateRecords
    preview: list[PreviewRecord]


class DatasetResult(ScanModel):
    id: str
    kind: DatasetKind
    collection_path: list[PathSegment] | None
    record_count: int
    record_types: dict[NativeType, int]
    structure: Structure
    records: Records
    fields: list[FieldResult]


class Diagnostic(ScanModel):
    code: str
    level: Literal["fatal", "error", "warning"]
    message: str
    count: int
    dataset: str | None
    field: str | None
    detector: str | None
    # Facts of the event, by code (for example the limited measures of a field).
    details: dict[str, Any]
    locations: list[dict[str, int]]


class EngineInfo(ScanModel):
    version: str
    normalization_version: int
    detectors: dict[str, int]


class CsvSourceInfo(ScanModel):
    delimiter: str
    quote: str
    header: list[str]
    # Whether the file starts with a UTF-8 byte order mark.
    bom: bool
    # "lf", "crlf", "cr", "mixed", or null when the file has no line break.
    line_ending: Literal["lf", "crlf", "cr", "mixed"] | None


class ExcelSourceInfo(ScanModel):
    """The table read from a workbook: where it is and what its header says."""

    dataset_path: str
    sheet: str
    table: str | None
    # A1 range of the header and the data, and the 1-based header row.
    range: str
    header_row: int
    header: list[str]


class SourceShape(ScanModel):
    """Global size of the source, whatever the dataset."""

    # Physical lines of a CSV file (header and multi-line cells included);
    # null for the other formats.
    lines: int | None
    # Analyzed records, all datasets together.
    records: int
    # Columns of a tabular source (CSV or Excel); null for JSON and JSONL.
    columns: int | None
    # Fields discovered, all datasets together.
    fields: int
    datasets: int
    # Analyzed records times columns; null when the source is not tabular.
    cells: int | None
    # Cells with a missing value, all fields together (see ``values.missing``).
    missing_cells: int
    # Records with at least one missing value, empty records and records
    # equal to an earlier one (null when the count is limited or disabled),
    # all datasets together.
    records_with_missing: int
    empty_records: int
    duplicate_records: int | None


class SourceInfo(ScanModel):
    format: Literal["csv", "json", "jsonl", "excel"]
    name: str
    size_bytes: int
    modified_at: datetime
    sha256: str
    encoding: str | None
    shape: SourceShape
    csv: CsvSourceInfo | None
    excel: ExcelSourceInfo | None = None

    @property
    def header(self) -> list[str] | None:
        """The column names of a tabular source (CSV or Excel), ``None`` for a
        JSON source."""
        if self.csv is not None:
            return self.csv.header
        return None if self.excel is None else self.excel.header


class CollectionScope(ScanModel):
    mode: Literal["auto", "explicit"]
    requested: list[str] | None


class Scope(ScanModel):
    collections: CollectionScope | None
    records_read: int
    records_analyzed: int
    records_excluded: int
    exclusions: dict[str, int]


class Timings(ScanModel):
    """Where ``RunInfo.duration_seconds`` went; the four parts add up to it."""

    # Reading and parsing the source, hashing included.
    reading: float
    # Analysis of the values, record callbacks included. With several workers,
    # the time the main process spends on it, waiting for workers included.
    analysis: float
    # Final computation of the datasets.
    finalize: float
    # Setup (workers, detectors) and the assembly of the result.
    other: float


class RunInfo(ScanModel):
    """What varies from one run to the next on the same source: it is not part
    of the description of the data."""

    started_at: datetime
    duration_seconds: float
    timings: Timings
    # Processes that analyzed values: 1 when the scan ran in the main process.
    workers: int
    # Peak memory of the main process (workers excluded) when the scan ended,
    # in bytes; null when the platform does not report it. It covers the whole
    # process, so it includes earlier work in the same process.
    peak_memory_bytes: int | None


class ScanResult(ScanModel):
    format: Literal["tabalyst.scan"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: int = FORMAT_REVISION
    engine: EngineInfo
    status: Literal["complete", "partial"]
    run: RunInfo
    source: SourceInfo
    config: ScanConfig
    config_sha256: str
    scope: Scope
    datasets: list[DatasetResult]
    diagnostics: list[Diagnostic]
