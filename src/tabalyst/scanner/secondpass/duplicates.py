# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The repeated values of an identifier or of a combination of columns (design
20.21, lot 15).

Every value is held as a 128-bit BLAKE2b digest with the record of its first
occurrence, so the memory does not depend on how long the values are. The first
time a digest comes back, the value becomes a repeated one: its text and its
count (the first occurrence included) go to a bounded table and are exact from
then on. The memory is drawn from the pool of the exact sets of the run
(MEM-06); when the pool cannot hold the digests the search stops and proves only
a lower bound (D08).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from hashlib import blake2b
from sys import getsizeof

from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.exactset import MEASURE_STEP, MEMORY_BUDGET, ExactPool
from tabalyst.scanner.secondpass.models import (
    DuplicateResult,
    DuplicatesLimited,
    DuplicateValue,
    RepeatedValues,
)
from tabalyst.scanner.secondpass.replay import CellReader

__all__ = ["MEMORY_BUDGET", "DuplicateAccumulator", "derive_from_samples", "digest"]

# Bytes charged for a new digest: the key (16 bytes of content) and the integer
# that holds its record and its flag. Measured at lot 15 (``planner_costs.py``).
ENTRY_BYTES = 81
# The first record of a value, or ``Callable`` of a batch: ``None`` for samples.
FirstRecord = Callable[[str], int]


def digest(parts: Sequence[str]) -> bytes:
    """The 128-bit digest of a value or of a combination: each part is prefixed
    by its length, so that no two combinations share a text."""
    hasher = blake2b(digest_size=16)
    for part in parts:
        raw = part.encode("utf-8", "surrogatepass")
        hasher.update(len(raw).to_bytes(4, "little"))
        hasher.update(raw)
    return hasher.digest()


def _native_text(native_type: str, value: object) -> str:
    if native_type == "integer":
        return str(int(value))  # type: ignore[call-overload]
    if native_type == "boolean":
        return str(bool(value))
    return str(value)


class _Repeated:
    """A tracked repeated value: its label (the text, or the texts of a combination),
    its occurrences and the record of the first."""

    __slots__ = ("count", "label", "record")

    def __init__(self, label: str | tuple[str, ...], count: int, record: int | None) -> None:
        self.label = label
        self.count = count
        self.record = record


class DuplicateAccumulator:
    """The digests seen, the values found repeated and their counts."""

    __slots__ = (
        "cell_ns",
        "columns",
        "incomplete",
        "limited",
        "lower_bound",
        "max_listed",
        "max_tracked",
        "payload",
        "pending",
        "pool",
        "redundant_seen",
        "repeated",
        "repeated_distinct",
        "table",
        "untracked",
        "used",
        "values",
    )

    def __init__(
        self,
        pool: ExactPool,
        *,
        max_listed: int,
        max_tracked: int,
        columns: Sequence[str] | None = None,
        cell_ns: int = 0,
    ) -> None:
        self.pool = pool
        self.max_listed = max_listed
        self.max_tracked = max_tracked
        self.columns = None if columns is None else list(columns)
        # What the plan expects a cell to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        # digest -> ``record << 1 | repeated``: the record is 0 when unknown.
        self.table: dict[bytes, int] = {}
        # digest -> the tracked repeated values.
        self.repeated: dict[bytes, _Repeated] = {}
        self.values = 0
        self.incomplete = 0
        self.repeated_distinct = 0
        # Occurrences of the repeated values, the first of each included.
        self.redundant_seen = 0
        self.untracked = 0
        self.payload = 0
        self.used = 0
        self.pending = 0
        self.limited = False
        self.lower_bound = 0

    @property
    def uses_pool(self) -> bool:
        """Whether the accumulator draws from the pool of the run's exact sets."""
        return True

    # Feeding ---------------------------------------------------------------

    def add_strings(self, raws: Sequence[str], counts: Sequence[int], first: FirstRecord | None) -> None:
        """Account for the distinct content strings of a batch with their counts;
        ``first`` gives the record of the first occurrence of each."""
        if self.limited:
            return
        for raw, count in zip(raws, counts, strict=True):
            self._add(
                blake2b(b"s" + raw.encode("utf-8", "surrogatepass"), digest_size=16).digest(),
                raw,
                count,
                None if first is None else first(raw),
            )
        self._measured(len(raws))

    def add_native(
        self, native_type: str, value: object, record: int | None = None, count: int = 1
    ) -> None:
        """A JSON integer, number or boolean: a value of its own type."""
        if self.limited:
            return
        text = _native_text(native_type, value)
        self._add(
            blake2b(f"{native_type[0]}{text}".encode(), digest_size=16).digest(),
            text,
            count,
            record,
        )
        self._measured(1)

    def add_combination(
        self, parts: Sequence[str], count: int, record: int | None
    ) -> None:
        """``count`` rows whose every column of the key has these values."""
        if self.limited:
            return
        self._add(digest(parts), tuple(parts), count, record)  # type: ignore[arg-type]
        self._measured(1)

    def add_incomplete(self, count: int = 1) -> None:
        """Rows where a column of the key has no value: not part of the key."""
        self.incomplete += count

    def _add(
        self, key: bytes, label: str | tuple[str, ...], count: int, record: int | None
    ) -> None:
        self.values += count
        table = self.table
        state = table.get(key)
        if state is None:
            if count == 1:
                table[key] = (record or 0) << 1
                self.payload += ENTRY_BYTES
                return
            table[key] = ((record or 0) << 1) | 1
            self.payload += ENTRY_BYTES
            self._repeat(key, label, count, record)
        elif state & 1:
            slot = self.repeated.get(key)
            if slot is not None:
                slot.count += count
            else:
                self.untracked += count
            self.redundant_seen += count
        else:
            table[key] = state | 1
            self._repeat(key, label, count + 1, (state >> 1) or None)

    def _repeat(
        self, key: bytes, label: str | tuple[str, ...], occurrences: int, record: int | None
    ) -> None:
        """The value comes back: from now on its count is tracked, if there is
        room."""
        self.repeated_distinct += 1
        self.redundant_seen += occurrences
        if len(self.repeated) < self.max_tracked:
            self.repeated[key] = _Repeated(label, occurrences, record)
            size = len(label) if isinstance(label, str) else sum(map(len, label))
            self.payload += ENTRY_BYTES + 2 * size
        else:
            self.untracked += occurrences

    # Memory ----------------------------------------------------------------

    def _measured(self, added: int) -> None:
        self.pending += added
        if self.pending >= MEASURE_STEP:
            self.measure()

    def measure(self) -> None:
        """Charge the pool with what the tables hold now, and stop the search if
        the pool cannot hold it (the same rule as the exact set)."""
        self.pending = 0
        used = self.payload + getsizeof(self.table) + getsizeof(self.repeated)
        self.pool.used += used - self.used
        self.used = used
        if self.pool.used > self.pool.total:
            self.stop()

    def stop(self) -> None:
        """Release the tables: the count of a prefix is not the cardinality."""
        self.lower_bound = len(self.table)
        self.limited = True
        self.pool.used -= self.used
        self.used = 0
        self.payload = 0
        self.table = {}
        self.repeated = {}

    # Result ----------------------------------------------------------------

    def result(
        self, expected: int, lower_bound: int | None, computed_from: str, records: bool
    ) -> DuplicateResult | DuplicatesLimited:
        """The repeated values, checked against the Scan: ``expected`` is the
        number of values it counted (the rows of a combination are not checked
        here) and ``lower_bound`` the distinct values it proved, if any."""
        if self.pending and not self.limited:
            self.measure()
        if self.limited:
            return DuplicatesLimited(
                values_read=self.values,
                distinct=self.lower_bound,
                repeated=self.repeated_distinct,
            )
        if self.columns is None and self.values != expected:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {expected}"
            )
        distinct = len(self.table)
        if lower_bound is not None and distinct < lower_bound:
            raise ScanMismatch(
                f"distinct values: the second pass found {distinct}, "
                f"the scan proved at least {lower_bound}"
            )
        redundant = self.values - distinct
        if self.redundant_seen - self.repeated_distinct != redundant:
            raise ScanMismatch("the counts of the repeated values do not add up")
        ranked = sorted(
            self.repeated.values(), key=lambda slot: (-slot.count, slot.label)
        )
        complete = not self.untracked
        return DuplicateResult(
            accuracy="exact" if complete else "exact_counts",
            computed_from=computed_from,  # type: ignore[arg-type]
            records=records,
            columns=self.columns,
            values=self.values,
            incomplete=self.incomplete if self.columns is not None else None,
            distinct=distinct,
            redundant=redundant,
            unique=distinct == self.values,
            repeated=RepeatedValues(
                distinct=self.repeated_distinct,
                occurrences=self.redundant_seen,
                tracked=len(ranked),
                untracked=self.untracked,
                complete=complete,
                truncated=len(ranked) > self.max_listed,
                listed=[
                    DuplicateValue(
                        value=slot.label if isinstance(slot.label, str) else list(slot.label),
                        count=slot.count,
                        first_record=slot.record,
                    )
                    for slot in ranked[: self.max_listed]
                ],
            ),
        )


class RawFeed:
    """The strings of one column of a key, converted once for every key that uses
    it: the string where the row has a value, ``None`` where it has none. A batch
    of a CSV file goes through ``convert``; a record at a time (JSON, Excel)
    through ``push_*`` and ``end_record``, and the rows wait in ``rows`` until the
    router hands a full buffer to the keys. ``records`` numbers the rows being
    handed, ``present`` counts the rows that have a value."""

    __slots__ = (
        "buffered",
        "failure",
        "pending",
        "present",
        "reader",
        "records",
        "rows",
        "seen",
        "values",
    )

    def __init__(self, reader: CellReader) -> None:
        self.reader = reader
        self.values = 0
        self.present = 0
        self.rows: list[str | None] = []
        self.records: Sequence[int] = []
        self.buffered: list[int] = []
        self.pending: str | None = None
        # The record has already given its value (the first occurrence counts).
        self.seen = False
        self.failure: str | None = None

    def convert(self, strings: Sequence[str], start: int = 0) -> list[str | None]:
        """The value of each string of consecutive records numbered from
        ``start``: the string itself when it is content, else ``None``."""
        self.values += len(strings)
        distinct = list(dict.fromkeys(strings))
        table = {
            raw: raw if ok else None
            for raw, ok in zip(distinct, self.reader.content(distinct), strict=True)
        }
        self.records = range(start, start + len(strings))
        found = [table[raw] for raw in strings]
        self.present += len(found) - found.count(None)
        return found

    def push_string(self, raw: str) -> None:
        """The string a record holds in the column."""
        self.values += 1
        self.seen = True
        self.pending = raw if self.reader.content([raw])[0] else None

    def push_native(self, native_type: str, value: object) -> None:
        """A JSON integer, number or boolean: its text, as the value."""
        self.values += 1
        self.seen = True
        self.pending = _native_text(native_type, value)

    def end_record(self, index: int = 0) -> None:
        """Close the row of the record numbered ``index``: what it held, or
        nothing."""
        self.rows.append(self.pending)
        self.present += self.pending is not None
        self.buffered.append(index)
        self.records = self.buffered
        self.pending = None
        self.seen = False

    def reset(self) -> None:
        """Forget the rows handed to the keys."""
        self.rows = []
        self.buffered = []
        self.records = self.buffered


class KeyAccumulator:
    """The repeated combinations of the values of two columns: the rows where both
    have a value go to the search for repeated values, the others are counted as
    incomplete."""

    def __init__(self, first: RawFeed, second: RawFeed, duplicates: DuplicateAccumulator) -> None:
        self.first = first
        self.second = second
        self.duplicates = duplicates
        self.failure: str | None = None

    @property
    def uses_pool(self) -> bool:
        return True

    def add(self, first: Sequence[str | None], second: Sequence[str | None]) -> None:
        """Account for aligned rows of the two columns."""
        records = self.first.records
        pairs = list(zip(first, second, strict=True))
        counts = Counter(pairs)
        # The last assignment wins, so walking backward keeps the first row.
        index = dict(zip(reversed(pairs), range(len(pairs) - 1, -1, -1), strict=True))
        duplicates = self.duplicates
        for pair, count in counts.items():
            left, right = pair
            if left is None or right is None:
                duplicates.add_incomplete(count)
            else:
                duplicates.add_combination((left, right), count, records[index[pair]])

    def check(self, first: FieldResult, second: FieldResult, records: int) -> None:
        """The rows that have a value in each column are the values the Scan
        counted, and the rows of the key (complete or not) are the records of
        the dataset; a difference means the key was not read as the Scan read the
        columns."""
        rows = self.duplicates.values + self.duplicates.incomplete
        if rows != records:
            raise ScanMismatch(f"the key has {rows} rows, the scan counted {records} records")
        for label, found, expected in (
            ("first column", self.first.present, first.values.count),
            ("second column", self.second.present, second.values.count),
        ):
            if found != expected:
                raise ScanMismatch(
                    f"the {label} has a value in {found} rows, the scan counted {expected}"
                )


def derive_from_samples(accumulator: DuplicateAccumulator, field: FieldResult) -> None:
    """Fill ``accumulator`` from the exact counts of a Scan that holds every
    distinct original value of the field, without reading the source (and so
    without a record). Raises ``ScanMismatch`` when the Scan does not hold them."""
    samples = field.values.samples
    if (
        samples.selection != "all"
        or samples.kept != samples.of
        or samples.long_texts is not None
        or any(entry.count_accuracy != "exact" for entry in samples.listed)
    ):
        raise ScanMismatch("the scan does not hold every distinct value with its exact count")
    strings = [entry for entry in samples.listed if entry.type == "string"]
    accumulator.add_strings([str(e.value) for e in strings], [e.count for e in strings], None)
    for entry in samples.listed:
        if entry.type != "string":
            accumulator.add_native(entry.type, entry.value, None, entry.count)
