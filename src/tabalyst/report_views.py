# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Views of a report document that its pages read: the projections with the
canonical facts of their field and the figures derived from them.

The document stores the facts once, in its base, and the projections of
``tabalyst.models``; nothing here is serialized. The views are computed when a
page is rendered (design 19.3).
"""

from typing import Literal

from pydantic import Field, FiniteFloat

from tabalyst.models import ColumnProfile, DatasetProfile, ResultModel
from tabalyst.report_labels import family_type_label
from tabalyst.scanner.models import (
    CharacterMap,
    FieldPatternsComplete,
    FieldResult,
    Observation,
    QualitySummary,
    RowSample,
    SampleRow,
)
from tabalyst.scanner.secondpass.models import (
    BinnedHistogram,
    CharacterProfileResult,
    DenseHistogram,
    DistinctCount,
    DistinctLimited,
    FrequencyTable,
    LengthDistribution,
    PatternCounts,
    PeriodCounts,
)

# An integer the scan counted keeps all its digits: the report never turns a
# large counter into a float (F06). A float is finite.
ExactNumber = int | FiniteFloat


class NumericStats(ResultModel):
    minimum: ExactNumber
    maximum: ExactNumber
    range: ExactNumber
    mean: ExactNumber
    # Null when the scan limited the median (its frequency table was released).
    median: ExactNumber | None


class DateFormatCount(ResultModel):
    format: str
    # Null for formats that are not numeric dates (month names, times).
    order: Literal["YMD", "MDY", "DMY"] | None
    separator: str | None
    count: int
    percent: float
    iso: bool = False


class DateBreakdownItem(ResultModel):
    label: str
    category: Literal["valid", "ambiguous", "invalid", "not_date"]
    count: int
    percent: float


class DateProfile(ResultModel):
    status: Literal["valid", "multiple_formats", "mixed", "ambiguous", "invalid"]
    present_count: int
    valid_count: int
    valid_percent: float
    ambiguous_count: int
    ambiguous_percent: float
    invalid_date_count: int
    invalid_date_percent: float
    not_date_count: int
    not_date_percent: float
    resolved_ambiguous_order: Literal["MDY", "DMY"] | None = None
    ambiguous_order_source: Literal["config"] | None = None
    # Unambiguous values per day-month order, exposed and never applied.
    ambiguity_evidence: dict[str, int]
    formats: list[DateFormatCount]
    format_count: int
    breakdown: list[DateBreakdownItem]


class StringLengthExample(ResultModel):
    value: str
    count: int


class StringLengthDistribution(ResultModel):
    length: int
    count: int
    percent: float
    relative_percent: float
    examples: list[StringLengthExample]


class StringProfile(ResultModel):
    status: Literal["very_short", "short", "medium", "long", "very_long"]
    present_count: int
    minimum_length: int
    maximum_length: int
    mean_length: FiniteFloat
    median_length: FiniteFloat
    distinct_length_count: int
    fixed_length: int | None = None
    length_distribution: list[StringLengthDistribution]
    representative_examples: list[str]


class CardinalityView(ResultModel):
    """Distinct values of a column, qualified (design 18.14): ``exact`` is the
    count of the whole file; ``at_least`` a proven lower bound that a scan limit
    stopped, with the KMV ``estimate`` when the scan made one; ``not_counted``
    a limit that proved nothing."""

    kind: Literal["exact", "at_least", "not_counted"]
    # Where an exact count comes from: the scan, or the second pass, which
    # counted the original values of a column the scan stopped counting.
    source: Literal["scan", "second_pass"] = "scan"
    # The exact count, or the lower bound.
    value: int | None = None
    estimate: float | None = None
    # Relative standard error of the estimate.
    error: float | None = None
    upper_bound: int | None = None
    reason: str | None = None
    limit: int | None = None


class QualityItem(ResultModel):
    """One observation of the scan with the words the report gives it."""

    observation: Observation
    title: str
    anchor: str
    status_word: str
    status_title: str
    status_class: str
    # Accuracy kind of the count (``report_labels``).
    kind: str
    noun: str
    # Display name of the field, null for a finding about the dataset.
    field_name: str | None = None
    column_position: int | None = None


class QualityGroup(ResultModel):
    """The observations of one rule in a dataset, for the overview."""

    rule: str
    title: str
    anchor: str
    status_word: str
    status_title: str
    status_class: str
    kind: str
    noun: str
    # Fields concerned, the sum of the counts, and what they are counted out of
    # when a single observation has it.
    fields: int
    total: int
    of: int | None
    headline: str


class QualityView(ResultModel):
    """What the scan found in a dataset, read from ``observations``. Without
    that block (``scan.observations.enabled`` false, or the build failed) the
    report says the findings were not computed and invents none."""

    available: bool
    summary: QualitySummary | None = None
    items: list[QualityItem] = Field(default_factory=list)
    groups: list[QualityGroup] = Field(default_factory=list)
    truncated: bool = False

    @property
    def counts(self) -> dict[str, int]:
        """The listed items by status."""
        counts = {"confirmed_issue": 0, "candidate_anomaly": 0, "informational": 0}
        for item in self.items:
            counts[item.observation.status] += 1
        return counts


class LimitView(ResultModel):
    """A limit of the scan (design 18.13) with the words of the report."""

    id: str
    field_path: str | None = None
    column_id: str | None = None
    measure: str
    label: str
    reason: str
    setting: str | None = None
    note: str | None = None
    limit: int | None = None
    lower_bound: int | None = None
    diagnostic: int | None = None


class DiagnosticLocation(ResultModel):
    record: int
    # CSV line, or 0-based JSON element index; null when not applicable.
    line: int | None = None
    element: int | None = None


class DiagnosticProfile(ResultModel):
    code: str
    level: Literal["fatal", "error", "warning"]
    message: str
    count: int
    # Null for a diagnostic of the whole scan.
    dataset: str | None
    path: str | None
    detector: str | None
    locations: list[DiagnosticLocation]


class LimitsView(ResultModel):
    """What the scan could not establish in a dataset: its limits, the
    structure it truncated and the diagnostics of the dataset and of the scan."""

    # False when the document has no ``observations`` block: the limited
    # measures are then not computed (the diagnostics still are listed).
    available: bool
    items: list[LimitView]
    untracked_observations: int
    depth_truncated_observations: int
    diagnostics: list[DiagnosticProfile]

    @property
    def present(self) -> bool:
        """Whether the limits section is shown: only when something was limited."""
        return bool(
            self.items
            or self.diagnostics
            or self.untracked_observations
            or self.depth_truncated_observations
        )


class PatternRow(ResultModel):
    """A pattern of a column as the report lists it: its place in the hierarchy
    (``family``), its distinct values, their share of the population the discovery
    read, and its length in characters (a discovered pattern has a fixed one).
    ``role`` is ``principal`` for the pattern with the most distinct values."""

    id: str
    family: str
    family_key: str = ""
    render: str
    role: Literal["principal", "secondary"]
    distinct: int
    share: float
    length: int


class PatternCellView(ResultModel):
    """A cell of a table of a family: the text of a head, a tail, a token or a
    combination of lengths, with its distinct values and occurrences and, when the
    second pass counted it, its occurrences over every value of the file."""

    value: str
    d: int
    o: int
    share_d: float
    share_o: float
    validated: int | None = None


class PatternTableView(ResultModel):
    """A table of a family (design 18.12): the values of one facet with their
    counts, not nested in the tree. ``others`` is what the cells leave out."""

    facet: str
    facet_text: str
    cells: list[PatternCellView]
    others_distinct: int
    others_d: int
    others_o: int
    bits: float | None = None
    saturated: bool = False


class PatternNodeView(ResultModel):
    """A node of the tree of a pattern: what it fixes at one facet (``fixes``,
    with what a merged single child fixed too) and its counts. ``validated`` and
    ``validated_distinct`` are those of the second pass, when it ran."""

    id: str
    level: int
    facet_text: str
    value: str
    also: list[str] = Field(default_factory=list)
    render: str
    role: Literal["principal", "secondary"]
    d: int
    o: int
    share_d: float
    share_o: float
    bits_d: float | None = None
    bits_o: float | None = None
    validated: int | None = None
    validated_distinct: int | None = None
    validated_exact: bool = True
    nodes: list["PatternNodeView"] = Field(default_factory=list)


PatternNodeView.model_rebuild()


class PatternPatternView(ResultModel):
    """A pattern of fixed length of a family, with its nodes and examples."""

    id: str
    render: str
    format: str
    lengths: list[int]
    d: int
    o: int
    share_d: float
    share_o: float
    examples: list[str] = Field(default_factory=list)
    unresolved: int = 0
    validated: int | None = None
    validated_distinct: int | None = None
    validated_exact: bool = True
    nodes: list[PatternNodeView] = Field(default_factory=list)
    node_count: int = 0


class PatternFamilyView(ResultModel):
    """A family: the values of one structure (or of structures merged at the edge of
    a block) as the list of its patterns, with its tables."""

    id: str
    key: str
    composition: list[str] = Field(default_factory=list)
    d: int
    o: int
    share_d: float
    share_o: float
    patterns: list[PatternPatternView]
    tables: list[PatternTableView] = Field(default_factory=list)
    validated: int | None = None
    new_variant_length: int = 0
    new_variant_segment: int = 0


class CharacterTile(ResultModel):
    """One character of the map: how it is drawn, its code point and its share
    of the characters read."""

    symbol: str
    codepoint: str
    name: str
    count: int
    share: float


class CharacterShare(ResultModel):
    """A family of characters, an emoji sequence or a case counter with its count
    and its share of the characters (or of the values) read."""

    label: str
    name: str | None = None
    count: int
    share: float


class CharacterMapView(ResultModel):
    """The character map of one column (design 9.2b). ``missing`` means the
    document has none for the column, ``unavailable`` that it cannot have one
    (``reason_text``), ``limited`` that a table passed its bound. ``source`` is the
    Scan (its stored samples, or every value when it kept them all) or the second
    pass (every value)."""

    status: Literal["complete", "limited", "unavailable", "missing"]
    reason_text: str | None = None
    source: Literal["scan", "second_pass"] | None = None
    basis: Literal["exact", "sample"] | None = None
    summary: CharacterMap | None = None
    tiles: list[CharacterTile] = Field(default_factory=list)
    scripts: list[CharacterShare] = Field(default_factory=list)
    categories: list[CharacterShare] = Field(default_factory=list)
    case: list[CharacterShare] = Field(default_factory=list)
    emoji: list[CharacterShare] = Field(default_factory=list)


class PatternView(ResultModel):
    """The inferred patterns of one column (design 18.12) with the examples
    they point to. ``missing`` means the document has no ``derived`` block."""

    status: Literal["complete", "not_applicable", "failed", "missing"]
    reason: str | None = None
    reason_text: str | None = None
    entry: FieldPatternsComplete | None = None
    # The patterns of the hierarchy, the largest first.
    rows: list[PatternRow] = Field(default_factory=list)
    # The hierarchy: the families in the order of the document, each with its
    # patterns, nodes and tables.
    families: list[PatternFamilyView] = Field(default_factory=list)
    node_count: int = 0
    has_validation: bool = False
    # The distinct values no pattern holds, their share of the population and the
    # structures left out of the families.
    outside_distinct: int = 0
    outside_share: float = 0.0
    outside_structures: int = 0
    # Values of the examples that this document holds, by pattern: a Report
    # keeps fewer sample values than its Scan, so some do not resolve.
    examples: dict[str, list[str]] = Field(default_factory=dict)
    unresolved: dict[str, int] = Field(default_factory=dict)


class RowsView(ResultModel):
    """The row sample the report shows (design 18.11 and 18.14). ``sample`` is
    null when the scan kept none (``scan.records.sample.rows`` is 0)."""

    sample: RowSample | None = None

    @property
    def rows(self) -> list[SampleRow]:
        return self.sample.rows if self.sample is not None else []

    @property
    def counts(self) -> dict[str, int]:
        """Rows shown per group; a row of two groups counts in both."""
        return {
            origin: sum(origin in row.origins for row in self.rows)
            for origin in ("start", "middle", "end")
        }


class ColumnAnalyses(ResultModel):
    """The results of the second pass for one column, as the pages read them.
    Only analyses that ended ``complete`` or ``limited`` (a proven lower bound)
    are here; the others are listed in the dataset's ``SecondPassView``."""

    distinct: DistinctCount | DistinctLimited | None = None
    patterns: PatternCounts | None = None
    periods: PeriodCounts | None = None
    histogram: DenseHistogram | BinnedHistogram | None = None
    lengths: LengthDistribution | None = None
    frequencies: FrequencyTable | None = None
    characters: CharacterProfileResult | None = None


InsightKind = Literal["exact", "estimated", "sample", "at_least", "fingerprint"]


class InsightFact(ResultModel):
    """One figure of an insight card, in words, with the accuracy of the figure
    itself: a card can hold exact counts beside an estimated median."""

    label: str
    value: str
    kind: InsightKind = "exact"
    note: str | None = None


class InsightBar(ResultModel):
    """One bar of a distribution: the exact count of a range of values and its
    share of the values the distribution counts."""

    label: str
    count: int
    share: float


class InsightBars(ResultModel):
    """A distribution drawn as bars. ``kind`` is the accuracy of the counts."""

    caption: str
    kind: InsightKind = "exact"
    items: list[InsightBar]
    note: str | None = None


class InsightTable(ResultModel):
    """A small table of an insight card. The cells are text; ``code`` lists the
    columns whose cells are values of the data, shown as code. ``kind`` is the
    accuracy of the figures of the table."""

    caption: str
    kind: InsightKind = "exact"
    headers: list[str]
    rows: list[list[str]]
    code: list[int] = Field(default_factory=list)
    note: str | None = None


class InsightCard(ResultModel):
    """What one analysis found, laid out for a reader (design 20.19 to 20.28):
    figures, distributions and tables, each qualified by its accuracy. It is
    derived when a page is rendered, from the document alone, and never
    serialized. ``fields`` are the ids of the columns it concerns; ``source``
    says where its figures come from: the second pass, or the Scan; ``scope``
    where it is printed."""

    id: str
    family: str
    title: str
    column: str
    fields: list[str]
    source: Literal["second_pass", "scan"] = "second_pass"
    # Where the card is printed: the dataset panel, the pages of its columns, or
    # both. A card that sums up the columns of a dataset has no column page.
    scope: Literal["dataset", "column", "both"] = "both"
    summary: str = ""
    facts: list[InsightFact] = Field(default_factory=list)
    bars: list[InsightBars] = Field(default_factory=list)
    tables: list[InsightTable] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @property
    def kinds(self) -> list[str]:
        """The accuracies that occur in the card, the exact one first."""
        found = {fact.kind for fact in self.facts}
        found.update(bars.kind for bars in self.bars)
        found.update(table.kind for table in self.tables)
        order = ("exact", "estimated", "sample", "at_least", "fingerprint")
        return [kind for kind in order if kind in found]


class SecondPassRow(ResultModel):
    """One analysis of the second pass, in words: what it was, how it ended and
    what it found. ``kind`` is the accuracy of its figures (``exact``, ``at_least``
    or ``not_computed``)."""

    column: str
    dataset_id: str = ""
    field_id: str = ""
    analysis: str
    status: Literal["complete", "limited", "failed", "skipped"]
    kind: Literal["exact", "at_least", "not_computed", "fingerprint"]
    summary: str


class SecondPassMetrics(ResultModel):
    computed: int
    skipped: int
    failed: int
    already_answered: int
    not_selected: int


class SecondPassView(ResultModel):
    """What the second pass did for a dataset (design 20.1, rule R1): who decided
    it, the analyses it ran, reused or could not run, and why the planner left
    the others out. ``available`` is false for a document that has no
    ``analyses`` member (a Report of an earlier build)."""

    available: bool = False
    mode: Literal["auto", "forced", "off"] = "auto"
    outcome: str = ""
    reason: str | None = None
    metrics: SecondPassMetrics | None = None
    rows: list[SecondPassRow] = Field(default_factory=list)
    # Reasons the planner did not select the other candidates, with their
    # number, most frequent first.
    left_out: list[tuple[str, int]] = Field(default_factory=list)
    source_read: bool = False
    source_verified: bool = False
    seconds: float | None = None
    # What the latest run did, over every dataset of the document.
    executed: int = 0
    reused: int = 0


class RelationCell(ResultModel):
    """One cell of a table: its count and its share of the category's classified
    rows (the conditional percentage the page shows before any score)."""

    count: int
    share: float | None
    # The class that holds most of its category, or a cell that is an exception.
    dominant: bool
    exception: bool


class RelationRow(ResultModel):
    """A category of a table: its cells, its totals and its purity."""

    label: str
    other: bool
    cells: list[RelationCell]
    classified: int
    rows: int
    coverage: float | None
    dominant: str | None
    purity: float | None
    exceptions: int


class RelationException(ResultModel):
    """An exception cell: the category and the class it should not have, the
    exact count of its rows, and the first of them."""

    category: str
    label: str
    count: int
    examples: list[tuple[int, str]]


class RelationRule(ResultModel):
    """A candidate rule learned from the data, in words."""

    category: str
    label: str
    support: int
    confidence: float
    exceptions: int


class RelationTable(ResultModel):
    """The table of one feature of a column against a category, as the page
    prints it. ``strength`` is a word for the score, or ``unstable`` when the
    counts are too low to name one (REL-14); it is ``None`` without a score."""

    feature: str
    feature_label: str
    leading: bool
    kind: Literal["exact"] = "exact"
    source: Literal["source", "samples"]
    sentence: str
    classes: list[str]
    other_class: bool
    rows: list[RelationRow]
    column_totals: list[int]
    total: int
    counted: int
    examined: int
    left_out: str
    purity: float | None
    reverse_purity: float | None
    baseline: float | None
    score: float | None
    strength: str | None
    note: str | None
    exceptions: list[RelationException]
    exception_count: int
    exception_cells: int
    rules: list[RelationRule]


class RelationGroup(ResultModel):
    """The tables that relate two columns, grouped so that the same
    phenomenon is not told three times (REL-16): the leading feature first."""

    category: str
    column: str
    tables: list[RelationTable]
    # The same pair of columns read the other way round, printed right after
    # the group it mirrors and collapsed.
    mirror: bool = False


class CorrelationRow(ResultModel):
    """The correlation of a pair of numeric columns, in words."""

    pair: str
    dataset_id: str = ""
    # The two fields of the pair, for the links to their column pages.
    field_id: str = ""
    partner_id: str = ""
    coefficient: float | None
    pairs: int
    rows: int
    note: str


class RelationsView(ResultModel):
    """The relationships of a dataset (HTML-06): tables of a category against a
    feature, and the correlations of numeric pairs, from the second pass."""

    groups: list[RelationGroup] = Field(default_factory=list)
    correlations: list[CorrelationRow] = Field(default_factory=list)
    # What the planner explored on the row sample to propose them, in words.
    notes: list[str] = Field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.groups or self.correlations)

    @property
    def count(self) -> int:
        return len(self.groups) + len(self.correlations)


class ColumnView(ColumnProfile):
    """A column projection with the canonical facts of its field (``field``,
    read as the scan wrote them) and the figures the pages derive from them."""

    field: FieldResult
    numeric: NumericStats | None
    date_profile: DateProfile | None
    string_profile: StringProfile | None
    distinct: CardinalityView
    quality: list[QualityItem] = Field(default_factory=list)
    # Whether ``quality`` lists every observation of the Scan: an absent
    # observation proves nothing when the list was cut or never computed (R6b).
    observations_state: Literal["complete", "truncated", "unavailable"] = "complete"
    limits: list[LimitView] = Field(default_factory=list)
    patterns: PatternView
    characters: CharacterMapView
    deep: ColumnAnalyses = Field(default_factory=ColumnAnalyses)
    insights: list[InsightCard] = Field(default_factory=list)

    @property
    def type_label(self) -> str:
        """The type of the column in words, for the pages that show one cell."""
        return family_type_label(self.classification.family, self.classification.type)

    @property
    def has_quality_issues(self) -> bool:
        """A candidate anomaly or a confirmed issue (QUAL-01), not a remark."""
        return any(
            item.observation.status != "informational" for item in self.quality
        )

    @property
    def has_observations(self) -> bool:
        return bool(self.quality)


class DatasetView(DatasetProfile):
    """A dataset projection whose columns are ``ColumnView`` objects."""

    columns: list[ColumnView]  # type: ignore[assignment]
    quality: QualityView
    limits: LimitsView
    rows: RowsView
    # Whether the document has a ``derived.patterns`` block.
    patterns_available: bool
    # Columns with the status of their quality issues, for the table filter.
    quality_issue_column_count: int
    observation_column_count: int
    second_pass: SecondPassView = Field(default_factory=SecondPassView)
    relations: RelationsView = Field(default_factory=RelationsView)
    insights: list[InsightCard] = Field(default_factory=list)
