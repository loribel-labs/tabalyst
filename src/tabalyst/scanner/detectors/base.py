"""Detector contract (design section 12.1).

A detector classifies one analyzable value at a time. ``classify`` is pure and
deterministic, so the engine may run it once per distinct value or through a
memoization cache with identical results (design section 13). Coverage,
formats and evidence are kept by the engine for every detector; a detector's
accumulator adds its own ``details``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal

if TYPE_CHECKING:
    from tabalyst.scanner.exposure import ExposureGate

State = Literal["matched", "ambiguous", "invalid"]


@dataclass(frozen=True, slots=True)
class Classification:
    """Result of a detector for one value; ``None`` stands for not matched.

    - ``matched`` values may carry a ``format`` and a parsed ``value`` for
      statistics. A matched value with ``candidates`` was ambiguous and
      resolved by configuration.
    - ``ambiguous`` values list their ``candidates`` formats and never carry a
      value: they must not enter statistics that need one interpretation.
    - ``invalid`` values have the detector's shape but fail validation, such
      as ``2026-02-30``; ``reason`` says why.
    - ``convention`` names the reading of an unambiguous value when several
      readings exist (date order, decimal convention); it feeds the ambiguity
      evidence of the field (design 12.6).
    """

    state: State
    format: str | None = None
    candidates: tuple[str, ...] = ()
    reason: str | None = None
    value: object = None
    convention: str | None = None


class _NotTested:
    """A value the detector did not test, such as one above its input cap."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NOT_TESTED"


NOT_TESTED = _NotTested()


@dataclass(frozen=True, slots=True)
class DetectorFailure:
    """``classify`` raised: only the exception type is kept, never the value."""

    error: str


class DetectorAccumulator:
    """Detector-specific statistics of one field.

    ``add`` receives every tested value with its classification (``None`` when
    not matched) and its count. In both execution modes it sees the same
    distinct values, first seen first, with the same total counts.
    """

    __slots__ = ()

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        """Account for ``count`` occurrences of ``value``."""

    def details(self, gate: ExposureGate) -> dict[str, object]:
        """JSON-compatible ``details`` of the detector result.

        Values of the field that ``details`` carries, such as email domains,
        must go through ``gate`` (design 12.8): the field may be sensitive.
        """
        return {}

    def field_matches(self) -> bool:
        """Field-level detectors decide at the end whether their values match."""
        return True


class Detector:
    """Base class of detectors; subclasses set the class attributes and
    implement ``classify``.

    - ``accepts``: native types of the values given to ``classify``, as
      analytical text for strings and canonical text for other types.
    - ``shapes``: optional pattern that the shape signature of a value must
      fully match (design 12.5); other values are not matched without calling
      ``classify``. It must accept the shape of every value ``classify`` can
      match, so rejection stays exact.
    - ``max_input_length``: longer values are ``not_tested``.
    - ``scope``: ``field`` detectors, such as enumeration candidates, decide
      at the end whether every value of the field matches or none does.
    """

    id: ClassVar[str]
    version: ClassVar[int] = 1
    family: ClassVar[str]
    accepts: ClassVar[frozenset[str]] = frozenset({"string"})
    sensitive: ClassVar[bool] = False
    max_input_length: ClassVar[int | None] = None
    scope: ClassVar[Literal["value", "field"]] = "value"
    shapes: re.Pattern[str] | None = None

    def __init__(self, settings: Mapping[str, object]) -> None:
        self.settings = settings

    def classify(self, value: str) -> Classification | None:
        raise NotImplementedError

    def accumulator(self) -> DetectorAccumulator:
        return DetectorAccumulator()


class AmbiguityAccumulator(DetectorAccumulator):
    """Ambiguity details shared by detectors with several readings
    (design 12.6).

    ``count`` and ``candidates`` cover every value that is ambiguous under the
    enabled readings, resolved by configuration or not. ``evidence`` counts
    unambiguous values per reading; it is exposed, never applied.
    """

    __slots__ = ("candidates", "count", "evidence", "resolution")

    def __init__(self, readings: list[str], resolution: dict[str, str] | None) -> None:
        self.count = 0
        self.candidates: dict[tuple[str, ...], int] = {}
        self.evidence = dict.fromkeys(sorted(readings), 0)
        self.resolution = resolution

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is None:
            return
        candidates = classification.candidates
        if candidates:
            self.count += count
            self.candidates[candidates] = self.candidates.get(candidates, 0) + count
        elif classification.state == "matched":
            convention = classification.convention
            if convention in self.evidence:
                self.evidence[convention] += count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {
            "ambiguity": {
                "count": self.count,
                "candidates": [
                    {"formats": list(formats), "count": count}
                    for formats, count in sorted(
                        self.candidates.items(), key=lambda item: (-item[1], item[0])
                    )
                ],
                "evidence": dict(self.evidence),
                "resolution": self.resolution,
            }
        }
