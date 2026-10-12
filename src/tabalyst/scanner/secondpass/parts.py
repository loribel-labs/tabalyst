# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The parts of the calendar dates of a field: year-month, day of the week, hour,
dates after a bound, the ambiguous dates under each reading and the invalid ones
by reason (design 20.25, lot 17).

A value is read as the first pass read it (the date detector of the Scan's
configuration, on the analytical text) and placed by the calendar date it is
written with: the offset of an aware datetime is not converted. The counts per
year and per month of the year are not kept: they are sums of the counts per
year-month. Ambiguous values are counted and never placed in the parts; the
simulation reads them again under each order, with the detector of the same
configuration but for its ``ambiguous_order``.
"""

from __future__ import annotations

from datetime import date

from tabalyst.scanner.detectors.base import Classification
from tabalyst.scanner.detectors.temporal import DateDetector, kind_of
from tabalyst.scanner.models import DetectorComplete, FieldResult
from tabalyst.scanner.planner.facts import date_evidence
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.models import (
    AmbiguitySimulation,
    AmbiguousReading,
    DateResolution,
    PartCount,
    PartsResult,
    PeriodCount,
    ReasonCount,
)

ORDERS = ("DMY", "MDY")
UNSPECIFIED = "unspecified"
# Ambiguous texts whose readings an accumulator remembers: a day and a month in
# a few years are a few thousand texts at most.
REMEMBERED = 16_384


def month_label(key: int) -> str:
    """``YYYY-MM`` of a month counted as ``year * 12 + month - 1``."""
    return f"{key // 12:04d}-{key % 12 + 1:02d}"


class _Reading:
    """The ambiguous dates read in one order."""

    __slots__ = ("after", "months", "placed", "weekdays")

    def __init__(self) -> None:
        self.placed = 0
        self.after = 0
        self.months: dict[int, int] = {}
        self.weekdays = [0] * 7


class PartsAccumulator:
    """The counters of the parts of the dates of one temporal kind."""

    __slots__ = (
        "after",
        "ambiguous",
        "as_of",
        "cell_ns",
        "date_settings",
        "detectors",
        "hours",
        "invalid",
        "kind",
        "months",
        "order",
        "placed",
        "readings",
        "remembered",
        "values",
        "weekdays",
    )

    def __init__(
        self,
        kind: str,
        date_settings: dict[str, object],
        *,
        as_of: date | None,
        order: str | None = None,
        cell_ns: int = 0,
    ) -> None:
        self.kind = kind
        # The order the ambiguous dates are read in (the detector then gives them
        # a date), when the evidence of the Scan chose one.
        self.order = order
        self.date_settings = date_settings
        # What the plan expects a cell to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.as_of = None if as_of is None else as_of.toordinal()
        self.values = 0
        self.placed = 0
        self.ambiguous = 0
        self.invalid: dict[str, int] = {}
        self.months: dict[int, int] = {}
        self.weekdays = [0] * 7
        self.hours = [0] * 24
        self.after = 0
        self.readings: dict[str, _Reading] = {}
        self.detectors: dict[str, DateDetector] = {}
        # The dates an ambiguous text makes under each order: the same text comes
        # back in every batch, and reading it is what costs.
        self.remembered: dict[str, tuple[date | None, date | None]] = {}

    def add(self, moment: Classification | None, text: str, count: int) -> None:
        """``count`` occurrences of a content string, with what the date
        detector made of its analytical text (``None``: not tested or not a date)."""
        self.values += count
        if moment is None:
            return
        state = moment.state
        if state == "ambiguous":
            self.ambiguous += count
            self._simulate(text, count)
            return
        if state == "invalid":
            reason = moment.reason or UNSPECIFIED
            self.invalid[reason] = self.invalid.get(reason, 0) + count
            return
        value = moment.value
        if state != "matched" or kind_of(value) != self.kind:
            return
        self.placed += count
        if self.kind == "time":
            self.hours[value.hour] += count  # type: ignore[attr-defined]
            return
        # `year`, `month` and `weekday` read the date as written.
        key = value.year * 12 + value.month - 1  # type: ignore[attr-defined]
        self.months[key] = self.months.get(key, 0) + count
        self.weekdays[value.weekday()] += count  # type: ignore[attr-defined]
        if self.kind != "date":
            self.hours[value.hour] += count  # type: ignore[attr-defined]
        if self.as_of is not None and value.toordinal() > self.as_of:  # type: ignore[attr-defined]
            self.after += count

    def _read(self, text: str) -> tuple[date | None, date | None]:
        """The date of an ambiguous text under each order (``None``: the detector
        does not read it so)."""
        found = self.remembered.get(text)
        if found is None:
            dates: list[date | None] = []
            for order in ORDERS:
                detector = self.detectors.get(order)
                if detector is None:
                    detector = self.detectors[order] = DateDetector(
                        {**self.date_settings, "ambiguous_order": order}
                    )
                read = detector.classify(text)
                dates.append(read.value if read is not None and read.state == "matched" else None)  # type: ignore[arg-type]
            found = (dates[0], dates[1])
            if len(self.remembered) < REMEMBERED:
                self.remembered[text] = found
        return found

    def _simulate(self, text: str, count: int) -> None:
        for order, value in zip(ORDERS, self._read(text), strict=True):
            reading = self.readings.setdefault(order, _Reading())
            if value is None:
                continue
            reading.placed += count
            key = value.year * 12 + value.month - 1
            reading.months[key] = reading.months.get(key, 0) + count
            reading.weekdays[value.weekday()] += count
            if self.as_of is not None and value.toordinal() > self.as_of:
                reading.after += count

    # The result -------------------------------------------------------------

    def result(self, field: FieldResult, as_of: str | None) -> PartsResult:
        """The parts, checked against the Scan: the dates of this kind, the
        ambiguous and the invalid values are those it counted. Raises
        ``ScanMismatch`` when they disagree."""
        stats = field.temporal.value if field.temporal.status == "complete" else None
        if stats is None or len(stats.kinds) != 1:
            raise ScanMismatch("the scan has no single temporal kind for the field")
        resolved = stats.ambiguous if self.order else 0
        if self.placed != stats.kinds[0].count + resolved:
            raise ScanMismatch(
                f"dates: the second pass found {self.placed}, "
                f"the scan {stats.kinds[0].count + resolved}"
            )
        if self.ambiguous != stats.ambiguous - resolved:
            raise ScanMismatch(
                f"ambiguous dates: the second pass found {self.ambiguous}, "
                f"the scan {stats.ambiguous - resolved}"
            )
        if not self.placed:
            raise ScanMismatch("the second pass found no date")
        invalid = sum(self.invalid.values())
        not_tested = self._check_invalid(field, invalid)
        time_only = self.kind == "time"
        return PartsResult(
            temporal_kind=self.kind,  # type: ignore[arg-type]
            values=self.values,
            count=self.placed,
            ambiguous=self.ambiguous,
            resolved=resolved,
            invalid=invalid,
            unplaced=self.values - self.placed - self.ambiguous - invalid,
            scan_not_tested=not_tested,
            invalid_reasons=[
                ReasonCount(reason=reason, count=count)
                for reason, count in sorted(self.invalid.items(), key=lambda i: (-i[1], i[0]))
            ],
            year_months=None if time_only else _months(self.months),
            weekdays=None if time_only else _parts(self.weekdays, 0),
            hours=None if self.kind == "date" else _present(self.hours),
            as_of=as_of if not time_only else None,
            after_as_of=self.after if as_of is not None and not time_only else None,
            simulation=self._simulation(as_of) if self.ambiguous else None,
            resolution=(
                DateResolution(order=self.order, evidence=date_evidence(field))  # type: ignore[arg-type]
                if self.order
                else None
            ),
        )

    def _check_invalid(self, field: FieldResult, invalid: int) -> int:
        """The invalid values against the date detector of the Scan; the number
        of values it did not test (adaptive detection), which this pass read."""
        detector = next((d for d in field.detectors if d.id == "date"), None)
        if not isinstance(detector, DetectorComplete):
            return 0
        coverage = detector.coverage
        if coverage.not_tested == 0:
            if invalid != coverage.invalid:
                raise ScanMismatch(
                    f"invalid dates: the second pass found {invalid}, the scan {coverage.invalid}"
                )
        elif not coverage.invalid <= invalid <= coverage.invalid + coverage.not_tested:
            raise ScanMismatch(
                f"invalid dates: the second pass found {invalid}, the scan {coverage.invalid} "
                f"and {coverage.not_tested} values not tested"
            )
        return coverage.not_tested

    def _simulation(self, as_of: str | None) -> AmbiguitySimulation:
        readings = []
        for order in ORDERS:
            reading = self.readings.get(order)
            if reading is None:
                continue
            readings.append(
                AmbiguousReading(
                    order=order,  # type: ignore[arg-type]
                    placed=reading.placed,
                    year_months=_months(reading.months),
                    weekdays=_parts(reading.weekdays, 0),
                    after_as_of=reading.after if as_of is not None else None,
                )
            )
        return AmbiguitySimulation(ambiguous=self.ambiguous, readings=readings)


def _months(counts: dict[int, int]) -> list[PeriodCount]:
    """The months that occur, in order, as ``YYYY-MM``."""
    return [PeriodCount(period=month_label(key), count=counts[key]) for key in sorted(counts)]


def _parts(counts: list[int], origin: int) -> list[PartCount]:
    """Every part of a cycle, from ``origin``, including those with no value."""
    return [PartCount(value=i + origin, count=count) for i, count in enumerate(counts)]


def _present(counts: list[int]) -> list[PartCount]:
    return [PartCount(value=i, count=count) for i, count in enumerate(counts) if count]
