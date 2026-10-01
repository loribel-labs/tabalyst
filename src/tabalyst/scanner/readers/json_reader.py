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

import decimal
import io
import json
import re
import sys
from collections.abc import Callable, Iterable, Iterator
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
# ``InvalidOperation``: a number whose exponent ``Decimal`` cannot represent.
_PARSE_ERRORS = (
    ijson.JSONError,
    json.JSONDecodeError,
    UnicodeDecodeError,
    decimal.InvalidOperation,
)
_SURROGATE = re.compile(r"[\ud800-\udfff]")
# Child paths kept by ``_Paths``; a larger cache is cleared, so it stays small.
MAX_PATHS = 65_536
_MAX_DETAIL = 200
# Every digit becomes "0" and every other byte "x": a digit run is then a run
# of "0", found by a substring search at memory speed.
_DIGIT_MASK = bytes(0x30 if 0x30 <= byte <= 0x39 else 0x78 for byte in range(256))


def _has_long_digit_run(path: Path) -> bool:
    """Whether the file holds more consecutive digits than Python converts.

    The compiled backend crashes the process (segmentation fault) on an
    integer above ``sys.int_max_str_digits`` digits in some parser states;
    such files are parsed by the pure-Python backend, which reports a parse
    error instead. Digit runs inside strings also match: they only cost the
    slower backend. Runs spanning read chunks are included.
    """
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        return False
    needle = b"0" * (limit + 1)
    tail = b""
    with path.open("rb") as raw:
        while chunk := raw.read(1 << 20):
            # The tail is already masked; masking is idempotent.
            data = (tail + chunk).translate(_DIGIT_MASK)
            if needle in data:
                return True
            tail = data[len(data.rstrip(b"0")) :]
    return False


def _reject_surrogates(
    events: Iterable[tuple[str, object]],
) -> Iterator[tuple[str, object]]:
    """Reject strings holding a lone surrogate escape, such as ``"\\ud800"``.

    Such a string is not valid Unicode and cannot be written as UTF-8 (I-JSON,
    RFC 7493). The pure-Python backend keeps the surrogate; the compiled
    backend already rejects lone low surrogates, but replaces a lone high
    surrogate with ``?`` before Tabalyst sees it.
    """
    for event, value in events:
        if (
            (event == "string" or event == "map_key")
            and not value.isascii()
            and _SURROGATE.search(value)
        ):
            raise ijson.JSONError("a string contains a lone surrogate escape")
        yield event, value


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


class _Paths:
    """Child paths already built, by parent path and key, so that every
    occurrence of one path shares one path object: the engine and record
    digests look paths up by identity first, and a new path would hash each
    of its segments."""

    __slots__ = ("_children",)

    def __init__(self) -> None:
        self._children: dict[tuple[int, str | None], tuple] = {}

    def child(self, parent: FieldPath, key: str | None) -> FieldPath:
        """``parent`` followed by the key ``key``, or by items when ``None``."""
        children = self._children
        entry = children.get((id(parent), key))
        # The entry keeps its parent alive, so the identity cannot be reused.
        if entry is not None and entry[0] is parent:
            return entry[1]
        if len(children) >= MAX_PATHS:
            children.clear()
        path = parent + (ITEMS if key is None else Key(key),)
        children[(id(parent), key)] = (parent, path)
        return path


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
    def __init__(
        self,
        path: Path,
        config: ScanConfig,
        on_bytes: Callable[[int], None] | None = None,
    ) -> None:
        self.path = path
        self.on_bytes = on_bytes
        self.tolerant = config.errors.policy == "tolerant"
        self.max_depth = config.limits.max_depth
        self.max_observations = config.limits.max_record_observations
        self.discovery_depth = config.json_.discovery_max_depth
        limit = config.json_.flatten.depth_limit()
        self.flatten_limit = sys.maxsize if limit is None else limit
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
        backend = BACKEND
        try:
            if backend.backend_name == "yajl2_c" and _has_long_digit_run(self.path):
                backend = ijson.get_backend("python")
            raw = self.path.open("rb")
        except OSError as exc:
            raise InputError(f"Cannot read JSON file {self.path}: {exc}") from exc
        stream = HashingStream(raw, self.on_bytes)
        buffered = io.BufferedReader(stream)
        try:
            # RFC 8259 lets parsers ignore a byte order mark; some Windows
            # tools write one.
            bom = buffered.peek(len(UTF8_BOM))[: len(UTF8_BOM)] == UTF8_BOM
            if bom:
                buffered.read(len(UTF8_BOM))
            events = backend.basic_parse(buffered, use_float=False)
            if backend.backend_name != "yajl2_c":
                events = _reject_surrogates(events)
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
                if isinstance(exc, decimal.InvalidOperation):
                    detail = "a number has an exponent out of range"
                detail = detail or type(exc).__name__
                # Parser messages may quote a whole token, such as a long number.
                if len(detail) > _MAX_DETAIL:
                    detail = detail[:_MAX_DETAIL] + "..."
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
        flatten_limit = self.flatten_limit
        discovery_depth = self.discovery_depth
        child = _Paths().child
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
                        key = parent.key
                    else:
                        key = None
                        parent.length += 1
                    if parent.abs is not None:
                        abs_path = child(parent.abs, key)
                    record = parent.record
                    if record is not None:
                        rel = child(parent.rel, key)
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
                # In automatic mode, only keys up to the discovery depth can
                # lead to a promoted array.
                keep_abs = (
                    self.auto
                    and is_map
                    and abs_path is not None
                    and len(abs_path) < discovery_depth
                )
                if record is not None:
                    # At the flatten limit the container is kept whole: its
                    # children are not observed, and not counted as lost. The
                    # frame has no record, only the array length is tracked.
                    whole = len(rel) >= flatten_limit
                    stack.append(
                        _Frame(
                            is_map,
                            abs=abs_path if keep_abs else None,
                            record=None if whole else record,
                            rel=rel,
                            owner=record,
                            slot=slot,
                            starts=starts,
                        )
                    )
                elif abs_path is not None and (keep_abs or abs_path in self.prefixes):
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
