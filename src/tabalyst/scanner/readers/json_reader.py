"""Streaming JSON reader with its own path stack (design sections 5.2, 6, 14).

The reader consumes ``ijson`` basic events, which carry no path prefixes: it
tracks canonical segments itself, so ``{"a.b": 1}`` and ``{"a": {"b": 1}}``
never collide. The source is read once, with SHA-256 computed while reading.

Automatic mode: a root array is the collection ``$[]``; a root object or
scalar is the one-record document ``$``, and every array reachable from the
root through keys only, up to ``json.discovery_max_depth``, is promoted to a
collection whose elements are not traversed again in the document. Explicit
mode analyzes only the collections listed in ``json.collections``.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterable, Iterator
from pathlib import Path

import ijson

from tabalyst.errors import InputError
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.observations import (
    DatasetOpened,
    Location,
    NativeType,
    Notice,
    Observation,
    Record,
    RecordExcluded,
    StreamItem,
)
from tabalyst.scanner.paths import (
    ITEMS,
    ROOT,
    FieldPath,
    Key,
    format_absolute,
    parse_path,
)
from tabalyst.scanner.readers.base import HashingStream, SourceSummary

# Replaced in tests to compare the compiled and pure-Python backends.
BACKEND = ijson

DOCUMENT = "$"
UTF8_BOM = b"\xef\xbb\xbf"
_CONTAINERS = frozenset({"start_map", "start_array"})
_ENDS = frozenset({"end_map", "end_array"})
# Exclusion reason: diagnostic code and message, the same for every record.
_EXCLUSIONS = {
    "record_too_large": (
        "record_too_large",
        (
            "Records with more than {limit} observations were excluded. Raise "
            "limits.max_record_observations to analyze them."
        ),
    ),
    "duplicate_key": (
        "json_duplicate_key",
        (
            "Records containing an object with a duplicate key were excluded: "
            "which value applies is ambiguous."
        ),
    ),
}
# Parser failures of both backends; other exceptions are bugs, not bad input.
_PARSE_ERRORS = (ijson.JSONError, json.JSONDecodeError, UnicodeDecodeError)


def _native(event: str, value: object) -> tuple[NativeType, object]:
    if event == "string":
        return "string", value
    if event == "number":
        # ijson reads integers as int and every other number as Decimal.
        return ("integer" if type(value) is int else "number"), value
    if event == "boolean":
        return "boolean", value
    if event == "null":
        return "null", None
    if event == "start_map":
        return "object", None
    return "array", 0


class _RecordBuilder:
    __slots__ = (
        "dataset",
        "depth_truncated",
        "excluded",
        "index",
        "location",
        "observations",
    )

    def __init__(self, dataset: str, index: int, location: Location) -> None:
        self.dataset = dataset
        self.index = index
        self.location = location
        self.observations: list[Observation] = []
        self.depth_truncated = 0
        self.excluded: str | None = None


class _Frame:
    """An open container.

    ``record`` receives the observations of its children, ``rel`` is its path
    in that record. ``collection`` is set instead when each child starts a
    record of that dataset. ``abs`` is kept only where a descendant could be a
    collection. ``owner`` and ``slot`` locate the array observation whose
    length is known at the end of the array.
    """

    __slots__ = (
        "abs",
        "collection",
        "is_map",
        "key",
        "keys",
        "length",
        "owner",
        "record",
        "rel",
        "slot",
        "starts",
    )

    def __init__(
        self,
        is_map: bool,
        *,
        abs: FieldPath | None = None,
        record: _RecordBuilder | None = None,
        rel: FieldPath | None = None,
        collection: str | None = None,
        owner: _RecordBuilder | None = None,
        slot: int = -1,
        starts: _RecordBuilder | None = None,
    ) -> None:
        self.is_map = is_map
        self.abs = abs
        self.record = record
        self.rel = rel
        self.collection = collection
        self.owner = owner
        self.slot = slot
        self.starts = starts
        self.key = ""
        self.keys: set[str] | None = set() if is_map and record is not None else None
        self.length = 0


class JsonReader:
    def __init__(self, path: Path, config: ScanConfig) -> None:
        self.path = path
        self.tolerant = config.errors.policy == "tolerant"
        self.max_depth = config.limits.max_depth
        self.max_observations = config.limits.max_record_observations
        self.discovery_depth = config.json_.discovery_max_depth
        requested = config.json_.collections
        self.auto = requested is None
        # Explicit collections by path, and the paths leading to them.
        self.targets: dict[FieldPath, str] = {}
        self.prefixes: set[FieldPath] = set()
        for text in requested or ():
            path_ = parse_path(text)
            self.targets[path_] = format_absolute(path_)
            self.prefixes.update(path_[:end] for end in range(len(path_)))
        self._found: set[str] = set()
        self._opened: set[str] = set()
        self._counts: dict[str, int] = {}
        self._summary: SourceSummary | None = None

    def summary(self) -> SourceSummary:
        if self._summary is None:
            raise RuntimeError("The JSON source has not been read completely")
        return self._summary

    def __iter__(self) -> Iterator[StreamItem]:
        try:
            raw = self.path.open("rb")
        except OSError as exc:
            raise InputError(f"Cannot read JSON file {self.path}: {exc}") from exc
        stream = HashingStream(raw)
        buffered = io.BufferedReader(stream)
        try:
            # RFC 8259 lets parsers ignore a byte order mark; some Windows
            # tools write one.
            bom = buffered.peek(len(UTF8_BOM))[: len(UTF8_BOM)] == UTF8_BOM
            if bom:
                buffered.read(len(UTF8_BOM))
            events = BACKEND.basic_parse(buffered, use_float=False)
            try:
                yield from self._walk(events)
            except InputError:
                raise
            except OSError as exc:
                raise InputError(f"Cannot read JSON file {self.path}: {exc}") from exc
            except _PARSE_ERRORS as exc:
                if stream.bytes_read == 0:
                    raise InputError(
                        f"{self.path.name} is empty; an empty file is not JSON."
                    ) from exc
                lines = str(exc).strip().splitlines()
                # The compiled backend reports some errors as a bytes repr.
                detail = lines[0].strip().removeprefix("b'") if lines else ""
                detail = detail or type(exc).__name__
                raise InputError(f"Invalid JSON in {self.path.name}: {detail}") from exc
            stream.drain()
        finally:
            buffered.close()
        self._summary = SourceSummary(
            format="json",
            bytes_read=stream.bytes_read,
            sha256=stream.hexdigest(),
            encoding="utf-8-sig" if bom else "utf-8",
        )

    # Datasets and records ------------------------------------------------

    def _open(
        self,
        dataset: str,
        kind,
        collection_path: FieldPath | None,
        container: tuple[str, FieldPath] | None = None,
    ) -> DatasetOpened | None:
        if dataset in self._opened:
            return None
        self._opened.add(dataset)
        self._counts[dataset] = 0
        return DatasetOpened(
            dataset=dataset,
            kind=kind,
            collection_path=collection_path,
            container=container,
        )

    def _new_record(self, dataset: str, element: int | None) -> _RecordBuilder:
        index = self._counts[dataset] = self._counts[dataset] + 1
        return _RecordBuilder(dataset, index, Location(record=index, element=element))

    def _add(self, record: _RecordBuilder, observation: Observation) -> int:
        """Append an observation and return its slot, or -1 when discarded."""
        if record.excluded is not None:
            return -1
        observations = record.observations
        if len(observations) >= self.max_observations:
            self._exclude(record, "record_too_large")
            return -1
        observations.append(observation)
        return len(observations) - 1

    def _exclude(self, record: _RecordBuilder, reason: str, detail: str = "") -> None:
        if record.excluded is not None:
            return
        where = f"Record {record.index} of dataset {record.dataset}"
        if record.location.element is not None:
            where += f" (element {record.location.element})"
        if reason == "record_too_large":
            problem = f"has more than {self.max_observations} observations"
            advice = "Raise limits.max_record_observations"
        else:
            problem = f"contains an object with the duplicate key {detail!r}"
            advice = "Remove the duplicate key"
        if not self.tolerant:
            raise InputError(
                f"{where} {problem}. {advice}, or use the tolerant error policy "
                "to exclude such records."
            )
        record.excluded = reason
        record.observations = []

    def _finish(self, record: _RecordBuilder) -> Record | RecordExcluded:
        if record.excluded is None:
            return Record(
                record.dataset,
                record.index,
                record.location,
                record.observations,
                record.depth_truncated,
            )
        code, message = _EXCLUSIONS[record.excluded]
        return RecordExcluded(
            dataset=record.dataset,
            index=record.index,
            location=record.location,
            reason=record.excluded,
            code=code,
            message=message.format(limit=self.max_observations),
        )

    def _collection(
        self, abs_path: FieldPath
    ) -> tuple[str | None, DatasetOpened | None]:
        """Dataset whose records are the elements of the array at ``abs_path``."""
        path = abs_path + (ITEMS,)
        if self.auto:
            dataset = format_absolute(path)
            container = None if not abs_path else (DOCUMENT, abs_path)
            return dataset, self._open(dataset, "collection", path, container)
        dataset = self.targets.get(path)
        if dataset is not None:
            self._found.add(dataset)
        return dataset, None

    # Event walk --------------------------------------------------------------

    def _walk(self, events: Iterable[tuple[str, object]]) -> Iterator[StreamItem]:
        if not self.auto:
            for path, dataset in self.targets.items():
                yield self._open(dataset, "collection", path)
        max_depth = self.max_depth
        discovery_depth = self.discovery_depth
        stack: list[_Frame] = []
        skip = 0  # depth inside a subtree outside every collection
        truncating = 0  # depth inside a subtree below max_depth
        truncated: _RecordBuilder | None = None

        for event, value in events:
            if skip:
                if event in _CONTAINERS:
                    skip += 1
                elif event in _ENDS:
                    skip -= 1
                continue
            if truncating:
                if event in _CONTAINERS:
                    truncating += 1
                    truncated.depth_truncated += 1
                elif event in _ENDS:
                    truncating -= 1
                elif event != "map_key":
                    truncated.depth_truncated += 1
                continue
            if event == "map_key":
                frame = stack[-1]
                frame.key = value
                seen = frame.keys
                # An excluded record only needs its end: stop remembering keys.
                if seen is not None and frame.record.excluded is None:
                    if value in seen:
                        self._exclude(frame.record, "duplicate_key", value)
                    else:
                        seen.add(value)
                continue
            if event in _ENDS:
                frame = stack.pop()
                owner = frame.owner
                if not frame.is_map and frame.slot >= 0 and owner.excluded is None:
                    observations = owner.observations
                    observations[frame.slot] = Observation(
                        observations[frame.slot].path, "array", frame.length
                    )
                if frame.starts is not None:
                    yield self._finish(frame.starts)
                continue

            # A value starts: find the record it belongs to and its paths.
            is_container = event in _CONTAINERS
            record: _RecordBuilder | None = None
            rel: FieldPath | None = None
            abs_path: FieldPath | None = None
            starts: _RecordBuilder | None = None
            if not stack:
                abs_path = ROOT
                if self.auto and event != "start_array":
                    yield self._open(DOCUMENT, "document", None)
                    record = starts = self._new_record(DOCUMENT, None)
                    rel = ROOT
            else:
                parent = stack[-1]
                if parent.collection is not None:
                    record = starts = self._new_record(parent.collection, parent.length)
                    parent.length += 1
                    rel = ROOT
                else:
                    if parent.is_map:
                        segment = Key(parent.key)
                    else:
                        segment = ITEMS
                        parent.length += 1
                    if parent.abs is not None:
                        abs_path = parent.abs + (segment,)
                    record = parent.record
                    if record is not None:
                        rel = parent.rel + (segment,)
                        if len(rel) > max_depth:
                            record.depth_truncated += 1
                            if is_container:
                                truncating = 1
                                truncated = record
                            continue

            slot = -1
            if record is not None:
                native_type, observed = _native(event, value)
                slot = self._add(record, Observation(rel, native_type, observed))

            if event == "start_array" and abs_path is not None:
                dataset, opened = self._collection(abs_path)
                if opened is not None:
                    yield opened
                if dataset is not None:
                    stack.append(
                        _Frame(
                            False,
                            collection=dataset,
                            owner=record,
                            slot=slot,
                            starts=starts,
                        )
                    )
                    continue

            if is_container:
                is_map = event == "start_map"
                if record is not None:
                    # In automatic mode, only keys up to the discovery depth
                    # can lead to a promoted array.
                    keep_abs = (
                        self.auto
                        and is_map
                        and abs_path is not None
                        and len(abs_path) < discovery_depth
                    )
                    stack.append(
                        _Frame(
                            is_map,
                            abs=abs_path if keep_abs else None,
                            record=record,
                            rel=rel,
                            owner=record,
                            slot=slot,
                            starts=starts,
                        )
                    )
                elif abs_path is not None and abs_path in self.prefixes:
                    stack.append(_Frame(is_map, abs=abs_path))
                else:
                    skip = 1
            elif starts is not None:
                yield self._finish(starts)

        for path, dataset in self.targets.items():
            if dataset not in self._found:
                yield Notice(
                    code="json_collection_not_found",
                    level="warning",
                    message=(
                        f"No array was found at {dataset}; the collection is empty. "
                        "Verify json.collections."
                    ),
                    dataset=dataset,
                )
