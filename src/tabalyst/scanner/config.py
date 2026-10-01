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
from tabalyst.scanner.paths import Items, format_absolute, parse_path

HARD_CAPS: dict[str, int] = {
    "max_fields": 1_000_000,
    "max_depth": 1_000,
    "max_record_observations": 100_000_000,
    "max_distinct_per_field": 50_000_000,
    "max_tracked_values": 500_000_000,
    "max_stored_value_length": 1_000_000,
    "max_listed_frequencies": 100_000,
    "max_samples": 10_000,
    "max_variant_groups": 100_000,
    "max_variants_per_group": 10_000,
    "max_evidence_examples": 1_000,
    "max_tracked_records": 500_000_000,
    "max_listed_records": 10_000,
}
MAX_PREVIEW_RECORDS = 1_000
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


SourceFormat = Literal["csv", "json", "jsonl"]
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


class LimitSettings(_Settings):
    max_fields: int = _limit(10_000, "max_fields")
    max_depth: int = _limit(64, "max_depth")
    max_record_observations: int = _limit(100_000, "max_record_observations")
    max_distinct_per_field: int = _limit(100_000, "max_distinct_per_field")
    max_tracked_values: int = _limit(2_000_000, "max_tracked_values")
    max_stored_value_length: int = _limit(1_000, "max_stored_value_length")
    max_listed_frequencies: int = _limit(100, "max_listed_frequencies", 0)
    max_samples: int = _limit(100, "max_samples", 0)
    max_variant_groups: int = _limit(100, "max_variant_groups", 0)
    max_variants_per_group: int = _limit(20, "max_variants_per_group", 0)
    max_evidence_examples: int = _limit(10, "max_evidence_examples", 0)
    max_tracked_records: int = _limit(2_000_000, "max_tracked_records")
    max_listed_records: int = _limit(10, "max_listed_records", 0)

    @model_validator(mode="after")
    def distinct_within_global_budget(self):
        if self.max_distinct_per_field > self.max_tracked_values:
            raise ValueError("max_distinct_per_field cannot exceed max_tracked_values")
        return self


class RecordSettings(_Settings):
    preview: int = Field(default=10, ge=0, le=MAX_PREVIEW_RECORDS)
    duplicates: bool = True


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
    decimal comma, thousands grouped by ``.`` or a space (design 12.10)."""

    enabled: bool = True
    conventions: list[NumberConvention] = Field(
        default_factory=lambda: ["dot", "comma"], min_length=1
    )
    ambiguous_convention: NumberConvention | None = None

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


class ScanConfig(_Settings):
    """Validated scan settings; every section has defaults."""

    csv: CsvConfig = Field(default_factory=CsvConfig)
    json_: JsonSettings = Field(default_factory=JsonSettings, alias="json")
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
    random_seed: int = 42

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
    """
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
