# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Report profile built from a Tabalyst Scan result (profile revision 10).

``build_profile`` turns a scan result, fresh or read back from a scan
document, into the profile that ``reporting.py`` renders: the columns come
from the scan fields, the duplicate, empty and incomplete rows from the
records block of each dataset. Normalization stages and variant groups and the
structure of JSON datasets are carried over for their report sections. The
findings of the scan (observations, limits, patterns) and its row sample are
not copied: the Report holds the Scan base, with the sample reduced
(``report_base``), and the pages read them from it (``report_sections``). No
file access here.

The report presents the scan: it never resolves an ambiguity the scan left
open (design 12.6). Ambiguous dates stay ambiguous, with the evidence of the
column shown beside them.
"""

import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import combinations

from tabalyst._version import __version__
from tabalyst.config import PresentationSettings, RowSampleSettings
from tabalyst.errors import ConfigurationError
from tabalyst.models import (
    AnalysesBlock,
    ArrayProfile,
    BaseScan,
    ColumnProfile,
    DatasetDateColumnSummary,
    DatasetDateSummary,
    DatasetProfile,
    DatasetStructure,
    DatasetSummary,
    DetectorFormat,
    DetectorProfile,
    NormalizationStage,
    NormalizationStats,
    ReportBlock,
    ReportGenerator,
    ReportProfile,
    StructureField,
    ValueOccurrence,
    ValueProfile,
    Variant,
    VariantGroup,
)
from tabalyst.report_classification import refine
from tabalyst.report_config import ReportConfig, check_length_distribution
from tabalyst.report_sections import cardinality_view
from tabalyst.report_summary import attach_summaries
from tabalyst.report_views import (
    DateBreakdownItem,
    DateFormatCount,
    DateProfile,
    NumericStats,
    StringLengthDistribution,
    StringLengthExample,
    StringProfile,
)
from tabalyst.scan_document import facts_sha256
from tabalyst.scanner.bottomk import BottomKSampler
from tabalyst.scanner.classify.models import Classification
from tabalyst.scanner.models import (
    ByLength,
    Complete,
    DatasetResult,
    DetectorComplete,
    DetectorFailed,
    FieldResult,
    Limited,
    RowSample,
    SampleEntry,
    ScanResult,
    ValueCount,
)
from tabalyst.scanner.planner.models import PlanBase
from tabalyst.scanner.planner.planner import plan_base
from tabalyst.scanner.rowsample import RowPriority

CONTAINER_TYPES = frozenset({"object", "array"})
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
    """Distinct analytical values when exact; raw counts, even for a masked
    column. The qualified count is ``report_sections.cardinality_view``."""
    view = cardinality_view(field)
    return view.value if view.kind == "exact" else None


def _listed_values(field: FieldResult) -> tuple[list[ValueCount], bool]:
    """Listed frequencies and whether they are every analytical value."""
    frequencies = field.values.frequencies
    if frequencies.status == "not_applicable":
        return [], True
    if frequencies.status != "complete":
        return [], False
    return frequencies.value.listed, not frequencies.value.truncated


def report_sample(field: FieldResult, seed: int, size: int) -> list[SampleEntry]:
    """The values of the scan sample of ``field`` that the report uses and
    keeps in its base: all of them up to ``size`` (``kept_per_column``),
    otherwise the ``size`` of smallest priority (design 19.4): the head of a
    ``bottom_k`` sample, or the ones a bottom-k would keep of an ``all`` sample,
    which the scan listed without a hash. A scan of any sample size therefore
    gives the same examples."""
    samples = field.values.samples
    listed = samples.listed
    if len(listed) <= size:
        return listed
    if samples.selection == "bottom_k":
        return listed[:size]
    entries = {(item.type, item.value): item for item in listed}
    sampler = BottomKSampler(size, seed=seed)
    sampler.update(entries, [item.count for item in listed])
    return [entries[entry.key] for entry in sampler.entries()]


def build_value_profile(
    field: FieldResult,
    *,
    inferred_type: str,
    position: int,
    config: ReportConfig,
    sample: list[ValueCount] | None = None,
) -> ValueProfile:
    """Bounded, reproducible value representation.

    Every value when the listing is complete and short enough; otherwise a
    selection among the report sample (``report_sample``), at most
    ``value_examples.kept_per_column`` distinct values of the scan sample.
    ``sample`` is that report sample when the caller already drew it.
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

    if sample is None:
        sample = report_sample(
            field, config.scan.random_seed, settings.kept_per_column
        )
    counts = {item.value: item.count for item in sample}
    population = sorted(counts)
    counts.update((item.value, item.count) for item in listed)
    candidates = random.Random(config.scan.random_seed + position).sample(
        population, len(population)
    )
    frequent_items = listed or sorted(
        sample, key=lambda item: (-item.count, item.value)
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
    field: FieldResult,
    inferred_type: str,
    config: ReportConfig,
    sample: list[ValueCount] | None = None,
) -> StringProfile | None:
    """Length classes and exact length counts; examples per length come from
    the listed frequencies, then the report sample (``sample`` when the caller
    already drew it)."""
    measure = field.string_lengths
    if inferred_type != "text" or measure.status != "complete" or not measure.value.count:
        return None
    lengths = measure.value
    settings = config.string_analysis
    bounds = config.scan.classification
    maximum = lengths.max_length
    if maximum <= bounds.very_short_max_length:
        status = "very_short"
    elif maximum <= bounds.short_max_length:
        status = "short"
    elif maximum <= bounds.medium_max_length:
        status = "medium"
    elif maximum <= bounds.long_max_length:
        status = "long"
    else:
        status = "very_long"
    distribution = []
    if maximum <= settings.length_distribution_max_length:
        listed, _ = _listed_values(field)
        pool = {item.value: item.count for item in listed}
        for item in sorted(
            sample
            if sample is not None
            else report_sample(
                field,
                config.scan.random_seed,
                config.value_examples.kept_per_column,
            ),
            key=lambda item: (-item.count, item.value),
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
    """Exact scan statistics for numeric columns: integers keep every digit."""
    if inferred_type not in {"integer", "number"} or field.numeric.status != "complete":
        return None
    stats = field.numeric.value
    median = stats.median
    # Integers stay integers: converting to float would round a large value.
    values = [stats.min, stats.max, stats.mean]
    values.append(values[1] - values[0])
    if median.status == "complete":
        values.append(median.value)
    if not all(
        isinstance(value, int) or math.isfinite(value) for value in values
    ):
        return None
    return NumericStats(
        minimum=values[0],
        maximum=values[1],
        range=values[3],
        mean=values[2],
        median=values[4] if median.status == "complete" else None,
    )


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


@dataclass(frozen=True)
class ColumnViews:
    """What the report computes from the facts of a field and does not store:
    the document keeps the facts, these are read from the base (design 19.3)."""

    numeric: NumericStats | None
    date_profile: DateProfile | None
    string_profile: StringProfile | None


def build_views(
    field: FieldResult,
    inferred_type: str,
    config: ReportConfig,
    sample: list[ValueCount] | None = None,
) -> ColumnViews:
    return ColumnViews(
        numeric=build_numeric(field, inferred_type),
        date_profile=build_date_profile(field),
        string_profile=build_string_profile(field, inferred_type, config, sample),
    )


def build_column(
    field: FieldResult,
    *,
    position: int,
    name: str,
    config: ReportConfig,
    classification: Classification,
) -> tuple[ColumnProfile, ColumnViews]:
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
    sample = report_sample(
        field, config.scan.random_seed, config.value_examples.kept_per_column
    )
    views = build_views(field, inferred, config, sample)
    value_profile = build_value_profile(
        field, inferred_type=inferred, position=position, config=config, sample=sample
    )
    missing = field.missing.count
    outside = technical.outside_count
    column = ColumnProfile(
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
        normalization=build_normalization(field, row_count),
        distinct_count=_distinct_count(field),
        examples=[
            item.value
            for item in value_profile.values[: config.value_examples.inline_display_size]
        ],
        value_profile=value_profile,
        classification=classification,
        exposure=field.exposure,
        detectors=build_detectors(field),
    )
    return column, views


# Structure ------------------------------------------------------------------


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
    if result.source.header is not None:
        return list(dataset.fields)
    limit = result.config.json_.flatten.depth_limit()
    return [
        field
        for field in dataset.fields
        if any(native not in CONTAINER_TYPES for native in field.native_types)
        or (len(field.path) == limit and field.collection is None)
    ]


def build_profile(
    result: ScanResult,
    config: ReportConfig,
    analyses: AnalysesBlock | None = None,
) -> ReportProfile:
    """The report profile of a scan: one dataset per scan dataset holding at
    least one column. ``config.scan`` must be the configuration of the scan.
    ``analyses`` is what the second pass added, if it was planned."""
    # The scan of the document carries its own bounds: check them against the
    # distribution setting here, since the config was only copied onto them.
    check_length_distribution(config, config.scan)
    header = result.source.header
    if header is not None:
        width = len(header)
        if len(result.datasets[0].fields) != width:
            # Untracked columns would be missing from every column-based count.
            raise ConfigurationError(
                f"The report needs every column: the table has {width} columns but "
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
    # The digest hashes the whole document: computed once for the second pass's
    # base and the base scan.
    facts = facts_sha256(result)
    refinement = Refinement(
        analyses=analyses,
        base=plan_base(result, facts) if analyses is not None else None,
        excluded_records=result.scope.records_excluded,
    )
    for dataset, fields in selected:
        if fields or header is not None or len(selected) == 1:
            datasets.append(
                build_dataset(
                    result,
                    dataset,
                    fields,
                    config,
                    refinement,
                )
            )
    base = report_base(
        result, config.value_examples.kept_per_column, config.row_sample
    )
    profile = ReportProfile(
        engine=base.engine,
        status=base.status,
        run=base.run,
        source=base.source,
        config=base.config,
        config_sha256=base.config_sha256,
        scope=base.scope,
        datasets=base.datasets,
        diagnostics=base.diagnostics,
        derived=base.derived,
        observations=base.observations,
        analyses=analyses,
        report=ReportBlock(
            generated_at=datetime.now(UTC),
            generator=ReportGenerator(version=__version__),
            processing_seconds=result.run.duration_seconds,
            config=PresentationSettings.model_validate(
                config.model_dump(exclude={"scan"})
            ),
            base_scan=BaseScan(
                format=base.format,
                format_version=base.format_version,
                format_revision=base.format_revision,
                engine_version=base.engine.version,
                source_sha256=base.source.sha256,
                config_sha256=base.config_sha256,
                facts_sha256=facts,
            ),
            datasets=datasets,
        ),
    )
    # The summaries are part of the document (contract summary-table.md 20): the
    # pages print them and compute nothing.
    return attach_summaries(profile)


def _without_members(block: ByLength) -> ByLength:
    """The samples by length of the scan without the values of their strata:
    the ids would point at values the Report does not keep (design 19.4). Each
    stratum keeps its length, counts and accuracy and says ``kept`` 0."""
    strata = [
        stratum.model_copy(update={"kept": 0, "ids": []}) for stratum in block.strata
    ]
    return block.model_copy(update={"strata": strata, "listed": []})


def report_rows(sample: RowSample, seed: int, settings: RowSampleSettings) -> RowSample:
    """The row sample a Report keeps: the first ``start`` rows, the last ``end``
    rows and the ``middle`` rows of the interior with the smallest priorities,
    which are the rows a bottom-k of that size would have kept (an exact subset
    of the Scan's, design 19.4). The header is the Scan's; ``kept`` and ``of``
    say what was dropped."""
    priority = RowPriority(seed)
    rows = sample.rows
    starts = [row for row in rows if "start" in row.origins][: settings.start]
    ends = [row for row in rows if "end" in row.origins]
    ends = ends[max(0, len(ends) - settings.end) :] if settings.end else []
    interior = sorted(
        (row for row in rows if row.origins == ["middle"]),
        key=lambda row: (priority.at(row.record), row.record),
    )[: settings.middle]
    chosen = {row.record: row for row in (*starts, *interior, *ends)}
    kept = [
        row
        for group in (
            [row for row in rows if "start" in row.origins],
            [row for row in rows if row.origins == ["middle"]],
            [row for row in rows if row.origins == ["end"]],
        )
        for row in group
        if row.record in chosen
    ]
    return sample.model_copy(update={"kept": len(kept), "rows": kept})


def report_base(
    result: ScanResult, size: int, rows: RowSampleSettings | None = None
) -> ScanResult:
    """The base a Report holds: the scan, with the sample of each field reduced
    to ``size`` values at most (``report_sample``), its size declared by ``kept``
    and ``of`` (design 19.4); the samples by length keep their counts and drop their
    members, and the row sample keeps the rows ``rows`` asks for
    (``report_rows``). Everything else is the scan's, unchanged."""
    seed = result.config.random_seed
    datasets = []
    for dataset in result.datasets:
        fields = []
        for field in dataset.fields:
            samples = field.values.samples
            kept = report_sample(field, seed, size)
            changes: dict[str, object] = {}
            if len(kept) < len(samples.listed):
                changes.update(kept=len(kept), listed=kept)
            if samples.by_length is not None:
                changes["by_length"] = _without_members(samples.by_length)
            if changes:
                reduced = samples.model_copy(update=changes)
                values = field.values.model_copy(update={"samples": reduced})
                field = field.model_copy(update={"values": values})
            fields.append(field)
        changes = {"fields": fields}
        sample = dataset.records.sample
        if sample is not None:
            # The rows are the Scan's: the Report states what it kept.
            kept = report_rows(sample, seed, rows or RowSampleSettings())
            changes["records"] = dataset.records.model_copy(update={"sample": kept})
        datasets.append(dataset.model_copy(update=changes))
    return result.model_copy(update={"datasets": datasets})


@dataclass(frozen=True)
class Refinement:
    """What the classification of the columns is refined with: the second pass
    of the Report and the Scan it must stand on (``report_classification``)."""

    analyses: AnalysesBlock | None = None
    base: PlanBase | None = None
    # Records the scan left out, scan-wide: the datasets are not told apart.
    excluded_records: int = 0


def build_dataset(
    result: ScanResult,
    dataset: DatasetResult,
    fields: list[FieldResult],
    config: ReportConfig,
    refinement: Refinement | None = None,
) -> DatasetProfile:
    refinement = refinement or Refinement()
    tabular = result.source.header is not None
    row_count = dataset.record_count
    built = [
        build_column(
            field,
            position=field.path[0].column if tabular else position,
            name=field.name if tabular else field.display,
            config=config,
            classification=refine(
                field,
                refinement.analyses,
                dataset=dataset.id,
                base=refinement.base,
                excluded_records=refinement.excluded_records,
            ),
        )
        for position, field in enumerate(fields, start=1)
    ]
    columns = [column for column, _ in built]
    views = [view for _, view in built]
    cell_count = sum(value_slots(field) for field in fields)
    missing_count = sum(column.missing_count for column in columns)
    trim_count = sum(column.normalization.trim_count for column in columns)
    collapse_count = sum(
        column.normalization.collapse_internal_whitespace_count for column in columns
    )
    empty = [column.id for column in columns if column.inferred_type == "empty"]
    constant = [column.id for column in columns if column.distinct_count == 1]
    numeric_columns = [view for view in views if view.numeric is not None]
    date_pairs = [
        (column, view.date_profile)
        for column, view in zip(columns, views, strict=True)
        if view.date_profile is not None
    ]
    date_columns = [column for column, _ in date_pairs]
    string_columns = [view for view in views if view.string_profile is not None]
    date_profiles = [profile for _, profile in date_pairs]
    inferred_type_counts = Counter(column.inferred_type for column in columns)
    type_family_counts = Counter(column.classification.family for column in columns)
    type_counts = Counter(
        f"{column.classification.family}/{column.classification.type}"
        for column in columns
    )
    date_present_count = sum(profile.present_count for profile in date_profiles)
    date_ambiguous_count = sum(profile.ambiguous_count for profile in date_profiles)
    maximum_column_ambiguous_count = max(
        (profile.ambiguous_count for profile in date_profiles), default=0
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
            numeric_column_count=len(numeric_columns),
            date_column_count=len(date_columns),
            string_column_count=len(string_columns),
            inferred_type_counts=dict(inferred_type_counts),
            inferred_type_percents={
                name: percent(count, len(columns))
                for name, count in inferred_type_counts.items()
            },
            type_family_counts=dict(type_family_counts),
            type_family_percents={
                name: percent(count, len(columns))
                for name, count in type_family_counts.items()
            },
            type_counts=dict(type_counts),
            type_percents={
                name: percent(count, len(columns))
                for name, count in type_counts.items()
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
                        ambiguous_count=profile.ambiguous_count,
                        relative_ambiguous_percent=percent(
                            profile.ambiguous_count,
                            maximum_column_ambiguous_count,
                        ),
                    )
                    for column, profile in date_pairs
                    if profile.ambiguous_count
                ],
            )
            if date_columns
            else None
        ),
        columns=columns,
        structure=(
            None
            if tabular
            else build_structure(dataset, {field.id for field in fields})
        ),
    )
