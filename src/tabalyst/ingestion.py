"""Validate CSV structure before asking pandas to load the raw strings."""

import csv
import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from tabalyst.config import CsvConfig
from tabalyst.models import SourceInfo


class CsvInputError(ValueError):
    pass


@dataclass
class CsvDataset:
    frame: pd.DataFrame
    headers: list[str]
    source: SourceInfo


def read_csv(path: Path, config: CsvConfig) -> CsvDataset:
    raw = path.read_bytes()
    try:
        content = raw.decode(config.encoding)
    except UnicodeError as exc:
        raise CsvInputError(
            f"Cannot decode {path.name} as {config.encoding}. Specify --encoding."
        ) from exc
    if "\0" in content:
        raise CsvInputError("CSV contains NUL characters; verify the file encoding.")

    reader = csv.reader(
        io.StringIO(content, newline=""), delimiter=config.delimiter, strict=True
    )
    row_count = 0
    try:
        headers = next(reader, None)
        if not headers:
            raise CsvInputError("CSV is empty or has no header on its first record.")
        for row_count, row in enumerate(reader, start=1):
            if len(row) != len(headers):
                raise CsvInputError(
                    f"Data record {row_count} (ending at physical line {reader.line_num}): "
                    f"expected {len(headers)} fields, found {len(row)}. "
                    "Verify the delimiter and quoting. No rows were skipped."
                )
    except csv.Error as exc:
        raise CsvInputError(
            f"Invalid CSV near physical line {reader.line_num}: {exc}"
        ) from exc

    # Internal IDs preserve duplicate/blank headers without pandas renaming them.
    ids = [f"column_{position}" for position in range(1, len(headers) + 1)]
    frame = pd.read_csv(
        io.StringIO(content, newline=""),
        sep=config.delimiter,
        engine="python",
        header=0,
        names=ids,
        dtype=str,
        na_filter=False,
        keep_default_na=False,
        skip_blank_lines=False,
        on_bad_lines="error",
    )
    if len(frame) != row_count:
        raise CsvInputError(
            "CSV record count changed during parsing; analysis was stopped."
        )
    return CsvDataset(
        frame=frame,
        headers=headers,
        source=SourceInfo(
            filename=path.name,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            encoding=config.encoding,
            delimiter=config.delimiter,
        ),
    )
