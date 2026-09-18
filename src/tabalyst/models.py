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
    missing_count: int
    missing_percent: float
    distinct_count: int
    examples: list[str]
    value_profile: ValueProfile
    semantic_type: Literal["enum"] | None = None
    enum: EnumCandidate | None = None
    numeric: NumericStats | None = None


class DatasetSummary(ResultModel):
    row_count: int
    column_count: int
    cell_count: int
    missing_count: int
    missing_percent: float
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
    format_version: Literal["0.2"] = "0.2"
    generated_at: datetime
    source: SourceInfo
    config: AnalysisConfig
    summary: DatasetSummary
    columns: list[ColumnProfile]
    issues: list[Issue]
    preview: list[PreviewRow]
