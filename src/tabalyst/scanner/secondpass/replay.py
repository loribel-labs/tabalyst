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

import copy
from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple, cast
from unicodedata import is_normalized

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.convention_rule import (
    dotted_thousands,
    holds_native_numbers,
    scan_convention,
)
from tabalyst.scanner.detectors.amount import MeasureReading
from tabalyst.scanner.detectors.base import Classification, Detector
from tabalyst.scanner.detectors.currency import CurrencyDetector
from tabalyst.scanner.detectors.number import NumberDetector
from tabalyst.scanner.detectors.percentage import PercentageDetector
from tabalyst.scanner.detectors.quantity import QuantityDetector
from tabalyst.scanner.detectors.registry import replayable
from tabalyst.scanner.detectors.shape import shape
from tabalyst.scanner.detectors.temporal import DateDetector
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.measures import UNCONVERTIBLE, decimal_or_unconvertible
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.normalization import ANALYTICAL_STAGE, Normalizer, collapse

Exact = int | Decimal


class Measure(NamedTuple):
    """What the detector of values with a unit or a marker made of a text
    (design 20.19): its ``state`` (``matched``, ``ambiguous`` or ``invalid``),
    the ``number`` of a matched value and whether it is written as a decimal,
    and, but for an invalid value, the ``marker`` (currency, ``%`` or unit),
    whether it is written ``before`` the number and whether a space separates
    them. ``resolved`` says that the number was read in the convention the
    column proves (an ambiguous value, or ``d.ddd`` as thousands; design 20.28),
    never that the configuration resolved it."""

    state: str
    number: Exact | None = None
    decimal: bool = False
    marker: str | None = None
    before: bool = False
    spaced: bool = False
    resolved: bool = False


class Cell(NamedTuple):
    """What a raw string is worth: the length of its analytical text in
    characters, ``-1`` when it is not content (empty, blank or a null marker),
    its number, ``None`` when the number detector did not accept it, the
    analytical text itself and, for an analysis of dates, what the date detector
    made of the text (``None``: not tested or not a date), and, for an
    extraction of values with a unit, what its detector made of it (``None``:
    not tested or not matched)."""

    length: int
    number: Exact | None
    text: str
    moment: Classification | None = None
    measure: Measure | None = None


# The detectors of values with a unit or a marker that an extraction replays.
MeasureDetector = CurrencyDetector | PercentageDetector | QuantityDetector
MEASURE_DETECTORS: dict[str, type[MeasureDetector]] = {
    "currency": CurrencyDetector,
    "percentage": PercentageDetector,
    "quantity": QuantityDetector,
}
_INVALID = Measure("invalid")
# What a replayed detector made of a text: its state (``matched``, ``ambiguous``,
# ``invalid``, ``not_matched`` or ``not_tested``) and, for an invalid text, the
# reason the detector gave.
Reading = tuple[str, str | None]
_NOT_TESTED: Reading = ("not_tested", None)
_NOT_MATCHED: Reading = ("not_matched", None)
_MATCHED: Reading = ("matched", None)
_AMBIGUOUS: Reading = ("ambiguous", None)
UNSPECIFIED = "unspecified"


def measure_of(reading: object, convention: str | None = None) -> Measure | None:
    """The ``Measure`` of what the ``measure`` method of a detector returned.
    ``convention`` is the one the detector was built to resolve the ambiguous
    numbers in by the evidence of the column (design 20.28): under ``comma``, a
    strict decimal ``d.ddd`` is a thousands group."""
    if reading is None:
        return None
    found, marker, before, spaced = cast("MeasureReading", reading)
    state = found.state
    if state == "invalid":
        return _INVALID
    if state != "matched":
        return Measure(state, marker=marker, before=before, spaced=spaced)
    if convention == "comma" and (thousands := dotted_thousands(found)) is not None:
        return Measure(state, thousands, False, marker, before, spaced, True)
    number = found.value
    # The number detector gives an int for the integer formats and a Decimal for
    # the decimal ones (an integer beyond what Python converts aside), which is
    # what ``integral_decimals`` of the numeric block counts.
    return Measure(
        state,
        number,  # type: ignore[arg-type]
        type(number) is not int,
        marker,
        before,
        spaced,
        convention is not None and bool(found.candidates),
    )


NOT_CONTENT = Cell(-1, None, "")


def _is_number(value: object) -> bool:
    return type(value) is int or isinstance(value, Decimal) or value is UNCONVERTIBLE


class CellReader:
    """Reads the cells of the strings of a field like the first pass.

    ``numbers`` is false when the number detector was turned off in the Scan:
    no value is a number then. ``convention`` is the one the Scan read the
    ambiguous numbers of the field in by the evidence of its column (design
    20.27), ``None`` for the ordinary reading: a field's reader comes from
    ``for_field``.
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
        # The detector that reads the ambiguous dates in one order, by order.
        self.date_settings = dates
        self.ordered_detectors: dict[str, DateDetector] = {}
        self.config = config
        self.measure_detectors: dict[tuple[str, str | None], MeasureDetector | None] = {}
        self.replays: dict[str, Detector | None] = {}
        self.convention: str | None = None
        self.regroup = False
        # The readers of the other conventions, shared by every view.
        self.views: dict[tuple[str | None, bool], CellReader] = {(None, False): self}

    def for_field(self, field: FieldResult) -> CellReader:
        """The reader of a field of the Scan: it reads the numbers the Scan
        counted in the field's ``numeric`` block, ambiguous ones included when
        the column proved a convention."""
        return self.reading(scan_convention(field))

    def for_sample(self, field: FieldResult) -> CellReader:
        """The reader of the cells the Scan wrote for a field in its row sample,
        where a number of the source's own type (JSON, Excel) is text too: in a
        field that holds such numbers, ``d.ddd`` keeps the value written, since
        a native number is never read in a convention (design 20.27)."""
        convention = scan_convention(field)
        return self.reading(
            convention, regroup=convention == "comma" and not holds_native_numbers(field)
        )

    def reading(self, convention: str | None, *, regroup: bool | None = None) -> CellReader:
        """The reader that reads the ambiguous numbers in ``convention`` and,
        when ``regroup`` (by default under ``comma``), the strict decimals
        ``d.ddd`` as thousands (design 20.27); ``None`` is the ordinary reading.
        The views share every cache but the number detector."""
        regroup = convention == "comma" if regroup is None else regroup
        view = self.views.get((convention, regroup))
        if view is None:
            view = copy.copy(self)
            view.convention = convention
            view.regroup = regroup
            settings = self.config.detectors.number.model_dump()
            view.detector = (
                NumberDetector({**settings, "ambiguous_convention": convention})
                if self.detector is not None
                else None
            )
            self.views[(convention, regroup)] = view
        return view

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
        self,
        raws: Sequence[str],
        *,
        numbers: bool = True,
        dates: bool | str = False,
        measure: str | None = None,
        convention: str | None = None,
    ) -> list[Cell]:
        """The cell of each distinct raw string, in order. Without ``numbers``
        the number detector is not run and no cell has a number: an analysis
        of lengths does not pay for it. With ``dates`` the date detector reads
        the analytical text of each content string (``dates`` may be ``DMY`` or
        ``MDY``, the order the field's ambiguous dates are read in), and with
        ``measure`` the detector of that id (``currency``, ``percentage`` or
        ``quantity``), which reads the ambiguous numbers in ``convention`` when
        the evidence of the column proves one (design 20.28)."""
        category = self.strings.category
        texts: list[str] = []
        positions: list[int] = []
        cells: list[Cell] = [NOT_CONTENT] * len(raws)
        for position, raw in enumerate(raws):
            if category(raw) == "content":
                texts.append(self.analytical(raw))
                positions.append(position)
        found = self._numbers(texts) if numbers else [None] * len(texts)
        moments = self._moments(texts, dates) if dates else [None] * len(texts)
        measures = (
            self._measures(measure, texts, convention)
            if measure is not None
            else [None] * len(texts)
        )
        for position, text, number, moment, read in zip(
            positions, texts, found, moments, measures, strict=True
        ):
            cells[position] = Cell(len(text), number, text, moment, read)
        return cells

    def measure_detector(
        self, detector: str, convention: str | None = None
    ) -> MeasureDetector | None:
        """The detector of values with a unit of that id, with the settings the
        Scan recorded and, with a ``convention``, the one that resolves its
        ambiguous numbers; ``None`` when the Scan turned it off."""
        key = (detector, convention)
        if key not in self.measure_detectors:
            settings = getattr(self.config.detectors, detector).model_dump()
            if convention is not None:
                settings["ambiguous_convention"] = convention
            self.measure_detectors[key] = (
                MEASURE_DETECTORS[detector](settings) if settings.get("enabled", True) else None
            )
        return self.measure_detectors[key]

    def _measures(
        self, detector: str, texts: list[str], convention: str | None
    ) -> list[Measure | None]:
        """What the detector of values with a unit makes of each analytical
        text, as the first pass does: a text above its input cap is not tested."""
        reader = self.measure_detector(detector, convention)
        if reader is None:
            return [None] * len(texts)
        cap = reader.max_input_length
        measure = reader.measure
        found: list[Measure | None] = []
        for text in texts:
            if cap is not None and len(text) > cap:
                found.append(None)
                continue
            try:
                found.append(measure_of(measure(text), convention))
            except Exception:  # noqa: BLE001 - a value the detector raises on is not read
                found.append(None)
        return found

    def replay_detector(self, detector: str) -> Detector | None:
        """The built-in detector of that id with the settings the Scan recorded,
        or ``None`` when the Scan turned it off or it cannot be replayed."""
        if detector not in self.replays:
            kind = replayable().get(detector)
            section = getattr(self.config.detectors, detector, None)
            settings = {} if section is None else section.model_dump()
            self.replays[detector] = (
                kind(settings) if kind is not None and settings.get("enabled", True) else None
            )
        return self.replays[detector]

    def readings(self, detector: str, texts: Sequence[str]) -> list[Reading] | None:
        """What the detector makes of each analytical text, as the first pass
        decides it (design 12): a text above the input cap is not tested, one
        whose shape the detector rules out is not matched without being
        classified, and the others go through ``classify_many``. ``None`` when
        the detector cannot be replayed."""
        reader = self.replay_detector(detector)
        if reader is None:
            return None
        cap = reader.max_input_length
        pattern = reader.shapes
        found: list[Reading] = [_NOT_TESTED] * len(texts)
        wanted: list[int] = []
        for position, text in enumerate(texts):
            if cap is not None and len(text) > cap:
                continue
            if pattern is not None and pattern.fullmatch(shape(text)) is None:
                found[position] = _NOT_MATCHED
            else:
                wanted.append(position)
        batch = [texts[position] for position in wanted]
        try:
            results = reader.classify_many(batch)
            if len(results) != len(batch):
                raise ValueError("classify_many returned a wrong number of results")
        except Exception:  # noqa: BLE001 - detector code is isolated, as in the scan
            results = [self._one(reader, text) for text in batch]  # type: ignore[misc]
        for position, result in zip(wanted, results, strict=True):
            if result is None:
                found[position] = _NOT_MATCHED
                continue
            state = result.state
            if state == "matched":
                found[position] = _MATCHED
            elif state == "ambiguous":
                found[position] = _AMBIGUOUS
            else:
                found[position] = ("invalid", result.reason or UNSPECIFIED)
        return found

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
        regroup = self.regroup
        for text, classification in zip(texts, found, strict=True):
            if (
                classification is None
                or (cap is not None and len(text) > cap)
                or getattr(classification, "state", None) != "matched"
                or not _is_number(classification.value)
            ):
                numbers.append(None)
            elif regroup and (thousands := dotted_thousands(classification)) is not None:  # type: ignore[arg-type]
                numbers.append(thousands)
            else:
                numbers.append(classification.value)
        return numbers

    def _moments(
        self, texts: list[str], order: bool | str = True
    ) -> list[Classification | None]:
        """What the date detector makes of each analytical text, as the first
        pass does: a text above the input cap of the detector is not tested. With
        an ``order`` the ambiguous dates are read in it, as ``ambiguous_order``
        of the configuration would."""
        detector = self.date_detector
        if isinstance(order, str) and detector is not None:
            detector = self.ordered_detectors.get(order)
            if detector is None:
                detector = self.ordered_detectors[order] = DateDetector(
                    {**self.date_settings, "ambiguous_order": order}
                )
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
    def _one(detector: Detector, text: str) -> object:
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
