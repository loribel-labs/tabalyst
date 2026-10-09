# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Experimental configuration. Later files override earlier settings.

A configuration file has one object per tool: ``scan`` (what Scan measures
and keeps), ``report`` (what the report presents) and, at the top level, the
``csv`` settings of ``tabalyst sample``, the ``output`` settings and the ``deep``
settings of the second pass (``SettingsFile``). The report is built
on Tabalyst Scan, so its analysis settings live in ``scan``, never in
``report`` (``tabalyst.report_config``).
"""

import codecs
import hashlib
import json
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from tabalyst.errors import ConfigurationError

KEPT_PER_COLUMN_MAX = 1000
ROW_SAMPLE_GROUP_MAX = 1000


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


class ValueExamplesSettings(BaseModel):
    """How the report represents the values of a column. The candidates of its
    examples are the ``kept_per_column`` smallest priorities of the scan sample
    (``scan.limits.max_samples``), or a draw seeded by ``scan.random_seed`` when
    the sample has no priorities."""

    model_config = ConfigDict(extra="forbid")

    # Sample values kept per column in the report document. Presentation: it
    # never changes the scan, so a scan is not run again when it changes. The
    # upper bound keeps the report fast: choosing diverse examples compares
    # the candidates pairwise (1,000 candidates took about 28 s on 34 columns).
    kept_per_column: int = Field(default=100, ge=1, le=KEPT_PER_COLUMN_MAX)
    full_distribution_max_distinct: int = Field(default=50, ge=1)
    short_text_max_length: int = Field(default=20, ge=1)
    short_text_percentile: float = Field(default=0.95, gt=0, le=1)
    short_text_result_size: int = Field(default=20, ge=1)
    long_text_result_size: int = Field(default=20, ge=1)
    long_text_truncate_at: int = Field(default=30, ge=1)
    truncation_suffix: str = "..."
    inline_display_size: int = Field(default=3, ge=1)


class StringAnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    very_short_max_length: int = Field(default=5, ge=1)
    short_max_length: int = Field(default=20, ge=1)
    medium_max_length: int = Field(default=50, ge=1)
    long_max_length: int = Field(default=255, ge=1)
    length_distribution_max_length: int = Field(default=50, ge=1)
    examples_per_length: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def length_thresholds_must_increase(self):
        thresholds = [
            self.very_short_max_length,
            self.short_max_length,
            self.medium_max_length,
            self.long_max_length,
        ]
        if any(left >= right for left, right in pairwise(thresholds)):
            raise ValueError("String length thresholds must increase")
        if self.length_distribution_max_length > self.medium_max_length:
            raise ValueError(
                "length_distribution_max_length cannot exceed medium_max_length"
            )
        return self


class RowSampleSettings(BaseModel):
    """Rows of the scan's row sample that the report keeps and shows: the first
    ``start`` rows, the ``middle`` rows of the interior with the smallest
    priorities (an exact subset of the scan's) and the last ``end`` rows. At
    most what the scan kept; presentation, so it never changes the scan."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(default=10, ge=0, le=ROW_SAMPLE_GROUP_MAX)
    middle: int = Field(default=10, ge=0, le=ROW_SAMPLE_GROUP_MAX)
    end: int = Field(default=10, ge=0, le=ROW_SAMPLE_GROUP_MAX)


class PresentationSettings(BaseModel):
    """Report presentation settings: the ``report`` object of configuration
    files."""

    model_config = ConfigDict(extra="forbid")

    string_analysis: StringAnalysisConfig = Field(default_factory=StringAnalysisConfig)
    value_examples: ValueExamplesSettings = Field(
        default_factory=ValueExamplesSettings
    )
    row_sample: RowSampleSettings = Field(default_factory=RowSampleSettings)


class OutputSettings(BaseModel):
    """How Tabalyst writes its documents: the ``output`` object of configuration
    files."""

    model_config = ConfigDict(extra="forbid")

    # Indent the scan and report documents (and write each sample entry on one
    # line) to read them; the default compact form is about 60% smaller.
    json_indent: bool = False


BinStrategy = Literal["linear", "sample_quantile"]
BINS_MIN = 2
BINS_MAX = 1_000


class PearsonSettings(BaseModel):
    """How pairs of numeric columns are explored and which are kept (design
    20.12, REL-04 to REL-06).

    The exploration reads the row sample, never the source. ``max_columns``
    and ``max_work`` (pairs times rows compared) bound its cost: the columns
    beyond them are left out, and the plan says so. ``max_candidates`` pairs at
    most are written in the plan, the best first; ``automatic_pairs`` of them
    at most are chosen without being asked. ``explore_min_pairs`` is the
    smallest number of rows a pair needs in the sample to be scored and
    ``min_pairs`` the smallest number a coefficient over every row needs to be
    defined; the second is part of the key of a result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_columns: int = Field(default=50, ge=2, le=200)
    max_work: int = Field(default=1_000_000, ge=1)
    max_candidates: int = Field(default=20, ge=0, le=1_000)
    automatic_pairs: int = Field(default=8, ge=0, le=1_000)
    explore_min_pairs: int = Field(default=30, ge=4)
    min_pairs: int = Field(default=10, ge=3)


class DeepSettings(BaseModel):
    """What the second pass computes beyond the plan: the number of bins of a
    histogram and where their bounds come from, and how pairs of numeric
    columns are chosen.

    ``linear`` splits the exact range of the Scan into bins of equal width;
    ``sample_quantile`` places the inner bounds at quantiles of the row sample
    (the shape of the occurrences) or, without enough rows, of the bottom-k
    sample (the distinct values), for a very skewed distribution. The outer
    bounds are always the exact minimum and maximum, and the counts per bin
    are exact in both.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    bins: int = Field(default=100, ge=BINS_MIN, le=BINS_MAX)
    bin_strategy: BinStrategy = "linear"
    pearson: PearsonSettings = Field(default_factory=PearsonSettings)

    def sha256(self) -> str:
        """Digest of the settings, for the document that used them."""
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


DeepMode = Literal["auto", "off", "force"]


class DeepSection(DeepSettings):
    """The ``deep`` object of configuration files: the settings of the second
    pass, and ``mode``, which tells ``tabalyst report`` what to do about it.

    ``auto`` (the default) lets the planner decide whether a second pass has a
    benefit and a low cost; ``off`` never runs one, for a script or a CI that must
    read each source once; ``force`` behaves as ``--deep``, with its confirmation.
    The mode only decides whether to plan, so it is not part of the settings a
    second-pass document records (``settings()``) and changing it never makes a
    stored result stale. ``tabalyst scan --deep`` is an explicit request and
    runs whatever the mode.
    """

    mode: DeepMode = "auto"

    def settings(self) -> DeepSettings:
        """What the second pass computes with: the section without its mode."""
        return DeepSettings.model_validate(self.model_dump(exclude={"mode"}))


class SettingsFile(BaseModel):
    """Settings of a configuration file besides its ``scan`` object: ``csv``
    for ``tabalyst sample``, the ``report`` presentation settings, the
    ``output`` settings and the ``deep`` settings of the second pass."""

    model_config = ConfigDict(extra="forbid")

    csv: CsvConfig = Field(default_factory=CsvConfig)
    report: PresentationSettings = Field(default_factory=PresentationSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    deep: DeepSection = Field(default_factory=DeepSection)


# Settings that moved, with their new location. The analysis settings moved to
# the ``scan`` object when the report moved onto Tabalyst Scan (profile revision
# 3; ``preview_rows`` in revision 5, when the preview became part of the scan,
# then lot 5 of the Scan and JSON work, when the first records became the start
# of the row sample);
# the presentation settings moved to the ``report`` object (revision 2 of the
# report document). Specific paths come first: the first match is reported.
MOVED_SETTINGS: dict[tuple[str, ...], str] = {
    ("missing_values",): "scan.values.null_markers and scan.values.missing",
    ("normalization",): "scan.normalization",
    ("date_detection",): "scan.detectors.date",
    ("type_inference",): "scan.types",
    ("enum_detection",): "scan.detectors.enumeration",
    ("value_examples", "candidate_sample_size"): "scan.limits.max_samples",
    ("value_examples", "random_seed"): "scan.random_seed",
    ("preview_rows",): "scan.records.sample.edge and report.row_sample",
    ("string_analysis",): "report.string_analysis",
    ("value_examples",): "report.value_examples",
}


def _moved_setting(document: dict) -> str | None:
    for path, target in MOVED_SETTINGS.items():
        node = document
        for key in path:
            if not isinstance(node, dict) or key not in node:
                break
            node = node[key]
        else:
            reason = (
                "the report is built on Tabalyst Scan and reads its analysis "
                "settings from the scan object"
                if target.startswith("scan.")
                else "the presentation settings of the report are in the "
                "report object"
            )
            return f"{'.'.join(path)} moved to {target}: {reason}"
    return None


def validation_message(exc: ValidationError, section: str | None = None) -> str:
    """First validation error, located by its dotted path in the file."""
    first = exc.errors(include_url=False)[0]
    location = ".".join(
        str(part) for part in ((section,) if section else ()) + tuple(first["loc"])
    )
    message = first["msg"]
    return f"{location}: {message}" if location else message


def merge_settings(base: dict, override: dict) -> dict:
    """Merge configuration layers: objects merge recursively, any other value,
    lists included, replaces the previous one."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_settings(result[key], value)
        else:
            result[key] = value
    return result


def _read_config_file(path: Path) -> dict:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigurationError(f"Cannot read configuration file {path}: {exc}") from exc
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            f"Invalid configuration in {path}: invalid JSON: {exc}"
        ) from exc
    if not isinstance(document, dict):
        raise ConfigurationError(
            f"Invalid configuration in {path}: the file must hold a JSON object"
        )
    return document


def load_config_layers(paths: Iterable[Path]) -> tuple[dict, dict]:
    """Validate each file, then merge the files in order.

    Returns the explicitly set report settings and ``scan`` section. Each file
    is validated completely, whichever command reads it, so a mistake in the
    section of another command is never silently ignored.
    """
    # Imported here: the scan configuration builds on this module.
    from tabalyst.scanner.config import ScanConfig

    report: dict = {}
    scan: dict = {}
    for path in paths:
        document = _read_config_file(path)
        has_scan = "scan" in document
        section = document.pop("scan", None)
        moved = _moved_setting(document)
        if moved:
            raise ConfigurationError(f"Invalid configuration in {path}: {moved}")
        try:
            current = SettingsFile.model_validate(document).model_dump(
                exclude_unset=True
            )
        except ValidationError as exc:
            raise ConfigurationError(
                f"Invalid configuration in {path}: {validation_message(exc)}"
            ) from exc
        report = merge_settings(report, current)
        if not has_scan:
            continue
        try:
            current = ScanConfig.model_validate(section).model_dump(
                exclude_unset=True, by_alias=True
            )
        except ValidationError as exc:
            raise ConfigurationError(
                f"Invalid configuration in {path}: {validation_message(exc, 'scan')}"
            ) from exc
        scan = merge_settings(scan, current)
    return report, scan


def load_config(paths: Iterable[Path]) -> SettingsFile:
    """Load and recursively merge the top-level settings of strict JSON
    configuration files."""
    merged, _ = load_config_layers(paths)
    return settings_from_layer(merged)


def settings_from_layer(merged: dict) -> SettingsFile:
    """The top-level settings of merged configuration layers."""
    try:
        return SettingsFile.model_validate(merged)
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid merged configuration: {validation_message(exc)}"
        ) from exc


def deep_settings(paths: Iterable[Path]) -> DeepSettings:
    """The ``deep`` settings of the configuration files (second pass)."""
    top_level, _ = load_config_layers(paths)
    return settings_from_layer(top_level).deep.settings()


def deep_mode(paths: Iterable[Path]) -> DeepMode:
    """The ``deep.mode`` of the configuration files (``auto`` by default)."""
    top_level, _ = load_config_layers(paths)
    return settings_from_layer(top_level).deep.mode


def json_indent(paths: Iterable[Path]) -> bool:
    """Whether the configuration files ask for indented scan and report
    documents (``output.json_indent``)."""
    top_level, _ = load_config_layers(paths)
    return settings_from_layer(top_level).output.json_indent


def resolve_config(
    paths: Iterable[Path] = (),
    *,
    separator: str | None = None,
    encoding: str | None = None,
) -> SettingsFile:
    """Resolve defaults, files and explicit CSV options of the top-level
    settings (``tabalyst sample``)."""
    settings = load_config(paths).model_dump()
    if separator is not None:
        settings["csv"]["delimiter"] = separator
    if encoding is not None:
        settings["csv"]["encoding"] = encoding
    try:
        return SettingsFile.model_validate(settings)
    except ValidationError as exc:
        raise ConfigurationError(
            f"Invalid configuration: {validation_message(exc)}"
        ) from exc
