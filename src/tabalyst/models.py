"""Serializable report profile (revision 5), independent from presentation.

Built from a Tabalyst Scan result by ``report_profile.py``.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, FiniteFloat

from tabalyst.report_config import ReportConfig


class ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInfo(ResultModel):
    filename: str
    format: Literal["csv", "json"]
    size_bytes: int
    sha256: str
    encoding: str
    # Null for JSON sources.
    delimiter: str | None


class NumericStats(ResultModel):
    minimum: FiniteFloat
    maximum: FiniteFloat
    range: FiniteFloat
    mean: FiniteFloat
    # Null when the scan limited the median (its frequency table was released).
    median: FiniteFloat | None


class NormalizationStats(ResultModel):
    trim_count: int
    trim_percent: float
    collapse_internal_whitespace_count: int
    collapse_internal_whitespace_percent: float


class DateFormatCount(ResultModel):
    format: str
    # Null for formats that are not numeric dates (month names, times).
    order: Literal["YMD", "MDY", "DMY"] | None
    separator: str | None
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
    present_count: int
    valid_count: int
    valid_percent: float
    ambiguous_count: int
    ambiguous_percent: float
    invalid_date_count: int
    invalid_date_percent: float
    not_date_count: int
    not_date_percent: float
    resolved_ambiguous_order: Literal["MDY", "DMY"] | None = None
    ambiguous_order_source: Literal["config"] | None = None
    # Unambiguous values per day-month order, exposed and never applied.
    ambiguity_evidence: dict[str, int]
    formats: list[DateFormatCount]
    format_count: int
    breakdown: list[DateBreakdownItem]


class StringLengthExample(ResultModel):
    value: str
    count: int


class StringLengthDistribution(ResultModel):
    length: int
    count: int
    percent: float
    relative_percent: float
    examples: list[StringLengthExample]


class StringProfile(ResultModel):
    status: Literal["very_short", "short", "medium", "long", "very_long"]
    present_count: int
    minimum_length: int
    maximum_length: int
    mean_length: FiniteFloat
    median_length: FiniteFloat
    distinct_length_count: int
    fixed_length: int | None = None
    length_distribution: list[StringLengthDistribution]
    representative_examples: list[str]


class ValueOccurrence(ResultModel):
    value: str
    count: int
    truncated: bool = False


class ValueProfile(ResultModel):
    selection: Literal["complete", "diverse_sample", "random_sample"]
    sampled_distinct_count: int
    values: list[ValueOccurrence]


class DetectorFormat(ResultModel):
    format: str
    count: int
    percent: float


class DetectorProfile(ResultModel):
    """What one detector recognized in a column (design 12.3)."""

    id: str
    status: Literal["complete", "failed"]
    primary: bool
    eligible_count: int
    matched_count: int
    matched_percent: float
    ambiguous_count: int
    invalid_count: int
    formats: list[DetectorFormat]


class ColumnProfile(ResultModel):
    id: str
    name: str
    # Display path of the scan field: the column label for CSV sources,
    # ``orders[].amount`` for JSON sources.
    path: str
    position: int
    inferred_type: Literal[
        "empty", "boolean", "integer", "number", "date", "text", "mixed"
    ]
    type_counts: dict[str, int]
    type_confidence: float | None
    type_error_count: int | None
    type_error_percent: float | None
    missing_count: int
    missing_percent: float
    with_issues: bool
    normalization: NormalizationStats
    # Null when a scan limit released the frequency table of the column.
    distinct_count: int | None
    examples: list[str]
    value_profile: ValueProfile
    semantic_type: str | None = None
    # How the values of a sensitive column are exposed, null otherwise.
    exposure: Literal["mask", "hide", "show"] | None = None
    date_profile: DateProfile | None = None
    string_profile: StringProfile | None = None
    numeric: NumericStats | None = None
    # Detectors that recognized values, in scan order; failed ones included.
    detectors: list[DetectorProfile] = []


class DatasetSummary(ResultModel):
    row_count: int
    column_count: int
    cell_count: int
    missing_count: int
    missing_percent: float
    trim_count: int
    collapse_internal_whitespace_count: int
    # A lower bound when ``duplicate_row_status`` is ``limited`` (the scan's
    # ``limits.max_tracked_records``), null when duplicates are not checked.
    duplicate_row_count: int | None
    duplicate_row_status: Literal["complete", "limited", "disabled"]
    empty_row_count: int
    empty_column_count: int
    constant_column_count: int
    with_issues_column_count: int
    numeric_column_count: int
    date_column_count: int
    string_column_count: int
    inferred_type_counts: dict[str, int]
    inferred_type_percents: dict[str, float]
    semantic_type_counts: dict[str, int]
    semantic_type_percents: dict[str, float]


class DatasetDateColumnSummary(ResultModel):
    column_id: str
    name: str
    position: int
    ambiguous_count: int
    relative_ambiguous_percent: float


class DatasetDateSummary(ResultModel):
    present_count: int
    valid_count: int
    ambiguous_count: int
    ambiguous_percent: float
    invalid_date_count: int
    not_date_count: int
    maximum_column_ambiguous_count: int
    columns: list[DatasetDateColumnSummary]


class Issue(ResultModel):
    code: str
    severity: Literal["info", "warning"]
    message: str
    count: int
    column_ids: list[str]
    row_numbers: list[int]


class PreviewRow(ResultModel):
    row_number: int
    # Null for a hidden value of a sensitive column, or a JSON value absent
    # from the record; the values of an items path are joined with ", ".
    values: list[str | None]
    # Positions (0-based) of the values absent from a JSON record.
    absent: list[int] = []


class DatasetProfile(ResultModel):
    """One scan dataset: the rows of a CSV, or the records of a JSON document
    or collection (design 5)."""

    id: str
    kind: Literal["table", "document", "collection"]
    summary: DatasetSummary
    date_summary: DatasetDateSummary | None = None
    columns: list[ColumnProfile]
    issues: list[Issue]
    preview: list[PreviewRow]


class ReportProfile(ResultModel):
    format_version: Literal["0.1.0a"] = "0.1.0a"
    format_revision: Literal[5] = 5
    generated_at: datetime
    processing_seconds: FiniteFloat
    source: SourceInfo
    config: ReportConfig
    datasets: list[DatasetProfile]
