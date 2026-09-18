"""Experimental configuration. Later files override earlier settings."""

import codecs
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
