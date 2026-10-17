# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Serializable report document (format ``tabalyst.report``, revision 4).

The document is the Scan base at the same paths, plus a ``report`` block with
the generation data, the presentation settings and the projections by dataset
and field identifier. Built from a Tabalyst Scan result by ``report_profile.py``.
The findings of the Scan (observations, limits, patterns) and its row sample are
read from the base, never copied into the projections.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, FiniteFloat, model_serializer

from tabalyst.config import PresentationSettings
from tabalyst.result_model import ResultModel
from tabalyst.scanner.classify.models import Classification
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.models import (
    Adaptive,
    Coverage,
    DatasetResult,
    Derived,
    Diagnostic,
    EngineInfo,
    Evidence,
    Observations,
    RunInfo,
    Scope,
)
from tabalyst.scanner.models import SourceInfo as ScanSource
from tabalyst.scanner.secondpass.models import DeepResult
from tabalyst.summary_models import ColumnSummary, TableSummary

FORMAT = "tabalyst.report"
FORMAT_VERSION = "0.2.0"
FORMAT_REVISION = 4


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
    details: dict[str, Any] = Field(default_factory=dict)
    adaptive: Adaptive | None = None


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
    normalization: NormalizationStats
    # Null when a scan limit released the frequency table of the column.
    distinct_count: int | None
    examples: list[str]
    value_profile: ValueProfile
    # Family and type of the column: the Scan's classification refined by the
    # second pass (``report_classification.refine``).
    classification: Classification
    # How the values of a sensitive column are exposed, null otherwise.
    exposure: Literal["mask", "hide", "show"] | None = None
    # Detectors that recognized values, in scan order; failed ones included.
    detectors: list[DetectorProfile] = Field(default_factory=list)
    # What the Summary table and the previews say, built with the document
    # (contract summary-table.md 20); ``None`` until ``report_summary`` fills it.
    summary: ColumnSummary | None = None


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
    numeric_column_count: int
    date_column_count: int
    string_column_count: int
    inferred_type_counts: dict[str, int]
    inferred_type_percents: dict[str, float]
    # Columns by family (key ``family``) and by type (key ``family/type``).
    type_family_counts: dict[str, int]
    type_family_percents: dict[str, float]
    type_counts: dict[str, int]
    type_percents: dict[str, float]


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
    structure: DatasetStructure | None = None
    # The counts and KPIs above the Summary table (contract 20); ``None`` until
    # ``report_summary`` fills it.
    table: TableSummary | None = None


class ReportGenerator(ResultModel):
    name: Literal["tabalyst"] = "tabalyst"
    version: str


class BaseScan(ResultModel):
    """The base a Report stands on (design 19.5): the identity of the Scan it
    holds, so that the base can be recognized, compared and extracted."""

    format: Literal["tabalyst.scan"]
    format_version: Literal["0.2.0"]
    format_revision: int
    engine_version: str
    source_sha256: str
    config_sha256: str
    # SHA-256 of the facts: the base without ``run`` and without the contents
    # of the samples, so that a Report has the identity of its Scan whatever
    # its presentation settings or the sample values it kept.
    facts_sha256: str


class ReportBlock(ResultModel):
    """What a Report adds to the Scan base."""

    generated_at: datetime
    generator: ReportGenerator
    processing_seconds: FiniteFloat
    # Presentation only; the Scan configuration is the root ``config``.
    config: PresentationSettings
    base_scan: BaseScan
    # One projection per dataset shown, identified by the dataset ``id``; its
    # columns are identified by the field ``id``.
    datasets: list[DatasetProfile]


AnalysesMode = Literal["auto", "forced", "off"]
AnalysesOutcome = Literal[
    "ran", "reused", "nothing_selected", "disabled", "unavailable", "failed"
]


class AnalysesBlock(ResultModel):
    """What the second pass did for this Report (design 20.1, rule R1).

    ``mode`` says who decided: ``auto`` (the planner, on benefit and cost),
    ``forced`` (``--deep`` or ``deep.mode`` ``force``) or ``off`` (``deep.mode``
    ``off``). ``outcome`` is ``ran`` (analyses were computed), ``reused`` (stored
    results were enough), ``nothing_selected``, ``disabled``, ``unavailable``
    (the analyses that need the source could not read it: ``reason`` says why and
    each is ``skipped`` in ``deep``) or ``failed`` (an automatic second pass met
    an error and the Report goes without it). ``deep`` is the second-pass
    document, the plan with what it kept, left out and why, and the results; it
    is absent when no plan was made."""

    mode: AnalysesMode
    outcome: AnalysesOutcome
    reason: str | None = None
    deep: DeepResult | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        data = handler(self)
        for name in ("reason", "deep"):
            if data.get(name, 0) is None:
                del data[name]
        return data


class ReportProfile(ResultModel):
    """The Report document: the Scan base, then the ``report`` block."""

    # Plain names of the fields of the base, as in a Scan document.
    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    format: Literal["tabalyst.report"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[4] = FORMAT_REVISION
    engine: EngineInfo
    status: Literal["complete", "partial"]
    run: RunInfo
    source: ScanSource
    config: ScanConfig
    config_sha256: str
    scope: Scope
    datasets: list[DatasetResult]
    diagnostics: list[Diagnostic]
    # The ``derived`` block of the Scan, carried as it is: a Report keeps fewer
    # sample values and cannot compute it again (design 19.3).
    derived: Derived | None = None
    # Likewise the ``observations`` block, computed by the Scan from its facts.
    observations: Observations | None = None
    # What the second pass added to the Report (design 20.4); the common loader
    # ignores it, like ``report``.
    analyses: AnalysesBlock | None = None
    report: ReportBlock

    @model_serializer(mode="wrap")
    def _omit_derived(self, handler) -> dict[str, Any]:
        data = handler(self)
        for name in ("derived", "observations", "analyses"):
            if data.get(name, 0) is None:
                del data[name]
        return data
