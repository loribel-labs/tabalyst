# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Opening a workbook with calamine, shared by Excel Inspect and the Excel
reader (design inspect excel.md, lot X-1 measurements).

Calamine reads a whole sheet into memory when it is asked for (about 0.9 byte
per byte of uncompressed sheet XML, 45 bytes per cell), so the size of a sheet
is checked from the zip directory before it is read, one sheet at a time.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from xml.etree import ElementTree

from python_calamine import (
    CalamineError,
    CalamineWorkbook,
    PasswordError,
    load_workbook,
)

from tabalyst.errors import InputError

EXCEL_SUFFIXES = (".xlsx", ".xlsm")
# Spreadsheet formats that Tabalyst recognizes and does not read.
UNSUPPORTED_SPREADSHEET_SUFFIXES = (".xls", ".xlsb", ".ods")

# Largest uncompressed sheet XML read: about 0.9 GB of memory (excel.md, X-1).
MAX_SHEET_XML_BYTES = 1 << 30
# Workbook description parts are small; a larger one is not read.
_MAX_PART_BYTES = 16 << 20

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RELATIONSHIPS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PACKAGE_RELATIONSHIPS = (
    "{http://schemas.openxmlformats.org/package/2006/relationships}"
)


def read_workbook_bytes(
    path: Path, on_bytes: Callable[[int], None] | None = None
) -> tuple[bytes, str]:
    """The bytes of the workbook and their SHA-256, read once.

    Everything that follows (the zip directory, calamine) works on these bytes,
    so the hash is that of the content that was parsed, even if the file is
    saved again meanwhile. ``on_bytes`` gets the running count.
    """
    digest = hashlib.sha256()
    chunks = []
    read = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1 << 20):
                digest.update(chunk)
                chunks.append(chunk)
                read += len(chunk)
                if on_bytes is not None:
                    on_bytes(read)
    except OSError as exc:
        raise InputError(f"Cannot read Excel file {path}: {exc}") from exc
    return b"".join(chunks), digest.hexdigest()


def open_workbook(data: bytes, name: str) -> CalamineWorkbook:
    """Open a workbook, given its bytes, lazily and with its named tables.

    Raises ``InputError`` for a protected, corrupt or unreadable workbook.
    """
    try:
        return load_workbook(io.BytesIO(data), load_tables=True)
    except PasswordError as exc:
        raise InputError(f"{name} is password protected; Tabalyst cannot read it.") from exc
    except (CalamineError, OSError, zipfile.BadZipFile, ValueError) as exc:
        raise InputError(f"Cannot read workbook {name}: {exc}") from exc


@contextmanager
def calamine_errors(name: str) -> Iterator[None]:
    """Report what calamine raises while a sheet or table is read as an
    ``InputError``, as ``open_workbook`` does for the whole file."""
    try:
        yield
    except PasswordError as exc:
        raise InputError(f"{name} is password protected; Tabalyst cannot read it.") from exc
    except (CalamineError, zipfile.BadZipFile) as exc:
        raise InputError(f"Cannot read workbook {name}: {exc}") from exc


def sheet_xml_sizes(data: bytes) -> dict[str, int]:
    """Uncompressed size of the XML part of each sheet, by sheet name.

    Read from the zip directory, nothing is decompressed but the two small
    parts that name the sheets. A workbook whose parts cannot be matched gives
    an empty result: the check is then skipped and calamine reports the problem.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            workbook = _small_part(archive, "xl/workbook.xml")
            relationships = _small_part(archive, "xl/_rels/workbook.xml.rels")
            if workbook is None or relationships is None:
                return {}
            targets = {
                item.get("Id"): item.get("Target", "")
                for item in ElementTree.fromstring(relationships).iter(
                    f"{_PACKAGE_RELATIONSHIPS}Relationship"
                )
            }
            sizes: dict[str, int] = {}
            for sheet in ElementTree.fromstring(workbook).iter(f"{_MAIN}sheet"):
                target = targets.get(sheet.get(f"{_RELATIONSHIPS}id"))
                if not target or sheet.get("name") is None:
                    continue
                part = target.lstrip("/")
                part = part if part.startswith("xl/") else f"xl/{part}"
                try:
                    sizes[sheet.get("name", "")] = archive.getinfo(part).file_size
                except KeyError:
                    continue
            return sizes
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError):
        return {}


def _small_part(archive: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        if archive.getinfo(name).file_size > _MAX_PART_BYTES:
            return None
        return archive.read(name)
    except KeyError:
        return None


def check_sheet_size(name: str, sheet: str, sizes: dict[str, int]) -> None:
    """Refuse a sheet too large to be read into memory."""
    size = sizes.get(sheet)
    if size is not None and size > MAX_SHEET_XML_BYTES:
        raise InputError(
            f"Sheet {sheet!r} of {name} is too large to read: its content "
            f"is {size / (1 << 20):,.0f} MiB uncompressed, the limit is "
            f"{MAX_SHEET_XML_BYTES >> 20:,} MiB."
        )


def column_letters(index: int) -> str:
    """Spreadsheet letters of a 0-based column index (0 is ``A``)."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def cell_name(row: int, column: int) -> str:
    """A1 notation of a 0-based row and column."""
    return f"{column_letters(column)}{row + 1}"


def is_blank(value: object) -> bool:
    """Whether a cell value is empty: calamine gives ``""`` for an empty cell,
    and a whitespace-only string is as empty to a reader of a table."""
    return value is None or (isinstance(value, str) and not value.strip())

