# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The table of a sheet: its header row and its data rows (design inspect
``excel.md``, cases B).

Pure functions over the rows that calamine yields, shared by Excel Inspect and
the Excel reader so both find the same table: nothing here opens a file. Rows
and columns are 0-based inside this module; the documents speak 1-based.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import chain, islice

from tabalyst.scanner.readers.excel_common import cell_name, is_blank

# Rows searched, from the first filled row, for the header of a sheet
# (provisional: measured on synthetic workbooks only).
HEADER_SCAN_ROWS = 50


@dataclass(slots=True)
class Facts:
    """What the rows of a sheet say about its table."""

    # Header row (0-based, sheet coordinates), first and last column of the
    # table, last filled row, and the header names between those columns.
    header_row: int
    first_column: int
    last_column: int
    last_row: int
    header: list[str]
    rows: int = 0
    blank_rows: int = 0
    # Header names that repeat an earlier one, and header cells left empty.
    duplicates: int = 0
    blank_headers: int = 0

    @property
    def range(self) -> str:
        return (
            f"{cell_name(self.header_row, self.first_column)}:"
            f"{cell_name(self.last_row, self.last_column)}"
        )


def _is_text(value: object) -> bool:
    return isinstance(value, str) and not is_blank(value)


def find_header(rows: Sequence[Sequence[object]]) -> int | None:
    """Index in ``rows`` of the header row, or ``None``.

    The first row that fills at least half the width (one cell is enough for a
    one-column sheet), holds only text, repeats few names (at least half of its
    values are distinct) and is followed by a filled row.
    """
    width = max((len(row) for row in rows), default=0)
    for index, row in enumerate(rows):
        filled = [value for value in row if not is_blank(value)]
        if not filled or len(filled) * 2 < width:
            continue
        if len(filled) < 2 and width > 1:
            continue
        if not all(_is_text(value) for value in filled):
            continue
        if len({value.strip().lower() for value in filled}) * 2 < len(filled):
            continue
        following = rows[index + 1] if index + 1 < len(rows) else None
        if following is None or all(is_blank(value) for value in following):
            continue
        return index
    return None


def header_cells(row: Sequence[object]) -> tuple[int, int, list[str]]:
    """First and last column of the header of ``row`` and the names between
    them, empty for a blank cell. ``row`` must hold a filled cell."""
    filled = [i for i, value in enumerate(row) if not is_blank(value)]
    low, high = filled[0], filled[-1]
    names = [
        str(value).strip() if not is_blank(value) else ""
        for value in row[low : high + 1]
    ]
    return low, high, names


def analyze_rows(
    rows: Iterator[Sequence[object]], *, first_row: int, first_column: int
) -> Facts | None:
    """Find the table of a sheet from its rows, or ``None`` without a header.

    ``rows`` start at sheet row ``first_row`` and column ``first_column``
    (0-based). Only the first ``HEADER_SCAN_ROWS`` rows are held to find the
    header; the others are counted as they pass.
    """
    head = list(islice(rows, HEADER_SCAN_ROWS))
    found = find_header(head)
    if found is None:
        return None
    low, high, names = header_cells(head[found])
    seen: set[str] = set()
    duplicates = 0
    for name in names:
        if name and name in seen:
            duplicates += 1
        seen.add(name)
    facts = Facts(
        header_row=first_row + found,
        first_column=first_column + low,
        last_column=first_column + high,
        last_row=first_row + found,
        header=names,
        duplicates=duplicates,
        blank_headers=sum(1 for name in names if not name),
    )
    pending_blank = 0
    for offset, data in enumerate(chain(head[found + 1 :], rows), start=found + 1):
        if all(is_blank(value) for value in data[low : high + 1]):
            pending_blank += 1
            continue
        facts.rows += 1
        facts.blank_rows += pending_blank
        pending_blank = 0
        facts.last_row = first_row + offset
    return facts


def merged_in_table(
    merged: Iterable[tuple[tuple[int, int], tuple[int, int]]], facts: Facts
) -> tuple[int, int]:
    """Merged ranges of the table: ``(on the header row, in the data rows)``.

    A range above the header (a title) is not part of the table. A range on
    the header row spanning several columns is a group heading, which makes
    the header more than one row."""
    on_header = 0
    in_data = 0
    for (top, left), (bottom, right) in merged:
        if bottom < facts.header_row or top > facts.last_row:
            continue
        if right < facts.first_column or left > facts.last_column:
            continue
        if top <= facts.header_row <= bottom:
            if right > left:
                on_header += 1
        else:
            in_data += 1
    return on_header, in_data


