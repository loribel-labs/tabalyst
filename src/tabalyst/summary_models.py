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
    """The words of a finding need only these four members."""

    code: str
    count: int | None
    unit: FindingUnit
    accuracy: Accuracy


def finding_text(item: Finding | FindingRef) -> str:
    """A finding in words with its count: ``3 spelling-variant groups``; a lower
    bound is never worded exact."""
    from tabalyst.report_labels import (
        TABLE_AT_LEAST,
        finding_label,
        finding_name,
    )

    if item.count is None:
        text = finding_name(item.code, item.unit)
    else:
        text = finding_label(item.code, item.count, item.unit)
    return f"{TABLE_AT_LEAST} {text}" if item.accuracy == "lower_bound" else text


# Overview -------------------------------------------------------------------

OverviewAccuracy = Literal["exact", "lower_bound"]
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
    ``text``, written from them when asked."""

    kind: OverviewKind
    type: str
    facts: list[OverviewFact]

    @property
    def text(self) -> str:
        from tabalyst.report_overview import overview_sentence

        return overview_sentence(self)


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


# Column ---------------------------------------------------------------------

Flag = Literal["error", "issue", "obs"]


class ColumnSummary(ResultModel):
    """What the Summary table, the previews and the column page say about a column,
    computed once when the Report is built, the exposure already applied."""

    findings: ColumnFindings
    overview: Overview
    details: Details
    # The groups of spelling variants behind the Issue of the same name, for the hover.
    variants: VariantDetails | None
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
    columns: list[SignalColumn]

    @property
    def noun(self) -> str:
        from tabalyst.report_labels import finding_noun

        return finding_noun(self.code, self.unit, self.total)

    def _heading(self) -> tuple[str, str]:
        """The title and the subtitle of the tile: the catalogue's, or the noun."""
        from tabalyst.report_labels import SIGNAL_TITLES

        noun = self.noun
        return SIGNAL_TITLES.get(self.code, (noun[:1].upper() + noun[1:], ""))

    @property
    def title(self) -> str:
        return self._heading()[0]

    @property
    def subtitle(self) -> str:
        return self._heading()[1]

    @property
    def note(self) -> str | None:
        from tabalyst.report_labels import SIGNAL_NOTES

        return SIGNAL_NOTES.get(self.code)

    @property
    def target(self) -> str | None:
        from tabalyst.report_labels import SIGNAL_TARGETS

        return SIGNAL_TARGETS.get(self.code)


class SignalsView(ResultModel):
    """The signals of a dataset, the tiles shown first and what is left."""

    shown: list[Signal]
    more: int
    # Columns whose Errors or Issues were not completely looked at.
    incomplete_columns: int


class StateCount(ResultModel):
    state: str
    columns: int

    @property
    def label(self) -> str:
        from tabalyst.report_labels import LIST_STATE_LABELS

        return LIST_STATE_LABELS[self.state]


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

    @property
    def labels(self) -> list[str]:
        return [finding_text(item) for item in self.findings]


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
