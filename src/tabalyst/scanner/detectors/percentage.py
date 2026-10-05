# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Percentage detector (``docs/dev/scan/detectors.md``).

A signed number part, an optional space and ``%``. The number part follows
the number detector (``amount.py``); the parsed value is the number as
written, 12 for ``12%``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from tabalyst.scanner.detectors.amount import (
    NUMBER_PART,
    SPACES,
    AmountAccumulator,
    AmountReader,
)
from tabalyst.scanner.detectors.base import Classification, Detector

_PERCENTAGE = re.compile(
    rf"(?P<sign>[+-]?)(?P<body>{NUMBER_PART})(?P<space>[{SPACES}]?)%"
)


class PercentageDetector(Detector):
    id = "percentage"
    family = "ratio"

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self.reader = AmountReader(settings, "invalid_number")

    def classify(self, value: str) -> Classification | None:
        if value[-1:] != "%":  # exact cheap rejection
            return None
        match = _PERCENTAGE.fullmatch(value)
        if match is None:
            return None
        return self.reader.read(match["sign"], match["body"], "", match["space"] + "%")

    def classify_many(self, values: Sequence[str]) -> list[Classification | None]:
        classify = self.classify
        return [classify(value) if value[-1:] == "%" else None for value in values]

    def accumulator(self) -> AmountAccumulator:
        return self.reader.accumulator()
