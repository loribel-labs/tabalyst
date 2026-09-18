"""Serializable analysis results, independent from presentation."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, FiniteFloat

from tabalyst.config import AnalysisConfig


class ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInfo(ResultModel):
    filename: str
    size_bytes: int
    sha256: str
    encoding: str
    delimiter: str


class NumericStats(ResultModel):
    minimum: FiniteFloat
    maximum: FiniteFloat
    mean: FiniteFloat
    median: FiniteFloat


class NormalizationStats(ResultModel):
    trim_count: int
    trim_percent: float
    collapse_internal_whitespace_count: int
    collapse_internal_whitespace_percent: float


class DateFormatCount(ResultModel):
    format: str
    order: Literal["YMD", "MDY", "DMY"]
    separator: str
    count: int
    percent: float
    iso: bool = False


class DateBreakdownItem(ResultModel):
    label: str
    category: Literal["valid", "ambiguous", "invalid", "not_date"]
    count: int
    percent: float


class DateProfile(ResultModel):
    status: Literal["valid", "multiple_formats", "mixed", "ambiguous", "invalid"]
    valid_count: int
    ambiguous_count: int
    invalid_date_count: int
    not_date_count: int
    resolved_ambiguous_order: Literal["MDY", "DMY"] | None = None
    ambiguous_order_source: Literal["config", "column"] | None = None
    formats: list[DateFormatCount]
    format_count: int
    breakdown: list[DateBreakdownItem]
    errors: dict[str, int]


class StringLengthExample(ResultModel):
    value: str
    count: int


class StringLengthDistribution(ResultModel):
    length: int
    count: int
    percent: float
    distinct_count: int
    examples: list[StringLengthExample]


class StringProfile(ResultModel):
    status: Literal["very_short", "short", "medium", "long", "very_long"]
    present_count: int
    minimum_length: int
    maximum_length: int
    distinct_length_count: int
    fixed_length: int | None = None
    length_distribution: list[StringLengthDistribution]


class ValueOccurrence(ResultModel):
    value: str
    count: int
    truncated: bool = False


class ValueProfile(ResultModel):
    selection: Literal["complete", "diverse_sample", "random_sample"]
    sampled_distinct_count: int
    values: list[ValueOccurrence]


class EnumCandidate(ResultModel):
    status: Literal["candidate"] = "candidate"
    observed_distinct_count: int
    non_missing_count: int
    coverage_percent: float
    confidence: float


class ColumnProfile(ResultModel):
    id: str
    name: str
    position: int
    inferred_type: Literal[
        "empty", "boolean", "integer", "number", "date", "text", "mixed"
    ]
    type_counts: dict[str, int]
    type_confidence: float
    type_error_count: int | None
    type_error_percent: float | None
    missing_count: int
    missing_percent: float
    normalization: NormalizationStats
    distinct_count: int
    examples: list[str]
    value_profile: ValueProfile
    semantic_type: Literal["enum", "date"] | None = None
    enum: EnumCandidate | None = None
    date_profile: DateProfile | None = None
    string_profile: StringProfile | None = None
    numeric: NumericStats | None = None


class DatasetSummary(ResultModel):
    row_count: int
    column_count: int
    cell_count: int
    missing_count: int
    missing_percent: float
    trim_count: int
    collapse_internal_whitespace_count: int
    duplicate_row_count: int
    empty_row_count: int
    empty_column_count: int
    constant_column_count: int


class Issue(ResultModel):
    code: str
    severity: Literal["info", "warning"]
    message: str
    count: int
    column_ids: list[str]
    row_numbers: list[int]


class PreviewRow(ResultModel):
    row_number: int
    values: list[str]


class DatasetProfile(ResultModel):
    format_version: Literal["0.3"] = "0.3"
    generated_at: datetime
    processing_seconds: FiniteFloat
    source: SourceInfo
    config: AnalysisConfig
    summary: DatasetSummary
    columns: list[ColumnProfile]
    issues: list[Issue]
    preview: list[PreviewRow]
