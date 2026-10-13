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
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsFailed,
    FieldPatternsNotApplicable,
    FieldResult,
    LengthStratum,
    LongTexts,
    Observation,
    Observations,
    PatternFamily,
    PatternToken,
    QualitySummary,
    RowSample,
    SampleEntry,
    ScanResult,
)
from tabalyst.scanner.normalization import STAGES
from tabalyst.scanner.pattern_eligibility import deciding_reason
from tabalyst.scanner.patterninfer import (
    EXAMPLES,
    GRAMMAR_NAME,
    GRAMMAR_VERSION,
    compile_signature,
    matches,
    render_signature,
)
from tabalyst.scanner.quality import OBSERVATIONS_VERSION, RULES
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
    _check_patterns(result, problems)
    _check_observations(result, problems)
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
    cut = sum(len(row.truncated) for row in sample.rows)
    reduced = sample.kept < sample.of
    if cut > sample.truncated_cells or (cut != sample.truncated_cells and not reduced):
        problems.append(f"{where}.truncated_cells: must count the cut cells")
    if middle:
        priority = RowPriority(sample.hash.seed)
        worst = max(priority.at(index) for index in middle)
        if sample.threshold is not None:
            written = int(sample.threshold, 16)
            # A Report keeps the smallest priorities of the middle (design
            # 19.4): its largest is at most the threshold of the Scan.
            if written < worst or (written != worst and not reduced):
                problems.append(
                    f"{where}.threshold: must be the largest middle priority"
                )
    elif sample.threshold is not None and not reduced:
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
    _check_normalization(field, where, problems)
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


def _check_normalization(field: FieldResult, where: str, problems: list[str]) -> None:
    """The stages in order and the ``equals`` rule: a stage that changed nothing
    takes the count of its input, and only such a stage does (design 10)."""
    where = f"{where}.normalization"
    stages = field.normalization.stages
    if [stage.stage for stage in stages] != ["raw", *STAGES]:
        problems.append(f"{where}.stages: must be raw then the stages in order")
        return
    raw = stages[0].cardinality
    cardinality = field.values.cardinality
    if raw is None or raw.status != cardinality.status:
        problems.append(f"{where}.stages[raw]: must have the status of the cardinality")
    elif isinstance(raw, Complete) and raw.value != cardinality.value:
        problems.append(f"{where}.stages[raw]: must have the cardinality's value")
    previous = stages[0]
    changes = []
    for stage in stages[1:]:
        label = f"{where}.stages[{stage.stage}]"
        if not stage.enabled:
            if (stage.changed, stage.cardinality, stage.equals) != (None, None, None):
                problems.append(f"{label}: a disabled stage has no counts")
            continue
        if stage.changed is None or not 0 <= stage.changed <= field.strings.content:
            problems.append(f"{label}: changed is out of range")
            continue
        changes.append(stage.changed)
        takes = (
            stage.changed == 0
            and previous.cardinality is not None
            and previous.cardinality.status in ("complete", "limited")
        )
        if (stage.equals is not None) != takes:
            problems.append(
                f"{label}: equals goes with a stage that changed nothing"
            )
        elif takes and (
            stage.equals != previous.stage or stage.cardinality != previous.cardinality
        ):
            problems.append(
                f"{label}: a stage that changed nothing has the count of {previous.stage}"
            )
        previous = stage
    groups = field.normalization.variant_groups
    if isinstance(groups, Complete) and not any(changes) and groups.value.groups:
        problems.append(f"{where}.variant_groups: no stage changed a string")


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


def _check_characters(field: FieldResult, where: str, problems: list[str]) -> None:
    profile = field.string_characteristics
    content = field.strings.content
    where = f"{where}.string_characteristics"
    counters = profile.model_dump(exclude={"distinct_characters", "special_characters"})
    if any(count > content for name, count in counters.items() if name != "characters"):
        problems.append(f"{where}: a counter exceeds the content strings")
    inventory = profile.special_characters
    if isinstance(inventory, Complete):
        listed = inventory.value.listed
        if inventory.value.distinct != len(listed):
            problems.append(f"{where}: distinct must equal the characters listed")
        if any(
            not 1 <= item.value_count <= item.occurrence_count <= content
            for item in listed
        ):
            problems.append(f"{where}: a special character has a count out of range")
        if any(ord(item.char) != item.codepoint for item in listed):
            problems.append(f"{where}: a codepoint does not match its character")


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
    _check_characters(field, where, problems)
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


def _check_patterns(result: ScanResult, problems: list[str]) -> None:
    """The inferred patterns: one entry per field, candidates that reconcile with
    the population and examples that match their signature (design 18.12)."""
    if result.derived is None or result.derived.patterns is None:
        return
    patterns = result.derived.patterns
    if (patterns.grammar.name, patterns.grammar.version) != (
        GRAMMAR_NAME,
        GRAMMAR_VERSION,
    ):
        problems.append("derived.patterns.grammar: not the grammar of this version")
    fields = {
        (dataset.id, field.id): field
        for dataset in result.datasets
        for field in dataset.fields
    }
    if [(entry.dataset, entry.field) for entry in patterns.fields] != list(fields):
        problems.append(
            "derived.patterns.fields: one entry per field, in the order of the fields"
        )
        return
    for entry in patterns.fields:
        _check_eligibility(entry, problems)
        if isinstance(entry, FieldPatternsFailed):
            _check_failed_patterns(entry, result, problems)
        elif isinstance(entry, FieldPatternsComplete):
            _check_field_patterns(
                entry, fields[(entry.dataset, entry.field)], result, problems
            )


def _check_eligibility(entry: FieldPatterns, problems: list[str]) -> None:
    """The eligibility of an entry agrees with its status (design 18.12): only an
    eligible field is discovered, a field that is not assessed scores 0, and
    the reason of an entry without patterns is the deciding one."""
    where = f"derived.patterns[{entry.dataset}.{entry.field}].eligibility"
    eligibility = entry.eligibility
    if not 0 <= eligibility.score <= 1 or not eligibility.reasons:
        problems.append(f"{where}: needs a score from 0 to 1 and reasons")
    if eligibility.state in ("excluded", "not_assessable") and eligibility.score:
        problems.append(f"{where}: a field that is not assessed scores 0")
    if isinstance(entry, FieldPatternsComplete) and eligibility.state != "eligible":
        problems.append(f"{where}: only an eligible field has patterns")
    if isinstance(entry, FieldPatternsNotApplicable) and (
        eligibility.state == "eligible" or entry.reason != deciding_reason(eligibility)
    ):
        problems.append(f"{where}: does not say why the field has no patterns")


def _check_failed_patterns(
    entry: FieldPatternsFailed, result: ScanResult, problems: list[str]
) -> None:
    """A failed entry points to the diagnostic that names its field."""
    where = f"derived.patterns[{entry.dataset}.{entry.field}]"
    if not 0 <= entry.diagnostic < len(result.diagnostics):
        problems.append(f"{where}: diagnostic does not exist")
        return
    diagnostic = result.diagnostics[entry.diagnostic]
    if (diagnostic.code, diagnostic.dataset, diagnostic.field) != (
        "pattern_inference_failed",
        entry.dataset,
        entry.field,
    ):
        problems.append(f"{where}: diagnostic is not its pattern_inference_failed")


def _check_field_patterns(
    entry: FieldPatternsComplete,
    field: FieldResult,
    result: ScanResult,
    problems: list[str],
) -> None:
    """The hierarchy of a field: a population that describes its samples, ids in
    order, signatures of fixed length that match their examples, and the sums
    that add up (patterns to their family, nodes to their pattern, families and
    ``other`` to the population)."""
    where = f"derived.patterns[{entry.dataset}.{entry.field}]"
    settings = result.config.pattern_inference
    samples = field.values.samples
    population = entry.population
    excluded = population.excluded
    complete = (
        samples.selection == "all"
        and "max_values" not in entry.limits
        and not (
            excluded.long_text_occurrences
            or excluded.non_string_values
            or excluded.empty_values
            or excluded.too_long_values
            or excluded.too_complex_values
        )
    )
    if population.selection != samples.selection or population.complete != complete:
        problems.append(f"{where}.population: does not describe the field's samples")
    if population.occurrences_basis != ("exact" if complete else "sample"):
        problems.append(f"{where}.population: occurrences_basis must follow the population")
    if population.distinct > population.available:
        problems.append(f"{where}.population: distinct exceeds available")
    expected_long = samples.long_texts.occurrences if samples.long_texts else 0
    if population.excluded.long_text_occurrences != expected_long:
        problems.append(f"{where}.population.excluded: long_text_occurrences differs")
    if population.distinct > settings.max_values:
        problems.append(f"{where}.population: more values than max_values")
    if len(entry.families) > settings.max_families:
        problems.append(f"{where}: more families than max_families")
    values = {item.id: item.value for item in samples.listed}
    if samples.by_length is not None:
        values.update({item.id: item.value for item in samples.by_length.listed})
    # A Report base keeps fewer values: its examples may name values it dropped.
    resolvable = samples.kept == samples.of
    published = 0
    distinct = occurrences = 0
    for number, family in enumerate(entry.families, 1):
        label = f"{where}.families[{family.id}]"
        if family.id != f"f{number}":
            problems.append(f"{label}: family ids must be f1, f2, ... in order")
        distinct += family.d
        occurrences += family.o
        published += _check_family(
            family, label, settings.max_patterns_per_family, values if resolvable else None,
            problems,
        )
    if published > settings.max_patterns:
        problems.append(f"{where}: more patterns and nodes than max_patterns")
    if (distinct + entry.other.d, occurrences + entry.other.o) != (
        population.distinct,
        population.occurrences,
    ):
        problems.append(f"{where}: families and other must add up to the population")


def _check_family(
    family: PatternFamily,
    label: str,
    per_family: int,
    values: dict[int, str] | None,
    problems: list[str],
) -> int:
    """The checks of one family; returns the patterns and nodes it publishes."""
    if len(family.patterns) > per_family:
        problems.append(f"{label}: more patterns than max_patterns_per_family")
    if len(family.examples) > EXAMPLES or family.examples != sorted(family.examples):
        problems.append(f"{label}: examples are the smallest ids, at most {EXAMPLES}")
    if family.composition and family.composition[0] != family.key:
        problems.append(f"{label}: composition must start with the key of the family")
    for table in family.tables:
        if len(table.cells) > per_family:
            problems.append(f"{label}: a table has more cells than max_patterns_per_family")
    published = len(family.patterns)
    left_out = sum(cell.d for table in family.tables for cell in table.cells)
    left_out += sum(table.others.d for table in family.tables)
    left_out_o = sum(cell.o for table in family.tables for cell in table.cells)
    left_out_o += sum(table.others.o for table in family.tables)
    if (
        sum(pattern.d for pattern in family.patterns) + left_out,
        sum(pattern.o for pattern in family.patterns) + left_out_o,
    ) != (family.d, family.o):
        problems.append(f"{label}: patterns and tables must add up to the family")
    for number, pattern in enumerate(family.patterns, 1):
        name = f"{label}.patterns[{pattern.id}]"
        published += len(pattern.nodes)
        if pattern.id != f"{family.id}.p{number}":
            problems.append(f"{name}: pattern ids must be p1, p2, ... in order")
        _check_signature(pattern.signature, pattern.render, name, problems)
        if len(pattern.examples) > EXAMPLES or pattern.examples != sorted(pattern.examples):
            problems.append(f"{name}: examples are the smallest ids, at most {EXAMPLES}")
        if pattern.nodes and (
            sum(node.d for node in pattern.nodes),
            sum(node.o for node in pattern.nodes),
        ) != (pattern.d, pattern.o):
            problems.append(f"{name}: nodes must add up to the pattern")
        for position, node in enumerate(pattern.nodes, 1):
            node_name = f"{name}.nodes[{node.id}]"
            if node.id != f"{pattern.id}.n{position}" or node.parent != pattern.id:
                problems.append(f"{node_name}: node id or parent is wrong")
            if node.role != ("principal" if position == 1 else "secondary"):
                problems.append(f"{node_name}: only the first node is principal")
            _check_signature(node.signature, node.render, node_name, problems)
        if values is not None:
            matcher = compile_signature(pattern.signature)
            for example in pattern.examples:
                value = values.get(example)
                if value is None:
                    problems.append(f"{name}: example {example} is not a sampled value")
                elif not matches(matcher, value):
                    problems.append(f"{name}: example {example} does not match")
    return published


def _check_signature(
    signature: list[PatternToken], render: str, name: str, problems: list[str]
) -> None:
    if render != render_signature(signature):
        problems.append(f"{name}: render does not describe the signature")
    if any(
        token.min != token.max
        or token.min < 1
        or (token.kind == "literal") != (token.text is not None)
        for token in signature
    ):
        problems.append(f"{name}.signature: invalid token")


_STATUS_RANK = {"confirmed_issue": 0, "candidate_anomaly": 1, "informational": 2}


def _check_observations(result: ScanResult, problems: list[str]) -> None:
    """The observations: ids, references, the summaries and their flags, and the
    counts that the facts give again (design 18.13)."""
    block = result.observations
    settings = result.config.observations
    if block is None:
        if settings.enabled and not any(
            diagnostic.code == "observations_failed" for diagnostic in result.diagnostics
        ):
            problems.append(
                "observations: missing although scan.observations.enabled is set"
            )
        return
    if not settings.enabled:
        problems.append("observations: present although scan.observations is disabled")
        return
    if block.version != OBSERVATIONS_VERSION:
        problems.append("observations.version: not the version of these rules")
    datasets = {dataset.id: dataset for dataset in result.datasets}
    if [summary.dataset for summary in block.datasets] != list(datasets):
        problems.append("observations.datasets: one summary per dataset, in order")
        return
    if block.summary.dataset is not None:
        problems.append("observations.summary: the whole scan has no dataset")
    _check_summaries(block.summary, block.datasets, problems)
    maximum = settings.max_items
    if len(block.items) > maximum or len(block.limits) > maximum:
        problems.append("observations: more items than scan.observations.max_items")
    expected_limits = block.summary.limits
    expected_items = (
        block.summary.informational
        + block.summary.candidate_anomalies
        + block.summary.confirmed_issues
    )
    complete = (
        len(block.items) == expected_items and len(block.limits) == expected_limits
    )
    if block.truncated == complete:
        problems.append("observations.truncated: must say whether the lists are cut")
    if [item.id for item in block.items] != [
        f"o{number}" for number in range(1, len(block.items) + 1)
    ]:
        problems.append("observations.items: ids must be o1, o2, ... in order")
    if [limit.id for limit in block.limits] != [
        f"l{number}" for number in range(1, len(block.limits) + 1)
    ]:
        problems.append("observations.limits: ids must be l1, l2, ... in order")
    ranks = [
        _STATUS_RANK[RULES[item.rule][1]] for item in block.items if item.rule in RULES
    ]
    if ranks != sorted(ranks):
        problems.append("observations.items: confirmed issues, candidates, remarks")
    for limit in block.limits:
        _check_reference(
            limit.dataset, limit.field, datasets, f"limits[{limit.id}]", problems
        )
        if limit.diagnostic is not None and not (
            0 <= limit.diagnostic < len(result.diagnostics)
        ):
            problems.append(f"observations.limits[{limit.id}]: diagnostic does not exist")
    for item in block.items:
        _check_observation(item, result, datasets, expected_limits, problems)
    if complete:
        _check_recount(block, problems)
        _check_facts(block, result, datasets, problems)


def _check_summaries(
    summary: QualitySummary, datasets: list[QualitySummary], problems: list[str]
) -> None:
    for where, entry in [("summary", summary)] + [
        (f"datasets[{item.dataset}]", item) for item in datasets
    ]:
        issues = entry.candidate_anomalies + entry.confirmed_issues
        if (
            entry.has_observations != bool(entry.informational + issues)
            or entry.has_quality_issues != bool(issues)
            or entry.has_limits != bool(entry.limits)
        ):
            problems.append(f"observations.{where}: flags must follow the counts")
    for name in ("informational", "candidate_anomalies", "confirmed_issues", "limits"):
        if getattr(summary, name) < sum(getattr(item, name) for item in datasets):
            problems.append(f"observations.summary.{name}: less than the datasets add up")


def _check_reference(
    dataset: str | None,
    field_id: str | None,
    datasets: dict[str, DatasetResult],
    where: str,
    problems: list[str],
) -> None:
    if dataset is None:
        if field_id is not None:
            problems.append(f"observations.{where}: a field needs its dataset")
    elif dataset not in datasets:
        problems.append(f"observations.{where}: unknown dataset")
    elif field_id is not None and field_id not in {
        field.id for field in datasets[dataset].fields
    }:
        problems.append(f"observations.{where}: unknown field")


def _check_observation(
    item: Observation,
    result: ScanResult,
    datasets: dict[str, DatasetResult],
    limits: int,
    problems: list[str],
) -> None:
    where = f"items[{item.id}]"
    if item.rule not in RULES:
        problems.append(f"observations.{where}: unknown rule {item.rule}")
        return
    if (item.category, item.status) != RULES[item.rule]:
        problems.append(f"observations.{where}: category and status follow the rule")
    _check_reference(item.dataset, item.field, datasets, where, problems)
    if item.count < 1 or (item.of is not None and item.count > item.of):
        problems.append(f"observations.{where}: count is out of range")
    if len(item.records) > result.config.limits.max_listed_records:
        problems.append(f"observations.{where}: more records than max_listed_records")
    if any(not 0 <= index < len(result.diagnostics) for index in item.diagnostics):
        problems.append(f"observations.{where}: diagnostic does not exist")
    known = {f"l{number}" for number in range(1, limits + 1)}
    if not known.issuperset(item.limited_by):
        problems.append(f"observations.{where}: limited_by names no limit")
    if item.patterns:
        entries = {
            (entry.dataset, entry.field): entry
            for entry in (
                result.derived.patterns.fields
                if result.derived is not None and result.derived.patterns is not None
                else ()
            )
        }
        entry = entries.get((item.dataset, item.field))
        ids = (
            {candidate.id for candidate in entry.candidates}
            if isinstance(entry, FieldPatternsComplete)
            else set()
        )
        if not ids.issuperset(item.patterns):
            problems.append(f"observations.{where}: patterns names no candidate")


def _check_recount(block: Observations, problems: list[str]) -> None:
    """The listed items agree with the summaries they were counted into."""
    for summary in [block.summary, *block.datasets]:
        chosen = [
            item
            for item in block.items
            if summary.dataset is None or item.dataset == summary.dataset
        ]
        counts = {
            status: sum(1 for item in chosen if item.status == status)
            for status in _STATUS_RANK
        }
        listed = sum(
            1
            for limit in block.limits
            if summary.dataset is None or limit.dataset == summary.dataset
        )
        if (
            counts["informational"],
            counts["candidate_anomaly"],
            counts["confirmed_issue"],
            listed,
        ) != (
            summary.informational,
            summary.candidate_anomalies,
            summary.confirmed_issues,
            summary.limits,
        ):
            problems.append(
                f"observations.summary[{summary.dataset}]: counts differ from the items"
            )


def _check_facts(
    block: Observations,
    result: ScanResult,
    datasets: dict[str, DatasetResult],
    problems: list[str],
) -> None:
    """The counts the facts of the scan give again, for the rules that are one
    counter (QUAL-02: an observation names its source)."""
    for item in block.items:
        where = f"observations.items[{item.id}]"
        expected: int | None = None
        if item.rule == "excluded_records":
            expected = result.scope.records_excluded
        elif item.dataset in datasets:
            dataset = datasets[item.dataset]
            fields = {field.id: field for field in dataset.fields}
            field = fields.get(item.field) if item.field is not None else None
            if item.rule == "duplicate_rows":
                count = dataset.records.duplicates.count
                expected = (
                    count.value
                    if isinstance(count, Complete)
                    else getattr(count, "lower_bound", None)
                )
            elif field is not None and item.rule == "missing_values":
                expected = field.missing.count
            elif field is not None and item.rule in (
                "trimmed_cells",
                "collapsed_whitespace",
            ):
                stage = "trim" if item.rule == "trimmed_cells" else "collapse_whitespace"
                expected = next(
                    (
                        entry.changed
                        for entry in field.normalization.stages
                        if entry.stage == stage
                    ),
                    None,
                )
        if expected is not None and item.count != expected:
            problems.append(f"{where}: count differs from the facts ({expected})")
