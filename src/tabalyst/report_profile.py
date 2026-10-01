"""Report profile built from a Tabalyst Scan result (profile revision 10).

``build_profile`` turns a scan result, fresh or read back from a scan
document, into the profile that ``reporting.py`` renders: the columns come
from the scan fields, the preview, duplicate, empty and incomplete rows from
the records block of each dataset. Normalization stages and variant groups,
limited measures, diagnostics and the structure of JSON datasets are carried
over for their report sections. No file access here.

The report presents the scan: it never resolves an ambiguity the scan left
open (design 12.6). Ambiguous dates stay ambiguous, with the evidence of the
column shown beside them.
"""

import math
import random
import re
from collections import Counter
from datetime import UTC, datetime
from itertools import combinations, islice

from pydantic import BaseModel

from tabalyst.errors import ConfigurationError
from tabalyst.models import (
    ArrayProfile,
    ColumnProfile,
    DatasetDateColumnSummary,
    DatasetDateSummary,
    DatasetLimits,
    DatasetProfile,
    DatasetStructure,
    DatasetSummary,
    DateBreakdownItem,
    DateFormatCount,
    DateProfile,
    DetectorFormat,
    DetectorProfile,
    DiagnosticLocation,
    DiagnosticProfile,
    Issue,
    MeasureLimit,
    NormalizationStage,
    NormalizationStats,
    NumericStats,
    PreviewRow,
    ReportProfile,
    ScanFieldDetails,
    SourceInfo,
    StringLengthDistribution,
    StringLengthExample,
    StringProfile,
    StructureField,
    ValueOccurrence,
    ValueProfile,
    Variant,
    VariantGroup,
)
from tabalyst.report_config import ReportConfig
from tabalyst.scanner.engine import has_limited_measure
from tabalyst.scanner.models import (
    Complete,
    DatasetResult,
    DetectorComplete,
    DetectorFailed,
    FieldResult,
    Limited,
    Records,
    ScanResult,
    ValueCount,
)

# Row numbers listed by an issue.
LISTED_ROWS = 10
# Diagnostics of records excluded under the tolerant error policy.
EXCLUSION_CODES = frozenset(
    {
        "csv_width_mismatch",
        "record_too_large",
        "json_duplicate_key",
        "jsonl_invalid_line",
        "jsonl_record_not_object",
        "jsonl_line_too_long",
    }
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
    if complete and (
        len(listed) <= settings.full_distribution_max_distinct
        or field.interpretations.primary == "enumeration"
    ):
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


def build_normalization(field: FieldResult, row_count: int) -> NormalizationStats:
    """Every normalization stage of the scan, then its variant groups, already
    exposed (design 10 and 12.8)."""
    stages = []
    for stage in field.normalization.stages:
        cardinality = stage.cardinality
        stages.append(
            NormalizationStage(
                stage=stage.stage,
                enabled=stage.enabled,
                changed_count=stage.changed,
                changed_percent=(
                    None if stage.changed is None else percent(stage.changed, row_count)
                ),
                distinct_count=(
                    cardinality.value if isinstance(cardinality, Complete) else None
                ),
                distinct_status=(
                    "disabled" if cardinality is None else cardinality.status
                ),
            )
        )
    groups = field.normalization.variant_groups
    complete = isinstance(groups, Complete)
    trim = _stage_changes(field, "trim")
    collapse = _stage_changes(field, "collapse_whitespace")
    return NormalizationStats(
        trim_count=trim,
        trim_percent=percent(trim, row_count),
        collapse_internal_whitespace_count=collapse,
        collapse_internal_whitespace_percent=percent(collapse, row_count),
        stages=stages,
        variant_group_count=groups.value.groups if complete else None,
        variant_group_status=groups.status,
        variant_groups=[
            VariantGroup(
                key=group.key,
                count=group.count,
                distinct_count=group.distinct,
                variants=[
                    Variant(value=item.value, count=item.count)
                    for item in group.variants
                ],
                truncated=group.truncated,
            )
            for group in (groups.value.listed if complete else [])
        ],
        variant_groups_truncated=complete and groups.value.truncated,
    )


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
                coverage=coverage,
                evidence=detector.evidence,
                details=detector.details,
                adaptive=detector.adaptive,
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
    type_counts = dict(technical.counts)
    complex_counts = {
        name: count for name, count in field.native_types.items() if name in CONTAINER_TYPES
    }
    if inferred == "empty" and complex_counts:
        # Containers kept whole at the flatten limit: no scalar family.
        inferred = "complex"
        type_counts = complex_counts
    date_profile = build_date_profile(field)
    value_profile = build_value_profile(
        field, inferred_type=inferred, position=position, config=config
    )
    missing = field.missing.count
    outside = technical.outside_count
    return ColumnProfile(
        id=field.id,
        name=name,
        path=field.display,
        position=position,
        inferred_type=inferred,
        type_counts=type_counts,
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
        normalization=build_normalization(field, row_count),
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
        scan_details=ScanFieldDetails(
            first_record=field.first_record,
            occurrences=field.occurrences,
            value_count=field.values.count,
            presence=field.presence,
            native_types=dict(field.native_types),
            strings=field.strings,
            missing=field.missing,
            first=field.values.first,
            last=field.values.last,
            string_characteristics=field.string_characteristics,
            string_lengths=(
                field.string_lengths.value
                if isinstance(field.string_lengths, Complete)
                else None
            ),
            numeric=field.numeric.value if isinstance(field.numeric, Complete) else None,
            booleans=(
                field.booleans.value if isinstance(field.booleans, Complete) else None
            ),
            temporal=(
                field.temporal.value if isinstance(field.temporal, Complete) else None
            ),
        ),
    )


def _preview(records: Records, fields: list[FieldResult]) -> list[PreviewRow]:
    """Preview rows of the scan, already exposed (design 12.8). A JSON value
    absent from the record is null; the values of an items path are joined;
    a JSON null is the text ``null``."""
    preview = []
    for record in records.preview:
        exposed: list[str | None] = []
        absent = []
        for position, field in enumerate(fields):
            if field.id not in record.values:
                absent.append(position)
                exposed.append(None)
                continue
            texts = record.values[field.id]
            exposed.append(
                None
                if texts is None
                else PREVIEW_SEPARATOR.join(
                    "null" if text is None else text for text in texts
                )
            )
        preview.append(
            PreviewRow(row_number=record.record, values=exposed, absent=absent)
        )
    return preview


# Limits and structure -------------------------------------------------------


def _limited_measures(model: object, location: str):
    """Every ``limited`` envelope under a scan model, with its location. The
    ``value`` of a complete envelope is left out of locations; list items are
    named by their stage or id."""
    if isinstance(model, Limited):
        yield location, model
    elif isinstance(model, BaseModel):
        for name in type(model).model_fields:
            if isinstance(model, Complete):
                inner = location
            else:
                inner = f"{location}.{name}" if location else name
            yield from _limited_measures(getattr(model, name), inner)
    elif isinstance(model, list):
        for index, item in enumerate(model):
            label = getattr(item, "stage", None) or getattr(item, "id", None)
            yield from _limited_measures(item, f"{location}.{label or index}")


def build_limits(
    result: ScanResult, dataset: DatasetResult, columns: dict[str, str]
) -> DatasetLimits:
    """Limited measures of the dataset and of each field, structural
    truncation, and the diagnostics of the dataset and of the whole scan.
    ``columns`` maps the field ids shown as columns to their column ids."""
    displays = {field.id: field.display for field in dataset.fields}
    measures = [
        MeasureLimit(
            column_id=None,
            path=None,
            measure=location,
            reason=measure.reason,
            limit=measure.limit,
            lower_bound=measure.lower_bound,
        )
        for part in ("structure", "records")
        for location, measure in _limited_measures(getattr(dataset, part), part)
    ]
    measures += [
        MeasureLimit(
            column_id=columns.get(field.id),
            path=field.display,
            measure=location,
            reason=measure.reason,
            limit=measure.limit,
            lower_bound=measure.lower_bound,
        )
        for field in dataset.fields
        for location, measure in _limited_measures(field, "")
    ]
    diagnostics = [
        DiagnosticProfile(
            code=diagnostic.code,
            level=diagnostic.level,
            message=diagnostic.message,
            count=diagnostic.count,
            dataset=diagnostic.dataset,
            path=displays.get(diagnostic.field, diagnostic.field),
            detector=diagnostic.detector,
            locations=[
                DiagnosticLocation.model_validate(location)
                for location in diagnostic.locations
            ],
        )
        for diagnostic in result.diagnostics
        if diagnostic.dataset in (None, dataset.id)
    ]
    return DatasetLimits(
        measures=measures,
        untracked_observations=dataset.structure.untracked_observations,
        depth_truncated_observations=dataset.structure.depth_truncated_observations,
        diagnostics=diagnostics,
    )


def build_structure(dataset: DatasetResult, columns: set[str]) -> DatasetStructure:
    """Every path of a JSON dataset, containers included, with presence per
    parent and array lengths (design 16.2)."""
    displays = {field.id: field.display for field in dataset.fields}
    paths = dataset.structure.paths
    fields = []
    for field in dataset.fields:
        presence = field.presence
        arrays = field.arrays
        fields.append(
            StructureField(
                id=field.id,
                path=field.display,
                depth=len(field.path),
                parent=displays.get(field.parent) if field.parent else None,
                native_types=dict(field.native_types),
                occurrences=field.occurrences,
                parent_type=presence.parent_type,
                parent_count=presence.parent_count,
                present_count=presence.present,
                absent_count=presence.absent,
                present_percent=(
                    None
                    if presence.parent_type == "array"
                    else percent(presence.present, presence.parent_count)
                ),
                collection=field.collection,
                arrays=(
                    None
                    if arrays is None
                    else ArrayProfile(
                        count=arrays.count,
                        empty_count=arrays.empty,
                        minimum_length=arrays.min_length,
                        maximum_length=arrays.max_length,
                        mean_length=(
                            round(arrays.total_items / arrays.count, 2)
                            if arrays.count
                            else 0.0
                        ),
                        item_count=arrays.total_items,
                    )
                ),
                column=field.id in columns,
            )
        )
    complete = isinstance(paths, Complete)
    return DatasetStructure(
        record_types=dict(dataset.record_types),
        path_count=paths.value if complete else None,
        path_status="complete" if complete else "limited",
        max_depth_seen=dataset.structure.max_depth_seen,
        fields=fields,
    )


# Dataset --------------------------------------------------------------------


def report_fields(result: ScanResult, dataset: DatasetResult) -> list[FieldResult]:
    """The fields shown as columns: every CSV column; the JSON fields holding
    scalar values or nulls, containers being structure (design 16.4), except
    the containers kept whole at the flatten limit, which are complex columns."""
    if result.source.csv is not None:
        return list(dataset.fields)
    limit = result.config.json_.flatten.depth_limit()
    return [
        field
        for field in dataset.fields
        if any(native not in CONTAINER_TYPES for native in field.native_types)
        or (len(field.path) == limit and field.collection is None)
    ]


def build_profile(result: ScanResult, config: ReportConfig) -> ReportProfile:
    """The report profile of a scan: one dataset per scan dataset holding at
    least one column. ``config.scan`` must be the configuration of the scan."""
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
    records = dataset.records
    duplicates = records.duplicates
    if isinstance(duplicates.count, Limited):
        duplicate_status = "limited"
        duplicate_count = duplicates.count.lower_bound or 0
    elif duplicates.count.status == "complete":
        duplicate_status = "complete"
        duplicate_count = duplicates.count.value
    else:
        duplicate_status = "disabled"
        duplicate_count = None
    add_issue(
        "duplicate_rows",
        "Duplicate rows beyond their first occurrence"
        + (", at least" if duplicate_status == "limited" else ""),
        duplicate_count,
        rows=duplicates.records,
    )
    add_issue(
        "missing_values",
        "Missing cells",
        missing_count,
        [column.id for column in columns if column.missing_count],
        records.with_missing.records,
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
    variant_columns = [
        column for column in columns if column.normalization.variant_group_count
    ]
    add_issue(
        "variant_groups",
        "Values written in several ways that normalization compares as equal",
        sum(column.normalization.variant_group_count for column in variant_columns),
        [column.id for column in variant_columns],
        severity="info",
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
            duplicate_row_count=duplicate_count,
            duplicate_row_status=duplicate_status,
            empty_row_count=records.empty.count,
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
        preview=_preview(records, fields),
        limits=build_limits(
            result,
            dataset,
            {field.id: column.id for field, column in zip(fields, columns, strict=True)},
        ),
        structure=(
            None
            if csv is not None
            else build_structure(dataset, {field.id for field in fields})
        ),
    )
