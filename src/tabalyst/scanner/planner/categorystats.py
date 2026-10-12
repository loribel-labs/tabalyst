# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exploration of the numbers by category on the row sample (design 20.23).

The planner proposes the pairs of a category and a numeric column worth
describing over every row (REL-02, REL-04 to REL-06) by grouping the sample
rows by category and rating each pair with the corrected correlation ratio. It
reads the Scan only, never the source, and bounds its own work: the columns, and
the pairs times the rows grouped (COST-05). A column that is left out, and a
pair that has no score, are counted with their reason in the plan, never
dropped in silence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tabalyst.config import StatsSettings
from tabalyst.scanner.correlation_ratio import GroupMoments, moments_of, ratio
from tabalyst.scanner.features import MISSING, Coder, category_coder
from tabalyst.scanner.models import DatasetResult, FieldResult
from tabalyst.scanner.planner.analyzer import PairProposal
from tabalyst.scanner.planner.crosstabs import (
    COLUMN_BUDGET,
    IDENTIFIER,
    NEAR_UNIQUE,
    NOT_IN_SAMPLE,
    SAME_COLUMN,
    category_state,
    code_rows,
    value_direction,
)
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import ExploredStats, StatsExploration
from tabalyst.scanner.planner.relations import (
    NUMERIC_TYPES,
    TOO_FEW_VALUES,
    column_floats,
    column_state,
)
from tabalyst.scanner.planner.samplerows import cell_text, usable_rows

if TYPE_CHECKING:
    # Imported by the planner when it needs one: the second pass imports the
    # planner, so a module-level import here would be circular.
    from tabalyst.scanner.secondpass.replay import CellReader

# Decimals kept in the plan: enough for a ranking, and the same on any machine.
DECIMALS = 6


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, DECIMALS)


@dataclass(slots=True)
class _Category:
    facts: FieldFacts
    coder: Coder
    codes: list[int] = field(default_factory=list)
    usable: int = 0


@dataclass(slots=True)
class _Number:
    facts: FieldFacts
    floats: list[float | None] = field(default_factory=list)
    usable: int = 0


def explore_pair(
    codes: Sequence[int],
    floats: Sequence[float | None],
    classes: int,
    settings: StatsSettings,
    scope: str,
) -> StatsExploration:
    """What the rows say of one pair (REL-05). The last class, ``other``, is
    counted among the rows and takes no part in the score."""
    grouped: dict[int, list[float]] = {}
    for code, number in zip(codes, floats, strict=True):
        if code != MISSING and number is not None:
            grouped.setdefault(code, []).append(number)
    rows = sum(len(values) for values in grouped.values())
    named: list[GroupMoments] = [
        moments_of(values) for code, values in grouped.items() if code != classes - 1
    ]
    found = ratio(named, settings.explore_min_rows)
    return StatsExploration(
        scope=scope,  # type: ignore[arg-type]
        rows=rows,
        groups=found.groups,
        eta_squared=_rounded(found.eta_squared),
        epsilon_squared=_rounded(found.epsilon_squared),
        score=_rounded(found.score),
        reason=found.reason,
    )


def explore_dataset(
    scan_dataset: DatasetResult,
    facts: Sequence[FieldFacts],
    reader: CellReader,
    settings: StatsSettings,
    lenient: bool,
) -> tuple[ExploredStats | None, list[PairProposal]]:
    """The exploration of one dataset: the block that describes it and the
    pairs to list, the best first. ``None`` when it has no category or no
    number to describe."""
    results = {item.id: item for item in scan_dataset.fields}
    placed = {item.field: number for number, item in enumerate(facts)}
    excluded_categories: dict[str, int] = {}
    excluded_numeric: dict[str, int] = {}

    def leave_out(reason: str, store: dict[str, int]) -> None:
        store[reason] = store.get(reason, 0) + 1

    categories: list[_Category] = []
    numbers: list[_Number] = []
    for item in facts:
        if item.technical_type in NUMERIC_TYPES:
            why = column_state(item)
            if why is None:
                numbers.append(_Number(item))
            else:
                leave_out(why, excluded_numeric)
        reason = category_state(item)
        if reason is None:
            coder, reason = category_coder(
                reader, results[item.field], settings.max_categories, settings.max_distinct
            )
            if coder is not None:
                categories.append(_Category(item, coder))
                continue
        leave_out(reason or "not_a_category", excluded_categories)
    if not categories or not numbers:
        return None, []

    usable, unavailable = usable_rows(scan_dataset, settings.explore_min_rows)
    if usable is None:
        return (
            ExploredStats(
                dataset=scan_dataset.id,
                categories=len(categories),
                numeric=len(numbers),
                excluded_categories=dict(sorted(excluded_categories.items())),
                excluded_numeric=dict(sorted(excluded_numeric.items())),
                unavailable=unavailable,
            ),
            [],
        )
    in_sample = set(usable.sample.fields)

    def present(item: FieldFacts) -> bool:
        return item.field in in_sample and usable.sample.covers([item.field])

    rows = len(usable.rows)
    kept_categories: list[_Category] = []
    for category in categories:
        if not present(category.facts):
            leave_out(NOT_IN_SAMPLE, excluded_categories)
            continue
        category.usable = sum(
            cell_text(row, category.facts.field) is not None for row in usable.rows
        )
        kept_categories.append(category)
    categories = kept_categories
    kept_numbers: list[_Number] = []
    for number in numbers:
        if not present(number.facts):
            leave_out(NOT_IN_SAMPLE, excluded_numeric)
            continue
        number.floats, _ = column_floats(
            usable.rows, number.facts.field, reader, lenient=lenient
        )
        number.usable = sum(value is not None for value in number.floats)
        if number.usable < settings.explore_min_rows:
            leave_out(TOO_FEW_VALUES, excluded_numeric)
            continue
        kept_numbers.append(number)
    numbers = kept_numbers

    def pairs_count() -> int:
        return sum(
            1
            for category in categories
            for number in numbers
            if number.facts.field != category.facts.field
        )

    def fits() -> bool:
        return (
            len(categories) + len(numbers) <= settings.max_columns
            and pairs_count() * rows <= settings.max_work
        )

    # The columns beyond the budget are the least present ones; ties keep the
    # order of the document. The larger side loses its last one first.
    while categories and numbers and not fits():
        side = numbers if len(numbers) >= len(categories) else categories
        ranked = sorted(range(len(side)), key=lambda i: (-side[i].usable, i))
        side.pop(ranked[-1])
        leave_out(COLUMN_BUDGET, excluded_numeric if side is numbers else excluded_categories)

    block = ExploredStats(
        dataset=scan_dataset.id,
        scope=usable.scope,  # type: ignore[arg-type]
        rows=rows,
        categories=len(categories),
        numeric=len(numbers),
        excluded_categories=dict(sorted(excluded_categories.items())),
        excluded_numeric=dict(sorted(excluded_numeric.items())),
    )
    for category in categories:
        category.codes = code_rows(category.coder, usable.rows, category.facts.field)
    category_fields = {category.facts.field for category in categories}
    scored: list[tuple[float, int, int, PairProposal]] = []
    undefined: dict[str, int] = {}
    possible = evaluated = order = 0
    for category in categories:
        for number in numbers:
            if number.facts.field == category.facts.field:
                continue
            if number.facts.field in category_fields and not value_direction(
                category.facts, number.facts, placed
            ):
                continue
            possible += 1
            evaluated += 1
            order += 1
            exploration = explore_pair(
                category.codes,
                number.floats,
                len(category.coder.classes),
                settings,
                usable.scope,
            )
            if exploration.score is None:
                reason = exploration.reason or "too_few_rows"
                undefined[reason] = undefined.get(reason, 0) + 1
                continue
            if exploration.score <= 0.0:
                continue
            proposal = PairProposal(
                category.facts, number.facts, exploration, from_samples=usable.complete
            )
            scored.append((-exploration.score, -exploration.rows, order, proposal))
    scored.sort(key=lambda item: item[:3])
    listed = [item[3] for item in scored[: settings.max_candidates]]
    block = block.model_copy(
        update={
            "possible": possible,
            "evaluated": evaluated,
            "undefined": sum(undefined.values()),
            "undefined_reasons": dict(sorted(undefined.items())),
            "listed": len(listed),
            "work": evaluated * rows,
        }
    )
    return block, listed


def explicit_proposal(
    dataset: DatasetResult,
    category: FieldFacts,
    number: FieldFacts,
    reader: CellReader,
    settings: StatsSettings,
    lenient: bool,
) -> PairProposal:
    """A pair that was asked for: scored when the sample allows it, whatever the
    exploration thought of its columns (REL-06), and not applicable when a column
    cannot play its part."""
    if category.field == number.field:
        return PairProposal(category, number, None, (SAME_COLUMN,))
    results: dict[str, FieldResult] = {item.id: item for item in dataset.fields}
    reason = category_state(category)
    coder: Coder | None = None
    if reason in (None, IDENTIFIER, NEAR_UNIQUE):
        # A request may name an identifier as category: it is asked for.
        coder, reason = category_coder(
            reader, results[category.field], settings.max_categories, settings.max_distinct
        )
    if reason is None:
        if number.technical_type not in NUMERIC_TYPES:
            reason = "not_numeric"
        elif number.withheld:
            reason = "sensitive_exposure"
        elif number.repeated:
            reason = "repeated_path"
        elif number.numeric != "complete":
            reason = "measure_unavailable"
    if reason is not None or coder is None:
        return PairProposal(category, number, None, (reason or "not_a_category",))
    usable, _ = usable_rows(dataset, settings.explore_min_rows)
    if usable is None or not usable.sample.covers([category.field, number.field]):
        return PairProposal(category, number, None)
    exploration = explore_pair(
        code_rows(coder, usable.rows, category.field),
        column_floats(usable.rows, number.field, reader, lenient=lenient)[0],
        len(coder.classes),
        settings,
        usable.scope,
    )
    return PairProposal(category, number, exploration, from_samples=usable.complete)
