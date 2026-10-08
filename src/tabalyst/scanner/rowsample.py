# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Row sample of a dataset: first rows, a bottom-k of the interior, last rows
(design 18.11).

One pass, in the scan process. The first ``edge`` records are kept; the latest
``edge`` records wait in a buffer, and a record that leaves the buffer becomes a
candidate of the middle, a bottom-k by a priority that depends on its position
only, so two identical rows are two observations (ROW-05). At the end the
buffer is the end of the dataset. The rows are projected once, with the cells of
every field of the same row (ROW-06).
"""

from __future__ import annotations

import hashlib
import struct
from collections import deque
from collections.abc import Callable
from heapq import heappop, heappush, heappushpop
from typing import TypeAlias

from tabalyst.scanner.config import RowSampleSettings
from tabalyst.scanner.exposure import mask
from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.models import (
    RowOrigin,
    RowPopulation,
    RowSample,
    RowSizes,
    SampleHash,
    SampleRow,
)
from tabalyst.scanner.observations import Record
from tabalyst.scanner.paths import FieldPath

ROW_HASH_ALGORITHM = "blake2b"
# Version of the priority function: any change of the function, of the seed or
# of the position encoding raises it.
ROW_HASH_VERSION = 1
ROW_HASH_BITS = 64
_PERSON = b"tabalyst.rows.v1"
_BLOCK_SHIFT = 3
_BLOCK_SIZE = 1 << _BLOCK_SHIFT
_UNPACK = struct.Struct("<8Q").unpack

# Modelled bytes (design 18.11), checked against ``tracemalloc`` by a test: a row
# of a table is a list of strings; a record is a dictionary of lists of tuples.
TABLE_ROW_BYTES = 200
TABLE_CELL_BYTES = 60
RECORD_BYTES = 250
RECORD_PATH_BYTES = 200
RECORD_VALUE_BYTES = 120

CONTAINER_TYPES = frozenset({"object", "array"})
MEMORY_BUDGET = "memory_budget"

Cells: TypeAlias = dict[FieldPath, list[tuple[str, str | None]]]
# index, cells (a list of strings for a table row, a dictionary for a record),
# the cut cells (column positions or paths) and the modelled bytes.
Stored: TypeAlias = tuple[int, object, object, int]


class RowPriority:
    """Priority of a position in ``[0, 2**64)``, smaller is better.

    BLAKE2b with a 512-bit digest of the seed and the block of eight positions
    gives the eight priorities of the block: one hash call for eight rows
    (benchmarks.md, lot 3b). It depends only on the seed and the position.
    """

    __slots__ = ("_block", "_copy", "_values")

    def __init__(self, seed: int) -> None:
        if not 0 <= seed < 1 << 64:
            raise ValueError(f"seed must be in [0, 2**64), got {seed}")
        self._copy = hashlib.blake2b(
            seed.to_bytes(8, "little"), digest_size=64, person=_PERSON
        ).copy
        self._block = -1
        self._values: tuple[int, ...] = ()

    def _hash(self, block: int) -> tuple[int, ...]:
        state = self._copy()
        state.update(block.to_bytes(8, "little"))
        return _UNPACK(state.digest())

    def at(self, index: int) -> int:
        """Priority of one position, keeping the block of the last one."""
        block = index >> _BLOCK_SHIFT
        if block != self._block:
            self._values = self._hash(block)
            self._block = block
        return self._values[index & (_BLOCK_SIZE - 1)]

    def range(self, first: int, stop: int) -> list[int]:
        """Priorities of the positions ``first`` to ``stop - 1``, in order: one
        hash call per block of eight positions."""
        if stop <= first:
            return []
        values: list[int] = []
        extend = values.extend
        for block in range(first >> _BLOCK_SHIFT, ((stop - 1) >> _BLOCK_SHIFT) + 1):
            extend(self._hash(block))
        low = first & (_BLOCK_SIZE - 1)
        return values[low : low + stop - first]


class RowBudget:
    """Modelled bytes of the rows kept by the datasets of a scan, first come
    first served (design 18.11)."""

    __slots__ = ("limit", "used")

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.used = 0


def expose_cells(
    observed: Cells,
    ids: dict[FieldPath, str],
    exposures: dict[FieldPath, str | None],
    is_content: Callable[[str], bool],
) -> dict[str, list[str | None] | None]:
    """Cells of the listed fields, through their exposure (design 12.8). Nulls
    and strings that are not content are shown as read; a hidden value hides its
    whole cell."""
    cells: dict[str, list[str | None] | None] = {}
    for path, values in observed.items():
        field_id = ids.get(path)
        if field_id is None:
            continue
        exposure = exposures.get(path)
        if exposure in (None, "show"):
            cells[field_id] = [text for _, text in values]
            continue
        texts: list[str | None] | None = []
        for native, text in values:
            if text is None or (native == "string" and not is_content(text)):
                texts.append(text)
            elif exposure == "mask":
                texts.append(mask(text))
            else:
                texts = None
                break
        cells[field_id] = texts
    return cells


class RowSampler:
    """The row sample of one dataset, collected while it is read.

    ``declared`` are the paths of a table whose rows come as lists of strings
    (``add_batch``); any record can come through ``add_record``.
    """

    __slots__ = (
        "_budget",
        "_buffer",
        "_cell_chars",
        "_cut_by_budget",
        "_declared",
        "_finalized",
        "_head",
        "_middle",
        "_priority",
        "_start",
        "_start_closed",
        "edge",
        "k",
        "requested",
        "seed",
        "seen",
        "settings",
    )

    def __init__(
        self,
        settings: RowSampleSettings,
        seed: int,
        budget: RowBudget,
        declared: tuple[FieldPath, ...] = (),
    ) -> None:
        self.settings = settings
        self.seed = seed
        self.edge = settings.edge
        self.requested = settings.rows - 2 * settings.edge
        # The size of the middle in force: it only shrinks.
        self.k = self.requested
        self._cell_chars = settings.cell_chars
        self._budget = budget
        self._declared = declared
        self._priority = RowPriority(seed)
        self.seen = 0
        # Records assigned to the start, kept or not.
        self._head = 0
        self._start: list[Stored] = []
        self._start_closed = False
        self._buffer: deque[tuple[int, object]] = deque()
        # A min-heap of (-priority, -index, ...): the root is the worst row.
        self._middle: list[tuple[int, int, object, object, int]] = []
        self._cut_by_budget = False
        self._finalized = False

    # Reading ------------------------------------------------------------------

    def add_record(self, record: Record) -> None:
        """Take one record, in reading order. The record is kept by reference
        until it is projected: readers never reuse their observations."""
        self.seen += 1
        if self._head < self.edge:
            self._head += 1
            self._store_start(record.index, record)
            return
        if not self.edge:
            self._offer(record.index, record)
            return
        buffer = self._buffer
        buffer.append((record.index, record))
        if len(buffer) > self.edge:
            self._offer(*buffer.popleft())

    def add_batch(self, start: int, rows: list[list[str]]) -> None:
        """Rows with consecutive indices from ``start``: the same sample as
        ``add_record`` for each of them, whatever the batches are."""
        count = len(rows)
        if not count:
            return
        self.seen += count
        take = min(count, self.edge - self._head)
        if take > 0:
            for offset in range(take):
                self._store_start(start + offset, rows[offset])
            self._head += take
            start += take
            rows = rows[take:]
        buffer = self._buffer
        total = len(buffer) + len(rows)
        evict = max(0, total - self.edge)
        from_buffer = min(evict, len(buffer))
        for _ in range(from_buffer):
            self._offer(*buffer.popleft())
        evicted = evict - from_buffer
        if evicted:
            self._offer_range(start, rows, evicted)
        buffer.extend((start + offset, rows[offset]) for offset in range(evicted, len(rows)))

    def _offer_range(self, start: int, rows: list[list[str]], count: int) -> None:
        """Candidates of the middle: ``rows[:count]``, with the indices from
        ``start``."""
        if not self.k:
            return
        priorities = self._priority.range(start, start + count)
        middle = self._middle
        position = 0
        while position < count and len(middle) < self.k:
            self._admit(priorities[position], start + position, rows[position])
            position += 1
        if position == count or not middle or len(middle) < self.k:
            return
        limit = -middle[0][0]
        for offset in [
            offset
            for offset in range(position, count)
            if priorities[offset] <= limit
        ]:
            self._admit(priorities[offset], start + offset, rows[offset])

    def _offer(self, index: int, row: object) -> None:
        if self.k:
            self._admit(self._priority.at(index), index, row)

    def _admit(self, priority: int, index: int, row: object) -> None:
        middle = self._middle
        if len(middle) >= self.k:
            worst = middle[0]
            if (priority, index) >= (-worst[0], -worst[1]):
                return
        cells, cut, size = self._project(row)
        entry = (-priority, -index, cells, cut, size)
        budget = self._budget
        if len(middle) < self.k:
            heappush(middle, entry)
            budget.used += size
        else:
            budget.used += size - heappushpop(middle, entry)[4]
        self._fit()

    def _fit(self) -> None:
        """Give up the worst rows of the middle while the budget is exceeded."""
        budget = self._budget
        while budget.used > budget.limit and self._middle:
            self._give_up_worst()

    def _give_up_worst(self) -> None:
        """Drop the worst row of the middle; the size in force can only shrink."""
        self._budget.used -= heappop(self._middle)[4]
        self.k = len(self._middle)
        self._cut_by_budget = True

    def _store_start(self, index: int, row: object) -> None:
        if self._start_closed:
            return
        cells, cut, size = self._project(row)
        budget = self._budget
        if budget.used + size > budget.limit:
            self._start_closed = True
            self._cut_by_budget = True
            return
        budget.used += size
        self._start.append((index, cells, cut, size))

    # Projection ---------------------------------------------------------------

    def _project(self, row: object) -> tuple[object, object, int]:
        if type(row) is list:
            return self._project_row(row)
        return self._project_record(row)  # type: ignore[arg-type]

    def _project_row(self, row: list[str]) -> tuple[list[str], tuple[int, ...], int]:
        cap = self._cell_chars
        cut: tuple[int, ...] = ()
        if row and max(map(len, row)) > cap:
            cut = tuple(position for position, cell in enumerate(row) if len(cell) > cap)
            row = [cell[:cap] for cell in row]
        return row, cut, TABLE_ROW_BYTES + TABLE_CELL_BYTES * len(row) + sum(map(len, row))

    def _project_record(self, record: Record) -> tuple[Cells, frozenset[FieldPath], int]:
        """The scalar observations of a record, as canonical text per path. The
        values of a path are cut together at ``cell_chars`` characters."""
        cap = self._cell_chars
        cells: Cells = {}
        spent: dict[FieldPath, int] = {}
        cut: set[FieldPath] = set()
        size = RECORD_BYTES
        for observation in record.observations:
            native = observation.type
            if native in CONTAINER_TYPES:
                continue
            path = observation.path
            used = spent.get(path, 0)
            if native == "null":
                text = None
            else:
                text = (
                    observation.value
                    if native == "string"
                    else canonical_text(native, observation.value)
                )
                # A value without characters costs nothing of the cell budget.
                if text and used >= cap:
                    cut.add(path)
                    continue
                if len(text) > cap - used:
                    text = text[: cap - used]
                    cut.add(path)
                spent[path] = used + len(text)
                size += len(text)
            values = cells.get(path)
            if values is None:
                values = cells[path] = []
                size += RECORD_PATH_BYTES
            values.append((native, text))
            size += RECORD_VALUE_BYTES
        return cells, frozenset(cut), size

    # Result -------------------------------------------------------------------

    def finalize(
        self,
        ids: dict[FieldPath, str],
        exposures: dict[FieldPath, str | None],
        scalar_ids: list[str],
        fields_limited: bool,
        is_content: Callable[[str], bool],
    ) -> RowSample:
        """The sample, with its end projected: the buffer, newest first, while
        the byte budget allows (the middle gives up rows to make room).
        Exposure applies here. The end is charged to the budget now, so with
        several datasets the order of their finalization is part of the result
        (deterministic: the order of the datasets). Call it once."""
        if self._finalized:
            raise RuntimeError("The row sample was already finalized")
        self._finalized = True
        budget = self._budget
        end: list[Stored] = []
        for index, row in reversed(self._buffer):
            cells, cut, size = self._project(row)
            while budget.used + size > budget.limit and self._middle:
                self._give_up_worst()
            if budget.used + size > budget.limit:
                self._cut_by_budget = True
                break
            budget.used += size
            end.append((index, cells, cut, size))
        end.reverse()

        edge = self.edge
        seen = self.seen
        interior = max(0, seen - 2 * edge)
        middle = sorted(self._middle, key=lambda entry: -entry[1])
        # The start rows whose position is among the last ``edge`` also belong
        # to the end (ROW-04): a record is stored once with both labels.
        end_from = seen - edge
        built: list[SampleRow] = []
        truncated_cells = 0
        paths = self._declared
        for number, (index, cells, cut, _) in enumerate(self._start, start=1):
            origins: list[RowOrigin] = ["start", "end"] if number > end_from else ["start"]
            truncated_cells += self._append(
                built, index, cells, cut, origins, paths, ids, exposures, is_content
            )
        for entry in middle:
            truncated_cells += self._append(
                built, -entry[1], entry[2], entry[3], ["middle"], paths, ids, exposures, is_content
            )
        for index, cells, cut, _ in end:
            truncated_cells += self._append(
                built, index, cells, cut, ["end"], paths, ids, exposures, is_content
            )
        rows_bytes = (
            sum(item[3] for item in self._start)
            + sum(entry[4] for entry in self._middle)
            + sum(item[3] for item in end)
        )
        threshold = None
        if interior > len(self._middle) and self._middle:
            threshold = f"{-self._middle[0][0]:016x}"
        # Rows are stored once; none is lost when every record is a row.
        stored = len(self._start) + len(self._middle) + len(end)
        return RowSample(
            selection="start_middle_end",
            hash=SampleHash(
                algorithm=ROW_HASH_ALGORITHM,
                version=ROW_HASH_VERSION,
                bits=ROW_HASH_BITS,
                seed=self.seed,
            ),
            requested=RowSizes(
                rows=self.settings.rows, edge=edge, middle=self.requested
            ),
            middle_k=self.k,
            reason=MEMORY_BUDGET if self._cut_by_budget else None,
            population=RowPopulation(
                records=seen, interior=interior, scope="interior_rows"
            ),
            complete=stored == seen,
            threshold=threshold,
            fields=scalar_ids,
            fields_limited=fields_limited,
            cell_chars=self._cell_chars,
            truncated_cells=truncated_cells,
            bytes=rows_bytes,
            max_bytes=budget.limit,
            kept=len(built),
            of=len(built),
            rows=built,
        )

    def _append(
        self,
        built: list[SampleRow],
        index: int,
        cells: object,
        cut: object,
        origins: list[RowOrigin],
        paths: tuple[FieldPath, ...],
        ids: dict[FieldPath, str],
        exposures: dict[FieldPath, str | None],
        is_content: Callable[[str], bool],
    ) -> int:
        """Add a row to ``built`` and return the number of cells it cut."""
        if type(cells) is list:
            observed: Cells = {
                path: [("string", cell)] for path, cell in zip(paths, cells, strict=True)
            }
            cut_paths = [paths[position] for position in cut]  # type: ignore[attr-defined]
        else:
            observed = cells  # type: ignore[assignment]
            cut_paths = sorted(cut, key=lambda path: ids.get(path, ""))  # type: ignore[call-overload]
        built.append(
            SampleRow(
                record=index,
                origins=origins,
                values=expose_cells(observed, ids, exposures, is_content),
                truncated=[ids[path] for path in cut_paths if path in ids],
            )
        )
        return len(cut_paths)
