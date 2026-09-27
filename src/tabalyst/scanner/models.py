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
FORMAT_VERSION = "0.1.0a"
FORMAT_REVISION = 1


class ScanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Measure envelopes -----------------------------------------------------------


class Complete(ScanModel, Generic[T]):
    status: Literal["complete"] = "complete"
    value: T


class Limited(ScanModel):
    status: Literal["limited"] = "limited"
    reason: str
    limit: int
    lower_bound: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unproven_bound(self, handler) -> dict[str, Any]:
        data = handler(self)
        if data.get("lower_bound") is None:
            data.pop("lower_bound", None)
        return data


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


class Samples(ScanModel):
    selection: Literal["all", "uniform_distinct", "first_seen"]
    listed: list[ValueCount]


class FieldValues(ScanModel):
    count: int
    cardinality: IntMeasure
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
    normalization: Normalization


# Datasets and scan ----------------------------------------------------------


class Structure(ScanModel):
    paths: IntMeasure
    untracked_observations: int
    depth_truncated_observations: int
    max_depth_seen: int


class DatasetResult(ScanModel):
    id: str
    kind: DatasetKind
    collection_path: list[PathSegment] | None
    record_count: int
    record_types: dict[NativeType, int]
    structure: Structure
    fields: list[FieldResult]


class Diagnostic(ScanModel):
    code: str
    level: Literal["fatal", "error", "warning"]
    message: str
    count: int
    dataset: str | None
    field: str | None
    detector: str | None
    locations: list[dict[str, int]]


class EngineInfo(ScanModel):
    version: str
    normalization_version: int
    detectors: dict[str, int]


class CsvSourceInfo(ScanModel):
    delimiter: str
    header: list[str]


class SourceInfo(ScanModel):
    format: Literal["csv", "json"]
    name: str
    size_bytes: int
    modified_at: datetime
    sha256: str
    encoding: str | None
    csv: CsvSourceInfo | None


class CollectionScope(ScanModel):
    mode: Literal["auto", "explicit"]
    requested: list[str] | None


class Scope(ScanModel):
    collections: CollectionScope | None
    records_read: int
    records_analyzed: int
    records_excluded: int
    exclusions: dict[str, int]


class ScanResult(ScanModel):
    format: Literal["tabalyst.scan"] = FORMAT
    format_version: Literal["0.1.0a"] = FORMAT_VERSION
    format_revision: int = FORMAT_REVISION
    engine: EngineInfo
    status: Literal["complete", "partial"]
    started_at: datetime
    duration_seconds: float
    source: SourceInfo
    config: ScanConfig
    config_sha256: str
    scope: Scope
    datasets: list[DatasetResult]
    diagnostics: list[Diagnostic]
