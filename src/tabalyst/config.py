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


class AnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    csv: CsvConfig = Field(default_factory=CsvConfig)
    missing_values: list[str] = Field(default_factory=lambda: [""])
    preview_rows: int = Field(default=10, ge=0, le=100)


def load_config(paths: list[Path]) -> AnalysisConfig:
    merged = {}
    for path in paths:
        current = AnalysisConfig.model_validate_json(
            path.read_text(encoding="utf-8-sig")
        ).model_dump(exclude_unset=True)
        csv_options = {**merged.get("csv", {}), **current.get("csv", {})}
        merged.update(current)
        merged["csv"] = csv_options
    return AnalysisConfig.model_validate(merged)
