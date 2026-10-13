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

from tabalyst.report_labels import (
    AT_LEAST,
    EXACT,
    MEASURE_LABELS,
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
    DiagnosticLocation,
    DiagnosticProfile,
    LimitsView,
    LimitView,
    PatternView,
    QualityGroup,
    QualityItem,
    QualityView,
    RowsView,
)
from tabalyst.scanner.models import (
    CardinalityLimited,
    Complete,
    DatasetResult,
    Derived,
    Diagnostic,
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsFailed,
    FieldPatternsNotApplicable,
    FieldResult,
    Limited,
    NotApplicable,
    Observation,
    Observations,
)
from tabalyst.scanner.quality import ANALYTICAL_STAGES

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
            setting=REASON_SETTINGS.get(limit.reason),
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


def pattern_view(
    field: FieldResult, entry: FieldPatterns | None, derived: Derived | None
) -> PatternView:
    """The patterns of a column with their examples that resolve here. A
    Report keeps the smallest priorities of the sample, so an example of the
    Scan may not be among them; the view counts those it cannot show."""
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
    for candidate in entry.candidates:
        shown = [values[item] for item in candidate.examples if item in values]
        examples[candidate.id] = shown
        unresolved[candidate.id] = len(candidate.examples) - len(shown)
    return PatternView(
        status="complete", entry=entry, examples=examples, unresolved=unresolved
    )


def pattern_entries(derived: Derived | None) -> dict[tuple[str, str], FieldPatterns]:
    """The pattern entry of each field, by dataset and field id."""
    if derived is None or derived.patterns is None:
        return {}
    return {(entry.dataset, entry.field): entry for entry in derived.patterns.fields}


# Rows --------------------------------------------------------------------------


def rows_view(dataset: DatasetResult) -> RowsView:
    """The row sample the base of the report holds for a dataset."""
    return RowsView(sample=dataset.records.sample)
