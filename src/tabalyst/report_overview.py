# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Overview of a column: one short sentence per profile, computed at render time.

Facts only, read from the classification and from the measures the column view
already holds (contract summary-table.md 7.1). Never serialized; a limited
measure is worded "at least" or left out, never said exact.
"""

from __future__ import annotations

from typing import Literal

from tabalyst.models import ResultModel
from tabalyst.report_labels import (
    OVERVIEW_COMPOSITION,
    OVERVIEW_KINDS,
    OVERVIEW_NUMERIC,
    OVERVIEW_SHAPED,
    OVERVIEW_TEMPORAL,
    OVERVIEW_TEXT,
    format_number,
    plural,
)
from tabalyst.report_measures import dominant_share
from tabalyst.report_views import ColumnView
from tabalyst.scanner.models import Complete

OverviewAccuracy = Literal["exact", "lower_bound"]


class OverviewFact(ResultModel):
    """A figure the sentence uses, with the accuracy it is worded with."""

    name: str
    value: int | float | str
    accuracy: OverviewAccuracy = "exact"


class Overview(ResultModel):
    """The sentence of a column and the facts behind it."""

    text: str
    facts: list[OverviewFact]


class _Builder:
    """Collects the facts of a sentence while the words are written."""

    def __init__(self) -> None:
        self.facts: list[OverviewFact] = []

    def count(self, name: str, value: int, accuracy: OverviewAccuracy = "exact") -> str:
        """``value`` as a number, with ``at least`` when it is a lower bound."""
        self.facts.append(OverviewFact(name=name, value=value, accuracy=accuracy))
        prefix = "at least " if accuracy == "lower_bound" else ""
        return f"{prefix}{value:,}"

    def counted(
        self,
        name: str,
        value: int,
        accuracy: OverviewAccuracy,
        one: str,
        many: str,
    ) -> str:
        """``value`` with the noun that agrees with it: ``1 format``, ``at least
        3 formats``."""
        self.facts.append(OverviewFact(name=name, value=value, accuracy=accuracy))
        prefix = "at least " if accuracy == "lower_bound" else ""
        return f"{prefix}{plural(value, one, many)}"

    def share(self, name: str, value: float) -> str:
        self.facts.append(OverviewFact(name=name, value=value))
        text = f"{value:.1%}"
        # Rounding must not claim that one value holds everything when it does not.
        return "more than 99.9%" if value < 1 and text == "100.0%" else text


def _distinct(column: ColumnView, build: _Builder, one: str, many: str) -> str | None:
    """The distinct values as a phrase (``12 categories``), or ``None`` when the
    scan did not count."""
    view = column.distinct
    if view.kind == "not_counted" or view.value is None:
        return None
    accuracy: OverviewAccuracy = "exact" if view.kind == "exact" else "lower_bound"
    return build.counted("distinct", view.value, accuracy, one, many)


def _formats(column: ColumnView, build: _Builder) -> str | None:
    """The recurring formats of the patterns, ``None`` when there is none to tell."""
    view = column.patterns
    if view.status != "complete" or view.entry is None or not view.rows:
        return None
    whole = view.entry.population.complete and not view.outside_distinct
    return build.counted(
        "formats",
        len(view.rows),
        "exact" if whole else "lower_bound",
        "recurring format",
        "recurring formats",
    )


def _top_share(column: ColumnView, build: _Builder) -> str | None:
    """Share of the present values held by the most frequent one. The listing is
    ranked by count, so the share is exact even when the table is cut."""
    frequencies = column.field.values.frequencies
    present = column.field.values.count
    if not isinstance(frequencies, Complete) or not frequencies.value.listed or not present:
        return None
    return build.share("top_share", frequencies.value.listed[0].count / present)


def _unique_id(column: ColumnView, build: _Builder) -> str:
    present = column.field.values.count
    text = f"All {build.count('present', present)} present values are distinct"
    if any(item.scope.partial for item in column.classification.evidence):
        text += " in the records the scan accepted"
    formats = _formats(column, build)
    return f"{text}, in {formats}." if formats else f"{text}."


def _identifier(column: ColumnView, build: _Builder) -> str:
    distinct = _distinct(column, build, "distinct value", "distinct values")
    formats = _formats(column, build)
    if distinct is None:
        return "Identifier values; their distinct count was not computed."
    text = f"{distinct[0].upper()}{distinct[1:]}"
    return f"{text} across {formats}." if formats else f"{text}."


def _enum(column: ColumnView, build: _Builder) -> str:
    distinct = _distinct(column, build, "category", "categories")
    top = _top_share(column, build)
    text = f"{distinct[0].upper()}{distinct[1:]}" if distinct else "Categories"
    return f"{text}; the most frequent holds {top} of present values." if top else f"{text}."


def _boolean(column: ColumnView, build: _Builder) -> str:
    top = _top_share(column, build)
    if top is None:
        return "Boolean-like values."
    return f"Boolean-like values; the more frequent state holds {top} of present values."


def _constant(column: ColumnView, build: _Builder) -> str:
    present = build.counted(
        "present", column.field.values.count, "exact", "present position", "present positions"
    )
    return f"One value on all {present}."


def _numeric(column: ColumnView, build: _Builder) -> str:
    text = OVERVIEW_NUMERIC[column.classification.type]
    stats = column.numeric
    if stats is not None:
        low = format_number(stats.minimum)
        high = format_number(stats.maximum)
        build.facts.append(OverviewFact(name="minimum", value=stats.minimum))
        build.facts.append(OverviewFact(name="maximum", value=stats.maximum))
        text += f" ranging from {low} to {high}"
        if stats.median is not None:
            build.facts.append(OverviewFact(name="median", value=stats.median))
            text += f", with a median of {format_number(stats.median)}"
    dominant = dominant_share(column.field)
    # The marker is a value of the source: it follows the exposure of the column,
    # and only the detector that classified the column may speak for it.
    if (
        dominant is not None
        and dominant.detector == column.classification.type
        and column.exposure in (None, "show")
    ):
        accuracy: OverviewAccuracy = "exact" if dominant.exact else "lower_bound"
        build.facts.append(
            OverviewFact(name="dominant", value=dominant.value, accuracy=accuracy)
        )
        word = "most often" if dominant.exact else "often"
        text += f"; {word} {dominant.value}"
    return f"{text}."


def _temporal(column: ColumnView, build: _Builder) -> str:
    noun = OVERVIEW_TEMPORAL[column.classification.type]
    temporal = column.field.temporal
    if not isinstance(temporal, Complete) or not temporal.value.kinds:
        return f"{noun}; their range was not computed."
    parts = []
    for kind in temporal.value.kinds:
        low, high = kind.min[:10], kind.max[:10]
        build.facts.append(OverviewFact(name=f"{kind.kind}_minimum", value=low))
        build.facts.append(OverviewFact(name=f"{kind.kind}_maximum", value=high))
        parts.append(f"{OVERVIEW_KINDS[kind.kind]} range from {low} to {high}")
    text = "; ".join(parts)
    profile = column.date_profile
    if profile is not None and profile.format_count:
        formats = build.counted(
            "formats",
            profile.format_count,
            "exact",
            "recognized format",
            "recognized formats",
        )
        text += f", in {formats}"
    # Ambiguous values are excluded from the range (design 9.6); their number is
    # an Issue and is not repeated here.
    if temporal.value.ambiguous:
        text += " (ambiguous dates left out of the range)"
    return f"{text}."


def _shaped(column: ColumnView, build: _Builder) -> str:
    kind = column.classification.type
    text = OVERVIEW_SHAPED[kind]
    detector = next((item for item in column.detectors if item.id == kind), None)
    if detector is None or not detector.formats:
        return f"{text}."
    count = len(detector.formats)
    partial = detector.adaptive is not None or bool(
        detector.coverage and detector.coverage.not_tested
    )
    figure = build.counted(
        "formats",
        count,
        "lower_bound" if partial else "exact",
        "recognized format",
        "recognized formats",
    )
    return f"{text} in {figure}."


def _text(column: ColumnView, build: _Builder) -> str:
    kind = column.classification.type
    noun = OVERVIEW_TEXT.get(kind)
    profile = column.string_profile
    if noun is None or profile is None:
        return "Text; its length class is not determined."
    median = profile.median_length
    build.facts.append(OverviewFact(name="median_length", value=median))
    text = f"{noun}, with a median length of {format_number(median)} characters"
    distinct = _distinct(column, build, "distinct value", "distinct values")
    if distinct:
        text += f" and {distinct}"
    return f"{text}."


def _mixed(column: ColumnView, build: _Builder) -> str:
    kinds = sorted(
        {
            OVERVIEW_COMPOSITION[name]
            for name, count in column.type_counts.items()
            if count and name in OVERVIEW_COMPOSITION
        }
    )
    build.facts.extend(OverviewFact(name="composition", value=name) for name in kinds)
    if len(kinds) < 2:
        return "Present values mix several representations."
    return f"Present values combine {', '.join(kinds[:-1])} and {kinds[-1]} representations."


def _overview(column: ColumnView, build: _Builder) -> str:
    family = column.classification.family
    kind = column.classification.type
    if kind == "unique_id":
        return _unique_id(column, build)
    if kind == "id":
        return _identifier(column, build)
    if kind == "enum":
        return _enum(column, build)
    if kind == "boolean":
        return _boolean(column, build)
    if kind == "constant":
        return _constant(column, build)
    if family == "numeric":
        return _numeric(column, build)
    if family == "temporal":
        return _temporal(column, build)
    if kind in OVERVIEW_SHAPED:
        return _shaped(column, build)
    if family == "text":
        return _text(column, build)
    if kind == "mixed":
        return _mixed(column, build)
    if kind == "empty":
        return "No present values in the analyzed scope."
    return "Values fit more than one type; none is established."


def overview_for(column: ColumnView) -> Overview:
    """The sentence of a column with the facts it uses."""
    build = _Builder()
    text = _overview(column, build)
    return Overview(text=text, facts=build.facts)


def overview_text(column: ColumnView) -> str:
    """Only the sentence of a column."""
    return overview_for(column).text
