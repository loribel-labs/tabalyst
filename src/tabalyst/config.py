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
from datetime import date
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
# Fewest bins per column that a grid of ranks can use.
RANK_BINS_MIN = 4
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
    defined. ``rank_bins`` is the number of bins per column of the grid the
    Spearman coefficient is read from (0 turns it off, and the exploration stops
    rating pairs by rank too); ``min_pairs`` and ``rank_bins`` are part of the
    key of a result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_columns: int = Field(default=50, ge=2, le=200)
    max_work: int = Field(default=1_000_000, ge=1)
    max_candidates: int = Field(default=20, ge=0, le=1_000)
    automatic_pairs: int = Field(default=8, ge=0, le=1_000)
    explore_min_pairs: int = Field(default=30, ge=4)
    min_pairs: int = Field(default=10, ge=3)
    rank_bins: int = Field(default=64, ge=0, le=1_024)

    @field_validator("rank_bins")
    @classmethod
    def _rank_bins_usable(cls, value: int) -> int:
        if 0 < value < RANK_BINS_MIN:
            raise ValueError(f"rank_bins is 0 (off) or at least {RANK_BINS_MIN}")
        return value


class CrosstabSettings(BaseModel):
    """How tables of a category against a feature of another column are explored
    and computed (design 20.13, REL-01 to REL-03, REL-11 to REL-16).

    A table has at most ``max_categories`` category rows (the most frequent
    values, the rest is ``other``) and at most ``max_classes`` class columns,
    ``other`` included for the lengths, the prefixes and the values; a column with more than
    ``max_distinct`` distinct values is not a category. ``prefix_length`` is the
    number of characters of a prefix. ``examples`` exceptions are kept per cell
    and ``max_exception_cells`` cells at most are listed as exceptions (the
    result says whether that was all of them).
    A category whose dominant class takes ``rule_purity`` percent of at least
    ``rule_support`` classified rows gives a candidate rule. The exploration
    reads the row sample, never the source: ``max_columns`` and ``max_work``
    (tables times rows coded) bound its cost, ``max_candidates`` tables at most
    are written in the plan and ``automatic_tables`` of them at most are chosen
    without being asked. ``explore_min_rows`` is the smallest number of rows a
    table needs in the sample to be scored.

    Everything that changes a result is part of the key of that result; the
    budgets of the exploration are not.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_categories: int = Field(default=30, ge=2, le=200)
    max_classes: int = Field(default=12, ge=3, le=50)
    max_distinct: int = Field(default=100, ge=2, le=1_000)
    prefix_length: int = Field(default=2, ge=1, le=8)
    examples: int = Field(default=3, ge=0, le=10)
    max_exception_cells: int = Field(default=20, ge=1, le=1_000)
    rule_purity: int = Field(default=90, ge=50, le=100)
    rule_support: int = Field(default=30, ge=1)
    max_columns: int = Field(default=50, ge=2, le=200)
    max_work: int = Field(default=1_000_000, ge=1)
    max_candidates: int = Field(default=20, ge=0, le=1_000)
    automatic_tables: int = Field(default=8, ge=0, le=1_000)
    explore_min_rows: int = Field(default=30, ge=4)


class StatsSettings(BaseModel):
    """How the numbers of a column are described by category (design 20.23).

    A table has at most ``max_categories`` category rows (the most frequent
    values, the rest is ``other``) and a column with more than ``max_distinct``
    distinct values is not a category. Every category gets the same ``bins``
    bins, placed as ``deep.bin_strategy`` says. The exploration reads the row
    sample, never the source: ``max_columns`` and ``max_work`` (analyses times
    rows compared) bound its cost, ``max_candidates`` analyses at most are
    written in the plan and ``automatic_stats`` of them at most are chosen
    without being asked. ``explore_min_rows`` is the smallest number of rows an
    analysis needs in the sample to be scored.

    ``max_categories`` and ``bins`` are part of the key of a result; the
    budgets of the exploration are not.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_categories: int = Field(default=30, ge=2, le=200)
    max_distinct: int = Field(default=100, ge=2, le=1_000)
    bins: int = Field(default=50, ge=BINS_MIN, le=BINS_MAX)
    max_columns: int = Field(default=50, ge=2, le=200)
    max_work: int = Field(default=1_000_000, ge=1)
    max_candidates: int = Field(default=20, ge=0, le=1_000)
    automatic_stats: int = Field(default=8, ge=0, le=1_000)
    explore_min_rows: int = Field(default=30, ge=4)


class MeasureSettings(BaseModel):
    """How the values with a unit, a currency marker or a percent sign are
    extracted (design 20.19).

    ``max_groups`` markers or units at most get metrics of their own, the most
    frequent first; the others are summed up in ``other``. ``max_values``
    distinct pairs of a marker and a number are counted exactly; beyond, every
    group goes on in bins whose width is a power of two, with exact counts and
    moments and estimated quantiles. Both are part of the key of a result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_groups: int = Field(default=20, ge=1, le=1_000)
    max_values: int = Field(default=100_000, ge=1, le=10_000_000)


class ShapeSettings(BaseModel):
    """How the shape of the numbers of a column is described (design 20.24).

    ``max_values`` distinct numbers are counted exactly in a table, which gives
    exact quantiles and exact counts of outliers; beyond, the numbers go on in
    bins whose width is a power of two, with estimated quantiles and counts of
    outliers that have certain bounds. It is part of the key of a result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_values: int = Field(default=100_000, ge=1, le=10_000_000)


class DatetimeSettings(BaseModel):
    """How the parts of the dates of a column are counted (design 20.25).

    ``as_of`` is a calendar date (``YYYY-MM-DD``) after which the dates are
    counted; it is never the date of the day, so that a result does not change
    with the clock, and without it nothing is counted. ``infer_order`` (on by
    default) reads the ambiguous dates, such as ``03/04/2020``, in the order that
    the unambiguous dates of the column give when they all give the same one
    (day-month, or month-day), and counts them with the others; off, or with both
    orders present, they stay ambiguous and are not placed. ``min_evidence`` is
    the fewest unambiguous dates that must prove the order (3 by default; below
    it the dates stay ambiguous). An order given by
    ``detectors.date.ambiguous_order`` always wins. They are part of the key of a
    result, and ``infer_order`` and ``min_evidence`` also of the distribution
    over time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    as_of: str | None = None
    infer_order: bool = True
    min_evidence: int = Field(default=3, ge=1)

    @field_validator("as_of")
    @classmethod
    def _calendar_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as exc:
            raise ValueError("as_of must be a calendar date, YYYY-MM-DD") from exc


class ResidualSettings(BaseModel):
    """What the values that a pattern or a detector leaves out are kept as
    (design 20.20).

    ``max_listed`` values are listed per source and state, the most frequent
    first; ``max_tracked`` distinct values at most are counted per source and
    state (beyond, the occurrences of new values are only counted); a value of
    more than ``max_value_length`` characters is counted and never listed;
    ``max_detectors`` detectors at most are replayed per field. ``records``
    asks for the first record of each value even when the Scan already holds
    every distinct value, which makes the second pass read the source. All are
    part of the key of a result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_listed: int = Field(default=20, ge=1, le=1_000)
    max_tracked: int = Field(default=10_000, ge=1, le=1_000_000)
    max_value_length: int = Field(default=100, ge=1, le=10_000)
    max_detectors: int = Field(default=3, ge=1, le=20)
    records: bool = False


class DuplicateSettings(BaseModel):
    """How the repeated values of an identifier or of a key are reported
    (design 20.21).

    ``max_listed`` repeated values are listed, the most repeated first;
    ``max_tracked`` distinct repeated values at most are counted (beyond, the
    occurrences of new ones are only counted). ``records`` asks for the first
    record of each value even when the Scan already holds every distinct value,
    which makes the second pass read the source. All are part of the key of a
    result.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_listed: int = Field(default=20, ge=1, le=1_000)
    max_tracked: int = Field(default=10_000, ge=1, le=1_000_000)
    records: bool = False


class DeepSettings(BaseModel):
    """What the second pass computes beyond the plan: the number of bins of a
    histogram and where their bounds come from, how pairs of numeric columns,
    tables of categories and numbers by category are chosen, how values with a
    unit are extracted, and how residual and repeated values are kept.

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
    crosstab: CrosstabSettings = Field(default_factory=CrosstabSettings)
    stats: StatsSettings = Field(default_factory=StatsSettings)
    measures: MeasureSettings = Field(default_factory=MeasureSettings)
    shape: ShapeSettings = Field(default_factory=ShapeSettings)
    datetime: DatetimeSettings = Field(default_factory=DatetimeSettings)
    residuals: ResidualSettings = Field(default_factory=ResidualSettings)
    duplicates: DuplicateSettings = Field(default_factory=DuplicateSettings)

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


class SmartBaseWeights(BaseModel):
    """The base weight of each kind of target (design 20.15). A weight grows
    with its base and with the rarity of what the target stands for, up to
    ``SmartWeights.cap``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirmed_issue: float = Field(default=10.0, ge=0)
    candidate_anomaly: float = Field(default=6.0, ge=0)
    value: float = Field(default=5.0, ge=0)
    relation_exception: float = Field(default=5.0, ge=0)
    pattern: float = Field(default=4.0, ge=0)
    extreme: float = Field(default=4.0, ge=0)
    signal: float = Field(default=3.0, ge=0)
    bin: float = Field(default=2.0, ge=0)


class SmartWeights(BaseModel):
    """The weight of a target: ``min(cap, base * (1 + gain * rarity))``, where
    ``rarity`` goes from 0 (the target covers every row) to 1 (it covers a share
    of ``floor`` rows or less) and is ``unknown_rarity`` when the frequency of
    the target is not known. Monotone in the share and in the base."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base: SmartBaseWeights = Field(default_factory=SmartBaseWeights)
    gain: float = Field(default=1.0, ge=0)
    floor: float = Field(default=1e-6, gt=0, lt=1)
    cap: float = Field(default=20.0, gt=0)
    unknown_rarity: float = Field(default=0.5, ge=0, le=1)


class SmartSettings(BaseModel):
    """How the plan of a smart sample defines its targets (design 20.15).

    A column of at most ``max_enum_values`` distinct values gets one target per
    value; a numeric column is cut into ``numeric_bins`` bins of equal width
    between its minimum and maximum. The plan keeps ``candidates_per_target`` rows
    per target in memory at most, in ``max_candidate_bytes`` bytes, and
    ``reserve_share`` of the rows asked for are a reserve of ordinary rows. At
    most ``max_targets`` targets are kept, the heaviest first.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_enum_values: int = Field(default=100, ge=1, le=10_000)
    numeric_bins: int = Field(default=10, ge=2, le=100)
    candidates_per_target: int = Field(default=2, ge=1, le=3)
    reserve_share: float = Field(default=0.2, ge=0, le=0.9)
    max_targets: int = Field(default=10_000, ge=1, le=1_000_000)
    max_candidate_bytes: int = Field(default=64 * 1024 * 1024, ge=1)
    weights: SmartWeights = Field(default_factory=SmartWeights)

    def sha256(self) -> str:
        """Digest of the settings, for the plan that used them."""
        canonical = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SettingsFile(BaseModel):
    """Settings of a configuration file besides its ``scan`` object: ``csv``
    for ``tabalyst sample``, the ``report`` presentation settings, the
    ``output`` settings, the ``deep`` settings of the second pass and the
    ``smart`` settings of the plan of a smart sample."""

    model_config = ConfigDict(extra="forbid")

    csv: CsvConfig = Field(default_factory=CsvConfig)
    report: PresentationSettings = Field(default_factory=PresentationSettings)
    output: OutputSettings = Field(default_factory=OutputSettings)
    deep: DeepSection = Field(default_factory=DeepSection)
    smart: SmartSettings = Field(default_factory=SmartSettings)


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


def smart_settings(paths: Iterable[Path]) -> SmartSettings:
    """The ``smart`` settings of the configuration files (plan of a smart sample)."""
    top_level, _ = load_config_layers(paths)
    return settings_from_layer(top_level).smart


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
