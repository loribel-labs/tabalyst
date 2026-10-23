# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The exact row store that starts in memory and moves to disk past the memory budget."""

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tabalyst.dedup.diskstore import SqliteRowStore
from tabalyst.dedup.store import (
    ENTRY_OVERHEAD,
    ExactRowStore,
    MemoryRowStore,
    Occurrence,
)

# Bytes of the database per distinct key beyond the length of the key: the cell header,
# the packed count and position, and the unused part of the pages (design dedup 8.5).
DISK_ENTRY_OVERHEAD = 24

# Margin over the entries already held, since the database never fills its pages.
DISK_FILL_FACTOR = 1.25


@dataclass(frozen=True)
class SpillEvent:
    """The store has just moved from memory to disk (design dedup 8.5).

    ``records`` is the number of records observed, the one that tipped the budget
    included; the progress reads "memory budget reached at record N".
    """

    records: int
    distinct: int
    accounted_bytes: int
    budget_bytes: int


def estimate_disk_bytes(key_bytes: int, entries: int) -> int:
    """Size the database will have for ``entries`` keys of ``key_bytes`` bytes in all."""
    return int((key_bytes + entries * DISK_ENTRY_OVERHEAD) * DISK_FILL_FACTOR)


class TieredRowStore:
    """A ``MemoryRowStore`` until its accounted bytes pass the budget, then SQLite.

    The switch is decided on the accounted bytes only (design dedup 8.3), so the
    same file and budget choose the same mode on any machine. The entries are
    copied whole into the database before the dictionary is dropped: no group is
    lost, and a failure of the copy raises with the temporary files already deleted.
    ``on_spill`` receives a ``SpillEvent`` once the copy is done.
    """

    def __init__(
        self,
        budget_bytes: int,
        temp_dir: Path | None = None,
        *,
        on_spill: Callable[[SpillEvent], None] | None = None,
        digest: Callable[[bytes], int] | None = None,
    ) -> None:
        self._budget = budget_bytes
        self._directory = Path(tempfile.gettempdir()) if temp_dir is None else temp_dir
        self._on_spill = on_spill
        self._digest = digest
        self._memory: MemoryRowStore | None = MemoryRowStore()
        self._disk: SqliteRowStore | None = None
        self._active: ExactRowStore = self._memory

    @property
    def storage_mode(self) -> str:
        """``"memory"`` until the switch, ``"disk"`` after it."""
        return self._active.storage_mode

    @property
    def budget_bytes(self) -> int:
        """The accounted bytes that the memory table may hold."""
        return self._budget

    def observe(self, key: bytes, position: int) -> Occurrence:
        """Count one more record with ``key``, switching to disk when the budget is passed."""
        occurrence = self._active.observe(key, position)
        memory = self._memory
        if (
            memory is not None
            and occurrence.count == 1
            and memory.accounted_bytes > self._budget
        ):
            self._spill(position + 1)
        return occurrence

    def _spill(self, records: int) -> None:
        memory = self._memory
        assert memory is not None
        accounted = memory.accounted_bytes
        entries = len(memory)
        reserve = estimate_disk_bytes(accounted - entries * ENTRY_OVERHEAD, entries)
        disk = SqliteRowStore(self._directory, digest=self._digest, reserve_bytes=reserve)
        try:
            disk.load(memory.sorted_items())
        except BaseException:
            disk.close()
            raise
        memory.close()
        # The dictionary is gone: the page cache can take the memory budget.
        disk.set_cache_bytes(self._budget)
        self._memory = None
        self._disk = disk
        self._active = disk
        if self._on_spill is not None:
            self._on_spill(SpillEvent(records, entries, accounted, self._budget))

    def close(self) -> None:
        """Release the memory and delete the temporary database, whatever the state."""
        if self._memory is not None:
            self._memory.close()
        if self._disk is not None:
            self._disk.close()
