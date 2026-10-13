# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The facts of one field that the analyzers read (design 20.5).

``scan_facts`` reads a finished Scan once and gives every analyzer the same
immutable view, so no analyzer walks the document or sees a sampled value.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from tabalyst.scanner.config import DetectorSettings
from tabalyst.scanner.convention_rule import NumberRule, single_reading
from tabalyst.scanner.detectors.registry import replayable
from tabalyst.scanner.models import (
    CardinalityComplete,
    CardinalityLimited,
    DatasetResult,
    DetectorComplete,
    FamilyPattern,
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsFailed,
    FieldPatternsNotApplicable,
    FieldResult,
    ItemsSegment,
    PatternNode,
    ScanResult,
)
from tabalyst.scanner.patterninfer import settings_digest


@dataclass(frozen=True, slots=True)
class PatternFacts:
    """The inferred patterns of a field (design 18.12)."""

    status: str
    reason: str | None
    # How many patterns the hierarchy publishes (families and their patterns).
    patterns: int
    basis: str | None
    # The distinct values no pattern holds.
    other_distinct: int
    # The facets that the validation counts in a table (a facet is counted once
    # in a family) and the patterns and nodes it keeps a counter for.
    facets: int = 0
    nodes: int = 0
    # What produced the entry: the versions of the grammar and of the algorithm and
    # the digest of the settings of the discovery. They are part of the key of the
    # validation, so a result is never reused for a tree another discovery made.
    grammar_version: int = 0
    algorithm_version: int = 0
    settings_sha256: str = ""


@dataclass(frozen=True, slots=True)
class TemporalFacts:
    """The temporal values of a field: their kinds and, for a single date or
    datetime kind, the span in days and whether the Scan already counts years.
    ``ambiguous`` values are left out of all that; ``day_first`` and
    ``month_first`` count the unambiguous dates that only one order reads, from
    which ``inferred`` gives the reading of the ambiguous ones, which the second
    pass applies and so counts the dates again."""

    count: int
    kinds: tuple[str, ...]
    span_days: int | None
    years_counted: bool
    ambiguous: int = 0
    day_first: int = 0
    month_first: int = 0

    def inferred(self, minimum: int = 1) -> str | None:
        """The order the evidence gives the ambiguous dates (``order_of``)."""
        return order_of({"DMY": self.day_first, "MDY": self.month_first}, minimum)


def order_of(evidence: dict[str, int], minimum: int = 1) -> str | None:
    """``DMY`` when at least ``minimum`` dates read day-month only and none
    month-day, ``MDY`` for the opposite, else ``None``: with both orders the
    column is mixed, and with fewer than ``minimum`` the proof is too thin."""
    return single_reading(
        {"DMY": evidence.get("DMY", 0), "MDY": evidence.get("MDY", 0)}, minimum
    )


def date_evidence(field: FieldResult) -> dict[str, int]:
    """The unambiguous dates of a field by the order that alone reads them
    (``DMY``, ``MDY``), as the date detector of the Scan counted them, whatever
    their separator. Empty when the Scan has no ambiguity to report for the field
    or an order was given by the configuration."""
    for result in field.detectors:
        if result.id != "date" or not isinstance(result, DetectorComplete):
            continue
        ambiguity = result.details.get("ambiguity")
        if (
            not isinstance(ambiguity, dict)
            or not ambiguity.get("count")
            or ambiguity.get("resolution") is not None
        ):
            return {}
        evidence = ambiguity.get("evidence") or {}
        return {order: int(evidence.get(order, 0)) for order in ("DMY", "MDY")}
    return {}


def inferred_order(field: FieldResult, minimum: int = 1) -> str | None:
    """The order (``DMY`` or ``MDY``) that the unambiguous dates of a field give
    its ambiguous ones, or ``None``.

    The date detector of the Scan counts, as evidence, the values that only one
    order reads (``25/03/2020``, whatever the separator; a year-first date is
    never ambiguous and counts for neither). When some read as day-month and none
    as month-day, or the opposite, the ambiguous values (``03/04/2020``) are read
    that way, when at least ``minimum`` dates prove it. With both orders, or
    fewer proofs, they stay ambiguous. An order the configuration gave
    (``ambiguous_order``) leaves nothing to infer."""
    return order_of(date_evidence(field), minimum)


# The detectors whose values carry a number and a marker or a unit (lot 14).
MEASURE_DETECTORS = ("currency", "percentage", "quantity")
# Markers a field of units may hold when the Scan stopped counting them: the
# default of ``detectors.quantity.max_tracked_units``.
UNTRACKED_MARKERS = 10_000


@dataclass(frozen=True, slots=True)
class MeasureFacts:
    """What one detector of values with a marker or a unit found in a field:
    its coverage and the number of distinct markers it counted (a currency
    marker, ``%`` or a unit). ``convention`` is the one its unambiguous values
    prove for the ambiguous ones (design 20.28), ``None`` when it proves none
    or the configuration decided."""

    detector: str
    eligible: int
    matched: int
    ambiguous: int
    invalid: int
    not_tested: int
    markers: int
    convention: str | None = None

    @property
    def readable(self) -> int:
        """The values the extraction reads as numbers: the ones the detector
        matched and, with a convention, the ambiguous ones it now resolves."""
        return self.matched + (self.ambiguous if self.convention else 0)


@dataclass(frozen=True, slots=True)
class DetectorFacts:
    """The coverage of a detector the second pass can replay (lot 15)."""

    detector: str
    eligible: int
    matched: int
    ambiguous: int
    invalid: int
    not_matched: int
    not_tested: int


@dataclass(frozen=True, slots=True)
class ArrayFacts:
    """What the Scan counted of the arrays of a field (design 20.33): the arrays,
    those without an item, the shortest and the longest, and all the items."""

    count: int
    empty: int
    min_length: int
    max_length: int
    total_items: int


# The detectors whose sensitive values the second pass tells the class of
# (design 20.35).
CLASSIFIED_DETECTORS = ("ip_address", "phone")


def lacks_values(dataset: DatasetResult, field: FieldResult) -> bool:
    """Whether some records of the dataset have no value for the field, which a
    field that is not repeated in a record makes a plain subtraction: the records
    minus the values the Scan counted (design 20.30)."""
    return field.values.count < dataset.record_count


def repeats(field: FieldResult) -> bool:
    """Whether the path of the field repeats in a record (items of an array),
    which the analyses by record cannot count."""
    return any(isinstance(segment, ItemsSegment) for segment in field.path)


def matrix_members(dataset: DatasetResult) -> list[FieldResult]:
    """The fields that take part in the missing values counted together (design
    20.31), in document order: those that have a value and lack one in some
    records, not repeated in a record, with their values in the document (exposure
    ``mask`` or ``hide`` leaves a field out, as it does every second-pass
    analysis)."""
    return [
        field
        for field in dataset.fields
        if field.values.count > 0
        and lacks_values(dataset, field)
        and not repeats(field)
        and field.exposure not in ("mask", "hide")
    ]


@dataclass(frozen=True, slots=True)
class FieldFacts:
    """Everything the planner knows about a field. ``where`` is the location of
    the field in the Scan (``datasets/<id>/fields/<id>``)."""

    dataset: str
    field: str
    display: str
    name: str
    where: str
    values: int
    technical_type: str
    # None, "show", "mask" or "hide": a masked or hidden field is never read again.
    exposure: str | None
    cardinality: str
    distinct: int | None
    distinct_lower_bound: int | None
    distinct_estimate: float | None
    frequencies: str
    frequencies_distinct: int | None
    frequencies_truncated: bool
    numeric: str
    numeric_min: float | None
    numeric_max: float | None
    # Numbers the scan counted for the field, and whether its path repeats in a
    # record (items of an array), which no pair of columns may use.
    numeric_count: int
    repeated: bool
    lengths: str
    min_length: int | None
    mean_length: float | None
    max_length: int | None
    long_text_occurrences: int
    samples_listed: int
    # Every distinct original value is listed with its exact count.
    samples_all: bool
    temporal: TemporalFacts | None
    temporal_status: str
    patterns: PatternFacts | None
    # The detectors of values with a marker that read at least one value.
    measures: tuple[MeasureFacts, ...] = ()
    # The replayable detectors that read at least one value.
    detectors: tuple[DetectorFacts, ...] = ()
    # Records of the dataset, and the fields of it that miss a value together
    # with others (``matrix_members``): whether this one is among them and how many.
    records: int = 0
    matrix_member: bool = False
    matrix_size: int = 0
    # Records the scan left out (a tolerant policy): the numbers of the source
    # then have gaps and no longer give the place of a record among the analyzed.
    records_excluded: int = 0
    # The arrays of the field, and for an object field the occurrences, the keys
    # the Scan found below it and whether they are not all present in every
    # object; the format of the source and whether the Scan stopped tracking
    # paths of the dataset (a set of keys could then hold keys it never named).
    arrays: ArrayFacts | None = None
    objects: int = 0
    object_keys: int = 0
    object_varies: bool = False
    source_format: str = ""
    untracked_paths: bool = False
    # Fields of the dataset: the observations of a record the sets of keys sweep.
    dataset_fields: int = 0
    # Content strings of the field, and the sensitive detectors that read some.
    strings_content: int = 0
    classified: tuple[str, ...] = ()
    # Characters the Scan's character map lists (``limits.max_top_characters``): the
    # second pass lists as many.
    top_characters: int = 20
    # Status of the Scan's character map of the field (``complete`` when it has none to say).
    character_map: str = "complete"

    @property
    def withheld(self) -> bool:
        """Whether exposure keeps the values of the field out of the document."""
        return self.exposure in ("mask", "hide")

    @property
    def cells(self) -> int:
        """The occurrences an analysis of the field reads: its values, or its
        arrays or objects, which hold none of their own."""
        return max(self.values, 0 if self.arrays is None else self.arrays.count, self.objects)

    @property
    def long_texts_only(self) -> bool:
        """Whether every stored value is a long text, which has no distinct
        count or histogram of its own (LONG-05)."""
        return self.long_text_occurrences > 0 and self.samples_listed == 0


def _temporal(field: FieldResult) -> tuple[str, TemporalFacts | None]:
    envelope = field.temporal
    if envelope.status != "complete":
        return envelope.status, None
    stats = envelope.value
    kinds = tuple(kind.kind for kind in stats.kinds)
    span: int | None = None
    years = False
    if len(stats.kinds) == 1 and stats.kinds[0].kind in ("date", "datetime_naive", "datetime_aware"):
        kind = stats.kinds[0]
        try:
            span = (
                datetime.fromisoformat(kind.max).date()
                - datetime.fromisoformat(kind.min).date()
            ).days
        except ValueError:
            span = None
        years = kind.years is not None
    evidence = date_evidence(field)
    return "complete", TemporalFacts(
        stats.count, kinds, span, years, stats.ambiguous, evidence.get("DMY", 0), evidence.get("MDY", 0)
    )


def _markers(result: DetectorComplete) -> int:
    """The distinct markers a detector of values with a marker counted."""
    details = result.details
    if result.id == "percentage":
        return 1
    if result.id == "currency":
        currencies = details.get("currencies")
        return len(currencies) if isinstance(currencies, dict) else UNTRACKED_MARKERS
    units = details.get("units")
    if isinstance(units, dict) and units.get("status") == "complete":
        return int(units["value"]["distinct"])
    return UNTRACKED_MARKERS


def _evidence(result: DetectorComplete) -> dict[str, int]:
    """The unambiguous values of a detector by the convention that alone reads
    them (``details.ambiguity.evidence``), empty when it has none to report."""
    ambiguity = result.details.get("ambiguity")
    evidence = ambiguity.get("evidence") if isinstance(ambiguity, dict) else None
    if not isinstance(evidence, dict):
        return {}
    return {name: int(count) for name, count in evidence.items()}


def _convention(rule: NumberRule, result: DetectorComplete) -> str | None:
    """The convention that reads the values a detector of values with a marker
    writes ambiguously. A ``dot`` proof changes nothing when the Scan counted no
    ambiguous value and tested every one, while a ``comma`` proof also reads
    ``d.ddd`` as thousands, which the Scan does not count for these detectors."""
    convention = rule.convention(_evidence(result))
    coverage = result.coverage
    if convention == "dot" and not (coverage.ambiguous or coverage.not_tested):
        return None
    return convention


def _measure_rules(detectors: DetectorSettings) -> dict[str, NumberRule]:
    """The rule of the convention of each detector of values with a marker, from
    the configuration the Scan recorded (read once for the whole Scan)."""
    return {
        name: NumberRule.of(getattr(detectors, name).model_dump())
        for name in MEASURE_DETECTORS
    }


def _measures(field: FieldResult, rules: dict[str, NumberRule]) -> tuple[MeasureFacts, ...]:
    found = []
    for result in field.detectors:
        if result.id not in MEASURE_DETECTORS or not isinstance(result, DetectorComplete):
            continue
        coverage = result.coverage
        if not coverage.matched:
            continue
        found.append(
            MeasureFacts(
                detector=result.id,
                eligible=coverage.eligible,
                matched=coverage.matched,
                ambiguous=coverage.ambiguous,
                invalid=coverage.invalid,
                not_tested=coverage.not_tested,
                markers=_markers(result),
                convention=_convention(rules[result.id], result),
            )
        )
    return tuple(found)


def _detectors(field: FieldResult) -> tuple[DetectorFacts, ...]:
    ids = replayable()
    found = []
    for result in field.detectors:
        if result.id not in ids or not isinstance(result, DetectorComplete):
            continue
        coverage = result.coverage
        if not coverage.matched and not coverage.ambiguous:
            continue
        found.append(
            DetectorFacts(
                detector=result.id,
                eligible=coverage.eligible,
                matched=coverage.matched,
                ambiguous=coverage.ambiguous,
                invalid=coverage.invalid,
                not_matched=coverage.not_matched,
                not_tested=coverage.not_tested,
            )
        )
    return tuple(found)


def _patterns(
    index: dict[tuple[str, str], FieldPatterns],
    dataset: str,
    field: str,
    provenance: tuple[int, int, str],
) -> PatternFacts | None:
    entry = index.get((dataset, field))
    if entry is None:
        return None
    if isinstance(entry, FieldPatternsComplete):
        patterns = entry.all_patterns()
        basis = (
            None if not patterns else "all_distinct" if entry.population.complete else "sample"
        )
        return PatternFacts(
            "complete",
            None,
            len(patterns),
            basis,
            entry.outside_patterns()[0],
            *_hierarchy_size(entry),
            grammar_version=provenance[0],
            algorithm_version=provenance[1],
            settings_sha256=provenance[2],
        )
    assert isinstance(entry, (FieldPatternsNotApplicable, FieldPatternsFailed))
    return PatternFacts(
        entry.status,
        entry.reason,
        0,
        None,
        0,
        grammar_version=provenance[0],
        algorithm_version=provenance[1],
        settings_sha256=provenance[2],
    )


def _hierarchy_size(entry: FieldPatternsComplete) -> tuple[int, int]:
    """The facets counted in a table by the validation of a field and its patterns
    and nodes: a facet read by the nodes of a family or listed in one of its tables
    is one table."""

    def nodes(items: Sequence[FamilyPattern | PatternNode], facets: set[str]) -> int:
        total = len(items)
        for item in items:
            for child in item.nodes:
                if child.facet != "composition":
                    facets.add(child.facet)
            total += nodes(item.nodes, facets)
        return total

    facets_total = nodes_total = 0
    for family in entry.families:
        facets = {table.facet for table in family.tables if table.facet != "lengths"}
        nodes_total += nodes(family.patterns, facets)
        facets_total += len(facets)
    return facets_total, nodes_total


def _arrays(field: FieldResult) -> ArrayFacts | None:
    stats = field.arrays
    if stats is None:
        return None
    return ArrayFacts(
        count=stats.count,
        empty=stats.empty,
        min_length=stats.min_length,
        max_length=stats.max_length,
        total_items=stats.total_items,
    )


def _classified(field: FieldResult) -> tuple[str, ...]:
    """The detectors of ``CLASSIFIED_DETECTORS`` that matched a value of the
    field."""
    return tuple(
        result.id
        for result in field.detectors
        if result.id in CLASSIFIED_DETECTORS
        and isinstance(result, DetectorComplete)
        and result.coverage.matched
    )


def _facts(
    dataset: DatasetResult,
    field: FieldResult,
    index: dict[tuple[str, str], FieldPatterns],
    rules: dict[str, NumberRule],
    members: frozenset[str],
    excluded: int,
    children: dict[str, list[FieldResult]],
    source_format: str,
    provenance: tuple[int, int, str],
    top_characters: int,
    character_map: str,
) -> FieldFacts:
    cardinality = field.values.cardinality
    distinct: int | None = None
    lower: int | None = None
    estimate: float | None = None
    if isinstance(cardinality, CardinalityComplete):
        distinct = cardinality.value
    elif isinstance(cardinality, CardinalityLimited):
        lower = cardinality.lower_bound
        if cardinality.estimate is not None:
            estimate = cardinality.estimate.value
    frequencies = field.values.frequencies
    numeric = field.numeric
    lengths = field.string_lengths
    samples = field.values.samples
    temporal_status, temporal = _temporal(field)
    return FieldFacts(
        dataset=dataset.id,
        field=field.id,
        display=field.display,
        name=field.name,
        where=f"datasets/{dataset.id}/fields/{field.id}",
        values=field.values.count,
        technical_type=field.technical_type.type,
        exposure=field.exposure,
        cardinality=cardinality.status,
        distinct=distinct,
        distinct_lower_bound=lower,
        distinct_estimate=estimate,
        frequencies=frequencies.status,
        frequencies_distinct=(
            frequencies.value.distinct if frequencies.status == "complete" else None
        ),
        frequencies_truncated=(
            frequencies.value.truncated if frequencies.status == "complete" else False
        ),
        numeric=numeric.status,
        numeric_min=numeric.value.min if numeric.status == "complete" else None,
        numeric_max=numeric.value.max if numeric.status == "complete" else None,
        numeric_count=numeric.value.count if numeric.status == "complete" else 0,
        repeated=repeats(field),
        lengths=lengths.status,
        min_length=lengths.value.min_length if lengths.status == "complete" else None,
        mean_length=float(lengths.value.mean_length) if lengths.status == "complete" else None,
        max_length=lengths.value.max_length if lengths.status == "complete" else None,
        long_text_occurrences=(
            0 if samples.long_texts is None else samples.long_texts.occurrences
        ),
        samples_listed=len(samples.listed),
        samples_all=(
            samples.selection == "all"
            and samples.kept == samples.of
            and samples.long_texts is None
        ),
        temporal=temporal,
        temporal_status=temporal_status,
        patterns=_patterns(index, dataset.id, field.id, provenance),
        measures=_measures(field, rules),
        detectors=_detectors(field),
        records=dataset.record_count,
        matrix_member=field.id in members,
        matrix_size=len(members),
        records_excluded=excluded,
        arrays=_arrays(field),
        objects=field.native_types.get("object", 0),
        object_keys=len(children.get(field.id, ())),
        object_varies=any(
            child.presence.absent != 0 for child in children.get(field.id, ())
        ),
        source_format=source_format,
        untracked_paths=dataset.structure.untracked_observations > 0,
        dataset_fields=len(dataset.fields),
        strings_content=field.strings.content,
        classified=_classified(field),
        top_characters=top_characters,
        character_map=character_map,
    )


# The root of the records of a JSON source is no field of the Scan, yet the sets
# of keys of a record are the first thing to know of it: the plan names it ``$``,
# the way the root is displayed (design 20.33).
ROOT_FIELD = "$"


def root_facts(scan: ScanResult) -> list[FieldFacts]:
    """The facts of the root of the records of each dataset whose records are all
    objects (JSON and JSONL), one per dataset; none for a table."""
    if scan.source.format not in ("json", "jsonl"):
        return []
    roots: list[FieldFacts] = []
    for dataset in scan.datasets:
        if not dataset.record_count or dataset.record_types.get("object", 0) != dataset.record_count:
            continue
        top = [field for field in dataset.fields if field.parent is None]
        roots.append(
            FieldFacts(
                dataset=dataset.id,
                field=ROOT_FIELD,
                display=ROOT_FIELD,
                name=ROOT_FIELD,
                where=f"datasets/{dataset.id}/fields/{ROOT_FIELD}",
                values=0,
                technical_type="object",
                exposure=None,
                cardinality="not_applicable",
                distinct=None,
                distinct_lower_bound=None,
                distinct_estimate=None,
                frequencies="not_applicable",
                frequencies_distinct=None,
                frequencies_truncated=False,
                numeric="not_applicable",
                numeric_min=None,
                numeric_max=None,
                numeric_count=0,
                repeated=False,
                lengths="not_applicable",
                min_length=None,
                mean_length=None,
                max_length=None,
                long_text_occurrences=0,
                samples_listed=0,
                samples_all=False,
                temporal=None,
                temporal_status="not_applicable",
                patterns=None,
                records=dataset.record_count,
                records_excluded=scan.scope.records_excluded,
                objects=dataset.record_count,
                object_keys=len(top),
                object_varies=any(child.presence.absent != 0 for child in top),
                source_format=scan.source.format,
                untracked_paths=dataset.structure.untracked_observations > 0,
                dataset_fields=len(dataset.fields),
            )
        )
    return roots


def scan_facts(scan: ScanResult) -> list[FieldFacts]:
    """The facts of every field of the Scan, in document order."""
    index = (
        {}
        if scan.derived is None or scan.derived.patterns is None
        else {
            (entry.dataset, entry.field): entry for entry in scan.derived.patterns.fields
        }
    )
    rules = _measure_rules(scan.config.detectors)
    maps = (
        {}
        if scan.derived is None or scan.derived.characters is None
        else {
            (entry.dataset, entry.field): entry.characters.status
            for entry in scan.derived.characters.fields
        }
    )
    grammar, algorithm = (
        (scan.derived.patterns.grammar.version, scan.derived.patterns.algorithm.version)
        if scan.derived is not None and scan.derived.patterns is not None
        else (0, 0)
    )
    provenance = (grammar, algorithm, settings_digest(scan.config.pattern_inference))
    facts: list[FieldFacts] = []
    for dataset in scan.datasets:
        members = frozenset(field.id for field in matrix_members(dataset))
        children: dict[str, list[FieldResult]] = {}
        for field in dataset.fields:
            if field.parent is not None:
                children.setdefault(field.parent, []).append(field)
        facts.extend(
            _facts(
                dataset,
                field,
                index,
                rules,
                members,
                scan.scope.records_excluded,
                children,
                scan.source.format,
                provenance,
                scan.config.limits.max_top_characters,
                maps.get((dataset.id, field.id), "complete"),
            )
            for field in dataset.fields
        )
    return facts
