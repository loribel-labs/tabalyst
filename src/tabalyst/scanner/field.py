"""Per-field accumulator: presence, native types and string categories.

Accumulators are mutable slotted classes; the dataset turns them into
immutable models at finalization (design section 3).
"""

from __future__ import annotations

from collections.abc import Sequence

from tabalyst.scanner.observations import DeclaredField, Observation
from tabalyst.scanner.paths import FieldPath


class StringClassifier:
    """Sorts a raw string into ``empty``, ``blank``, ``marker`` or ``content``,
    in that order (design section 7)."""

    __slots__ = ("_case_sensitive", "_markers", "has_markers")

    def __init__(self, markers: Sequence[str], case_sensitive: bool) -> None:
        self._case_sensitive = case_sensitive
        self._markers = frozenset(
            markers if case_sensitive else (marker.casefold() for marker in markers)
        )
        self.has_markers = bool(self._markers)

    def is_marker(self, value: str) -> bool:
        stripped = value.strip()
        if not self._case_sensitive:
            stripped = stripped.casefold()
        return stripped in self._markers


class FieldState:
    __slots__ = (
        "array_items",
        "array_max_length",
        "array_min_length",
        "arrays",
        "arrays_empty",
        "blank",
        "content",
        "declared",
        "empty",
        "first_record",
        "marker",
        "native_types",
        "occurrences",
        "path",
    )

    def __init__(self, path: FieldPath, declared: DeclaredField | None = None) -> None:
        self.path = path
        self.declared = declared
        self.occurrences = 0
        self.native_types: dict[str, int] = {}
        self.first_record: int | None = None
        self.empty = 0
        self.blank = 0
        self.marker = 0
        self.content = 0
        self.arrays = 0
        self.arrays_empty = 0
        self.array_min_length = 0
        self.array_max_length = 0
        self.array_items = 0

    def observe(
        self, observation: Observation, record: int, strings: StringClassifier
    ) -> None:
        self.occurrences += 1
        if self.first_record is None:
            self.first_record = record
        native_type = observation.type
        self.native_types[native_type] = self.native_types.get(native_type, 0) + 1
        if native_type == "string":
            value = observation.value
            if not value:
                self.empty += 1
            elif value.isspace():
                self.blank += 1
            elif strings.has_markers and strings.is_marker(value):
                self.marker += 1
            else:
                self.content += 1
        elif native_type == "array":
            length = observation.value
            if self.arrays == 0 or length < self.array_min_length:
                self.array_min_length = length
            self.array_max_length = max(self.array_max_length, length)
            self.arrays += 1
            self.array_items += length
            if length == 0:
                self.arrays_empty += 1

    def count(self, native_type: str) -> int:
        return self.native_types.get(native_type, 0)

    @property
    def value_count(self) -> int:
        """Analyzable scalar values: content strings, integers, numbers, booleans."""
        return (
            self.content
            + self.count("integer")
            + self.count("number")
            + self.count("boolean")
        )
