# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Excel reader: one sheet or named table of a workbook, with typed values
(design inspect ``excel.md``, lot X-3).

The table is the one ``excel.dataset_path`` names. Each filled data row becomes
an object whose members are column segments, as for CSV, so presence rules and
the report are shared; the values keep their Excel type (lot X-1, X-6). Calamine
reads the sheet into memory (``check_sheet_size`` bounds it) and the file is
hashed in a pass of its own, so the identity covers every byte.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from itertools import chain, islice
from pathlib import Path

from python_calamine import (
    CalamineError,
    TableNotFound,
    WorksheetNotFound,
)

from tabalyst.errors import ConfigurationError, InputError
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.observations import (
    DatasetOpened,
    DeclaredField,
    Location,
    Observation,
    Record,
    StreamItem,
)
from tabalyst.scanner.paths import ROOT, Column, Key, column_labels, parse_path
from tabalyst.scanner.readers.base import ExcelSummary, SourceSummary
from tabalyst.scanner.readers.excel_common import (
    cell_name,
    check_sheet_size,
    is_blank,
    open_workbook,
    read_workbook_bytes,
    sheet_xml_sizes,
)
from tabalyst.scanner.readers.excel_table import (
    HEADER_SCAN_ROWS,
    find_header,
    header_cells,
)

DATASET = "rows"
# Integers that a float holds exactly.
_EXACT = 2**53


class ExcelReader:
    def __init__(
        self,
        path: Path,
        config: ScanConfig,
        on_bytes: Callable[[int], None] | None = None,
    ) -> None:
        self.path = path
        self.on_bytes = on_bytes
        self.dataset_path = config.excel.dataset_path
        self.header_row = config.excel.header_row
        self.max_observations = config.limits.max_record_observations
        self._summary: SourceSummary | None = None
        self._last_row = 0

    def summary(self) -> SourceSummary:
        if self._summary is None:
            raise RuntimeError("The Excel source has not been read completely")
        return self._summary

    def __iter__(self) -> Iterator[StreamItem]:
        if self.dataset_path is None:
            raise ConfigurationError(
                f"{self.path.name} is a workbook: set excel.dataset_path, in a "
                "configuration file or the Inspect file, or pass --collection. "
                f"`tabalyst inspect {self.path.name}` lists the tables."
            )
        # One read: the hash is that of the bytes parsed below.
        data, sha256 = read_workbook_bytes(self.path, self.on_bytes)
        size = len(data)
        names = [
            segment.name
            for segment in parse_path(self.dataset_path)
            if isinstance(segment, Key)
        ]
        sheet = names[0]
        table = names[1] if len(names) == 2 else None
        header, rows, place = self._table(data, sheet, table)
        yield from self._records(header, rows, place.header_row)
        last_row = place.last_row if place.last_row is not None else self._last_row
        self._summary = SourceSummary(
            format="excel",
            bytes_read=size,
            sha256=sha256,
            encoding=None,
            excel=ExcelSummary(
                dataset_path=self.dataset_path,
                sheet=sheet,
                table=table,
                range=(
                    f"{cell_name(place.header_row - 1, place.left)}:"
                    f"{cell_name(last_row, place.right)}"
                ),
                header_row=place.header_row,
                header=header,
            ),
        )

    def _table(
        self, data: bytes, sheet: str, table: str | None
    ) -> tuple[list[str], Iterator[Sequence[object]], _Place]:
        """The header, the data rows (lazily) and the place of the table. Sheet
        content is read here, one sheet only."""
        sizes = sheet_xml_sizes(data)
        check_sheet_size(self.path.name, sheet, sizes)
        workbook = open_workbook(data, self.path.name)
        if sheet not in workbook.sheet_names:
            raise ConfigurationError(
                f"The sheet {sheet!r} is not in {self.path.name}. Its sheets: "
                + ", ".join(repr(name) for name in workbook.sheet_names)
                + ". Inspect the workbook again to list its tables."
            )
        try:
            if table is not None:
                return self._named_table(workbook, sheet, table)
            return self._sheet_table(workbook, sheet)
        except (TableNotFound, WorksheetNotFound) as exc:
            raise ConfigurationError(
                f"The table {self.dataset_path} is not in {self.path.name}."
            ) from exc
        except CalamineError as exc:
            raise InputError(f"Cannot read workbook {self.path.name}: {exc}") from exc

    def _named_table(self, workbook, sheet: str, table: str):
        found = workbook.get_table_by_name(table)
        if found.sheet != sheet:
            raise ConfigurationError(
                f"The table {table!r} is on the sheet {found.sheet!r} of "
                f"{self.path.name}, not on {sheet!r}."
            )
        header = [str(name) for name in found.columns]
        top, left = found.start
        place = _Place(header_row=top, left=left, right=found.end[1], last_row=found.end[0])
        return header, iter(found.to_python()), place

    def _sheet_table(self, workbook, sheet: str):
        data = workbook.get_sheet_by_name(sheet)
        if data.start is None:
            raise InputError(f"The sheet {sheet!r} of {self.path.name} is empty.")
        first_row, first_column = data.start
        rows = islice(data.iter_rows(), first_row, None)
        override = self.header_row
        wanted = HEADER_SCAN_ROWS if override is None else max(
            HEADER_SCAN_ROWS, override - first_row + 1
        )
        head = list(islice(rows, wanted))
        if override is None:
            found = find_header(head)
        else:
            found = override - 1 - first_row
            if not 0 <= found < len(head) or all(is_blank(v) for v in head[found]):
                raise ConfigurationError(
                    f"excel.header_row is {override}, but row {override} of "
                    f"sheet {sheet!r} is empty or outside its content."
                )
        if found is None:
            raise InputError(
                f"No header row was found in the first {HEADER_SCAN_ROWS} rows of "
                f"sheet {sheet!r} of {self.path.name}. Set excel.header_row "
                "(config.structure.header_row in the Inspect file)."
            )
        low, high, header = header_cells(head[found])
        columns = slice(low, high + 1)
        body = (row[columns] for row in chain(head[found + 1 :], rows))
        # The last row is the last filled one, known once the rows are read.
        place = _Place(
            header_row=first_row + found + 1,
            left=first_column + low,
            right=first_column + high,
            last_row=None,
        )
        return header, body, place

    def _records(
        self, header: list[str], rows: Iterator[Sequence[object]], header_row: int
    ) -> Iterator[StreamItem]:
        width = len(header)
        if width == 0:
            raise InputError(f"The table {self.dataset_path} has no column.")
        # Each record observes its root and every column.
        if width + 1 > self.max_observations:
            raise InputError(
                f"The table has {width} columns, so each record has {width + 1} "
                "observations, above limits.max_record_observations "
                f"({self.max_observations})."
            )
        paths = [(Column(position),) for position in range(1, width + 1)]
        yield DatasetOpened(
            dataset=DATASET,
            kind="table",
            collection_path=None,
            fields=tuple(
                DeclaredField(path=path, name=name, display=label)
                for path, name, label in zip(
                    paths, header, column_labels(header), strict=True
                )
            ),
        )
        root = Observation(ROOT, "object", None)
        index = 0
        # 0-based index of the last filled row; the header row when none.
        self._last_row = header_row - 1
        for offset, row in enumerate(rows):
            if all(is_blank(value) for value in row):
                continue
            index += 1
            observations = [root]
            for path, value in zip(paths, row, strict=True):
                observations.append(Observation(path, *_typed(value)))
            sheet_row = header_row + offset + 1
            self._last_row = sheet_row - 1
            yield Record(
                DATASET,
                index,
                Location(record=index, line=sheet_row),
                observations,
            )


@dataclass(frozen=True, slots=True)
class _Place:
    """Where the table is: 1-based header row, 0-based first and last column,
    and the 0-based last row when the definition gives it (a named table)."""

    header_row: int
    left: int
    right: int
    last_row: int | None


def _typed(value: object) -> tuple[str, object]:
    """Native type and value of a cell (lot X-1, decision X-6)."""
    if isinstance(value, bool):
        return "boolean", value
    if isinstance(value, float):
        if not math.isfinite(value):
            return "string", str(value)
        if value.is_integer() and abs(value) <= _EXACT:
            return "integer", int(value)
        return "number", Decimal(repr(value))
    if isinstance(value, int):
        return "integer", value
    if isinstance(value, dt.datetime):
        return "string", value.isoformat(sep=" ")
    if isinstance(value, dt.date | dt.time):
        return "string", value.isoformat()
    if isinstance(value, dt.timedelta):
        return "string", str(value)
    return "string", value if isinstance(value, str) else str(value)
