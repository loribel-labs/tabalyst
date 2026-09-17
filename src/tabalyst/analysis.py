"""Pure column and dataset analysis. Raw cells are never rewritten."""

import math
import re
from collections import Counter
from datetime import UTC, date, datetime
from itertools import islice

import pandas as pd

from tabalyst.config import AnalysisConfig
from tabalyst.ingestion import CsvDataset
from tabalyst.models import (
    ColumnProfile,
    DatasetProfile,
    DatasetSummary,
    Issue,
    NumericStats,
    PreviewRow,
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
    counts: Counter[str] = Counter()
    for value, count in present.str.strip().value_counts().items():
        counts[value_type(value)] += int(count)
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
    return ColumnProfile(
        id=f"column_{position}",
        name=name if name is not None else str(values.name or ""),
        position=position,
        inferred_type=inferred,
        type_counts=dict(counts),
        missing_count=int(absent.sum()),
        missing_percent=percent(int(absent.sum()), len(values)),
        distinct_count=int(present.nunique()),
        examples=present.drop_duplicates().head(3).tolist(),
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
