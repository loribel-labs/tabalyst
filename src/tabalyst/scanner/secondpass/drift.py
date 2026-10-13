# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A column followed by position in the file: ten slices of records, the values
and the missing ones of each, and the slice where each value first appears
(design 20.30, lot 19).

The slices are cut on the record number, in file order, so the same file gives
the same slices on any machine. A record has a value for the field or it has
none: the missing ones of a slice are its records minus its values, which holds
for a CSV row, a JSON key that is absent, null or empty, and a cell the Scan
counted as missing, whatever the definition of ``values.missing``. A field that
repeats in a record cannot be counted this way and is left out by the planner.
"""

from __future__ import annotations

from bisect import bisect_right

from tabalyst.scanner.crosstab import association
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.frequencies import TYPE_ORDER, native_key
from tabalyst.scanner.secondpass.models import (
    DriftCategory,
    DriftSlice,
    DriftValues,
    PositionDriftResult,
    TableAssociation,
)

# The slices of the records, deciles of the file.
SLICES = 10


def slice_bounds(records: int) -> list[int]:
    """The first position (the record number minus one) of each slice, then the
    end: the position ``p`` is in slice ``p * 10 // records``."""
    return [(k * records + SLICES - 1) // SLICES for k in range(SLICES + 1)]


def table_association(counts: list[list[int]]) -> TableAssociation:
    """Cramér's V of a table of counts (the rows are the values, the columns the
    slices), in the model the tables of the second pass use."""
    found = association(counts)
    return TableAssociation(
        defined=found.corrected is not None,
        n=found.n,
        effective_categories=found.effective_rows,
        effective_classes=found.effective_columns,
        chi_square=found.chi_square,
        degrees=found.degrees,
        cramers_v=found.cramers_v,
        corrected=found.corrected,
        low_share=found.low_share,
        stable=found.stable,
        sparse=found.sparse,
        reason=found.reason,
    )


class DriftAccumulator:
    """The values of one field by slice of records. With ``track`` set, every
    distinct value gets its own count per slice; a source that holds more distinct
    values than ``limit`` cannot be the one the Scan read, and the result fails."""

    __slots__ = ("bounds", "cell_ns", "counts", "limit", "max_listed", "overflow", "track", "values")

    def __init__(
        self,
        records: int,
        *,
        track: bool,
        limit: int,
        max_listed: int,
        cell_ns: int = 0,
    ) -> None:
        self.bounds = slice_bounds(records)
        self.track = track
        self.limit = limit
        self.max_listed = max_listed
        # What the plan expects a cell to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.values = [0] * SLICES
        self.counts: dict[tuple[str, str], list[int]] = {}
        self.overflow = False

    @property
    def needs_text(self) -> bool:
        """Whether the analytical text of a value is read (it is, to follow the
        values) and not only whether the record has one."""
        return self.track

    def slice_of(self, record: int) -> int:
        """The slice of a record, numbered from 1."""
        return bisect_right(self.bounds, record - 1) - 1

    def segments(self, start: int, length: int) -> list[tuple[int, int]]:
        """The ranges ``(low, high)`` of the ``length`` consecutive records from
        ``start`` that fall in one slice each."""
        found: list[tuple[int, int]] = []
        low = 0
        first = start - 1
        while low < length:
            index = min(bisect_right(self.bounds, first + low) - 1, SLICES - 1)
            high = min(length, self.bounds[index + 1] - first)
            if high <= low:
                # A record beyond the last one the Scan counted: it belongs to no
                # slice, and the check against the Scan fails the result.
                high = length
            found.append((low, high))
            low = high
        return found

    def add_presence(self, record: int, count: int) -> None:
        """``count`` content values at ``record``, of which only the presence is wanted."""
        self.values[min(self.slice_of(record), SLICES - 1)] += count

    def add_text(self, record: int, text: str, count: int) -> None:
        """``count`` content strings with the same analytical text, in the slice of
        ``record``."""
        self._add(record, ("string", text), count)

    def add_native(self, record: int, native_type: str, value: object) -> None:
        """A JSON integer, number or boolean at ``record``."""
        self._add(record, native_key(native_type, value), 1)

    def _add(self, record: int, key: tuple[str, str], count: int) -> None:
        index = min(self.slice_of(record), SLICES - 1)
        self.values[index] += count
        if not self.track:
            return
        held = self.counts.get(key)
        if held is None:
            if len(self.counts) >= self.limit:
                self.overflow = True
                return
            held = self.counts[key] = [0] * SLICES
        held[index] += count

    def result(self, field: FieldResult, records: int) -> PositionDriftResult:
        """The slices and the values, checked against the Scan."""
        if self.overflow:
            raise ScanMismatch("distinct values: the second pass found more than the scan")
        total = sum(self.values)
        if total != field.values.count:
            raise ScanMismatch(f"values: the second pass found {total}, the scan {field.values.count}")
        sizes = [self.bounds[k + 1] - self.bounds[k] for k in range(SLICES)]
        if any(value > size for value, size in zip(self.values, sizes, strict=True)):
            raise ScanMismatch("a slice holds more values than records")
        first_slice: dict[tuple[str, str], int] = {}
        new = [0] * SLICES
        for key, per_slice in self.counts.items():
            index = next(i for i, count in enumerate(per_slice) if count)
            first_slice[key] = index
            new[index] += 1
        slices = [
            DriftSlice(
                first_record=self.bounds[k] + 1,
                records=sizes[k],
                values=self.values[k],
                missing=sizes[k] - self.values[k],
                new_values=new[k] if self.track else None,
            )
            for k in range(SLICES)
        ]
        missing = [slice_.missing for slice_ in slices]
        return PositionDriftResult(
            records=records,
            values=total,
            missing=sum(missing),
            slices=slices,
            missing_association=table_association([self.values, missing]),
            followed=self._followed(field, first_slice) if self.track else None,
        )

    def _followed(self, field: FieldResult, first_slice: dict[tuple[str, str], int]) -> DriftValues:
        frequencies = field.values.frequencies
        if frequencies.status != "complete" or frequencies.value.truncated:
            raise ScanMismatch("the frequencies of the scan are not complete")
        counted = {key: sum(per_slice) for key, per_slice in self.counts.items()}
        listed_by_scan = {(entry.type, entry.value): entry.count for entry in frequencies.value.listed}
        if counted != listed_by_scan:
            raise ScanMismatch("the values and counts are not those the scan listed")
        ordered = sorted(
            self.counts.items(),
            key=lambda item: (-counted[item[0]], item[0][1], TYPE_ORDER[item[0][0]]),
        )
        shown = ordered[: self.max_listed]
        other = [0] * SLICES
        for _, per_slice in ordered[self.max_listed :]:
            for index, count in enumerate(per_slice):
                other[index] += count
        return DriftValues(
            distinct=len(ordered),
            listed=[
                DriftCategory(
                    value=key[1],
                    type=key[0],  # type: ignore[arg-type]
                    count=counted[key],
                    counts=list(per_slice),
                    first_slice=first_slice[key],
                )
                for key, per_slice in shown
            ],
            other=other,
            association=table_association([list(per_slice) for _, per_slice in ordered]),
        )
