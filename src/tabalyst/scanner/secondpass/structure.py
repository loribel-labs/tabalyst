# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The lengths of the arrays of a field and the sets of keys of the objects of a
JSON source (design 20.33, lot 18).

Both are counted exactly and checked against the Scan, which counted the same
occurrences: the arrays and their items, the objects and, for each key the Scan
named below an object, the objects that hold it.
"""

from __future__ import annotations

from fractions import Fraction

from tabalyst.scanner.measures import output_number
from tabalyst.scanner.models import FieldResult, LengthCount
from tabalyst.scanner.observations import Record
from tabalyst.scanner.paths import FieldPath
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.bins import exact_quantiles
from tabalyst.scanner.secondpass.models import (
    ArrayProfileResult,
    StructureResult,
    StructureVariant,
)


class ArrayAccumulator:
    """A counter per length of the arrays of one field. A source with more distinct
    lengths than the Scan's range holds cannot be the one it read."""

    __slots__ = ("cell_ns", "counts", "limit", "overflow")

    def __init__(self, limit: int, cell_ns: int = 0) -> None:
        self.limit = limit
        # What the plan expects an array to cost, which weighs the route; no
        # input of the result.
        self.cell_ns = cell_ns
        self.counts: dict[int, int] = {}
        self.overflow = False

    def add(self, length: int) -> None:
        """One array of ``length`` items."""
        counts = self.counts
        found = counts.get(length)
        if found is not None:
            counts[length] = found + 1
        elif len(counts) < self.limit:
            counts[length] = 1
        else:
            # Raised by ``result``, so the failure is a mismatch with the scan.
            self.overflow = True

    def result(self, field: FieldResult) -> ArrayProfileResult:
        """The lengths, checked against the Scan."""
        stats = field.arrays
        counts = self.counts
        if self.overflow:
            raise ScanMismatch("array lengths: the second pass found more than the scan's range")
        if stats is None or not counts:
            raise ScanMismatch("arrays: the scan counted none for the field")
        arrays = sum(counts.values())
        items = sum(length * count for length, count in counts.items())
        for label, found, expected in (
            ("arrays", arrays, stats.count),
            ("empty arrays", counts.get(0, 0), stats.empty),
            ("items", items, stats.total_items),
            ("shortest array", min(counts), stats.min_length),
            ("longest array", max(counts), stats.max_length),
        ):
            if found != expected:
                raise ScanMismatch(f"{label}: the second pass found {found}, the scan {expected}")
        ordered = sorted(counts.items())
        return ArrayProfileResult(
            arrays=arrays,
            empty=counts.get(0, 0),
            items=items,
            min_length=ordered[0][0],
            max_length=ordered[-1][0],
            mean_length=output_number(Fraction(items, arrays)),
            quantiles=exact_quantiles(ordered, arrays),
            length_histogram=[LengthCount(length=length, count=count) for length, count in ordered],
        )


class KeySets:
    """The sets of keys of the objects at one path.

    The keys are the ones the Scan named below the object (``names``, at the
    ``paths`` of the fields), so a set is an integer with a bit per key and a source
    that holds another key cannot be the one the Scan read. A set is tracked from
    its first object, up to ``max_variants`` of them: it is then counted exactly, and
    the objects with a set beyond the limit are only summed up.
    """

    __slots__ = (
        "active",
        "cell_ns",
        "key_counts",
        "mask",
        "max_variants",
        "names",
        "objects",
        "paths",
        "untracked",
        "variants",
    )

    def __init__(
        self,
        names: list[str],
        paths: list[FieldPath],
        max_variants: int,
        cell_ns: int = 0,
    ) -> None:
        self.names = names
        self.paths = paths
        self.max_variants = max_variants
        # What the plan expects an object to cost: no input of the result.
        self.cell_ns = cell_ns
        self.key_counts = [0] * len(names)
        self.variants: dict[int, int] = {}
        self.objects = 0
        self.untracked = 0
        self.mask = 0
        self.active = False

    def begin(self) -> None:
        """An object starts: the one before it ends."""
        if self.active:
            self.end()
        self.active = True
        self.mask = 0

    def end(self) -> None:
        """The open object is complete: count its set of keys."""
        if not self.active:
            return
        self.active = False
        self.objects += 1
        variants = self.variants
        mask = self.mask
        found = variants.get(mask)
        if found is not None:
            variants[mask] = found + 1
        elif len(variants) < self.max_variants:
            variants[mask] = 1
        else:
            self.untracked += 1

    def result(
        self, expected: int, children: list[FieldResult], max_listed: int, max_keys: int
    ) -> StructureResult:
        """The sets, checked against the Scan: ``expected`` objects, and for every
        key it named the objects that hold it (the parents of ``children`` that
        have them)."""
        self.end()
        if self.objects != expected:
            raise ScanMismatch(
                f"objects: the second pass found {self.objects}, the scan {expected}"
            )
        for found, child in zip(self.key_counts, children, strict=True):
            if found != child.presence.present:
                raise ScanMismatch(
                    f"objects with a key: the second pass found {found}, "
                    f"the scan {child.presence.present}"
                )
        total = len(self.names)
        ordered = sorted(self.variants.items(), key=lambda item: -item[1])
        listed = [
            StructureVariant(
                count=count,
                keys=mask.bit_count(),
                absent=[
                    self.names[index] for index in range(min(total, max_keys)) if not mask >> index & 1
                ],
                absent_total=total - mask.bit_count(),
            )
            for mask, count in ordered[:max_listed]
        ]
        return StructureResult(
            objects=self.objects,
            keys=total,
            always=sum(1 for count in self.key_counts if count == self.objects),
            key_names=self.names[:max_keys],
            key_names_truncated=total > max_keys,
            distinct=len(ordered),
            complete=not self.untracked,
            untracked=self.untracked,
            listed=listed,
            other_objects=sum(count for _, count in ordered[max_listed:]),
        )


class StructureAccumulator:
    """The sets of keys of every object path of a dataset, from one sweep of each
    record: an object starts at its own observation, and the observations of its
    keys follow it in document order, before the next object of the same path."""

    __slots__ = ("events", "failure", "records", "roots", "trackers", "values")

    def __init__(self) -> None:
        self.events: dict[FieldPath, tuple[KeySets | None, list[tuple[KeySets, int, int]]]] = {}
        self.roots: list[KeySets] = []
        self.trackers: list[KeySets] = []
        self.failure: str | None = None
        self.records = 0
        # Observations met, for the cells counted by the run.
        self.values = 0

    def track(self, path: FieldPath | None, sets: KeySets) -> None:
        """Count the sets of keys of the objects at ``path``; ``None`` is the root
        of the records, which the Scan holds as no field."""
        self.trackers.append(sets)
        if path is None:
            self.roots.append(sets)
        else:
            _, marks = self.events.get(path, (None, []))
            self.events[path] = (sets, marks)
        for index, child in enumerate(sets.paths):
            start, marks = self.events.get(child, (None, []))
            marks.append((sets, index, 1 << index))
            self.events[child] = (start, marks)

    def add_record(self, record: Record) -> None:
        """One record of the dataset."""
        self.records += 1
        for sets in self.roots:
            sets.begin()
        events = self.events
        self.values += len(record.observations)
        for observation in record.observations:
            found = events.get(observation.path)
            if found is None:
                continue
            start, marks = found
            if start is not None and observation.type == "object":
                start.begin()
            for sets, index, bit in marks:
                # Inlined ``KeySets.mark``: it runs for every key of every object.
                sets.mask |= bit
                sets.key_counts[index] += 1
        for sets in self.trackers:
            sets.end()
