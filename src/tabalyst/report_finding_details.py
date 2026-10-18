# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Details of a finding of the Findings table: the evidence behind a count.

The spelling variants (``variant_groups``): the groups to correct, each with its
spellings; the ambiguous dates (``ambiguous_dates``): the formats that fit the same
values. Values go through the exposure of their column, whatever the document holds
(contract summary-table.md 7.6 and 22).
"""

from __future__ import annotations

import re
from typing import NamedTuple

from tabalyst.report_details import STATES
from tabalyst.report_findings import detector_of
from tabalyst.report_views import ColumnView
from tabalyst.result_model import ResultModel
from tabalyst.scanner.exposure import ExposureGate, ExposureMode
from tabalyst.scanner.models import DetectorComplete, FieldResult, SampleEntry
from tabalyst.scanner.normalization import Normalizer
from tabalyst.summary_models import (
    DateCandidate,
    DateDetail,
    DateFormat,
    DateOrder,
    DateReading,
    DominantLength,
    DominantPattern,
    FindingDetails,
    FindingExample,
    LengthDetail,
    MinorityLength,
    MinorityPattern,
    PatternDetail,
    Spelling,
    TypeCount,
    TypeDetail,
    VariantDetails,
    VariantGroupDetail,
    VariantState,
    WhitespaceChange,
    WhitespaceDetail,
    WhitespaceExample,
    WhitespaceKind,
    WhitespaceKindCount,
    WhitespaceStage,
)

# Groups and spellings written in the hover; the rest is counted.
GROUPS_SHOWN = 20
SPELLINGS_SHOWN = 6
# Pairs of formats and formats read without doubt written for ambiguous dates.
DATE_FORMATS_SHOWN = 6
DATE_ORDERS: tuple[DateOrder, ...] = ("DMY", "MDY")
# Minority patterns written, and the examples of each (contract summary-table.md 22.3).
PATTERNS_SHOWN = 5
LENGTHS_SHOWN = 5
EXAMPLES_PER_ITEM = 3
EXAMPLES_PER_KIND = 3
# An example is cut here, whatever length the Scan stored: a column of long texts must not
# weigh on the document.
EXAMPLE_MAX_CHARS = 64


def variant_details(column: ColumnView) -> VariantDetails | None:
    """The variants of a column, or ``None`` when it has no group to show.

    A hidden column gives no value; a masked one gives merged masks, which are not
    spellings of the source (``state`` says so). The groups are the largest
    the scan listed, at most ``GROUPS_SHOWN``; ``more_groups`` counts the others when the total is known.
    """
    stats = column.normalization
    if not stats.variant_groups and not stats.variant_group_count:
        return None
    mode: ExposureMode = column.exposure or "show"
    states: dict[ExposureMode, VariantState] = {
        "show": "shown",
        "mask": "masked",
        "hide": "hidden",
    }
    state = states[mode]
    gate = ExposureGate(mode)
    groups: list[VariantGroupDetail] = []
    for group in stats.variant_groups[:GROUPS_SHOWN]:
        counts = gate.counts((item.value, item.count) for item in group.variants)
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        # A mask can merge every spelling of a group into one: nothing to correct.
        if len(ordered) < (1 if mode == "show" else 2):
            continue
        listed = ordered[:SPELLINGS_SHOWN]
        groups.append(
            VariantGroupDetail(
                spellings=[
                    Spelling(value=value, count=count, most_frequent=index == 0)
                    for index, (value, count) in enumerate(listed)
                ],
                more_spellings=max(0, group.distinct_count - len(listed)),
            )
        )
    total = stats.variant_group_count
    return VariantDetails(
        state=state,
        groups=groups,
        more_groups=None if total is None else max(0, total - len(groups)),
    )


class ExposedVariantGroup(ResultModel):
    """A stored group of spelling variants as the column page lists it, through the
    exposure: the key and the spellings are masks for a masked column."""

    key: str
    count: int
    truncated: bool
    variants: list[tuple[str, int]]


def exposed_variant_groups(column: ColumnView) -> list[ExposedVariantGroup]:
    """Every stored variant group of a column through its exposure (CA-19): nothing
    for a hidden column, merged masks for a masked one."""
    mode: ExposureMode = column.exposure or "show"
    if mode == "hide":
        return []
    gate = ExposureGate(mode)
    return [
        ExposedVariantGroup(
            key=gate.value(group.key) or "",
            count=group.count,
            truncated=group.truncated,
            variants=list(gate.counts((v.value, v.count) for v in group.variants).items()),
        )
        for group in column.normalization.variant_groups
    ]


def date_details(column: ColumnView) -> DateDetail | None:
    """What makes the dates of a column ambiguous, or ``None`` when the column has no
    ``ambiguous_dates`` observation or the date detector kept no account of it.

    Everything comes from the detector's account of the ambiguity and from the date
    profile of the column; the ambiguity is never resolved here. Formats are shapes, so
    the exposure of the column changes nothing (contract summary-table.md 22.4).
    """
    if not any(item.observation.rule == "ambiguous_dates" for item in column.quality):
        return None
    detector = detector_of(column.field, "date")
    if not isinstance(detector, DetectorComplete):
        return None
    ambiguity = detector.details.get("ambiguity") or {}
    if not ambiguity.get("count"):
        return None
    candidates = sorted(
        (
            DateCandidate(formats=list(item["formats"]), count=item["count"])
            for item in ambiguity.get("candidates", [])
        ),
        key=lambda item: (-item.count, item.formats),
    )
    evidence = ambiguity.get("evidence", {})
    readings = sorted(
        (
            DateReading(order=order, count=evidence[order])
            for order in DATE_ORDERS
            if evidence.get(order)
        ),
        key=lambda item: (-item.count, item.order),
    )
    known = sorted(
        (
            DateFormat(format=item.format, order=item.order, count=item.count)
            for item in (column.date_profile.formats if column.date_profile else [])
        ),
        key=lambda item: (-item.count, item.format),
    )
    return DateDetail(
        ambiguous_count=ambiguity["count"],
        candidates=candidates[:DATE_FORMATS_SHOWN],
        more_candidates=max(0, len(candidates) - DATE_FORMATS_SHOWN),
        readings=readings,
        formats=known[:DATE_FORMATS_SHOWN],
        more_formats=max(0, len(known) - DATE_FORMATS_SHOWN),
    )


class ExampleSource(NamedTuple):
    """Where the examples of the details are read (contract summary-table.md 22.5).

    ``field`` holds the whole sample of the Scan, ``None`` when it is not at hand (a
    document attached at render: the base of the column is used); ``normalizer`` turns an
    original value into the analytical text the lengths are counted on.
    """

    field: FieldResult | None
    normalizer: Normalizer


def sample_entries(field: FieldResult) -> dict[int, SampleEntry]:
    """The sampled original values this field holds, by entry id: the sample and the
    samples by length."""
    samples = field.values.samples
    entries = {entry.id: entry for entry in samples.listed}
    if samples.by_length is not None:
        entries.update((entry.id, entry) for entry in samples.by_length.listed)
    return entries


def _examples(ids: list[int], entries: dict[int, SampleEntry]) -> list[FindingExample]:
    """The first ``EXAMPLES_PER_ITEM`` values the ids point to that the sample holds."""
    taken = [entries[item] for item in ids if item in entries][:EXAMPLES_PER_ITEM]
    return [
        FindingExample(
            value=entry.value[:EXAMPLE_MAX_CHARS],
            count=entry.count,
            truncated=len(entry.value) > EXAMPLE_MAX_CHARS,
        )
        for entry in taken
    ]


def _field(column: ColumnView, source: ExampleSource | None) -> FieldResult:
    return source.field if source is not None and source.field is not None else column.field


def pattern_details(
    column: ColumnView, source: ExampleSource | None = None
) -> PatternDetail | None:
    """The patterns behind the ``minority_pattern`` observation of a column, or ``None``
    when it has none or the document holds no pattern entry for it.

    A pattern writes the literal text its values share (a prefix, a domain), so its render
    is a value of the source: for a ``mask`` or ``hide`` column there is no detail, as the
    Scan itself discovers no pattern there (``excluded: exposure``), whatever the document
    holds (CA-19, contract summary-table.md 22.4).

    ``source`` is the field with the sample the Scan held before the Report reduced it
    (22.5); without it the examples come from the field of the column, which may no longer
    hold the entries the patterns point to.
    """
    if column.exposure in ("mask", "hide"):
        return None
    observation = next(
        (
            item.observation
            for item in column.quality
            if item.observation.rule == "minority_pattern"
        ),
        None,
    )
    entry = column.patterns.entry
    if observation is None or entry is None:
        return None
    every = entry.all_patterns()
    by_id = {pattern.id: pattern for pattern in every}
    named = sorted(
        (by_id[item] for item in observation.patterns if item in by_id),
        key=lambda pattern: (-pattern.d, pattern.id),
    )
    if not named:
        return None
    entries = sample_entries(_field(column, source))
    listed = [
        MinorityPattern(
            id=pattern.id,
            render=pattern.render,
            distinct=pattern.d,
            examples=_examples(pattern.examples, entries),
        )
        for pattern in named[:PATTERNS_SHOWN]
    ]
    dominant = max(every, key=lambda pattern: pattern.d)
    return PatternDetail(
        examples_from="sample" if any(item.examples for item in listed) else "none",
        population=entry.population.distinct,
        population_complete=entry.population.complete,
        dominant=DominantPattern(render=dominant.render, distinct=dominant.d),
        patterns=listed,
        more_patterns=len(observation.patterns) - len(listed),
    )


def length_details(
    column: ColumnView, source: ExampleSource | None = None
) -> LengthDetail | None:
    """The lengths behind the ``minority_length`` observation of a column, or ``None``
    when it has none or the exact histogram is not at hand.

    The minority lengths are every length of the histogram but the dominant one: the Scan
    raises the observation only when the dominant length holds nearly every text, and the
    detail never re-decides the rule. Examples are analytical texts of the length, read from
    the cases the Scan kept for it (scan design 18.15; ``source`` gives the normalization that
    turns an original text into the analytical one), through the exposure.
    """
    if not any(item.observation.rule == "minority_length" for item in column.quality):
        return None
    measure = column.field.string_lengths
    if measure.status != "complete" or not measure.value.length_histogram:
        return None
    histogram = sorted(
        measure.value.length_histogram, key=lambda item: (-item.count, item.length)
    )
    dominant, others = histogram[0], histogram[1:]
    if not others:
        return None
    mode: ExposureMode = column.exposure or "show"
    gate = ExposureGate(mode)
    listed = others[:LENGTHS_SHOWN]
    cases = _field(column, source).values.samples.cases
    classes = (
        {item.length: item for item in cases.lengths.classes}
        if cases is not None and cases.lengths is not None
        else {}
    )
    minority = []
    for item in listed:
        case = classes.get(item.length)
        texts: dict[str, int] = {}
        if case is not None and mode != "hide":
            # The cases hold original texts; the figure counts the analytical text, so two
            # originals that normalize alike are one example.
            analytical = source.normalizer.analytical if source is not None else str
            for entry in case.listed:
                text = analytical(entry.value)
                texts[text] = texts.get(text, 0) + entry.count
        exposed = gate.counts(texts.items())
        shown = list(exposed.items())[:EXAMPLES_PER_ITEM]
        minority.append(
            MinorityLength(
                length=item.length,
                count=item.count,
                examples=[
                    FindingExample(
                        value=value[:EXAMPLE_MAX_CHARS],
                        count=count,
                        truncated=len(value) > EXAMPLE_MAX_CHARS,
                    )
                    for value, count in shown
                ],
                complete=bool(
                    case is not None
                    and case.selection == "all"
                    and exposed
                    and len(exposed) <= EXAMPLES_PER_ITEM
                ),
            )
        )
    return LengthDetail(
        state=STATES[mode],
        examples_from="cases" if any(item.examples for item in minority) else "none",
        total=measure.value.count,
        dominant=DominantLength(length=dominant.length, count=dominant.count),
        lengths=minority,
        more_lengths=len(others) - len(listed),
    )


# The rule of the Scan behind each stage, and the stage and order of the kinds of its cases.
WHITESPACE_RULES: dict[WhitespaceStage, str] = {"trim": "trimmed_cells", "collapse_whitespace": "collapsed_whitespace"}
KIND_ORDER: tuple[WhitespaceKind, ...] = ("leading", "trailing", "repeated")
KIND_STAGE: dict[WhitespaceKind, WhitespaceStage] = {
    "leading": "trim",
    "trailing": "trim",
    "repeated": "collapse_whitespace",
}


ELLIPSIS = "\u2026"
# The first run of whitespace the ``collapse_whitespace`` stage rewrites.
_RUN = re.compile("[^\\S\r\n]{2,}|[^\\S \r\n]")


def whitespace_window(kind: WhitespaceKind, value: str) -> tuple[str, bool]:
    """The part of a long value that shows its whitespace, with an ellipsis on each cut
    side, and whether it was cut. A text cut at its head would hide trailing whitespace, so
    each kind keeps its own end (contract summary-table.md 22.4)."""
    if len(value) <= EXAMPLE_MAX_CHARS:
        return value, False
    room = EXAMPLE_MAX_CHARS - 1
    if kind == "trailing":
        return ELLIPSIS + value[-room:], True
    if kind == "leading":
        return value[:room] + ELLIPSIS, True
    found = _RUN.search(value)
    start = max(0, (found.start() if found else 0) - 20)
    window = value[start : start + EXAMPLE_MAX_CHARS - 2]
    return (ELLIPSIS if start else "") + window + ELLIPSIS, True


def whitespace_details(
    column: ColumnView, source: ExampleSource | None = None
) -> WhitespaceDetail | None:
    """The whitespace behind the ``trimmed_cells`` and ``collapsed_whitespace``
    observations of a column, or ``None`` when it has neither.

    The stages are those the Scan ran and that changed texts. The examples are original
    texts of the cases the Scan kept for each kind (scan design 18.15), in the order the Scan
    lists them, at most ``EXAMPLES_PER_KIND`` of each kind, through the exposure; the count
    of the cells of each kind is the Scan's, exact. A kind is ``complete`` when its examples
    are every distinct text of it. Without cases (a document attached at render, or cases
    turned off) the kinds and examples are empty and ``examples_from`` says ``none``.
    """
    observed = {
        stage
        for stage, rule in WHITESPACE_RULES.items()
        if any(item.observation.rule == rule for item in column.quality)
    }
    changes = [
        WhitespaceChange(stage=stage, changed=item.changed)
        for stage in WHITESPACE_RULES
        if stage in observed
        for item in column.field.normalization.stages
        if item.stage == stage and item.changed
    ]
    if not changes:
        return None
    mode: ExposureMode = column.exposure or "show"
    gate = ExposureGate(mode)
    cases = _field(column, source).values.samples.cases
    by_kind = (
        {item.kind: item for item in cases.whitespace or ()} if cases is not None else {}
    )
    stages = {item.stage for item in changes}
    kinds: list[WhitespaceKindCount] = []
    examples = []
    for kind in KIND_ORDER:
        case = by_kind.get(kind)
        if case is None or KIND_STAGE[kind] not in stages:
            continue
        # Equal masks are merged first, then the first few are shown.
        exposed = gate.counts((entry.value, entry.count) for entry in case.listed)
        for value, count in list(exposed.items())[:EXAMPLES_PER_KIND]:
            text, cut = whitespace_window(kind, value)
            examples.append(WhitespaceExample(kind=kind, value=text, count=count, truncated=cut))
        kinds.append(
            WhitespaceKindCount(
                kind=kind,
                occurrences=case.occurrences,
                complete=bool(
                    case.selection == "all" and exposed and len(exposed) <= EXAMPLES_PER_KIND
                ),
            )
        )
    return WhitespaceDetail(
        state=STATES[mode],
        examples_from="cases" if examples else "none",
        stages=changes,
        kinds=kinds,
        examples=examples,
    )


def type_details(column: ColumnView) -> TypeDetail | None:
    """The composition by technical type behind the ``mixed_types`` observation of a column,
    or ``None`` when it has none or the scan counted no type.

    The closest family is chosen as the Scan does when it counts the values outside it
    (``quality._best_family_count``): the integers, the integers and the other numbers
    together, the dates, the booleans or the text, whichever holds the most. A tie goes to the
    first of that order, so the figure is stable.
    """
    if not any(item.observation.rule == "mixed_types" for item in column.quality):
        return None
    counts = {kind: count for kind, count in column.field.technical_type.counts.items() if count}
    if not counts:
        return None
    total = sum(counts.values())
    integers = counts.get("integer", 0)
    families = [
        ("integer", integers),
        ("number", integers + counts.get("number", 0)),
        ("date", counts.get("date", 0)),
        ("boolean", counts.get("boolean", 0)),
        ("text", counts.get("text", 0)),
    ]
    kind, held = max(families, key=lambda item: item[1])
    return TypeDetail(
        total=total,
        types=[
            TypeCount(type=name, count=count)
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        closest=TypeCount(type=kind, count=held),
        outside=total - held,
    )


def finding_details(
    column: ColumnView, source: ExampleSource | None = None
) -> FindingDetails:
    """Every detail of the Findings table for a column, through its exposure. ``source``
    gives the examples their sample and the normalization of the lengths."""
    return FindingDetails(
        variants=variant_details(column),
        dates=date_details(column),
        patterns=pattern_details(column, source),
        lengths=length_details(column, source),
        whitespace=whitespace_details(column, source),
        types=type_details(column),
    )
