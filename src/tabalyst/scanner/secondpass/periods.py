# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Exact counts of the dates of a field per day, month or year (design 20.10,
TIME-01 to TIME-03).

A value is read as the first pass read it (the date detector of the Scan's
configuration, on the analytical text) and placed by the calendar date it is
written with. Ambiguous values are counted and never placed; values of another
temporal kind or that are not dates are counted apart. The totals are checked
against the temporal block of the Scan.
"""

from __future__ import annotations

from datetime import date

from tabalyst.scanner.detectors.base import Classification
from tabalyst.scanner.detectors.temporal import kind_of
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import DateResolution, PeriodCount, PeriodCounts


class PeriodAccumulator:
    """A counter per calendar period of one temporal kind."""

    __slots__ = ("ambiguous", "counts", "granularity", "kind", "order", "placed", "values")

    def __init__(self, granularity: str, kind: str, order: str | None = None) -> None:
        self.granularity = granularity
        self.kind = kind
        # The order the ambiguous dates are read in (the detector then gives them
        # a date), when the evidence of the Scan chose one.
        self.order = order
        self.counts: dict[int, int] = {}
        self.values = 0
        self.placed = 0
        self.ambiguous = 0

    def add(self, moment: Classification | None, count: int) -> None:
        """A content string of the field with the classification the date
        detector gave its analytical text (``None``: not tested or not a date)."""
        self.values += count
        if moment is None:
            return
        if moment.state == "ambiguous":
            self.ambiguous += count
            return
        if moment.state != "matched" or kind_of(moment.value) != self.kind:
            return
        value = moment.value
        # `toordinal` and `year` read the date as written, not converted.
        if self.granularity == "day":
            key = value.toordinal()  # type: ignore[attr-defined]
        elif self.granularity == "month":
            key = value.year * 12 + value.month - 1  # type: ignore[attr-defined]
        else:
            key = value.year  # type: ignore[attr-defined]
        self.counts[key] = self.counts.get(key, 0) + count
        self.placed += count

    def _label(self, key: int) -> str:
        if self.granularity == "day":
            return date.fromordinal(key).isoformat()
        if self.granularity == "month":
            return f"{key // 12:04d}-{key % 12 + 1:02d}"
        return f"{key:04d}"

    def result(
        self, expected: int, expected_ambiguous: int, evidence: dict[str, int] | None = None
    ) -> PeriodCounts:
        """The counts, checked against the Scan: the dates of this kind and the
        ambiguous values are those it counted, the ambiguous ones being placed
        with the others when an order read them."""
        resolved = expected_ambiguous if self.order else 0
        evidence = evidence or {}
        if self.placed != expected + resolved:
            raise ScanMismatch(
                f"dates: the second pass found {self.placed}, the scan {expected + resolved}"
            )
        if self.ambiguous != expected_ambiguous - resolved:
            raise ScanMismatch(
                f"ambiguous dates: the second pass found {self.ambiguous}, "
                f"the scan {expected_ambiguous - resolved}"
            )
        if not self.counts:
            raise ScanMismatch("the second pass found no date")
        keys = sorted(self.counts)
        return PeriodCounts(
            granularity=self.granularity,  # type: ignore[arg-type]
            temporal_kind=self.kind,  # type: ignore[arg-type]
            values=self.values,
            count=self.placed,
            ambiguous=self.ambiguous,
            resolved=resolved,
            unplaced=self.values - self.placed - self.ambiguous,
            first=self._label(keys[0]),
            last=self._label(keys[-1]),
            periods=[PeriodCount(period=self._label(key), count=self.counts[key]) for key in keys],
            resolution=(
                DateResolution(order=self.order, evidence=evidence)  # type: ignore[arg-type]
                if self.order
                else None
            ),
        )
