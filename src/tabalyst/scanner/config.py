# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan configuration: complete schema, defaults, hard caps and fingerprint.

``ScanConfig`` follows design section 15. Hard caps are the protected core
configuration (design section 11): a value above a cap is rejected before any
scan starts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from tabalyst.config import (
    CsvConfig,
    load_config_layers,
    merge_settings,
    validation_message,
)
from tabalyst.errors import ConfigurationError
from tabalyst.scanner.paths import Items, Key, format_absolute, parse_path

HARD_CAPS: dict[str, int] = {
    "max_fields": 1_000_000,
    "max_depth": 1_000,
    "max_record_observations": 100_000_000,
    "max_line_bytes": 268_435_456,
    "max_distinct_per_field": 50_000_000,
    "max_tracked_values": 500_000_000,
    "max_stored_value_length": 1_000_000,
    "max_listed_frequencies": 100_000,
    "max_samples": 100_000,
    "max_long_samples": 10_000,
    "max_samples_per_length": 10_000,
    "max_length_strata": 10_000,
    "long_preview_chars": 1_000_000,
    "max_sample_memory": 1 << 40,
    "max_special_characters": 100_000,
    "max_distinct_characters": 1_114_112,
    "max_top_characters": 1_000,
    "max_variant_groups": 100_000,
    "max_variants_per_group": 10_000,
    "max_evidence_examples": 1_000,
    "max_tracked_records": 500_000_000,
    "max_listed_records": 10_000,
}
MAX_PATTERNS = 200
MAX_PATTERN_LENGTH = 1_000
MAX_PATTERN_INPUT_LENGTH = 10_000
# A streamed field keeps its warm-up values: the warm-up is bounded.
MAX_WARMUP_VALUES = 1_000_000
MAX_PROBE_INTERVAL = 1_000_000

MissingCategory = Literal["absent", "null", "empty", "blank", "marker"]
ScalarType = Literal["string", "integer", "number", "boolean"]


class _Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")


SourceFormat = Literal["csv", "json", "jsonl", "excel"]
ErrorPolicy = Literal["strict", "tolerant"]

# Characters a flatten separator may never be: they are part of the path
# syntax (design inspect section 5.2).
_RESERVED_SEPARATORS = "[]\"\\$_"


class FlattenSettings(_Settings):
    enabled: StrictBool = True
    separator: str = "."
    max_depth: StrictInt | None = Field(default=None, ge=1, le=HARD_CAPS["max_depth"])

    def depth_limit(self) -> int | None:
        """Segments at which a container is kept whole, ``None`` without limit.

        Disabled flatten is a depth of one (design inspect section 7.2).
        """
        return self.max_depth if self.enabled else 1

    @field_validator("separator")
    @classmethod
    def usable_separator(cls, value: str) -> str:
        if (
            len(value) != 1
            or value.isalnum()
            or value.isspace()
            or not value.isprintable()
            or value in _RESERVED_SEPARATORS
        ):
            raise ValueError(
                "The flatten separator must be one character that is not a "
                f"letter, digit, whitespace or one of {_RESERVED_SEPARATORS}: "
                f"{value!r}"
            )
        return value


class ArraySettings(_Settings):
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


class JsonSettings(_Settings):
    collections: list[str] | None = None
    discovery_max_depth: int = Field(default=3, ge=0, le=HARD_CAPS["max_depth"])
    flatten: FlattenSettings = Field(default_factory=FlattenSettings)
    arrays: ArraySettings = Field(default_factory=ArraySettings)

    @field_validator("collections")
    @classmethod
    def absolute_paths(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        if not values:
            raise ValueError(
                "Collection paths cannot be an empty list; use null for automatic "
                "discovery"
            )
        paths: dict[tuple, str] = {}
        canonical: list[str] = []
        for value in values:
            if not value.startswith("$"):
                raise ValueError(f"Collection paths must be absolute: {value!r}")
            path = parse_path(value)
            if not path or not isinstance(path[-1], Items):
                raise ValueError(
                    f"Collection paths must select array elements with '[]': {value!r}"
                )
            if path in paths:
                raise ValueError(
                    f"Collection paths must be unique: {paths[path]!r} and {value!r}"
                )
            paths[path] = value
            # Equal paths in other spellings hash equally (design inspect 10.3).
            canonical.append(format_absolute(path))
        # Overlapping selections would put one record in two datasets.
        for path, value in paths.items():
            for other, other_value in paths.items():
                if len(other) > len(path) and other[: len(path)] == path:
                    raise ValueError(
                        f"Collection paths cannot overlap: {value!r} contains "
                        f"{other_value!r}"
                    )
        return canonical


def json_collection_paths(values: Sequence[str] | None) -> list[str] | None:
    """The ``--collection`` values that are JSON collection paths (absolute,
    ending in ``[]``), ``None`` when there are none. A value naming a sheet or
    a table (``$.Sales``) belongs to a workbook, which reads it itself; the
    configuration of the other sources must not choke on it."""
    kept = []
    for value in values or ():
        try:
            path = parse_path(value) if value.startswith("$") else ()
        except ValueError:
            continue
        if path and isinstance(path[-1], Items):
            kept.append(value)
    return kept or None


def canonical_excel_path(value: object) -> str | None:
    """A sheet (``$.Sales``) or a table of a sheet (``$.Sales.Orders``) in its
    canonical spelling; the workbook is the root. Raises ``ValueError``."""
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
    if not 1 <= len(path) <= 2 or not all(isinstance(seg, Key) for seg in path):
        raise ValueError(
            "dataset_path must name a sheet ($.Sheet) or a table of a sheet "
            f"($.Sheet.Table): {value!r}"
        )
    return format_absolute(path)


class ExcelSettings(_Settings):
    """The table read from an Excel workbook: a sheet or a named table, and the
    1-based sheet row of the header of a sheet (``null``: detected)."""

    dataset_path: str | None = None
    header_row: StrictInt | None = Field(default=None, ge=1)

    @field_validator("dataset_path", mode="before")
    @classmethod
    def sheet_or_table(cls, value: object) -> object:
        return canonical_excel_path(value)


class ErrorSettings(_Settings):
    # ``None`` is the default of the source format (``resolve_config_defaults``).
    policy: ErrorPolicy | None = None
    max_locations: int = Field(default=10, ge=0, le=10_000)


class ValueSettings(_Settings):
    null_markers: list[str] = Field(default_factory=list)
    null_markers_case_sensitive: bool = True
    missing: list[MissingCategory] = Field(
        default_factory=lambda: ["absent", "null", "empty", "blank", "marker"]
    )

    @field_validator("null_markers")
    @classmethod
    def comparable_markers(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or value.strip() != value:
                raise ValueError(
                    "Null markers must be non-empty, without surrounding whitespace: "
                    f"{value!r}"
                )
        return values

    @field_validator("missing")
    @classmethod
    def unique_categories(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Missing categories must be unique")
        return values


class NormalizationSettings(_Settings):
    nfc: bool = True
    trim: bool = True
    collapse_whitespace: bool = True
    casefold: bool = True
    strip_accents: bool = True


def _limit(default: int, name: str, minimum: int = 1):
    return Field(default=default, ge=minimum, le=HARD_CAPS[name])


DEFAULT_MAX_SAMPLES = 10_000
# Long texts (design 18.6): at most 100 per field, previewed on 200 characters.
DEFAULT_MAX_LONG_SAMPLES = 100
DEFAULT_LONG_PREVIEW_CHARS = 200
# Samples by length (design 18.7): up to 64 lengths of 100 values each.
DEFAULT_MAX_SAMPLES_PER_LENGTH = 100
DEFAULT_MAX_LENGTH_STRATA = 64
# The model of the bytes the samples of the whole scan may take (design 18.10).
DEFAULT_MAX_SAMPLE_MEMORY = 512 << 20


class LimitSettings(_Settings):
    max_fields: int = _limit(10_000, "max_fields")
    max_depth: int = _limit(64, "max_depth")
    max_record_observations: int = _limit(100_000, "max_record_observations")
    # Largest JSONL line parsed (16 MiB by default; design inspect section 15).
    max_line_bytes: int = _limit(16_777_216, "max_line_bytes")
    max_distinct_per_field: int = _limit(100_000, "max_distinct_per_field")
    max_tracked_values: int = _limit(2_000_000, "max_tracked_values")
    max_stored_value_length: int = _limit(1_000, "max_stored_value_length")
    max_listed_frequencies: int = _limit(100, "max_listed_frequencies", 0)
    # K, the size of the sample kept per field. Left unset it follows T when T
    # is lower than the default (design 18.2).
    max_samples: int = _limit(DEFAULT_MAX_SAMPLES, "max_samples", 0)
    # Long texts (values above max_stored_value_length) keep a small sample of
    # previews and digests (design 18.6).
    max_long_samples: int = _limit(
        DEFAULT_MAX_LONG_SAMPLES, "max_long_samples", 0
    )
    long_preview_chars: int = _limit(
        DEFAULT_LONG_PREVIEW_CHARS, "long_preview_chars"
    )
    # Samples by length (design 18.7): the values kept for each tracked length
    # (0 turns the samples by length off) and the lengths tracked per field.
    max_samples_per_length: int = _limit(
        DEFAULT_MAX_SAMPLES_PER_LENGTH, "max_samples_per_length", 0
    )
    max_length_strata: int = _limit(
        DEFAULT_MAX_LENGTH_STRATA, "max_length_strata", 0
    )
    # Bytes, by the model of design 18.10, that the samples of the whole scan
    # may reserve; the long texts share a part of it.
    max_sample_memory: int = _limit(
        DEFAULT_MAX_SAMPLE_MEMORY, "max_sample_memory"
    )
    # Tables of characters (design 9.2): the special characters listed and the
    # distinct characters counted exactly per field.
    max_special_characters: int = _limit(256, "max_special_characters", 0)
    max_distinct_characters: int = _limit(1_024, "max_distinct_characters")
    # The most frequent characters and emoji the character map lists (design
    # 9.2b); 0 turns the map off.
    max_top_characters: int = _limit(20, "max_top_characters", 0)
    max_variant_groups: int = _limit(100, "max_variant_groups", 0)
    max_variants_per_group: int = _limit(20, "max_variants_per_group", 0)
    max_evidence_examples: int = _limit(10, "max_evidence_examples", 0)
    max_tracked_records: int = _limit(2_000_000, "max_tracked_records")
    max_listed_records: int = _limit(10, "max_listed_records", 0)

    @model_validator(mode="after")
    def distinct_within_global_budget(self):
        if self.max_distinct_per_field > self.max_tracked_values:
            raise ValueError("max_distinct_per_field cannot exceed max_tracked_values")
        if self.max_samples > self.max_distinct_per_field:
            if "max_samples" in self.model_fields_set:
                raise ValueError("max_samples cannot exceed max_distinct_per_field")
            # The sample is drawn from the exact table: a lower tracking limit
            # lowers the default sample size with it.
            self.max_samples = self.max_distinct_per_field
        return self


MAX_ROW_SAMPLE_ROWS = 100_000
MAX_ROW_SAMPLE_CELL_CHARS = 100_000


class RowSampleSettings(_Settings):
    """Row sample of a dataset (design 18.11): ``edge`` first rows, ``edge`` last
    rows and a bottom-k of the interior, ``rows`` in all; 0 rows turns it off.

    ``max_bytes`` is the budget, in bytes of a cost model, of the cells kept by
    the whole scan.
    """

    rows: int = Field(default=1_000, ge=0, le=MAX_ROW_SAMPLE_ROWS)
    edge: int = Field(default=50, ge=0, le=MAX_ROW_SAMPLE_ROWS // 2)
    cell_chars: int = Field(default=200, ge=1, le=MAX_ROW_SAMPLE_CELL_CHARS)
    max_bytes: int = Field(default=16 << 20, ge=1 << 20, le=1 << 40)

    @model_validator(mode="after")
    def edges_fit_in_the_sample(self):
        if self.rows and 2 * self.edge > self.rows:
            raise ValueError("2 * edge cannot exceed rows")
        return self


class RecordSettings(_Settings):
    duplicates: bool = True
    sample: RowSampleSettings = Field(default_factory=RowSampleSettings)

    @model_validator(mode="before")
    @classmethod
    def preview_moved_to_the_row_sample(cls, data):
        # The first records are the start of the row sample since lot 5.
        if isinstance(data, dict) and "preview" in data:
            raise ValueError(
                "preview moved to scan.records.sample.edge (rows kept by the "
                "scan) and report.row_sample (rows the report shows)"
            )
        return data


MAX_INFERRED_PATTERNS = 1_024
# The most distinct values one field's discovery can be set to read (design 18.12).
MAX_PATTERN_VALUES = 20_000
MAX_PATTERN_VALUE_LENGTH = 1_000


class PatternInferenceSettings(_Settings):
    """Discovery of structural patterns from the samples (design 18.12).

    The discovery reads the samples of the finished scan, never the source.
    ``max_values`` bounds the distinct values a field's discovery reads,
    ``max_families`` the families it publishes, ``max_patterns_per_family`` the
    patterns of one family, ``max_patterns`` the patterns and nodes of a field
    and ``max_depth`` the levels of the tree below a family (the pattern is the
    first). ``max_value_length`` bounds the stored values that take part (longer
    ones are counted as excluded) and ``min_distinct`` the distinct values a
    field needs to be assessed.
    """

    enabled: bool = True
    max_values: int = Field(default=10_000, ge=1, le=MAX_PATTERN_VALUES)
    max_families: int = Field(default=16, ge=1, le=MAX_INFERRED_PATTERNS)
    max_patterns_per_family: int = Field(default=32, ge=1, le=MAX_INFERRED_PATTERNS)
    max_patterns: int = Field(default=128, ge=1, le=MAX_INFERRED_PATTERNS)
    max_depth: int = Field(default=3, ge=1, le=4)
    max_value_length: int = Field(default=64, ge=1, le=MAX_PATTERN_VALUE_LENGTH)
    min_distinct: int = Field(default=2, ge=1, le=1_000)


MAX_OBSERVATION_ITEMS = 100_000


class ObservationSettings(_Settings):
    """Observations, quality issues and limits derived from the finished scan
    (design 18.13). ``max_items`` bounds the observations and, separately, the
    limits that are listed; the summaries count them all."""

    enabled: bool = True
    max_items: int = Field(default=1_000, ge=1, le=MAX_OBSERVATION_ITEMS)


class TypeSettings(_Settings):
    minimum_confidence: float = Field(default=0.95, gt=0.5, le=1)


class DetectionSettings(_Settings):
    minimum_share: float = Field(default=0.95, gt=0, le=1)
    # Adaptive detection (design 13): 0 keeps detection exhaustive.
    warmup_values: int = Field(default=10_000, ge=0, le=MAX_WARMUP_VALUES)
    probe_interval: int = Field(default=100, ge=0, le=MAX_PROBE_INTERVAL)
    # Detectors that reacted to at most this share of the warm-up values are
    # skipped too; 0 skips only those that reacted to none.
    rare_share: float = Field(default=0.001, ge=0, le=1)


NumberConvention = Literal["dot", "comma"]
MonthLanguage = Literal["en", "fr"]


class NumberSettings(_Settings):
    """``dot``: decimal point, thousands grouped by ``,`` or a space; ``comma``:
    decimal comma, thousands grouped by ``.`` or a space (design 12.10).

    ``infer_convention`` (on by default) reads the ambiguous numbers, such as
    ``1,234``, in the convention the unambiguous numbers of the column prove, at
    least ``min_evidence`` of them and none proving the other (design 20.27);
    ``ambiguous_convention`` always wins. ``detectors.number`` applies them in the
    Scan; the amount detectors (``currency``, ``percentage``, ``quantity``)
    inherit them, but the Scan counts no number of an amount, so they change
    nothing there: the second pass applies them to the numbers of the values
    with a unit (design 20.28)."""

    enabled: bool = True
    conventions: list[NumberConvention] = Field(
        default_factory=lambda: ["dot", "comma"], min_length=1
    )
    ambiguous_convention: NumberConvention | None = None
    infer_convention: bool = True
    min_evidence: int = Field(default=3, ge=1)

    @field_validator("conventions")
    @classmethod
    def unique_conventions(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Number conventions must be unique")
        return values

    @model_validator(mode="after")
    def ambiguous_convention_must_be_enabled(self):
        if (
            self.ambiguous_convention
            and self.ambiguous_convention not in self.conventions
        ):
            raise ValueError("ambiguous_convention must also appear in conventions")
        return self


class DateSettings(_Settings):
    enabled: bool = True
    orders: list[Literal["YMD", "MDY", "DMY"]] = Field(
        default_factory=lambda: ["YMD", "MDY", "DMY"]
    )
    separators: list[str] = Field(default_factory=lambda: ["-", "/", "."])
    ambiguous_order: Literal["MDY", "DMY"] | None = None
    month_languages: list[MonthLanguage] = Field(
        default_factory=lambda: ["en", "fr"]
    )

    @field_validator("separators")
    @classmethod
    def valid_separators(cls, values: list[str]) -> list[str]:
        if not values or any(
            len(value) != 1 or value.isdigit() or value in "\r\n" for value in values
        ):
            raise ValueError("Date separators must be non-digit single characters")
        if len(set(values)) != len(values):
            raise ValueError("Date separators must be unique")
        return values

    @field_validator("month_languages")
    @classmethod
    def unique_languages(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Month languages must be unique")
        return values

    @model_validator(mode="after")
    def ambiguous_order_must_be_enabled(self):
        if self.ambiguous_order and self.ambiguous_order not in self.orders:
            raise ValueError("ambiguous_order must also appear in date orders")
        return self


class BooleanSettings(_Settings):
    enabled: bool = True
    pairs: list[tuple[str, str]] = Field(
        default_factory=lambda: [
            ("true", "false"),
            ("yes", "no"),
            ("y", "n"),
            ("oui", "non"),
            ("vrai", "faux"),
        ]
    )

    @field_validator("pairs")
    @classmethod
    def distinct_words(cls, values: list[tuple[str, str]]) -> list[tuple[str, str]]:
        words = [word for pair in values for word in pair]
        for word in words:
            if not word or word.strip() != word:
                raise ValueError(
                    "Boolean words must be non-empty, without surrounding "
                    f"whitespace: {word!r}"
                )
        if len({word.casefold() for word in words}) != len(words):
            raise ValueError("Boolean words must be unique, ignoring case")
        return values


class EnumerationSettings(_Settings):
    enabled: bool = True
    minimum_values: int = Field(default=500, ge=1)
    maximum_distinct: int = Field(default=49, ge=1, le=10_000)
    case_sensitive: bool = True


class EmailSettings(_Settings):
    enabled: bool = True
    max_tracked_domains: int = Field(default=10_000, ge=1, le=1_000_000)
    max_listed_domains: int = Field(default=20, ge=0, le=10_000)


class UrlSettings(_Settings):
    enabled: bool = True
    schemes: list[str] = Field(default_factory=lambda: ["http", "https", "ftp"])
    www: bool = True
    max_tracked_hosts: int = Field(default=10_000, ge=1, le=1_000_000)
    max_listed_hosts: int = Field(default=20, ge=0, le=10_000)

    @field_validator("schemes")
    @classmethod
    def letter_schemes(cls, values: list[str]) -> list[str]:
        for value in values:
            if re.fullmatch(r"[a-z]+", value) is None:
                raise ValueError(
                    f"URL schemes must be lowercase ASCII letters: {value!r}"
                )
        if len(set(values)) != len(values):
            raise ValueError("URL schemes must be unique")
        return values


PhoneRegion = Literal["nanp", "fr"]


class PhoneSettings(_Settings):
    """``nanp``: Canada, the United States and the other NANP countries;
    ``fr``: France."""

    enabled: bool = True
    regions: list[PhoneRegion] = Field(
        default_factory=lambda: ["nanp", "fr"], min_length=1
    )

    @field_validator("regions")
    @classmethod
    def unique_regions(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Phone regions must be unique")
        return values


PostalRegion = Literal["ca", "us"]


class PostalCodeSettings(_Settings):
    """``ca``: Canadian postal codes; ``us``: United States ZIP codes."""

    enabled: bool = True
    regions: list[PostalRegion] = Field(
        default_factory=lambda: ["ca", "us"], min_length=1
    )

    @field_validator("regions")
    @classmethod
    def unique_regions(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Postal code regions must be unique")
        return values


class CurrencySettings(NumberSettings):
    """Conventions of the number part of amounts, set independently of
    ``detectors.number``."""


class PercentageSettings(NumberSettings):
    """Conventions of the number part of percentages, set independently of
    ``detectors.number``."""


class QuantitySettings(NumberSettings):
    """Conventions of the number part of quantities, set independently of
    ``detectors.number``, and the counted units of ``details``."""

    max_tracked_units: int = Field(default=10_000, ge=1, le=1_000_000)
    max_listed_units: int = Field(default=20, ge=0, le=10_000)


class UuidSettings(_Settings):
    enabled: bool = True


IpVersion = Literal["ipv4", "ipv6"]


class IpAddressSettings(_Settings):
    enabled: bool = True
    versions: list[IpVersion] = Field(
        default_factory=lambda: ["ipv4", "ipv6"], min_length=1
    )

    @field_validator("versions")
    @classmethod
    def unique_versions(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("IP address versions must be unique")
        return values


class DetectorSettings(_Settings):
    number: NumberSettings = Field(default_factory=NumberSettings)
    date: DateSettings = Field(default_factory=DateSettings)
    boolean: BooleanSettings = Field(default_factory=BooleanSettings)
    enumeration: EnumerationSettings = Field(default_factory=EnumerationSettings)
    email: EmailSettings = Field(default_factory=EmailSettings)
    url: UrlSettings = Field(default_factory=UrlSettings)
    phone: PhoneSettings = Field(default_factory=PhoneSettings)
    postal_code: PostalCodeSettings = Field(default_factory=PostalCodeSettings)
    currency: CurrencySettings = Field(default_factory=CurrencySettings)
    percentage: PercentageSettings = Field(default_factory=PercentageSettings)
    quantity: QuantitySettings = Field(default_factory=QuantitySettings)
    uuid: UuidSettings = Field(default_factory=UuidSettings)
    ip_address: IpAddressSettings = Field(default_factory=IpAddressSettings)


class PatternSettings(_Settings):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    regex: str = Field(min_length=1, max_length=MAX_PATTERN_LENGTH)
    description: str | None = None
    accepts: list[ScalarType] = Field(default_factory=lambda: ["string"], min_length=1)
    sensitive: bool = False
    max_input_length: int = Field(default=256, ge=1, le=MAX_PATTERN_INPUT_LENGTH)

    @field_validator("regex")
    @classmethod
    def compilable(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"Invalid regular expression: {exc}") from exc
        return value

    @field_validator("accepts")
    @classmethod
    def unique_types(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("Accepted types must be unique")
        return values


class ExposureSettings(_Settings):
    sensitive_values: Literal["mask", "hide", "show"] = "mask"
    # ``aggregate`` publishes the declared keys of the detectors (extension and
    # domain, area code, postal area) on a masked or hidden field too; ``mask``
    # brings the masking back (Patterns DEC-027).
    detector_keys: Literal["aggregate", "mask"] = "aggregate"


class ScanConfig(_Settings):
    """Validated scan settings; every section has defaults."""

    csv: CsvConfig = Field(default_factory=CsvConfig)
    json_: JsonSettings = Field(default_factory=JsonSettings, alias="json")
    excel: ExcelSettings = Field(default_factory=ExcelSettings)
    errors: ErrorSettings = Field(default_factory=ErrorSettings)
    values: ValueSettings = Field(default_factory=ValueSettings)
    normalization: NormalizationSettings = Field(default_factory=NormalizationSettings)
    limits: LimitSettings = Field(default_factory=LimitSettings)
    records: RecordSettings = Field(default_factory=RecordSettings)
    types: TypeSettings = Field(default_factory=TypeSettings)
    detection: DetectionSettings = Field(default_factory=DetectionSettings)
    detectors: DetectorSettings = Field(default_factory=DetectorSettings)
    patterns: list[PatternSettings] = Field(
        default_factory=list, max_length=MAX_PATTERNS
    )
    exposure: ExposureSettings = Field(default_factory=ExposureSettings)
    pattern_inference: PatternInferenceSettings = Field(
        default_factory=PatternInferenceSettings
    )
    observations: ObservationSettings = Field(default_factory=ObservationSettings)
    # The seed of the bottom-k hash (design 18.3) is an unsigned 64-bit integer.
    random_seed: int = Field(default=42, ge=0, lt=2**64)

    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)

    @field_validator("patterns")
    @classmethod
    def unique_pattern_ids(cls, values: list[PatternSettings]) -> list[PatternSettings]:
        ids = [pattern.id for pattern in values]
        if len(set(ids)) != len(ids):
            raise ValueError("Pattern identifiers must be unique")
        return values


def exact_share(threshold: float) -> Fraction:
    """The decimal value of a share threshold: ``Fraction(0.1)`` is above one
    tenth in binary, so an exact 10% would miss it."""
    return Fraction(str(threshold))


def resolve_config_defaults(config: ScanConfig, source_format: SourceFormat) -> ScanConfig:
    """The configuration a scan of ``source_format`` really applies.

    ``errors.policy`` is never ``None`` in the result: ``tolerant`` for JSONL,
    ``strict`` for CSV and JSON. Flatten settings that change nothing while
    flatten is disabled are normalized, so equal rules hash equally
    (design inspect 5.5, 5.6). Resolving twice gives the same configuration.
    A JSONL source has one dataset, ``$[]``: another collection path is a
    configuration error (design inspect 9.1).
    """
    if source_format == "jsonl" and config.json_.collections not in (None, ["$[]"]):
        raise ConfigurationError(
            "A JSONL source has one dataset, '$[]'; json.collections must be null "
            f"or ['$[]'], not {config.json_.collections}"
        )
    policy = config.errors.policy
    if policy is None:
        policy = "tolerant" if source_format == "jsonl" else "strict"
    flatten = config.json_.flatten
    if not flatten.enabled:
        flatten = FlattenSettings(enabled=False)
    return config.model_copy(
        update={
            "errors": config.errors.model_copy(update={"policy": policy}),
            "json_": config.json_.model_copy(update={"flatten": flatten}),
        }
    )


def config_sha256(config: ScanConfig) -> str:
    """SHA-256 of the canonical JSON: sorted keys, no whitespace, UTF-8.

    Of the configuration as given: hash the result of ``resolve_config_defaults``
    to identify the rules a scan applies."""
    canonical = json.dumps(
        config.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_scan_config(
    paths: Iterable[Path] = (),
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
) -> ScanConfig:
    """Resolve the configuration layers of a scan (design section 15).

    From lowest to highest priority: built-in defaults, the ``scan`` section
    of each configuration file in order, then explicit options. Hard caps are
    enforced by validation. Objects merge; lists, such as ``collections``,
    replace.
    """
    _, settings = load_config_layers(paths)
    return scan_config_from_layer(
        settings, delimiter=delimiter, encoding=encoding, collections=collections
    )


def scan_config_from_layer(
    settings: dict,
    *,
    delimiter: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
) -> ScanConfig:
    """The scan configuration of merged ``scan`` settings plus explicit
    options (``resolve_scan_config`` without reading files)."""
    options: dict = {}
    if delimiter is not None:
        options.setdefault("csv", {})["delimiter"] = delimiter
    if encoding is not None:
        options.setdefault("csv", {})["encoding"] = encoding
    if collections:
        options["json"] = {"collections": list(collections)}
    try:
        return ScanConfig.model_validate(merge_settings(settings, options))
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid scan configuration: {validation_message(exc, 'scan')}"
        ) from exc
