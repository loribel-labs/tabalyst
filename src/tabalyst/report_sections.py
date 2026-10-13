# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Views of the findings of a Scan that the report pages read: the quality
observations, the limits, the inferred patterns, the row sample and the
qualified distinct count of a column.

Everything here is computed when a page is rendered, from the document alone
(HTML-01): no source, no recomputation of a rule. A block the document does not
have is reported as not computed and never rebuilt (design 18.14).
"""

import unicodedata
from typing import Literal

from tabalyst.report_labels import (
    AT_LEAST,
    CHARACTER_CATEGORIES,
    CHARACTER_REASONS,
    EXACT,
    MEASURE_LABELS,
    MEASURE_REASON_SETTINGS,
    PATTERN_REASONS,
    POPULATION_NOUNS,
    REASON_NOTES,
    REASON_SETTINGS,
    SAMPLE,
    STATUS_CLASSES,
    STATUS_TITLES,
    STATUS_WORDS,
    observation_kind,
    rule_label,
)
from tabalyst.report_views import (
    CardinalityView,
    CharacterMapView,
    CharacterShare,
    CharacterTile,
    DiagnosticLocation,
    DiagnosticProfile,
    LimitsView,
    LimitView,
    PatternCellView,
    PatternFamilyView,
    PatternNodeView,
    PatternPatternView,
    PatternRow,
    PatternTableView,
    PatternView,
    QualityGroup,
    QualityItem,
    QualityView,
    RowsView,
)
from tabalyst.scanner.models import (
    CardinalityLimited,
    CharacterMap,
    Complete,
    DatasetResult,
    Derived,
    Diagnostic,
    FieldCharacters,
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsFailed,
    FieldPatternsNotApplicable,
    FieldResult,
    Limited,
    NotApplicable,
    Observation,
    Observations,
    PatternNode,
    PatternTable,
)
from tabalyst.scanner.quality import ANALYTICAL_STAGES
from tabalyst.scanner.secondpass.models import (
    CharacterProfileResult,
    PatternCounts,
    PatternNodeCount,
    PatternTableCount,
)

# Worst accuracy first: a group is as sure as its least sure item.
_KIND_RANK = {AT_LEAST: 0, SAMPLE: 1, EXACT: 2}


def cardinality_view(field: FieldResult, exact_original: int | None = None) -> CardinalityView:
    """The distinct analytical values of a column, exact or qualified.

    The count follows the last enabled analytical stage. A stage that changed
    nothing (``equals``) is the identity on the distinct values, so the raw
    count and its estimate are still the right ones; a stage that changed
    something has its own count, which carries no estimate (design 10).

    ``exact_original`` is the exact distinct count of the original values that
    the second pass made. It answers a count the scan stopped only while no
    stage changes the values: after a stage that does, the figure shown is of
    another population and the exact count of the originals is not it.
    """
    measure = field.values.cardinality
    changed = False
    for stage in field.normalization.stages:
        if stage.stage in ANALYTICAL_STAGES and stage.enabled and stage.equals is None:
            measure = stage.cardinality
            changed = True
    if exact_original is not None and not changed and isinstance(measure, Limited):
        return CardinalityView(kind="exact", source="second_pass", value=exact_original)
    if isinstance(measure, Complete):
        return CardinalityView(kind="exact", value=measure.value)
    if isinstance(measure, NotApplicable):
        return CardinalityView(kind="exact", value=0)
    if not isinstance(measure, Limited):
        return CardinalityView(kind="not_counted")
    estimate = measure.estimate if isinstance(measure, CardinalityLimited) else None
    return CardinalityView(
        kind="at_least" if measure.lower_bound is not None else "not_counted",
        value=measure.lower_bound,
        estimate=None if estimate is None else estimate.value,
        error=None if estimate is None else estimate.relative_standard_error,
        upper_bound=(
            measure.upper_bound if isinstance(measure, CardinalityLimited) else None
        ),
        reason=measure.reason,
        limit=measure.limit,
    )


# Quality -----------------------------------------------------------------------


def _quality_item(
    observation: Observation, names: dict[str, tuple[str, int | None]]
) -> QualityItem:
    label = rule_label(observation.rule)
    name, position = names.get(observation.field, (observation.field, None))
    return QualityItem(
        observation=observation,
        title=label.title,
        anchor=label.anchor,
        status_word=STATUS_WORDS[observation.status],
        status_title=STATUS_TITLES[observation.status],
        status_class=STATUS_CLASSES[observation.status],
        kind=observation_kind(observation),
        noun=POPULATION_NOUNS[observation.population],
        field_name=name if observation.field is not None else None,
        column_position=position,
    )


def _quality_groups(items: list[QualityItem]) -> list[QualityGroup]:
    """One group per rule, in the order the items come (status, then rule)."""
    grouped: dict[str, list[QualityItem]] = {}
    for item in items:
        grouped.setdefault(item.observation.rule, []).append(item)
    groups = []
    for rule, members in grouped.items():
        first = members[0]
        fields = {item.observation.field for item in members} - {None}
        of = first.observation.of if len(members) == 1 else None
        groups.append(
            QualityGroup(
                rule=rule,
                title=first.title,
                anchor=first.anchor,
                status_word=first.status_word,
                status_title=first.status_title,
                status_class=first.status_class,
                kind=min((item.kind for item in members), key=_KIND_RANK.__getitem__),
                noun=first.noun,
                fields=len(fields),
                total=sum(item.observation.count for item in members),
                of=of,
                headline=rule_label(rule).headline,
            )
        )
    return groups


def quality_view(
    observations: Observations | None,
    dataset_id: str,
    names: dict[str, tuple[str, int | None]],
) -> QualityView:
    """The findings of a dataset, and of the whole scan, from ``observations``.
    ``names`` maps a field id to its display name and column position."""
    if observations is None:
        return QualityView(available=False)
    items = [
        _quality_item(observation, names)
        for observation in observations.items
        if observation.dataset in (None, dataset_id)
    ]
    summary = next(
        (item for item in observations.datasets if item.dataset == dataset_id), None
    )
    return QualityView(
        available=True,
        summary=summary,
        items=items,
        groups=_quality_groups(items),
        truncated=observations.truncated,
    )


# Limits ------------------------------------------------------------------------


def limit_views(
    observations: Observations | None,
    dataset_id: str,
    paths: dict[str, str],
    columns: set[str],
) -> list[LimitView]:
    """The limits of the scan that concern a dataset. ``paths`` maps a field id
    to its display path and ``columns`` holds the ids of the fields shown as
    columns (a column has the id of its field)."""
    if observations is None:
        return []
    return [
        LimitView(
            id=limit.id,
            field_path=paths.get(limit.field, limit.field) if limit.field else None,
            column_id=limit.field if limit.field in columns else None,
            measure=limit.measure,
            label=MEASURE_LABELS.get(limit.measure, limit.measure),
            reason=limit.reason,
            setting=MEASURE_REASON_SETTINGS.get(
                (limit.measure, limit.reason), REASON_SETTINGS.get(limit.reason)
            ),
            note=REASON_NOTES.get(limit.reason),
            limit=limit.limit,
            lower_bound=limit.lower_bound,
            diagnostic=limit.diagnostic,
        )
        for limit in observations.limits
        if limit.dataset in (None, dataset_id)
    ]


def diagnostic_views(
    diagnostics: list[Diagnostic], dataset: DatasetResult
) -> list[DiagnosticProfile]:
    """Diagnostics of a dataset and of the whole scan, with the display path of
    their field."""
    displays = {field.id: field.display for field in dataset.fields}
    return [
        DiagnosticProfile(
            code=diagnostic.code,
            level=diagnostic.level,
            message=diagnostic.message,
            count=diagnostic.count,
            dataset=diagnostic.dataset,
            path=displays.get(diagnostic.field, diagnostic.field),
            detector=diagnostic.detector,
            locations=[
                DiagnosticLocation.model_validate(location)
                for location in diagnostic.locations
            ],
        )
        for diagnostic in diagnostics
        if diagnostic.dataset in (None, dataset.id)
    ]


def limits_view(
    observations: Observations | None,
    diagnostics: list[Diagnostic],
    dataset: DatasetResult,
    columns: set[str],
) -> LimitsView:
    paths = {field.id: field.display for field in dataset.fields}
    return LimitsView(
        available=observations is not None,
        items=limit_views(observations, dataset.id, paths, columns),
        untracked_observations=dataset.structure.untracked_observations,
        depth_truncated_observations=dataset.structure.depth_truncated_observations,
        diagnostics=diagnostic_views(diagnostics, dataset),
    )


# Patterns ----------------------------------------------------------------------


def _sample_values(field: FieldResult) -> dict[int, str]:
    """The original values of the sample this document holds, by entry id."""
    samples = field.values.samples
    values = {entry.id: entry.value for entry in samples.listed}
    if samples.by_length is not None:
        values.update((entry.id, entry.value) for entry in samples.by_length.listed)
    return values


FACET_WORDS = {
    "composition": "structure",
    "lengths": "lengths",
}


def facet_text(facet: str) -> str:
    """A facet in words: ``head:2`` is the start of the second token."""
    kind, _, number = facet.partition(":")
    if not number:
        return FACET_WORDS.get(kind, kind)
    return {"head": "start", "tail": "end", "token": "whole"}.get(kind, kind) + f" of token {number}"


def _share(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _node_view(
    node: PatternNode,
    total: tuple[int, int],
    counted: dict[str, PatternNodeCount],
) -> tuple[PatternNodeView, int]:
    """A node with its descendants, and the number of nodes in its subtree."""
    children = [_node_view(child, total, counted) for child in node.nodes]
    tally = counted.get(node.id)
    return (
        PatternNodeView(
            id=node.id,
            level=node.level,
            facet_text=facet_text(node.facet),
            value=node.value,
            also=[f"{facet_text(item.facet)} {item.value}" for item in node.also],
            render=node.render,
            role=node.role,
            d=node.d,
            o=node.o,
            share_d=_share(node.d, total[0]),
            share_o=_share(node.o, total[1]),
            bits_d=node.gain.bits_d if node.gain else None,
            bits_o=node.gain.bits_o if node.gain else None,
            validated=tally.occurrences if tally else None,
            validated_distinct=tally.distinct.count if tally else None,
            validated_exact=tally.distinct.accuracy == "exact" if tally else True,
            nodes=[view for view, _ in children],
        ),
        1 + sum(size for _, size in children),
    )


def _counted(nodes: list[PatternNodeCount], into: dict[str, PatternNodeCount]) -> None:
    for node in nodes:
        into[node.id] = node
        _counted(node.nodes, into)


def _table_view(
    table: PatternTable, total: tuple[int, int], counted: PatternTableCount | None
) -> PatternTableView:
    held = {cell.value: cell.occurrences for cell in counted.cells} if counted else {}
    return PatternTableView(
        facet=table.facet,
        facet_text=facet_text(table.facet),
        cells=[
            PatternCellView(
                value=cell.value,
                d=cell.d,
                o=cell.o,
                share_d=_share(cell.d, total[0]),
                share_o=_share(cell.o, total[1]),
                validated=held.get(cell.value) if counted else None,
            )
            for cell in table.cells
        ],
        others_distinct=table.others.distinct,
        others_d=table.others.d,
        others_o=table.others.o,
        bits=table.gain.sigma if table.gain else None,
        saturated=counted.saturated if counted else False,
    )


def pattern_view(
    field: FieldResult,
    entry: FieldPatterns | None,
    derived: Derived | None,
    counts: PatternCounts | None = None,
) -> PatternView:
    """The patterns of a column with their examples that resolve here. A
    Report keeps the smallest priorities of the sample, so an example of the
    Scan may not be among them; the view counts those it cannot show. ``counts``
    are the occurrences the second pass counted on the whole file, when it ran."""
    if derived is None or derived.patterns is None or entry is None:
        return PatternView(status="missing")
    if isinstance(entry, FieldPatternsNotApplicable):
        return PatternView(
            status="not_applicable",
            reason=entry.reason,
            reason_text=PATTERN_REASONS.get(entry.reason, entry.reason),
        )
    if isinstance(entry, FieldPatternsFailed):
        return PatternView(
            status="failed",
            reason=entry.reason,
            reason_text=PATTERN_REASONS.get(entry.reason, entry.reason),
        )
    assert isinstance(entry, FieldPatternsComplete)
    values = _sample_values(field)
    examples: dict[str, list[str]] = {}
    unresolved: dict[str, int] = {}
    total = entry.population.distinct
    sizes = (total, entry.population.occurrences)
    families = {pattern.id: family for family in entry.families for pattern in family.patterns}
    family_counts = {item.id: item for item in counts.families} if counts else {}
    pattern_counts: dict[str, PatternNodeCount] = {}
    for item in family_counts.values():
        _counted(item.patterns, pattern_counts)
    rows: list[PatternRow] = []
    for number, pattern in enumerate(sorted(entry.all_patterns(), key=lambda item: -item.d)):
        shown = [values[item] for item in pattern.examples if item in values]
        examples[pattern.id] = shown
        unresolved[pattern.id] = len(pattern.examples) - len(shown)
        rows.append(
            PatternRow(
                id=pattern.id,
                family=families[pattern.id].id,
                family_key=families[pattern.id].key,
                render=pattern.render,
                role="principal" if number == 0 else "secondary",
                distinct=pattern.d,
                share=_share(pattern.d, total),
                length=sum(
                    token.min * (len(token.text) if token.text is not None else 1)
                    for token in pattern.signature
                ),
            )
        )
    family_views: list[PatternFamilyView] = []
    node_count = 0
    for family in entry.families:
        counted_family = family_counts.get(family.id)
        table_counts = {t.facet: t for t in counted_family.tables} if counted_family else {}
        pattern_views: list[PatternPatternView] = []
        for pattern in family.patterns:
            nodes = [_node_view(node, sizes, pattern_counts) for node in pattern.nodes]
            tally = pattern_counts.get(pattern.id)
            size = sum(count for _, count in nodes)
            node_count += size
            pattern_views.append(
                PatternPatternView(
                    id=pattern.id,
                    render=pattern.render,
                    format=pattern.format,
                    lengths=pattern.lengths,
                    d=pattern.d,
                    o=pattern.o,
                    share_d=_share(pattern.d, sizes[0]),
                    share_o=_share(pattern.o, sizes[1]),
                    examples=examples[pattern.id],
                    unresolved=unresolved[pattern.id],
                    validated=tally.occurrences if tally else None,
                    validated_distinct=tally.distinct.count if tally else None,
                    validated_exact=tally.distinct.accuracy == "exact" if tally else True,
                    nodes=[view for view, _ in nodes],
                    node_count=size,
                )
            )
        family_views.append(
            PatternFamilyView(
                id=family.id,
                key=family.key,
                composition=family.composition,
                d=family.d,
                o=family.o,
                share_d=_share(family.d, sizes[0]),
                share_o=_share(family.o, sizes[1]),
                patterns=pattern_views,
                tables=[
                    _table_view(table, sizes, table_counts.get(table.facet))
                    for table in family.tables
                ],
                validated=counted_family.occurrences if counted_family else None,
                new_variant_length=counted_family.new_variants.length if counted_family else 0,
                new_variant_segment=counted_family.new_variants.segment if counted_family else 0,
            )
        )
    outside = entry.outside_patterns()[0]
    return PatternView(
        status="complete",
        entry=entry,
        rows=rows,
        families=family_views,
        node_count=node_count,
        has_validation=counts is not None,
        outside_distinct=outside,
        outside_share=_share(outside, total),
        outside_structures=entry.other.structures,
        examples=examples,
        unresolved=unresolved,
    )


def pattern_entries(derived: Derived | None) -> dict[tuple[str, str], FieldPatterns]:
    """The pattern entry of each field, by dataset and field id."""
    if derived is None or derived.patterns is None:
        return {}
    return {(entry.dataset, entry.field): entry for entry in derived.patterns.fields}


# Characters --------------------------------------------------------------------


def character_entries(derived: Derived | None) -> dict[tuple[str, str], FieldCharacters]:
    """The character map of each field, by dataset and field id."""
    if derived is None or derived.characters is None:
        return {}
    return {(entry.dataset, entry.field): entry for entry in derived.characters.fields}


# How a character that cannot be drawn as itself is shown.
_VISIBLE = {" ": "\u2420", "\t": "\u21e5", "\n": "\u21b5", "\r": "\u240d", "\u00a0": "NBSP"}


def _symbol(char: str) -> str:
    """The character as the map draws it: itself when it can be seen, a mark or
    its code point otherwise."""
    if char in _VISIBLE:
        return _VISIBLE[char]
    if char.isprintable() and not unicodedata.category(char).startswith("M"):
        return char
    return f"U+{ord(char):04X}"


def _ratio(count: int, total: int) -> float:
    return count / total if total else 0.0


def character_view(
    entry: FieldCharacters | None, exact: CharacterProfileResult | None
) -> CharacterMapView:
    """The character map of a column: the exact one of the second pass when there is
    one, otherwise the Scan's (design 9.2b)."""
    if exact is not None:
        return _character_map(exact, "second_pass")
    if entry is None:
        return CharacterMapView(status="missing")
    found = entry.characters
    if isinstance(found, Complete):
        return _character_map(found.value, "scan")
    if isinstance(found, Limited):
        return CharacterMapView(
            status="limited",
            source="scan",
            reason_text=(
                f"More distinct characters or emoji than the {found.limit:,} the map keeps: "
                "it lists none."
            ),
        )
    reason = getattr(found, "reason", found.status)
    return CharacterMapView(
        status="unavailable", reason_text=CHARACTER_REASONS.get(reason, CHARACTER_REASONS["failed"])
    )


def _character_map(
    found: CharacterMap, source: Literal["scan", "second_pass"]
) -> CharacterMapView:
    characters = found.characters
    values = found.values
    return CharacterMapView(
        status="complete",
        source=source,
        basis=found.basis,
        summary=found,
        tiles=[
            CharacterTile(
                symbol=_symbol(item.char),
                codepoint=f"U+{item.codepoint:04X}",
                name=unicodedata.name(item.char, "") or CHARACTER_CATEGORIES.get(
                    unicodedata.category(item.char), ""
                ),
                count=item.occurrence_count,
                share=_ratio(item.occurrence_count, characters),
            )
            for item in found.top
        ],
        scripts=[
            CharacterShare(
                label=item.name.title(),
                count=item.occurrence_count,
                share=_ratio(item.occurrence_count, characters),
            )
            for item in found.scripts
        ],
        categories=[
            CharacterShare(
                label=CHARACTER_CATEGORIES.get(item.name, item.name),
                name=item.name,
                count=item.occurrence_count,
                share=_ratio(item.occurrence_count, characters),
            )
            for item in found.categories
        ],
        case=[
            CharacterShare(label=label, count=count, share=_ratio(count, values))
            for label, count in (
                ("Ends with a capital", found.ends_uppercase),
                ("Ends with a lowercase letter", found.ends_lowercase),
                ("Title case", found.title_case),
            )
        ],
        emoji=[
            CharacterShare(
                label=item.sequence,
                count=item.occurrence_count,
                share=_ratio(item.occurrence_count, found.emoji_sequences),
            )
            for item in found.emoji
        ],
    )


# Rows --------------------------------------------------------------------------


def rows_view(dataset: DatasetResult) -> RowsView:
    """The row sample the base of the report holds for a dataset."""
    return RowsView(sample=dataset.records.sample)
