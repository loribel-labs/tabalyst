"""Reader protocol and the source description completed while reading."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterator
from dataclasses import dataclass
from typing import BinaryIO, Literal, Protocol

from tabalyst.scanner.observations import StreamItem


@dataclass(frozen=True, slots=True)
class CsvSummary:
    delimiter: str
    header: list[str]


@dataclass(frozen=True, slots=True)
class SourceSummary:
    format: Literal["csv", "json"]
    bytes_read: int
    sha256: str
    encoding: str | None
    csv: CsvSummary | None = None


class Reader(Protocol):
    """Synchronous iterator of stream items for one source."""

    def __iter__(self) -> Iterator[StreamItem]: ...

    def summary(self) -> SourceSummary:
        """Source description, available once iteration is complete."""
        ...


class HashingStream(io.RawIOBase):
    """Binary stream that counts and hashes every byte read through it."""

    def __init__(self, raw: BinaryIO) -> None:
        self._raw = raw
        self._hash = hashlib.sha256()
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        count = self._raw.readinto(buffer)
        if count:
            self._hash.update(memoryview(buffer)[:count])
            self.bytes_read += count
        return count

    def drain(self, chunk_size: int = 1 << 20) -> None:
        """Read the remaining bytes so the digest covers the whole source."""
        while chunk := self._raw.read(chunk_size):
            self._hash.update(chunk)
            self.bytes_read += len(chunk)

    def hexdigest(self) -> str:
        return self._hash.hexdigest()

    def close(self) -> None:
        self._raw.close()
        super().close()
