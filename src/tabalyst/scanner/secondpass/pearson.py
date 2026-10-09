# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Accumulators of the Pearson correlation of a pair of columns (design 20.12).

A numeric column is read once per batch whatever the number of pairs that use
it (``ColumnFeed``, REL-03); each pair keeps its own co-moments over the rows
where both columns have a number (``PairAccumulator``, REL-07, REL-08).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence

from tabalyst.scanner.models import NumericStats
from tabalyst.scanner.pearson import (
    EMPTY,
    CoMoments,
    coefficient,
    comoments,
    merge,
    to_float,
)
from tabalyst.scanner.planner.costmodel import REPLAY_MEMO_ENTRIES
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import PearsonExclusions, PearsonResult
from tabalyst.scanner.secondpass.replay import CellReader, native_number

# A raw string's float (``None`` when it is not a number) and whether it is one.
_Entry = tuple[float | None, bool]
_NOT_A_NUMBER: _Entry = (None, False)


class ColumnFeed:
    """The numbers of one column, converted once for every pair that uses it.

    A batch of CSV strings goes through ``convert``; a record at a time (JSON,
    Excel) goes through ``push_*`` and ``end_record``, and the rows wait in
    ``rows`` until the router hands a full buffer to the pairs. ``numbers``
    counts the numbers the column holds as the Scan counts them, those beyond
    float64 included.
    """

    __slots__ = ("failure", "memo", "numbers", "pending", "reader", "rows", "seen", "values")

    def __init__(self, reader: CellReader) -> None:
        self.reader = reader
        self.memo: dict[str, _Entry] = {}
        self.numbers = 0
        self.values = 0
        self.rows: list[float | None] = []
        self.pending: float | None = None
        # The record has already given its value (the first occurrence counts).
        self.seen = False
        self.failure: str | None = None

    def convert(self, strings: Sequence[str]) -> list[float | None]:
        """The float of each string of consecutive records, ``None`` for a
        string that is not a number."""
        self.values += len(strings)
        counts = Counter(strings)
        memo = self.memo
        table: dict[str, _Entry] = {}
        missing: list[str] = []
        for raw in counts:
            entry = memo.get(raw)
            if entry is None:
                missing.append(raw)
            else:
                table[raw] = entry
        if missing:
            room = REPLAY_MEMO_ENTRIES - len(memo)
            for raw, cell in zip(missing, self.reader.cells(missing, numbers=True), strict=True):
                number = cell.number
                entry = _NOT_A_NUMBER if number is None else (to_float(number), True)
                table[raw] = entry
                if room > 0:
                    memo[raw] = entry
                    room -= 1
        self.numbers += sum(count for raw, count in counts.items() if table[raw][1])
        return [table[raw][0] for raw in strings]

    def push_string(self, raw: str) -> None:
        """The string a record holds in the column."""
        self.values += 1
        self.seen = True
        self.pending = self._one(raw)

    def _one(self, raw: str) -> float | None:
        entry = self.memo.get(raw)
        if entry is None:
            cell = self.reader.cells([raw], numbers=True)[0]
            entry = _NOT_A_NUMBER if cell.number is None else (to_float(cell.number), True)
            if len(self.memo) < REPLAY_MEMO_ENTRIES:
                self.memo[raw] = entry
        self.numbers += entry[1]
        return entry[0]

    def push_native(self, native_type: str, value: object) -> None:
        """A JSON number: it is a number whatever its text. A boolean is not."""
        self.values += 1
        self.seen = True
        if native_type == "boolean":
            self.pending = None
            return
        self.numbers += 1
        self.pending = to_float(native_number(native_type, value))

    def end_record(self) -> None:
        """Close the row of the record: what it held, or nothing."""
        self.rows.append(self.pending)
        self.pending = None
        self.seen = False


class PairAccumulator:
    """The co-moments of one pair over the rows where both columns have a
    number, and the rows left out (REL-07 to REL-09)."""

    def __init__(self, first: ColumnFeed, second: ColumnFeed, min_pairs: int) -> None:
        self.first = first
        self.second = second
        self.min_pairs = min_pairs
        self.moments: CoMoments = EMPTY
        self.failure: str | None = None
        self.rows = 0
        self.first_missing = 0
        self.second_missing = 0
        self.both_missing = 0

    def add(self, first: Sequence[float | None], second: Sequence[float | None]) -> None:
        """Account for aligned rows of the two columns."""
        batch = comoments(first, second)
        total = len(first)
        first_none = first.count(None)
        second_none = second.count(None)
        left_out = total - batch.n
        both = first_none + second_none - left_out
        self.rows += total
        self.both_missing += both
        self.first_missing += first_none - both
        self.second_missing += second_none - both
        self.moments = merge(self.moments, batch)

    def check(self, first: NumericStats, second: NumericStats) -> None:
        """The numbers the reading found in each column are the Scan's; a
        difference means the pair was not read as the Scan read the columns."""
        for label, found, expected in (
            ("first column", self.first.numbers, first.count),
            ("second column", self.second.numbers, second.count),
        ):
            if found != expected:
                raise ScanMismatch(
                    f"the {label} holds {found} numbers, the scan counted {expected}"
                )

    def result(self, source: str) -> PearsonResult:
        moments = self.moments
        r, reason = coefficient(moments, self.min_pairs)
        have = moments.n > 0
        return PearsonResult(
            source=source,  # type: ignore[arg-type]
            min_pairs=self.min_pairs,
            rows=self.rows,
            pairs=moments.n,
            excluded=PearsonExclusions(
                first_missing=self.first_missing,
                second_missing=self.second_missing,
                both_missing=self.both_missing,
            ),
            defined=r is not None,
            coefficient=r,
            reason=reason,
            mean_first=moments.mean_first if have else None,
            mean_second=moments.mean_second if have else None,
            std_first=math.sqrt(moments.m2_first / moments.n) if have else None,
            std_second=math.sqrt(moments.m2_second / moments.n) if have else None,
            covariance=moments.covariance,
        )

