"""Report profile built from a Tabalyst Scan result (profile revision 3).

The scan analyzes the columns. ``RowFacts`` collects, in the same pass, the
record-level facts a scan does not keep: the preview, duplicate rows, empty
rows and rows with missing values. ``build_profile`` turns both into the
profile that ``reporting.py`` renders. No pandas and no file access here.

The report presents the scan: it never resolves an ambiguity the scan left
open (design 12.6). Ambiguous dates stay ambiguous, with the evidence of the
column shown beside them.
"""

import hashlib
import math
import random
import re
from collections import Counter
from datetime import UTC, datetime
from itertools import combinations, islice

from tabalyst.errors import ConfigurationError
from tabalyst.models import (
    ColumnProfile,
    DatasetDateColumnSummary,
    DatasetDateSummary,
    DatasetProfile,
    DatasetSummary,
    DateBreakdownItem,
    DateFormatCount,
    DateProfile,
    DetectorFormat,
    DetectorProfile,
    Issue,
    NormalizationStats,
    NumericStats,
    PreviewRow,
    ReportProfile,
    SourceInfo,
    StringLengthDistribution,
    StringLengthExample,
    StringProfile,
    ValueOccurrence,
    ValueProfile,
)
from tabalyst.report_config import ReportConfig
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.engine import has_limited_measure
from tabalyst.scanner.exposure import mask
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.models import (
    ColumnSegment,
    DatasetResult,
    DetectorComplete,
    DetectorFailed,
    FieldResult,
    KeySegment,
    ScanResult,
    ValueCount,
)
from tabalyst.scanner.observations import Record
from tabalyst.scanner.paths import ITEMS, Column, FieldPath, Key

# Row numbers listed by an issue.
LISTED_ROWS = 10
# Diagnostics of records excluded under the tolerant error policy.
EXCLUSION_CODES = frozenset(
    {"csv_width_mismatch", "record_too_large", "json_duplicate_key"}
)
CONTAINER_TYPES = frozenset({"object", "array"})
# Separator of the values an items path takes in one record of the preview.
PREVIEW_SEPARATOR = ", "
# Stages whose output is the analytical value (design section 10).
ANALYTICAL_STAGES = ("nfc", "trim", "collapse_whitespace")
# Interpretations that repeat the technical type.
TECHNICAL_INTERPRETATIONS = frozenset({"number", "boolean"})
DATE_ORDERS = frozenset({"YMD", "MDY", "DMY"})
NUMERIC_DATE_FORMAT = re.compile(
    r"(?P<a>YYYY|MM?|DD?)(?P<s>[^A-Za-z0-9])(?P<b>MM?|DD?)(?P=s)(?P<c>YYYY|DD?)"
)


def percent(count: int, total: int) -> float:
    return round(100 * count / total, 2) if total else 0.0


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


# Record-level facts ---------------------------------------------------------


class DatasetRows:
    """Record-level facts of one dataset, collected while the scan reads it.

    Values are the scalar observations of a record: every cell of a CSV row,
    every string, number, boolean or null of a JSON record. They are missing
    under the scan's definition (``scan.values``); a JSON field absent from a
    record is not a value of that record. Duplicate records compare every
    observation through a 128-bit BLAKE2b digest of the record, one digest per
    distinct record; lot 5c bounds this state with a budget.
    """

    __slots__ = (
        "_facts",
        "_seen",
        "duplicate_count",
        "duplicate_rows",
        "empty_row_count",
        "preview",
        "rows_with_missing",
    )

    def __init__(self, facts: "RowFacts") -> None:
        self._facts = facts
        self._seen: set[bytes] = set()
        # Observed scalar values of the first records, per path.
        self.preview: list[tuple[int, dict[FieldPath, list[tuple[str, str]]]]] = []
        self.duplicate_count = 0
        self.duplicate_rows: list[int] = []
        self.rows_with_missing: list[int] = []
        self.empty_row_count = 0

    def add(self, record: Record) -> None:
        facts = self._facts
        index = record.index
        values: dict[FieldPath, list[tuple[str, str]]] = {}
        missing = scalars = 0
        for observation in record.observations:
            native = observation.type
            if native in CONTAINER_TYPES:
                continue
            if native == "null":
                text = "null"
                missing += facts.null_missing
            elif native == "string":
                text = observation.value
                missing += facts.is_missing(text)
            else:
                text = canonical_text(native, observation.value)
            scalars += 1
            values.setdefault(observation.path, []).append((native, text))
        if len(self.preview) < facts.preview_rows:
            self.preview.append((index, values))
        if missing:
            if len(self.rows_with_missing) < LISTED_ROWS:
                self.rows_with_missing.append(index)
            if missing == scalars:
                self.empty_row_count += 1
        key = [(observation.path, observation.type, observation.value)
               for observation in record.observations]
        digest = hashlib.blake2b(
            repr(key).encode("utf-8", "surrogatepass"), digest_size=16
        ).digest()
        if digest in self._seen:
            self.duplicate_count += 1
            if len(self.duplicate_rows) < LISTED_ROWS:
                self.duplicate_rows.append(index)
        else:
            self._seen.add(digest)


class RowFacts:
    """Record-level facts of every dataset, collected while the scan reads.

    Pass an instance as the ``on_record`` callback of ``scan()``; the facts of
    a dataset are ``rows.datasets[dataset_id]``.
    """

    __slots__ = (
        "_blank_missing",
        "_empty_missing",
        "_marker_missing",
        "_strings",
        "datasets",
        "null_missing",
        "preview_rows",
    )

    def __init__(self, config: ScanConfig, preview_rows: int) -> None:
        values = config.values
        self._strings = StringClassifier(
            values.null_markers, values.null_markers_case_sensitive
        )
        self._empty_missing = "empty" in values.missing
        self._blank_missing = "blank" in values.missing
        self._marker_missing = "marker" in values.missing
        self.null_missing = "null" in values.missing
        self.preview_rows = preview_rows
        self.datasets: dict[str, DatasetRows] = {}

    def category(self, value: str) -> str:
        """The string category of design section 7."""
        if not value:
            return "empty"
        if value.isspace():
            return "blank"
        if self._strings.has_markers and self._strings.is_marker(value):
            return "marker"
        return "content"

    def is_missing(self, value: str) -> bool:
        if not value:
            return self._empty_missing
        if value.isspace():
            return self._blank_missing
        return (
            self._marker_missing
            and self._strings.has_markers
            and self._strings.is_marker(value)
        )

    def __call__(self, record: Record) -> None:
        rows = self.datasets.get(record.dataset)
        if rows is None:
            rows = self.datasets[record.dataset] = DatasetRows(self)
        rows.add(record)


# Columns --------------------------------------------------------------------


def _date_detector(field: FieldResult) -> DetectorComplete | None:
    for detector in field.detectors:
        if detector.id == "date" and isinstance(detector, DetectorComplete):
            return detector
    return None


def _date_format(format_name: str, count: int, total: int) -> DateFormatCount:
    match = NUMERIC_DATE_FORMAT.fullmatch(format_name)
    order = separator = None
    if match:
        order = "".join(match.group(part)[0] for part in "abc")
        if order in DATE_ORDERS:
            separator = match.group("s")
        else:
            order = None
    return DateFormatCount(
        format=format_name,
        order=order,
        separator=separator,
        count=count,
        percent=percent(count, total),
        iso=format_name == "YYYY-MM-DD",
    )


def build_date_profile(field: FieldResult) -> DateProfile | None:
    """Date formats of the scan's date detector, ambiguity kept unresolved."""
    detector = _date_detector(field)
    if detector is None:
        return None
    coverage = detector.coverage
    if not (coverage.matched or coverage.ambiguous or coverage.invalid):
        return None
    total = coverage.eligible
    valid = coverage.matched
    ambiguous = coverage.ambiguous
    invalid = coverage.invalid
    not_date = coverage.not_matched + coverage.not_tested
    ambiguity = detector.details.get("ambiguity") or {}
    resolution = ambiguity.get("resolution")

    formats = [_date_format(item.format, item.count, total) for item in detector.formats]
    breakdown = [
        DateBreakdownItem(
            label=item.format,
            category="valid",
            count=item.count,
            percent=item.percent,
        )
        for item in formats
    ]
    if ambiguous:
        # Candidates count resolved values too; without a resolution, every
        # ambiguous value is unresolved (design 12.6).
        breakdown.extend(
            DateBreakdownItem(
                label="Ambiguous: " + " or ".join(candidate["formats"]),
                category="ambiguous",
                count=candidate["count"],
                percent=percent(candidate["count"], total),
            )
            for candidate in ambiguity.get("candidates", [])
        )
    breakdown.sort(key=lambda item: (-item.count, item.label))
    breakdown += [
        DateBreakdownItem(
            label="Invalid date",
            category="invalid",
            count=invalid,
            percent=percent(invalid, total),
        ),
        DateBreakdownItem(
            label="Not a date",
            category="not_date",
            count=not_date,
            percent=percent(not_date, total),
        ),
    ]
    if valid == total:
        status = "valid" if len(formats) == 1 else "multiple_formats"
    elif ambiguous == total:
        status = "ambiguous"
    elif invalid == total:
        status = "invalid"
    else:
        status = "mixed"
    return DateProfile(
        status=status,
        present_count=total,
        valid_count=valid,
        valid_percent=percent(valid, total),
        ambiguous_count=ambiguous,
        ambiguous_percent=percent(ambiguous, total),
        invalid_date_count=invalid,
        invalid_date_percent=percent(invalid, total),
        not_date_count=not_date,
        not_date_percent=percent(not_date, total),
        resolved_ambiguous_order=resolution["order"] if resolution else None,
        ambiguous_order_source=resolution["source"] if resolution else None,
        ambiguity_evidence=dict(ambiguity.get("evidence", {})),
        formats=formats,
        format_count=len(formats),
        breakdown=breakdown,
    )


def _distinct_count(field: FieldResult) -> int | None:
    """Distinct analytical values; raw counts, even for a masked column."""
    measure = field.values.cardinality
    for stage in field.normalization.stages:
        if stage.stage in ANALYTICAL_STAGES and stage.enabled:
            measure = stage.cardinality
    if measure.status == "complete":
        return measure.value
    return 0 if measure.status == "not_applicable" else None


def _listed_values(field: FieldResult) -> tuple[list[ValueCount], bool]:
    """Listed frequencies and whether they are every analytical value."""
    frequencies = field.values.frequencies
    if frequencies.status == "not_applicable":
        return [], True
    if frequencies.status != "complete":
        return [], False
    return frequencies.value.listed, not frequencies.value.truncated


def build_value_profile(
    field: FieldResult,
    *,
    inferred_type: str,
    position: int,
    config: ReportConfig,
) -> ValueProfile:
    """Bounded, reproducible value representation.

    Every value when the listing is complete and short enough; otherwise a
    selection among the scan samples, which are a uniform sample of the
    distinct values drawn with ``scan.random_seed``.
    """
    settings = config.value_examples
    listed, complete = _listed_values(field)
    if complete and len(listed) <= settings.full_distribution_max_distinct:
        return ValueProfile(
            selection="complete",
            sampled_distinct_count=len(listed),
            values=[
                ValueOccurrence(value=item.value, count=item.count) for item in listed
            ],
        )

    counts = {item.value: item.count for item in field.values.samples.listed}
    population = sorted(counts)
    counts.update((item.value, item.count) for item in listed)
    candidates = random.Random(config.scan.random_seed + position).sample(
        population, len(population)
    )
    frequent_items = listed or sorted(
        field.values.samples.listed, key=lambda item: (-item.count, item.value)
    )
    frequent = [item.value for item in frequent_items[: settings.inline_display_size]]
    lengths = sorted(len(value) for value in candidates)
    percentile_index = max(
        0, math.ceil(settings.short_text_percentile * len(lengths)) - 1
    )
    short_text = (
        inferred_type == "text"
        and bool(lengths)
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
        selected = (frequent + [value for value in selected if value not in frequent])[
            : settings.short_text_result_size
        ]
        return ValueProfile(
            selection="diverse_sample",
            sampled_distinct_count=len(population),
            values=sorted(
                [ValueOccurrence(value=value, count=counts[value]) for value in selected],
                key=lambda item: (-item.count, item.value),
            ),
        )

    selected = candidates[: settings.long_text_result_size]
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
        sampled_distinct_count=len(population),
        values=sorted(values, key=lambda item: (-item.count, item.value)),
    )


def build_string_profile(
    field: FieldResult, inferred_type: str, config: ReportConfig
) -> StringProfile | None:
    """Length classes and exact length counts; examples per length come from
    the listed frequencies, then the samples."""
    measure = field.string_lengths
    if inferred_type != "text" or measure.status != "complete" or not measure.value.count:
        return None
    lengths = measure.value
    settings = config.string_analysis
    maximum = lengths.max_length
    if maximum <= settings.very_short_max_length:
        status = "very_short"
    elif maximum <= settings.short_max_length:
        status = "short"
    elif maximum <= settings.medium_max_length:
        status = "medium"
    elif maximum <= settings.long_max_length:
        status = "long"
    else:
        status = "very_long"
    distribution = []
    if maximum <= settings.length_distribution_max_length:
        listed, _ = _listed_values(field)
        pool = {item.value: item.count for item in listed}
        for item in sorted(
            field.values.samples.listed, key=lambda item: (-item.count, item.value)
        ):
            pool.setdefault(item.value, item.count)
        examples: dict[int, list[StringLengthExample]] = {}
        for value, count in pool.items():
            bucket = examples.setdefault(len(value), [])
            if len(bucket) < settings.examples_per_length:
                bucket.append(StringLengthExample(value=value, count=count))
        highest = max(item.count for item in lengths.length_histogram)
        distribution = [
            StringLengthDistribution(
                length=item.length,
                count=item.count,
                percent=percent(item.count, lengths.count),
                relative_percent=percent(item.count, highest),
                examples=examples.get(item.length, []),
            )
            for item in lengths.length_histogram
        ]
    return StringProfile(
        status=status,
        present_count=lengths.count,
        minimum_length=lengths.min_length,
        maximum_length=maximum,
        mean_length=round(float(lengths.mean_length), 2),
        median_length=round(float(lengths.median_length), 2),
        distinct_length_count=len(lengths.length_histogram),
        fixed_length=maximum if lengths.min_length == maximum else None,
        length_distribution=distribution,
        representative_examples=[
            item.examples[0].value
            for item in sorted(distribution, key=lambda item: -item.count)[:3]
            if item.examples
        ],
    )


def build_numeric(field: FieldResult, inferred_type: str) -> NumericStats | None:
    """Exact scan statistics as floats, for numeric columns."""
    if inferred_type not in {"integer", "number"} or field.numeric.status != "complete":
        return None
    stats = field.numeric.value
    median = stats.median
    values = [float(stats.min), float(stats.max), float(stats.mean)]
    values.append(values[1] - values[0])
    if median.status == "complete":
        values.append(float(median.value))
    if not all(math.isfinite(value) for value in values):
        return None
    return NumericStats(
        minimum=values[0],
        maximum=values[1],
        range=values[3],
        mean=values[2],
        median=values[4] if median.status == "complete" else None,
    )


def semantic_type(field: FieldResult) -> str | None:
    """``date`` for date columns, else the primary interpretation of the scan
    when it adds to the technical type."""
    if field.technical_type.type == "date":
        return "date"
    primary = field.interpretations.primary
    return None if primary in TECHNICAL_INTERPRETATIONS else primary


def _stage_changes(field: FieldResult, name: str) -> int:
    for stage in field.normalization.stages:
        if stage.stage == name:
            return stage.changed or 0
    return 0


def build_detectors(field: FieldResult) -> list[DetectorProfile]:
    """Detectors that recognized values of the field, and failed ones."""
    detectors = []
    primary = field.interpretations.primary
    for detector in field.detectors:
        if isinstance(detector, DetectorFailed):
            detectors.append(
                DetectorProfile(
                    id=detector.id,
                    status="failed",
                    primary=False,
                    eligible_count=0,
                    matched_count=0,
                    matched_percent=0.0,
                    ambiguous_count=0,
                    invalid_count=0,
                    formats=[],
                )
            )
            continue
        if not isinstance(detector, DetectorComplete):
            continue
        coverage = detector.coverage
        if not (coverage.matched or coverage.ambiguous or coverage.invalid):
            continue
        detectors.append(
            DetectorProfile(
                id=detector.id,
                status="complete",
                primary=detector.id == primary,
                eligible_count=coverage.eligible,
                matched_count=coverage.matched,
                matched_percent=percent(coverage.matched, coverage.eligible),
                ambiguous_count=coverage.ambiguous,
                invalid_count=coverage.invalid,
                formats=[
                    DetectorFormat(
                        format=item.format,
                        count=item.count,
                        percent=percent(item.count, coverage.eligible),
                    )
                    for item in detector.formats
                ],
            )
        )
    return detectors


def value_slots(field: FieldResult) -> int:
    """Places the field could hold a value: its occurrences, plus the parents
    where an object member is absent. The row count for CSV columns."""
    return field.occurrences + (field.presence.absent or 0)


def build_column(
    field: FieldResult, *, position: int, name: str, config: ReportConfig
) -> ColumnProfile:
    row_count = value_slots(field)
    technical = field.technical_type
    inferred = technical.type
    date_profile = build_date_profile(field)
    value_profile = build_value_profile(
        field, inferred_type=inferred, position=position, config=config
    )
    trim = _stage_changes(field, "trim")
    collapse = _stage_changes(field, "collapse_whitespace")
    missing = field.missing.count
    outside = technical.outside_count
    return ColumnProfile(
        id=field.id,
        name=name,
        path=field.display,
        position=position,
        inferred_type=inferred,
        type_counts=dict(technical.counts),
        type_confidence=technical.confidence,
        type_error_count=outside,
        type_error_percent=(
            None if outside is None else percent(outside, field.values.count)
        ),
        missing_count=missing,
        missing_percent=percent(missing, row_count),
        with_issues=(
            missing > 0
            or inferred == "mixed"
            or bool(date_profile and date_profile.ambiguous_count)
        ),
        normalization=NormalizationStats(
            trim_count=trim,
            trim_percent=percent(trim, row_count),
            collapse_internal_whitespace_count=collapse,
            collapse_internal_whitespace_percent=percent(collapse, row_count),
        ),
        distinct_count=_distinct_count(field),
        examples=[
            item.value
            for item in value_profile.values[: config.value_examples.inline_display_size]
        ],
        value_profile=value_profile,
        semantic_type=semantic_type(field),
        exposure=field.exposure,
        date_profile=date_profile,
        string_profile=build_string_profile(field, inferred, config),
        numeric=build_numeric(field, inferred),
        detectors=build_detectors(field),
    )


def _field_path(field: FieldResult) -> FieldPath:
    """The observation path of a scan field."""
    path: list = []
    for segment in field.path:
        if isinstance(segment, KeySegment):
            path.append(Key(segment.key))
        elif isinstance(segment, ColumnSegment):
            path.append(Column(segment.column))
        else:
            path.append(ITEMS)
    return tuple(path)


def _preview(
    rows: DatasetRows, fields: list[FieldResult], facts: RowFacts
) -> list[PreviewRow]:
    """Raw preview rows; values of sensitive columns go through their
    exposure, as in the scan (design 12.8). A JSON value absent from the
    record is null; the values of an items path are joined."""
    paths = [_field_path(field) for field in fields]
    exposures = [field.exposure for field in fields]
    preview = []
    for row_number, observed in rows.preview:
        exposed: list[str | None] = []
        absent = []
        for position, (path, exposure) in enumerate(zip(paths, exposures, strict=True)):
            values = observed.get(path)
            if values is None:
                absent.append(position)
                exposed.append(None)
                continue
            texts = []
            for native, text in values:
                if (
                    exposure in (None, "show")
                    or native == "null"
                    or (native == "string" and facts.category(text) != "content")
                ):
                    texts.append(text)
                elif exposure == "mask":
                    texts.append(mask(text))
            # A hidden value hides the whole cell.
            hidden = len(texts) < len(values)
            exposed.append(None if hidden else PREVIEW_SEPARATOR.join(texts))
        preview.append(PreviewRow(row_number=row_number, values=exposed, absent=absent))
    return preview


# Dataset --------------------------------------------------------------------


def report_fields(result: ScanResult, dataset: DatasetResult) -> list[FieldResult]:
    """The fields shown as columns: every CSV column; the JSON fields holding
    scalar values or nulls, containers being structure (design 16.4)."""
    if result.source.csv is not None:
        return list(dataset.fields)
    return [
        field
        for field in dataset.fields
        if any(native not in CONTAINER_TYPES for native in field.native_types)
    ]


def build_profile(
    result: ScanResult, rows: RowFacts, config: ReportConfig
) -> ReportProfile:
    """The report profile of a scan and its record-level facts: one dataset
    per scan dataset holding at least one column."""
    csv = result.source.csv
    if csv is not None:
        width = len(csv.header)
        if len(result.datasets[0].fields) != width:
            # Untracked columns would be missing from every column-based count.
            raise ConfigurationError(
                f"The report needs every column: the CSV has {width} columns but "
                f"scan.limits.max_fields is {config.scan.limits.max_fields}. "
                "Raise scan.limits.max_fields."
            )
    datasets = []
    selected = [
        (dataset, report_fields(result, dataset)) for dataset in result.datasets
    ]
    if not any(fields for _, fields in selected):
        # A source without scalar values still shows its first dataset.
        selected = selected[:1]
    for dataset, fields in selected:
        if fields or csv is not None or len(selected) == 1:
            datasets.append(
                build_dataset(
                    result,
                    dataset,
                    fields,
                    rows.datasets.get(dataset.id) or DatasetRows(rows),
                    rows,
                    config,
                )
            )
    source = result.source
    return ReportProfile(
        generated_at=datetime.now(UTC),
        processing_seconds=result.duration_seconds,
        source=SourceInfo(
            filename=source.name,
            format=source.format,
            size_bytes=source.size_bytes,
            sha256=source.sha256,
            encoding=source.encoding or config.scan.csv.encoding,
            delimiter=csv.delimiter if csv is not None else None,
        ),
        config=config,
        datasets=datasets,
    )


def build_dataset(
    result: ScanResult,
    dataset: DatasetResult,
    fields: list[FieldResult],
    dataset_rows: DatasetRows,
    facts: RowFacts,
    config: ReportConfig,
) -> DatasetProfile:
    csv = result.source.csv
    row_count = dataset.record_count
    columns = [
        build_column(
            field,
            position=field.path[0].column if csv is not None else position,
            name=field.name if csv is not None else field.display,
            config=config,
        )
        for position, field in enumerate(fields, start=1)
    ]
    cell_count = sum(value_slots(field) for field in fields)
    missing_count = sum(column.missing_count for column in columns)
    trim_count = sum(column.normalization.trim_count for column in columns)
    collapse_count = sum(
        column.normalization.collapse_internal_whitespace_count for column in columns
    )
    empty = [column.id for column in columns if column.inferred_type == "empty"]
    constant = [column.id for column in columns if column.distinct_count == 1]
    mixed = [column.id for column in columns if column.inferred_type == "mixed"]
    numeric_columns = [column for column in columns if column.numeric is not None]
    date_columns = [column for column in columns if column.date_profile is not None]
    string_columns = [column for column in columns if column.string_profile is not None]
    date_profiles = [column.date_profile for column in date_columns]
    ambiguous_columns = [
        column for column in date_columns if column.date_profile.ambiguous_count
    ]
    inferred_type_counts = Counter(column.inferred_type for column in columns)
    semantic_type_counts = Counter(column.semantic_type or "none" for column in columns)
    date_present_count = sum(profile.present_count for profile in date_profiles)
    date_ambiguous_count = sum(profile.ambiguous_count for profile in date_profiles)
    maximum_column_ambiguous_count = max(
        (profile.ambiguous_count for profile in date_profiles), default=0
    )
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
                    row_numbers=list(islice(rows, LISTED_ROWS)),
                )
            )

    exclusions = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.code in EXCLUSION_CODES
        and diagnostic.dataset in (None, dataset.id)
    ]
    excluded_rows = [
        location["record"]
        for diagnostic in exclusions
        for location in diagnostic.locations
    ]
    add_issue(
        "excluded_records",
        "Records excluded by the tolerant error policy, not analyzed",
        sum(diagnostic.count for diagnostic in exclusions),
        rows=sorted(excluded_rows),
    )
    add_issue(
        "duplicate_rows",
        "Duplicate rows beyond their first occurrence",
        dataset_rows.duplicate_count,
        rows=dataset_rows.duplicate_rows,
    )
    add_issue(
        "missing_values",
        "Missing cells",
        missing_count,
        [column.id for column in columns if column.missing_count],
        dataset_rows.rows_with_missing,
    )
    add_issue("empty_columns", "Columns without any present values", len(empty), empty)
    add_issue(
        "trimmed_cells",
        "Cells changed by trimming surrounding whitespace",
        trim_count,
        [column.id for column in columns if column.normalization.trim_count],
        severity="info",
        always=True,
    )
    add_issue(
        "collapsed_whitespace",
        "Cells changed by collapsing repeated internal whitespace",
        collapse_count,
        [
            column.id
            for column in columns
            if column.normalization.collapse_internal_whitespace_count
        ],
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
    add_issue(
        "ambiguous_dates",
        "Date values matching more than one day-month order",
        date_ambiguous_count,
        [column.id for column in ambiguous_columns],
    )
    header_counts = Counter(csv.header if csv is not None else ())
    bad_headers = [
        column.id
        for column in columns
        if csv is not None
        and (not column.name.strip() or header_counts[column.name] > 1)
    ]
    add_issue(
        "ambiguous_headers",
        "Blank or repeated column names",
        len(bad_headers),
        bad_headers,
    )
    limited = [
        column.id
        for column, field in zip(columns, fields, strict=True)
        if has_limited_measure(field)
    ]
    add_issue(
        "limited_measures",
        "Columns with measures stopped by a scan limit",
        len(limited),
        limited,
        severity="info",
    )

    return DatasetProfile(
        id=dataset.id,
        kind=dataset.kind,
        summary=DatasetSummary(
            row_count=row_count,
            column_count=len(columns),
            cell_count=cell_count,
            missing_count=missing_count,
            missing_percent=percent(missing_count, cell_count),
            trim_count=trim_count,
            collapse_internal_whitespace_count=collapse_count,
            duplicate_row_count=dataset_rows.duplicate_count,
            empty_row_count=dataset_rows.empty_row_count,
            empty_column_count=len(empty),
            constant_column_count=len(constant),
            with_issues_column_count=sum(column.with_issues for column in columns),
            numeric_column_count=len(numeric_columns),
            date_column_count=len(date_columns),
            string_column_count=len(string_columns),
            inferred_type_counts=dict(inferred_type_counts),
            inferred_type_percents={
                name: percent(count, len(columns))
                for name, count in inferred_type_counts.items()
            },
            semantic_type_counts=dict(semantic_type_counts),
            semantic_type_percents={
                name: percent(count, len(columns))
                for name, count in semantic_type_counts.items()
            },
        ),
        date_summary=(
            DatasetDateSummary(
                present_count=date_present_count,
                valid_count=sum(profile.valid_count for profile in date_profiles),
                ambiguous_count=date_ambiguous_count,
                ambiguous_percent=percent(date_ambiguous_count, date_present_count),
                invalid_date_count=sum(
                    profile.invalid_date_count for profile in date_profiles
                ),
                not_date_count=sum(profile.not_date_count for profile in date_profiles),
                maximum_column_ambiguous_count=maximum_column_ambiguous_count,
                columns=[
                    DatasetDateColumnSummary(
                        column_id=column.id,
                        name=column.name,
                        position=column.position,
                        ambiguous_count=column.date_profile.ambiguous_count,
                        relative_ambiguous_percent=percent(
                            column.date_profile.ambiguous_count,
                            maximum_column_ambiguous_count,
                        ),
                    )
                    for column in ambiguous_columns
                ],
            )
            if date_columns
            else None
        ),
        columns=columns,
        issues=issues,
        preview=_preview(dataset_rows, fields, facts),
    )
