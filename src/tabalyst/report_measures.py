# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measures that the report derives from blocks the Scan already holds: the
quantiles of the string lengths, the tail of the frequencies, the dominant unit
or marker of a detector, the decades of the dates and the empty periods of
their distribution over time.

Computed when a page is rendered, from the document alone (HTML-01): no source
is read, nothing is written to the document. A block that is limited or
missing gives ``None`` (not computed), never a value rebuilt from less.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from typing import Any

from tabalyst.scanner.models import Complete, DetectorComplete, FieldResult

LENGTH_QUANTILES = ((1, 4), (1, 2), (3, 4))
# Detector members that count a unit or a marker, and what they are called.
DOMINANT_MEMBERS = {"quantity": "units", "currency": "currencies"}


@dataclass(frozen=True)
class LengthSpread:
    """Nearest-rank quantiles of the string lengths (exact: the histogram is)."""

    q25: int
    median: int
    q75: int

    @property
    def iqr(self) -> int:
        return self.q75 - self.q25


@dataclass(frozen=True)
class FrequencyTail:
    """Values outside the listed frequencies. ``share`` is exact when the
    frequency table is complete, which is the only case this is computed for."""

    values: int
    of: int

    @property
    def share(self) -> float:
        return self.values / self.of if self.of else 0.0


@dataclass(frozen=True)
class DominantShare:
    """The most frequent unit or marker of a detector and its share of the
    values the detector counted for it. ``exact`` is false when the listing of
    the detector was cut: the share is then a ceiling for the dominant one and
    ``total`` a floor."""

    detector: str
    value: str
    count: int
    total: int
    exact: bool

    @property
    def share(self) -> float:
        return self.count / self.total if self.total else 0.0


@dataclass(frozen=True)
class DecadeCount:
    decade: int
    count: int


def length_spread(field: FieldResult) -> LengthSpread | None:
    """Quartiles of the lengths, from the exact length histogram."""
    lengths = field.string_lengths
    if not isinstance(lengths, Complete) or not lengths.value.count:
        return None
    total = lengths.value.count
    ordered = sorted(lengths.value.length_histogram, key=lambda item: item.length)
    found: list[int] = []
    for numerator, denominator in LENGTH_QUANTILES:
        rank = max(1, -(-total * numerator // denominator))
        seen = 0
        for item in ordered:
            seen += item.count
            if seen >= rank:
                found.append(item.length)
                break
    return LengthSpread(*found)


def frequency_tail(field: FieldResult) -> FrequencyTail | None:
    """Values that the listed frequencies leave out; ``None`` when the table is
    limited or when the listing is whole (there is no tail)."""
    frequencies = field.values.frequencies
    if not isinstance(frequencies, Complete) or not frequencies.value.truncated:
        return None
    listed = sum(item.count for item in frequencies.value.listed)
    return FrequencyTail(values=field.values.count - listed, of=field.values.count)


def _counts(member: Any) -> tuple[dict[str, int], bool] | None:
    """Counts by value of a detector detail and whether the listing is whole.
    A detail is either a plain mapping (currencies) or an envelope."""
    if hasattr(member, "model_dump"):
        member = member.model_dump()
    if not isinstance(member, dict):
        return None
    if "status" in member:
        if member.get("status") != "complete":
            return None
        value = member["value"]
        listed = {item["value"]: item["count"] for item in value["listed"]}
        return listed, not value["truncated"]
    return {str(key): int(count) for key, count in member.items()}, True


def dominant_share(field: FieldResult) -> DominantShare | None:
    """The dominant unit of a ``quantity`` field or marker of a ``currency``
    field. Uses the detector with the most values when several carry one."""
    best: DominantShare | None = None
    for result in field.detectors:
        member = DOMINANT_MEMBERS.get(result.id)
        if member is None or not isinstance(result, DetectorComplete):
            continue
        found = _counts(result.details.get(member))
        if found is None or not found[0]:
            continue
        counts, whole = found
        value, count = max(counts.items(), key=lambda item: (item[1], item[0]))
        total = sum(counts.values()) if whole else max(
            sum(counts.values()), result.coverage.matched + result.coverage.ambiguous
        )
        candidate = DominantShare(result.id, value, count, total, whole)
        if best is None or candidate.total > best.total:
            best = candidate
    return best


def decades(field: FieldResult) -> list[DecadeCount] | None:
    """Dates per decade (the year floored to a multiple of ten), from the
    years of the temporal block; ``None`` when a kind has no per-year counts."""
    temporal = field.temporal
    if not isinstance(temporal, Complete) or not temporal.value.kinds:
        return None
    total: Counter[int] = Counter()
    for kind in temporal.value.kinds:
        if kind.years is None:
            return None
        for item in kind.years:
            total[item.year // 10 * 10] += item.count
    return [DecadeCount(decade, count) for decade, count in sorted(total.items())]


@dataclass(frozen=True)
class EmptyPeriods:
    """The periods without a date between the first and the last one that has
    one, and the longest run of them (``longest_from`` to ``longest_to``, in
    periods of ``granularity``)."""

    granularity: str
    periods: int
    empty: int
    longest: int
    longest_from: str | None
    longest_to: str | None


def _ordinal(period: str, granularity: str) -> int:
    """The position of a period label (``YYYY-MM-DD``, ``YYYY-MM`` or ``YYYY``)
    on a line of periods of that granularity."""
    if granularity == "day":
        return date.fromisoformat(period).toordinal()
    if granularity == "month":
        year, month = period.split("-")
        return int(year) * 12 + int(month) - 1
    return int(period)


def _label(ordinal: int, granularity: str) -> str:
    if granularity == "day":
        return date.fromordinal(ordinal).isoformat()
    if granularity == "month":
        return f"{ordinal // 12:04d}-{ordinal % 12 + 1:02d}"
    return f"{ordinal:04d}"


def empty_periods(granularity: str, periods: list[str]) -> EmptyPeriods | None:
    """The gaps in the non-empty ``periods`` (ascending labels of a distribution
    over time), or ``None`` for fewer than two periods. Derived at render time
    from the document: ``datetime_parts`` does not store them."""
    if len(periods) < 2:
        return None
    ordinals = [_ordinal(period, granularity) for period in periods]
    longest = 0
    start = end = None
    empty = 0
    for before, after in pairwise(ordinals):
        gap = after - before - 1
        empty += gap
        if gap > longest:
            longest, start, end = gap, before + 1, after - 1
    return EmptyPeriods(
        granularity=granularity,
        periods=ordinals[-1] - ordinals[0] + 1,
        empty=empty,
        longest=longest,
        longest_from=None if start is None else _label(start, granularity),
        longest_to=None if end is None else _label(end, granularity),
    )
