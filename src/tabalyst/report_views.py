# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Views of a report document that its pages read: the projections with the
canonical facts of their field and the figures derived from them.

The document stores the facts once, in its base, and the projections of
``tabalyst.models``; nothing here is serialized. The views are computed when a
page is rendered (design 19.3).
"""

from typing import Literal

from pydantic import FiniteFloat

from tabalyst.models import ColumnProfile, DatasetProfile, ResultModel
from tabalyst.scanner.models import FieldResult


class NumericStats(ResultModel):
    minimum: FiniteFloat
    maximum: FiniteFloat
    range: FiniteFloat
    mean: FiniteFloat
    # Null when the scan limited the median (its frequency table was released).
    median: FiniteFloat | None


class DateFormatCount(ResultModel):
    format: str
    # Null for formats that are not numeric dates (month names, times).
    order: Literal["YMD", "MDY", "DMY"] | None
    separator: str | None
    count: int
    percent: float
    iso: bool = False


class DateBreakdownItem(ResultModel):
    label: str
    category: Literal["valid", "ambiguous", "invalid", "not_date"]
    count: int
    percent: float


class DateProfile(ResultModel):
    status: Literal["valid", "multiple_formats", "mixed", "ambiguous", "invalid"]
    present_count: int
    valid_count: int
    valid_percent: float
    ambiguous_count: int
    ambiguous_percent: float
    invalid_date_count: int
    invalid_date_percent: float
    not_date_count: int
    not_date_percent: float
    resolved_ambiguous_order: Literal["MDY", "DMY"] | None = None
    ambiguous_order_source: Literal["config"] | None = None
    # Unambiguous values per day-month order, exposed and never applied.
    ambiguity_evidence: dict[str, int]
    formats: list[DateFormatCount]
    format_count: int
    breakdown: list[DateBreakdownItem]


class StringLengthExample(ResultModel):
    value: str
    count: int


class StringLengthDistribution(ResultModel):
    length: int
    count: int
    percent: float
    relative_percent: float
    examples: list[StringLengthExample]


class StringProfile(ResultModel):
    status: Literal["very_short", "short", "medium", "long", "very_long"]
    present_count: int
    minimum_length: int
    maximum_length: int
    mean_length: FiniteFloat
    median_length: FiniteFloat
    distinct_length_count: int
    fixed_length: int | None = None
    length_distribution: list[StringLengthDistribution]
    representative_examples: list[str]


class ColumnView(ColumnProfile):
    """A column projection with the canonical facts of its field (``field``,
    read as the scan wrote them) and the figures the pages derive from them."""

    field: FieldResult
    numeric: NumericStats | None
    date_profile: DateProfile | None
    string_profile: StringProfile | None


class DatasetView(DatasetProfile):
    """A dataset projection whose columns are ``ColumnView`` objects."""

    columns: list[ColumnView]  # type: ignore[assignment]
