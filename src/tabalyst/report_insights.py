# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight cards of the report: what the later analyses of the second pass
found (values with a unit, shape of the numbers, parts of the dates, values
left out, repeated values, numbers by category) and the measures the report
derives from the Scan, laid out with the accuracy of each figure.

Computed when a page is rendered, from the document alone (HTML-01): no
source, no recomputation. An analysis that did not end ``complete`` or
``limited`` has no card; the second-pass table says why. The values of a
column whose exposure is ``mask`` or ``hide`` are never listed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from tabalyst.models import AnalysesBlock
from tabalyst.report_deep import CONVENTION_WORDS, shown
from tabalyst.report_labels import SHAPE_REASONS, STATS_REASONS, WEEKDAYS
from tabalyst.report_measures import (
    decades,
    dominant_share,
    empty_periods,
    frequency_tail,
    length_spread,
)
from tabalyst.report_views import (
    InsightBar,
    InsightBars,
    InsightCard,
    InsightFact,
    InsightKind,
    InsightTable,
)
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.secondpass.models import (
    AnalysisOutput,
    BinnedHistogram,
    DenseHistogram,
    DuplicateResult,
    DuplicatesLimited,
    MeasureLevel,
    MeasureResult,
    PartCount,
    PartsResult,
    PeriodCounts,
    Quantile,
    ResidualResult,
    ShapeResult,
    StatsResult,
    StatsSummary,
)

# Rows a table lists and bars a distribution draws; the document holds the rest.
MAX_ROWS = 15
MAX_BARS = 16
MAX_GROUPS = 25
# Units whose own distribution is drawn.
MAX_UNIT_BARS = 4

_HIDDEN = {"mask", "hide"}
_FAMILIES = {
    "measures": "Values with a unit",
    "shape": "Shape of the numbers",
    "parts": "Parts of the dates",
    "residuals": "Values left out",
    "duplicates": "Repeated values",
    "categories": "Numbers by category",
    "scan": "Read from the Scan",
}
FAMILY_ORDER = tuple(_FAMILIES)


def family_title(family: str) -> str:
    """The heading of a family of cards."""
    return _FAMILIES[family]


def _count(value: int) -> str:
    return f"{value:,}"


def _quantile(quantile: Quantile) -> tuple[str, InsightKind]:
    if quantile.accuracy == "exact":
        return shown(quantile.value), "exact"
    text = shown(quantile.value)
    if quantile.lower is not None and quantile.upper is not None:
        text += f" (between {shown(quantile.lower)} and {shown(quantile.upper)})"
    return text, "estimated"


def _bars(items: Iterable[tuple[str, int]], caption: str, *, note: str | None = None) -> InsightBars:
    pairs = list(items)
    total = sum(count for _, count in pairs)
    return InsightBars(
        caption=caption,
        items=[
            InsightBar(label=label, count=count, share=count / total if total else 0.0)
            for label, count in pairs
        ],
        note=note,
    )


def _grouped(labels: list[tuple[str, str]], counts: list[int]) -> list[tuple[str, int]]:
    """Consecutive ranges merged into at most ``MAX_BARS`` bars: the counts are
    sums, so they stay exact. ``labels`` are the first and last label of each."""
    step = -(-len(counts) // MAX_BARS) or 1
    merged: list[tuple[str, int]] = []
    for start in range(0, len(counts), step):
        end = min(start + step, len(counts)) - 1
        first, last = labels[start][0], labels[end][1]
        merged.append((first if first == last else f"{first} to {last}", sum(counts[start : end + 1])))
    return merged


def _histogram_bars(
    histogram: DenseHistogram | BinnedHistogram, caption: str
) -> InsightBars | None:
    if isinstance(histogram, DenseHistogram):
        values = histogram.values
        if not values:
            return None
        labels = [(_count(item.value),) * 2 for item in values]
        return _bars(_grouped(labels, [item.count for item in values]), caption)
    counts = histogram.counts
    if not counts:
        return None
    edges = histogram.edges
    labels = [(shown(edges[i]), shown(edges[i + 1])) for i in range(len(counts))]
    return _bars(
        _grouped(labels, counts),
        caption,
        note="Bins are [low, high); the last one includes its upper edge.",
    )


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.1%}" if whole else "0%"


def _facts_of_level(level: MeasureLevel, *, with_sum: bool = True) -> list[InsightFact]:
    stats = level.numeric
    median_text, median_kind = _quantile(level.histogram.median)
    facts = [
        InsightFact(label="Minimum", value=shown(stats.min)),
        InsightFact(label="Median", value=median_text, kind=median_kind),
        InsightFact(label="Mean", value=shown(stats.mean)),
        InsightFact(label="Maximum", value=shown(stats.max)),
    ]
    if with_sum:
        facts.append(InsightFact(label="Sum", value=shown(stats.sum)))
    return facts


def _measures_card(
    base: str, display: str, fields: list[str], result: MeasureResult, hidden: bool
) -> InsightCard:
    titles = {
        "currency": "Amounts",
        "percentage": "Percentages",
        "quantity": "Quantities with a unit",
    }
    marker = {"currency": "currency", "percentage": "sign", "quantity": "unit"}[result.detector]
    estimated = result.storage == "grid"
    facts = [
        InsightFact(label="Values", value=_count(result.values)),
        InsightFact(label="Numbers read", value=_count(result.parsed)),
    ]
    for label, count in (
        ("Ambiguous, not placed", result.ambiguous),
        ("Invalid shape", result.invalid),
        ("Not read", result.unparsed),
    ):
        if count:
            facts.append(InsightFact(label=label, value=_count(count)))
    notes: list[str] = []
    if result.resolution is not None:
        proof = result.resolution.evidence.get(result.resolution.convention, 0)
        facts.append(
            InsightFact(
                label="Ambiguous numbers read",
                value=(
                    f"{_count(result.resolved)} with the "
                    f"{CONVENTION_WORDS[result.resolution.convention]} convention"
                ),
                note=f"proved by {_count(proof)} unambiguous values of the column",
            )
        )
    if result.detector != "percentage":
        markers = result.markers
        facts.append(
            InsightFact(
                label=f"Distinct {marker}s" if marker != "currency" else "Distinct currencies",
                value=_count(markers.distinct),
            )
        )
        if markers.modes and not hidden:
            facts.append(
                InsightFact(
                    label=f"Dominant {marker}",
                    value=f"{markers.modes[0]} ({markers.dominant_share:.0%})",
                )
            )
        layout = markers.layout
        facts.append(
            InsightFact(
                label="Written",
                value=(
                    f"{marker} after the number {_count(layout.after)}, before it "
                    f"{_count(layout.before)}; with a space {_count(layout.spaced)}, "
                    f"without {_count(layout.unspaced)}"
                ),
            )
        )
    if result.percent_range is not None:
        span = result.percent_range
        facts.append(
            InsightFact(
                label="Percentages",
                value=(
                    f"{_count(span.below)} below 0, {_count(span.within)} from 0 to 100, "
                    f"{_count(span.above)} above 100"
                ),
                note="a share above 100 is a fact of the data, not an error",
            )
        )
    bars: list[InsightBars] = []
    tables: list[InsightTable] = []
    if result.homogeneous:
        facts.extend(_facts_of_level(result.overall))
        drawn = _histogram_bars(result.overall.histogram, "Distribution of the numbers")
        if drawn is not None:
            bars.append(drawn)
    else:
        notes.append(
            "The numbers mix several "
            f"{'currencies' if marker == 'currency' else marker + 's'}: no conversion is made, "
            "so the overall figures are not shown. Read each one alone."
        )
    if result.groups and not hidden:
        rows = []
        for group in result.groups[:MAX_GROUPS]:
            median, _ = _quantile(group.histogram.median)
            rows.append(
                [
                    group.marker,
                    _count(group.count),
                    shown(group.numeric.min),
                    median,
                    shown(group.numeric.mean),
                    shown(group.numeric.max),
                ]
            )
        if result.other is not None:
            median, _ = _quantile(result.other.histogram.median)
            rows.append(
                [
                    f"{_count(result.other.markers)} other {marker}s",
                    _count(result.other.count),
                    shown(result.other.numeric.min),
                    median,
                    shown(result.other.numeric.mean),
                    shown(result.other.numeric.max),
                ]
            )
        tables.append(
            InsightTable(
                caption=f"By {marker}",
                kind="estimated" if estimated else "exact",
                headers=[marker.capitalize(), "Numbers", "Minimum", "Median", "Mean", "Maximum"],
                rows=rows,
                code=[0],
                note=(
                    "Counts, minimum, mean and maximum are exact; medians are estimates "
                    "between certain bounds."
                    if estimated
                    else None
                ),
            )
        )
        if len(result.groups) > 1 or not result.homogeneous:
            for group in result.groups[:MAX_UNIT_BARS]:
                drawn = _histogram_bars(group.histogram, f"Distribution in {group.marker}")
                if drawn is not None:
                    bars.append(drawn)
    if result.computed_from == "samples":
        notes.append("Computed from the values the Scan kept: the source was not read.")
    return InsightCard(
        id=f"{base}-measures",
        family="measures",
        title=titles[result.detector],
        column=display,
        fields=fields,
        summary=f"{_count(result.parsed)} numbers read from {_count(result.values)} values.",
        facts=facts,
        bars=bars,
        tables=tables,
        notes=notes,
    )


def _shape_card(base: str, display: str, fields: list[str], result: ShapeResult) -> InsightCard:
    moments = result.moments
    tukey = result.tukey
    exact_quartiles = tukey.accuracy == "exact"
    facts: list[InsightFact] = []
    if moments.skewness is not None and moments.excess_kurtosis is not None:
        facts.append(
            InsightFact(
                label="Skewness",
                value=f"{moments.skewness:+.3f}",
                note="float64, relative error of a few units in 1e-12",
            )
        )
        facts.append(InsightFact(label="Excess kurtosis", value=f"{moments.excess_kurtosis:+.3f}"))
    else:
        facts.append(
            InsightFact(
                label="Skewness",
                value="undefined: "
                + SHAPE_REASONS.get(moments.reason or "", moments.reason or "undefined"),
            )
        )
    quartiles: InsightKind = "exact" if exact_quartiles else "estimated"
    q1, _ = _quantile(tukey.q1)
    q3, _ = _quantile(tukey.q3)
    facts.append(InsightFact(label="First quartile", value=q1, kind=quartiles))
    facts.append(InsightFact(label="Third quartile", value=q3, kind=quartiles))
    facts.append(InsightFact(label="Interquartile range", value=shown(tukey.iqr), kind=quartiles))
    for fence, name in zip(tukey.fences, ("Mild outliers", "Far outliers"), strict=False):
        below, above = fence.below, fence.above
        if exact_quartiles:
            value = (
                f"{_count(below.certain)} below {shown(fence.low)}, "
                f"{_count(above.certain)} above {shown(fence.high)}"
            )
        else:
            value = (
                f"{_count(below.certain)} to {_count(below.possible)} below {shown(fence.low)}, "
                f"{_count(above.certain)} to {_count(above.possible)} above {shown(fence.high)}"
            )
        facts.append(
            InsightFact(
                label=f"{name} (beyond {fence.factor:g} interquartile ranges)",
                value=value,
                kind="exact" if exact_quartiles else "estimated",
            )
        )
    scale = result.scale
    decimals = ", ".join(f"{_count(item.count)} with {item.places}" for item in scale.places[:6])
    facts.append(
        InsightFact(
            label="Decimals written",
            value=decimals + (", ..." if len(scale.places) > 6 else ""),
            note=(
                f"the precision varies up to {scale.max_places} decimals"
                if scale.mixed
                else None
            ),
        )
    )
    if scale.trailing_zero:
        facts.append(InsightFact(label="Ending in a 0", value=_count(scale.trailing_zero)))
    bars: list[InsightBars] = []
    if result.log is not None:
        drawn = _histogram_bars(result.log, "Bins of equal ratio (positive numbers)")
        if drawn is not None:
            bars.append(drawn)
    drawn = _histogram_bars(result.equal_count, "Bins of about equal counts")
    if drawn is not None:
        bars.append(drawn)
    notes = []
    if result.log is None and result.log_reason:
        notes.append(f"No bins of equal ratio: {result.log_reason.replace('_', ' ')}.")
    if result.storage == "grid":
        notes.append(
            "The distinct numbers passed the limit of the exact table: counts per bin are "
            "exact, the quartiles and the outliers are bracketed."
        )
    return InsightCard(
        id=f"{base}-shape",
        family="shape",
        title="Shape of the numbers",
        column=display,
        fields=fields,
        summary=f"{_count(result.count)} numbers.",
        facts=facts,
        bars=bars,
        notes=notes,
    )


def _part_bars(parts: list[PartCount], names: Iterable[str] | None, caption: str) -> InsightBars:
    labels = list(names) if names is not None else None
    return _bars(
        ((labels[item.value] if labels else f"{item.value:02d}h", item.count) for item in parts),
        caption,
    )


def _parts_card(base: str, display: str, fields: list[str], result: PartsResult) -> InsightCard:
    unit = "times" if result.temporal_kind == "time" else "dates"
    facts = [
        InsightFact(label="Values", value=_count(result.values)),
        InsightFact(label=f"Valid {unit}", value=_count(result.count)),
    ]
    if result.invalid:
        reasons = ", ".join(
            f"{item.reason.replace('_', ' ')} {_count(item.count)}"
            for item in result.invalid_reasons[:4]
        )
        facts.append(
            InsightFact(label="Invalid", value=_count(result.invalid), note=reasons or None)
        )
    if result.ambiguous:
        facts.append(InsightFact(label="Ambiguous, not placed", value=_count(result.ambiguous)))
    if result.resolution is not None:
        proof = result.resolution.evidence.get(result.resolution.order, 0)
        facts.append(
            InsightFact(
                label="Ambiguous dates read",
                value=f"{_count(result.resolved)} read as {result.resolution.order}",
                note=f"proved by {_count(proof)} unambiguous dates of the column",
            )
        )
    if result.after_as_of is not None:
        facts.append(
            InsightFact(label=f"After {result.as_of}", value=_count(result.after_as_of))
        )
    bars: list[InsightBars] = []
    if result.weekdays is not None:
        bars.append(_part_bars(result.weekdays, WEEKDAYS, "Day of the week"))
    if result.hours:
        bars.append(_part_bars(result.hours, None, "Hour"))
    if result.year_months:
        months = result.year_months
        if len(months) > 36:
            years: dict[str, int] = defaultdict(int)
            for item in months:
                years[item.period[:4]] += item.count
            labels = [(year, year) for year in years]
            bars.append(_bars(_grouped(labels, list(years.values())), "Year"))
        else:
            bars.append(_bars(((item.period, item.count) for item in months), "Month"))
    tables: list[InsightTable] = []
    simulation = result.simulation
    if simulation is not None:
        rows = []
        for reading in simulation.readings:
            busiest = (
                max(reading.weekdays, key=lambda part: (part.count, -part.value))
                if reading.weekdays
                else None
            )
            rows.append(
                [
                    reading.order,
                    _count(reading.placed),
                    WEEKDAYS[busiest.value] if busiest else "-",
                    _count(reading.after_as_of) if reading.after_as_of is not None else "-",
                ]
            )
        headers = ["Order", "Dates placed", "Busiest weekday", "After the cut-off"]
        if result.after_as_of is None:
            headers.pop()
            rows = [row[:-1] for row in rows]
        tables.append(
            InsightTable(
                caption=f"If the {_count(simulation.ambiguous)} ambiguous dates were read as",
                headers=headers,
                rows=rows,
                note="Nothing is applied: this measures what the choice of an order would change.",
            )
        )
    notes = ["Dates and hours are counted as written; an offset is never converted."]
    return InsightCard(
        id=f"{base}-parts",
        family="parts",
        title="Parts of the dates" if unit == "dates" else "Parts of the times",
        column=display,
        fields=fields,
        summary=f"{_count(result.count)} {unit}.",
        facts=facts,
        bars=bars,
        tables=tables,
        notes=notes,
    )


def _residuals_card(
    base: str, display: str, fields: list[str], result: ResidualResult, hidden: bool
) -> InsightCard:
    exact = result.accuracy == "exact"
    facts = [InsightFact(label="Values read", value=_count(result.values))]
    tables: list[InsightTable] = []
    notes: list[str] = []
    for index, table in enumerate(result.tables):
        what = (
            "no pattern reads them"
            if table.source == "pattern"
            else f"{table.detector} found them {table.state.replace('_', ' ')}"
        )
        kind: InsightKind = "exact" if table.complete else "at_least"
        facts.append(
            InsightFact(
                label=f"Left out: {what}",
                value=f"{_count(table.occurrences)} occurrences",
                note=(
                    f"{_count(table.distinct)} distinct values"
                    if table.complete
                    else f"at least {_count(table.distinct)} distinct values tracked"
                ),
                kind="exact",
            )
        )
        if table.reasons:
            tables.append(
                InsightTable(
                    caption=f"Why {table.detector} found them invalid",
                    headers=["Reason", "Occurrences"],
                    rows=[[item.reason.replace("_", " "), _count(item.count)] for item in table.reasons],
                )
            )
        if hidden:
            continue
        rows = [
            [item.value, _count(item.count), _count(item.first_record) if item.first_record else "-"]
            for item in table.listed[:MAX_ROWS]
        ]
        if rows:
            tables.append(
                InsightTable(
                    caption=f"Most frequent values left out ({index + 1})",
                    kind=kind,
                    headers=["Value", "Occurrences", "First record"],
                    rows=rows,
                    code=[0],
                    note=(
                        None
                        if table.complete and len(table.listed) <= MAX_ROWS
                        else "The list is bounded; the occurrences of the values it holds are exact."
                    ),
                )
            )
    if result.patterns:
        tables.append(
            InsightTable(
                caption="Each pattern over every occurrence",
                headers=["Pattern", "Occurrences", "Distinct values", "Example", "First record"],
                rows=[
                    [
                        item.render,
                        _count(item.occurrences),
                        ("" if item.distinct_accuracy == "exact" else "at least ")
                        + _count(item.distinct),
                        "-" if hidden or item.example is None else item.example,
                        _count(item.first_record) if item.first_record else "-",
                    ]
                    for item in result.patterns[:MAX_ROWS]
                ],
                code=[0, 3],
            )
        )
    if result.detectors:
        tables.append(
            InsightTable(
                caption="Detectors replayed on every value",
                headers=["Detector", "Eligible", "Matched", "Ambiguous", "Invalid", "Not matched"],
                rows=[
                    [
                        item.detector,
                        _count(item.eligible),
                        _count(item.matched),
                        _count(item.ambiguous),
                        _count(item.invalid),
                        _count(item.not_matched),
                    ]
                    for item in result.detectors
                ],
                code=[0],
            )
        )
    if hidden:
        notes.append("The values are withheld by the exposure setting of the column.")
    if result.computed_from == "samples":
        notes.append("Computed from the values the Scan kept: no first record, the source was not read.")
    if not exact:
        notes.append("Occurrences are exact; some lists or distinct counts are bounded.")
    return InsightCard(
        id=f"{base}-residuals",
        family="residuals",
        title="Values left out by patterns and detectors",
        column=display,
        fields=fields,
        summary=f"{_count(result.values)} values read.",
        facts=facts,
        tables=tables,
        notes=notes,
    )


def _duplicates_card(
    base: str,
    display: str,
    fields: list[str],
    result: DuplicateResult | DuplicatesLimited,
    hidden: bool,
) -> InsightCard:
    if isinstance(result, DuplicatesLimited):
        return InsightCard(
            id=f"{base}-duplicates",
            family="duplicates",
            title="Repeated values",
            column=display,
            fields=fields,
            summary=f"At least {_count(result.repeated)} repeated values.",
            facts=[
                InsightFact(label="Values read before the stop", value=_count(result.values_read)),
                InsightFact(
                    label="Distinct values", value=f"at least {_count(result.distinct)}", kind="at_least"
                ),
                InsightFact(
                    label="Repeated values", value=f"at least {_count(result.repeated)}", kind="at_least"
                ),
            ],
            notes=["The search stopped when its memory budget was spent: these are lower bounds."],
        )
    facts = [
        InsightFact(label="Values read", value=_count(result.values)),
        InsightFact(label="Distinct values", value=_count(result.distinct)),
    ]
    if result.incomplete:
        facts.append(InsightFact(label="Rows with a column missing", value=_count(result.incomplete)))
    notes: list[str] = []
    tables: list[InsightTable] = []
    if result.unique:
        facts.append(InsightFact(label="Repeated values", value="none, every value is different"))
    else:
        repeated = result.repeated
        facts.append(InsightFact(label="Values found more than once", value=_count(repeated.distinct)))
        facts.append(InsightFact(label="Extra occurrences", value=_count(result.redundant)))
        if hidden:
            notes.append("The values are withheld by the exposure setting of the column.")
        else:
            headers = [" and ".join(result.columns) if result.columns else "Value", "Occurrences", "First record"]
            tables.append(
                InsightTable(
                    caption="Most repeated values",
                    kind="exact",
                    headers=headers,
                    rows=[
                        [
                            " | ".join(item.value) if isinstance(item.value, list) else item.value,
                            _count(item.count),
                            _count(item.first_record) if item.first_record else "-",
                        ]
                        for item in repeated.listed[:MAX_ROWS]
                    ],
                    code=[0],
                    note=(
                        None
                        if repeated.complete and len(repeated.listed) <= MAX_ROWS
                        else "The list is bounded; the counts of the values it holds are exact."
                    ),
                )
            )
    if result.computed_from == "samples":
        notes.append("Computed from the values the Scan kept: no first record, the source was not read.")
    return InsightCard(
        id=f"{base}-duplicates",
        family="duplicates",
        title="Repeated values" if not result.columns else "Repeated combinations",
        column=display,
        fields=fields,
        summary="No repeated value." if result.unique else f"{_count(result.repeated.distinct)} values found more than once.",
        facts=facts,
        tables=tables,
        notes=notes,
    )


def _stats_row(label: str, rows: int, summary: StatsSummary) -> list[str]:
    median = summary.median
    return [
        label,
        _count(rows),
        _count(summary.count),
        "-" if summary.min is None else shown(summary.min),
        "-" if median is None else _quantile(median)[0].split(" (")[0],
        "-" if summary.mean is None else shown(summary.mean),
        "-" if summary.max is None else shown(summary.max),
    ]


def _stats_card(
    base: str, display: str, fields: list[str], result: StatsResult, hidden: bool
) -> InsightCard:
    excluded = result.excluded
    facts = [
        InsightFact(label="Rows", value=_count(result.rows)),
        InsightFact(label="Rows with a category and a number", value=_count(result.counted)),
    ]
    for label, count in (
        ("Rows without a category", excluded.category_missing),
        ("Rows without a number", excluded.value_missing),
        ("Rows with neither", excluded.both_missing),
    ):
        if count:
            facts.append(InsightFact(label=label, value=_count(count)))
    found = result.association
    if found.epsilon_squared is not None and found.eta_squared is not None:
        facts.append(
            InsightFact(
                label="Share of the variance the categories explain",
                value=f"{found.eta_squared:.1%}",
                note=f"{found.epsilon_squared:.1%} once corrected for the number of categories",
            )
        )
    else:
        facts.append(
            InsightFact(
                label="Share of the variance the categories explain",
                value="no score: "
                + STATS_REASONS.get(found.reason or "", found.reason or "undefined"),
            )
        )
    tables: list[InsightTable] = []
    notes = [
        (
            "An association between two columns, not a cause. Counts are exact; the "
            "minimum, maximum, mean and spread are computed in float64; medians are "
            "estimates between certain bounds."
        )
    ]
    if hidden:
        notes.append("The categories are withheld by the exposure setting of the column.")
    else:
        classes = result.categories.classes
        ranked = sorted(
            (
                (item.label, group)
                for item, group in zip(classes, result.groups, strict=False)
                if group.rows
            ),
            key=lambda pair: -pair[1].rows,
        )
        rows = [_stats_row(label, group.rows, group) for label, group in ranked]
        tables.append(
            InsightTable(
                caption=f"{display} by category",
                kind="estimated",
                headers=["Category", "Rows", "Numbers", "Minimum", "Median", "Mean", "Maximum"],
                rows=rows[:MAX_GROUPS],
                code=[0],
                note=(
                    f"The {len(rows) - MAX_GROUPS} categories with the fewest rows are in the report JSON."
                    if len(rows) > MAX_GROUPS
                    else None
                ),
            )
        )
    return InsightCard(
        id=f"{base}-categories",
        family="categories",
        title="Numbers by category",
        column=display,
        fields=fields,
        summary=f"{_count(result.counted)} of {_count(result.rows)} rows.",
        facts=facts,
        tables=tables,
        notes=notes,
    )


def _card_of(
    item_id: str,
    display: str,
    fields: list[str],
    result: AnalysisOutput,
    hidden: bool,
) -> InsightCard | None:
    if isinstance(result, MeasureResult):
        return _measures_card(item_id, display, fields, result, hidden)
    if isinstance(result, ShapeResult):
        return _shape_card(item_id, display, fields, result)
    if isinstance(result, PartsResult):
        return _parts_card(item_id, display, fields, result)
    if isinstance(result, ResidualResult):
        return _residuals_card(item_id, display, fields, result, hidden)
    if isinstance(result, DuplicateResult | DuplicatesLimited):
        return _duplicates_card(item_id, display, fields, result, hidden)
    if isinstance(result, StatsResult):
        return _stats_card(item_id, display, fields, result, hidden)
    return None


def dataset_insights(
    analyses: AnalysesBlock | None,
    dataset: str,
    exposure: Mapping[str, str | None],
) -> list[InsightCard]:
    """The cards of the second pass for one dataset, grouped by family in the
    order of ``FAMILY_ORDER``, then in the order of the columns. ``exposure``
    maps a field id to its exposure setting."""
    if analyses is None or analyses.deep is None:
        return []
    cards: list[InsightCard] = []
    for item in analyses.deep.analyses:
        if item.dataset != dataset or item.result is None:
            continue
        if item.status not in ("complete", "limited"):
            continue
        fields = [item.field] + ([item.partner] if item.partner else [])
        hidden = any(exposure.get(field) in _HIDDEN for field in fields)
        card = _card_of(
            f"i-{len(cards) + 1}-{item.analyzer.replace('_', '-')}",
            item.display,
            fields,
            item.result,
            hidden,
        )
        if card is not None:
            cards.append(card)
    order = {family: index for index, family in enumerate(FAMILY_ORDER)}
    return sorted(cards, key=lambda card: order[card.family])


def shown_cards(cards: list[InsightCard], per_family: int) -> list[InsightCard]:
    """The cards the dataset panel prints: ``per_family`` at most of each family,
    so that a family with many columns does not push the others out."""
    taken: dict[str, int] = defaultdict(int)
    kept = []
    for card in cards:
        taken[card.family] += 1
        if taken[card.family] <= per_family:
            kept.append(card)
    return kept


def scan_insight(
    field: FieldResult,
    display: str,
    field_id: str,
    periods: PeriodCounts | None,
    hidden: bool,
) -> InsightCard | None:
    """The measures the report derives from the Scan for one column (lengths,
    tail of the frequencies, dominant unit, decades, empty periods); ``None``
    when the Scan holds none of them. They are exact, or said to be bounded."""
    facts: list[InsightFact] = []
    spread = length_spread(field)
    if spread is not None and spread.q25 != spread.q75:
        facts.append(
            InsightFact(
                label="Lengths, quartiles",
                value=f"{spread.q25}, {spread.median}, {spread.q75} characters",
                note=f"interquartile range {spread.iqr}",
            )
        )
    tail = frequency_tail(field)
    if tail is not None:
        facts.append(
            InsightFact(
                label="Values outside the listed frequencies",
                value=f"{_count(tail.values)} of {_count(tail.of)} ({_share(tail.values, tail.of)})",
            )
        )
    dominant = None if hidden else dominant_share(field)
    if dominant is not None:
        kind: InsightKind = "exact" if dominant.exact else "at_least"
        facts.append(
            InsightFact(
                label="Dominant unit" if dominant.detector == "quantity" else "Dominant currency",
                value=f"{dominant.value}: {_count(dominant.count)} of {_count(dominant.total)}",
                kind=kind,
                note=None if dominant.exact else "the listing of the detector was cut",
            )
        )
    tens = decades(field)
    if tens:
        facts.append(
            InsightFact(
                label="Dates by decade",
                value=", ".join(f"{item.decade}s {_count(item.count)}" for item in tens[:8])
                + (", ..." if len(tens) > 8 else ""),
            )
        )
    if periods is not None:
        gaps = empty_periods(periods.granularity, [item.period for item in periods.periods])
        if gaps is not None:
            facts.append(
                InsightFact(
                    label=f"Empty {periods.granularity}s between the first and the last date",
                    value=f"{_count(gaps.empty)} of {_count(gaps.periods)}",
                    note=(
                        f"longest run {_count(gaps.longest)}, {gaps.longest_from} to {gaps.longest_to}"
                        if gaps.longest
                        else None
                    ),
                )
            )
    if not facts:
        return None
    return InsightCard(
        id=f"s-{field_id}",
        family="scan",
        title="Read from the Scan",
        column=display,
        fields=[field_id],
        source="scan",
        summary="Derived from the Scan, without reading the source again.",
        facts=facts,
    )
