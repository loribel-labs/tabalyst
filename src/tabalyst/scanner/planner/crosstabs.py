# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exploration of the tables of a category against a feature on the row sample
(design 20.13).

The planner proposes the tables worth counting over every row (REL-02, REL-04 to
REL-06, REL-11) by coding the sample rows of the eligible columns and scoring
each table with the bias-corrected Cramér's V. It reads the Scan only, never the
source, and bounds its own work: the columns, and the tables times the rows
coded (COST-05). A column that is left out, and a table that has no score, are
counted with their reason in the plan, never dropped in silence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tabalyst.config import CrosstabSettings
from tabalyst.scanner.crosstab import Association, association, purity_forward
from tabalyst.scanner.features import (
    FEATURES,
    MISSING,
    Coder,
    category_coder,
    feature_coder,
)
from tabalyst.scanner.models import (
    DatasetResult,
    FieldPatternsComplete,
    FieldResult,
    ScanResult,
)
from tabalyst.scanner.planner.analyzer import PairProposal
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.identifiers import identifier_like, uniqueness
from tabalyst.scanner.planner.models import ExploredTables, TableExploration
from tabalyst.scanner.planner.samplerows import cell_text, usable_rows

if TYPE_CHECKING:
    # Imported by the planner when it needs one: the second pass imports the
    # planner, so a module-level import here would be circular.
    from tabalyst.scanner.secondpass.replay import CellReader

# Decimals kept in the plan: enough for a ranking, and the same on any machine.
DECIMALS = 6
# A category repeats: more than half of the values distinct is not one.
MAX_UNIQUE_SHARE = 0.5
# Technical types whose values a feature reads.
FEATURE_TYPES = ("text", "mixed", "integer")

# Reasons a column is left out of the exploration (counted in the plan).
SENSITIVE = "sensitive_exposure"
REPEATED = "repeated_path"
IDENTIFIER = "identifier_like"
NOT_IN_SAMPLE = "not_in_sample"
NOT_TEXT = "not_text"
COLUMN_BUDGET = "column_budget"
NO_VALUES = "no_values"
NEAR_UNIQUE = "near_unique"
SAME_COLUMN = "same_column"


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, DECIMALS)


@dataclass(slots=True)
class _Column:
    """A column of the exploration: its facts, its field and the codes of the
    sample rows, one list per coder."""

    facts: FieldFacts
    result: FieldResult
    usable: int = 0
    coder: Coder | None = None
    coders: dict[str, Coder] = field(default_factory=dict)
    codes: dict[str, list[int]] = field(default_factory=dict)


def code_rows(coder: Coder, rows: Sequence[object], field_id: str) -> list[int]:
    """The code of the cell each sample row holds in a field: the cells are read
    once per distinct text. A row without a single value is ``MISSING``."""
    texts = [cell_text(row, field_id) for row in rows]  # type: ignore[arg-type]
    distinct = list(dict.fromkeys(text for text in texts if text is not None))
    codes = dict(zip(distinct, coder.code_texts(distinct), strict=True))
    return [MISSING if text is None else codes[text] for text in texts]


def table_of(
    first: Sequence[int], second: Sequence[int], rows: int, columns: int
) -> tuple[list[list[int]], int]:
    """The table of the rows that have a class in both axes, and how many."""
    counts = Counter(zip(first, second, strict=True))
    table = [[0] * columns for _ in range(rows)]
    classified = 0
    for (a, b), count in counts.items():
        if a >= 0 and b >= 0:
            table[a][b] = count
            classified += count
    return table, classified


def explore_table(
    first: Sequence[int],
    second: Sequence[int],
    rows: int,
    columns: int,
    settings: CrosstabSettings,
    scope: str,
) -> TableExploration:
    """What the rows say of one table (REL-05)."""
    table, classified = table_of(first, second, rows, columns)
    found: Association = association(table, settings.explore_min_rows)
    purity = purity_forward(table).value
    if found.corrected is None:
        return TableExploration(
            scope=scope,  # type: ignore[arg-type]
            rows=classified,
            categories=found.effective_rows,
            classes=found.effective_columns,
            purity=_rounded(purity),
            reason=found.reason,
        )
    return TableExploration(
        scope=scope,  # type: ignore[arg-type]
        rows=classified,
        categories=found.effective_rows,
        classes=found.effective_columns,
        purity=_rounded(purity),
        cramers_v=_rounded(found.cramers_v),
        score=_rounded(found.corrected),
        stable=found.stable,
    )


def _category_state(facts: FieldFacts) -> str | None:
    """Why a field cannot be a category, from the Scan alone."""
    if facts.values == 0:
        return NO_VALUES
    if facts.withheld:
        return SENSITIVE
    if facts.repeated:
        return REPEATED
    if identifier_like(facts):
        return IDENTIFIER
    share = uniqueness(facts)
    if share is not None and share > MAX_UNIQUE_SHARE:
        return NEAR_UNIQUE
    return None


def _feature_state(facts: FieldFacts) -> str | None:
    if facts.values == 0:
        return NO_VALUES
    if facts.withheld:
        return SENSITIVE
    if facts.repeated:
        return REPEATED
    if facts.technical_type not in FEATURE_TYPES:
        return NOT_TEXT
    return None


def _patterns(scan: ScanResult) -> dict[tuple[str, str], FieldPatternsComplete]:
    if scan.derived is None or scan.derived.patterns is None:
        return {}
    return {
        (entry.dataset, entry.field): entry
        for entry in scan.derived.patterns.fields
        if isinstance(entry, FieldPatternsComplete)
    }


def feature_for(
    reader: CellReader,
    feature: str,
    field_result: FieldResult,
    entry: FieldPatternsComplete | None,
    settings: CrosstabSettings,
    max_value_length: int,
) -> tuple[Coder | None, str | None]:
    """The coder of a feature of a column, or why the column does not offer it."""
    return feature_coder(
        reader,
        feature,
        field_result,
        entry,
        max_classes=settings.max_classes,
        prefix_length=settings.prefix_length,
        max_value_length=max_value_length,
    )


def explore_dataset(
    scan: ScanResult,
    dataset: DatasetResult,
    facts: Sequence[FieldFacts],
    reader: CellReader,
    settings: CrosstabSettings,
) -> tuple[ExploredTables | None, list[PairProposal]]:
    """The exploration of one dataset: the block that describes it and the tables
    to list, the best first. ``None`` when no column can be a category."""
    results = {item.id: item for item in dataset.fields}
    patterns = _patterns(scan)
    max_value_length = scan.config.pattern_inference.max_value_length

    excluded_categories: dict[str, int] = {}
    categories: list[_Column] = []
    for item in facts:
        reason = _category_state(item)
        coder: Coder | None = None
        if reason is None:
            coder, reason = category_coder(
                reader, results[item.field], settings.max_categories, settings.max_distinct
            )
        if reason is not None:
            excluded_categories[reason] = excluded_categories.get(reason, 0) + 1
            continue
        column = _Column(item, results[item.field], coder=coder)
        categories.append(column)
    if not categories:
        return None, []

    usable, unavailable = usable_rows(dataset, settings.explore_min_rows)
    if usable is None:
        return (
            ExploredTables(
                dataset=dataset.id,
                categories=len(categories),
                excluded_categories=dict(sorted(excluded_categories.items())),
                unavailable=unavailable,
            ),
            [],
        )

    excluded_features: dict[str, int] = {}

    def leave_out(reason: str, store: dict[str, int]) -> None:
        store[reason] = store.get(reason, 0) + 1

    in_sample = set(usable.sample.fields)

    def present(item: FieldFacts) -> bool:
        return item.field in in_sample and usable.sample.covers([item.field])

    def values_in_sample(item: FieldFacts) -> int:
        return sum(cell_text(row, item.field) is not None for row in usable.rows)

    kept_categories: list[_Column] = []
    for column in categories:
        if not present(column.facts):
            leave_out(NOT_IN_SAMPLE, excluded_categories)
            continue
        column.usable = values_in_sample(column.facts)
        kept_categories.append(column)
    categories = kept_categories

    columns: list[_Column] = []
    for item in facts:
        reason = _feature_state(item)
        if reason is not None:
            leave_out(reason, excluded_features)
            continue
        if not present(item):
            leave_out(NOT_IN_SAMPLE, excluded_features)
            continue
        column = _Column(item, results[item.field])
        for feature in FEATURES:
            coder, why = feature_for(
                reader,
                feature,
                column.result,
                patterns.get((dataset.id, item.field)),
                settings,
                max_value_length,
            )
            if coder is None:
                leave_out(why or feature, excluded_features)
                continue
            column.coders[feature] = coder
        if not column.coders:
            continue
        column.usable = values_in_sample(item)
        columns.append(column)

    rows = len(usable.rows)

    def tables(cats: list[_Column], cols: list[_Column]) -> int:
        total = 0
        for cat in cats:
            for col in cols:
                if col.facts.field != cat.facts.field:
                    total += len(col.coders)
        return total

    # The columns beyond the budget are the least present ones; ties keep the
    # order of the document. The larger side loses its last one first. Only the
    # columns that stay are coded.
    def fits() -> bool:
        return (
            len(categories) + len(columns) <= settings.max_columns
            and tables(categories, columns) * rows <= settings.max_work
        )

    def drop(side: list[_Column]) -> None:
        ranked = sorted(range(len(side)), key=lambda i: (-side[i].usable, i))
        side.pop(ranked[-1])
        leave_out(COLUMN_BUDGET, excluded_features if side is columns else excluded_categories)

    while categories and columns and not fits():
        drop(columns if len(columns) >= len(categories) else categories)

    for column in categories:
        assert column.coder is not None
        column.codes["category"] = code_rows(column.coder, usable.rows, column.facts.field)
    for column in columns:
        for feature, coder in column.coders.items():
            column.codes[feature] = code_rows(coder, usable.rows, column.facts.field)

    block = ExploredTables(
        dataset=dataset.id,
        scope=usable.scope,  # type: ignore[arg-type]
        rows=rows,
        categories=len(categories),
        columns=len(columns),
        excluded_categories=dict(sorted(excluded_categories.items())),
        excluded_features=dict(sorted(excluded_features.items())),
    )
    scored: list[tuple[int, float, int, int, PairProposal]] = []
    undefined: dict[str, int] = {}
    evaluated = 0
    possible = 0
    widest = 0
    order = 0
    for cat in categories:
        assert cat.coder is not None
        for col in columns:
            if col.facts.field == cat.facts.field:
                continue
            group: list[tuple[int, float, int, int, PairProposal]] = []
            for feature, coder in col.coders.items():
                possible += 1
                evaluated += 1
                exploration = explore_table(
                    cat.codes["category"],
                    col.codes[feature],
                    len(cat.coder.classes),
                    len(coder.classes),
                    settings,
                    usable.scope,
                )
                widest = max(widest, len(cat.coder.classes) * len(coder.classes))
                order += 1
                if exploration.score is None:
                    reason = exploration.reason or "too_few_rows"
                    undefined[reason] = undefined.get(reason, 0) + 1
                    continue
                if exploration.score <= 0.0:
                    continue
                proposal = PairProposal(
                    cat.facts,
                    col.facts,
                    exploration,
                    from_samples=usable.complete,
                    feature=feature,
                )
                # A table on counts too low to trust ranks after the stable ones
                # (never out: it stays listed with its caution, REL-11).
                unstable = int(exploration.stable is False)
                group.append((unstable, -exploration.score, -exploration.rows, order, proposal))
            group.sort(key=lambda item: item[:4])
            for number, (unstable, negative, rows_key, position, proposal) in enumerate(group):
                if number:
                    proposal = PairProposal(
                        proposal.first,
                        proposal.second,
                        proposal.exploration,
                        from_samples=proposal.from_samples,
                        feature=proposal.feature,
                        redundant=True,
                    )
                scored.append((unstable, negative, rows_key, position, proposal))
    scored.sort(key=lambda item: item[:4])
    listed = [item[4] for item in scored[: settings.max_candidates]]
    block = block.model_copy(
        update={
            "possible": possible,
            "evaluated": evaluated,
            "undefined": sum(undefined.values()),
            "undefined_reasons": dict(sorted(undefined.items())),
            "listed": len(listed),
            "work": evaluated * rows,
            "cells": widest,
        }
    )
    return block, listed


def explicit_proposals(
    scan: ScanResult,
    dataset: DatasetResult,
    category: FieldFacts,
    column: FieldFacts,
    features: Sequence[str],
    reader: CellReader,
    settings: CrosstabSettings,
) -> list[PairProposal]:
    """The tables of a pair of columns that was asked for, scored when the sample
    allows it whatever the exploration thought of them (REL-06), and not
    applicable when a column cannot play its part."""
    results = {item.id: item for item in dataset.fields}
    patterns = _patterns(scan)
    max_value_length = scan.config.pattern_inference.max_value_length
    proposals: list[PairProposal] = []
    if category.field == column.field:
        return [PairProposal(category, column, None, (SAME_COLUMN,), feature=f) for f in features]
    reason = _category_state(category)
    coder: Coder | None = None
    if reason in (None, IDENTIFIER, NEAR_UNIQUE):
        # A request may name an identifier as category: it is asked for.
        coder, reason = category_coder(
            reader, results[category.field], settings.max_categories, settings.max_distinct
        )
    column_reason = _feature_state(column)
    usable, _ = usable_rows(dataset, settings.explore_min_rows)
    for feature in features:
        why = reason or column_reason
        feature_side: Coder | None = None
        if why is None:
            feature_side, why = feature_for(
                reader,
                feature,
                results[column.field],
                patterns.get((dataset.id, column.field)),
                settings,
                max_value_length,
            )
        if why is not None or coder is None or feature_side is None:
            proposals.append(PairProposal(category, column, None, (why or "not_a_category",), feature=feature))
            continue
        exploration = None
        from_samples = False
        if usable is not None and usable.sample.covers([category.field, column.field]):
            first = code_rows(coder, usable.rows, category.field)
            second = code_rows(feature_side, usable.rows, column.field)
            exploration = explore_table(
                first,
                second,
                len(coder.classes),
                len(feature_side.classes),
                settings,
                usable.scope,
            )
            from_samples = usable.complete
        proposals.append(
            PairProposal(
                category, column, exploration, from_samples=from_samples, feature=feature
            )
        )
    return proposals
