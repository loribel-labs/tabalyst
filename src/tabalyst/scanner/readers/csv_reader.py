"""Streaming CSV reader with SHA-256 computed while reading (design sections 5.1, 6, 14).

The first record is the header. Each data record becomes an object whose
members are column segments, so presence rules are shared with JSON.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from pathlib import Path

from tabalyst.errors import InputError
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.observations import (
    DatasetOpened,
    DeclaredField,
    Location,
    Observation,
    Record,
    RecordExcluded,
    StreamItem,
)
from tabalyst.scanner.paths import ROOT, Column, column_labels
from tabalyst.scanner.readers.base import CsvSummary, HashingStream, SourceSummary

DATASET = "rows"


class CsvReader:
    def __init__(self, path: Path, config: ScanConfig) -> None:
        self.path = path
        self.encoding = config.csv.encoding
        self.delimiter = config.csv.delimiter
        self.tolerant = config.errors.policy == "tolerant"
        self._summary: SourceSummary | None = None

    def summary(self) -> SourceSummary:
        if self._summary is None:
            raise RuntimeError("The CSV source has not been read completely")
        return self._summary

    def __iter__(self) -> Iterator[StreamItem]:
        try:
            raw = self.path.open("rb")
        except OSError as exc:
            raise InputError(f"Cannot read CSV file {self.path}: {exc}") from exc
        stream = HashingStream(raw)
        text = io.TextIOWrapper(
            io.BufferedReader(stream), encoding=self.encoding, newline=""
        )
        reader = csv.reader(_lines(text), delimiter=self.delimiter, strict=True)
        try:
            try:
                header = next(reader, None)
                if not header:
                    raise InputError(
                        "CSV is empty or has no header on its first record."
                    )
                yield from self._records(reader, header)
            except csv.Error as exc:
                raise InputError(
                    f"Invalid CSV near physical line {reader.line_num}: {exc}"
                ) from exc
            except UnicodeError as exc:
                raise InputError(
                    f"Cannot decode {self.path.name} as {self.encoding}. "
                    "Specify the CSV encoding."
                ) from exc
            except OSError as exc:
                raise InputError(f"Cannot read CSV file {self.path}: {exc}") from exc
            stream.drain()
        finally:
            text.close()
        self._summary = SourceSummary(
            format="csv",
            bytes_read=stream.bytes_read,
            sha256=stream.hexdigest(),
            encoding=self.encoding,
            csv=CsvSummary(delimiter=self.delimiter, header=header),
        )

    def _records(self, reader, header: list[str]) -> Iterator[StreamItem]:
        width = len(header)
        paths = [(Column(position),) for position in range(1, width + 1)]
        yield DatasetOpened(
            dataset=DATASET,
            kind="table",
            collection_path=None,
            fields=tuple(
                DeclaredField(path=path, name=name, display=display)
                for path, name, display in zip(
                    paths, header, column_labels(header), strict=True
                )
            ),
        )
        record_observation = Observation(ROOT, "object", None)
        excluded_message = (
            f"Records with a number of fields other than {width} were excluded. "
            "Verify the delimiter and quoting."
        )
        index = 0
        while True:
            line = reader.line_num + 1
            row = next(reader, None)
            if row is None:
                return
            index += 1
            location = Location(record=index, line=line)
            if len(row) != width:
                if not self.tolerant:
                    raise InputError(
                        f"Data record {index} (starting at physical line {line}): "
                        f"expected {width} fields, found {len(row)}. "
                        "Verify the delimiter and quoting, or use the tolerant "
                        "error policy to exclude such records."
                    )
                yield RecordExcluded(
                    dataset=DATASET,
                    index=index,
                    location=location,
                    reason="width_mismatch",
                    code="csv_width_mismatch",
                    message=excluded_message,
                )
                continue
            observations = [record_observation]
            observations.extend(
                Observation(path, "string", value)
                for path, value in zip(paths, row, strict=True)
            )
            yield Record(DATASET, index, location, observations)


def _lines(text: Iterable[str]) -> Iterator[str]:
    for number, line in enumerate(text, start=1):
        if "\0" in line:
            raise InputError(
                f"CSV contains NUL characters near physical line {number}; "
                "verify the file encoding."
            )
        yield line
