# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Bounded selection of the rows of a smart sample (design 20.16, SMART-05 to SMART-11).

While the source is read, a few candidate rows per target and a bottom-k reserve
of ordinary rows are held, whole, in a pool shared by the targets a row covers.
At the end a greedy cover over that pool chooses the rows: the mandatory targets
first, then the weight not yet covered. It is a heuristic on a bounded pool and
promises no optimum (SMART-07).
"""

from __future__ import annotations

import heapq
from bisect import insort
from collections.abc import Sequence
from dataclasses import dataclass

from tabalyst.scanner.smart.evaluate import Cover

# The share of the byte budget optional targets may fill: the rest is kept for
# mandatory targets and the reserve, which must not be starved by lighter ones.
OPTIONAL_SHARE = 0.8

MISS_SIZE = "size"
MISS_BUDGET = "budget"
MISS_NOT_OBSERVED = "not_observed"


@dataclass(slots=True)
class _Held:
    """A row kept in the pool, once, with the number of roles that hold it."""

    record: int
    row: list[str]
    cost: int
    cover: Cover
    priority: int
    refs: int = 0
    reserve: bool = False


@dataclass(slots=True)
class TargetOutcome:
    """What happened to one target of the plan.

    ``observed`` is the number of rows that cover it in the whole source,
    ``candidates`` the rows held for it at the end of the reading. ``miss`` says
    why a target is not covered: it never was seen, the budget refused its rows,
    or the sample is too small for it.
    """

    observed: int = 0
    candidates: int = 0
    refused: int = 0
    covered: bool = False
    miss: str | None = None


@dataclass(slots=True)
class SelectionOutcome:
    """The rows chosen, in source order, and what the pool and the cover did."""

    rows: list[tuple[int, list[str]]]
    targets: list[TargetOutcome]
    cover_rows: int
    reserve_rows: int
    shortfall: int
    candidate_rows: int
    peak_bytes: int
    refused_rows: int
    mandatory_covered: int = 0
    mandatory_total: int = 0


def row_cost(row: Sequence[str]) -> int:
    """The size of a row as source text, in characters: the cells and a separator
    for each, close to the bytes the pool stands for."""
    return sum(map(len, row)) + len(row)


class SelectionPool:
    """The candidates of a smart sample, fed row by row.

    ``weights`` and ``mandatory`` are per target, by position in the plan;
    targets nothing can test have no cover and cost nothing. ``size`` is the
    sample size and ``reserve`` the rows of it that are ordinary rows. At most
    ``per_target`` rows are held for a target, ``budget`` characters in all.
    """

    def __init__(
        self,
        weights: Sequence[float],
        mandatory: Sequence[bool],
        *,
        size: int,
        reserve: int,
        per_target: int,
        budget: int,
    ) -> None:
        self.weights = weights
        self.mandatory = mandatory
        self.size = size
        self.reserve = reserve
        self.per_target = per_target
        self.budget = budget
        count = len(weights)
        self.outcomes = [TargetOutcome() for _ in range(count)]
        # Rows that cover each target, counted flat (the hot path of the reading),
        # and the key a row must beat to enter a full list of candidates.
        self._observed = [0] * count
        self._worst: list[tuple[int, int] | None] = [None] * count
        self._slots: list[list[tuple[int, int]]] = [[] for _ in range(count)]
        self._held: dict[int, _Held] = {}
        self._bottom: list[tuple[int, int, int]] = []
        self.used = 0
        self.peak = 0
        self.refused_rows = 0
        # The reserve pool holds up to ``size`` rows: enough that, after the cover
        # has taken its rows, the reserve can still be filled in priority order.
        self._reserve_cap = size

    # Feeding ---------------------------------------------------------------------

    def feed(
        self, start: int, rows: list[list[str]], covers: list[Cover], priorities: list[int]
    ) -> None:
        """Offer the rows of a batch, numbered from ``start``."""
        observed = self._observed
        worst = self._worst
        bottom = self._bottom
        cap = self._reserve_cap
        for offset, (row, cover) in enumerate(zip(rows, covers, strict=True)):
            record = start + offset
            priority = priorities[offset]
            held: _Held | None = None
            key = (priority, record)
            for target in cover:
                observed[target] += 1
                limit = worst[target]
                if limit is not None and key >= limit:
                    continue
                held = self._offer(target, record, priority, row, cover, held)
            if cap and (len(bottom) < cap or (-bottom[0][0], -bottom[0][1]) > (priority, record)):
                self._reserve(record, priority, row, cover)

    def _limit(self, target: int) -> float:
        return self.budget if self.mandatory[target] else self.budget * OPTIONAL_SHARE

    def _hold(self, record: int, priority: int, row: list[str], cover: Cover) -> _Held:
        held = self._held.get(record)
        if held is None:
            held = self._held[record] = _Held(record, row, row_cost(row), cover, priority)
            self.used += held.cost
            self.peak = max(self.peak, self.used)
        return held

    def _release(self, held: _Held) -> None:
        held.refs -= 1
        if held.refs <= 0 and not held.reserve:
            self._held.pop(held.record, None)
            self.used -= held.cost

    def _offer(
        self,
        target: int,
        record: int,
        priority: int,
        row: list[str],
        cover: Cover,
        held: _Held | None,
    ) -> _Held | None:
        slots = self._slots[target]
        key = (priority, record)
        full = len(slots) >= self.per_target
        if full and key >= slots[-1]:
            return held
        known = held if held is not None else self._held.get(record)
        if known is None and self.used + row_cost(row) > self._limit(target):
            # Refused for the budget, counted on the target (SMART-11).
            self.outcomes[target].refused += 1
            self.refused_rows += 1
            return held
        known = known or self._hold(record, priority, row, cover)
        if full:
            _, dropped = slots.pop()
            evicted = self._held.get(dropped)
            if evicted is not None:
                self._release(evicted)
        insort(slots, key)
        if len(slots) >= self.per_target:
            self._worst[target] = slots[-1]
        known.refs += 1
        return known

    def _reserve(self, record: int, priority: int, row: list[str], cover: Cover) -> None:
        bottom = self._bottom
        known = self._held.get(record)
        if known is None and self.used + row_cost(row) > self.budget:
            self.refused_rows += 1
            return
        held = known or self._hold(record, priority, row, cover)
        if held.reserve:
            return
        held.reserve = True
        heapq.heappush(bottom, (-priority, -record, record))
        if len(bottom) > self._reserve_cap:
            _, _, worst = heapq.heappop(bottom)
            gone = self._held.get(worst)
            if gone is not None:
                gone.reserve = False
                if gone.refs <= 0:
                    self._held.pop(worst, None)
                    self.used -= gone.cost

    # Choosing --------------------------------------------------------------------

    def finish(self) -> SelectionOutcome:
        """The rows of the sample, once the whole source was read."""
        outcomes = self.outcomes
        for target, slots in enumerate(self._slots):
            outcomes[target].candidates = len(slots)
            outcomes[target].observed = self._observed[target]
        held = self._held
        covered = [False] * len(outcomes)
        chosen: dict[int, _Held] = {}
        slots_left = max(0, self.size - self.reserve)

        def greedy(weight: Sequence[float]) -> None:
            nonlocal slots_left
            heap: list[tuple[float, int, int]] = []
            for row in held.values():
                gain = sum(weight[t] for t in row.cover)
                if gain > 0:
                    heap.append((-gain, row.priority, row.record))
            heapq.heapify(heap)
            while heap and slots_left > 0:
                negative, priority, record = heapq.heappop(heap)
                if record in chosen:
                    continue
                row = held[record]
                gain = sum(weight[t] for t in row.cover if not covered[t])
                if gain <= 0:
                    continue
                if -negative > gain + 1e-12:
                    heapq.heappush(heap, (-gain, priority, record))
                    continue
                chosen[record] = row
                slots_left -= 1
                for t in row.cover:
                    covered[t] = True

        mandatory_weight = [w if m else 0.0 for w, m in zip(self.weights, self.mandatory, strict=True)]
        greedy(mandatory_weight)
        greedy(self.weights)
        cover_rows = len(chosen)

        # What is left of the sample goes to ordinary rows, by priority: the
        # reserve first, then any other row the pool holds (SMART-10, E13).
        wanted = self.size - len(chosen)
        reserve_taken = 0
        if wanted > 0:
            ordered = sorted(
                (row for row in held.values() if row.reserve and row.record not in chosen),
                key=lambda r: (r.priority, r.record),
            )
            for row in ordered[:wanted]:
                chosen[row.record] = row
                reserve_taken += 1
            wanted = self.size - len(chosen)
        if wanted > 0:
            rest = sorted(
                (row for row in held.values() if row.record not in chosen),
                key=lambda r: (r.priority, r.record),
            )
            for row in rest[:wanted]:
                chosen[row.record] = row
                reserve_taken += 1
        for row in chosen.values():
            for t in row.cover:
                covered[t] = True

        mandatory_total = mandatory_done = 0
        for target, outcome in enumerate(outcomes):
            if self.mandatory[target] and outcome.observed:
                mandatory_total += 1
                mandatory_done += covered[target]
            outcome.covered = covered[target]
            if outcome.covered:
                continue
            if outcome.observed == 0:
                outcome.miss = MISS_NOT_OBSERVED
            elif outcome.candidates == 0:
                outcome.miss = MISS_BUDGET
            else:
                outcome.miss = MISS_SIZE
        rows = sorted(((r.record, r.row) for r in chosen.values()), key=lambda item: item[0])
        return SelectionOutcome(
            rows=rows,
            targets=outcomes,
            cover_rows=cover_rows,
            reserve_rows=reserve_taken,
            shortfall=max(0, self.size - len(chosen)),
            candidate_rows=len(held),
            peak_bytes=self.peak,
            refused_rows=self.refused_rows,
            mandatory_covered=mandatory_done,
            mandatory_total=mandatory_total,
        )
