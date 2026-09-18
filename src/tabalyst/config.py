"""Experimental configuration. Later files override earlier settings."""

import codecs
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CsvConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    encoding: str = "utf-8-sig"
    delimiter: str = ","

    @field_validator("encoding")
    @classmethod
    def known_encoding(cls, value: str) -> str:
        try:
            codecs.lookup(value)
        except LookupError as exc:
            raise ValueError(f"Unknown encoding: {value}") from exc
        return value

    @field_validator("delimiter")
    @classmethod
    def single_separator(cls, value: str) -> str:
        if len(value) != 1 or value in '\r\n"\0':
            raise ValueError(
                "Delimiter must be one character, excluding quotes/NUL/newlines"
            )
        return value


class ValueExamplesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_distribution_max_distinct: int = Field(default=50, ge=1)
    candidate_sample_size: int = Field(default=100, ge=1)
    short_text_max_length: int = Field(default=20, ge=1)
    short_text_percentile: float = Field(default=0.95, gt=0, le=1)
    short_text_result_size: int = Field(default=20, ge=1)
    long_text_result_size: int = Field(default=20, ge=1)
    long_text_truncate_at: int = Field(default=30, ge=1)
    truncation_suffix: str = "..."
    inline_display_size: int = Field(default=3, ge=1)
    random_seed: int = 42


class NormalizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trim: bool = True
    collapse_internal_whitespace: bool = True


class DateDetectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    orders: list[Literal["YMD", "MDY", "DMY"]] = Field(
        default_factory=lambda: ["YMD", "MDY", "DMY"]
    )
    separators: list[str] = Field(default_factory=lambda: ["-", "/", "."])
    ambiguous_order: Literal["MDY", "DMY"] | None = None

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

    @model_validator(mode="after")
    def ambiguous_order_must_be_enabled(self):
        if self.ambiguous_order and self.ambiguous_order not in self.orders:
            raise ValueError("ambiguous_order must also appear in date orders")
        return self


class TypeInferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_confidence: float = Field(default=0.95, gt=0.5, le=1)


class StringAnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    short_max_length: int = Field(default=30, ge=1)
    long_max_length: int = Field(default=255, ge=1)

    @model_validator(mode="after")
    def length_thresholds_must_increase(self):
        if self.long_max_length <= self.short_max_length:
            raise ValueError("long_max_length must exceed short_max_length")
        return self


class EnumDetectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    minimum_row_count: int = Field(default=500, ge=1)
    maximum_distinct_values: int = Field(default=49, ge=1)
    eligible_types: list[str] = Field(default_factory=lambda: ["text"])
    case_sensitive: bool = True


class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv: CsvConfig = Field(default_factory=CsvConfig)
    missing_values: list[str] = Field(default_factory=lambda: [""])
    preview_rows: int = Field(default=10, ge=0, le=100)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)
    date_detection: DateDetectionConfig = Field(default_factory=DateDetectionConfig)
    type_inference: TypeInferenceConfig = Field(default_factory=TypeInferenceConfig)
    string_analysis: StringAnalysisConfig = Field(default_factory=StringAnalysisConfig)
    value_examples: ValueExamplesConfig = Field(default_factory=ValueExamplesConfig)
    enum_detection: EnumDetectionConfig = Field(default_factory=EnumDetectionConfig)


def load_config(paths: list[Path]) -> AnalysisConfig:
    def merge(base: dict, override: dict) -> dict:
        result = dict(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = value
        return result

    merged = {}
    for path in paths:
        current = AnalysisConfig.model_validate_json(
            path.read_text(encoding="utf-8-sig")
        ).model_dump(exclude_unset=True)
        merged = merge(merged, current)
    return AnalysisConfig.model_validate(merged)
