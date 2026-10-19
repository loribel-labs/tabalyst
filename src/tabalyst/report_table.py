# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Rows of the Summary table: what each of the eight cells prints.

Assembles the summary stored with each column (classification, Overview, findings,
Details) into the cells; the template prints a row and computes nothing (contract
summary-table.md 7.3, 20). The words of a cell are written here from the stored
codes and numbers; the rows themselves are not serialized.
"""

from __future__ import annotations

import math

from pydantic import Field

from tabalyst.report_labels import (
    CAVEAT_STATES,
    DATES_CANDIDATES,
    DATES_FORMATS,
    DATES_JOINER,
    DATES_ORDERS,
    DATES_READINGS,
    DATES_TITLE,
    DATES_UNRESOLVED,
    EXAMPLES_HIDDEN,
    EXAMPLES_MASKED,
    FAMILY_LABELS,
    LENGTHS_ANALYTICAL,
    LENGTHS_DOMINANT,
    LENGTHS_MINORITY,
    LENGTHS_NO_EXAMPLES,
    LENGTHS_SAMPLE_EXAMPLES,
    LENGTHS_TITLE,
    LENGTHS_UNIT,
    LIST_STATE_LABELS,
    LIST_STATE_TITLES,
    PATTERNS_DOMINANT,
    PATTERNS_MINORITY,
    PATTERNS_NO_EXAMPLES,
    PATTERNS_SAMPLE_EXAMPLES,
    PATTERNS_SAMPLE_POPULATION,
    PATTERNS_TITLE,
    SIGNAL_NOTES,
    SIGNAL_TARGETS,
    SIGNAL_TITLES,
    TYPES_CLOSEST,
    TYPES_COMPOSITION,
    TYPES_NOTE,
    TYPES_OUTSIDE,
    TYPES_TITLE,
    TYPES_WORDS,
    WHITESPACE_KIND_TITLES,
    WHITESPACE_NO_EXAMPLES,
    WHITESPACE_NOTE,
    WHITESPACE_SAMPLE_EXAMPLES,
    WHITESPACE_TITLES,
    finding_noun,
    finding_text,
    plural,
    spoken_whitespace,
    type_label,
    visible_whitespace,
)
from tabalyst.report_overview import overview_sentence
from tabalyst.report_preview import (
    CheckLine,
    FindingPreview,
    check_lines,
    percent_text,
    preview_of,
)
from tabalyst.report_views import ColumnView, DatasetView
from tabalyst.result_model import ResultModel
from tabalyst.summary_models import (
    ColumnSummary,
    DateDetail,
    Details,
    FindingList,
    Flag,
    LengthDetail,
    MissingFinding,
    PatternDetail,
    QualityColumn,
    QualityView,
    Signal,
    SignalsView,
    StateCount,
    TypeDetail,
    ValidationList,
    VariantDetails,
    WhitespaceDetail,
)

# Finding labels written in a cell; the rest is in the preview of "+3 more"
# (decision 7, lot R9b).
LABELS_SHOWN = 2


class FindingsCell(ResultModel):
    """The Errors or the Issues of a row: the state of the list, the labels of its
    findings and what the checks that found nothing did not cover."""

    state: str
    state_label: str
    state_title: str
    labels: list[str]
    # The preview of every finding of the list, in the order of the labels: the
    # first ``LABELS_SHOWN`` are written in the cell, the others behind "+N more".
    previews: list[FindingPreview]
    # "1 check partially assessed": only on a list that found something, whose
    # state would otherwise hide a check that did not cover everything.
    caveat: str | None
    # The checks it speaks of, and (for a list that found nothing) every check
    # that applies, so that its state can be explained.
    caveat_checks: list[CheckLine]
    checks: list[CheckLine]
    # Sort key: the number of findings.
    order: int

    @property
    def shown(self) -> list[FindingPreview]:
        return self.previews[:LABELS_SHOWN]

    @property
    def rest(self) -> list[FindingPreview]:
        return self.previews[LABELS_SHOWN:]


class MissingCell(ResultModel):
    """Positions with no present value, as the Missing view states them."""

    count: int
    percent: float | None
    state: str


class ColumnRow(ResultModel):
    """One row of the table. Its identity is the dataset id plus the field id,
    never the displayed name (RF-02, CA-03)."""

    dataset_id: str
    field_id: str
    name: str
    path: str
    position: int
    family: str
    family_label: str
    # ``family/type``: the type alone is not unique across families (CA-02).
    type_key: str
    type_label: str
    overview: str
    missing: MissingCell
    errors: FindingsCell
    issues: FindingsCell
    details: Details
    # The groups of spelling variants behind the Issue of the same name, for the hover.
    variants: VariantDetails | None
    flags: list[Flag]

    @property
    def flag_text(self) -> str:
        return " ".join(self.flags)


# The stored signals and quality figures with their words. The document holds codes and
# numbers (``summary_models``); these views add the words and are never serialized.


class SignalTile(Signal):
    """A signal with the words of its tile."""

    noun: str
    title: str
    subtitle: str
    note: str | None
    target: str | None
    # "0.5% of 99,994" when the figure has a known population; the figure alone otherwise.
    share: str | None
    # Width of its bar on the log scale of the overview, from the same share.
    bar: float | None


class SignalsPanel(SignalsView):
    """The signals of a dataset with the words of their tiles."""

    shown: list[SignalTile]  # type: ignore[assignment]


class StateRow(StateCount):
    """A state count with the label of its state."""

    label: str


class ValidationRows(ValidationList):
    """How many columns are in each state, with the words of the states."""

    states: list[StateRow]  # type: ignore[assignment]


class QualityRow(QualityColumn):
    """A column of a quality figure with its findings in words."""

    labels: list[str]


class TopColumn(ResultModel):
    """An affected column: how many kinds of finding it has and how far its widest
    one reaches in the column. The kinds are never added up as values."""

    field_id: str
    name: str
    errors: int
    issues: int
    # The finding that touches the largest share of the column, when any has a share.
    worst: str | None
    worst_cls: str | None
    percent_text: str | None
    # The bar is stacked: the widest Error share, then the widest Issue share. Its
    # length is their sum on a log scale from ``BAR_FLOOR`` to 100%, shared out between
    # the two classes in proportion to their shares; ``bar`` is the whole length.
    bar: float
    error_bar: float
    issue_bar: float
    # Every finding of the column in words, Errors first, for the tooltip and the popover.
    labels: list[str]


class QualityPanel(QualityView):
    """The quality figures of a dataset with the words of their findings and states.

    ``error_findings`` and ``issue_findings`` count findings (a check on a column),
    never occurrences: findings of two codes are not added (findings.md).
    """

    error_findings: int
    issue_findings: int
    # The columns with a finding of each class, a column with both in each, with the
    # words of the findings of that class only.
    error_class_columns: list[QualityRow]
    issue_class_columns: list[QualityRow]
    top: list[TopColumn]

    error_columns: list[QualityRow]  # type: ignore[assignment]
    issue_columns: list[QualityRow]  # type: ignore[assignment]
    clean_columns: list[QualityRow]  # type: ignore[assignment]
    errors: ValidationRows
    issues: ValidationRows


def _small_percent(percent: float) -> str:
    """A share with two decimals, three below 0.01%, and a bound under that: a few
    values among hundreds of thousands must never be written 0%."""
    if percent >= 0.01:
        return percent_text(percent)
    if percent >= 0.001:
        return f"{percent:.3f}".rstrip("0") + "%"
    return "<0.001%"


def _share_percent(signal: Signal) -> float | None:
    """The share of a signal out of what its check looked at, when both are known."""
    population = signal.population
    if population is None or signal.total > population:
        return None
    return 100 * signal.total / population


def _share(signal: Signal) -> str | None:
    percent = _share_percent(signal)
    if percent is None:
        return None
    prefix = "at least " if signal.lower_bound else ""
    return f"{prefix}{_small_percent(percent)} of {signal.population:,}"


def _tile(signal: Signal) -> SignalTile:
    noun = finding_noun(signal.code, signal.unit, signal.total)
    title, subtitle = SIGNAL_TITLES.get(signal.code, (noun[:1].upper() + noun[1:], ""))
    return SignalTile(
        **dict(signal),
        noun=noun,
        title=title,
        subtitle=subtitle,
        note=SIGNAL_NOTES.get(signal.code),
        target=SIGNAL_TARGETS.get(signal.code),
        share=_share(signal),
        bar=None if _share_percent(signal) is None else _bar(_share_percent(signal) or 0.0),
    )


def _signals_panel(view: SignalsView) -> SignalsPanel:
    return SignalsPanel(
        shown=[_tile(signal) for signal in view.shown],
        more=view.more,
        incomplete_columns=view.incomplete_columns,
    )


def _validation_rows(listing: ValidationList) -> ValidationRows:
    return ValidationRows(
        name=listing.name,
        with_findings=listing.with_findings,
        states=[
            StateRow(**dict(item), label=LIST_STATE_LABELS[item.state])
            for item in listing.states
        ],
    )


def _quality_rows(columns: list[QualityColumn]) -> list[QualityRow]:
    return [
        QualityRow(**dict(item), labels=[finding_text(ref) for ref in item.findings])
        for item in columns
    ]


def _class_rows(view: QualityView, cls: str) -> list[QualityRow]:
    """The columns with a finding of one class, each with the words of those findings."""
    rows = []
    for item in (*view.error_columns, *view.issue_columns):
        found = [ref for ref in item.findings if ref.cls == cls]
        if found:
            rows.append(
                QualityRow(**{**dict(item), "findings": found}, labels=[finding_text(r) for r in found])
            )
    return rows


# The smallest share a bar can tell apart; below it the bar keeps its minimal width.
BAR_FLOOR = 0.001


def _bar(percent: float) -> float:
    """Width of a bar on a log scale: a share of 0.01% and one of 10% both stay readable."""
    clamped = min(max(percent, BAR_FLOOR), 100.0)
    return round(100 * math.log10(clamped / BAR_FLOOR) / math.log10(100 / BAR_FLOOR), 1)


def _top_columns(view: QualityView) -> list[TopColumn]:
    """Every affected column, the widest share first, then the kinds of finding."""
    rows = []
    for item in (*view.error_columns, *view.issue_columns):
        shared = [ref for ref in item.findings if ref.percent is not None]
        # An Error outranks any Issue, however small its share: the row must not
        # read as an Issue when the column has an Error.
        worst = max(
            shared, key=lambda ref: (ref.cls == "error", ref.percent or 0.0), default=None
        )
        widest = {
            cls: max((ref.percent or 0.0 for ref in shared if ref.cls == cls), default=0.0)
            for cls in ("error", "issue")
        }
        percent = sum(widest.values()) if shared else None
        bar = 0.0 if not percent else _bar(percent)
        error_bar = bar * widest["error"] / percent if percent else 0.0
        ordered = sorted(item.findings, key=lambda ref: (ref.cls != "error", -(ref.count or 0)))
        rows.append(
            TopColumn(
                field_id=item.field_id,
                labels=[f"{ref.cls.capitalize()}: {finding_text(ref)}" for ref in ordered],
                name=item.name,
                errors=sum(ref.cls == "error" for ref in item.findings),
                issues=sum(ref.cls == "issue" for ref in item.findings),
                worst=None if worst is None else SIGNAL_TITLES.get(worst.code, (worst.code, ""))[0],
                worst_cls=None if worst is None else worst.cls,
                percent_text=None if percent is None else _small_percent(percent),
                bar=bar,
                error_bar=round(error_bar, 1),
                issue_bar=round(bar - error_bar, 1),
            )
        )
    return sorted(
        rows,
        key=lambda row: (
            row.percent_text is None,
            -row.bar,
            -(row.errors + row.issues),
            row.name,
        ),
    )


def _quality_panel(view: QualityView) -> QualityPanel:
    errors = _class_rows(view, "error")
    issues = _class_rows(view, "issue")
    return QualityPanel(
        **{
            **dict(view),
            "top": _top_columns(view),
            "error_findings": sum(len(row.findings) for row in errors),
            "issue_findings": sum(len(row.findings) for row in issues),
            "error_class_columns": errors,
            "issue_class_columns": issues,
            "error_columns": _quality_rows(view.error_columns),
            "issue_columns": _quality_rows(view.issue_columns),
            "clean_columns": _quality_rows(view.clean_columns),
            "errors": _validation_rows(view.errors),
            "issues": _validation_rows(view.issues),
        }
    )


class ColumnTable(ResultModel):
    """The rows of a dataset and the counts of the segment above them."""

    rows: list[ColumnRow]
    error_count: int
    issue_count: int
    observation_count: int
    signals: SignalsPanel
    quality: QualityPanel


def _caveat(listing: FindingList) -> tuple[str | None, list[CheckLine]]:
    """The checks of a list that found something but did not complete."""
    if listing.state != "detected":
        return None, []
    found = {item.code for item in listing.items}
    incomplete = [
        item
        for item in listing.assessments
        if item.state in CAVEAT_STATES and item.code not in found
    ]
    if not incomplete:
        return None, []
    words = []
    for state, phrase in CAVEAT_STATES.items():
        count = sum(item.state == state for item in incomplete)
        if count:
            words.append(f"{plural(count, 'check', 'checks')} {phrase}")
    lines = [
        line
        for line in check_lines(listing, incomplete_only=True)
        if line.code not in found
    ]
    return ", ".join(words), lines


def _cell(listing: FindingList) -> FindingsCell:
    labels = [finding_text(item) for item in listing.items]
    caveat, caveat_checks = _caveat(listing)
    return FindingsCell(
        state=listing.state,
        state_label=LIST_STATE_LABELS[listing.state],
        state_title=LIST_STATE_TITLES[listing.state],
        labels=labels,
        previews=[preview_of(item, listing.assessments) for item in listing.items],
        caveat=caveat,
        caveat_checks=caveat_checks,
        checks=[] if listing.items else check_lines(listing),
        order=len(labels),
    )


def _missing(missing: MissingFinding) -> MissingCell:
    # Two decimals like ``ColumnProfile.missing_percent``: the figure of the JSON.
    percent = missing.share.percent
    return MissingCell(
        count=missing.count,
        percent=None if percent is None else round(percent, 2),
        state=missing.state,
    )


def _summary(column: ColumnView) -> ColumnSummary:
    if column.summary is None:
        raise ValueError(
            f"Column {column.id!r} has no summary: build the Report with its summaries."
        )
    return column.summary


def column_row(column: ColumnView, dataset_id: str) -> ColumnRow:
    """The row of a column, written from its stored summary."""
    summary = _summary(column)
    classification = column.classification
    return ColumnRow(
        dataset_id=dataset_id,
        field_id=column.id,
        name=column.name,
        path=column.path,
        position=column.position,
        family=classification.family,
        family_label=FAMILY_LABELS[classification.family],
        type_key=f"{classification.family}/{classification.type}",
        type_label=type_label(classification.family, classification.type),
        overview=overview_sentence(summary.overview),
        missing=_missing(summary.findings.missing),
        errors=_cell(summary.findings.errors),
        issues=_cell(summary.findings.issues),
        details=summary.details,
        variants=summary.finding_details.variants,
        flags=list(summary.flags),
    )


def page_findings(column: ColumnView) -> tuple[FindingsCell, FindingsCell]:
    """The Errors and the Issues of one column for its own page, with the previews
    the table prints."""
    found = _summary(column).findings
    return _cell(found.errors), _cell(found.issues)


class DetailRow(ResultModel):
    """A line of a detail: a label (words or a format), its figure, a note and the
    example values under it."""

    label: str
    figure: int | None = None
    note: str | None = None
    values: list[str] = Field(default_factory=list)
    # What a screen reader adds to the label (the marks of whitespace are not words).
    spoken: str | None = None


class DetailSection(ResultModel):
    title: str
    rows: list[DetailRow]


class FindingDetailView(ResultModel):
    """A detail of the Findings table with its words: one line of preview for the cell
    and the sections of the hover. Never serialized."""

    title: str
    # The chips of the cell: the formats of the largest pair, one chip each.
    preview: list[str]
    preview_figure: int | None
    # Items of the first list that the preview leaves out.
    preview_more: int
    notes: list[str]
    sections: list[DetailSection]
    # What the lists leave out, in words ("+2 more patterns").
    footer: list[str] = Field(default_factory=list)
    # The words behind each chip of the preview, when the chip is not read as words.
    preview_spoken: list[str] = Field(default_factory=list)


def _omitted(count: int, one: str, many: str) -> list[str]:
    """The line that counts what a bounded list leaves out; none when it left nothing."""
    return [f"+{count:,} more {one if count == 1 else many}"] if count else []


def _dates_view(detail: DateDetail) -> FindingDetailView:
    candidates = [
        DetailRow(label=DATES_JOINER.join(item.formats), figure=item.count)
        for item in detail.candidates
    ]
    sections = [DetailSection(title=DATES_CANDIDATES, rows=candidates)]
    if detail.readings:
        sections.append(
            DetailSection(
                title=DATES_READINGS,
                rows=[
                    DetailRow(label=DATES_ORDERS[item.order], figure=item.count)
                    for item in detail.readings
                ],
            )
        )
    if detail.formats:
        sections.append(
            DetailSection(
                title=DATES_FORMATS,
                rows=[
                    DetailRow(label=item.format, figure=item.count) for item in detail.formats
                ],
            )
        )
    notes = [DATES_UNRESOLVED]
    return FindingDetailView(
        title=DATES_TITLE,
        preview=list(detail.candidates[0].formats) if detail.candidates else [],
        preview_figure=candidates[0].figure if candidates else None,
        preview_more=max(0, len(candidates) - 1) + detail.more_candidates,
        notes=notes,
        sections=sections,
        footer=_omitted(detail.more_candidates, "pair of formats", "pairs of formats")
        + _omitted(detail.more_formats, "format", "formats"),
    )


def _patterns_view(detail: PatternDetail) -> FindingDetailView:
    rows = [
        DetailRow(
            label=item.render,
            figure=item.distinct,
            note=percent_text(100 * item.distinct / detail.population)
            if detail.population
            else None,
            values=[example.value for example in item.examples],
        )
        for item in detail.patterns
    ]
    notes = [
        PATTERNS_NO_EXAMPLES
        if detail.examples_from == "none"
        else PATTERNS_SAMPLE_EXAMPLES
    ]
    if not detail.population_complete:
        notes.append(PATTERNS_SAMPLE_POPULATION)
    dominant = detail.dominant
    sections = [
        DetailSection(
            title=PATTERNS_DOMINANT,
            rows=[DetailRow(label=dominant.render, figure=dominant.distinct)],
        ),
        DetailSection(title=PATTERNS_MINORITY, rows=rows),
    ]
    return FindingDetailView(
        title=PATTERNS_TITLE,
        preview=[item.render for item in detail.patterns[:2]],
        preview_figure=None,
        preview_more=max(0, len(detail.patterns) - 2) + detail.more_patterns,
        notes=notes,
        sections=sections,
        footer=_omitted(detail.more_patterns, "pattern", "patterns"),
    )


def _whitespace_view(detail: WhitespaceDetail, rule: str) -> FindingDetailView:
    kinds = ("leading", "trailing") if rule == "trimmed_cells" else ("repeated",)
    examples = [item for item in detail.examples if item.kind in kinds]
    sections = [
        DetailSection(
            title=WHITESPACE_KIND_TITLES[kind],
            rows=[
                DetailRow(
                    label=visible_whitespace(item.value),
                    spoken=spoken_whitespace(kind, item.value),
                )
                for item in examples
                if item.kind == kind
            ],
        )
        for kind in kinds
        if any(item.kind == kind for item in examples)
    ]
    if detail.state == "masked":
        example_note = EXAMPLES_MASKED
    elif detail.state == "hidden":
        example_note = EXAMPLES_HIDDEN
    elif not examples:
        example_note = WHITESPACE_NO_EXAMPLES
    else:
        example_note = WHITESPACE_SAMPLE_EXAMPLES
    shown = examples[:2]
    return FindingDetailView(
        title=WHITESPACE_TITLES[rule],
        preview=[visible_whitespace(item.value) for item in shown],
        preview_figure=None,
        preview_more=max(0, len(examples) - len(shown)),
        notes=[example_note, WHITESPACE_NOTE] if examples else [example_note],
        sections=sections,
        preview_spoken=[spoken_whitespace(item.kind, item.value) for item in shown],
    )


def _types_view(detail: TypeDetail) -> FindingDetailView:
    def word(kind: str) -> str:
        return TYPES_WORDS.get(kind, kind)

    def share(count: int) -> str:
        return percent_text(100 * count / detail.total)

    rows = [
        DetailRow(label=word(item.type), figure=item.count, note=share(item.count))
        for item in detail.types
    ]
    closest = detail.closest
    one, many = TYPES_OUTSIDE
    return FindingDetailView(
        title=TYPES_TITLE,
        preview=[f"{word(item.type)} {share(item.count)}" for item in detail.types[:2]],
        preview_figure=None,
        preview_more=max(0, len(detail.types) - 2),
        notes=[f"{detail.outside:,} {one if detail.outside == 1 else many}.", TYPES_NOTE],
        sections=[
            DetailSection(title=TYPES_COMPOSITION, rows=rows),
            DetailSection(
                title=TYPES_CLOSEST,
                rows=[DetailRow(label=word(closest.type), figure=closest.count, note=share(closest.count))],
            ),
        ],
    )


def _characters(length: int) -> str:
    return f"{length:,} {LENGTHS_UNIT[0] if length == 1 else LENGTHS_UNIT[1]}"


def _lengths_view(detail: LengthDetail) -> FindingDetailView:
    rows = [
        DetailRow(
            label=_characters(item.length),
            figure=item.count,
            note=percent_text(100 * item.count / detail.total) if detail.total else None,
            values=[example.value for example in item.examples],
        )
        for item in detail.lengths
    ]
    if detail.state == "masked":
        example_note = EXAMPLES_MASKED
    elif detail.state == "hidden":
        example_note = EXAMPLES_HIDDEN
    elif detail.examples_from == "none":
        example_note = LENGTHS_NO_EXAMPLES
    else:
        example_note = LENGTHS_SAMPLE_EXAMPLES
    dominant = detail.dominant
    return FindingDetailView(
        title=LENGTHS_TITLE,
        preview=[_characters(item.length) for item in detail.lengths[:2]],
        preview_figure=None,
        preview_more=max(0, len(detail.lengths) - 2) + detail.more_lengths,
        notes=[example_note, LENGTHS_ANALYTICAL],
        sections=[
            DetailSection(
                title=LENGTHS_DOMINANT,
                rows=[DetailRow(label=_characters(dominant.length), figure=dominant.count)],
            ),
            DetailSection(title=LENGTHS_MINORITY, rows=rows),
        ],
        footer=_omitted(detail.more_lengths, "length", "lengths"),
    )


def finding_detail_views(dataset: DatasetView) -> dict[tuple[str, str], FindingDetailView]:
    """The details of a dataset's Findings table that are not spelling variants, by
    column id and observation rule."""
    views: dict[tuple[str, str], FindingDetailView] = {}
    for column in dataset.columns:
        if column.summary is None:
            continue
        dates = column.summary.finding_details.dates
        if dates is not None:
            views[(column.id, "ambiguous_dates")] = _dates_view(dates)
        patterns = column.summary.finding_details.patterns
        if patterns is not None:
            views[(column.id, "minority_pattern")] = _patterns_view(patterns)
        lengths = column.summary.finding_details.lengths
        if lengths is not None:
            views[(column.id, "minority_length")] = _lengths_view(lengths)
        types = column.summary.finding_details.types
        if types is not None:
            views[(column.id, "mixed_types")] = _types_view(types)
        whitespace = column.summary.finding_details.whitespace
        if whitespace is not None:
            for change in whitespace.stages:
                rule = {"trim": "trimmed_cells", "collapse_whitespace": "collapsed_whitespace"}[change.stage]
                views[(column.id, rule)] = _whitespace_view(whitespace, rule)
    return views


def column_table(dataset: DatasetView) -> ColumnTable:
    """The table of a dataset, one row per column in the order of the report."""
    table = dataset.table
    if table is None:
        raise ValueError(
            f"Dataset {dataset.id!r} has no table summary: build the Report with its summaries."
        )
    return ColumnTable(
        rows=[column_row(column, dataset.id) for column in dataset.columns],
        error_count=table.error_count,
        issue_count=table.issue_count,
        observation_count=table.observation_count,
        signals=_signals_panel(table.signals),
        quality=_quality_panel(table.quality),
    )
