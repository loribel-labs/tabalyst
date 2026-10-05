# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSONL / NDJSON reader (design inspect section 9).

A source is one dataset ``$[]`` whose records are its object lines. Lines are
split on ``\\n`` only; each one is parsed on its own with the standard ``json``
module and walked into the same observations as an element of a JSON array, so
both formats read a record alike. An excluded line is counted and located by
its physical line number. The source is read once, with SHA-256 computed
while reading.
"""

from __future__ import annotations

import decimal
import io
import json
import re
import sys
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

from tabalyst.errors import InputError
from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.observations import (
    DatasetOpened,
    Location,
    NativeType,
    Observation,
    Record,
    RecordExcluded,
    StreamItem,
)
from tabalyst.scanner.paths import ITEMS, ROOT, FieldPath
from tabalyst.scanner.readers.base import HashingStream, SourceSummary
from tabalyst.scanner.readers.json_common import SURROGATE, Paths

DATASET = "$[]"
UTF8_BOM = b"\xef\xbb\xbf"
# JSON whitespace: a line holding only these is blank.
_BLANK = b" \t\r\n"
# An escape of a surrogate code point; a hit only costs a scan of the line.
_SURROGATE_ESCAPE = re.compile(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}")
# Bytes skipped at a time inside a line above the size limit.
_SKIP_CHUNK = 1 << 20
_BUFFER_SIZE = 1 << 20
_MAX_DETAIL = 200
_END = object()

# Exclusion reason: diagnostic code and message, the same for every record.
_EXCLUSIONS = {
    "invalid_line": (
        "jsonl_invalid_line",
        "Lines that are not valid JSON were excluded.",
    ),
    "not_object": (
        "jsonl_record_not_object",
        (
            "Lines holding valid JSON that is not an object were excluded: a "
            "record is a JSON object."
        ),
    ),
    "line_too_long": (
        "jsonl_line_too_long",
        (
            "Lines longer than {line_limit} bytes were excluded. Raise "
            "limits.max_line_bytes to analyze them."
        ),
    ),
    "duplicate_key": (
        "json_duplicate_key",
        (
            "Records containing an object with a duplicate key were excluded: "
            "which value applies is ambiguous."
        ),
    ),
    "record_too_large": (
        "record_too_large",
        (
            "Records with more than {limit} observations were excluded. Raise "
            "limits.max_record_observations to analyze them."
        ),
    ),
}


class _Duplicate(dict):
    """An object that held a key twice, which ``dict`` would have collapsed."""

    key: str = ""


def _object(pairs: list[tuple[str, object]]) -> dict:
    mapping = dict(pairs)
    if len(mapping) == len(pairs):
        return mapping
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            break
        seen.add(key)
    duplicate = _Duplicate(mapping)
    duplicate.key = key
    return duplicate


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not valid JSON")


def _parse(text: str) -> object:
    return json.loads(
        text,
        parse_float=Decimal,
        parse_constant=_reject_constant,
        object_pairs_hook=_object,
    )


def _has_lone_surrogate(root: object) -> bool:
    """Whether a string or key of the parsed line holds a lone surrogate."""
    stack = [root]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            if not value.isascii() and SURROGATE.search(value):
                return True
        elif isinstance(value, dict):
            for key in value:
                if not key.isascii() and SURROGATE.search(key):
                    return True
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False


def _count_values(root: object) -> int:
    """Values in ``root``, itself and every descendant included."""
    count = 0
    stack = [root]
    while stack:
        value = stack.pop()
        count += 1
        if isinstance(value, (dict, list)):
            stack.extend(value.values() if isinstance(value, dict) else value)
    return count


def _native(value: object) -> NativeType:
    kind = type(value)
    if kind is str:
        return "string"
    if kind is bool:
        return "boolean"
    if kind is int:
        return "integer"
    if kind is Decimal:
        return "number"
    if value is None:
        return "null"
    return "object" if isinstance(value, dict) else "array"


class JsonlLine(NamedTuple):
    """One non-blank line, classified.

    ``kind`` is ``object`` (``value`` is the parsed ``dict``), or an exclusion
    reason: ``invalid_line`` (``value`` describes the failure), ``not_object``
    or ``line_too_long``. ``index`` counts non-blank lines from 1; ``line`` is
    the physical line number.
    """

    kind: str
    index: int
    line: int
    value: object


class JsonlLines:
    """Classified lines of a JSONL source, hashed while read.

    The one place that opens and splits a JSONL source (design inspect
    section 9.2): the Scan reader and Inspect consume it, so both classify a
    line alike. It applies no error policy: an excluded line is yielded, never
    raised. Invalid UTF-8 and a source without a non-blank line are fatal.
    ``blank`` counts the blank lines skipped; ``summary`` is available once the
    iteration is complete.
    """

    def __init__(
        self,
        path: Path,
        max_line_bytes: int,
        on_bytes: Callable[[int], None] | None = None,
    ) -> None:
        self.path = path
        self.max_line_bytes = max_line_bytes
        self.on_bytes = on_bytes
        self.blank = 0
        self._summary: SourceSummary | None = None

    def summary(self) -> SourceSummary:
        if self._summary is None:
            raise RuntimeError("The JSONL source has not been read completely")
        return self._summary

    def __iter__(self) -> Iterator[JsonlLine]:
        try:
            raw = self.path.open("rb")
        except OSError as exc:
            raise InputError(f"Cannot read JSONL file {self.path}: {exc}") from exc
        stream = HashingStream(raw, self.on_bytes)
        buffered = io.BufferedReader(stream, buffer_size=_BUFFER_SIZE)
        try:
            bom = buffered.peek(len(UTF8_BOM))[: len(UTF8_BOM)] == UTF8_BOM
            if bom:
                buffered.read(len(UTF8_BOM))
            try:
                yield from self._classify(buffered)
            except OSError as exc:
                raise InputError(f"Cannot read JSONL file {self.path}: {exc}") from exc
            stream.drain()
        finally:
            buffered.close()
        self._summary = SourceSummary(
            format="jsonl",
            bytes_read=stream.bytes_read,
            sha256=stream.hexdigest(),
            encoding="utf-8-sig" if bom else "utf-8",
        )

    def _read_line(self, buffered: io.BufferedReader) -> tuple[bytes, bool] | None:
        """The next physical line without its line break, and whether it is
        above the size limit (its content is then not kept); ``None`` at the
        end of the source."""
        limit = self.max_line_bytes
        # Room for the limit, a carriage return and the line feed.
        data = buffered.readline(limit + 2)
        if not data:
            return None
        if data.endswith(b"\n"):
            data = data[:-1]
            if data.endswith(b"\r"):
                data = data[:-1]
            return data, len(data) > limit
        if len(data) <= limit + 1:
            # The last line, without a line break.
            data = data[:-1] if data.endswith(b"\r") else data
            return data, len(data) > limit
        # Above the limit: skip the rest of the line, which is still hashed.
        while True:
            rest = buffered.readline(_SKIP_CHUNK)
            if not rest or rest.endswith(b"\n"):
                return b"", True

    def _classify(self, buffered: io.BufferedReader) -> Iterator[JsonlLine]:
        line = 0
        index = 0
        while (read := self._read_line(buffered)) is not None:
            line += 1
            data, too_long = read
            if not too_long and not data.strip(_BLANK):
                self.blank += 1
                continue
            index += 1
            if too_long:
                yield JsonlLine("line_too_long", index, line, None)
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InputError(
                    f"Cannot decode line {line} of {self.path.name} as UTF-8: "
                    f"invalid byte at offset {exc.start} of the line."
                ) from exc
            try:
                value = _parse(text)
            except (ValueError, RecursionError, ArithmeticError) as exc:
                yield JsonlLine("invalid_line", index, line, _detail(exc))
                continue
            if _SURROGATE_ESCAPE.search(text) and _has_lone_surrogate(value):
                yield JsonlLine(
                    "invalid_line",
                    index,
                    line,
                    "a string contains a lone surrogate escape",
                )
                continue
            if not isinstance(value, dict):
                yield JsonlLine("not_object", index, line, None)
                continue
            yield JsonlLine("object", index, line, value)
        if not index:
            raise InputError(f"{self.path.name} has no record line; it is empty.")


class JsonlReader:
    def __init__(
        self,
        path: Path,
        config: ScanConfig,
        on_bytes: Callable[[int], None] | None = None,
    ) -> None:
        self.path = path
        self.tolerant = config.errors.policy == "tolerant"
        self.max_depth = config.limits.max_depth
        self.max_observations = config.limits.max_record_observations
        self.max_line_bytes = config.limits.max_line_bytes
        limit = config.json_.flatten.depth_limit()
        self.flatten_limit = sys.maxsize if limit is None else limit
        self._paths = Paths()
        self._lines = JsonlLines(path, self.max_line_bytes, on_bytes)

    def summary(self) -> SourceSummary:
        return self._lines.summary()

    def __iter__(self) -> Iterator[StreamItem]:
        yield DatasetOpened(
            dataset=DATASET, kind="collection", collection_path=(ITEMS,)
        )
        child = self._paths.child
        for kind, index, line, value in self._lines:
            location = Location(record=index, line=line)
            if kind == "object":
                yield self._record(value, index, location, child)
            else:
                yield self._exclude(index, location, kind, value or "")

    # Records -------------------------------------------------------------

    def _record(self, root: dict, index: int, location: Location, child) -> StreamItem:
        """The observations of one object, as the JSON reader would emit them
        for an element of an array."""
        max_depth = self.max_depth
        flatten_limit = self.flatten_limit
        max_observations = self.max_observations
        if type(root) is _Duplicate:
            return self._exclude(index, location, "duplicate_key", root.key)
        observations = [Observation(ROOT, "object", None)]
        append = observations.append
        truncated = 0
        # Open containers: iterator over their members, path, is an object.
        stack = [(iter(root.items()), ROOT, True)]
        while stack:
            members, path, is_object = stack[-1]
            member = next(members, _END)
            if member is _END:
                stack.pop()
                continue
            if is_object:
                key, item = member
                rel: FieldPath = child(path, key)
            else:
                item = member
                rel = child(path, None)
            if len(rel) > max_depth:
                truncated += _count_values(item)
                continue
            if len(observations) >= max_observations:
                return self._exclude(index, location, "record_too_large")
            kind = _native(item)
            if kind == "object":
                append(Observation(rel, "object", None))
                if len(rel) < flatten_limit:
                    if type(item) is _Duplicate:
                        return self._exclude(
                            index, location, "duplicate_key", item.key
                        )
                    stack.append((iter(item.items()), rel, True))
            elif kind == "array":
                append(Observation(rel, "array", len(item)))
                if len(rel) < flatten_limit:
                    stack.append((iter(item), rel, False))
            else:
                append(Observation(rel, kind, item))
        return Record(DATASET, index, location, observations, truncated)

    def _exclude(
        self, index: int, location: Location, reason: str, detail: str = ""
    ) -> RecordExcluded:
        code, message = _EXCLUSIONS[reason]
        if not self.tolerant:
            raise InputError(self._strict_message(index, location, reason, detail))
        return RecordExcluded(
            dataset=DATASET,
            index=index,
            location=location,
            reason=reason,
            code=code,
            message=message.format(
                line_limit=self.max_line_bytes, limit=self.max_observations
            ),
        )

    def _strict_message(
        self, index: int, location: Location, reason: str, detail: str
    ) -> str:
        where = f"Record {index} (line {location.line}) of {self.path.name}"
        if reason == "invalid_line":
            problem = f"is not valid JSON ({detail})"
            advice = "Fix the line"
        elif reason == "not_object":
            problem = "is valid JSON but not an object"
            advice = "Remove the line"
        elif reason == "line_too_long":
            problem = f"is longer than {self.max_line_bytes} bytes"
            advice = "Raise limits.max_line_bytes"
        elif reason == "duplicate_key":
            problem = f"contains an object with the duplicate key {detail!r}"
            advice = "Remove the duplicate key"
        else:
            problem = f"has more than {self.max_observations} observations"
            advice = "Raise limits.max_record_observations"
        return (
            f"{where} {problem}. {advice}, or use the tolerant error policy "
            "to exclude such records."
        )


def _detail(exc: Exception) -> str:
    """A short description of a parse failure, without quoting values."""
    if isinstance(exc, json.JSONDecodeError):
        detail = f"{exc.msg} at column {exc.colno}"
    elif isinstance(exc, decimal.InvalidOperation):
        detail = "a number has an exponent out of range"
    elif isinstance(exc, RecursionError):
        detail = "the nesting is too deep"
    else:
        detail = str(exc).strip() or type(exc).__name__
    return detail[:_MAX_DETAIL] + ("..." if len(detail) > _MAX_DETAIL else "")
