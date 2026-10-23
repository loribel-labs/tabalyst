# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Counters of the duplicate groups, the marks of the records and the exact count of rows."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from tabalyst.dedup.failures import DedupInputError, DedupReportError
from tabalyst.dedup.identity import canonical_key
from tabalyst.dedup.store import ExactRowStore, MemoryRowStore

# Bit arrays grow by this many bytes at a time (512 Ki records), so that the growth
# stays cheap and a file of 10 million records holds about 2.5 MB of marks.
_CHUNK = 1 << 16


@dataclass(frozen=True)
class GroupStats:
    """The quantities of design dedup 12.2, under the names of the report's ``records``."""

    total: int
    distinct: int
    singletons: int
    duplicate_groups: int
    groups_occurring_twice: int
    groups_occurring_three_plus: int
    extra_copies: int
    duplicate_group_occurrences: int
    max_occurrences: int

    @property
    def extra_copy_percent(self) -> float:
        """``100 * extra_copies / total``, ``0`` for a file without records."""
        return 100 * self.extra_copies / self.total if self.total else 0.0

    def violations(self) -> list[str]:
        """The invariants of design dedup 12.3 that do not hold, as readable lines.

        The invariants about the outputs are checked where the outputs exist.
        """
        broken: list[str] = []

        def need(holds: bool, rule: str) -> None:
            if not holds:
                broken.append(rule)

        need(self.total == self.distinct + self.extra_copies, "total = distinct + extra_copies")
        need(
            self.distinct == self.singletons + self.duplicate_groups,
            "distinct = singletons + duplicate_groups",
        )
        need(
            self.duplicate_group_occurrences == self.duplicate_groups + self.extra_copies,
            "duplicate_group_occurrences = duplicate_groups + extra_copies",
        )
        need(
            self.duplicate_groups
            == self.groups_occurring_twice + self.groups_occurring_three_plus,
            "duplicate_groups = groups_occurring_twice + groups_occurring_three_plus",
        )
        need(
            0 <= self.singletons <= self.distinct <= self.total,
            "0 <= singletons <= distinct <= total",
        )
        need(
            (self.max_occurrences == 0) == (self.total == 0),
            "max_occurrences = 0 if and only if total = 0",
        )
        need(
            (self.duplicate_groups == 0) == (self.max_occurrences <= 1),
            "duplicate_groups = 0 if and only if max_occurrences <= 1",
        )
        need(
            (self.groups_occurring_three_plus > 0) == (self.max_occurrences >= 3),
            "groups_occurring_three_plus > 0 if and only if max_occurrences >= 3",
        )
        return broken

    def check(self) -> None:
        """Raise ``DedupReportError`` (``unexpected_error``) when an invariant is broken.

        A broken invariant is an internal error: such counts are never published.
        """
        broken = self.violations()
        if broken:
            raise DedupReportError(
                "Internal error: the counts of the rows are inconsistent ("
                + "; ".join(broken)
                + ").",
                reason="unexpected_error",
                records_read=self.total,
            )


class RecordMarks:
    """Two bit arrays that fix the content of the outputs without the store (design 8.4).

    ``is_extra(i)`` tells that record ``i`` is an extra copy of an earlier row;
    ``is_group_first(i)`` that it is the first record of a row that occurs at least
    twice. An index that was never marked reads as ``False``.
    """

    def __init__(self) -> None:
        self._extra = bytearray()
        self._group_first = bytearray()

    @property
    def nbytes(self) -> int:
        """Bytes held by the two arrays."""
        return len(self._extra) + len(self._group_first)

    def is_extra(self, position: int) -> bool:
        """Whether record ``position`` is an extra copy of an earlier row."""
        return _get(self._extra, position)

    def is_group_first(self, position: int) -> bool:
        """Whether record ``position`` is the first of a row that occurs at least twice."""
        return _get(self._group_first, position)

    def mark_extra(self, position: int) -> None:
        """Flag record ``position`` as an extra copy, growing the array when needed."""
        _set(self._extra, position)

    def mark_group_first(self, position: int) -> None:
        """Flag record ``position`` as the first of a repeated row, growing when needed."""
        _set(self._group_first, position)

    def extra_total(self) -> int:
        """Number of records marked as extra copies."""
        return int.from_bytes(self._extra, "little").bit_count()

    def group_first_total(self) -> int:
        """Number of records marked as the first of a repeated row."""
        return int.from_bytes(self._group_first, "little").bit_count()

    def trim(self, total: int) -> None:
        """Drop the room kept beyond ``total`` records."""
        size = (total + 7) // 8
        del self._extra[size:]
        del self._group_first[size:]


def _get(bits: bytearray, position: int) -> bool:
    index = position >> 3
    return index < len(bits) and bool(bits[index] >> (position & 7) & 1)


def _set(bits: bytearray, position: int) -> None:
    index = position >> 3
    if index >= len(bits):
        bits.extend(bytes(max(_CHUNK, index + 1 - len(bits))))
    bits[index] |= 1 << (position & 7)


class GroupCounters:
    """Counts the groups from the count of each record, without a pass over the store.

    ``update`` takes the count that ``ExactRowStore.observe`` returned (design 8.2).
    """

    def __init__(self) -> None:
        self._total = 0
        self._distinct = 0
        self._twice = 0
        self._three_plus = 0
        self._max = 0

    def update(self, count: int) -> None:
        """Take in one record whose key now has ``count`` occurrences.

        Call it once per record, in order: each count follows the previous one of
        the same key by exactly one.
        """
        self._total += 1
        if count == 1:
            self._distinct += 1
        elif count == 2:
            self._twice += 1
        elif count == 3:
            self._twice -= 1
            self._three_plus += 1
        self._max = max(self._max, count)

    def stats(self) -> GroupStats:
        """The quantities so far; ``singletons`` and the occurrences of the groups derive."""
        groups = self._twice + self._three_plus
        extra = self._total - self._distinct
        return GroupStats(
            total=self._total,
            distinct=self._distinct,
            singletons=self._distinct - groups,
            duplicate_groups=groups,
            groups_occurring_twice=self._twice,
            groups_occurring_three_plus=self._three_plus,
            extra_copies=extra,
            duplicate_group_occurrences=groups + extra,
            max_occurrences=self._max,
        )


@dataclass(frozen=True)
class GroupResult:
    """The exact counts of a sequence of rows and the marks that fix its outputs."""

    stats: GroupStats
    marks: RecordMarks


def count_rows(
    rows: Iterable[Sequence[str]],
    store: ExactRowStore | None = None,
    *,
    max_rows: int | None = None,
) -> GroupResult:
    """Count the duplicate groups of ``rows`` exactly and mark their records.

    Rows are compared by their canonical key, whole and without normalization. A
    ``MemoryRowStore`` is used and closed when no ``store`` is given; a store passed
    in stays open, since its owner decides when to release it.

    Raises ``DedupInputError`` (``row_limit_exceeded``) at record number
    ``max_rows + 1``, and ``DedupReportError`` if the counts break an invariant.
    """
    owned = store is None
    active: ExactRowStore = MemoryRowStore() if store is None else store
    counters = GroupCounters()
    marks = RecordMarks()
    try:
        for position, row in enumerate(rows):
            if max_rows is not None and position >= max_rows:
                raise DedupInputError(
                    f"The file has more than {max_rows:,} data records.",
                    reason="row_limit_exceeded",
                    records_read=position + 1,
                    limit=max_rows,
                )
            count, first = active.observe(canonical_key(row), position)
            counters.update(count)
            if count > 1:
                marks.mark_extra(position)
                if count == 2:
                    marks.mark_group_first(first)
    finally:
        if owned:
            active.close()
    stats = counters.stats()
    stats.check()
    if (
        marks.extra_total() != stats.extra_copies
        or marks.group_first_total() != stats.duplicate_groups
    ):
        raise DedupReportError(
            "Internal error: the marks of the records disagree with the counts.",
            reason="unexpected_error",
            records_read=stats.total,
        )
    marks.trim(stats.total)
    return GroupResult(stats, marks)
