"""Items that readers stream to the engine (design section 6).

A reader yields ``DatasetOpened`` before the records of a dataset, then one
``Record`` or ``RecordExcluded`` per record, materialized one at a time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tabalyst.scanner.paths import FieldPath

NativeType = Literal[
    "null", "boolean", "integer", "number", "string", "object", "array"
]
NATIVE_TYPES: tuple[NativeType, ...] = (
    "null",
    "boolean",
    "integer",
    "number",
    "string",
    "object",
    "array",
)
DatasetKind = Literal["table", "document", "collection"]


@dataclass(frozen=True, slots=True)
class Location:
    """Where a record comes from: CSV physical line or JSON element index."""

    record: int
    line: int | None = None
    element: int | None = None

    def to_dict(self) -> dict[str, int]:
        location = {"record": self.record}
        if self.line is not None:
            location["line"] = self.line
        if self.element is not None:
            location["element"] = self.element
        return location


@dataclass(frozen=True, slots=True)
class DeclaredField:
    """A field known before any record, with its source label (CSV columns)."""

    path: FieldPath
    name: str
    display: str


@dataclass(frozen=True, slots=True)
class DatasetOpened:
    """A dataset starts; its records follow, possibly interleaved with others.

    ``container`` names the dataset and field path whose arrays hold the
    records of this collection, when that field is itself analyzed (an array
    promoted from a JSON document).
    """

    dataset: str
    kind: DatasetKind
    collection_path: FieldPath | None
    fields: tuple[DeclaredField, ...] = ()
    container: tuple[str, FieldPath] | None = None


@dataclass(frozen=True, slots=True)
class Observation:
    path: FieldPath
    type: NativeType
    value: object


@dataclass(slots=True)
class Record:
    """One analyzed record. ``depth_truncated`` counts the observations below
    ``limits.max_depth`` that the reader did not emit."""

    dataset: str
    index: int
    location: Location
    observations: list[Observation]
    depth_truncated: int = 0


@dataclass(frozen=True, slots=True)
class RecordExcluded:
    """A record left out of the analysis under the tolerant policy.

    ``code`` and ``message`` describe the diagnostic in the reader's terms, so
    the engine never tests the source format.
    """

    dataset: str
    index: int
    location: Location
    reason: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class Notice:
    """A technical event described by the reader, forwarded as a diagnostic."""

    code: str
    level: Literal["error", "warning"]
    message: str
    dataset: str | None = None
    location: Location | None = None


StreamItem = DatasetOpened | Record | RecordExcluded | Notice
