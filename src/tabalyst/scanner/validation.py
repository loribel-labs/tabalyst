# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Semantic validation of a scan result: the invariants between its fields
that a JSON Schema cannot express (design 19.7).
"""

from __future__ import annotations

from tabalyst.scanner.config import config_sha256
from tabalyst.scanner.models import (
    CardinalityComplete,
    CardinalityLimited,
    Complete,
    DatasetResult,
    DetectorComplete,
    FieldResult,
    ScanResult,
)


def check_scan(result: ScanResult) -> list[str]:
    """Violated invariants of ``result``, one message each, empty when valid.

    A scan the engine produced is always valid; the check is for documents that
    were read back, edited or produced by another implementation. Each message
    starts with the location of the offending block.
    """
    problems: list[str] = []
    _check_scan(result, problems)
    for dataset in result.datasets:
        _check_dataset(dataset, result, problems)
    return problems


def _check_scan(result: ScanResult, problems: list[str]) -> None:
    scope = result.scope
    if scope.records_read != scope.records_analyzed + scope.records_excluded:
        problems.append(
            "scope: records_read must equal records_analyzed + records_excluded"
        )
    if sum(scope.exclusions.values()) != scope.records_excluded:
        problems.append("scope: exclusions must add up to records_excluded")
    if result.config_sha256 != config_sha256(result.config):
        problems.append("config_sha256: does not match config")
    shape = result.source.shape
    if shape.datasets != len(result.datasets):
        problems.append("source.shape: datasets must equal the number of datasets")
    if shape.fields != sum(len(dataset.fields) for dataset in result.datasets):
        problems.append("source.shape: fields must equal the number of fields")
    if shape.records != sum(dataset.record_count for dataset in result.datasets):
        problems.append("source.shape: records must equal the sum of record_count")
    known = {dataset.id for dataset in result.datasets}
    for index, diagnostic in enumerate(result.diagnostics):
        if diagnostic.dataset is not None and diagnostic.dataset not in known:
            problems.append(f"diagnostics[{index}]: unknown dataset")


def _check_dataset(
    dataset: DatasetResult, result: ScanResult, problems: list[str]
) -> None:
    where = f"datasets[{dataset.id}]"
    ids = [field.id for field in dataset.fields]
    if len(set(ids)) != len(ids):
        problems.append(f"{where}: field ids must be unique")
    if sum(dataset.record_types.values()) != dataset.record_count:
        problems.append(f"{where}: record_types must add up to record_count")
    records = dataset.records
    for name in ("with_missing", "empty"):
        block = getattr(records, name)
        if len(block.records) > block.count:
            problems.append(f"{where}.records.{name}: lists more records than counted")
    if len(records.preview) > result.config.records.preview:
        problems.append(f"{where}.records.preview: longer than records.preview")
    for field in dataset.fields:
        _check_field(field, f"{where}.fields[{field.id}]", result, problems)


def _check_field(
    field: FieldResult, where: str, result: ScanResult, problems: list[str]
) -> None:
    presence = field.presence
    if presence.present != field.occurrences:
        problems.append(f"{where}.presence: present must equal occurrences")
    if presence.absent is not None and (
        presence.absent != presence.parent_count - presence.present
    ):
        problems.append(f"{where}.presence: absent must equal parent_count - present")
    if sum(field.native_types.values()) != field.occurrences:
        problems.append(f"{where}.native_types: must add up to occurrences")
    strings = field.strings
    if (
        strings.count
        != strings.empty + strings.blank + strings.marker + strings.content
    ):
        problems.append(f"{where}.strings: categories must add up to count")
    if strings.count != field.native_types.get("string", 0):
        problems.append(f"{where}.strings: count must equal the string occurrences")
    scalars = sum(
        field.native_types.get(name, 0) for name in ("integer", "number", "boolean")
    )
    if field.values.count != strings.content + scalars:
        problems.append(f"{where}.values: count must equal content strings and scalars")
    components = field.missing.components
    expected = sum(getattr(components, name) or 0 for name in field.missing.definition)
    if field.missing.count != expected:
        problems.append(f"{where}.missing: count must add up the defined components")
    _check_cardinality(field, where, problems)
    _check_listings(field, where, result, problems)
    _check_statistics(field, where, problems)
    for detector in field.detectors:
        if isinstance(detector, DetectorComplete):
            _check_coverage(detector, f"{where}.detectors[{detector.id}]", problems)


def _check_cardinality(field: FieldResult, where: str, problems: list[str]) -> None:
    cardinality = field.values.cardinality
    where = f"{where}.values.cardinality"
    count = field.values.count
    if isinstance(cardinality, CardinalityComplete):
        if cardinality.value > count:
            problems.append(f"{where}: value exceeds the analyzed values")
    elif isinstance(cardinality, CardinalityLimited):
        lower, upper = cardinality.lower_bound, cardinality.upper_bound
        if upper is not None and upper != count:
            problems.append(f"{where}: upper_bound must equal values.count")
        if lower is not None and lower > count:
            problems.append(f"{where}: lower_bound exceeds the analyzed values")
        reached = cardinality.threshold_reached_at_record
        overflow = cardinality.overflow_detected_at_record
        if cardinality.reason == "distinct_limit":
            if lower != cardinality.limit + 1:
                problems.append(f"{where}: lower_bound must be limit + 1")
            if reached is None or overflow is None or reached > overflow:
                problems.append(
                    f"{where}: the limit must be reached before it overflows"
                )
        elif reached is not None or overflow is not None:
            problems.append(f"{where}: records are only known for distinct_limit")


def _check_listings(
    field: FieldResult, where: str, result: ScanResult, problems: list[str]
) -> None:
    count = field.values.count
    frequencies = field.values.frequencies
    if isinstance(frequencies, Complete):
        listing = frequencies.value
        if sum(item.count for item in listing.listed) > count:
            problems.append(
                f"{where}.values.frequencies: listed counts exceed values.count"
            )
        if listing.truncated != (listing.distinct > len(listing.listed)):
            problems.append(f"{where}.values.frequencies: truncated is inconsistent")
        cardinality = field.values.cardinality
        if isinstance(cardinality, CardinalityComplete) and (
            listing.distinct > cardinality.value
        ):
            problems.append(
                f"{where}.values.frequencies: more analytical than raw distinct values"
            )
    samples = field.values.samples
    if samples.kept != len(samples.listed) or samples.kept > samples.of:
        problems.append(f"{where}.values.samples: kept does not match the listing")
    if samples.of > result.config.limits.max_samples:
        problems.append(f"{where}.values.samples: longer than max_samples")
    if any(item.count < 1 or item.count > count for item in samples.listed):
        problems.append(f"{where}.values.samples: a count is out of range")
    listed_total = sum(item.count for item in samples.listed)
    # A Report keeps fewer values than the scan sampled (kept < of).
    complete = samples.kept == samples.of
    if (
        samples.selection == "all"
        and complete
        and samples.listed
        and listed_total != count
    ):
        problems.append(
            f"{where}.values.samples: all counts must add up to values.count"
        )
    _check_sample_members(field, where, problems)


def _check_sample_members(field: FieldResult, where: str, problems: list[str]) -> None:
    """The bottom-k members of a sample and the estimate of the cardinality."""
    samples = field.values.samples
    where_samples = f"{where}.values.samples"
    ids = [item.id for item in samples.listed]
    if len(set(ids)) != len(ids) or any(entry_id < 0 for entry_id in ids):
        problems.append(f"{where_samples}: entry ids must be distinct and not negative")
    if samples.selection == "bottom_k":
        if samples.k is None or samples.hash is None:
            problems.append(f"{where_samples}: a bottom_k sample names k and hash")
        elif samples.of > samples.k:
            problems.append(f"{where_samples}: more values than k")
    elif samples.k is not None or samples.hash is not None or samples.threshold:
        problems.append(f"{where_samples}: only a bottom_k sample names k and hash")
    cardinality = field.values.cardinality
    estimate = (
        cardinality.estimate if isinstance(cardinality, CardinalityLimited) else None
    )
    if estimate is None:
        return
    where_estimate = f"{where}.values.cardinality.estimate"
    if samples.selection != "bottom_k" or estimate.k != samples.k:
        problems.append(f"{where_estimate}: must come from the bottom_k sample")
    lower = cardinality.lower_bound or 0
    upper = cardinality.upper_bound
    if estimate.value < lower or (upper is not None and estimate.value > upper):
        problems.append(f"{where_estimate}: value must stay within the certain bounds")
    if estimate.unclamped_value is not None and estimate.value not in (lower, upper):
        problems.append(f"{where_estimate}: unclamped_value only when a bound applied")


def _check_statistics(field: FieldResult, where: str, problems: list[str]) -> None:
    lengths = field.string_lengths
    if isinstance(lengths, Complete):
        value = lengths.value
        if sum(item.count for item in value.length_histogram) != value.count:
            problems.append(f"{where}.string_lengths: histogram must add up to count")
        if value.count > field.strings.content:
            problems.append(
                f"{where}.string_lengths: count exceeds the content strings"
            )
        if not value.min_length <= value.max_length:
            problems.append(f"{where}.string_lengths: min_length exceeds max_length")
    numeric = field.numeric
    if isinstance(numeric, Complete):
        value = numeric.value
        if value.native_count + value.text_count != value.count:
            problems.append(f"{where}.numeric: native and text counts must add up")
        if value.positive + value.negative + value.zero != value.count:
            problems.append(f"{where}.numeric: signs must add up to count")
        if not value.min <= value.max:
            problems.append(f"{where}.numeric: min exceeds max")
    booleans = field.booleans
    if isinstance(booleans, Complete):
        total = booleans.value.true + booleans.value.false
        if total != field.native_types.get("boolean", 0):
            problems.append(
                f"{where}.booleans: counts must equal the boolean occurrences"
            )


def _check_coverage(
    detector: DetectorComplete, where: str, problems: list[str]
) -> None:
    coverage = detector.coverage
    if coverage.tested != coverage.eligible - coverage.not_tested:
        problems.append(f"{where}.coverage: tested must be eligible - not_tested")
    parts = (
        coverage.matched + coverage.ambiguous + coverage.invalid + coverage.not_matched
    )
    if coverage.tested != parts:
        problems.append(f"{where}.coverage: tested must add up its outcomes")
