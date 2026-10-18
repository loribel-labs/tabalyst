# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Finalized, immutable scan results (design sections 8 and 16).

Blocks introduced by later lots are absent until their lot, then always
present, with an envelope status when they do not apply.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from tabalyst.scanner.classify.models import Classification
from tabalyst.scanner.config import MissingCategory, ScalarType, ScanConfig
from tabalyst.scanner.observations import DatasetKind, NativeType

T = TypeVar("T")

FORMAT = "tabalyst.scan"
FORMAT_VERSION = "0.2.0"
FORMAT_REVISION = 4


class ScanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# Measure envelopes -----------------------------------------------------------


class Complete(ScanModel, Generic[T]):
    status: Literal["complete"] = "complete"
    value: T


# ``Any``: a serialized model is a plain dict whose values are JSON data.
def _omit_none(data: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """Drop the optional members that carry no information (absent is not
    ``null``: the contract names them only when they are known)."""
    for name in names:
        if data.get(name, 0) is None:
            del data[name]
    return data


class Limited(ScanModel):
    status: Literal["limited"] = "limited"
    reason: str
    limit: int
    lower_bound: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unproven_bound(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("lower_bound",))


class NotApplicable(ScanModel):
    status: Literal["not_applicable"] = "not_applicable"
    reason: str


class Disabled(ScanModel):
    status: Literal["disabled"] = "disabled"


class Failed(ScanModel):
    status: Literal["failed"] = "failed"
    reason: str
    diagnostic: int


def measure(value_type: Any) -> Any:
    """Envelope of a limitable measure whose complete value is ``value_type``."""
    return Annotated[
        Complete[value_type] | Limited | NotApplicable | Disabled | Failed,
        Field(discriminator="status"),
    ]


IntMeasure = measure(int)

# Accuracy of a value or of the identity of the values it counts (design 18.1):
# ``exact``, ``estimated`` by a named method, ``fingerprint_based`` (equality of
# a digest, not of the whole value) or ``unknown``.
Accuracy = Literal["exact", "estimated", "fingerprint_based", "partial", "unknown"]


class EstimatePart(ScanModel):
    """One of the two disjoint domains of an estimate that adds up: the values
    stored in the sample (``values``) and the long texts (``long_texts``),
    each exact or estimated by KMV (design 18.6)."""

    domain: Literal["values", "long_texts"]
    accuracy: Literal["exact", "estimated"]
    value: float
    relative_standard_error: float
    k: int | None = None
    theta_hex: str | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("k", "theta_hex"))


class CardinalityEstimate(ScanModel):
    """KMV estimate of the distinct original values (design 18.5).

    ``value`` is held within the certain bounds of the envelope;
    ``unclamped_value`` is the raw estimator, present only when a bound
    changed it. ``theta_hex`` (the sample threshold) is absent for a sensitive
    field: it is the priority of one of its values. A field with long texts
    has two disjoint domains: ``parts`` gives each (the estimate is their sum)
    and ``k`` and ``theta_hex`` are then those of the parts.
    """

    accuracy: Literal["estimated"] = "estimated"
    method: Literal["kmv"]
    value: float
    unclamped_value: float | None = None
    relative_standard_error: float
    k: int | None = None
    theta_hex: str | None = None
    parts: list[EstimatePart] | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self), ("unclamped_value", "k", "theta_hex", "parts")
        )


class CardinalityComplete(Complete[int]):
    """Exact distinct count of the original values (design 9.1)."""

    accuracy: Accuracy
    domain: str
    identity_accuracy: Accuracy


class CardinalityLimited(Limited):
    """Distinct count that stopped being tracked (design 9.1).

    ``upper_bound`` is the certain maximum (the analyzed values);
    ``threshold_reached_at_record`` and ``overflow_detected_at_record`` are the
    records where the table reached its limit T and where T + 1 values were
    proven, for the reason ``distinct_limit`` only.
    """

    domain: str
    identity_accuracy: Accuracy
    upper_bound: int | None = None
    threshold_reached_at_record: int | None = None
    overflow_detected_at_record: int | None = None
    estimate: CardinalityEstimate | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            (
                "lower_bound",
                "upper_bound",
                "threshold_reached_at_record",
                "overflow_detected_at_record",
                "estimate",
            ),
        )


Cardinality = Annotated[
    CardinalityComplete | CardinalityLimited | NotApplicable | Disabled | Failed,
    Field(discriminator="status"),
]


# Paths ------------------------------------------------------------------------


class KeySegment(ScanModel):
    key: str


class ItemsSegment(ScanModel):
    items: Literal[True] = True


class ColumnSegment(ScanModel):
    column: int


PathSegment = KeySegment | ItemsSegment | ColumnSegment


# Fields -----------------------------------------------------------------------


class Presence(ScanModel):
    parent_type: Literal["object", "array", "record"]
    parent_count: int
    present: int
    absent: int | None


class StringCategories(ScanModel):
    count: int
    empty: int
    blank: int
    marker: int
    content: int


class MissingComponents(ScanModel):
    absent: int | None
    null: int
    empty: int
    blank: int
    marker: int


class Missing(ScanModel):
    count: int
    definition: list[MissingCategory]
    components: MissingComponents


class ArrayStats(ScanModel):
    count: int
    empty: int
    min_length: int
    max_length: int
    total_items: int


class ValueCount(ScanModel):
    """An analytical value in its canonical text, with its native type."""

    value: str
    type: ScalarType
    count: int


class ValueAt(ScanModel):
    value: str
    type: ScalarType
    record: int


class Frequencies(ScanModel):
    distinct: int
    listed: list[ValueCount]
    truncated: bool


class SampleEntry(ValueCount):
    """A sampled original value with its exact count (design 18.9).

    ``id`` numbers the entry in the listing of the Scan and stays the same in a
    Report that keeps a subset of it.
    """

    id: int
    count_accuracy: Accuracy
    identity_accuracy: Accuracy


class SampleHash(ScanModel):
    """Priority function of a bottom-k sample (design 18.3)."""

    algorithm: str
    version: int
    bits: int
    seed: int


class LongTextEntry(ScanModel):
    """A sampled long text: bounded preview, original sizes and digest of the
    complete content, which is its identity (design 18.6)."""

    id: int
    digest: str
    type: ScalarType
    preview: str
    truncated: bool
    original_length_chars: int
    original_length_bytes: int
    count: int
    count_accuracy: Accuracy
    identity_accuracy: Accuracy


class DigestInfo(ScanModel):
    """Function that gives a long text its digest (design 18.6)."""

    algorithm: str
    bits: int


class LongTexts(ScanModel):
    """Sample of the values longer than ``limits.max_stored_value_length``.

    ``occurrences`` counts every occurrence of a long value, exactly. ``of``
    long texts are sampled, ``kept`` listed (exposure can withhold them). Like
    ``Samples`` it is ``all`` until a text was dropped, then ``bottom_k``; ``k``
    is the size granted (design 18.10), ``requested_k`` the one asked for when
    the budget made it smaller.
    """

    selection: Literal["all", "bottom_k"]
    k: int
    requested_k: int | None = None
    preview_chars: int
    occurrences: int
    kept: int
    of: int
    digest: DigestInfo
    hash: SampleHash | None = None
    threshold: str | None = None
    listed: list[LongTextEntry]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("requested_k", "hash", "threshold"))


class LengthOther(ScanModel):
    """What the strata by length do not hold: ``lengths`` distinct lengths that
    are not tracked and the ``occurrences`` counted while they were not
    (design 18.7). The strata and ``other`` add up to every stored value."""

    lengths: int
    occurrences: int


class LengthStratum(ScanModel):
    """The values of one length, a bottom-k sample of the originals.

    ``ids`` number entries of ``samples.listed`` or of ``by_length.listed``;
    ``kept`` of the ``of`` values sampled are listed (exposure withholds them).
    ``count_accuracy`` is ``exact`` when the length was tracked from its first
    occurrence; ``partial`` when it was admitted late, and then the counts cover
    the occurrences from ``tracking_started_at_occurrence`` on (LEN-05).
    ``selection`` is ``all`` while the stratum dropped no value.
    """

    length: int
    selection: Literal["all", "bottom_k"]
    kept: int
    of: int
    occurrences: int
    count_accuracy: Accuracy
    tracking_started_at_occurrence: int | None = None
    threshold: str | None = None
    ids: list[int]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self), ("tracking_started_at_occurrence", "threshold")
        )


class ByLength(ScanModel):
    """Samples by length of the original text (design 18.7), a stratum for each
    of at most ``max_lengths`` tracked lengths with ``per_length_k`` values each.

    A stratum lists the ``id`` of its values; one that is already in the
    ``listed`` of ``samples`` is not copied, ``listed`` here holds the others and
    its ids continue the numbering of the sample. ``limited`` says that some
    stored values are in no stratum: ``other`` sums them. ``max_lengths`` is the
    number in force, ``requested_max_lengths`` the one asked for when the memory
    budget (design 18.10) granted fewer.
    """

    domain: Literal["original"]
    unit: Literal["characters"]
    per_length_k: int
    max_lengths: int
    requested_max_lengths: int | None = None
    reason: str | None = None
    limited: bool
    tracked: int
    strata: list[LengthStratum]
    other: LengthOther | None = None
    listed: list[SampleEntry]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("requested_max_lengths", "reason", "other"))


class CaseEntry(ScanModel):
    """An original text of a case and the exact number of its occurrences in the
    whole field (design 18.15)."""

    value: str
    count: int


class WhitespaceCase(ScanModel):
    """The cells of one kind of whitespace and a bottom-k of their original texts.

    ``occurrences`` is the exact number of cells of the kind. ``selection`` is
    ``all`` while the class dropped no text, so ``listed`` is then every
    distinct text of the case; ``of`` texts were sampled and ``kept`` listed
    (exposure can withhold them, as for ``Samples``).
    """

    kind: Literal["leading", "trailing", "repeated"]
    occurrences: int
    selection: Literal["all", "bottom_k"]
    kept: int
    of: int
    threshold: str | None = None
    listed: list[CaseEntry]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("threshold",))


class LengthCase(ScanModel):
    """The cells of one analytical length: ``WhitespaceCase`` for a length."""

    length: int
    occurrences: int
    selection: Literal["all", "bottom_k"]
    kept: int
    of: int
    threshold: str | None = None
    listed: list[CaseEntry]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("threshold",))


class CaseLengths(ScanModel):
    """Cases by analytical length, written for a field with a minority length:
    every tracked length but the dominant one. At most ``max_lengths`` lengths
    are tracked, as met; the cells of the others are summed in ``other``."""

    max_lengths: int
    other: LengthOther | None = None
    classes: list[LengthCase]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("other",))


class Cases(ScanModel):
    """Bounded samples of the cases of the rules observed in the field
    (design 18.15). ``per_class_k`` is the number of texts kept per class
    (design 18.10), ``requested_per_class_k`` the one asked for when the memory
    budget granted fewer."""

    per_class_k: int
    requested_per_class_k: int | None = None
    reason: str | None = None
    whitespace: list[WhitespaceCase] | None = None
    lengths: CaseLengths | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            ("requested_per_class_k", "reason", "whitespace", "lengths"),
        )


class Samples(ScanModel):
    """Distinct original values with their exact counts (design 18.9).

    ``all`` lists every distinct value, in first-seen order; ``bottom_k`` the
    ones of smallest priority, in ascending priority, and names ``k``, the
    ``hash`` and the ``threshold`` (the largest priority kept, as hexadecimal
    digits; absent while no value was dropped and for a sensitive field).

    ``kept`` values are listed out of the ``of`` the scan sampled: a Scan has
    ``kept == of`` unless exposure withheld values (``mask`` merges, ``hide``
    lists none); a Report keeps fewer (design 19.4) and says so here."""

    selection: Literal["all", "bottom_k"]
    kept: int
    of: int
    listed: list[SampleEntry]
    k: int | None = None
    # The size asked for, written only when the memory budget granted less
    # (design 18.10); ``reason`` is then ``memory_budget``.
    requested_k: int | None = None
    reason: str | None = None
    hash: SampleHash | None = None
    threshold: str | None = None
    # The values longer than ``limits.max_stored_value_length``, absent when
    # the field has none (design 18.6).
    long_texts: LongTexts | None = None
    # Samples by length of the stored values, only for a ``bottom_k`` sample
    # (an ``all`` sample lists every value) and when they are turned on.
    by_length: ByLength | None = None
    # Samples of the cases of the observed rules (design 18.15), absent when
    # the field has none or they are turned off.
    cases: Cases | None = None

    @model_serializer(mode="wrap")
    def _omit_bottom_k(self, handler) -> dict[str, Any]:
        return _omit_none(
            handler(self),
            (
                "k",
                "requested_k",
                "reason",
                "hash",
                "threshold",
                "long_texts",
                "by_length",
                "cases",
            ),
        )


class FieldValues(ScanModel):
    count: int
    cardinality: Cardinality
    frequencies: measure(Frequencies)
    samples: Samples
    first: ValueAt | None
    last: ValueAt | None


class SpecialCharacter(ScanModel):
    """A special character of the field: in ``value_count`` distinct values and
    ``occurrence_count`` occurrences of values (design 9.2)."""

    char: str
    codepoint: int
    value_count: int
    occurrence_count: int


class SpecialCharacters(ScanModel):
    """``value_count`` is exact while the table of distinct values is complete;
    a streamed field counts a value again in each batch that holds it, so the
    counts are then ``upper_bound``s (``occurrence_count`` stays exact)."""

    distinct: int
    value_count_accuracy: Literal["exact", "upper_bound"]
    listed: list[SpecialCharacter]


class StringCharacteristics(ScanModel):
    """Occurrences of the strings of a field with each characteristic, and the
    characters of the field (design 9.2). Counts only: shares are computed."""

    non_ascii: int
    with_line_breaks: int
    with_control_characters: int
    with_surrounding_whitespace: int
    with_repeated_whitespace: int
    uppercase: int
    lowercase: int
    mixed_case: int
    no_letters: int
    with_ascii_lowercase: int
    with_ascii_uppercase: int
    with_other_latin_letters: int
    with_non_latin_letters: int
    with_ascii_digits: int
    with_other_digits: int
    starts_uppercase: int
    starts_lowercase: int
    with_tabs: int
    with_non_breaking_spaces: int
    ascii_only: int
    letters_only: int
    digits_only: int
    alphanumeric_only: int
    letters_and_digits: int
    with_invisible_characters: int
    with_replacement_character: int
    characters: int
    distinct_characters: measure(int)
    special_characters: measure(SpecialCharacters)


class LengthCount(ScanModel):
    length: int
    count: int


class StringLengths(ScanModel):
    count: int
    min_length: int
    max_length: int
    mean_length: int | float
    median_length: int | float
    length_histogram: list[LengthCount]


Number = int | float


class NumericCoverage(ScanModel):
    """The values of the field that the numeric block describes: ``count`` of
    the block out of ``of``, the analyzable values (``values.count``)."""

    of: int
    share: float


class NumericStats(ScanModel):
    count: int
    native_count: int
    text_count: int
    min: Number
    max: Number
    sum: Number
    mean: Number
    population_variance: Number
    population_std: Number
    positive: int
    negative: int
    zero: int
    integral_decimals: int
    median: measure(Number)
    coverage: NumericCoverage


class BooleanCounts(ScanModel):
    true: int
    false: int


StageName = Literal[
    "raw", "nfc", "trim", "collapse_whitespace", "casefold", "strip_accents"
]


class NormalizationStage(ScanModel):
    """``changed`` and ``cardinality`` are ``null`` for a disabled stage and
    ``changed`` for ``raw``.

    ``equals`` names the stage whose output this one received (the previous
    enabled stage, or ``raw``) when ``changed`` is 0: no occurrence was
    modified, so the distinct values are the same and so is ``cardinality``,
    complete or limited (design 10). A limited stage that changed something
    has no ``equals``: its count is not derived from the raw table (D13).
    ``cardinality`` of a limited stage never carries the estimate or the upper
    bound of ``values.cardinality``, which is where to read them.
    """

    stage: StageName
    enabled: bool
    changed: int | None
    cardinality: IntMeasure | None
    equals: StageName | None = None

    @model_serializer(mode="wrap")
    def _omit_equals(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("equals",))


class Variant(ScanModel):
    """A raw string variant of a comparison key."""

    value: str
    count: int


class VariantGroup(ScanModel):
    """A comparison key with at least two distinct raw variants; ``count`` and
    ``distinct`` cover every variant, ``variants`` the most frequent ones."""

    key: str
    count: int
    distinct: int
    variants: list[Variant]
    truncated: bool


class VariantGroups(ScanModel):
    groups: int
    listed: list[VariantGroup]
    truncated: bool


class Normalization(ScanModel):
    version: int
    stages: list[NormalizationStage]
    variant_groups: measure(VariantGroups)


TemporalKindName = Literal["date", "datetime_naive", "datetime_aware", "time"]


class YearCount(ScanModel):
    year: int
    count: int


class TemporalKind(ScanModel):
    """Values of one kind; ``min`` and ``max`` are ISO strings. Aware values
    compare as instants; naive and aware values are never compared."""

    kind: TemporalKindName
    count: int
    min: str
    max: str
    years: list[YearCount] | None


class TemporalStats(ScanModel):
    """Temporal values of the date detector; ``ambiguous`` values are counted
    and excluded (design 9.6)."""

    count: int
    ambiguous: int
    kinds: list[TemporalKind]


TechnicalTypeName = Literal[
    "integer", "number", "date", "boolean", "text", "mixed", "empty"
]


class TechnicalType(ScanModel):
    """Port of the current type inference (design 9.7): ``confidence`` is the
    accepted share, ``null`` without values; ``outside_count`` is ``null`` for
    ``mixed``."""

    type: TechnicalTypeName
    confidence: float | None
    counts: dict[str, int]
    outside_count: int | None


class Coverage(ScanModel):
    """Design 12.2: ``tested = eligible - not_tested`` and ``tested = matched +
    ambiguous + invalid + not_matched``. ``share_tested`` is ``null`` when no
    value was tested."""

    eligible: int
    tested: int
    matched: int
    ambiguous: int
    invalid: int
    not_matched: int
    not_tested: int
    share_tested: float | None
    share_eligible: float


class FormatCount(ScanModel):
    format: str
    count: int


class Evidence(ScanModel):
    """First distinct analytical values of each state, bounded by
    ``limits.max_evidence_examples``."""

    matched: list[str]
    ambiguous: list[str]
    invalid: list[str]
    not_matched: list[str]


class _Detector(ScanModel):
    id: str
    version: int


class Adaptive(ScanModel):
    """Design 13: the detector reacted to ``warmup_reactions`` of the first
    ``skipped_after`` distinct values of the field, none or at most
    ``detection.rare_share`` of them, so later values other than probes were
    not tested. ``diagnostic`` points to the warning raised when a probe
    reacted after a warm-up without any reaction."""

    skipped_after: int
    warmup_reactions: int
    not_tested: int
    diagnostic: int | None


class DetectorComplete(_Detector):
    status: Literal["complete"] = "complete"
    coverage: Coverage
    formats: list[FormatCount]
    evidence: Evidence
    details: dict[str, Any]
    adaptive: Adaptive | None


class DetectorNotApplicable(_Detector):
    status: Literal["not_applicable"] = "not_applicable"
    reason: str


class DetectorDisabled(_Detector):
    status: Literal["disabled"] = "disabled"


class DetectorFailed(_Detector):
    """A failure is never reported as values that did not match (CA19)."""

    status: Literal["failed"] = "failed"
    reason: str
    diagnostic: int


DetectorResult = Annotated[
    DetectorComplete | DetectorNotApplicable | DetectorDisabled | DetectorFailed,
    Field(discriminator="status"),
]


class InterpretationCandidate(ScanModel):
    detector: str
    matched: int
    share_eligible: float


class Interpretations(ScanModel):
    """Detectors whose ``share_eligible`` reaches ``detection.minimum_share``;
    ``primary`` only when exactly one qualifies (design 12.4)."""

    primary: str | None
    candidates: list[InterpretationCandidate]


class FieldResult(ScanModel):
    id: str
    path: list[PathSegment]
    display: str
    name: str
    parent: str | None
    collection: str | None
    first_record: int | None
    occurrences: int
    presence: Presence
    native_types: dict[NativeType, int]
    strings: StringCategories
    missing: Missing
    arrays: ArrayStats | None
    values: FieldValues
    string_characteristics: StringCharacteristics
    string_lengths: measure(StringLengths)
    numeric: measure(NumericStats)
    booleans: measure(BooleanCounts)
    temporal: measure(TemporalStats)
    normalization: Normalization
    technical_type: TechnicalType
    detectors: list[DetectorResult]
    interpretations: Interpretations
    # Family and type of the field, decided from the blocks above (contract
    # docs/dev/report/summary-table.md 3).
    classification: Classification
    sensitive: bool
    # The exposure applied to the values of a sensitive field (design 12.8).
    exposure: Literal["mask", "hide", "show"] | None


# Datasets and scan ----------------------------------------------------------


class Structure(ScanModel):
    paths: IntMeasure
    untracked_observations: int
    depth_truncated_observations: int
    max_depth_seen: int


class RecordList(ScanModel):
    count: int
    # Record indices of the first ones, up to ``limits.max_listed_records``.
    records: list[int]


class DuplicateRecords(ScanModel):
    # Records equal to an earlier record of the dataset, beyond its first
    # occurrence; limited with reason ``record_budget``.
    count: IntMeasure
    records: list[int]


RowOrigin = Literal["start", "middle", "end"]


class SampleRow(ScanModel):
    """A row of the row sample: its position in the dataset (the record index),
    the groups it belongs to and the cells of the projected fields.

    ``values`` holds the canonical text per field id, through its exposure: a
    list when the path repeats, ``null`` for a JSON null or a hidden cell, no
    key for a field absent from the record. ``truncated`` lists the
    fields whose cell was cut at ``cell_chars`` (design 18.11).
    """

    record: int
    origins: list[RowOrigin]
    values: dict[str, list[str | None] | None]
    truncated: list[str] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_untruncated(self, handler) -> dict[str, Any]:
        data = handler(self)
        if not data.get("truncated"):
            data.pop("truncated", None)
        return data


class RowSizes(ScanModel):
    """Sizes asked for: ``rows`` in all, ``edge`` first and ``edge`` last rows,
    and ``middle`` = ``rows`` - 2 * ``edge`` rows of the interior."""

    rows: int
    edge: int
    middle: int


class RowPopulation(ScanModel):
    """The records read (``records``) and the ones the middle is drawn from:
    positions ``edge`` + 1 to ``records`` - ``edge``, ``interior`` of them
    (``scope`` names it, ROW-07)."""

    records: int
    interior: int
    scope: Literal["interior_rows"]


class RowSample(ScanModel):
    """Common row sample of a dataset: first rows, a bottom-k of the interior
    and last rows, the same cells for every projected field (design 18.11).

    ``middle_k`` is the size of the middle in force, below ``requested.middle``
    when the byte budget cut it (``reason`` is then ``memory_budget``, which
    also covers start or end rows left out). ``complete`` says that every record
    read is a row. ``threshold`` (16 hexadecimal digits) is the largest priority
    kept in the middle, written once a middle row was dropped. ``fields`` are
    the projected field ids; ``fields_limited`` says that untracked paths are not
    projected. ``bytes`` is the modelled size of the rows kept, ``max_bytes`` the
    budget of the scan. ``kept`` rows are listed out of the ``of`` sampled: a
    Report keeps the header and no row (``kept`` 0).
    """

    selection: Literal["start_middle_end"]
    hash: SampleHash
    requested: RowSizes
    middle_k: int
    reason: str | None = None
    population: RowPopulation
    complete: bool
    threshold: str | None = None
    fields: list[str]
    fields_limited: bool
    cell_chars: int
    truncated_cells: int
    bytes: int
    max_bytes: int
    kept: int
    of: int
    rows: list[SampleRow]

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("reason", "threshold"))

    def interior(self) -> list[SampleRow]:
        """The rows drawn from the interior, with the scope they speak for: the
        only rows an exploration may treat as a sample (ROW-07)."""
        return [row for row in self.rows if row.origins == ["middle"]]

    def covers(self, field_ids: list[str]) -> bool:
        """Whether every named field is projected and none of its cells was cut
        or withheld: the rows can serve a relation between them (ROW-11). A
        sample that lists no row, or fewer than it sampled (a Report), serves
        none."""
        if not self.rows or self.kept != self.of:
            return False
        if not set(field_ids) <= set(self.fields):
            return False
        return not any(
            field in row.truncated or (field in row.values and row.values[field] is None)
            for row in self.rows
            for field in field_ids
        )


class Records(ScanModel):
    with_missing: RecordList
    empty: RecordList
    duplicates: DuplicateRecords
    # Absent when ``records.sample.rows`` is 0.
    sample: RowSample | None = None

    @model_serializer(mode="wrap")
    def _omit_sample(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("sample",))


class DatasetResult(ScanModel):
    id: str
    kind: DatasetKind
    collection_path: list[PathSegment] | None
    record_count: int
    record_types: dict[NativeType, int]
    structure: Structure
    records: Records
    fields: list[FieldResult]


class Diagnostic(ScanModel):
    code: str
    level: Literal["fatal", "error", "warning"]
    message: str
    count: int
    dataset: str | None
    field: str | None
    detector: str | None
    # Facts of the event, by code (for example the limited measures of a field).
    details: dict[str, Any]
    locations: list[dict[str, int]]


class EngineInfo(ScanModel):
    version: str
    normalization_version: int
    detectors: dict[str, int]
    # Versions of the rules that classify the fields, by name.
    classification: dict[str, int]


class CsvSourceInfo(ScanModel):
    delimiter: str
    quote: str
    header: list[str]
    # Whether the file starts with a UTF-8 byte order mark.
    bom: bool
    # "lf", "crlf", "cr", "mixed", or null when the file has no line break.
    line_ending: Literal["lf", "crlf", "cr", "mixed"] | None


class ExcelSourceInfo(ScanModel):
    """The table read from a workbook: where it is and what its header says."""

    dataset_path: str
    sheet: str
    table: str | None
    # A1 range of the header and the data, and the 1-based header row.
    range: str
    header_row: int
    header: list[str]


class SourceShape(ScanModel):
    """Global size of the source, whatever the dataset."""

    # Physical lines of a CSV file (header and multi-line cells included);
    # null for the other formats.
    lines: int | None
    # Analyzed records, all datasets together.
    records: int
    # Columns of a tabular source (CSV or Excel); null for JSON and JSONL.
    columns: int | None
    # Fields discovered, all datasets together.
    fields: int
    datasets: int
    # Analyzed records times columns; null when the source is not tabular.
    cells: int | None
    # Cells with a missing value, all fields together (see ``values.missing``).
    missing_cells: int
    # Records with at least one missing value, empty records and records
    # equal to an earlier one (null when the count is limited or disabled),
    # all datasets together.
    records_with_missing: int
    empty_records: int
    duplicate_records: int | None


class SourceInfo(ScanModel):
    format: Literal["csv", "json", "jsonl", "excel"]
    name: str
    size_bytes: int
    modified_at: datetime
    sha256: str
    encoding: str | None
    shape: SourceShape
    csv: CsvSourceInfo | None
    excel: ExcelSourceInfo | None = None

    @property
    def header(self) -> list[str] | None:
        """The column names of a tabular source (CSV or Excel), ``None`` for a
        JSON source."""
        if self.csv is not None:
            return self.csv.header
        return None if self.excel is None else self.excel.header


class CollectionScope(ScanModel):
    mode: Literal["auto", "explicit"]
    requested: list[str] | None


class Scope(ScanModel):
    collections: CollectionScope | None
    records_read: int
    records_analyzed: int
    records_excluded: int
    exclusions: dict[str, int]


class Timings(ScanModel):
    """Where ``RunInfo.duration_seconds`` went; the five parts add up to it."""

    # Reading and parsing the source, hashing included.
    reading: float
    # Analysis of the values, record callbacks included. With several workers,
    # the time the main process spends on it, waiting for workers included.
    analysis: float
    # Final computation of the datasets.
    finalize: float
    # Analyses derived from the samples and the observations (design 18.12, 18.13).
    derived: float
    # Setup (workers, detectors) and the assembly of the result.
    other: float


class SamplingCounters(ScanModel):
    """Work of the bottom-k samplers over all fields (design 18.4). Counters
    that the scan could not measure are not written; a count of 0 is a
    measured zero."""

    # Priorities computed, keys that entered a sample, occurrences of keys it
    # already held, keys computed and rejected, and keys that left it.
    hashed_keys: int
    hit_keys: int
    admitted_keys: int
    rejected_keys: int
    evicted_keys: int
    # Long texts hashed in full, and their size in UTF-8 bytes.
    long_texts_hashed: int
    long_bytes_hashed: int
    bottom_k_fields: int
    # Fields whose sample was smaller than asked for (memory budget).
    reduced_fields: int
    # Fields that have samples by length, and those among them with values
    # in no stratum.
    strata_fields: int
    strata_limited_fields: int
    # Sizes K of the bottom-k samples, among the fields that have one.
    k_effective_min: int | None = None
    k_effective_max: int | None = None
    # Bytes of the cost model reserved for the samples, the long texts and the
    # samples by length.
    sample_model_bytes: int
    long_model_bytes: int
    length_model_bytes: int

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("k_effective_min", "k_effective_max"))


class RunCounters(ScanModel):
    """Optional diagnostic counters of a run (``scan(counters=True)``)."""

    sampling: SamplingCounters


class RunInfo(ScanModel):
    """What varies from one run to the next on the same source: it is not part
    of the description of the data."""

    started_at: datetime
    duration_seconds: float
    timings: Timings
    # Processes that analyzed values: 1 when the scan ran in the main process.
    workers: int
    # Peak memory of the main process (workers excluded) when the scan ended,
    # in bytes; null when the platform does not report it. It covers the whole
    # process, so it includes earlier work in the same process.
    peak_memory_bytes: int | None
    # Diagnostic counters, written only when asked for.
    counters: RunCounters | None = None

    @model_serializer(mode="wrap")
    def _omit_counters(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("counters",))


# Derived analyses -------------------------------------------------------------
# Computed after the scan from its samples, never from the source (design 18.12).

PatternTokenKind = Literal[
    "digit_ascii",
    "upper_ascii",
    "lower_ascii",
    "letter_unicode",
    "upper_digit",
    "lower_digit",
    "alphanumeric",
    "literal",
]


class PatternToken(ScanModel):
    """One token of a pattern signature (design 18.12): a class of characters
    repeated ``min`` to ``max`` times (characters), or a ``literal`` text
    repeated ``min`` to ``max`` times. A discovered pattern has ``min`` equal
    to ``max`` everywhere (DEC-034)."""

    kind: PatternTokenKind
    text: str | None = None
    min: int
    max: int

    @model_serializer(mode="wrap")
    def _omit_text(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("text",))


class PatternExcluded(ScanModel):
    """What did not take part in the discovery. ``long_text_occurrences`` counts
    occurrences of values too long to be stored (their previews never serve:
    LONG-05); the others count distinct sampled values."""

    long_text_occurrences: int
    non_string_values: int
    empty_values: int
    too_long_values: int
    too_complex_values: int


class PatternPopulation(ScanModel):
    """The values the discovery read. ``distinct`` took part out of
    ``available`` usable values (a cap on the population may leave some out);
    ``occurrences`` is the sum of their counts, ``exact`` when the population is
    the whole distribution of the field and ``sample`` otherwise."""

    source: Literal["samples"]
    selection: Literal["all", "bottom_k"]
    complete: bool
    available: int
    distinct: int
    occurrences: int
    occurrences_basis: Literal["exact", "sample"]
    excluded: PatternExcluded


EligibilityState = Literal["eligible", "low_relevance", "excluded", "not_assessable"]
EligibilityReason = Literal[
    # excluded
    "exposure",
    "booleans_only",
    "structures_only",
    "long_texts_only",
    "no_values",
    # not_assessable
    "samples_withheld",
    "too_few_distinct",
    "inference_error",
    # assessed: eligible or low_relevance
    "regular_structure",
    "many_fixed_lengths",
    "integer_digits",
    "small_integers",
    "decimal_numbers",
    "no_structural_marks",
    "few_distinct",
    "semantic_detector",
]


class PatternEligibility(ScanModel):
    """Whether a field is a candidate for the discovery (design 18.12, PAT-12).

    ``score`` runs from 0 to 1 (four decimals) and is 0 for a field that is
    ``excluded`` or ``not_assessable``; only an ``eligible`` field is
    discovered. ``reasons`` are codes, never empty, so a reader can tell "no
    pattern" from "not looked at"."""

    state: EligibilityState
    score: float
    reasons: list[EligibilityReason]


class PatternGain(ScanModel):
    """What a facet saves in the node it specializes (design 18.12, E4): bits on
    the distinct values (``bits_d``) and on the occurrences (``bits_o``) for the
    prefix of a node or the cell of a table, and ``sigma`` of the whole facet."""

    bits_d: float
    bits_o: float
    sigma: float


class PatternCondition(ScanModel):
    """What a node fixes besides its own facet: the facet (``head:N``, ``tail:N``
    or ``token:N``) and the text of its head, tail or token."""

    facet: str
    value: str


class PatternNode(ScanModel):
    """A specialization of a pattern (design 18.12), with its counts in distinct
    values (``d``) and occurrences (``o``). ``facet`` is ``composition`` (one of the
    structures a family merged: the nodes of a pattern add up to it) or a facet of
    content, ``head:N``, ``tail:N`` or ``token:N`` (the first or last characters of
    the Nth token of the structure, or the whole token): its ``gain`` is what the
    prefix saves. The nodes of a content facet are a part of their parent, the
    rest being its ``others``. ``value`` is the text the node fixes at its facet (the
    head or the tail, spelled from the left, or the whole token; the text of the
    structure for a node of composition): what the validation reads a node by.
    ``also`` lists what else the node fixes, because a node whose only child covers
    95% of it merged into it (the year, once the month is known). ``nodes`` are the
    nodes below: a longer prefix of the same facet or a facet that depends on this
    node."""

    id: str
    parent: str
    level: int
    facet: str
    value: str
    signature: list[PatternToken]
    render: str
    d: int
    o: int
    role: Literal["principal", "secondary"]
    gain: PatternGain | None = None
    also: list[PatternCondition] = []
    nodes: list[PatternNode] = []

    @model_serializer(mode="wrap")
    def _omit_empty(self, handler) -> dict[str, Any]:
        data = _omit_none(handler(self), ("gain",))
        for name in ("also", "nodes"):
            if not data.get(name):
                data.pop(name, None)
        return data


class FamilyPattern(ScanModel):
    """A pattern of fixed length (DEC-034) of a family: one combination of the
    lengths of the variable tokens, its constants folded into the signature.
    ``lengths`` are those of the class tokens, a merged block counting as one;
    ``format`` is the exact form of the commonest value, one symbol per
    character."""

    id: str
    signature: list[PatternToken]
    render: str
    format: str
    lengths: list[int]
    d: int
    o: int
    examples: list[int]
    nodes: list[PatternNode]


class PatternTableCell(ScanModel):
    value: str
    d: int
    o: int


class PatternTableOthers(ScanModel):
    distinct: int
    d: int
    o: int


class PatternTable(ScanModel):
    """The values of a facet of a family with their counts, not nested in the tree
    (design 18.12). ``facet`` is ``lengths`` (the combinations of lengths that
    ``max_patterns_per_family`` or ``max_patterns`` kept out of the patterns) or a
    facet of content, ``head:N``, ``tail:N`` or ``token:N``, which no node reads
    because it is independent of the nodes: its cells are the prefixes it keeps
    (text, spelled from the left), with the ``gain`` of the facet. ``others`` is the
    rest of the table, so that cells and rest add up to the family."""

    facet: str
    cells: list[PatternTableCell]
    others: PatternTableOthers
    gain: PatternGain | None = None

    @model_serializer(mode="wrap")
    def _omit_gain(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("gain",))


class PatternFamily(ScanModel):
    """The values of one structure (the classes of their tokens, without
    lengths), or of structures merged at the edge of a block (``composition``
    lists their keys). A family is not a pattern: it presents itself as its
    patterns (design 18.12)."""

    id: str
    key: str
    composition: list[str] = []
    d: int
    o: int
    patterns: list[FamilyPattern]
    tables: list[PatternTable]
    examples: list[int]

    @model_serializer(mode="wrap")
    def _omit_composition(self, handler) -> dict[str, Any]:
        data = handler(self)
        if not data.get("composition"):
            data.pop("composition", None)
        return data


class PatternOtherStructures(ScanModel):
    """The values no published family reads: ``structures`` counts the
    structures left out (``max_families``), ``d`` and ``o`` their values."""

    structures: int
    d: int
    o: int


PatternLimit = Literal[
    "max_values", "max_families", "max_patterns_per_family", "max_patterns", "max_depth"
]


class FieldPatternsComplete(ScanModel):
    dataset: str
    field: str
    status: Literal["complete"] = "complete"
    eligibility: PatternEligibility
    population: PatternPopulation
    families: list[PatternFamily]
    other: PatternOtherStructures
    limits: list[PatternLimit]

    def all_patterns(self) -> list[FamilyPattern]:
        """The patterns of the hierarchy in the order of the document: the families
        in order, each with its patterns. The place of a pattern in this list is its
        class for the features and the targets that name patterns (Patterns lot P7)."""
        return [pattern for family in self.families for pattern in family.patterns]

    def outside_patterns(self) -> tuple[int, int]:
        """The distinct values and the occurrences of the population that no pattern
        holds: the structures left out of the families (``other``) and the
        combinations of lengths that a budget kept in the table of lengths of a
        family. They are the part of the population that a pattern cannot be named
        for."""
        distinct, occurrences = self.other.d, self.other.o
        for family in self.families:
            for table in family.tables:
                if table.facet == "lengths":
                    distinct += sum(cell.d for cell in table.cells) + table.others.d
                    occurrences += sum(cell.o for cell in table.cells) + table.others.o
        return distinct, occurrences


class FieldPatternsNotApplicable(ScanModel):
    """A field the discovery does not read: its eligibility says why. ``reason``
    repeats the deciding code of the eligibility, for the readers that want one
    word."""

    dataset: str
    field: str
    status: Literal["not_applicable"] = "not_applicable"
    eligibility: PatternEligibility
    reason: str


class FieldPatternsFailed(ScanModel):
    """The inference raised on this field: the other fields and analyses are
    unaffected and ``diagnostic`` points to the ``pattern_inference_failed``
    error (the exception type only: its message could quote a value)."""

    dataset: str
    field: str
    status: Literal["failed"] = "failed"
    eligibility: PatternEligibility
    reason: Literal["inference_error"] = "inference_error"
    diagnostic: int


FieldPatterns = Annotated[
    FieldPatternsComplete | FieldPatternsNotApplicable | FieldPatternsFailed,
    Field(discriminator="status"),
]


class PatternGrammar(ScanModel):
    """The versioned grammar of the signatures and their rendering (PAT-04)."""

    name: str
    version: int


class PatternAlgorithm(ScanModel):
    """The version of the discovery: scores, constants and order of its steps.
    A change of the algorithm or of a constant of it raises it (FR-020)."""

    version: int


class DerivedPatterns(ScanModel):
    """Structural patterns inferred from the samples, one entry per field
    (design 18.12). They are distinct from the configured ``pattern:<id>``
    detectors."""

    grammar: PatternGrammar
    algorithm: PatternAlgorithm
    domain: Literal["original"]
    fields: list[FieldPatterns]


class CharacterCount(ScanModel):
    """One character of the most frequent ones, with the occurrences of it in the
    values read (design 9.2b)."""

    char: str
    codepoint: int
    occurrence_count: int


class CharacterFamily(ScanModel):
    """Characters of one Unicode family: the script of a letter (the first word of
    its Unicode name, such as ``LATIN`` or ``CYRILLIC``) or a general category
    (``Lu``, ``Nd``, ``Po``...)."""

    name: str
    occurrence_count: int


class EmojiCount(ScanModel):
    """An emoji sequence (one emoji, its modifiers and joiners, a flag or a
    keycap), with its occurrences."""

    sequence: str
    occurrence_count: int


class CharacterMap(ScanModel):
    """What the characters of the strings of a field are (design 9.2b).

    ``basis`` is ``exact`` when every string of the field was read and ``sample``
    when the values read are the stored samples. ``values`` counts the strings
    read, ``characters`` their characters. ``top`` lists the most frequent
    characters, letters and digits included, by descending occurrences then code
    point; ``scripts`` and ``categories`` list every family met. The case
    counters count occurrences of values: ``ends_uppercase`` and
    ``ends_lowercase`` look at the last character, ``title_case`` is
    ``str.istitle()``. ``with_emoji`` counts the values with an emoji,
    ``emoji_sequences`` the sequences themselves. Shares are not stored."""

    basis: Literal["exact", "sample"]
    values: int
    characters: int
    distinct: int
    top: list[CharacterCount]
    scripts: list[CharacterFamily]
    categories: list[CharacterFamily]
    ends_uppercase: int
    ends_lowercase: int
    title_case: int
    with_emoji: int
    emoji_sequences: int
    emoji: list[EmojiCount]


FieldCharacterMap = Annotated[
    Complete[CharacterMap] | Limited | NotApplicable | Disabled | Failed,
    Field(discriminator="status"),
]


class FieldCharacters(ScanModel):
    """The character map of one field."""

    dataset: str
    field: str
    characters: FieldCharacterMap


class DerivedCharacters(ScanModel):
    """Character maps computed from the samples, one entry per field (design
    9.2b). The second pass replaces them with exact ones."""

    fields: list[FieldCharacters]


class Derived(ScanModel):
    """Analyses computed after the scan from its samples (specification 5.2)."""

    patterns: DerivedPatterns | None = None
    characters: DerivedCharacters | None = None

    @model_serializer(mode="wrap")
    def _omit_absent(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("patterns", "characters"))


# Observations, quality issues and limits -------------------------------------

ObservationStatus = Literal["informational", "candidate_anomaly", "confirmed_issue"]
ObservationCategory = Literal[
    "presence", "records", "types", "dates", "normalization", "names", "values", "patterns"
]
# What ``count`` counts, out of ``of`` when the population has a known size.
ObservationPopulation = Literal[
    "value_slots",
    "content_strings",
    "occurrences",
    "records",
    "distinct_values",
    "groups",
    "columns",
]
ObservationAccuracy = Literal["exact", "lower_bound", "sample"]


def _omit_empty(data: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    """Drop the optional members that are ``None`` or an empty list."""
    for name in names:
        if name in data and data[name] in (None, []):
            del data[name]
    return data


class Observation(ScanModel):
    """A finding about the data (QUAL-02), computed from the facts of the scan
    by the versioned ``rule`` and never from values.

    ``status`` says how much to trust it: ``informational`` is a remark that
    may be perfectly valid, ``candidate_anomaly`` a signal that a rule cannot
    confirm, ``confirmed_issue`` a defect by the structure of the source.
    ``dataset`` and ``field`` locate it (both absent for the whole scan);
    ``records`` lists the first record indices, ``patterns`` the inferred
    patterns, ``diagnostics`` the diagnostics and ``limited_by`` the limits
    that stop its count from being exact.
    """

    id: str
    rule: str
    category: ObservationCategory
    status: ObservationStatus
    dataset: str | None = None
    field: str | None = None
    population: ObservationPopulation
    count: int
    of: int | None = None
    accuracy: ObservationAccuracy
    records: list[int] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    diagnostics: list[int] = Field(default_factory=list)
    limited_by: list[str] = Field(default_factory=list)

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_empty(
            handler(self),
            (
                "dataset",
                "field",
                "of",
                "records",
                "patterns",
                "diagnostics",
                "limited_by",
            ),
        )


class Limit(ScanModel):
    """What the scan could not establish (QUAL-04): a measure stopped by a
    limit, a sample that was cut or withheld, a structure that was truncated.
    A limit is never a defect of the data. ``measure`` is the location in the
    dataset or field; ``diagnostic`` points to the error of a failed analysis.
    """

    id: str
    dataset: str | None = None
    field: str | None = None
    measure: str
    reason: str
    limit: int | None = None
    lower_bound: int | None = None
    diagnostic: int | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler) -> dict[str, Any]:
        return _omit_empty(
            handler(self),
            ("dataset", "field", "limit", "lower_bound", "diagnostic"),
        )


class QualitySummary(ScanModel):
    """What was found, whole scan (``dataset`` absent) or one dataset, counted
    before ``scan.observations.max_items`` cuts the lists. ``has_observations``
    is any observation, ``has_quality_issues`` a candidate anomaly or a
    confirmed issue, ``has_limits`` any limit; they stand for the counts."""

    dataset: str | None = None
    informational: int
    candidate_anomalies: int
    confirmed_issues: int
    limits: int
    has_observations: bool
    has_quality_issues: bool
    has_limits: bool

    @model_serializer(mode="wrap")
    def _omit_dataset(self, handler) -> dict[str, Any]:
        return _omit_empty(handler(self), ("dataset",))


class Observations(ScanModel):
    """Findings of the scan on the data and on itself (design 18.13), derived
    from the facts and from ``derived``, without reading the source.

    ``items`` hold the confirmed issues first, then the candidate anomalies,
    then the informational remarks; ``limits`` are apart. At most
    ``scan.observations.max_items`` of each are listed and ``truncated`` says
    that the summaries count more.
    """

    version: int
    truncated: bool
    summary: QualitySummary
    datasets: list[QualitySummary]
    items: list[Observation]
    limits: list[Limit]


class ScanResult(ScanModel):
    format: Literal["tabalyst.scan"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: int = FORMAT_REVISION
    engine: EngineInfo
    status: Literal["complete", "partial"]
    run: RunInfo
    source: SourceInfo
    config: ScanConfig
    config_sha256: str
    scope: Scope
    datasets: list[DatasetResult]
    diagnostics: list[Diagnostic]
    # Analyses computed from the samples; absent when none was (design 18.12).
    derived: Derived | None = None
    # Findings, quality issues and limits; absent when
    # ``scan.observations.enabled`` is false, or when their computation failed
    # (the ``observations_failed`` diagnostic, design 18.13).
    observations: Observations | None = None

    @model_serializer(mode="wrap")
    def _omit_derived(self, handler) -> dict[str, Any]:
        return _omit_none(handler(self), ("derived", "observations"))
