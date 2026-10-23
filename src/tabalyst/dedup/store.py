# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact row store: its interface and its in-memory realization."""

from collections.abc import Iterator
from typing import NamedTuple, NoReturn, Protocol

from tabalyst.dedup.failures import DedupReportError

# Bytes accounted per distinct row on top of the length of its key (design dedup 8.3).
# Measured in lot 2 (design 8.3): the key object header, the dictionary slot, the
# index table at the worst moment of its growth and the packed count and position.
ENTRY_OVERHEAD = 160

# One integer per entry holds the position of the first record above the count of
# occurrences. A count cannot reach 2**40 without a file of terabytes.
_COUNT_BITS = 40
_COUNT_MASK = (1 << _COUNT_BITS) - 1


class Occurrence(NamedTuple):
    """What a store knows of a key after observing one more record."""

    # The name is the one of the contract (design dedup 8.1); it hides ``tuple.count``,
    # which nothing here calls.
    count: int  # type: ignore[assignment]
    """Occurrences of the key so far, this one included."""
    first_position: int
    """0-based index of the first record that had the key."""


class ExactRowStore(Protocol):
    """Counts the occurrences of whole row keys, exactly (design dedup 8.1)."""

    @property
    def storage_mode(self) -> str:
        """``"memory"`` or ``"disk"``."""
        ...

    def observe(self, key: bytes, position: int) -> Occurrence:
        """Add one record with ``key`` at ``position`` and return its occurrence."""
        ...

    def close(self) -> None:
        """Release memory and delete temporary files; the store is unusable afterwards."""
        ...


class _ClosedEntries(dict[bytes, int]):
    """Replaces the table of a closed store so that a late use fails instead of lying."""

    def get(self, key: object, default: object = None) -> int:  # type: ignore[override]
        raise RuntimeError("the row store is closed")

    def items(self) -> NoReturn:
        raise RuntimeError("the row store is closed")

    def __len__(self) -> int:
        raise RuntimeError("the row store is closed")


class MemoryRowStore:
    """Dictionary of whole keys: exact by construction, since equality compares the key.

    ``accounted_bytes`` is the deterministic size that the memory budget bounds; it is
    not the real memory of the process.
    """

    storage_mode = "memory"

    def __init__(self) -> None:
        self._entries: dict[bytes, int] = {}
        self._accounted = 0

    def __len__(self) -> int:
        """Number of distinct keys."""
        return len(self._entries)

    @property
    def accounted_bytes(self) -> int:
        """Sum of ``len(key) + ENTRY_OVERHEAD`` over the distinct keys."""
        return self._accounted

    def observe(self, key: bytes, position: int) -> Occurrence:
        """Insert ``key`` with count 1 at ``position``, or count one more occurrence."""
        entries = self._entries
        packed = entries.get(key)
        if packed is None:
            entries[key] = (position << _COUNT_BITS) | 1
            self._accounted += len(key) + ENTRY_OVERHEAD
            return Occurrence(1, position)
        if packed & _COUNT_MASK == _COUNT_MASK:
            # Past this count the carry would corrupt the first position.
            raise DedupReportError(
                "Internal error: a row occurs more often than the store can count.",
                reason="unexpected_error",
            )
        packed += 1
        entries[key] = packed
        return Occurrence(packed & _COUNT_MASK, packed >> _COUNT_BITS)

    def items(self) -> Iterator[tuple[bytes, Occurrence]]:
        """Every entry, for the migration to the disk store (ADR exact store, 4)."""
        for key, packed in self._entries.items():
            yield key, Occurrence(packed & _COUNT_MASK, packed >> _COUNT_BITS)

    def sorted_items(self) -> Iterator[tuple[bytes, Occurrence]]:
        """Every entry in key order: the migration inserts in B-tree order.

        Random-order inserts into the disk table cost three times more once it is
        larger than its page cache (measured in lot 3). The sorted list of keys is
        eight bytes per entry, which the budget does not count.
        """
        entries = self._entries
        for key in sorted(entries):
            packed = entries[key]
            yield key, Occurrence(packed & _COUNT_MASK, packed >> _COUNT_BITS)

    def close(self) -> None:
        """Forget every entry; any later use raises ``RuntimeError``."""
        self._entries = _ClosedEntries()
        self._accounted = 0
