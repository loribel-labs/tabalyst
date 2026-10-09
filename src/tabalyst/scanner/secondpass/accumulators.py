# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The states of the analyses of the second pass: counters fed by the reading
and the result each one gives. Each checks its totals against the Scan before
it answers (PASS2-02): a count that disagrees is a failure, never a result."""

from __future__ import annotations

import math
from array import array
from fractions import Fraction

from tabalyst.scanner.measures import (
    UNCONVERTIBLE,
    output_number,
    weighted_median,
)
from tabalyst.scanner.models import LengthCount, NumericStats
from tabalyst.scanner.secondpass.bins import (
    BinEdges,
    binned_quantiles,
    exact_quantiles,
    rounded,
)
from tabalyst.scanner.secondpass.models import (
    MAX_MODES,
    BinnedHistogram,
    DenseHistogram,
    LengthDistribution,
    OutsideBins,
    ValueCountNumber,
)
from tabalyst.scanner.secondpass.replay import Exact


class ScanMismatch(Exception):
    """What the second pass counted is not what the Scan says it read. The
    message holds counts, never a value of the data."""


def _check(label: str, found: object, expected: object) -> None:
    if found != expected:
        raise ScanMismatch(f"{label}: the second pass found {found}, the scan {expected}")


class DenseAccumulator:
    """A counter per integer of a small domain, starting at ``low``."""

    __slots__ = ("counts", "domain", "invalid", "low", "outside", "total")

    def __init__(self, low: int, domain: int) -> None:
        self.low = low
        self.domain = domain
        self.counts = array("q", bytes(8 * domain))
        self.total = 0
        self.outside = 0
        self.invalid: str | None = None

    def add(self, number: Exact, count: int) -> None:
        if type(number) is not int:
            if number is UNCONVERTIBLE:
                self.invalid = "unconvertible_number"
                return
            if number.adjusted() > 40:  # far beyond any domain of 65,536 integers
                self.outside += count
                return
            integral = int(number)
            if integral != number:
                self.invalid = "non_integral_value"
                return
            number = integral
        offset = number - self.low
        if 0 <= offset < self.domain:
            self.counts[offset] += count
            self.total += count
        else:
            self.outside += count

    def result(self, stats: NumericStats) -> DenseHistogram:
        if self.invalid is not None:
            raise ScanMismatch(f"{self.invalid}: the field is not a field of integers")
        _check("values outside the domain of the scan", self.outside, 0)
        _check("numeric values", self.total, stats.count)
        values = [
            (self.low + offset, count)
            for offset, count in enumerate(self.counts)
            if count
        ]
        _check("minimum", values[0][0], stats.min)
        _check("maximum", values[-1][0], stats.max)
        top = max(count for _, count in values)
        modes = [value for value, count in values if count == top]
        quantiles = exact_quantiles(values, self.total)
        return DenseHistogram(
            count=self.total,
            min=values[0][0],
            max=values[-1][0],
            distinct=len(values),
            values=[ValueCountNumber(value=value, count=count) for value, count in values],
            modes=modes[:MAX_MODES],
            modes_truncated=len(modes) > MAX_MODES,
            median=quantiles[2],
            quantiles=quantiles,
        )


class BinAccumulator:
    """A counter per bin of exact edges. ``strategy``, ``requested``, ``source``
    and ``reason`` describe where the edges come from (``BinnedHistogram``).

    ``low`` and ``high`` are the bounds the edges were placed on. They are the
    exact minimum and maximum of the Scan when those are integers, and widened
    to the neighbouring floats when they are float64 roundings of a decimal
    number, so that every value of the source is inside them.
    """

    __slots__ = (
        "above",
        "below",
        "counts",
        "edges",
        "high",
        "invalid",
        "low",
        "reason",
        "requested",
        "seen_max",
        "seen_min",
        "source",
        "strategy",
        "tight",
        "total",
    )

    def __init__(
        self,
        edges: BinEdges,
        *,
        strategy: str,
        requested: str,
        source: str,
        reason: str | None,
        tight: bool,
    ) -> None:
        self.edges = edges
        self.counts = [0] * edges.bins
        self.total = 0
        self.below = 0
        self.above = 0
        self.low = edges.edges[0]
        self.high = edges.edges[-1]
        self.strategy = strategy
        self.requested = requested
        self.source = source
        self.reason = reason
        # Whether the bounds are the exact minimum and maximum, which then
        # tighten the bounds of an estimate.
        self.tight = tight
        self.seen_min: Exact | None = None
        self.seen_max: Exact | None = None
        self.invalid: str | None = None

    def add(self, number: Exact, count: int) -> None:
        if number is UNCONVERTIBLE:
            self.invalid = "unconvertible_number"
            return
        if self.seen_min is None or number < self.seen_min:
            self.seen_min = number
        if self.seen_max is None or number > self.seen_max:
            self.seen_max = number
        index = self.edges.index(number)
        if index < 0:
            self.below += count
        elif index >= self.edges.bins:
            self.above += count
        else:
            self.counts[index] += count
            self.total += count

    def result(self, stats: NumericStats) -> BinnedHistogram:
        if self.invalid is not None:
            raise ScanMismatch(f"{self.invalid}: a number beyond the precision of the scan")
        _check("values outside the bounds of the scan", self.below + self.above, 0)
        _check("numeric values", self.total, stats.count)
        _check("minimum", output_number(Fraction(self.seen_min)), stats.min)
        _check("maximum", output_number(Fraction(self.seen_max)), stats.max)
        edges = self.edges.edges
        minimum = Fraction(self.seen_min) if self.tight else edges[0]
        maximum = Fraction(self.seen_max) if self.tight else edges[-1]
        quantiles = binned_quantiles(edges, self.counts, self.total, minimum, maximum)
        written = [rounded(edge) for edge in edges]
        written[0], written[-1] = stats.min, stats.max
        return BinnedHistogram(
            strategy=self.strategy,  # type: ignore[arg-type]
            requested_strategy=self.requested,  # type: ignore[arg-type]
            bounds_source=self.source,  # type: ignore[arg-type]
            reason=self.reason,
            count=self.total,
            min=stats.min,
            max=stats.max,
            edges=written,
            counts=list(self.counts),
            outside=OutsideBins(below=self.below, above=self.above),
            median=quantiles[2],
            quantiles=quantiles,
        )


class LengthAccumulator:
    """A counter per length, in characters of the analytical text."""

    __slots__ = ("counts",)

    def __init__(self) -> None:
        self.counts: dict[int, int] = {}

    def add(self, length: int, count: int) -> None:
        self.counts[length] = self.counts.get(length, 0) + count

    def result(self, content: int) -> LengthDistribution:
        counts = self.counts
        total = sum(counts.values())
        _check("content strings", total, content)
        characters = sum(length * n for length, n in counts.items())
        return LengthDistribution(
            count=total,
            min_length=min(counts),
            max_length=max(counts),
            mean_length=output_number(Fraction(characters, total)),
            median_length=output_number(weighted_median(list(counts.items()), total)),
            length_histogram=[
                LengthCount(length=length, count=counts[length]) for length in sorted(counts)
            ],
        )


def decimal_bounds(value: float) -> tuple[Fraction, Fraction, bool]:
    """The bounds to place edges on for a minimum or maximum written by the
    Scan: itself when it is an integer, which is exact, and otherwise the
    neighbouring floats on each side, for the float64 rounding of a decimal
    number can be above or below it. The last member says whether it is exact."""
    if isinstance(value, int):
        return Fraction(value), Fraction(value), True
    return (
        Fraction(math.nextafter(value, -math.inf)),
        Fraction(math.nextafter(value, math.inf)),
        False,
    )

