# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exploration of the pairs of numeric columns on the row sample (design 20.12).

The planner proposes the pairs worth counting over every row (REL-04 to REL-06)
by scoring all the pairs of the eligible columns on the rows the Scan sampled.
It reads the Scan only, never the source, and bounds its own work: the number
of columns, and the pairs times the rows compared (COST-05). A column that is
left out, and a pair that has no coefficient, are counted with their reason in
the plan, never dropped in silence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from itertools import combinations
from typing import TYPE_CHECKING

from tabalyst.config import PearsonSettings
from tabalyst.scanner.models import DatasetResult, SampleRow
from tabalyst.scanner.pearson import (
    INSUFFICIENT_PAIRS,
    CoMoments,
    coefficient,
    comoments,
    interval,
    score,
    to_float,
)
from tabalyst.scanner.planner.analyzer import PairProposal
from tabalyst.scanner.planner.facts import FieldFacts
from tabalyst.scanner.planner.identifiers import identifier_like, uniqueness
from tabalyst.scanner.planner.models import Exploration, ExploredDataset
from tabalyst.scanner.planner.samplerows import cell_text, usable_rows
from tabalyst.scanner.rankcorr import average_ranks, rank_interval, sample_coefficient

if TYPE_CHECKING:
    # Imported by the planner when it needs one: the second pass imports the
    # planner, so a module-level import here would be circular.
    from tabalyst.scanner.secondpass.replay import CellReader

NUMERIC_TYPES = ("integer", "number")
# An integer column almost all distinct is a key whatever its name.
KEY_SHARE = 0.99
# Decimals kept in the plan: enough for a ranking, and the same on any machine.
DECIMALS = 6

# Reasons a column is left out of the exploration (counted in the plan).
NOT_NUMERIC = "not_numeric"
CONSTANT = "constant"
SENSITIVE = "sensitive_exposure"
REPEATED = "repeated_path"
IDENTIFIER = "identifier_like"
NOT_IN_SAMPLE = "not_in_sample"
TOO_FEW_VALUES = "too_few_values"
COLUMN_BUDGET = "column_budget"
MEASURE_UNAVAILABLE = "measure_unavailable"


@dataclass(slots=True)
class _Column:
    facts: FieldFacts
    floats: list[float | None] = field(default_factory=list)
    usable: int = 0
    # Average ranks, for a column that has a number in every sampled row: the
    # pairs of such columns share them instead of sorting the rows again.
    ranks: list[float] | None = None


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, DECIMALS)


def column_floats(
    rows: Sequence[SampleRow], field_id: str, reader: CellReader, *, lenient: bool
) -> tuple[list[float | None], int]:
    """The float64 of the number each row holds in a field, or ``None``, and
    how many numbers the cells hold (those beyond float64 included, as the Scan
    counts them). A number is read like the first pass reads it; ``lenient``
    (JSON, whose native numbers the sample writes as text) also accepts what a
    decimal reads."""
    texts = [cell_text(row, field_id) for row in rows]
    counts = Counter(text for text in texts if text is not None)
    distinct = list(counts)
    numbers: dict[str, float | None] = {}
    found = 0
    for text, cell in zip(distinct, reader.cells(distinct, numbers=True), strict=True):
        value = cell.number
        if value is None and lenient and cell.length >= 0:
            try:
                parsed: object = Decimal(cell.text)
            except InvalidOperation:
                parsed = None
            value = parsed  # type: ignore[assignment]
        if value is not None:
            found += counts[text]
        numbers[text] = to_float(value)
    return [None if text is None else numbers[text] for text in texts], found


def explore_pair(
    first: Sequence[float | None],
    second: Sequence[float | None],
    settings: PearsonSettings,
    scope: str,
    ranks: tuple[Sequence[float], Sequence[float]] | None = None,
) -> Exploration:
    """What the rows say of one pair (REL-05). ``ranks`` are the average ranks of
    two columns without a missing value (see ``_Column.ranks``)."""
    moments = comoments(first, second)
    return _explored(moments, first, second, settings, scope, ranks)


def effective_score(exploration: Exploration) -> float | None:
    """What rates a pair: the larger of the scores of the linear and the rank
    coefficient, ``None`` when neither is defined."""
    scores = [s for s in (exploration.score, exploration.rank_score) if s is not None]
    return max(scores) if scores else None


def _explored(
    moments: CoMoments,
    first: Sequence[float | None],
    second: Sequence[float | None],
    settings: PearsonSettings,
    scope: str,
    ranks: tuple[Sequence[float], Sequence[float]] | None = None,
) -> Exploration:
    if moments.n < settings.explore_min_pairs:
        return Exploration(scope=scope, pairs=moments.n, reason=INSUFFICIENT_PAIRS)  # type: ignore[arg-type]
    r, reason = coefficient(moments, settings.explore_min_pairs)
    if r is None:
        # A column that does not vary has no rank either: the reason stays.
        return Exploration(scope=scope, pairs=moments.n, reason=reason)  # type: ignore[arg-type]
    rank: dict[str, float | None] = {}
    if settings.rank_bins:
        n, rho = sample_coefficient(first, second, settings.explore_min_pairs, ranks)
        found = None if rho is None else rank_interval(rho, n)
        if rho is not None and found is not None:
            rank = {
                "rank_coefficient": _rounded(rho),
                "rank_lower": _rounded(found[0]),
                "rank_upper": _rounded(found[1]),
                "rank_score": _rounded(score(found)),
            }
    bounds = interval(r, moments.n)
    assert bounds is not None
    return Exploration(
        scope=scope,  # type: ignore[arg-type]
        pairs=moments.n,
        coefficient=_rounded(r),
        lower=_rounded(bounds[0]),
        upper=_rounded(bounds[1]),
        score=_rounded(score(bounds)),
        **rank,  # type: ignore[arg-type]
    )


def column_state(facts: FieldFacts) -> str | None:
    """Why a field cannot be a column of an exploration, from the Scan alone."""
    if facts.technical_type not in NUMERIC_TYPES:
        return NOT_NUMERIC
    if facts.withheld:
        return SENSITIVE
    if facts.numeric != "complete":
        return MEASURE_UNAVAILABLE
    if facts.repeated:
        return REPEATED
    if facts.numeric_min == facts.numeric_max:
        return CONSTANT
    share = uniqueness(facts)
    if identifier_like(facts) or (
        facts.technical_type == "integer" and share is not None and share >= KEY_SHARE
    ):
        return IDENTIFIER
    return None


def _columns_fit(columns: int, rows: int, settings: PearsonSettings) -> bool:
    return columns <= settings.max_columns and columns * (columns - 1) // 2 * rows <= settings.max_work


def explore_dataset(
    dataset: DatasetResult,
    facts: Sequence[FieldFacts],
    reader: CellReader,
    settings: PearsonSettings,
    lenient: bool,
) -> tuple[ExploredDataset | None, list[PairProposal]]:
    """The exploration of one dataset: the block that describes it and the pairs
    to list, the best first. ``None`` when it has fewer than two numeric
    columns."""
    numeric = [f for f in facts if f.technical_type in NUMERIC_TYPES]
    if len(numeric) < 2:
        return None, []
    usable, unavailable = usable_rows(dataset, settings.explore_min_pairs)
    if usable is None:
        return ExploredDataset(dataset=dataset.id, numeric=len(numeric), unavailable=unavailable), []

    excluded: dict[str, int] = {}

    def leave_out(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    columns: list[_Column] = []
    fields_in_sample = set(usable.sample.fields)
    for item in numeric:
        reason = column_state(item)
        if reason is None and (
            item.field not in fields_in_sample or not usable.sample.covers([item.field])
        ):
            reason = NOT_IN_SAMPLE
        if reason is not None:
            leave_out(reason)
            continue
        column = _Column(item)
        column.floats, _ = column_floats(usable.rows, item.field, reader, lenient=lenient)
        column.usable = sum(value is not None for value in column.floats)
        if column.usable < settings.explore_min_pairs:
            leave_out(TOO_FEW_VALUES)
            continue
        if settings.rank_bins and column.usable == len(column.floats):
            column.ranks = average_ranks(column.floats)  # type: ignore[arg-type]
        columns.append(column)

    # Columns beyond the budget are the least present; ties keep document order.
    rows = len(usable.rows)
    keep = len(columns)
    while keep > 2 and not _columns_fit(keep, rows, settings):
        keep -= 1
    if len(columns) > keep:
        ranked = sorted(range(len(columns)), key=lambda i: (-columns[i].usable, i))
        dropped = set(ranked[keep:])
        for _ in dropped:
            leave_out(COLUMN_BUDGET)
        columns = [c for i, c in enumerate(columns) if i not in dropped]
    block = ExploredDataset(
        dataset=dataset.id,
        scope=usable.scope,  # type: ignore[arg-type]
        rows=rows,
        numeric=len(numeric),
        columns=len(columns),
        excluded=dict(sorted(excluded.items())),
    )
    if len(columns) < 2:
        return block, []

    scored: list[tuple[float, int, int, PairProposal]] = []
    undefined: dict[str, int] = {}
    evaluated = 0
    for (i, a), (j, b) in combinations(enumerate(columns), 2):
        evaluated += 1
        shared = (a.ranks, b.ranks) if a.ranks is not None and b.ranks is not None else None
        exploration = explore_pair(a.floats, b.floats, settings, usable.scope, shared)
        rated = effective_score(exploration)
        if rated is None:
            reason = exploration.reason or INSUFFICIENT_PAIRS
            undefined[reason] = undefined.get(reason, 0) + 1
            continue
        if rated <= 0.0:
            continue
        proposal = PairProposal(a.facts, b.facts, exploration, from_samples=usable.complete)
        scored.append((-rated, -exploration.pairs, i * len(columns) + j, proposal))
    scored.sort(key=lambda item: item[:3])
    listed = [item[3] for item in scored[: settings.max_candidates]]
    block = block.model_copy(
        update={
            "possible": len(columns) * (len(columns) - 1) // 2,
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
    first: FieldFacts,
    second: FieldFacts,
    reader: CellReader,
    settings: PearsonSettings,
    lenient: bool,
) -> PairProposal:
    """A pair that was asked for: scored when the sample allows it, whatever the
    exploration thought of its columns (REL-06), and not applicable only when a
    column is not a number at all."""
    for item in (first, second):
        if item.technical_type not in NUMERIC_TYPES:
            return PairProposal(first, second, None, (NOT_NUMERIC,))
        if item.withheld:
            return PairProposal(first, second, None, (SENSITIVE,))
        if item.repeated:
            return PairProposal(first, second, None, (REPEATED,))
        if item.numeric != "complete":
            return PairProposal(first, second, None, (MEASURE_UNAVAILABLE,))
    usable, _ = usable_rows(dataset, settings.explore_min_pairs)
    if usable is None or not usable.sample.covers([first.field, second.field]):
        return PairProposal(first, second, None)
    exploration = explore_pair(
        column_floats(usable.rows, first.field, reader, lenient=lenient)[0],
        column_floats(usable.rows, second.field, reader, lenient=lenient)[0],
        settings,
        usable.scope,
    )
    return PairProposal(first, second, exploration, from_samples=usable.complete)
