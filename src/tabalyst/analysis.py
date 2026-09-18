"""Pure column and dataset analysis. Raw cells are never rewritten."""

import math
import random
import re
from collections import Counter
from datetime import UTC, date, datetime
from itertools import combinations, islice

import pandas as pd

from tabalyst.config import AnalysisConfig
from tabalyst.ingestion import CsvDataset
from tabalyst.models import (
    ColumnProfile,
    DatasetProfile,
    DatasetSummary,
    EnumCandidate,
    Issue,
    NumericStats,
    PreviewRow,
    ValueOccurrence,
    ValueProfile,
)

INTEGER = re.compile(r"[+-]?(?:0|[1-9][0-9]*)")
NUMBER = re.compile(
    r"[+-]?(?:(?:0|[1-9][0-9]*)(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)
ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def percent(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


def value_type(value: str) -> str:
    if value.casefold() in {"true", "false"}:
        return "boolean"
    if INTEGER.fullmatch(value):
        return "integer"
    if NUMBER.fullmatch(value):
        return "number"
    if ISO_DATE.fullmatch(value):
        try:
            date.fromisoformat(value)
            return "date"
        except ValueError:
            pass
    return "text"


def missing_mask(values: pd.Series, config: AnalysisConfig) -> pd.Series:
    return values.str.strip().isin({marker.strip() for marker in config.missing_values})


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
    absent = missing_mask(values, config)
    present = values[~absent]
    frequencies = sorted(
        ((str(value), int(count)) for value, count in present.value_counts().items()),
        key=lambda item: (-item[1], item[0]),
    )
    counts: Counter[str] = Counter()
    for value, count in frequencies:
        counts[value_type(value.strip())] += count
    kinds = set(counts)
    if not kinds:
        inferred = "empty"
    elif kinds <= {"integer", "number"}:
        inferred = "number" if "number" in kinds else "integer"
    else:
        inferred = next(iter(kinds)) if len(kinds) == 1 else "mixed"

    numeric = None
    if inferred in {"integer", "number"}:
        numbers = pd.to_numeric(present.str.strip(), errors="coerce").astype(float)
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
    return ColumnProfile(
        id=f"column_{position}",
        name=name if name is not None else str(values.name or ""),
        position=position,
        inferred_type=inferred,
        type_counts=dict(counts),
        missing_count=int(absent.sum()),
        missing_percent=percent(int(absent.sum()), len(values)),
        distinct_count=len(frequencies),
        examples=[
            item.value
            for item in value_profile.values[: config.value_examples.inline_display_size]
        ],
        value_profile=value_profile,
        semantic_type="enum" if enum else None,
        enum=enum,
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
    empty = [column.id for column in columns if column.inferred_type == "empty"]
    constant = [column.id for column in columns if column.distinct_count == 1]
    mixed = [column.id for column in columns if column.inferred_type == "mixed"]
    issues = []

    def add_issue(code, message, count, ids=(), rows=(), severity="warning"):
        if count:
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
        "missing_values",
        "Missing cells",
        missing_count,
        [c.id for c in columns if c.missing_count],
        (i + 1 for i, value in enumerate(absent.any(axis=1)) if value),
    )
    add_issue(
        "duplicate_rows",
        "Duplicate rows beyond their first occurrence",
        int(duplicates.sum()),
        rows=(i + 1 for i, value in enumerate(duplicates) if value),
    )
    add_issue("empty_columns", "Columns without any present values", len(empty), empty)
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
        source=dataset.source,
        config=config,
        summary=DatasetSummary(
            row_count=len(frame),
            column_count=len(columns),
            cell_count=frame.size,
            missing_count=missing_count,
            missing_percent=percent(missing_count, frame.size),
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
