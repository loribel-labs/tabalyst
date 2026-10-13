# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The columns of a dataset that miss a value in the same records (design 20.31,
lot 19).

A record lacks a value for a column when the Scan would not count one: an empty,
blank or marker string, a null, an absent key. For each column the records of a
batch become one integer with a bit per record, so the records that lack a value
in two columns are the bit count of an AND, and a pair costs the same however many
rows a batch holds. Every count is exact: the sum of a column is checked against
the Scan, which counted the same records.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction

from tabalyst.scanner.models import DatasetResult, FieldResult
from tabalyst.scanner.observations import Record
from tabalyst.scanner.paths import FieldPath
from tabalyst.scanner.planner.costmodel import PAIR_FEED_ROWS
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import MissingMatrixResult, MissingPartner
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.routing import field_path

# A byte 0 or 1 of a flag, as the digit that ``int(..., 2)`` reads.
_DIGITS = bytes.maketrans(b"\x00\x01", b"01")
_NATIVE_VALUES = frozenset({"integer", "number", "boolean"})


class MatrixAccumulator:
    """Counts of the records that lack a value, per column and per pair of the
    ``members`` of a dataset, which the Scan found to lack one somewhere."""

    __slots__ = (
        "_bits",
        "_buffered",
        "both",
        "by_path",
        "failure",
        "members",
        "missing",
        "reader",
        "records",
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
        self.records = 0
        # Cells handed, for the count of the run.
        self.values = 0
        self.failure: str | None = None
        # Records that carry a value, one bit per record of the buffer (a source
        # read one record at a time).
        self._bits = [0] * count
        self._buffered = 0

    def add_rows(self, rows: Sequence[Sequence[str]], indexes: Sequence[int]) -> None:
        """A batch of rows of strings: ``indexes[k]`` is where the row holds the
        k-th member."""
        size = len(rows)
        full = (1 << size) - 1
        content = self.reader.content
        masks: list[int] = []
        for index in indexes:
            flags = content([row[index] for row in rows])
            if all(flags):
                masks.append(0)
            else:
                masks.append(full ^ int(bytes(flags).translate(_DIGITS), 2))
        self.values += size * len(indexes)
        self._count(masks, size)

    def add_record(self, record: Record) -> None:
        """One record read on its own: a member has a value when it observes a
        content string or a number."""
        category = self.reader.strings.category
        bit = 1 << self._buffered
        by_path = self.by_path
        for observation in record.observations:
            column = by_path.get(observation.path)
            if column is None:
                continue
            kind = observation.type
            if kind == "string":
                if category(observation.value) == "content":  # type: ignore[arg-type]
                    self._bits[column] |= bit
            elif kind in _NATIVE_VALUES:
                self._bits[column] |= bit
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
        self._count(masks, size)

    def _count(self, masks: list[int], size: int) -> None:
        self.records += size
        live = [(column, mask) for column, mask in enumerate(masks) if mask]
        missing = self.missing
        for column, mask in live:
            missing[column] += mask.bit_count()
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
