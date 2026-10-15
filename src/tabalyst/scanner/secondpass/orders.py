# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The order of two dates of the same record, counted over every row (design 20.38).

A pair of date columns is read once per batch: each distinct string of a column is
read by the date detector as the Scan reads the column (the ambiguous dates in the
order its evidence gives), and the two dates of a record are compared when both are
of the same kind. Every count is exact: ``records`` is checked against the Scan.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import NamedTuple

from tabalyst.scanner.detectors.temporal import kind_of
from tabalyst.scanner.models import DatasetResult, FieldResult
from tabalyst.scanner.observations import Observation, Record
from tabalyst.scanner.paths import FieldPath
from tabalyst.scanner.planner.costmodel import PAIR_FEED_ROWS, REPLAY_MEMO_ENTRIES
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import (
    DateOrderBreak,
    DateOrderExclusions,
    DateOrderResult,
)
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.routing import field_path

# What a raw string is worth for the order, other than a date.
_MISSING = "missing"
_NOT_A_DATE = "not_a_date"
_AMBIGUOUS = "ambiguous"
_OTHER_KIND = "other_kind"
# The reason that counts when both sides have one: the first of this list.
_PRIORITY = {_MISSING: 0, _NOT_A_DATE: 1, _AMBIGUOUS: 2}
# What stands for a value that is no string (a number, several strings): text that
# no date detector reads, so the record counts as "not a date" and not as missing.
_NOT_TEXT = "\x00"


class DateReading(NamedTuple):
    """A string read as a date (``value``, of kind ``kind``) or why it is none."""

    reason: str | None
    kind: str | None = None
    value: object = None


class DateSide:
    """One column of the pair: the reading of its strings, remembered. ``order`` is
    the order the evidence of the Scan gives the ambiguous dates of the column."""

    __slots__ = ("memo", "order", "reader")

    def __init__(self, reader: CellReader, order: str | None) -> None:
        self.reader = reader
        self.order = order
        self.memo: dict[str, DateReading] = {}

    def read(self, strings: Sequence[str]) -> list[DateReading]:
        memo = self.memo
        fresh = [raw for raw in dict.fromkeys(strings) if raw not in memo]
        if fresh:
            room = REPLAY_MEMO_ENTRIES - len(memo)
            cells = self.reader.cells(fresh, numbers=False, dates=self.order or True)
            table: dict[str, DateReading] = {}
            for raw, cell in zip(fresh, cells, strict=True):
                table[raw] = self._reading(cell.length, cell.moment)
            for raw, reading in table.items():
                if room > 0:
                    memo[raw] = reading
                    room -= 1
            return [memo.get(raw) or table[raw] for raw in strings]
        return [memo[raw] for raw in strings]

    @staticmethod
    def _reading(length: int, moment: object) -> DateReading:
        if length < 0:
            return DateReading(_MISSING)
        state = getattr(moment, "state", None)
        if state == "matched":
            value = moment.value  # type: ignore[attr-defined]
            kind = kind_of(value)
            return DateReading(None, kind, value) if kind is not None else DateReading(_NOT_A_DATE)
        if state == "ambiguous":
            return DateReading(_AMBIGUOUS)
        return DateReading(_NOT_A_DATE)


def comparable(a: DateReading, b: DateReading) -> bool:
    """Whether two readings are dates of the same kind, which can be put in order."""
    return a.reason is None and b.reason is None and a.kind == b.kind


def breaks_order(a: DateReading, b: DateReading) -> bool:
    """Whether the first date is after the second."""
    return comparable(a, b) and a.value > b.value  # type: ignore[operator]


class OrderAccumulator:
    """Counts, for a pair of date columns, the records where the first date is on
    or before the second, equal to it, or after it."""

    __slots__ = (
        "_buffer",
        "broken",
        "by_path",
        "compared",
        "equal",
        "excluded",
        "failure",
        "listed",
        "max_listed",
        "records",
        "sides",
        "values",
    )

    def __init__(
        self,
        first: tuple[FieldResult, CellReader, str | None],
        second: tuple[FieldResult, CellReader, str | None],
        max_listed: int,
    ) -> None:
        self.by_path: dict[FieldPath, int] = {
            field_path(first[0].path): 0,
            field_path(second[0].path): 1,
        }
        self.sides = (DateSide(first[1], first[2]), DateSide(second[1], second[2]))
        self.max_listed = max_listed
        self.records = 0
        self.compared = 0
        self.equal = 0
        self.broken = 0
        self.excluded = {_MISSING: 0, _NOT_A_DATE: 0, _AMBIGUOUS: 0, _OTHER_KIND: 0}
        self.listed: list[DateOrderBreak] = []
        # Cells handed, for the count of the run.
        self.values = 0
        self.failure: str | None = None
        # Records read one at a time (JSON, Excel) wait here for a full buffer.
        self._buffer: tuple[list[str], list[str]] = ([], [])

    def add_rows(self, rows: Sequence[Sequence[str]], indexes: Sequence[int]) -> None:
        """A batch of rows of strings: ``indexes[k]`` is where the row holds the
        k-th column of the pair."""
        self.values += len(rows) * 2
        self._count(
            [row[indexes[0]] for row in rows],
            [row[indexes[1]] for row in rows],
        )

    def add_record(self, record: Record) -> None:
        """One record read on its own: a column without a value or with a null has
        none for the pair; one that holds a single string is read as it is, and
        anything else (a number, several values) is no date."""
        found: dict[int, list[Observation]] = {0: [], 1: []}
        for observation in record.observations:
            column = self.by_path.get(observation.path)
            if column is not None:
                found[column].append(observation)
        self.values += 2
        for column in (0, 1):
            seen = [o for o in found[column] if o.type != "null"]
            if not seen:
                text = ""
            elif len(seen) == 1 and seen[0].type == "string":
                text = seen[0].value  # type: ignore[assignment]
            else:
                text = _NOT_TEXT
            self._buffer[column].append(text)
        if len(self._buffer[0]) >= PAIR_FEED_ROWS:
            self.flush()

    def flush(self) -> None:
        """Count the records buffered by ``add_record``."""
        first, second = self._buffer
        if not first:
            return
        self._buffer = ([], [])
        self._count(first, second)

    def _count(self, firsts: list[str], seconds: list[str]) -> None:
        left, right = self.sides[0].read(firsts), self.sides[1].read(seconds)
        excluded = self.excluded
        for position, (a, b) in enumerate(zip(left, right, strict=True)):
            number = self.records + position + 1
            if a.reason is not None or b.reason is not None:
                reason = min((r for r in (a.reason, b.reason) if r), key=_PRIORITY.__getitem__)
                excluded[reason] += 1
                continue
            if not comparable(a, b):
                excluded[_OTHER_KIND] += 1
                continue
            self.compared += 1
            if a.value == b.value:
                self.equal += 1
            elif breaks_order(a, b):
                self.broken += 1
                if len(self.listed) < self.max_listed:
                    self.listed.append(
                        DateOrderBreak(
                            record=number,
                            first=a.value.isoformat(),  # type: ignore[attr-defined]
                            second=b.value.isoformat(),  # type: ignore[attr-defined]
                        )
                    )
        self.records += len(firsts)

    def check(self, dataset: DatasetResult) -> None:
        """Compare the records read with the Scan's: the same records."""
        if self.records != dataset.record_count:
            raise ScanMismatch(
                f"records: the second pass read {self.records}, the scan {dataset.record_count}"
            )

    def result(self) -> DateOrderResult:
        return DateOrderResult(
            records=self.records,
            compared=self.compared,
            equal=self.equal,
            broken=self.broken,
            excluded=DateOrderExclusions(
                missing=self.excluded[_MISSING],
                not_a_date=self.excluded[_NOT_A_DATE],
                ambiguous=self.excluded[_AMBIGUOUS],
                other_kind=self.excluded[_OTHER_KIND],
            ),
            truncated=self.broken > len(self.listed),
            listed=self.listed,
        )
