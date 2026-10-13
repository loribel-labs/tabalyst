# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The forms the values of a sensitive field take, counted without a value
(design 20.35, decision O61, lot 18).

A form is the mask the exposure gate gives a value (design 12.8) and, for an IP
address or a phone number, a class of a closed list. The accumulator keeps masks and
counts and never a value; the result sums up every mask or class that fewer than
``min_count`` values take, so no figure singles a few values out.
"""

from __future__ import annotations

from collections.abc import Sequence

from tabalyst.scanner.detectors.ip import ip_class
from tabalyst.scanner.detectors.phone import phone_class
from tabalyst.scanner.exposure import mask
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.frequencies import native_key
from tabalyst.scanner.secondpass.models import FormClasses, FormCount, FormsResult
from tabalyst.scanner.secondpass.replay import CellReader


def class_of(detector: str, text: str, value: str) -> str | None:
    """The class of a value the detector matched: ``value`` is what the detector
    made of it (the version of an address, the region of a number)."""
    if detector == "ip_address":
        return ip_class(text)
    if detector == "phone":
        return phone_class(text, value)
    return None


def floored(
    items: Sequence[tuple[str, int]], min_count: int, max_listed: int
) -> tuple[list[tuple[str, int]], int, int]:
    """Split ``items`` (most frequent first) into the ones that are listed, the
    number of the others and the values they hold. An item is listed when at least
    ``min_count`` values take it; when what is left out holds fewer values than
    that, the least frequent listed item joins it, so the sum of the others is not a
    figure about a few values either."""
    shown = [item for item in items if item[1] >= min_count][:max_listed]
    listed = {label for label, _ in shown}
    others = [item for item in items if item[0] not in listed]
    count = sum(value for _, value in others)
    while shown and 0 < count < min_count:
        last = shown.pop()
        others.append(last)
        count += last[1]
    return shown, len(others), count


class FormsAccumulator:
    """The masks of the analytical values of one field, each with its exact count,
    and the classes of what a detector reads. A mask is tracked from its first
    occurrence up to ``max_tracked`` of them; the values with another mask are only
    summed up."""

    __slots__ = (
        "by_class",
        "cell_ns",
        "detector",
        "forms",
        "max_listed",
        "max_tracked",
        "min_count",
        "unclassified",
        "untracked",
        "values",
    )

    def __init__(
        self,
        *,
        min_count: int,
        max_listed: int,
        max_tracked: int,
        detector: str | None,
        cell_ns: int = 0,
    ) -> None:
        self.min_count = min_count
        self.max_listed = max_listed
        self.max_tracked = max_tracked
        self.detector = detector
        # What the plan expects a value to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.forms: dict[tuple[str, str], int] = {}
        self.by_class: dict[str, int] = {}
        self.unclassified = 0
        self.untracked = 0
        self.values = 0

    def _add(self, key: tuple[str, str], count: int) -> None:
        forms = self.forms
        found = forms.get(key)
        if found is not None:
            forms[key] = found + count
        elif len(forms) < self.max_tracked:
            forms[key] = count
        else:
            self.untracked += count

    def add_strings(self, reader: CellReader, raws: Sequence[str], counts: Sequence[int]) -> None:
        """Account for the distinct content strings of a batch with their counts."""
        texts = [reader.analytical(raw) for raw in raws]
        add = self._add
        for text, count in zip(texts, counts, strict=True):
            add(("string", mask(text)), count)
        self.values += sum(counts)
        if self.detector is not None:
            self._classify(reader, texts, counts)

    def add_native(self, native_type: str, value: object) -> None:
        """Account for one JSON integer, number or boolean, which no detector of
        strings reads."""
        kind, text = native_key(native_type, value)
        self._add((kind, mask(text)), 1)
        self.values += 1
        if self.detector is not None:
            self.unclassified += 1

    def _classify(self, reader: CellReader, texts: list[str], counts: Sequence[int]) -> None:
        assert self.detector is not None
        detector = reader.replay_detector(self.detector)
        if detector is None:
            self.unclassified += sum(counts)
            return
        try:
            found = detector.classify_many(texts)
        except Exception:  # noqa: BLE001 - detector code is isolated, as in the scan
            found = [None] * len(texts)
        for text, count, classification in zip(texts, counts, found, strict=True):
            kind = None
            if classification is not None and classification.state == "matched":
                kind = class_of(self.detector, text, str(classification.value or ""))
            if kind is None:
                self.unclassified += count
            else:
                self.by_class[kind] = self.by_class.get(kind, 0) + count

    def result(self, field: FieldResult) -> FormsResult:
        """The forms, checked against the Scan: the values it counted, and the
        count of every mask it lists."""
        expected = field.values.count
        if self.values != expected:
            raise ScanMismatch(f"values: the second pass found {self.values}, the scan {expected}")
        self._check(field)
        merged: dict[str, int] = {}
        for (_, form), count in self.forms.items():
            merged[form] = merged.get(form, 0) + count
        ordered = sorted(merged.items(), key=lambda item: (-item[1], item[0]))
        shown, other_forms, other_values = floored(ordered, self.min_count, self.max_listed)
        return FormsResult(
            values=self.values,
            forms=len(merged),
            complete=not self.untracked,
            untracked=self.untracked,
            min_count=self.min_count,
            listed=[FormCount(form=form, count=count) for form, count in shown],
            other_forms=other_forms,
            other_values=other_values + self.untracked,
            classes=None if self.detector is None else self._classes(),
        )

    def _classes(self) -> FormClasses:
        assert self.detector is not None
        ordered = sorted(self.by_class.items(), key=lambda item: (-item[1], item[0]))
        shown, _, other = floored(ordered, self.min_count, len(ordered))
        return FormClasses(
            detector=self.detector,  # type: ignore[arg-type]
            listed=[FormCount(form=form, count=count) for form, count in shown],
            other=other,
            unclassified=self.unclassified,
        )

    def _check(self, field: FieldResult) -> None:
        """The masks the Scan lists, with their counts, are the ones counted here;
        when it lists them all, so are their number."""
        frequencies = field.values.frequencies
        if frequencies.status != "complete":
            return
        for entry in frequencies.value.listed:
            held = self.forms.get((entry.type, entry.value))
            if held is None:
                if not self.untracked:
                    raise ScanMismatch("a mask the scan lists was not found by the second pass")
            elif held != entry.count:
                raise ScanMismatch(
                    f"occurrences of a mask: the second pass found {held}, the scan {entry.count}"
                )
        listed_all = not self.untracked and not frequencies.value.truncated
        if listed_all and len(self.forms) != frequencies.value.distinct:
            raise ScanMismatch(
                f"distinct masks: the second pass found {len(self.forms)}, "
                f"the scan {frequencies.value.distinct}"
            )

