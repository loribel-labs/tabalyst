# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The numbers of the values with a currency marker, a percent sign or a unit
(design 20.19, lot 14).

A value is read as the first pass read it: the ``currency``, ``percentage`` or
``quantity`` detector of the Scan's configuration, on the analytical text. Its
number is placed in the group of its marker; nothing is converted, so a group
holds one quantity and the whole field holds them all. Each marker counts its
numbers exactly in a table until the field holds ``max_values`` distinct pairs of
a marker and a number; every group then goes on in bins of a width that is a
power of two, whose counts, sums and extremes stay exact.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TypeVar

from tabalyst.scanner.measures import (
    UNCONVERTIBLE,
    NumericAccumulator,
    Unrepresentable,
    output_number,
)
from tabalyst.scanner.models import (
    Complete,
    DetectorComplete,
    FieldResult,
    Limited,
    NumericStats,
)
from tabalyst.scanner.planner.analyzer import DENSE_DOMAIN_MAX
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.bins import (
    BinEdges,
    binned_quantiles,
    exact_quantiles,
    linear_edges,
    rounded,
)
from tabalyst.scanner.secondpass.models import (
    MAX_MODES,
    BinnedHistogram,
    DenseHistogram,
    MarkerCount,
    MarkerEnumeration,
    MarkerLayout,
    MeasureGroup,
    MeasureLevel,
    MeasureOther,
    MeasureResult,
    OutsideBins,
    PercentRange,
    Quantile,
    RareMarkers,
    ValueCountNumber,
)
from tabalyst.scanner.secondpass.replay import CellReader, Exact, Measure

# The finest width of a bin of the grid, 2**-64: a fixed floor keeps the width
# a function of the range alone, whatever the order of the values.
GRID_MIN_EXPONENT = -64
# Markers listed by the enumeration; a column has a handful of units.
MAX_LISTED_MARKERS = 1_000
# A marker written in less than this share of the values with a marker is rare.
RARE_SHARE = Fraction(1, 100)
# The reason a median is not exact once the numbers went on in bins.
MAX_VALUES = "max_values"
MARKER_KINDS = {"currency": "currency", "percentage": "percent", "quantity": "unit"}

Level = TypeVar("Level", bound=MeasureLevel)


def _index(number: Exact | Fraction, exponent: int) -> int:
    """The bin of the grid of width ``2 ** exponent`` that holds ``number``:
    ``floor(number / 2 ** exponent)``, exact. Integer shifts and the integer
    ratio of a Decimal: a Fraction would cost several times as much."""
    if type(number) is int:
        return number >> exponent if exponent >= 0 else number << -exponent
    numerator, denominator = number.as_integer_ratio()
    if exponent >= 0:
        return numerator // (denominator << exponent)
    return (numerator << -exponent) // denominator


def smallest_exponent(minimum: Fraction, maximum: Fraction, bins: int) -> int:
    """The smallest exponent, not below ``GRID_MIN_EXPONENT``, whose bins hold
    ``[minimum, maximum]`` in at most ``bins`` bins. A wider range never needs a
    smaller one, so the grid of a group, which only widens when a value does not
    fit, ends with the exponent of its whole range whatever the order."""
    exponent = GRID_MIN_EXPONENT
    span = maximum - minimum
    if span > 0:
        ratio = span / bins
        # The bins fit only when their width exceeds ``ratio``: start below
        # its base-2 logarithm.
        exponent = max(
            exponent, ratio.numerator.bit_length() - ratio.denominator.bit_length() - 1
        )
    while _index(maximum, exponent) - _index(minimum, exponent) + 1 > bins:
        exponent += 1
    return exponent


class Grid:
    """Counts per bin ``[j * 2**exponent, (j + 1) * 2**exponent)``, at most
    ``bins`` of them between the lowest and the highest bin that hold a value.
    A value outside doubles the width until it fits."""

    __slots__ = ("bins", "counts", "exponent", "high", "low")

    def __init__(self, bins: int, exponent: int = GRID_MIN_EXPONENT) -> None:
        self.bins = bins
        self.exponent = exponent
        self.counts: dict[int, int] = {}
        self.low = 0
        self.high = -1

    def add(self, number: Exact | Fraction, count: int) -> None:
        index = _index(number, self.exponent)
        if not self.counts:
            self.low = self.high = index
        elif index < self.low or index > self.high:
            low, high = min(self.low, index), max(self.high, index)
            while high - low + 1 > self.bins:
                self._coarsen()
                low, high, index = low >> 1, high >> 1, index >> 1
            self.low, self.high = low, high
        self.counts[index] = self.counts.get(index, 0) + count

    def _coarsen(self) -> None:
        merged: dict[int, int] = {}
        for index, count in self.counts.items():
            merged[index >> 1] = merged.get(index >> 1, 0) + count
        self.counts = merged
        self.exponent += 1
        self.low >>= 1
        self.high >>= 1


class _Group:
    """The values written with one marker."""

    __slots__ = ("ambiguous", "grid", "numeric", "parsed", "table")

    def __init__(self) -> None:
        self.parsed = 0
        self.ambiguous = 0
        self.numeric = NumericAccumulator()
        # The median comes from the table or the grid, not from this list.
        self.numeric.median_values = None
        self.table: dict[Exact, int] | None = {}
        self.grid: Grid | None = None


class MeasureAccumulator:
    """The groups of the values with a marker of one field, fed with what the
    detector made of each content string (``Measure``)."""

    __slots__ = (
        "above",
        "after",
        "ambiguous",
        "before",
        "below",
        "bins",
        "cell_ns",
        "detector",
        "entries",
        "gridded",
        "groups",
        "invalid",
        "max_groups",
        "max_values",
        "parsed",
        "spaced",
        "strings",
        "unconvertible",
        "unspaced",
        "values",
        "within",
    )

    def __init__(
        self,
        detector: str,
        *,
        max_groups: int,
        max_values: int,
        bins: int,
        cell_ns: int = 0,
    ) -> None:
        self.detector = detector
        # What the plan expects a cell to cost: it weighs the route among the
        # workers and is no input of the result.
        self.cell_ns = cell_ns
        self.max_groups = max_groups
        self.max_values = max_values
        self.bins = bins
        self.groups: dict[str, _Group] = {}
        # Content values, of them strings (the values the detector may read).
        self.values = 0
        self.strings = 0
        self.parsed = 0
        self.ambiguous = 0
        self.invalid = 0
        self.unconvertible = 0
        self.before = self.after = self.spaced = self.unspaced = 0
        self.below = self.within = self.above = 0
        # Distinct pairs of a marker and a number held by the tables, and
        # whether the groups went on in bins.
        self.entries = 0
        self.gridded = False

    def add(self, measure: Measure | None, count: int) -> None:
        """``count`` occurrences of a content string."""
        self.values += count
        self.strings += count
        if measure is None:
            return
        state = measure.state
        if state == "invalid":
            self.invalid += count
            return
        marker = measure.marker
        assert marker is not None
        group = self.groups.get(marker)
        if group is None:
            group = self.groups[marker] = _Group()
            if self.gridded:
                group.table, group.grid = None, Grid(self.bins)
        if measure.before:
            self.before += count
        else:
            self.after += count
        if measure.spaced:
            self.spaced += count
        else:
            self.unspaced += count
        if state != "matched":
            self.ambiguous += count
            group.ambiguous += count
            return
        self.parsed += count
        group.parsed += count
        number = measure.number
        if number is UNCONVERTIBLE:
            self.unconvertible += count
            return
        assert number is not None
        group.numeric.add(number, measure.decimal, False, count)
        if self.detector == "percentage":
            if number < 0:
                self.below += count
            elif number > 100:
                self.above += count
            else:
                self.within += count
        table = group.table
        if table is None:
            assert group.grid is not None
            group.grid.add(number, count)
        elif number in table:
            table[number] += count
        else:
            table[number] = count
            self.entries += 1
            if self.entries > self.max_values:
                self._to_grids()

    def add_native(self, count: int = 1) -> None:
        """A JSON number or boolean: a value no detector of strings reads."""
        self.values += count

    def _to_grids(self) -> None:
        """Every group goes on in bins: the width of each is the smallest that
        holds what its table counted, and it only widens from there."""
        self.gridded = True
        for group in self.groups.values():
            table = group.table
            assert table is not None
            grid = Grid(
                self.bins,
                smallest_exponent(Fraction(min(table)), Fraction(max(table)), self.bins)
                if table
                else GRID_MIN_EXPONENT,
            )
            for number, count in table.items():
                grid.add(number, count)
            group.table, group.grid = None, grid
        self.entries = 0

    # The result -------------------------------------------------------------

    def result(self, field: FieldResult, computed_from: str) -> MeasureResult:
        """The three levels, checked against the Scan: the values of the field,
        what its detector counted and the markers it listed. Raises
        ``ScanMismatch`` when they disagree and ``Unrepresentable`` for a number
        beyond the precision of the Scan."""
        if self.unconvertible:
            raise Unrepresentable
        self._check(field)
        if not self.parsed:
            raise ScanMismatch("the second pass found no number with a marker")
        of = self.values
        ranked = sorted(
            ((marker, group) for marker, group in self.groups.items() if group.parsed),
            key=lambda item: (-item[1].parsed, item[0]),
        )
        kept, rest = ranked[: self.max_groups], ranked[self.max_groups :]
        overall = self._level(MeasureLevel, [group for _, group in ranked], of)
        groups = [
            self._level(MeasureGroup, [group], of, marker=marker) for marker, group in kept
        ]
        other = (
            self._level(MeasureOther, [group for _, group in rest], of, markers=len(rest))
            if rest
            else None
        )
        return MeasureResult(
            accuracy="exact_counts" if self.gridded else "exact",
            storage="grid" if self.gridded else "table",
            computed_from=computed_from,  # type: ignore[arg-type]
            detector=self.detector,  # type: ignore[arg-type]
            values=self.values,
            parsed=self.parsed,
            ambiguous=self.ambiguous,
            invalid=self.invalid,
            unparsed=self.values - self.parsed - self.ambiguous - self.invalid,
            scan_not_tested=_detector(field, self.detector).coverage.not_tested,
            homogeneous=len(ranked) == 1,
            overall=overall,
            groups=groups,
            other=other,
            markers=self._markers(),
            percent_range=(
                PercentRange(below=self.below, within=self.within, above=self.above)
                if self.detector == "percentage"
                else None
            ),
        )

    def _check(self, field: FieldResult) -> None:
        if self.values != field.values.count:
            raise ScanMismatch(
                f"values: the second pass found {self.values}, the scan {field.values.count}"
            )
        detector = _detector(field, self.detector)
        coverage = detector.coverage
        if self.strings != coverage.eligible:
            raise ScanMismatch(
                f"strings: the second pass found {self.strings}, the scan {coverage.eligible}"
            )
        found = (self.parsed, self.ambiguous, self.invalid)
        counted = (coverage.matched, coverage.ambiguous, coverage.invalid)
        if coverage.not_tested == 0:
            if found != counted:
                raise ScanMismatch(
                    f"matched, ambiguous and invalid: the second pass found {found}, "
                    f"the scan {counted}"
                )
            self._check_markers(detector)
        # The Scan left values untested: this pass, which reads them all, finds
        # at least what it found and no more than those values can add.
        elif any(a < b for a, b in zip(found, counted, strict=True)) or (
            sum(found) - sum(counted) > coverage.not_tested
        ):
            raise ScanMismatch(
                f"matched, ambiguous and invalid: the second pass found {found}, "
                f"the scan {counted} and {coverage.not_tested} values not tested"
            )

    def _check_markers(self, detector: DetectorComplete) -> None:
        counts = {
            marker: group.parsed + group.ambiguous for marker, group in self.groups.items()
        }
        details = detector.details
        if self.detector == "currency":
            listed = details.get("currencies")
            if isinstance(listed, dict) and listed != counts:
                raise ScanMismatch(
                    f"currencies: the second pass found {len(counts)} markers, "
                    f"the scan {len(listed)}, or other counts"
                )
        elif self.detector == "quantity":
            units = details.get("units")
            if not isinstance(units, dict) or units.get("status") != "complete":
                return
            block = units["value"]
            if block["distinct"] != len(counts) or any(
                counts.get(item["value"]) != item["count"] for item in block["listed"]
            ):
                raise ScanMismatch(
                    f"units: the second pass found {len(counts)} units, "
                    f"the scan {block['distinct']}, or other counts"
                )

    def _level(
        self, kind: type[Level], members: list[_Group], of: int, **extra: str | int
    ) -> Level:
        """The metrics of the numbers of ``members`` together, as a ``kind``
        with the ``extra`` members it adds."""
        if len(members) == 1:
            numeric = members[0].numeric
        else:
            numeric = NumericAccumulator()
            for group in members:
                numeric.merge(group.numeric)
        count = numeric.count
        if self.gridded:
            return self._grid_level(kind, members, numeric, of, extra)
        if len(members) == 1:
            # A single group (a homogeneous field): its own table, not a copy.
            table = members[0].table
            assert table is not None
        else:
            table = {}
            for group in members:
                assert group.table is not None
                for number, occurrences in group.table.items():
                    table[number] = table.get(number, 0) + occurrences
        pairs = sorted(table.items(), key=lambda item: item[0])
        if sum(table.values()) != count:
            raise ScanMismatch("the table of the numbers does not add up to their count")
        quantiles = exact_quantiles(pairs, count)  # type: ignore[arg-type]
        top = max(table.values())
        modes = [number for number, occurrences in pairs if occurrences == top]
        stats = _stats(numeric, of, quantiles[2].value, self.max_values)
        minimum, maximum = Fraction(pairs[0][0]), Fraction(pairs[-1][0])
        histogram: DenseHistogram | BinnedHistogram
        if (
            all(Fraction(number).denominator == 1 for number, _ in pairs)
            and maximum - minimum < DENSE_DOMAIN_MAX
        ):
            integers = [(int(number), occurrences) for number, occurrences in pairs]
            histogram = DenseHistogram(
                count=count,
                min=integers[0][0],
                max=integers[-1][0],
                distinct=len(integers),
                values=[ValueCountNumber(value=v, count=c) for v, c in integers],
                modes=[int(number) for number in modes[:MAX_MODES]],
                modes_truncated=len(modes) > MAX_MODES,
                median=quantiles[2],
                quantiles=quantiles,
            )
        else:
            edges = BinEdges(linear_edges(minimum, maximum, self.bins))
            counts = [0] * edges.bins
            for number, occurrences in pairs:
                counts[edges.index(number)] += occurrences
            histogram = _binned(edges.edges, counts, count, stats, quantiles, "range")
        return kind(
            **extra,
            count=count,
            distinct=len(pairs),
            numeric=stats,
            modes=[output_number(Fraction(number)) for number in modes[:MAX_MODES]],
            modes_truncated=len(modes) > MAX_MODES,
            histogram=histogram,
        )

    def _grid_level(
        self,
        kind: type[Level],
        members: list[_Group],
        numeric: NumericAccumulator,
        of: int,
        extra: dict[str, str | int],
    ) -> Level:
        """The metrics of groups that went on in bins: one grid of the width of
        their whole range, into which the grid of each group folds exactly."""
        count = numeric.count
        assert numeric.minimum is not None and numeric.maximum is not None
        minimum, maximum = Fraction(numeric.minimum), Fraction(numeric.maximum)
        exponent = smallest_exponent(minimum, maximum, self.bins)
        merged: dict[int, int] = {}
        for group in members:
            grid = group.grid
            assert grid is not None and grid.exponent <= exponent
            shift = exponent - grid.exponent
            for index, occurrences in grid.counts.items():
                merged[index >> shift] = merged.get(index >> shift, 0) + occurrences
        low, high = min(merged), max(merged)
        if sum(merged.values()) != count:
            raise ScanMismatch("the bins of the numbers do not add up to their count")
        width = Fraction(2) ** exponent
        edges = [minimum, *(index * width for index in range(low + 1, high + 1)), maximum]
        counts = [merged.get(index, 0) for index in range(low, high + 1)]
        quantiles = binned_quantiles(edges, counts, count, minimum, maximum)
        stats = _stats(numeric, of, None, self.max_values)
        # Bins hold no distinct count and no mode.
        return kind(
            **extra,
            count=count,
            distinct=None,
            numeric=stats,
            modes=None,
            modes_truncated=None,
            histogram=_binned(edges, counts, count, stats, quantiles, "grid"),
        )

    def _markers(self) -> MarkerEnumeration:
        """The markers as an enumeration of the values written with one."""
        counts = sorted(
            (
                (marker, group.parsed + group.ambiguous, group.parsed)
                for marker, group in self.groups.items()
            ),
            key=lambda item: (-item[1], item[0]),
        )
        total = sum(count for _, count, _ in counts)
        top = counts[0][1]
        rare = [count for _, count, _ in counts if Fraction(count, total) < RARE_SHARE]
        return MarkerEnumeration(
            kind=MARKER_KINDS[self.detector],  # type: ignore[arg-type]
            count=total,
            distinct=len(counts),
            listed=[
                MarkerCount(value=marker, count=count, parsed=parsed, share=round(count / total, 4))
                for marker, count, parsed in counts[:MAX_LISTED_MARKERS]
            ],
            truncated=len(counts) > MAX_LISTED_MARKERS,
            modes=[marker for marker, count, _ in counts if count == top][:MAX_MODES],
            dominant_share=round(top / total, 4),
            rare=RareMarkers(share_below=float(RARE_SHARE), markers=len(rare), count=sum(rare)),
            layout=MarkerLayout(
                before=self.before, after=self.after, spaced=self.spaced, unspaced=self.unspaced
            ),
        )


def _detector(field: FieldResult, detector: str) -> DetectorComplete:
    for result in field.detectors:
        if result.id == detector:
            if not isinstance(result, DetectorComplete):
                raise ScanMismatch(f"the {detector} detector of the scan is {result.status}")
            return result
    raise ScanMismatch(f"the scan has no {detector} detector for the field")


def _stats(
    numeric: NumericAccumulator, of: int, median: float | None, max_values: int
) -> NumericStats:
    """The members of the numeric block of a population; the median from the
    table, or ``limited`` once the numbers went on in bins."""
    block = numeric.finalize(Limited(reason=MAX_VALUES, limit=max_values), of)
    if not isinstance(block, Complete):
        raise Unrepresentable
    stats: NumericStats = block.value
    if median is not None:
        stats = stats.model_copy(update={"median": Complete[int | float](value=median)})
    return stats


def _binned(
    edges: list[Fraction],
    counts: list[int],
    count: int,
    stats: NumericStats,
    quantiles: list[Quantile],
    source: str,
) -> BinnedHistogram:
    written = [rounded(edge) for edge in edges]
    written[0], written[-1] = stats.min, stats.max
    return BinnedHistogram(
        strategy="linear",
        requested_strategy="linear",
        bounds_source=source,  # type: ignore[arg-type]
        count=count,
        min=stats.min,
        max=stats.max,
        edges=written,
        counts=counts,
        outside=OutsideBins(below=0, above=0),
        median=quantiles[2],
        quantiles=quantiles,
    )


def derive_from_samples(
    accumulator: MeasureAccumulator, field: FieldResult, cells: CellReader
) -> None:
    """Fill ``accumulator`` from the exact counts of a Scan that holds every
    distinct original value of the field, without reading the source. Raises
    ``ScanMismatch`` when the Scan does not hold them."""
    samples = field.values.samples
    if (
        samples.selection != "all"
        or samples.kept != samples.of
        or samples.long_texts is not None
        or any(entry.count_accuracy != "exact" for entry in samples.listed)
    ):
        raise ScanMismatch("the scan does not hold every distinct value with its exact count")
    strings = [entry for entry in samples.listed if entry.type == "string"]
    read = cells.cells(
        [str(entry.value) for entry in strings], numbers=False, measure=accumulator.detector
    )
    for entry, cell in zip(strings, read, strict=True):
        if cell.length >= 0:
            accumulator.add(cell.measure, entry.count)
    for entry in samples.listed:
        if entry.type != "string":
            accumulator.add_native(entry.count)
