# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The first pass's reading of a cell, replayed (PASS2-02).

A second pass must interpret a value exactly as the Scan did, or its counts
could not be put beside the Scan's. This module repeats, for one field, the two
decisions the first pass made on a string: whether it is content, and what
analytical text and number it gives. It uses the same normalizer, classifier
and number detector, built from the configuration the Scan recorded.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple
from unicodedata import is_normalized

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.detectors.base import Classification
from tabalyst.scanner.detectors.number import NumberDetector
from tabalyst.scanner.detectors.temporal import DateDetector
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.measures import UNCONVERTIBLE, decimal_or_unconvertible
from tabalyst.scanner.normalization import ANALYTICAL_STAGE, Normalizer, collapse

Exact = int | Decimal


class Cell(NamedTuple):
    """What a raw string is worth: the length of its analytical text in
    characters, ``-1`` when it is not content (empty, blank or a null marker),
    its number, ``None`` when the number detector did not accept it, the
    analytical text itself and, for an analysis of dates, what the date detector
    made of the text (``None``: not tested or not a date)."""

    length: int
    number: Exact | None
    text: str
    moment: Classification | None = None


NOT_CONTENT = Cell(-1, None, "")


def _is_number(value: object) -> bool:
    return type(value) is int or isinstance(value, Decimal) or value is UNCONVERTIBLE


class CellReader:
    """Reads the cells of the strings of a field like the first pass.

    ``numbers`` is false when the number detector was turned off in the Scan:
    no value is a number then.
    """

    def __init__(self, config: ScanConfig) -> None:
        values = config.values
        self.strings = StringClassifier(
            values.null_markers, values.null_markers_case_sensitive
        )
        self.normalizer = Normalizer(config.normalization)
        section = config.detectors.number
        settings = section.model_dump()
        self.detector: NumberDetector | None = (
            NumberDetector(settings) if settings.get("enabled", True) else None
        )
        dates = config.detectors.date.model_dump()
        self.date_detector: DateDetector | None = (
            DateDetector(dates) if dates.get("enabled", True) else None
        )

    def analytical(self, raw: str) -> str:
        """The analytical text of a content string: what ``string_lengths`` and
        the numeric measure of the Scan are made of. The shortcut is the one the
        first pass takes for printable strings."""
        normalizer = self.normalizer
        if (
            normalizer.fast
            and raw.isprintable()
            and (raw.isascii() or not normalizer.nfc or is_normalized("NFC", raw))
        ):
            text = raw.strip()
            return collapse(text) if "  " in text else text
        return normalizer.run(raw)[0][ANALYTICAL_STAGE]

    def cells(
        self, raws: Sequence[str], *, numbers: bool = True, dates: bool = False
    ) -> list[Cell]:
        """The cell of each distinct raw string, in order. Without ``numbers``
        the number detector is not run and no cell has a number: an analysis
        of lengths does not pay for it. With ``dates`` the date detector reads
        the analytical text of each content string."""
        category = self.strings.category
        texts: list[str] = []
        positions: list[int] = []
        cells: list[Cell] = [NOT_CONTENT] * len(raws)
        for position, raw in enumerate(raws):
            if category(raw) == "content":
                texts.append(self.analytical(raw))
                positions.append(position)
        found = self._numbers(texts) if numbers else [None] * len(texts)
        moments = self._moments(texts) if dates else [None] * len(texts)
        for position, text, number, moment in zip(
            positions, texts, found, moments, strict=True
        ):
            cells[position] = Cell(len(text), number, text, moment)
        return cells

    def content(self, raws: Sequence[str]) -> list[bool]:
        """Whether each raw string is content (not empty, blank or a null
        marker), as the first pass decides it. It reads nothing else: the
        original values of a field (design 21) need no analytical text."""
        strings = self.strings
        if not strings.has_markers and all(map(str.strip, raws)):
            return [True] * len(raws)
        category = strings.category
        return [category(raw) == "content" for raw in raws]

    def _numbers(self, texts: list[str]) -> list[Exact | None]:
        detector = self.detector
        if detector is None:
            return [None] * len(texts)
        cap = detector.max_input_length
        try:
            found = detector.classify_many(texts)
            if len(found) != len(texts):
                raise ValueError("classify_many returned a wrong number of results")
        except Exception:  # noqa: BLE001 - detector code is isolated, as in the scan
            found = [self._one(detector, text) for text in texts]
        numbers: list[Exact | None] = []
        for text, classification in zip(texts, found, strict=True):
            if (
                classification is None
                or (cap is not None and len(text) > cap)
                or getattr(classification, "state", None) != "matched"
                or not _is_number(classification.value)
            ):
                numbers.append(None)
            else:
                numbers.append(classification.value)
        return numbers

    def _moments(self, texts: list[str]) -> list[Classification | None]:
        """What the date detector makes of each analytical text, as the first
        pass does: a text above the input cap of the detector is not tested."""
        detector = self.date_detector
        if detector is None:
            return [None] * len(texts)
        cap = detector.max_input_length
        try:
            found = detector.classify_many(texts)
            if len(found) != len(texts):
                raise ValueError("classify_many returned a wrong number of results")
        except Exception:  # noqa: BLE001 - detector code is isolated, as in the scan
            found = [self._one(detector, text) for text in texts]  # type: ignore[misc]
        return [
            None if classification is None or (cap is not None and len(text) > cap) else classification
            for text, classification in zip(texts, found, strict=True)
        ]

    @staticmethod
    def _one(detector: NumberDetector, text: str) -> object:
        try:
            return detector.classify(text)
        except Exception:  # noqa: BLE001 - a failing value is not a number
            return None


def native_number(native_type: str, value: object) -> Exact:
    """The number of a JSON integer or number: an ``int``, or a ``Decimal`` of
    the text the reader kept, which is how the first pass counted it."""
    if native_type == "integer":
        return int(value)  # type: ignore[call-overload]
    return decimal_or_unconvertible(str(value))  # type: ignore[return-value]
