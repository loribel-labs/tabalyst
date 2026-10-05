# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Enumeration candidate detector (design 12.10), ported from the current
engine.

A field-level detector: its values match together when the field has at least
``minimum_values`` eligible values and at most ``maximum_distinct`` distinct
analytical values (ignoring case when ``case_sensitive`` is false); otherwise
none matches. It keeps at most ``maximum_distinct + 1`` values, so its state is
bounded and its result does not depend on frequency tables. Once it holds
``maximum_distinct + 1`` values, the field is rejected and later values are
only counted (``rejects_field``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.exposure import ExposureGate

_MEMBER = Classification("matched")


class EnumerationDetector(Detector):
    id = "enumeration"
    family = "categorical"
    scope = "field"

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.minimum_values = settings.get("minimum_values", 500)
        self.maximum_distinct = settings.get("maximum_distinct", 49)
        self.case_sensitive = settings.get("case_sensitive", True)

    def classify(self, value: str) -> Classification:
        return _MEMBER

    def classify_many(self, values: Sequence[str]) -> list[Classification]:
        return [_MEMBER] * len(values)

    def accumulator(self) -> EnumerationAccumulator:
        return EnumerationAccumulator(
            self.minimum_values, self.maximum_distinct, self.case_sensitive
        )


class EnumerationAccumulator(DetectorAccumulator):
    __slots__ = ("case_sensitive", "keys", "maximum", "minimum", "values")

    def __init__(self, minimum: int, maximum: int, case_sensitive: bool) -> None:
        self.minimum = minimum
        self.maximum = maximum
        self.case_sensitive = case_sensitive
        self.values = 0
        self.keys: set[str] = set()

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        self.values += count
        if len(self.keys) <= self.maximum:
            self.keys.add(value if self.case_sensitive else value.casefold())

    def field_matches(self) -> bool:
        return self.values >= self.minimum and len(self.keys) <= self.maximum

    def rejects_field(self) -> bool:
        # Keys stop growing past the maximum: the field can no longer match,
        # and ``details`` no longer changes.
        return len(self.keys) > self.maximum

    def details(self, gate: ExposureGate) -> dict[str, object]:
        distinct = len(self.keys)
        if distinct <= self.maximum:
            return {"distinct": {"status": "complete", "value": distinct}}
        return {
            "distinct": {
                "status": "limited",
                "reason": "maximum_distinct",
                "limit": self.maximum,
                "lower_bound": distinct,
            }
        }
