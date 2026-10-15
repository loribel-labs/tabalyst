# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exploration of the order of two dates in the row sample (design 20.38).

The planner proposes the pairs of date columns worth counting over every row, those
where one date is on or before the other in nearly every row, by comparing all the
pairs of the eligible columns on the rows the Scan sampled. It reads the Scan only,
never the source, and bounds its own work like the exploration of the pairs of
numbers (20.12): a column that is left out is counted with its reason in the plan,
never dropped in silence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING

from tabalyst.config import DateOrderSettings
from tabalyst.scanner.detectors.temporal import kind_of
from tabalyst.scanner.models import DatasetResult, FieldResult, SampleRow
from tabalyst.scanner.planner.analyzer import PairProposal
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.models import Exploration, ExploredOrders
from tabalyst.scanner.planner.samplerows import cell_text, usable_rows

if TYPE_CHECKING:
    # Imported by the planner when it needs one: the second pass imports the
    # planner, so a module-level import here would be circular.
    from tabalyst.scanner.secondpass.replay import CellReader

# The kinds of date that can be put in order; a time of day has no date to compare.
ORDERED_KINDS = ("date", "datetime_naive", "datetime_aware")
# Decimals kept in the plan: the same on any machine.
DECIMALS = 6

# Reasons a column is left out of the exploration (counted in the plan).
NOT_A_DATE = "not_a_date"
SENSITIVE = "sensitive_exposure"
REPEATED = "repeated_path"
MIXED_KINDS = "mixed_kinds"
NOT_IN_SAMPLE = "not_in_sample"
TOO_FEW_VALUES = "too_few_values"
COLUMN_BUDGET = "column_budget"
TOO_FEW_ROWS = "too_few_rows"


@dataclass(slots=True)
class _Column:
    facts: FieldFacts
    # Per sampled row: the date the cell reads as, or ``None``.
    dates: list[object | None] = field(default_factory=list)
    usable: int = 0


def column_state(facts: FieldFacts) -> str | None:
    """Why a field cannot be a column of the exploration, from the Scan alone."""
    if facts.technical_type != "date" or facts.temporal is None:
        return NOT_A_DATE
    if facts.withheld:
        return SENSITIVE
    if facts.repeated:
        return REPEATED
    kinds = facts.temporal.kinds
    if len(kinds) != 1 or kinds[0] not in ORDERED_KINDS:
        return MIXED_KINDS
    return None


def column_dates(
    rows: Sequence[SampleRow], field_result: FieldResult, facts: FieldFacts, reader: CellReader
) -> list[object | None]:
    """The date each sampled row holds in a field, read as the second pass reads
    it: the ambiguous dates in the order the evidence of the Scan gives the
    column. ``None`` for a row without a date, or whose date stays ambiguous."""
    # Imported here: the second pass imports the planner (see TYPE_CHECKING above).
    from tabalyst.scanner.secondpass.orders import DateSide

    texts = [cell_text(row, field_result.id) for row in rows]
    order = facts.temporal.inferred() if facts.temporal is not None else None
    readings = DateSide(reader, order).read(["" if text is None else text for text in texts])
    return [
        None if text is None or reading.reason is not None else reading.value
        for text, reading in zip(texts, readings, strict=True)
    ]


def compare(
    first: Sequence[object | None], second: Sequence[object | None]
) -> tuple[int, int, int]:
    """Over the rows where both columns have a date of the same kind: how many
    there are, how many have the first on or before the second, and how many the
    second on or before the first."""
    rows = before = after = 0
    for a, b in zip(first, second, strict=True):
        if a is None or b is None or kind_of(a) != kind_of(b):
            continue
        rows += 1
        before += a <= b  # type: ignore[operator]
        after += a >= b  # type: ignore[operator]
    return rows, before, after


def explore_pair(
    first: Sequence[object | None],
    second: Sequence[object | None],
    settings: DateOrderSettings,
    scope: str,
) -> tuple[Exploration, bool, bool]:
    """What the rows say of one pair: its exploration, whether the first column is
    the earlier one, and whether both orders hold (the same dates in both columns,
    which leaves nothing to follow). The ``score`` is the share of the rows where
    the earlier column is on or before the later one; it is defined only when
    enough rows have both dates."""
    rows, before, after = compare(first, second)
    if rows < settings.explore_min_pairs:
        return Exploration(scope=scope, pairs=rows, reason=TOO_FEW_ROWS), True, False  # type: ignore[arg-type]
    forward = before >= after
    ordered = before if forward else after
    both = min(before, after) >= settings.min_share * rows
    exploration = Exploration(
        scope=scope,  # type: ignore[arg-type]
        pairs=rows,
        score=round(ordered / rows, DECIMALS),
    )
    return exploration, forward, both


def holds(exploration: Exploration, settings: DateOrderSettings, both: bool) -> bool:
    """Whether a pair is worth counting: ordered in the share of rows the settings
    ask for, and not the same dates in both columns."""
    return exploration.score is not None and exploration.score >= settings.min_share and not both


def explore_dataset(
    dataset: DatasetResult,
    facts: Sequence[FieldFacts],
    reader: CellReader,
    settings: DateOrderSettings,
) -> tuple[ExploredOrders | None, list[PairProposal]]:
    """The exploration of one dataset: the block that describes it and the pairs
    to list, the best first. ``None`` when it has fewer than two date columns."""
    dated = [f for f in facts if f.technical_type == "date"]
    if len(dated) < 2:
        return None, []
    usable, unavailable = usable_rows(dataset, settings.explore_min_pairs)
    if usable is None:
        return ExploredOrders(dataset=dataset.id, dates=len(dated), unavailable=unavailable), []

    excluded: dict[str, int] = {}

    def leave_out(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    columns: list[_Column] = []
    fields_in_sample = set(usable.sample.fields)
    results = {item.id: item for item in dataset.fields}
    for item in dated:
        reason = column_state(item)
        if reason is None and (
            item.field not in fields_in_sample or not usable.sample.covers([item.field])
        ):
            reason = NOT_IN_SAMPLE
        if reason is not None:
            leave_out(reason)
            continue
        column = _Column(item)
        column.dates = column_dates(usable.rows, results[item.field], item, reader)
        column.usable = sum(value is not None for value in column.dates)
        if column.usable < settings.explore_min_pairs:
            leave_out(TOO_FEW_VALUES)
            continue
        columns.append(column)

    rows = len(usable.rows)
    keep = len(columns)
    while keep > 2 and not (
        keep <= settings.max_columns and keep * (keep - 1) // 2 * rows <= settings.max_work
    ):
        keep -= 1
    if len(columns) > keep:
        ranked = sorted(range(len(columns)), key=lambda i: (-columns[i].usable, i))
        dropped = set(ranked[keep:])
        for _ in dropped:
            leave_out(COLUMN_BUDGET)
        columns = [c for i, c in enumerate(columns) if i not in dropped]
    block = ExploredOrders(
        dataset=dataset.id,
        scope=usable.scope,  # type: ignore[arg-type]
        rows=rows,
        dates=len(dated),
        columns=len(columns),
        excluded=dict(sorted(excluded.items())),
    )
    if len(columns) < 2:
        return block, []

    scored: list[tuple[float, int, int, PairProposal]] = []
    undefined = evaluated = 0
    for (i, a), (j, b) in combinations(enumerate(columns), 2):
        evaluated += 1
        exploration, forward, both = explore_pair(a.dates, b.dates, settings, usable.scope)
        if exploration.score is None:
            undefined += 1
            continue
        if not holds(exploration, settings, both):
            continue
        first, second = (a, b) if forward else (b, a)
        proposal = PairProposal(
            first.facts, second.facts, exploration, from_samples=usable.complete
        )
        scored.append((-exploration.score, -exploration.pairs, i * len(columns) + j, proposal))
    scored.sort(key=lambda item: item[:3])
    listed = [item[3] for item in scored[: settings.max_candidates]]
    block = block.model_copy(
        update={
            "possible": len(columns) * (len(columns) - 1) // 2,
            "evaluated": evaluated,
            "undefined": undefined,
            "listed": len(listed),
            "work": evaluated * rows,
        }
    )
    return block, listed


def explicit_proposal(
    dataset: DatasetResult,
    first: FieldFacts,
    second: FieldFacts,
    reader: CellReader,
    settings: DateOrderSettings,
) -> PairProposal:
    """A pair that was asked for, in the order it was named (the first column is
    the one expected to be on or before the other): scored when the sample allows
    it, whatever the exploration thought of it, and not applicable only when a
    column cannot be put in order at all."""
    for item in (first, second):
        reason = column_state(item)
        if reason is not None:
            return PairProposal(first, second, None, (reason,))
    usable, _ = usable_rows(dataset, settings.explore_min_pairs)
    if usable is None or not usable.sample.covers([first.field, second.field]):
        return PairProposal(first, second, None)
    results = {item.id: item for item in dataset.fields}
    dates = [
        column_dates(usable.rows, results[item.field], item, reader) for item in (first, second)
    ]
    rows, before, _ = compare(dates[0], dates[1])
    exploration = (
        Exploration(scope=usable.scope, pairs=rows, score=round(before / rows, DECIMALS))  # type: ignore[arg-type]
        if rows >= settings.explore_min_pairs
        else Exploration(scope=usable.scope, pairs=rows, reason=TOO_FEW_ROWS)  # type: ignore[arg-type]
    )
    return PairProposal(first, second, exploration, from_samples=usable.complete)
