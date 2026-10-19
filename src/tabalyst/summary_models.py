# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Members of the Report document that summarize each column and each dataset.

Codes, numbers, units, accuracy and states, never a sentence: the words are looked
up in ``report_labels`` when a page is rendered (contract summary-table.md 20). The
models live apart from the rules that fill them so that ``models.py`` can hold them.
"""

from typing import Literal

from pydantic import Field

from tabalyst.result_model import ResultModel
from tabalyst.scanner.classify.catalog import (
    FindingClass,
    FindingUnit,
    PopulationKind,
)
from tabalyst.scanner.config import MissingCategory
from tabalyst.scanner.models import MissingComponents

# Findings -------------------------------------------------------------------

# The state of a check (contract 6.4). ``detected`` is the state of a list that
# holds findings; the five others are the vocabulary of decision 6.
AssessmentState = Literal[
    "detected", "none_detected", "not_assessed", "partial", "not_applicable", "failed"
]
# The accuracy of a count: the Scan's three (``exact``, ``lower_bound``,
# ``sample``), an estimate, and ``unavailable`` where no figure can be told.
Accuracy = Literal["exact", "lower_bound", "sample", "estimated", "unavailable"]
# How the examples of a finding were exposed: ``none`` when the Scan keeps no value
# for it.
ExamplesState = Literal["shown", "masked", "hidden", "none"]


class Population(ResultModel):
    """What a count is out of. ``size`` is ``None`` when the population has no
    known size (a number of groups has no denominator)."""

    kind: PopulationKind
    size: int | None = None


class Share(ResultModel):
    """``numerator`` out of ``denominator``, with the percentage. ``percent`` is
    ``None`` and ``accuracy`` ``unavailable`` when the share is not defined: a
    zero population, or a count the population cannot hold (RF-22)."""

    numerator: int
    denominator: int
    percent: float | None
    accuracy: Accuracy


class Example(ResultModel):
    """A value that illustrates a finding, already through the exposure of its
    column (``mask``, ``hide``, ``show``). The checks leave it empty: the summary
    builder fills it from the evidence the Scan keeps (``report_preview``)."""

    value: str
    count: int | None = None


class Finding(ResultModel):
    """One finding of a column: a count of a unit, out of a population, with the
    accuracy of the count and the facts it rests on."""

    code: str
    cls: FindingClass
    field: str
    count: int | None
    unit: FindingUnit
    population: Population
    share: Share | None = None
    accuracy: Accuracy
    status: AssessmentState = "detected"
    # Ids of the observations, detectors or analyses the count comes from.
    basis: list[str] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    # ``None`` until the summary builder has exposed the examples.
    examples_state: ExamplesState | None = None
    # Codes whose set is proven to overlap this one; empty without proof (RF-24).
    overlaps: list[str] = Field(default_factory=list)


class Assessment(ResultModel):
    """How far a check of one code went on a column, whether or not it found
    anything. ``reason`` is a code, not a sentence."""

    code: str
    state: AssessmentState
    accuracy: Accuracy = "unavailable"
    eligible: int | None = None
    tested: int | None = None
    reason: str | None = None


class FindingList(ResultModel):
    """The Errors or the Issues of a column: the findings and the state of the
    whole list (``detected`` when it holds findings), with the check behind each
    code so that a reader can tell what was and was not looked at."""

    items: list[Finding] = Field(default_factory=list)
    state: AssessmentState
    assessments: list[Assessment] = Field(default_factory=list)


class MissingFinding(ResultModel):
    """Positions with no present value (RF-12), apart from Errors and Issues: an
    absence is never an error by itself (CA-16). ``definition`` lists the
    components that count as missing in this document; ``components`` shows the
    five anyway."""

    field: str
    count: int
    unit: FindingUnit
    population: Population
    share: Share
    accuracy: Accuracy = "exact"
    state: AssessmentState
    definition: list[MissingCategory]
    components: MissingComponents


class ColumnFindings(ResultModel):
    """Everything the table says about a column besides its type."""

    field: str
    missing: MissingFinding
    errors: FindingList
    issues: FindingList


class FindingRef(ResultModel):
    """The words of a finding, and its class for the figures of the overview."""

    code: str
    cls: FindingClass
    count: int | None
    unit: FindingUnit
    accuracy: Accuracy
    # Share of the population in percent, ``None`` without one (a number of groups).
    percent: float | None = None


# Overview -------------------------------------------------------------------

OverviewAccuracy = Literal["exact", "lower_bound"]
# A circumstance of the profile that the sentence mentions, apart from its figures.
OverviewNote = Literal["partial_scope", "ambiguous_left_out"]
OverviewKind = Literal[
    "unique_id",
    "identifier",
    "enum",
    "boolean",
    "constant",
    "numeric",
    "temporal",
    "shaped",
    "text",
    "mixed",
    "empty",
    "unknown",
]


class OverviewFact(ResultModel):
    """A figure the sentence uses, with the accuracy it is worded with."""

    name: str
    value: int | float | str
    accuracy: OverviewAccuracy = "exact"


class Overview(ResultModel):
    """The profile of a column and the facts behind its sentence. ``kind`` picks the
    template and ``type`` the classification type it is worded for; the sentence is
    written from them by ``overview_sentence`` when a page is rendered."""

    kind: OverviewKind
    type: str
    facts: list[OverviewFact]
    notes: list[OverviewNote] = Field(default_factory=list)


# Details --------------------------------------------------------------------

DetailsState = Literal["shown", "masked", "hidden"]
DetailsAccuracy = Literal["exact", "lower_bound"]


class DetailExample(ResultModel):
    """A value of the source, already through the exposure, with its count."""

    value: str
    count: int
    share: float | None = None
    # The value was cut at the length the scan stores: not the whole value.
    truncated: bool = False


class DetailMeasure(ResultModel):
    """A complementary measure. ``label`` is the words, or the text listed (a
    format, a key) when the measure is a count of it."""

    name: str
    label: str
    value: int | float | str
    accuracy: DetailsAccuracy = "exact"


class Details(ResultModel):
    """What the Details cell of a column holds."""

    state: DetailsState
    examples: list[DetailExample]
    # Whether the examples are every distinct value of the column. A masked or
    # hidden list is never exhaustive: its forms are not the original values.
    exhaustive: bool
    # Distinct values the examples are taken from, when known and meaningful.
    total: int | None = None
    total_accuracy: DetailsAccuracy = "exact"
    note: str | None = None
    measures: list[DetailMeasure]


# Values ---------------------------------------------------------------------

ValueSelection = Literal["complete", "diverse_sample", "random_sample"]


class ColumnValues(ResultModel):
    """The values of a column the tables list in a cell and in its hover, through the
    exposure of the column (CA-19): ``examples`` are the inline chips, ``values`` the
    value and its count of the hover. All are empty when the column is hidden and hold
    merged masks when it is masked; the document keeps no raw value (contract 20.5)."""

    selection: ValueSelection
    sampled_distinct_count: int
    examples: list[str]
    values: list[tuple[str, int]]
    # Exposed values the Scan cut at its stored length: not the whole value.
    cut: list[str] = Field(default_factory=list)


# Spelling variants ----------------------------------------------------------

VariantState = Literal["shown", "masked", "hidden"]


class Spelling(ResultModel):
    value: str
    count: int
    # The most frequent spelling of its group: the likely target of a correction.
    most_frequent: bool


class VariantGroupDetail(ResultModel):
    """The spellings of one comparison key, the most frequent first."""

    spellings: list[Spelling]
    # Spellings the group has beyond those listed (never negative).
    more_spellings: int


class VariantDetails(ResultModel):
    """The groups of spelling variants of a column that a reader would correct."""

    state: VariantState
    groups: list[VariantGroupDetail]
    # Groups the scan found beyond those written here; ``None`` when unknown.
    more_groups: int | None

    @property
    def total_groups(self) -> int | None:
        return None if self.more_groups is None else len(self.groups) + self.more_groups


# Ambiguous dates ------------------------------------------------------------

# The two day-month orders a numeric date can be read in.
DateOrder = Literal["DMY", "MDY"]
DateFormatOrder = Literal["YMD", "MDY", "DMY"]


class DateCandidate(ResultModel):
    """The formats that fit a set of ambiguous values at once (``DD-MM-YYYY`` and
    ``MM-DD-YYYY``), with the number of occurrences that fit them."""

    formats: list[str]
    count: int


class DateReading(ResultModel):
    """The unambiguous values of the column that are written in one day-month order:
    the evidence for or against that reading, never applied."""

    order: DateOrder
    count: int


class DateFormat(ResultModel):
    """A date format the column holds without doubt, with its occurrences."""

    format: str
    # ``None`` for formats that are not numeric dates (month names, times).
    order: DateFormatOrder | None
    count: int


class DateDetail(ResultModel):
    """What makes the dates of a column ambiguous: the pairs of formats that fit the
    same values, the evidence of each order and the formats read without doubt.

    A format is a shape, not a value of the source: nothing here goes through the
    exposure. The detail exists only while the values stay ambiguous: when the
    configuration chose an order (``detectors.date.ambiguous_order``) the Scan raises no
    observation, and the report never resolves an ambiguity itself.
    """

    ambiguous_count: int
    candidates: list[DateCandidate]
    more_candidates: int
    readings: list[DateReading]
    formats: list[DateFormat]
    more_formats: int


# Minority patterns ----------------------------------------------------------

# Where the examples of a detail come from (contract summary-table.md 22.2): a value of the
# sample the Scan holds, or nowhere (the sample kept none of them).
# ``cases``: the cases the Scan kept for the rule (scan design 18.15); ``sample``: values of
# its sample of distinct values.
ExamplesFrom = Literal["sample", "cases", "none"]


class FindingExample(ResultModel):
    """A value that illustrates a detail, with its occurrences in the sample it was
    taken from. A detail with examples exists only for a column shown as it is."""

    value: str
    count: int | None = None
    # The value was cut: not the whole value.
    truncated: bool = False


class MinorityPattern(ResultModel):
    """A pattern few of the distinct values share, with examples of those values."""

    id: str
    # The pattern as the Patterns section writes it: a symbol per class of characters,
    # a literal text between quotes.
    render: str
    distinct: int
    examples: list[FindingExample]


class DominantPattern(ResultModel):
    """The pattern most distinct values share, which the minority ones are compared to."""

    render: str
    distinct: int


class PatternDetail(ResultModel):
    """The patterns behind a ``pattern.minority`` finding: the dominant one and the
    minority ones the Scan named, the largest first, each with examples.

    A render can hold the literal text its values share, so the detail exists only for a
    column exposed as ``show``. ``population`` is the number of distinct values the patterns were inferred on, and
    ``population_complete`` is false when that was a sample of them.
    """

    examples_from: ExamplesFrom
    population: int
    population_complete: bool
    dominant: DominantPattern
    patterns: list[MinorityPattern]
    # Patterns the finding names beyond those listed, or that the document no longer holds.
    more_patterns: int


# Minority lengths -----------------------------------------------------------


class DominantLength(ResultModel):
    """The length nearly every text of the column has."""

    length: int
    count: int


class MinorityLength(ResultModel):
    """A length few texts have, with examples of those texts."""

    length: int
    count: int
    examples: list[FindingExample]
    # The examples are every distinct text of the length: the Scan kept them all.
    complete: bool = False


class LengthDetail(ResultModel):
    """The lengths behind a ``length.minority`` finding: the dominant length and every
    other length of the exact histogram, the most frequent first.

    Lengths are those of the analytical text, in characters, as ``string_lengths`` counts
    them. A length and its count are numbers and stay whatever the exposure; the examples
    are values and go through it (``state``).
    """

    state: DetailsState
    examples_from: ExamplesFrom
    # The texts the histogram counts.
    total: int
    dominant: DominantLength
    lengths: list[MinorityLength]
    # Lengths of the histogram beyond those listed.
    more_lengths: int


# Whitespace ------------------------------------------------------------------

# The two stages of the normalization that change a text by its whitespace.
WhitespaceStage = Literal["trim", "collapse_whitespace"]
# What an example shows: whitespace before the text, after it, or repeated inside it.
WhitespaceKind = Literal["leading", "trailing", "repeated"]


class WhitespaceChange(ResultModel):
    """How many texts a stage changed (the count of the observation of its rule)."""

    stage: WhitespaceStage
    changed: int


class WhitespaceExample(FindingExample):
    """A value of a case that a stage changed, and why."""

    kind: WhitespaceKind


class WhitespaceKindCount(ResultModel):
    """The cells of one kind of whitespace, counted exactly by the Scan, and whether the
    examples of the kind are every distinct text of it."""

    kind: WhitespaceKind
    occurrences: int
    complete: bool = False


class WhitespaceDetail(ResultModel):
    """The whitespace behind the ``trimmed_cells`` and ``collapsed_whitespace`` findings.

    The counts are per stage (the texts a stage changed) and, from the cases the Scan keeps,
    per kind (``kinds``, exact). The examples are original texts of those cases (the analytical
    text has no whitespace to show). A text that both stages changed is an example of each,
    with its kind. The examples go through the exposure (``state``).
    """

    state: DetailsState
    examples_from: ExamplesFrom
    stages: list[WhitespaceChange]
    kinds: list[WhitespaceKindCount] = Field(default_factory=list)
    examples: list[WhitespaceExample]


# Mixed types ------------------------------------------------------------------


class TypeCount(ResultModel):
    """The values the scan recognized as one technical type."""

    type: str
    count: int


class TypeDetail(ResultModel):
    """The composition of a column with no dominant technical type, behind a
    ``type.mixed`` finding.

    ``types`` lists every type the scan counted, the most frequent first; ``closest`` is the
    family that comes closest to a technical type for the column (the one the finding counts
    the values outside of) and ``outside`` the values it does not hold. The scan counts
    types, not values, so there is no example, and nothing here goes through the exposure.
    """

    total: int
    types: list[TypeCount]
    closest: TypeCount
    outside: int


class FindingDetails(ResultModel):
    """The evidence behind the Issues of a column, one member per observation rule
    (contract summary-table.md 22). A member is ``None`` when the column has no
    observation of its rule."""

    variants: VariantDetails | None = None
    dates: DateDetail | None = None
    patterns: PatternDetail | None = None
    lengths: LengthDetail | None = None
    whitespace: WhitespaceDetail | None = None
    types: TypeDetail | None = None


# Column ---------------------------------------------------------------------

# The flags of the Summary table segments. They overlap on purpose: ``issue`` is every
# column with an Error or an Issue ("Quality issues"), ``error`` the ones with an Error
# ("With errors"), so a column with an Error carries both.
Flag = Literal["error", "issue", "obs"]


class ColumnSummary(ResultModel):
    """What the Summary table, the previews and the column page say about a column,
    computed once when the Report is built, the exposure already applied."""

    findings: ColumnFindings
    overview: Overview
    details: Details
    values: ColumnValues
    # The evidence behind the Issues of the Findings table (spelling variants, dates...).
    finding_details: FindingDetails
    flags: list[Flag]


# Dataset --------------------------------------------------------------------


class SignalColumn(ResultModel):
    """One column behind a signal, with its figure and its share of the largest."""

    field_id: str
    name: str
    count: int
    relative_percent: float
    # For the spelling variants: the largest group of the column, through the exposure.
    spellings: list[Spelling]


class Signal(ResultModel):
    """The findings of one code summed over the columns that have it. A sum only
    joins findings of one code counted in one unit."""

    code: str
    cls: str
    total: int
    unit: str
    # The sum is a lower bound when one of its terms is.
    lower_bound: bool
    # What the sum is out of: the values every column the check covered offered it.
    # ``None`` when a column with the finding has no population (a number of groups).
    population: int | None = None
    columns: list[SignalColumn]


class SignalsView(ResultModel):
    """The signals of a dataset, the tiles shown first and what is left."""

    shown: list[Signal]
    more: int
    # Columns whose Errors or Issues were not completely looked at.
    incomplete_columns: int


class StateCount(ResultModel):
    state: str
    columns: int


class ValidationList(ResultModel):
    """How many columns are in each state of the Errors or of the Issues."""

    name: str
    with_findings: int
    states: list[StateCount]


class QualityColumn(ResultModel):
    """A column of a quality figure, with the findings that put it there."""

    field_id: str
    name: str
    findings: list[FindingRef]


class QualityView(ResultModel):
    """The quality of the columns: each column is in exactly one of three groups.

    A column with Errors counts under Errors even when it also has Issues, so the
    three figures add up to the columns.
    """

    columns: int
    with_errors: int
    with_issues: int
    no_finding: int
    errors_percent: float
    issues_percent: float
    clean_percent: float
    error_columns: list[QualityColumn]
    issue_columns: list[QualityColumn]
    clean_columns: list[QualityColumn]
    # The states of every list, whatever the group (a column with both is in both).
    errors: ValidationList
    issues: ValidationList


class TableSummary(ResultModel):
    """The counts above the Summary table and the KPIs of the overview of a dataset."""

    error_count: int
    issue_count: int
    observation_count: int
    signals: SignalsView
    quality: QualityView
