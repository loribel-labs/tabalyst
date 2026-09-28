"""Declarative pattern detectors (design 12.7).

Each ``patterns`` entry of the configuration becomes a detector class with id
``pattern:<id>``, so a customer number or an internal code is detected without
changing the engine (CA14). The regular expression must match the whole
value. Patterns are trusted configuration: Python ``re`` has no timeout.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from tabalyst.scanner.config import PatternSettings
from tabalyst.scanner.detectors.base import Classification, Detector

PREFIX = "pattern:"
_MATCHED = Classification("matched")


class PatternDetector(Detector):
    """Base of the classes built by ``pattern_detector``."""

    family = "pattern"
    regex: re.Pattern[str]

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self._fullmatch = self.regex.fullmatch

    def classify(self, value: str) -> Classification | None:
        return _MATCHED if self._fullmatch(value) is not None else None

    def classify_many(self, values: Sequence[str]) -> list[Classification | None]:
        fullmatch = self._fullmatch
        return [
            _MATCHED if fullmatch(value) is not None else None for value in values
        ]


def pattern_detector(settings: PatternSettings) -> type[PatternDetector]:
    """A detector class for one validated ``patterns`` entry."""
    return type(
        f"PatternDetector_{settings.id}",
        (PatternDetector,),
        {
            "id": PREFIX + settings.id,
            "accepts": frozenset(settings.accepts),
            "sensitive": settings.sensitive,
            "max_input_length": settings.max_input_length,
            "regex": re.compile(settings.regex),
            "description": settings.description,
        },
    )
