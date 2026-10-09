# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact set of the original values of a field (design 20.8, EXACT-01 to
EXACT-07).

Equality is the one of the original domain (design 21): the raw string of a CSV
cell, and ``(native type, value)`` for the other types, so ``00123``, ``123``
and the integer 123 are three values. Each value goes to one set, chosen by the
value alone, and the sets hold different kinds of key: nothing is converted
when a value does not fit the compact one, and nothing can be merged.
"""

from __future__ import annotations

from collections.abc import Sequence
from sys import getsizeof

from tabalyst.scanner.planner.costmodel import INT_OBJECT_BYTES
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import DistinctCount, DistinctLimited

# Longest string of digits kept as an integer: below 2**60, an integer object of
# INT_OBJECT_BYTES. The length is the key of its set, so a leading zero keeps
# its place: ``00123`` and ``123`` never meet.
DIGITS_MAX = 18
# Values added between two measures of the memory held: a field read record by
# record (JSON) does not pay a walk of its tables for each value, and the pool
# can be exceeded by at most this many values (a batch of a CSV file is
# measured whole).
MEASURE_STEP = 256

MEMORY_BUDGET = "memory_budget"


class ExactPool:
    """The bytes the exact sets of one run may hold together (MEM-06). The
    sets of a run draw from it as they grow; none lifts it."""

    __slots__ = ("total", "used")

    def __init__(self, total: int) -> None:
        self.total = total
        self.used = 0


class ExactSet:
    """Every distinct original value of a field, exactly, within a pool.

    A string of digits (``DIGITS_MAX`` at most) is an integer in the set of its
    length; any other string is itself in the generic set. JSON integers,
    numbers (their canonical text) and booleans have their own. When the pool
    cannot hold what the sets weigh the field stops being tracked: its sets
    are freed, and the proven distinct values at that moment are a lower
    bound, never the count (D08).
    """

    __slots__ = (
        "booleans",
        "digits",
        "integers",
        "limited",
        "lower_bound",
        "numbers",
        "payload",
        "pending",
        "pool",
        "text",
        "used",
        "values",
    )

    def __init__(self, pool: ExactPool) -> None:
        self.pool = pool
        self.digits: dict[int, set[int]] = {}
        self.text: set[str] = set()
        self.integers: set[int] = set()
        self.numbers: set[str] = set()
        self.booleans: set[bool] = set()
        # Values counted (V), and the bytes of the keys held.
        self.values = 0
        self.payload = 0
        # Bytes charged to the pool, and natives added since the last measure.
        self.used = 0
        self.pending = 0
        self.limited = False
        self.lower_bound = 0

    def distinct(self) -> int:
        """Distinct values held (D); the lower bound once limited."""
        if self.limited:
            return self.lower_bound
        return (
            sum(map(len, self.digits.values()))
            + len(self.text)
            + len(self.integers)
            + len(self.numbers)
            + len(self.booleans)
        )

    def add_strings(self, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Account for the distinct content strings of a batch with their
        counts."""
        if self.limited:
            return
        self.values += sum(counts)
        groups: dict[int, list[str]] = {}
        generic: list[str] = []
        for raw in raws:
            if raw.isascii() and raw.isdigit() and len(raw) <= DIGITS_MAX:
                groups.setdefault(len(raw), []).append(raw)
            else:
                generic.append(raw)
        for length, group in groups.items():
            held = self.digits.setdefault(length, set())
            new = [key for key in map(int, group) if key not in held]
            held.update(new)
            self.payload += INT_OBJECT_BYTES * len(new)
        if generic:
            held_text = self.text
            fresh = [key for key in generic if key not in held_text]
            held_text.update(fresh)
            self.payload += sum(map(getsizeof, fresh))
        self.pending += len(raws)
        if self.pending >= MEASURE_STEP:
            self.measure()

    def add_native(self, native_type: str, value: object) -> None:
        """Account for one JSON integer, number or boolean."""
        if self.limited:
            return
        self.values += 1
        if native_type == "boolean":
            self.booleans.add(bool(value))
            return
        if native_type == "integer":
            number = int(value)  # type: ignore[call-overload]
            if number not in self.integers:
                self.integers.add(number)
                self.payload += getsizeof(number)
        else:
            form = str(value)
            if form not in self.numbers:
                self.numbers.add(form)
                self.payload += getsizeof(form)
        self.pending += 1
        if self.pending >= MEASURE_STEP:
            self.measure()

    def measure(self) -> None:
        """Charge the pool with what the sets hold now, and stop the field if
        the pool cannot hold it. The check follows the insertion, so a batch (at
        most ``MEASURE_STEP`` values, or one batch of a CSV file) and the old
        table that lives beside the new one while a set grows are held beyond
        it for a moment; the firm bound of the plan leaves room for the tables."""
        self.pending = 0
        tables = [getsizeof(held) for held in self.digits.values()]
        tables.extend(getsizeof(held) for held in (self.text, self.integers, self.numbers))
        used = self.payload + sum(tables)
        pool = self.pool
        pool.used += used - self.used
        self.used = used
        if pool.used > pool.total:
            self.stop()

    def stop(self) -> None:
        """Release the sets: the count of a prefix is not the cardinality."""
        self.lower_bound = self.distinct()
        self.limited = True
        self.pool.used -= self.used
        self.used = 0
        self.payload = 0
        self.digits = {}
        self.text = set()
        self.integers = set()
        self.numbers = set()
        self.booleans = set()

    def result(self, expected_values: int, lower_bound: int | None) -> DistinctCount | DistinctLimited:
        """The exact count, checked against the Scan, or what is proven when
        the field was stopped. ``expected_values`` is the Scan's count of values
        and ``lower_bound`` the distinct values it proved, if any."""
        if self.pending and not self.limited:
            self.measure()
        if self.limited:
            return DistinctLimited(values_read=self.values, lower_bound=self.lower_bound)
        if self.values != expected_values:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {expected_values}"
            )
        distinct = self.distinct()
        if lower_bound is not None and distinct < lower_bound:
            raise ScanMismatch(
                f"distinct values: the second pass found {distinct}, "
                f"the scan proved at least {lower_bound}"
            )
        return DistinctCount(
            values=self.values,
            distinct=distinct,
            redundant=self.values - distinct,
            unique=distinct == self.values,
        )
