"""Scan configuration: complete schema, defaults, hard caps and fingerprint.

``ScanConfig`` follows design section 15. Hard caps are the protected core
configuration (design section 11): a value above a cap is rejected before any
scan starts.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tabalyst.config import CsvConfig, DateDetectionConfig
from tabalyst.scanner.paths import Items, parse_path

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
}
MAX_PATTERNS = 200
MAX_PATTERN_LENGTH = 1_000
MAX_PATTERN_INPUT_LENGTH = 10_000

MissingCategory = Literal["absent", "null", "empty", "blank", "marker"]
ScalarType = Literal["string", "integer", "number", "boolean"]


class _Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JsonSettings(_Settings):
    collections: list[str] | None = None
    discovery_max_depth: int = Field(default=3, ge=0, le=HARD_CAPS["max_depth"])

    @field_validator("collections")
    @classmethod
    def absolute_paths(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        for value in values:
            if not value.startswith("$"):
                raise ValueError(f"Collection paths must be absolute: {value!r}")
            path = parse_path(value)
            if not path or not isinstance(path[-1], Items):
                raise ValueError(
                    f"Collection paths must select array elements with '[]': {value!r}"
                )
        if len(set(values)) != len(values):
            raise ValueError("Collection paths must be unique")
        return values


class ErrorSettings(_Settings):
    policy: Literal["strict", "tolerant"] = "strict"
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

    @model_validator(mode="after")
    def distinct_within_global_budget(self):
        if self.max_distinct_per_field > self.max_tracked_values:
            raise ValueError("max_distinct_per_field cannot exceed max_tracked_values")
        return self


class TypeSettings(_Settings):
    minimum_confidence: float = Field(default=0.95, gt=0.5, le=1)


class DetectionSettings(_Settings):
    minimum_share: float = Field(default=0.95, gt=0, le=1)


class DetectorSettings(_Settings):
    date: DateDetectionConfig = Field(default_factory=DateDetectionConfig)


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


def config_sha256(config: ScanConfig) -> str:
    """SHA-256 of the canonical JSON: sorted keys, no whitespace, UTF-8."""
    canonical = json.dumps(
        config.model_dump(mode="json", by_alias=True),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
