"""Private project-db revision-1 codec: decoded Scan values, never SQL casts."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.observations import Observation
from tabalyst.scanner.paths import ITEMS, Column, FieldPath, Key, path_to_json


class DatabaseValidationError(ValueError):
    """The database disagrees with its declared Tabalyst contract."""


class DatabaseCompatibilityError(DatabaseValidationError):
    """Unsupported logical project-db version; rebuilding is required."""


class DatabaseOpenError(OSError):
    """Physical DuckDB open failure, separate from logical compatibility."""


def json_text(value: object) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    text.encode("utf-8")
    return text


def path_text(path: FieldPath) -> str:
    return json_text(path_to_json(path))


def decode_path(text: str) -> FieldPath:
    try:
        value = json.loads(text)
        if not isinstance(value, list) or json_text(value) != text:
            raise ValueError
        segments = []
        for part in value:
            if not isinstance(part, dict) or len(part) != 1:
                raise ValueError
            if "key" in part and isinstance(part["key"], str):
                segments.append(Key(part["key"]))
            elif "items" in part and part["items"] is True:
                segments.append(ITEMS)
            elif "column" in part:
                bigint(part["column"], minimum=1)
                segments.append(Column(part["column"]))
            else:
                raise ValueError
        return tuple(segments)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise DatabaseValidationError("Invalid canonical path") from exc


def bigint(value: int, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise DatabaseValidationError("Index/count is outside the SQL BIGINT range")
    return value


def encode_value(observation: Observation) -> tuple[str | None, int | None]:
    native, value = observation.type, observation.value
    if native == "string" and isinstance(value, str):
        value.encode("utf-8")
        return value, None
    if native == "integer" and type(value) is int:
        return canonical_text(native, value), None
    if native == "number" and isinstance(value, Decimal) and value.is_finite():
        return canonical_text(native, value), None
    if native == "boolean" and type(value) is bool:
        return canonical_text(native, value), None
    if native in ("null", "object") and value is None:
        return None, None
    if native == "array":
        return None, bigint(value)
    raise DatabaseValidationError("Invalid observation tagged union")


def decode_value(native: str, text: str | None, length: int | None) -> object:
    """Reconstruct the exact int/Decimal repr used by the shared digest."""
    try:
        if native == "array" and text is None:
            return bigint(length)
        if length is not None:
            raise ValueError
        if native in ("null", "object") and text is None:
            return None
        if not isinstance(text, str):
            raise TypeError
        text.encode("utf-8")
        if native == "string":
            return text
        if native == "boolean" and text in ("true", "false"):
            return text == "true"
        if native == "integer":
            value = int(text)
        elif native == "number":
            value = Decimal(text)
            if not value.is_finite():
                raise ValueError
        else:
            raise ValueError
        if canonical_text(native, value) != text:
            raise ValueError
        return value
    except (ValueError, TypeError, InvalidOperation, UnicodeError) as exc:
        raise DatabaseValidationError("Invalid observation tagged union") from exc
