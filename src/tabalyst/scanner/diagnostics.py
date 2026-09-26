"""Collector of technical events, grouped with exact counts (design section 14)."""

from __future__ import annotations

from typing import Literal

from tabalyst.scanner.models import Diagnostic

Level = Literal["fatal", "error", "warning"]


class _Group:
    __slots__ = (
        "code",
        "count",
        "dataset",
        "detector",
        "field",
        "index",
        "level",
        "locations",
        "message",
    )

    def __init__(self, index, code, level, message, dataset, field, detector) -> None:
        self.index = index
        self.code = code
        self.level = level
        self.message = message
        self.dataset = dataset
        self.field = field
        self.detector = detector
        self.count = 0
        self.locations: list[dict[str, int]] = []


class DiagnosticCollector:
    """Groups events by code and subject; ``count`` stays complete while
    ``locations`` keeps at most ``max_locations`` entries."""

    def __init__(self, max_locations: int) -> None:
        self.max_locations = max_locations
        self._groups: dict[tuple, _Group] = {}

    def add(
        self,
        code: str,
        level: Level,
        message: str,
        *,
        dataset: str | None = None,
        field: str | None = None,
        detector: str | None = None,
        location: dict[str, int] | None = None,
    ) -> int:
        """Record one event and return the index of its diagnostic."""
        key = (code, dataset, field, detector)
        group = self._groups.get(key)
        if group is None:
            group = self._groups[key] = _Group(
                len(self._groups), code, level, message, dataset, field, detector
            )
        group.count += 1
        if location is not None and len(group.locations) < self.max_locations:
            group.locations.append(location)
        return group.index

    def finalize(self) -> list[Diagnostic]:
        return [
            Diagnostic(
                code=group.code,
                level=group.level,
                message=group.message,
                count=group.count,
                dataset=group.dataset,
                field=group.field,
                detector=group.detector,
                locations=group.locations,
            )
            for group in self._groups.values()
        ]
