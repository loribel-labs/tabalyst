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
    CardinalityEstimate,
    CardinalityLimited,
    Complete,
    DatasetResult,
    DetectorComplete,
    FieldResult,
    LengthStratum,
    LongTexts,
    RowSample,
    SampleEntry,
    ScanResult,
)
from tabalyst.scanner.rowsample import (
    ROW_HASH_ALGORITHM,
    ROW_HASH_BITS,
    ROW_HASH_VERSION,
    RowPriority,
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
    _check_row_sample(dataset, result, where, problems)
    for field in dataset.fields:
        _check_field(field, f"{where}.fields[{field.id}]", result, problems)


def _check_row_sample(
    dataset: DatasetResult, result: ScanResult, where: str, problems: list[str]
) -> None:
    """The row sample of a dataset (design 18.11)."""
    settings = result.config.records.sample
    sample = dataset.records.sample
    where = f"{where}.records.sample"
    if sample is None:
        if settings.rows:
            problems.append(f"{where}: missing although records.sample.rows is set")
        return
    if not settings.rows:
        problems.append(f"{where}: present although records.sample.rows is 0")
        return
    requested = sample.requested
    if (requested.rows, requested.edge, requested.middle) != (
        settings.rows,
        settings.edge,
        settings.rows - 2 * settings.edge,
    ):
        problems.append(f"{where}.requested: does not match records.sample")
    if (sample.cell_chars, sample.max_bytes) != (settings.cell_chars, settings.max_bytes):
        problems.append(f"{where}: cell_chars and max_bytes must match records.sample")
    if not 0 <= sample.middle_k <= requested.middle:
        problems.append(f"{where}.middle_k: outside 0 to the requested middle")
    if sample.reason not in (None, "memory_budget"):
        problems.append(f"{where}.reason: only memory_budget is known")
    if sample.middle_k < requested.middle and sample.reason is None:
        problems.append(f"{where}.reason: a cut middle needs its reason")
    population = sample.population
    if population.records != dataset.record_count:
        problems.append(f"{where}.population: records must equal record_count")
    if population.interior != max(0, population.records - 2 * requested.edge):
        problems.append(f"{where}.population: interior must be records - 2 * edge")
    if sample.bytes > sample.max_bytes:
        problems.append(f"{where}: bytes exceed max_bytes")
    field_ids = {field.id for field in dataset.fields}
    if not set(sample.fields) <= field_ids:
        problems.append(f"{where}.fields: lists an unknown field")
    if sample.kept != len(sample.rows) or sample.kept > sample.of:
        problems.append(f"{where}: kept must equal the rows listed and not exceed of")
    if sample.complete and sample.of != population.records:
        problems.append(f"{where}: complete needs every record to be a row")
    hash_ = sample.hash
    if (hash_.algorithm, hash_.version, hash_.bits, hash_.seed) != (
        ROW_HASH_ALGORITHM,
        ROW_HASH_VERSION,
        ROW_HASH_BITS,
        result.config.random_seed,
    ):
        problems.append(f"{where}.hash: not the priority function of this engine")
    elif sample.rows:
        _check_rows(sample, requested.edge, where, problems)


def _check_rows(
    sample: RowSample, edge: int, where: str, problems: list[str]
) -> None:
    fields = set(sample.fields)
    previous: dict[str, int] = {}
    order = {"start": 0, "middle": 1, "end": 2}
    last_group = 0
    middle: list[int] = []
    for number, row in enumerate(sample.rows):
        place = f"{where}.rows[{number}]"
        origins = row.origins
        if (
            not origins
            or origins != sorted(set(origins), key=order.__getitem__)
            or (len(origins) > 1 and "middle" in origins)
        ):
            problems.append(f"{place}.origins: invalid")
            continue
        group = order[origins[0]]
        if group < last_group:
            problems.append(f"{place}: rows must be grouped start, middle, end")
        last_group = max(last_group, group)
        key = origins[0] if origins != ["start", "end"] else "start"
        if row.record <= previous.get(key, 0):
            problems.append(f"{place}.record: positions must ascend in a group")
        previous[key] = row.record
        if not set(row.values) <= fields or not set(row.truncated) <= fields:
            problems.append(f"{place}: cells of a field that is not projected")
        if origins == ["middle"]:
            middle.append(row.record)
    starts = sum("start" in row.origins for row in sample.rows)
    ends = sum("end" in row.origins for row in sample.rows)
    if starts > edge or ends > edge or len(middle) > sample.middle_k:
        problems.append(f"{where}.rows: more rows than a group may hold")
    if sample.truncated_cells != sum(len(row.truncated) for row in sample.rows):
        problems.append(f"{where}.truncated_cells: must count the cut cells")
    if middle:
        priority = RowPriority(sample.hash.seed)
        worst = max(priority.at(index) for index in middle)
        if sample.threshold is not None and int(sample.threshold, 16) != worst:
            problems.append(f"{where}.threshold: must be the largest middle priority")
    elif sample.threshold is not None:
        problems.append(f"{where}.threshold: a sample without middle rows has none")


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
    long_texts = samples.long_texts
    # Long texts are sampled apart: their occurrences are not in the listing.
    expected = count - (0 if long_texts is None else long_texts.occurrences)
    if (
        samples.selection == "all"
        and complete
        and samples.listed
        and listed_total != expected
    ):
        problems.append(
            f"{where}.values.samples: all counts must add up to values.count"
        )
    _check_sample_members(field, where, problems)
    _check_by_length(field, expected, result, where, problems)


def _check_by_length(
    field: FieldResult,
    stored: int,
    result: ScanResult,
    where: str,
    problems: list[str],
) -> None:
    """The ``by_length`` block of a sample (design 18.7); ``stored`` is the
    number of occurrences of the values that fit a sample."""
    samples = field.values.samples
    block = samples.by_length
    if block is None:
        return
    where = f"{where}.values.samples.by_length"
    limits = result.config.limits
    if samples.selection != "bottom_k":
        problems.append(f"{where}: only a bottom_k sample has samples by length")
    if block.per_length_k != limits.max_samples_per_length or (
        block.max_lengths > limits.max_length_strata
    ):
        problems.append(f"{where}: sizes out of the configured limits")
    if (block.requested_max_lengths is None) != (block.reason is None) or (
        block.requested_max_lengths is not None
        and block.requested_max_lengths <= block.max_lengths
    ):
        problems.append(
            f"{where}: requested_max_lengths and reason go together and "
            "requested_max_lengths exceeds max_lengths"
        )
    if block.limited != (block.other is not None or block.max_lengths == 0):
        problems.append(f"{where}: limited must follow other and max_lengths")
    if block.tracked != len(block.strata) or block.tracked > block.max_lengths:
        problems.append(f"{where}: tracked does not match the strata")
    lengths = [stratum.length for stratum in block.strata]
    if lengths != sorted(set(lengths)) or any(length < 0 for length in lengths):
        problems.append(f"{where}: strata must be in ascending distinct lengths")
    shared = {item.id: item for item in samples.listed}
    pool = {item.id: item for item in block.listed}
    if len(pool) != len(block.listed) or shared.keys() & pool.keys():
        problems.append(f"{where}: pool ids must be new and distinct")
    members: set[int] = set()
    for stratum in block.strata:
        _check_stratum(
            stratum, shared | pool, block.per_length_k, members, where, problems
        )
    if not pool.keys() <= members:
        problems.append(f"{where}: a value of the pool belongs to no stratum")
    counted = sum(stratum.occurrences for stratum in block.strata)
    counted += 0 if block.other is None else block.other.occurrences
    if block.max_lengths and counted != stored:
        problems.append(f"{where}: strata and other must add up to the stored values")


def _check_stratum(
    stratum: LengthStratum,
    entries: dict[int, SampleEntry],
    per_length_k: int,
    members: set[int],
    where: str,
    problems: list[str],
) -> None:
    where = f"{where}.strata[length={stratum.length}]"
    if stratum.kept != len(stratum.ids) or stratum.kept > stratum.of:
        problems.append(f"{where}: kept does not match the ids")
    if stratum.of > per_length_k or stratum.occurrences < 1:
        problems.append(f"{where}: sizes out of range")
    if stratum.count_accuracy not in ("exact", "partial"):
        problems.append(f"{where}: count_accuracy is exact or partial")
    if (stratum.count_accuracy == "partial") != (
        stratum.tracking_started_at_occurrence is not None
    ):
        problems.append(
            f"{where}: tracking_started_at_occurrence goes with a partial stratum"
        )
    if stratum.selection == "all" and stratum.threshold is not None:
        problems.append(f"{where}: only a bottom_k stratum has a threshold")
    total = 0
    for entry_id in stratum.ids:
        entry = entries.get(entry_id)
        if entry is None or entry_id in members:
            problems.append(f"{where}: id {entry_id} is unknown or listed twice")
            continue
        members.add(entry_id)
        total += entry.count
        if len(entry.value) != stratum.length:
            problems.append(f"{where}: id {entry_id} has another length")
    if total > stratum.occurrences:
        problems.append(f"{where}: counts exceed occurrences")
    if (
        stratum.selection == "all"
        and stratum.count_accuracy == "exact"
        and stratum.kept == stratum.of
        and total != stratum.occurrences
    ):
        problems.append(f"{where}: all counts must add up to occurrences")


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
    if (samples.requested_k is None) != (samples.reason is None) or (
        samples.requested_k is not None
        and (samples.k is None or samples.k >= samples.requested_k)
    ):
        problems.append(
            f"{where_samples}: requested_k and reason go together and requested_k "
            "exceeds k"
        )
    _check_long_texts(field, where, problems)
    cardinality = field.values.cardinality
    estimate = (
        cardinality.estimate if isinstance(cardinality, CardinalityLimited) else None
    )
    if estimate is None:
        return
    where_estimate = f"{where}.values.cardinality.estimate"
    if estimate.parts is not None:
        _check_estimate_parts(estimate, samples.long_texts, where_estimate, problems)
    elif samples.selection != "bottom_k" or estimate.k != samples.k:
        problems.append(f"{where_estimate}: must come from the bottom_k sample")
    lower = cardinality.lower_bound or 0
    upper = cardinality.upper_bound
    if estimate.value < lower or (upper is not None and estimate.value > upper):
        problems.append(f"{where_estimate}: value must stay within the certain bounds")
    if estimate.unclamped_value is not None and estimate.value not in (lower, upper):
        problems.append(f"{where_estimate}: unclamped_value only when a bound applied")


def _check_estimate_parts(
    estimate: CardinalityEstimate,
    long_texts: LongTexts | None,
    where: str,
    problems: list[str],
) -> None:
    """An estimate of two domains: the values and the long texts (design 18.6)."""
    if long_texts is None:
        problems.append(f"{where}: parts need long_texts")
    if [part.domain for part in estimate.parts] != ["values", "long_texts"]:
        problems.append(f"{where}: parts must be values then long_texts")
        return
    if estimate.k is not None or estimate.theta_hex is not None:
        problems.append(f"{where}: k and theta_hex belong to the parts")
    raw = estimate.unclamped_value
    total = sum(part.value for part in estimate.parts)
    if abs((estimate.value if raw is None else raw) - total) > 1e-6 * max(total, 1):
        problems.append(f"{where}: value must be the sum of the parts")
    for part in estimate.parts:
        if (part.accuracy == "estimated") != (part.k is not None):
            problems.append(f"{where}: only an estimated part names k")


def _check_long_texts(field: FieldResult, where: str, problems: list[str]) -> None:
    """The ``long_texts`` block of a sample (design 18.6)."""
    long_texts = field.values.samples.long_texts
    if long_texts is None:
        return
    where = f"{where}.values.samples.long_texts"
    ids = [item.id for item in long_texts.listed]
    if len(set(ids)) != len(ids) or any(entry_id < 0 for entry_id in ids):
        problems.append(f"{where}: entry ids must be distinct and not negative")
    digests = [item.digest for item in long_texts.listed]
    if len(set(digests)) != len(digests):
        problems.append(f"{where}: digests must be distinct")
    if long_texts.kept != len(long_texts.listed) or long_texts.kept > long_texts.of:
        problems.append(f"{where}: kept does not match the listing")
    if long_texts.of > long_texts.k:
        problems.append(f"{where}: more texts than k")
    if long_texts.occurrences < 1 or long_texts.occurrences > field.values.count:
        problems.append(f"{where}: occurrences out of range")
    if (long_texts.requested_k is not None) and long_texts.requested_k <= long_texts.k:
        problems.append(f"{where}: requested_k must exceed k")
    if (long_texts.selection == "bottom_k") != (long_texts.hash is not None):
        problems.append(f"{where}: only a bottom_k sample names its hash")
    if long_texts.selection == "all" and long_texts.threshold is not None:
        problems.append(f"{where}: only a bottom_k sample has a threshold")
    listed_total = sum(item.count for item in long_texts.listed)
    if listed_total > long_texts.occurrences or any(
        item.count < 1 for item in long_texts.listed
    ):
        problems.append(f"{where}: a count is out of range")
    if (
        long_texts.selection == "all"
        and long_texts.kept == long_texts.of
        and listed_total != long_texts.occurrences
    ):
        problems.append(f"{where}: all counts must add up to occurrences")


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
