"""Finalized, immutable scan results (design sections 8 and 16).

Blocks introduced by later lots are absent until their lot, then always
present, with an envelope status when they do not apply.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from tabalyst.scanner.config import MissingCategory, ScanConfig
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


class FieldValues(ScanModel):
    count: int


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
