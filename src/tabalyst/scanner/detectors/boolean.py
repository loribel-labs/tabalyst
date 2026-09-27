"""Textual boolean detector (design 9.5 and 12.10).

A value matches when its analytical value, ignoring case, is one word of a
configured pair. The format is the pair, such as ``yes/no``; native JSON
booleans stay in the ``booleans`` block.
"""

from __future__ import annotations

from collections.abc import Mapping

from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorAccumulator,
)
from tabalyst.scanner.exposure import ExposureGate

DEFAULT_PAIRS = (
    ("true", "false"),
    ("yes", "no"),
    ("y", "n"),
    ("oui", "non"),
    ("vrai", "faux"),
)


class BooleanDetector(Detector):
    id = "boolean"
    family = "boolean"

    def __init__(self, settings: Mapping[str, object]) -> None:
        super().__init__(settings)
        self._words: dict[str, Classification] = {}
        for true_word, false_word in settings.get("pairs", DEFAULT_PAIRS):
            label = f"{true_word}/{false_word}"
            for word, meaning in ((true_word, True), (false_word, False)):
                self._words[word.casefold()] = Classification(
                    "matched", format=label, value=meaning
                )
        self._longest = max(map(len, self._words), default=0)

    def classify(self, value: str) -> Classification | None:
        if len(value) > self._longest:
            return None
        return self._words.get(value.casefold())

    def accumulator(self) -> BooleanAccumulator:
        return BooleanAccumulator()


class BooleanAccumulator(DetectorAccumulator):
    __slots__ = ("false", "true")

    def __init__(self) -> None:
        self.true = 0
        self.false = 0

    def add(
        self, value: str, classification: Classification | None, count: int
    ) -> None:
        if classification is not None and classification.state == "matched":
            if classification.value:
                self.true += count
            else:
                self.false += count

    def details(self, gate: ExposureGate) -> dict[str, object]:
        return {"true": self.true, "false": self.false}
