# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Strict reading of the records of a CSV file, shared by ``sample`` and Dedup (design dedup 4.4)."""

from __future__ import annotations

import codecs
import csv
import hashlib
import io
import os
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Literal, Protocol, TextIO, cast

from tabalyst.config import CsvConfig
from tabalyst.errors import InputError
from tabalyst.scanner.readers.base import HashingStream

CsvErrorKind = Literal["invalid_csv", "encoding_error", "source_unreadable"]


class CsvRecordError(InputError):
    """A CSV file cannot be read as a table of records of one width.

    ``kind`` is the stable class of the problem (the ``reason`` codes of a Dedup
    failure) and ``records_read`` the data records accepted before it. A message
    never holds the content of a cell.
    """

    def __init__(
        self, message: str, *, kind: CsvErrorKind, records_read: int = 0
    ) -> None:
        super().__init__(message)
        self.kind: CsvErrorKind = kind
        self.records_read = records_read


class _Reader(Protocol):
    """The part of ``csv.reader`` that is used."""

    @property
    def line_num(self) -> int: ...

    def __iter__(self) -> Iterator[list[str]]: ...


class CsvRecords:
    """An open CSV: its header and its data records, each of the width of the header.

    Iterating yields the data records once. A multiline cell stays in one record, and a
    blank line is a record of width 0, hence a width error, as in the Scan. The errors
    are ``CsvRecordError``.
    """

    def __init__(
        self,
        path: Path,
        config: CsvConfig,
        reader: _Reader,
        hashing: HashingStream | None,
    ) -> None:
        self._path = path
        self._config = config
        self._reader = reader
        self._hashing = hashing
        self.header: list[str] = []
        self.records_read = 0
        """Data records accepted so far; the record being handled counts."""

    @property
    def line_num(self) -> int:
        """The physical line where the last record read ends."""
        return self._reader.line_num

    @property
    def bytes_read(self) -> int:
        """Bytes read from the file so far; needs ``hash_content`` or ``on_bytes``."""
        return self._counted().bytes_read

    def content_digest(self) -> str:
        """The SHA-256 of the whole file, hexadecimal, available without a second read.

        Reads what remains of the file, so call it once the records are exhausted.
        Needs ``hash_content``.
        """
        hashing = self._counted()
        with self._translating():
            hashing.drain()
        return hashing.hexdigest()

    def _counted(self) -> HashingStream:
        if self._hashing is None:
            raise RuntimeError("the records were opened without hash_content")
        return self._hashing

    def read_header(self) -> None:
        """Read the first record, which is the header."""
        with self._translating():
            header = next(iter(self._reader), None)
        if not header:
            raise CsvRecordError(
                "CSV is empty or has no header on its first record.", kind="invalid_csv"
            )
        self.header = header

    def __iter__(self) -> Iterator[list[str]]:
        width = len(self.header)
        with self._translating():
            for row in self._reader:
                if len(row) != width:
                    raise CsvRecordError(
                        f"Data record {self.records_read + 1} (ending at physical "
                        f"line {self._reader.line_num}): expected {width} fields, "
                        f"found {len(row)}. Verify the delimiter and quoting.",
                        kind="invalid_csv",
                        records_read=self.records_read,
                    )
                self.records_read += 1
                yield row

    @contextmanager
    def _translating(self) -> Iterator[None]:
        try:
            yield
        except csv.Error as exc:
            raise CsvRecordError(
                f"Invalid CSV near physical line {self._reader.line_num}: {exc}",
                kind="invalid_csv",
                records_read=self.records_read,
            ) from exc
        except UnicodeError as exc:
            raise CsvRecordError(
                f"Cannot decode {self._path.name} as {self._config.encoding}. "
                "Specify --encoding.",
                kind="encoding_error",
                records_read=self.records_read,
            ) from exc
        except OSError as exc:
            raise CsvRecordError(
                f"Cannot read CSV file {self._path}: {exc}",
                kind="source_unreadable",
                records_read=self.records_read,
            ) from exc


@contextmanager
def open_records(
    path: Path,
    config: CsvConfig,
    *,
    hash_content: bool = False,
    on_bytes: Callable[[int], None] | None = None,
) -> Iterator[CsvRecords]:
    """Open ``path`` as text (``newline=""``, the configured encoding) and read its header.

    The records are read through ``csv.reader(strict=True)``. With ``hash_content``
    or ``on_bytes`` the bytes pass through a ``HashingStream``, so the SHA-256 of
    the file and the progress in bytes come from the one reading. Raises
    ``CsvRecordError`` when the file cannot be opened, has no header or cannot be
    decoded.
    """
    hashing: HashingStream | None = None
    stream: TextIO
    try:
        if hash_content or on_bytes is not None:
            raw = path.open("rb")
            hashing = HashingStream(raw, on_bytes)
            stream = io.TextIOWrapper(
                io.BufferedReader(hashing), encoding=config.encoding, newline=""
            )
        else:
            stream = path.open("r", encoding=config.encoding, newline="")
    except (OSError, UnicodeError) as exc:
        raise CsvRecordError(
            f"Cannot read CSV file {path}: {exc}", kind="source_unreadable"
        ) from exc
    try:
        reader = csv.reader(stream, delimiter=config.delimiter, strict=True)
        records = CsvRecords(path, config, reader, hashing)
        records.read_header()
        yield records
    finally:
        stream.close()


def output_encoding(source: Path, encoding: str) -> str:
    """The encoding to write beside ``source``: a UTF-8 byte-order mark only if it had one."""

    if codecs.lookup(encoding).name != "utf-8-sig":
        return encoding
    try:
        with source.open("rb") as stream:
            has_bom = stream.read(len(codecs.BOM_UTF8)) == codecs.BOM_UTF8
    except OSError as exc:
        raise CsvRecordError(
            f"Cannot read CSV file {source}: {exc}", kind="source_unreadable"
        ) from exc
    return "utf-8-sig" if has_bom else "utf-8"


class _DigestingSink(io.RawIOBase):
    """Binary sink that counts and hashes the bytes it passes to the file."""

    def __init__(self, raw: BinaryIO) -> None:
        self._raw = raw
        self._hash = hashlib.sha256()
        self.size_bytes = 0

    def writable(self) -> bool:
        return True

    def write(self, data: bytes | bytearray | memoryview, /) -> int:  # type: ignore[override]
        written = self._raw.write(data)
        self._hash.update(memoryview(data)[:written])
        self.size_bytes += written
        return written

    def hexdigest(self) -> str:
        return self._hash.hexdigest()

    def sync(self) -> None:
        self._raw.flush()
        os.fsync(self._raw.fileno())

    def close(self) -> None:
        if not self.closed:
            self._raw.close()
        super().close()


class CsvWriter:
    """An open CSV output with the writing conventions of design dedup 6.4.

    ``write_header`` and ``write_record`` write CRLF-terminated lines with minimal
    quoting; a row with one empty cell is written ``""`` and reads back as that row.
    ``rows_written`` counts the data records, the header excluded. ``size_bytes`` and
    ``sha256`` describe the file once ``open_writer`` has closed it.
    """

    def __init__(self, stream: TextIO, delimiter: str, sink: _DigestingSink) -> None:
        self._writer = csv.writer(stream, delimiter=delimiter, lineterminator="\r\n")
        self._sink = sink
        self.rows_written = 0

    def write_header(self, header: Sequence[str]) -> None:
        """Write the first line of the file, which is not counted as a row."""
        self._writer.writerow(header)

    def write_record(self, row: Sequence[str]) -> None:
        """Write one data record."""
        self._writer.writerow(row)
        self.rows_written += 1

    @property
    def size_bytes(self) -> int:
        """Bytes of the file, final once ``open_writer`` has left its block."""
        return self._sink.size_bytes

    @property
    def sha256(self) -> str:
        """SHA-256 of the file, hexadecimal, final once ``open_writer`` has left its block."""
        return self._sink.hexdigest()


@contextmanager
def open_writer(
    path: Path, config: CsvConfig, encoding: str
) -> Iterator[CsvWriter]:
    """Create ``path`` (it must not exist) as text in ``encoding``, with the delimiter of ``config``.

    On a normal exit the file is flushed and ``fsync``ed, so a crash after it cannot
    leave a short file under a name that is then published. On an exception the
    file is closed as it is and the caller deletes it. ``OSError`` is not translated:
    the caller knows whether it is a temporary or a final file.
    """
    sink = _DigestingSink(path.open("xb"))
    text = io.TextIOWrapper(io.BufferedWriter(cast(io.RawIOBase, sink)), encoding=encoding, newline="")
    try:
        yield CsvWriter(text, config.delimiter, sink)
        text.flush()
        sink.sync()
    finally:
        text.close()
