# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Serializable report profile (revision 10), independent from presentation.

Built from a Tabalyst Scan result by ``report_profile.py``.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, FiniteFloat

from tabalyst.report_config import ReportConfig
from tabalyst.scanner.models import (
    Adaptive,
    BooleanCounts,
    Coverage,
    Evidence,
    Missing,
    Presence,
    StringCategories,
    StringCharacteristics,
    StringLengths,
    TemporalStats,
    ValueAt,
)
from tabalyst.scanner.models import NumericStats as ScanNumericStats


class ResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInfo(ResultModel):
    filename: str
    format: Literal["csv", "json", "jsonl", "excel"]
    size_bytes: int
    sha256: str
    # Null for an Excel workbook, which has no text encoding.
    encoding: str | None
    # Null for JSON, JSONL and Excel sources.
    delimiter: str | None


class NumericStats(ResultModel):
    minimum: FiniteFloat
    maximum: FiniteFloat
    range: FiniteFloat
    mean: FiniteFloat
    # Null when the scan limited the median (its frequency table was released).
    median: FiniteFloat | None


MeasureStatus = Literal["complete", "limited", "not_applicable", "disabled", "failed"]


class NormalizationStage(ResultModel):
    """One stage of the scan's normalization (design 10), ``raw`` first."""

    stage: Literal[
        "raw", "nfc", "trim", "collapse_whitespace", "casefold", "strip_accents"
    ]
    enabled: bool
    # Occurrences changed by the stage; null for ``raw`` and disabled stages.
    changed_count: int | None
    changed_percent: float | None
    # Distinct values after the stage; null unless ``distinct_status`` is
    # ``complete``.
    distinct_count: int | None
    distinct_status: MeasureStatus


class Variant(ResultModel):
    value: str
    count: int


class VariantGroup(ResultModel):
    """Raw spellings sharing one comparison key."""

    key: str
    count: int
    distinct_count: int
    variants: list[Variant]
    truncated: bool


class NormalizationStats(ResultModel):
    trim_count: int
    trim_percent: float
    collapse_internal_whitespace_count: int
    collapse_internal_whitespace_percent: float
    stages: list[NormalizationStage]
    # Comparison keys with at least two raw spellings; null unless
    # ``variant_group_status`` is ``complete``.
    variant_group_count: int | None
    variant_group_status: MeasureStatus
    # The largest groups listed by the scan; empty for a hidden column.
    variant_groups: list[VariantGroup]
    variant_groups_truncated: bool


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
    coverage: Coverage | None = None
    evidence: Evidence | None = None
    details: dict[str, Any] = {}
    adaptive: Adaptive | None = None


class ScanFieldDetails(ResultModel):
    """Useful bounded field evidence retained from the exposed Scan document."""

    first_record: int | None
    occurrences: int
    value_count: int
    presence: Presence
    native_types: dict[str, int]
    strings: StringCategories
    missing: Missing
    first: ValueAt | None
    last: ValueAt | None
    string_characteristics: StringCharacteristics
    string_lengths: StringLengths | None
    numeric: ScanNumericStats | None
    booleans: BooleanCounts | None
    temporal: TemporalStats | None


class ColumnProfile(ResultModel):
    id: str
    name: str
    # Display path of the scan field: the column label for CSV sources,
    # ``orders[].amount`` for JSON sources.
    path: str
    position: int
    inferred_type: Literal[
        "empty", "complex", "boolean", "integer", "number", "date", "text", "mixed"
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
    scan_details: ScanFieldDetails | None = None


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


class MeasureLimit(ResultModel):
    """A scan measure stopped by a limit (design 8 and 11)."""

    # Null for a measure of the dataset.
    column_id: str | None
    # Display path of the scan field, null for a measure of the dataset.
    path: str | None
    # Location of the envelope in the scan result, such as
    # ``values.cardinality`` or ``normalization.stages.casefold.cardinality``.
    measure: str
    reason: str
    limit: int
    lower_bound: int | None


class DiagnosticLocation(ResultModel):
    record: int
    # CSV line, or 0-based JSON element index; null when not applicable.
    line: int | None = None
    element: int | None = None


class DiagnosticProfile(ResultModel):
    code: str
    level: Literal["fatal", "error", "warning"]
    message: str
    count: int
    # Null for a diagnostic of the whole scan.
    dataset: str | None
    path: str | None
    detector: str | None
    locations: list[DiagnosticLocation]


class DatasetLimits(ResultModel):
    """What the scan could not measure completely in a dataset."""

    measures: list[MeasureLimit]
    untracked_observations: int
    depth_truncated_observations: int
    # Diagnostics of this dataset and of the whole scan.
    diagnostics: list[DiagnosticProfile]


class ArrayProfile(ResultModel):
    count: int
    empty_count: int
    minimum_length: int
    maximum_length: int
    mean_length: FiniteFloat
    item_count: int


class StructureField(ResultModel):
    """One path of a JSON dataset, containers included (design 16.2)."""

    id: str
    path: str
    depth: int
    # Display path of the parent field, null at the record root.
    parent: str | None
    native_types: dict[str, int]
    occurrences: int
    parent_type: Literal["object", "array", "record"]
    parent_count: int
    present_count: int
    # Null for array items, which cannot be absent.
    absent_count: int | None
    # Share of the parents holding the field; null for array items, which
    # count elements rather than parents.
    present_percent: float | None
    # Dataset holding the elements of a promoted array.
    collection: str | None
    arrays: ArrayProfile | None
    # Whether the field is also listed as a column.
    column: bool


class DatasetStructure(ResultModel):
    """Shape of a JSON dataset; null for CSV sources."""

    record_types: dict[str, int]
    # Null unless ``path_status`` is ``complete``: ``scan.limits.max_fields``.
    path_count: int | None
    path_status: Literal["complete", "limited"]
    max_depth_seen: int
    fields: list[StructureField]


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
    limits: DatasetLimits
    structure: DatasetStructure | None = None


class ReportProfile(ResultModel):
    format_version: Literal["0.1.0a"] = "0.1.0a"
    format_revision: Literal[11] = 11
    generated_at: datetime
    processing_seconds: FiniteFloat
    source: SourceInfo
    config: ReportConfig
    datasets: list[DatasetProfile]
