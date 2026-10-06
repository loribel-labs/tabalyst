# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Inspect document and configuration models (design inspect section 4).

The document has a common shell (format triple, ``inspect``, ``source``,
``warnings``, ``config``) and a part that belongs to the Inspect kind
(``detection``, here JSON). Optional keys are absent from the JSON form, not
``null``, as the contract says. Every model refuses unknown keys.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from tabalyst.scanner.config import ErrorPolicy, FlattenSettings, canonical_excel_path
from tabalyst.scanner.paths import Items, format_absolute, parse_path

FORMAT = "tabalyst.inspect"
FORMAT_VERSION = "0.2.0"
FORMAT_REVISION = 1
NOTE = (
    'Edit only the "config" section. Tabalyst replaces every other section each '
    "time it inspects this source."
)

NativeName = Literal["object", "array", "string", "number", "boolean", "null"]
# Order of the counts of ``element_types`` (design 4.7).
NATIVE_ORDER: tuple[NativeName, ...] = (
    "object",
    "array",
    "string",
    "number",
    "boolean",
    "null",
)


class InspectModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Optional keys that the JSON form leaves out when they are ``None``.
    _sparse: ClassVar[tuple[str, ...]] = ()

    @model_serializer(mode="wrap")
    def _leave_out_absent_keys(self, handler) -> dict[str, Any]:
        data = handler(self)
        for name in self._sparse:
            if data.get(name) is None:
                data.pop(name, None)
        return data


# Shell -------------------------------------------------------------------


InspectKind = Literal["json", "excel"]


class InspectInfo(InspectModel):
    kind: InspectKind
    tabalyst_version: str
    generated_at: datetime
    note: str = NOTE


class InspectSource(InspectModel):
    name: str
    format: Literal["json", "jsonl", "excel"]
    size_bytes: int = Field(ge=0)
    sha256: str


class Location(InspectModel):
    record: int
    line: int


WarningCode = Literal[
    "ambiguous_collections",
    "no_collection",
    "candidates_truncated",
    "candidate_not_eligible",
    "candidate_not_eligible_truncated",
    "invalid_lines",
    "non_object_lines",
    "configured_path_not_found",
    "source_name_mismatch",
    "blocks_not_split",
    "duplicate_headers",
    "blank_headers",
    "merged_cells",
    "multi_level_header",
]


class InspectWarning(InspectModel):
    code: WarningCode
    level: Literal["warning", "info"]
    message: str
    path: str | None = None
    reason: str | None = None
    count: int | None = None
    locations: list[Location] | None = None

    _sparse: ClassVar[tuple[str, ...]] = ("path", "reason", "count", "locations")


# Configuration -----------------------------------------------------------


class StructureConfig(InspectModel):
    dataset_path: str | None = None

    @field_validator("dataset_path", mode="before")
    @classmethod
    def absolute_collection_path(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            # A ValueError, not a TypeError: pydantic reports only the former.
            raise ValueError(  # noqa: TRY004
                f"dataset_path must be a string or null, not {value!r}"
            )
        if not value.startswith("$"):
            raise ValueError(f"dataset_path must be an absolute path: {value!r}")
        path = parse_path(value)
        if not path or not isinstance(path[-1], Items):
            raise ValueError(
                f"dataset_path must select array elements with '[]': {value!r}"
            )
        # Equal paths in other spellings are the same choice (design 10.3).
        return format_absolute(path)


class ArraysConfig(InspectModel):
    mode: Literal["preserve"] = "preserve"

    @field_validator("mode", mode="before")
    @classmethod
    def supported_mode(cls, value: object) -> object:
        if value in ("ignore", "explode"):
            raise ValueError(
                f"Array mode {value!r} is not supported in this version; "
                "only 'preserve' is"
            )
        return value


class ErrorsConfig(InspectModel):
    policy: ErrorPolicy | None = None


class InspectConfig(InspectModel):
    """The editable ``config`` section (design section 5).

    An omitted key means "no choice": the layers below apply. Which keys were
    written is kept (``model_fields_set``) and drives ``to_scan_layer``.
    """

    structure: StructureConfig = Field(default_factory=StructureConfig)
    # The flatten rules are those of the scan configuration, key for key.
    flatten: FlattenSettings = Field(default_factory=FlattenSettings)
    arrays: ArraysConfig = Field(default_factory=ArraysConfig)
    errors: ErrorsConfig = Field(default_factory=ErrorsConfig)

    def to_scan_layer(self) -> dict[str, Any]:
        """The ``scan`` layer of the keys that are present (design 5.4)."""
        json_layer: dict[str, Any] = {}
        # An undecided path never selects the automatic discovery mode.
        if (
            "structure" in self.model_fields_set
            and "dataset_path" in self.structure.model_fields_set
            and self.structure.dataset_path is not None
        ):
            json_layer["collections"] = [self.structure.dataset_path]
        if "flatten" in self.model_fields_set:
            flatten = {
                name: getattr(self.flatten, name)
                for name in FlattenSettings.model_fields
                if name in self.flatten.model_fields_set
            }
            if flatten:
                json_layer["flatten"] = flatten
        if "arrays" in self.model_fields_set and "mode" in self.arrays.model_fields_set:
            json_layer["arrays"] = {"mode": self.arrays.mode}
        layer: dict[str, Any] = {}
        if json_layer:
            layer["json"] = json_layer
        if "errors" in self.model_fields_set and "policy" in self.errors.model_fields_set:
            layer["errors"] = {"policy": self.errors.policy}
        return layer


# JSON Inspect: detection -------------------------------------------------


class ScopeLimits(InspectModel):
    records: int
    fields: int


class DetectionScope(InspectModel):
    structure: Literal["complete"] = "complete"
    detail: Literal["bounded"] = "bounded"
    limits: ScopeLimits
    # The ``json.discovery_max_depth`` the candidates were searched with: a
    # cached detection is only valid for the same depth (design 12.4).
    discovery_max_depth: int
    candidates: Literal["truncated"] | None = None

    _sparse: ClassVar[tuple[str, ...]] = ("candidates",)


class RootInfo(InspectModel):
    type: NativeName | Literal["lines"]


class Observation(InspectModel):
    records: int
    fields: int
    max_depth: int
    nested_objects: bool
    arrays: bool
    complete: bool


class Candidate(InspectModel):
    path: str
    elements: int
    element_types: dict[str, int]
    eligible: bool
    ineligible_reason: Literal["empty", "non_object_elements"] | None = None
    observation: Observation

    _sparse: ClassVar[tuple[str, ...]] = ("ineligible_reason",)


SelectionBasis = Literal[
    "root_array",
    "jsonl_records",
    "only_eligible_candidate",
    "dominant_candidate",
    "ambiguous",
    "no_eligible_candidate",
    "candidates_truncated",
]


class Selection(InspectModel):
    path: str | None
    basis: SelectionBasis
    over: str | None = None

    _sparse: ClassVar[tuple[str, ...]] = ("over",)


class LineCounts(InspectModel):
    read: int
    blank: int
    objects: int
    invalid: int
    not_object: int


class JsonDetection(InspectModel):
    scope: DetectionScope
    root: RootInfo
    candidates: list[Candidate]
    selection: Selection
    lines: LineCounts | None = None

    _sparse: ClassVar[tuple[str, ...]] = ("lines",)


# Excel Inspect: configuration and detection -----------------------------


class ExcelStructureConfig(InspectModel):
    """Which table to read: a sheet, or a named table of a sheet.

    ``dataset_path`` uses the absolute path syntax with the workbook as root:
    ``$.Sales`` is a sheet, ``$.Sales.Orders`` the table ``Orders`` of that
    sheet, ``$["Q1 2026"]`` a sheet name that is not an identifier.
    ``header_row`` is the 1-based sheet row of the header of a sheet; ``null``
    means the detected one.
    """

    dataset_path: str | None = None
    header_row: Annotated[int, Field(strict=True, ge=1)] | None = None

    @field_validator("dataset_path", mode="before")
    @classmethod
    def sheet_or_table_path(cls, value: object) -> object:
        return canonical_excel_path(value)


class ExcelInspectConfig(InspectModel):
    """The editable ``config`` section of an Excel Inspect file."""

    structure: ExcelStructureConfig = Field(default_factory=ExcelStructureConfig)

    def to_scan_layer(self) -> dict[str, Any]:
        """The ``scan`` layer of the keys that are present (like the JSON kind:
        an undecided ``dataset_path`` selects nothing)."""
        if "structure" not in self.model_fields_set:
            return {}
        excel: dict[str, Any] = {}
        if (
            "dataset_path" in self.structure.model_fields_set
            and self.structure.dataset_path is not None
        ):
            excel["dataset_path"] = self.structure.dataset_path
        if "header_row" in self.structure.model_fields_set:
            excel["header_row"] = self.structure.header_row
        return {"excel": excel} if excel else {}


class ExcelScope(InspectModel):
    structure: Literal["complete"] = "complete"
    # Rows searched, from the first filled row, for the header of a sheet.
    header_scan_rows: int
    candidates: Literal["truncated"] | None = None

    _sparse: ClassVar[tuple[str, ...]] = ("candidates",)


class WorkbookInfo(InspectModel):
    sheets: int
    tables: int


class ExcelObservation(InspectModel):
    columns: int
    # The first header names, in order; ``columns`` is the full count.
    column_names: list[str]
    # Blank rows between the header and the last filled row.
    blank_rows: int
    merged_ranges: int


ExcelIneligibleReason = Literal["no_cells", "no_header", "no_data_rows", "has_tables"]


class ExcelCandidate(InspectModel):
    path: str
    kind: Literal["sheet", "table"]
    sheet: str
    table: str | None = None
    visible: bool
    # A1 range of the header and the data (``A4:H13``); absent without cells.
    range: str | None = None
    # 1-based sheet row of the header.
    header_row: int | None = None
    # Filled data rows.
    elements: int
    eligible: bool
    ineligible_reason: ExcelIneligibleReason | None = None
    observation: ExcelObservation | None = None

    _sparse: ClassVar[tuple[str, ...]] = (
        "table",
        "range",
        "header_row",
        "ineligible_reason",
        "observation",
    )


class ExcelDetection(InspectModel):
    scope: ExcelScope
    workbook: WorkbookInfo
    candidates: list[ExcelCandidate]
    selection: Selection


# Document ----------------------------------------------------------------


class InspectDocument(InspectModel):
    """The whole Inspect file, in the fixed order of design 4.1.

    ``detection`` and ``config`` belong to the kind named by ``inspect.kind``."""

    format: Literal["tabalyst.inspect"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    inspect: InspectInfo
    source: InspectSource
    detection: JsonDetection | ExcelDetection
    warnings: list[InspectWarning]
    config: InspectConfig | ExcelInspectConfig

    @model_validator(mode="before")
    @classmethod
    def _sections_of_the_kind(cls, data: Any) -> Any:
        """Read ``detection`` and ``config`` with the models of the kind, so a
        section never matches the model of another kind."""
        if not isinstance(data, dict):
            return data
        info = data.get("inspect")
        if not isinstance(info, dict) or info.get("kind") != "excel":
            return data
        data = dict(data)
        for key, model in (("detection", ExcelDetection), ("config", ExcelInspectConfig)):
            if isinstance(data.get(key), dict):
                data[key] = model.model_validate(data[key])
        return data

    @model_validator(mode="after")
    def _kind_matches_sections(self) -> InspectDocument:
        excel = self.inspect.kind == "excel"
        if not (
            isinstance(self.detection, ExcelDetection) == excel
            and isinstance(self.config, ExcelInspectConfig) == excel
        ):
            raise ValueError(
                f"detection and config do not belong to inspect.kind "
                f"{self.inspect.kind!r}"
            )
        return self
