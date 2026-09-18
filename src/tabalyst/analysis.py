"""Pure column and dataset analysis. Raw cells are never rewritten."""

import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import combinations, islice

import pandas as pd

from tabalyst.config import AnalysisConfig
from tabalyst.ingestion import CsvDataset
from tabalyst.models import (
    ColumnProfile,
    DatasetProfile,
    DatasetSummary,
    DateBreakdownItem,
    DateFormatCount,
    DateProfile,
    EnumCandidate,
    Issue,
    NormalizationStats,
    NumericStats,
    PreviewRow,
    StringLengthDistribution,
    StringLengthExample,
    StringProfile,
    ValueOccurrence,
    ValueProfile,
)

INTEGER = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
NUMBER = re.compile(
    r"[+-]?(?:(?:0|[1-9][0-9]*)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)
INTERNAL_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\r\n]+")


def percent(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


def value_type(value: str) -> str:
    if value.casefold() in {"true", "false"}:
        return "boolean"
    if INTEGER.fullmatch(value):
        return "integer"
    if NUMBER.fullmatch(value):
        return "number"
    return "text"


def missing_mask(values: pd.Series, config: AnalysisConfig) -> pd.Series:
    return values.str.strip().isin({marker.strip() for marker in config.missing_values})


def normalize_values(
    values: pd.Series, config: AnalysisConfig
) -> tuple[pd.Series, NormalizationStats]:
    """Normalize analysis values while counting each changed cell per operation."""
    normalized = values
    trim_count = 0
    collapse_count = 0
    if config.normalization.trim:
        trimmed = normalized.str.strip()
        trim_count = int((trimmed != normalized).sum())
        normalized = trimmed
    if config.normalization.collapse_internal_whitespace:
        collapsed = normalized.str.replace(
            INTERNAL_HORIZONTAL_WHITESPACE, " ", regex=True
        )
        collapse_count = int((collapsed != normalized).sum())
        normalized = collapsed
    return normalized, NormalizationStats(
        trim_count=trim_count,
        trim_percent=percent(trim_count, len(values)),
        collapse_internal_whitespace_count=collapse_count,
        collapse_internal_whitespace_percent=percent(collapse_count, len(values)),
    )


@dataclass(frozen=True)
class DateValueResult:
    state: str
    order: str | None = None
    separator: str | None = None
    format: str | None = None
    possible_orders: tuple[str, ...] = ()
    possible_formats: tuple[str, ...] = ()
    error: str | None = None


def valid_calendar_date(order: str, first: int, second: int, third: int) -> bool:
    if order == "YMD":
        year, month, day = first, second, third
    elif order == "MDY":
        month, day, year = first, second, third
    else:
        day, month, year = first, second, third
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def date_format_name(
    order: str,
    first: str,
    second: str,
    third: str,
    separator: str,
) -> str:
    """Describe component order, separator and zero-padding explicitly."""
    month = "MM" if len(second if order == "YMD" else first) == 2 else "M"
    if order == "YMD":
        day = "DD" if len(third) == 2 else "D"
        parts = ("YYYY", month, day)
    elif order == "MDY":
        day = "DD" if len(second) == 2 else "D"
        parts = (month, day, "YYYY")
    else:
        day = "DD" if len(first) == 2 else "D"
        month = "MM" if len(second) == 2 else "M"
        parts = (day, month, "YYYY")
    return separator.join(parts)


def classify_date_value(value: str, config: AnalysisConfig) -> DateValueResult:
    """Recognize configured numeric date structures without fuzzy interpretation."""
    settings = config.date_detection
    if not settings.enabled:
        return DateValueResult("not_date")
    separators = "".join(re.escape(separator) for separator in settings.separators)
    match = re.fullmatch(
        rf"(?P<a>\d{{1,4}})(?P<s1>[{separators}])(?P<b>\d{{1,4}})"
        rf"(?P<s2>[{separators}])(?P<c>\d{{1,4}})",
        value,
    )
    if not match:
        return DateValueResult("not_date")
    first_text, second_text, third_text = (
        match.group("a"),
        match.group("b"),
        match.group("c"),
    )
    first, second, third = map(int, (first_text, second_text, third_text))
    separator = match.group("s1")
    year_first = len(first_text) == 4
    year_last = len(third_text) == 4
    if year_first and len(second_text) <= 2 and len(third_text) <= 2:
        possible_orders = ("YMD",)
    elif year_last and len(first_text) <= 2 and len(second_text) <= 2:
        possible_orders = ("MDY", "DMY")
    elif year_first:
        return DateValueResult("invalid", error="invalid_component_width")
    else:
        return DateValueResult("not_date")
    if match.group("s1") != match.group("s2"):
        return DateValueResult("invalid", error="mixed_separators")
    allowed_orders = [order for order in possible_orders if order in settings.orders]
    if not allowed_orders:
        return DateValueResult("invalid", error="unsupported_order")
    valid_orders = tuple(
        order
        for order in allowed_orders
        if valid_calendar_date(order, first, second, third)
    )
    if not valid_orders:
        return DateValueResult("invalid", error="invalid_calendar_date")
    if len(valid_orders) == 1:
        order = valid_orders[0]
        return DateValueResult(
            "valid",
            order=order,
            separator=separator,
            format=date_format_name(
                order, first_text, second_text, third_text, separator
            ),
        )
    return DateValueResult(
        "ambiguous",
        separator=separator,
        possible_orders=valid_orders,
        possible_formats=tuple(
            date_format_name(
                order, first_text, second_text, third_text, separator
            )
            for order in valid_orders
        ),
    )


def build_date_profile(
    frequencies: list[tuple[str, int]], config: AnalysisConfig
) -> tuple[DateProfile | None, set[str]]:
    """Summarize strict date formats and resolve ambiguity only from clear evidence."""
    if not config.date_detection.enabled:
        return None, set()
    classified = {
        value: classify_date_value(value, config) for value, _ in frequencies
    }
    if not any(result.state != "not_date" for result in classified.values()):
        return None, set()

    evidence = Counter()
    for value, count in frequencies:
        result = classified[value]
        if result.state == "valid" and result.order in {"MDY", "DMY"}:
            evidence[result.order] += count
    resolved_order = config.date_detection.ambiguous_order
    resolution_source = "config" if resolved_order else None
    if not resolved_order:
        if evidence["MDY"] and not evidence["DMY"]:
            resolved_order = "MDY"
            resolution_source = "column"
        elif evidence["DMY"] and not evidence["MDY"]:
            resolved_order = "DMY"
            resolution_source = "column"

    valid_values: set[str] = set()
    formats: Counter[tuple[str, str, str]] = Counter()
    ambiguous_formats: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    valid_count = 0
    ambiguous_count = 0
    invalid_count = 0
    not_date_count = 0
    for value, count in frequencies:
        result = classified[value]
        order = result.order
        format_name = result.format
        if (
            result.state == "ambiguous"
            and resolved_order in result.possible_orders
        ):
            order = resolved_order
            format_name = result.possible_formats[
                result.possible_orders.index(str(resolved_order))
            ]
        if result.state == "valid" or order:
            valid_values.add(value)
            valid_count += count
            formats[(str(format_name), str(order), str(result.separator))] += count
        elif result.state == "ambiguous":
            ambiguous_count += count
            ambiguous_formats[
                "Ambiguous: " + " or ".join(result.possible_formats)
            ] += count
        elif result.state == "invalid":
            invalid_count += count
            errors[str(result.error)] += count
        else:
            not_date_count += count

    total = sum(count for _, count in frequencies)
    if valid_count == total:
        status = "valid" if len(formats) == 1 else "multiple_formats"
    elif ambiguous_count == total:
        status = "ambiguous"
    elif invalid_count == total:
        status = "invalid"
    else:
        status = "mixed"
    format_items = [
        DateFormatCount(
            format=format_name,
            order=order,
            separator=separator,
            count=count,
            percent=percent(count, total),
            iso=format_name == "YYYY-MM-DD",
        )
        for (format_name, order, separator), count in sorted(
            formats.items(), key=lambda item: (-item[1], item[0])
        )
    ]
    date_breakdown = [
        DateBreakdownItem(
            label=item.format,
            category="valid",
            count=item.count,
            percent=item.percent,
        )
        for item in format_items
    ]
    date_breakdown.extend(
        DateBreakdownItem(
            label=label,
            category="ambiguous",
            count=count,
            percent=percent(count, total),
        )
        for label, count in ambiguous_formats.items()
    )
    date_breakdown.sort(key=lambda item: (-item.count, item.label))
    breakdown = date_breakdown + [
        DateBreakdownItem(
            label="Invalid date",
            category="invalid",
            count=invalid_count,
            percent=percent(invalid_count, total),
        ),
        DateBreakdownItem(
            label="Not a date",
            category="not_date",
            count=not_date_count,
            percent=percent(not_date_count, total),
        ),
    ]
    return (
        DateProfile(
            status=status,
            valid_count=valid_count,
            ambiguous_count=ambiguous_count,
            invalid_date_count=invalid_count,
            not_date_count=not_date_count,
            resolved_ambiguous_order=resolved_order,
            ambiguous_order_source=resolution_source,
            formats=format_items,
            format_count=len(format_items),
            breakdown=breakdown,
            errors=dict(errors),
        ),
        valid_values,
    )


def infer_column_type(
    counts: Counter[str],
    date_profile: DateProfile | None,
    total: int,
    config: AnalysisConfig,
) -> tuple[str, str | None, float, int | None, float | None]:
    """Infer a dominant type and quantify values outside the accepted family."""
    if not total:
        return "empty", None, 1.0, 0, 0.0
    threshold = config.type_inference.minimum_confidence
    candidates = [
        ("integer", counts["integer"]),
        ("number", counts["integer"] + counts["number"]),
    ]
    for inferred_type, accepted in candidates:
        confidence = accepted / total
        if confidence >= threshold:
            errors = total - accepted
            return inferred_type, None, confidence, errors, percent(errors, total)

    date_accepted = (
        date_profile.valid_count + date_profile.ambiguous_count
        if date_profile
        else 0
    )
    date_confidence = date_accepted / total
    if date_profile and date_confidence >= threshold:
        inferred_type = (
            "date"
            if date_profile.format_count == 1
            and date_profile.ambiguous_count == 0
            else "mixed"
        )
        errors = total - date_profile.valid_count
        return inferred_type, "date", date_confidence, errors, percent(errors, total)

    for inferred_type in ("boolean", "text"):
        accepted = counts[inferred_type]
        confidence = accepted / total
        if confidence >= threshold:
            errors = total - accepted
            return inferred_type, None, confidence, errors, percent(errors, total)

    family_counts = [
        counts["integer"],
        counts["integer"] + counts["number"],
        date_accepted,
        counts["boolean"],
        counts["text"],
    ]
    return "mixed", None, max(family_counts) / total, None, None


def build_string_profile(
    present: pd.Series,
    frequencies: list[tuple[str, int]],
    inferred_type: str,
    config: AnalysisConfig,
) -> StringProfile | None:
    """Summarize text lengths and retain bounded examples for shorter values."""
    if inferred_type != "text" or present.empty:
        return None
    lengths = present.str.len()
    minimum = int(lengths.min())
    maximum = int(lengths.max())
    settings = config.string_analysis
    if maximum <= settings.very_short_max_length:
        status = "very_short"
    elif maximum <= config.string_analysis.short_max_length:
        status = "short"
    elif maximum <= config.string_analysis.medium_max_length:
        status = "medium"
    elif maximum <= config.string_analysis.long_max_length:
        status = "long"
    else:
        status = "very_long"
    distribution = []
    if maximum <= settings.length_distribution_max_length:
        for length in sorted({int(value) for value in lengths}):
            matching = [
                (value, count) for value, count in frequencies if len(value) == length
            ]
            distribution.append(
                StringLengthDistribution(
                    length=length,
                    count=sum(count for _, count in matching),
                    percent=percent(sum(count for _, count in matching), len(present)),
                    distinct_count=len(matching),
                    examples=[
                        StringLengthExample(value=value, count=count)
                        for value, count in matching[: settings.examples_per_length]
                    ],
                )
            )
    return StringProfile(
        status=status,
        present_count=len(present),
        minimum_length=minimum,
        maximum_length=maximum,
        mean_length=round(float(lengths.mean()), 2),
        median_length=round(float(lengths.median()), 2),
        distinct_length_count=int(lengths.nunique()),
        fixed_length=minimum if minimum == maximum else None,
        length_distribution=distribution,
    )


def normalized_edit_distance(left: str, right: str) -> float:
    """Return Levenshtein distance normalized to the longer string."""
    if left == right:
        return 0.0
    if not left or not right:
        return 1.0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1] / max(len(left), len(right))


def select_diverse_values(values: list[str], limit: int) -> list[str]:
    """Select a deterministic farthest-first subset from sampled short strings."""
    if len(values) <= limit:
        return values
    if limit == 1:
        return values[:1]
    distances: dict[tuple[int, int], float] = {}

    def distance(left: int, right: int) -> float:
        pair = (min(left, right), max(left, right))
        if pair not in distances:
            distances[pair] = normalized_edit_distance(values[left], values[right])
        return distances[pair]

    first, second = max(
        combinations(range(len(values)), 2), key=lambda pair: distance(*pair)
    )
    selected = [first, second]
    remaining = set(range(len(values))) - set(selected)
    while len(selected) < limit and remaining:
        next_index = max(
            remaining,
            key=lambda candidate: (
                min(distance(candidate, chosen) for chosen in selected),
                -candidate,
            ),
        )
        selected.append(next_index)
        remaining.remove(next_index)
    return [values[index] for index in selected]


def build_value_profile(
    frequencies: list[tuple[str, int]],
    *,
    inferred_type: str,
    position: int,
    config: AnalysisConfig,
) -> ValueProfile:
    """Build a bounded, reproducible value representation for the global JSON."""
    settings = config.value_examples
    if len(frequencies) <= settings.full_distribution_max_distinct:
        return ValueProfile(
            selection="complete",
            sampled_distinct_count=len(frequencies),
            values=[ValueOccurrence(value=value, count=count) for value, count in frequencies],
        )

    population = sorted(value for value, _ in frequencies)
    sample_size = min(settings.candidate_sample_size, len(population))
    candidates = random.Random(settings.random_seed + position).sample(
        population, sample_size
    )
    counts = dict(frequencies)
    lengths = sorted(len(value) for value in candidates)
    percentile_index = max(
        0, math.ceil(settings.short_text_percentile * len(lengths)) - 1
    )
    short_text = (
        inferred_type == "text"
        and lengths[percentile_index] <= settings.short_text_max_length
    )
    if short_text:
        short_candidates = [
            value
            for value in candidates
            if len(value) <= settings.short_text_max_length
        ]
        selected = select_diverse_values(
            short_candidates, settings.short_text_result_size
        )
        frequent = [
            value for value, _ in frequencies[: settings.inline_display_size]
        ]
        selected = (frequent + [value for value in selected if value not in frequent])[
            : settings.short_text_result_size
        ]
        return ValueProfile(
            selection="diverse_sample",
            sampled_distinct_count=sample_size,
            values=sorted(
                [ValueOccurrence(value=value, count=counts[value]) for value in selected],
                key=lambda item: (-item.count, item.value),
            ),
        )

    selected = candidates[: settings.long_text_result_size]
    frequent = [value for value, _ in frequencies[: settings.inline_display_size]]
    selected = (frequent + [value for value in selected if value not in frequent])[
        : settings.long_text_result_size
    ]
    values = []
    for value in selected:
        truncated = len(value) > settings.long_text_truncate_at
        display = (
            value[: settings.long_text_truncate_at] + settings.truncation_suffix
            if truncated
            else value
        )
        values.append(
            ValueOccurrence(value=display, count=counts[value], truncated=truncated)
        )
    return ValueProfile(
        selection="random_sample",
        sampled_distinct_count=sample_size,
        values=sorted(values, key=lambda item: (-item.count, item.value)),
    )


def infer_enum_candidate(
    present: pd.Series,
    *,
    inferred_type: str,
    row_count: int,
    config: AnalysisConfig,
) -> EnumCandidate | None:
    """Classify low-cardinality text as an enum candidate, not a physical type."""
    settings = config.enum_detection
    if (
        not settings.enabled
        or inferred_type not in settings.eligible_types
        or row_count < settings.minimum_row_count
    ):
        return None
    observed = (
        present.nunique()
        if settings.case_sensitive
        else present.str.casefold().nunique()
    )
    if not 0 < observed <= settings.maximum_distinct_values:
        return None
    coverage = percent(len(present), row_count)
    return EnumCandidate(
        observed_distinct_count=int(observed),
        non_missing_count=len(present),
        coverage_percent=coverage,
        confidence=round(len(present) / row_count, 4) if row_count else 0.0,
    )


def analyze_column(
    values: pd.Series,
    *,
    name: str | None = None,
    position: int = 1,
    config: AnalysisConfig | None = None,
) -> ColumnProfile:
    """Profile one raw string column, also usable independently of CSV ingestion."""
    config = config or AnalysisConfig()
    if not all(isinstance(value, str) for value in values):
        raise ValueError("Column analysis expects raw strings, without null objects.")
    normalized, normalization = normalize_values(values, config)
    absent = missing_mask(normalized, config)
    present = normalized[~absent]
    frequencies = sorted(
        ((str(value), int(count)) for value, count in present.value_counts().items()),
        key=lambda item: (-item[1], item[0]),
    )
    date_profile, valid_date_values = build_date_profile(frequencies, config)
    counts: Counter[str] = Counter()
    for value, count in frequencies:
        counts["date" if value in valid_date_values else value_type(value)] += count
    inferred, semantic_type, type_confidence, type_error_count, type_error_percent = (
        infer_column_type(counts, date_profile, len(present), config)
    )

    numeric = None
    if inferred in {"integer", "number"}:
        accepted_types = {"integer"} if inferred == "integer" else {"integer", "number"}
        numeric_values = present[present.map(lambda value: value_type(value) in accepted_types)]
        numbers = pd.to_numeric(numeric_values, errors="coerce").astype(float)
        stats = [numbers.min(), numbers.max(), numbers.mean(), numbers.median()]
        if numbers.notna().all() and all(math.isfinite(value) for value in stats):
            numeric = NumericStats(
                minimum=stats[0], maximum=stats[1], mean=stats[2], median=stats[3]
            )
    value_profile = build_value_profile(
        frequencies,
        inferred_type=inferred,
        position=position,
        config=config,
    )
    enum = infer_enum_candidate(
        present,
        inferred_type=inferred,
        row_count=len(values),
        config=config,
    )
    if enum and semantic_type is None:
        semantic_type = "enum"
    string_profile = build_string_profile(present, frequencies, inferred, config)
    return ColumnProfile(
        id=f"column_{position}",
        name=name if name is not None else str(values.name or ""),
        position=position,
        inferred_type=inferred,
        type_counts=dict(counts),
        type_confidence=round(type_confidence, 4),
        type_error_count=type_error_count,
        type_error_percent=type_error_percent,
        missing_count=int(absent.sum()),
        missing_percent=percent(int(absent.sum()), len(values)),
        normalization=normalization,
        distinct_count=len(frequencies),
        examples=[
            item.value
            for item in value_profile.values[: config.value_examples.inline_display_size]
        ],
        value_profile=value_profile,
        semantic_type=semantic_type,
        enum=enum,
        date_profile=date_profile,
        string_profile=string_profile,
        numeric=numeric,
    )


def analyze_dataset(dataset: CsvDataset, config: AnalysisConfig) -> DatasetProfile:
    frame = dataset.frame
    columns = [
        analyze_column(frame.iloc[:, i], name=name, position=i + 1, config=config)
        for i, name in enumerate(dataset.headers)
    ]
    absent = frame.apply(lambda values: missing_mask(values, config))
    duplicates = frame.duplicated(keep="first")
    missing_count = sum(column.missing_count for column in columns)
    trim_count = sum(column.normalization.trim_count for column in columns)
    collapse_count = sum(
        column.normalization.collapse_internal_whitespace_count for column in columns
    )
    empty = [column.id for column in columns if column.inferred_type == "empty"]
    constant = [column.id for column in columns if column.distinct_count == 1]
    mixed = [column.id for column in columns if column.inferred_type == "mixed"]
    issues = []

    def add_issue(
        code, message, count, ids=(), rows=(), severity="warning", always=False
    ):
        if count or always:
            issues.append(
                Issue(
                    code=code,
                    severity=severity,
                    message=message,
                    count=count,
                    column_ids=list(ids),
                    row_numbers=list(islice(rows, 10)),
                )
            )

    add_issue(
        "duplicate_rows",
        "Duplicate rows beyond their first occurrence",
        int(duplicates.sum()),
        rows=(i + 1 for i, value in enumerate(duplicates) if value),
    )
    add_issue(
        "missing_values",
        "Missing cells",
        missing_count,
        [c.id for c in columns if c.missing_count],
        (i + 1 for i, value in enumerate(absent.any(axis=1)) if value),
    )
    add_issue("empty_columns", "Columns without any present values", len(empty), empty)
    add_issue(
        "trimmed_cells",
        "Cells changed by trimming surrounding whitespace",
        trim_count,
        [c.id for c in columns if c.normalization.trim_count],
        severity="info",
        always=True,
    )
    add_issue(
        "collapsed_whitespace",
        "Cells changed by collapsing repeated internal whitespace",
        collapse_count,
        [c.id for c in columns if c.normalization.collapse_internal_whitespace_count],
        severity="info",
        always=True,
    )
    add_issue(
        "constant_columns",
        "Columns with one distinct present value",
        len(constant),
        constant,
        severity="info",
    )
    add_issue("mixed_types", "Columns with mixed value types", len(mixed), mixed)
    header_counts = Counter(dataset.headers)
    bad_headers = [
        c.id for c in columns if not c.name.strip() or header_counts[c.name] > 1
    ]
    add_issue(
        "ambiguous_headers",
        "Blank or repeated column names",
        len(bad_headers),
        bad_headers,
    )

    return DatasetProfile(
        generated_at=datetime.now(UTC),
        processing_seconds=0.0,
        source=dataset.source,
        config=config,
        summary=DatasetSummary(
            row_count=len(frame),
            column_count=len(columns),
            cell_count=frame.size,
            missing_count=missing_count,
            missing_percent=percent(missing_count, frame.size),
            trim_count=trim_count,
            collapse_internal_whitespace_count=collapse_count,
            duplicate_row_count=int(duplicates.sum()),
            empty_row_count=int(absent.all(axis=1).sum()),
            empty_column_count=len(empty),
            constant_column_count=len(constant),
        ),
        columns=columns,
        issues=issues,
        preview=[
            PreviewRow(row_number=i + 1, values=list(row))
            for i, row in enumerate(
                frame.head(config.preview_rows).itertuples(index=False, name=None)
            )
        ],
    )
