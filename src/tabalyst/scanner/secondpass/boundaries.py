# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Where the edges of a histogram are placed (``deep.bin_strategy``).

The outer bounds are the exact minimum and maximum of the Scan whatever the
strategy. ``linear`` splits the range into bins of equal width;
``sample_quantile`` places the inner edges at quantiles of what the Scan kept of
the field, which suits a very skewed distribution: the row sample, whose rows
are drawn from the occurrences, then the bottom-k sample, which holds distinct
values. The counts per bin are read from the whole source either way.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from tabalyst.scanner.measures import UNCONVERTIBLE
from tabalyst.scanner.models import DatasetResult, FieldResult, NumericStats
from tabalyst.scanner.secondpass.accumulators import decimal_bounds
from tabalyst.scanner.secondpass.bins import BinEdges, linear_edges, quantile_edges
from tabalyst.scanner.secondpass.replay import CellReader, native_number


@dataclass(frozen=True, slots=True)
class Placement:
    """The edges of a histogram and how they were chosen."""

    edges: BinEdges
    strategy: str
    requested: str
    source: str
    reason: str | None
    # Whether the outer bounds are the exact minimum and maximum.
    tight: bool


def _numbers(reader: CellReader, texts: list[str]) -> list[Fraction]:
    """The numbers of texts the Scan kept for a field, read as the Scan read
    its values; texts that are not numbers are left out."""
    distinct = list(dict.fromkeys(texts))
    cells = dict(zip(distinct, reader.cells(distinct), strict=True))
    found: list[Fraction] = []
    for text in texts:
        number = cells[text].number
        if number is not None and number is not UNCONVERTIBLE:
            found.append(Fraction(number))
    return found


def row_numbers(dataset: DatasetResult, field: FieldResult, reader: CellReader) -> list[Fraction]:
    """The numbers of the field in the row sample, one per row that holds one:
    the shape of the occurrences."""
    sample = dataset.records.sample
    if sample is None or field.id not in sample.fields:
        return []
    texts: list[str] = []
    for row in sample.rows:
        if field.id in row.truncated:
            continue
        cell = row.values.get(field.id)
        if cell:
            texts.extend(text for text in cell if text is not None)
    return _numbers(reader.for_sample(field), texts)


def distinct_numbers(field: FieldResult, reader: CellReader) -> list[Fraction]:
    """The numbers among the distinct values of the bottom-k sample. A number of
    the source's own type is taken as it is, never read in a convention."""
    listed = field.values.samples.listed
    strings = list(dict.fromkeys(entry.value for entry in listed if entry.type == "string"))
    cells = dict(zip(strings, reader.for_field(field).cells(strings), strict=True))
    found: list[Fraction] = []
    for entry in listed:
        if entry.type == "string":
            number = cells[entry.value].number
        elif entry.type in ("integer", "number"):
            number = native_number(entry.type, entry.value)
        else:
            continue
        if number is not None and number is not UNCONVERTIBLE:
            found.append(Fraction(number))
    return found


def place_edges(
    dataset: DatasetResult,
    field: FieldResult,
    stats: NumericStats,
    bins: int,
    requested: str,
    reader: CellReader,
) -> Placement:
    """Choose the edges of the histogram of ``field``."""
    low = decimal_bounds(stats.min)[0]
    high = decimal_bounds(stats.max)[1]
    tight = isinstance(stats.min, int) and isinstance(stats.max, int)
    if requested == "sample_quantile":
        enough = 2 * bins
        source = "rows"
        sample = row_numbers(dataset, field, reader)
        if len(sample) < enough:
            source = "distinct"
            sample = distinct_numbers(field, reader)
        edges = quantile_edges(low, high, bins, sample) if len(sample) >= enough else None
        if edges is not None:
            return Placement(BinEdges(edges), "sample_quantile", requested, source, None, tight)
        reason = "sample_too_small" if len(sample) < enough else "sample_without_spread"
        return Placement(
            BinEdges(linear_edges(low, high, bins)), "linear", requested, "range", reason, tight
        )
    return Placement(
        BinEdges(linear_edges(low, high, bins)), "linear", requested, "range", None, tight
    )
