# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The reader of a source, chosen by its format: shared by the first and the
second pass, which must read a source the same way (PASS2-02)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.identity import source_format_of
from tabalyst.scanner.readers.base import Reader
from tabalyst.scanner.readers.csv_reader import CsvReader
from tabalyst.scanner.readers.excel_reader import ExcelReader
from tabalyst.scanner.readers.json_reader import JsonReader
from tabalyst.scanner.readers.jsonl_reader import JsonlReader


def open_reader(
    path: Path, config: ScanConfig, on_bytes: Callable[[int], None] | None
) -> Reader:
    """A reader of ``path`` for the format its extension gives."""
    source_format = source_format_of(path)
    if source_format == "json":
        return JsonReader(path, config, on_bytes)
    if source_format == "jsonl":
        return JsonlReader(path, config, on_bytes)
    if source_format == "excel":
        return ExcelReader(path, config, on_bytes)
    return CsvReader(path, config, on_bytes)
