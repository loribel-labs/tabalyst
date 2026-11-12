# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The columns of a dataset that miss a value in the same records (design 20.31,
lot 19), and the exact combinations of the columns each record lacks (20.44).

A record lacks a value for a column when the Scan would not count one: an empty,
blank or marker string, a null, an absent key. For each column the records of a
batch become one integer with a bit per record, so the records that lack a value
in two columns are the bit count of an AND, and a pair costs the same however many
rows a batch holds. The combination of a record is an integer with a bit per
column. Every count is exact: the sum of a column is checked against the Scan,
which counted the same records.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from fractions import Fraction

from tabalyst.scanner.models import DatasetResult, FieldResult
from tabalyst.scanner.observations import Record
from tabalyst.scanner.paths import FieldPath
from tabalyst.scanner.planner.costmodel import PAIR_FEED_ROWS
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import (
    MissingColumn,
    MissingMatrixResult,
    MissingPartner,
    MissingPattern,
    MissingPatternsResult,
)
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.routing import field_path

# A byte 0 or 1 of a flag, as the digit that ``int(..., 2)`` reads.
_DIGITS = bytes.maketrans(b"\x00\x01", b"01")
_NATIVE_VALUES = frozenset({"integer", "number", "boolean"})


class PatternTable:
    """The records counted by the set of columns they lack a value in.

    A combination is an integer with a bit per column; 0 is a record with every value.
    It is tracked from its first record, up to ``limit`` of them, so the same file
    gives the same table on any machine; the records of a combination met when the
    table is full are only summed."""

    __slots__ = ("complete", "counts", "limit", "untracked")

    def __init__(self, limit: int) -> None:
        self.limit = limit
        # In order of first appearance, which breaks the ties of the listing.
        self.counts: dict[int, int] = {}
        self.complete = 0
        self.untracked = 0

    def add(self, pattern: int, count: int) -> None:
        if not pattern:
            self.complete += count
            return
        counts = self.counts
        found = counts.get(pattern)
        if found is not None:
            counts[pattern] = found + count
        elif len(counts) < self.limit:
            counts[pattern] = count
        else:
            self.untracked += count

    def add_flags(self, live: Sequence[tuple[int, Sequence[bool]]], size: int) -> None:
        """A batch of ``size`` records, given by the flags (a value or not) of the
        columns that lack a value in at least one of them. A ``Counter`` keeps the
        order of first appearance in the batch, so the table admits the combinations
        in the order of the file."""
        if not live:
            self.complete += size
            return
        columns = [1 << column for column, _ in live]
        for key, count in Counter(zip(*(flags for _, flags in live), strict=True)).items():
            pattern = 0
            for bit, flag in zip(columns, key, strict=True):
                if not flag:
                    pattern |= bit
            self.add(pattern, count)

    @property
    def records(self) -> int:
        return self.complete + self.untracked + sum(self.counts.values())


class MatrixAccumulator:
    """Counts of the records that lack a value, per column of the ``members`` of a
    dataset, which the Scan found to lack one somewhere; per pair of them when
    ``pairs`` is set (``missing_matrix``), and per combination when ``table`` is
    (``missing_patterns``). One accumulator serves both analyses of a dataset."""

    __slots__ = (
        "_all",
        "_bits",
        "_buffered",
        "both",
        "by_path",
        "failure",
        "members",
        "missing",
        "pairs",
        "reader",
        "records",
        "table",
        "values",
    )

    def __init__(self, reader: CellReader, members: Sequence[FieldResult]) -> None:
        self.reader = reader
        self.members = list(members)
        self.by_path: dict[FieldPath, int] = {
            field_path(field.path): index for index, field in enumerate(self.members)
        }
        count = len(self.members)
        self.missing = [0] * count
        self.both: dict[tuple[int, int], int] = {}
        self.pairs = False
        self.table: PatternTable | None = None
        self.records = 0
        # Cells handed, for the count of the run.
        self.values = 0
        self.failure: str | None = None
        # Records that carry a value, one bit per record of the buffer (a source
        # read one record at a time).
        self._bits = [0] * count
        self._buffered = 0
        self._all = (1 << count) - 1

    def count_pairs(self) -> None:
        """Count the records that lack a value in each pair of columns."""
        self.pairs = True

    def count_patterns(self, limit: int) -> None:
        """Count the records by the set of columns they lack a value in."""
        if self.table is None:
            self.table = PatternTable(limit)

    def add_rows(self, rows: Sequence[Sequence[str]], indexes: Sequence[int]) -> None:
        """A batch of rows of strings: ``indexes[k]`` is where the row holds the
        k-th member."""
        size = len(rows)
        content = self.reader.content
        live: list[tuple[int, list[bool]]] = []
        for column, index in enumerate(indexes):
            flags = content([row[index] for row in rows])
            if not all(flags):
                live.append((column, flags))
        self.values += size * len(indexes)
        self.records += size
        missing = self.missing
        for column, flags in live:
            missing[column] += size - sum(flags)
        if self.pairs and len(live) > 1:
            full = (1 << size) - 1
            self._count_pairs(
                [(column, full ^ int(bytes(flags).translate(_DIGITS), 2)) for column, flags in live]
            )
        if self.table is not None:
            self.table.add_flags(live, size)

    def add_record(self, record: Record) -> None:
        """One record read on its own: a member has a value when it observes a
        content string or a number."""
        category = self.reader.strings.category
        bit = 1 << self._buffered
        by_path = self.by_path
        present = 0
        for observation in record.observations:
            column = by_path.get(observation.path)
            if column is None:
                continue
            kind = observation.type
            if kind == "string":
                if category(observation.value) == "content":  # type: ignore[arg-type]
                    self._bits[column] |= bit
                    present |= 1 << column
            elif kind in _NATIVE_VALUES:
                self._bits[column] |= bit
                present |= 1 << column
        if self.table is not None:
            self.table.add(self._all ^ present, 1)
        self.values += len(self.members)
        self._buffered += 1
        if self._buffered >= PAIR_FEED_ROWS:
            self.flush()

    def flush(self) -> None:
        """Count the records buffered by ``add_record``."""
        size = self._buffered
        if not size:
            return
        full = (1 << size) - 1
        masks = [full ^ bits for bits in self._bits]
        self._bits = [0] * len(self.members)
        self._buffered = 0
        self.records += size
        live = [(column, mask) for column, mask in enumerate(masks) if mask]
        missing = self.missing
        for column, mask in live:
            missing[column] += mask.bit_count()
        if self.pairs:
            self._count_pairs(live)

    def _count_pairs(self, live: list[tuple[int, int]]) -> None:
        both = self.both
        for position, (first, first_mask) in enumerate(live):
            for second, second_mask in live[position + 1 :]:
                shared = (first_mask & second_mask).bit_count()
                if shared:
                    key = (first, second)
                    both[key] = both.get(key, 0) + shared

    def check(self, dataset: DatasetResult) -> None:
        """Compare the counts of every column with the Scan's: the same records,
        and as many without a value as the Scan counted."""
        if self.records != dataset.record_count:
            raise ScanMismatch(
                f"records: the second pass read {self.records}, the scan {dataset.record_count}"
            )
        for field, missing in zip(self.members, self.missing, strict=True):
            expected = dataset.record_count - field.values.count
            if missing != expected:
                raise ScanMismatch(
                    f"records without a value: the second pass found {missing}, the scan {expected}"
                )

    def result(self, column: int, max_listed: int) -> MissingMatrixResult:
        """The partners of a member, those that lack a value most with it first
        (the share of the records that lack one in either where both do, then the
        count of the two, then the order of the document)."""
        mine = self.missing[column]
        found: list[tuple[Fraction, int, int]] = []
        for other, missing in enumerate(self.missing):
            if other == column:
                continue
            shared = self.both.get((min(column, other), max(column, other)), 0)
            if shared:
                found.append((Fraction(shared, mine + missing - shared), shared, other))
        found.sort(key=lambda item: (-item[0], -item[1], item[2]))
        listed = [
            MissingPartner(
                field=self.members[other].id,
                display=self.members[other].display,
                missing=self.missing[other],
                both=shared,
            )
            for _, shared, other in found[:max_listed]
        ]
        return MissingMatrixResult(
            records=self.records,
            missing=mine,
            columns=len(self.members),
            partners=len(found),
            truncated=len(found) > max_listed,
            listed=listed,
        )

    def patterns_result(self, max_listed: int) -> MissingPatternsResult:
        """The combinations of the dataset, the most frequent first, then those of
        fewer columns, then the order of first appearance.

        Raises ``RuntimeError`` when the table does not add up to the records, or,
        while every combination is tracked, to the records each column lacks."""
        table = self.table
        assert table is not None
        if table.records != self.records:
            raise RuntimeError("the combinations do not add up to the records read")
        counts = list(table.counts.items())
        if not table.untracked:
            for column, missing in enumerate(self.missing):
                bit = 1 << column
                if sum(count for pattern, count in counts if pattern & bit) != missing:
                    raise RuntimeError("the combinations do not add up to a column")
        order = sorted(
            range(len(counts)),
            key=lambda index: (-counts[index][1], counts[index][0].bit_count(), index),
        )
        listed = [counts[index] for index in order[:max_listed]]
        ids = [member.id for member in self.members]
        return MissingPatternsResult(
            records=self.records,
            columns=[
                MissingColumn(field=member.id, display=member.display, missing=missing)
                for member, missing in zip(self.members, self.missing, strict=True)
            ],
            complete_records=table.complete,
            distinct=len(counts),
            complete=table.untracked == 0,
            untracked=table.untracked,
            listed=[
                MissingPattern(
                    columns=[ids[column] for column in range(len(ids)) if pattern >> column & 1],
                    count=count,
                )
                for pattern, count in listed
            ],
            other_patterns=len(counts) - len(listed),
            other_records=sum(count for _, count in counts) - sum(count for _, count in listed),
        )
