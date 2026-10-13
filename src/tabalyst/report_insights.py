# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight cards of the report: what the later analyses of the second pass
found (values with a unit, shape of the numbers, parts of the dates, values
left out, repeated values, numbers by category, drift along the file, columns
missing together, lengths of arrays and sets of keys, long texts, masks and
classes of sensitive columns) and the measures the report derives from the Scan,
laid out with the accuracy of each figure.

Computed when a page is rendered, from the document alone (HTML-01): no
source, no recomputation. An analysis that did not end ``complete`` or
``limited`` has no card; the second-pass table says why. The values of a
column whose exposure is ``mask`` or ``hide`` are never listed: the masks and
classes of a masked column are printed only when they are masks and classes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from tabalyst.models import AnalysesBlock
from tabalyst.report_deep import CONVENTION_WORDS, shown
from tabalyst.report_labels import SHAPE_REASONS, STATS_REASONS, TABLE_REASONS, WEEKDAYS
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
from tabalyst.scanner.detectors.ip import IP_CLASSES
from tabalyst.scanner.detectors.phone import PHONE_CLASSES
from tabalyst.scanner.exposure import mask
from tabalyst.scanner.models import FieldResult
from tabalyst.scanner.planner.facts import ROOT_FIELD
from tabalyst.scanner.secondpass.models import (
    AnalysisOutput,
    ArrayProfileResult,
    BinnedHistogram,
    CharacterProfileResult,
    DenseHistogram,
    DuplicateResult,
    DuplicatesLimited,
    FingerprintResult,
    FormsResult,
    MeasureLevel,
    MeasureResult,
    MissingMatrixResult,
    PartCount,
    PartsResult,
    PeriodCounts,
    PositionDriftResult,
    Quantile,
    ResidualResult,
    ShapeResult,
    StatsResult,
    StatsSummary,
    StructureResult,
    TableAssociation,
    TextProfileResult,
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
    "drift": "Drift along the file",
    "missing": "Missing together",
    "structure": "Structure of the JSON",
    "texts": "Long texts",
    "forms": "Sensitive columns without a value",
    "scan": "Read from the Scan",
}
FAMILY_ORDER = tuple(_FAMILIES)
# The classes a value of each detector takes, which a card checks before it prints
# one: anything else is not a class.
_CLASSES = {"ip_address": IP_CLASSES, "phone": PHONE_CLASSES}
CLASS_WORDS = {"ip_address": "IP addresses", "phone": "phone numbers"}


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


def _slice_label(first_record: int, records: int) -> str:
    return f"{_count(first_record)} to {_count(first_record + records - 1)}"


def _association_fact(label: str, found: TableAssociation) -> InsightFact:
    if found.corrected is None:
        why = TABLE_REASONS.get(found.reason or "", found.reason or "undefined")
        return InsightFact(label=label, value=f"no score: {why}")
    return InsightFact(
        label=label,
        value=f"{found.corrected:.2f}",
        note=None if found.stable else "low counts: read it with care",
    )


def _drift_card(
    base: str, display: str, fields: list[str], result: PositionDriftResult, hidden: bool
) -> InsightCard:
    facts = [
        InsightFact(label="Records", value=_count(result.records)),
        InsightFact(label="Values", value=_count(result.values)),
        InsightFact(
            label="Missing",
            value=f"{_count(result.missing)} ({_share(result.missing, result.records)})",
        ),
    ]
    bars: list[InsightBars] = []
    tables: list[InsightTable] = []
    notes = [
        (
            "The records are cut in ten slices of the same size, in file order. A change "
            "along the file shows that the column was filled or exported differently, "
            "not why."
        )
    ]
    if result.missing:
        facts.append(
            _association_fact(
                "Position and presence of a value (Cramér's V, corrected)",
                result.missing_association,
            )
        )
        bars.append(
            _bars(
                ((_slice_label(item.first_record, item.records), item.missing) for item in result.slices),
                "Records without a value, by slice of the file (records)",
                note="The slices hold the same number of records, so a bar longer than the others is a part of the file that misses more.",
            )
        )
    followed = result.followed
    if followed is not None:
        facts.append(
            InsightFact(label="Distinct values followed", value=_count(followed.distinct))
        )
        facts.append(
            _association_fact("Position and value (Cramér's V, corrected)", followed.association)
        )
        if hidden:
            notes.append("The values are withheld by the exposure setting of the column.")
        else:
            totals = [item.values for item in result.slices]
            headers = ["Value", "Count", *(str(number) for number in range(1, len(totals) + 1))]
            rows = [
                [
                    item.value,
                    _count(item.count),
                    *(f"{part / whole:.1%}" if whole else "-" for part, whole in zip(item.counts, totals, strict=True)),
                ]
                for item in followed.listed
            ]
            if any(followed.other):
                rows.append(
                    [
                        "(others)",
                        _count(sum(followed.other)),
                        *(f"{part / whole:.1%}" if whole else "-" for part, whole in zip(followed.other, totals, strict=True)),
                    ]
                )
            rows.append(
                [
                    "(first seen here)",
                    _count(sum(item.new_values or 0 for item in result.slices)),
                    *(_count(item.new_values or 0) for item in result.slices),
                ]
            )
            tables.append(
                InsightTable(
                    caption="Share of the values of each slice, from the first to the tenth",
                    headers=headers,
                    rows=rows,
                    code=[0],
                    note=(
                        f"The {_count(followed.distinct - len(followed.listed))} values with the fewest "
                        "occurrences are summed up in (others); the report JSON holds the rest."
                        if followed.distinct > len(followed.listed)
                        else None
                    ),
                )
            )
    return InsightCard(
        id=f"{base}-drift",
        family="drift",
        title="Drift along the file",
        column=display,
        fields=fields,
        summary=f"{_count(result.records)} records in ten slices.",
        facts=facts,
        bars=bars,
        tables=tables,
        notes=notes,
    )


def _together(both: int, first: int, second: int) -> float:
    """Of the records that lack a value in either column, the share that lack one in both."""
    union = first + second - both
    return both / union if union else 0.0


def _matrix_card(
    base: str, display: str, fields: list[str], result: MissingMatrixResult
) -> InsightCard:
    facts = [
        InsightFact(
            label="Records without a value",
            value=f"{_count(result.missing)} ({_share(result.missing, result.records)})",
        ),
        InsightFact(label="Other columns that miss a value", value=_count(result.columns - 1)),
        InsightFact(
            label="Lack one in the same records",
            value=_count(result.partners),
        ),
    ]
    rows = [
        [
            item.display,
            _count(item.missing),
            _count(item.both),
            _share(item.both, result.missing),
            f"{_together(item.both, result.missing, item.missing):.1%}",
        ]
        for item in result.listed
    ]
    tables = []
    if rows:
        tables.append(
            InsightTable(
                caption=f"Also without a value where {display} has none",
                headers=["Column", "Missing there", "Both", "Of this column's", "Together"],
                rows=rows,
                code=[0],
                note=(
                    f"{_count(result.partners - len(result.listed))} more columns are in the report JSON."
                    if result.truncated
                    else None
                ),
            )
        )
    return InsightCard(
        id=f"{base}-missing",
        family="missing",
        title="Missing together",
        column=display,
        fields=fields,
        scope="column",
        summary=f"{_count(result.partners)} of {_count(result.columns - 1)} other columns.",
        facts=facts,
        tables=tables,
        notes=[
            (
                "Together is the share of the records that lack a value in either column "
                "where both do. Counts are exact, and show that values go missing together, "
                "not why."
            )
        ],
    )


def _dataset_matrix_card(base: str, items: list[tuple[str, str, MissingMatrixResult]]) -> InsightCard:
    """One card for the dataset: the pairs of columns that lack a value together
    most, each pair once, from the partners every column listed."""
    pairs: dict[tuple[str, str], tuple[float, int, str, str, int, int]] = {}
    first = items[0][2]
    for field_id, display, result in items:
        for item in result.listed:
            key = tuple(sorted((field_id, item.field)))
            share = _together(item.both, result.missing, item.missing)
            pairs.setdefault(
                (key[0], key[1]),
                (share, item.both, display, item.display, result.missing, item.missing),
            )
    ranked = sorted(pairs.values(), key=lambda pair: (-pair[0], -pair[1], pair[2], pair[3]))
    rows = [
        [name, other, _count(a), _count(b), _count(both), f"{share:.1%}"]
        for share, both, name, other, a, b in ranked[:MAX_ROWS]
    ]
    shown = len(rows)
    return InsightCard(
        id=f"{base}-missing-pairs",
        family="missing",
        title="Columns missing together",
        column=f"{_count(first.columns)} columns",
        fields=[],
        scope="dataset",
        summary=(
            f"{_count(first.columns)} columns lack a value in some of the "
            f"{_count(first.records)} records."
        ),
        tables=[
            InsightTable(
                caption="Pairs of columns that lack a value in the same records",
                headers=["Column", "With", "Missing", "Missing there", "Both", "Together"],
                rows=rows,
                code=[0, 1],
                note=(
                    f"The {_count(len(ranked) - shown)} pairs with the lowest share are in the report JSON."
                    if len(ranked) > shown
                    else None
                ),
            )
        ],
        notes=[
            (
                "Together is the share of the records that lack a value in either column "
                "where both do. Pairs come from the partners listed for each column, the "
                "ones that lack a value most with it."
            )
        ],
    )


def _length_text(low: int, high: int) -> str:
    return _count(low) if low == high else f"{_count(low)} to {_count(high)}"


def _arrays_card(
    base: str, display: str, fields: list[str], result: ArrayProfileResult
) -> InsightCard:
    quantile = {round(item.level * 100): item for item in result.quantiles}
    facts = [
        InsightFact(label="Arrays", value=_count(result.arrays)),
        InsightFact(
            label="Empty arrays",
            value=f"{_count(result.empty)} ({_share(result.empty, result.arrays)})",
        ),
        InsightFact(label="Items", value=_count(result.items)),
        InsightFact(
            label="Length, shortest to longest",
            value=_length_text(result.min_length, result.max_length),
        ),
        InsightFact(label="Length, mean", value=shown(round(result.mean_length, 2))),
        InsightFact(label="Length, median", value=_quantile(quantile[50])[0]),
        InsightFact(
            label="Length, 5% to 95% of the arrays",
            value=f"{_quantile(quantile[5])[0]} to {_quantile(quantile[95])[0]}",
        ),
    ]
    labels = [(_count(item.length),) * 2 for item in result.length_histogram]
    bars = _bars(
        _grouped(labels, [item.count for item in result.length_histogram]),
        "Arrays by length (items)",
    )
    return InsightCard(
        id=f"{base}-arrays",
        family="structure",
        title="Lengths of the arrays",
        column=display,
        fields=fields,
        summary=f"{_count(result.arrays)} arrays, every length counted.",
        facts=facts,
        bars=[bars],
        notes=["The lengths are exact; the quantiles follow from the counts of every length."],
    )


def _keys_text(names: list[str], total: int) -> str:
    """The keys a set lacks, as a line: ``none`` when it lacks no key, and a
    mention of those the list left out."""
    if not total:
        return "none"
    text = ", ".join(names)
    return text + (f" and {_count(total - len(names))} more" if total > len(names) else "")


def _structure_card(
    base: str, display: str, fields: list[str], result: StructureResult, root: bool
) -> InsightCard:
    unit = "Records" if root else "Objects"
    facts = [
        InsightFact(label=unit, value=_count(result.objects)),
        InsightFact(label="Keys", value=_count(result.keys)),
        InsightFact(label="Keys in every one", value=_count(result.always)),
        InsightFact(
            label="Distinct sets of keys",
            value=_count(result.distinct),
            kind="exact" if result.complete else "at_least",
            note=(
                None
                if result.complete
                else f"{_count(result.untracked)} more {unit.lower()} have a set that was not tracked"
            ),
        ),
    ]
    rows = [
        [
            str(number),
            _count(item.count),
            _share(item.count, result.objects),
            _count(item.keys),
            _keys_text(item.absent, item.absent_total),
        ]
        for number, item in enumerate(result.listed, start=1)
    ]
    rest = result.distinct - len(result.listed)
    note = (
        f"The {_count(rest)} other sets, with {_count(result.other_objects)} {unit.lower()}, "
        "are in the report JSON."
        if rest > 0
        else None
    )
    return InsightCard(
        id=f"{base}-keys",
        family="structure",
        title="Sets of keys of the records" if root else "Sets of keys",
        column=display,
        fields=[] if root else fields,
        scope="dataset" if root else "both",
        summary=(
            f"{_count(result.objects)} {unit.lower()} in {_count(result.distinct)} "
            f"{'sets' if result.distinct != 1 else 'set'} of keys."
        ),
        facts=facts,
        tables=[
            InsightTable(
                caption=f"The most frequent sets of keys ({unit.lower()})",
                headers=["Set", unit, "Share", "Keys present", "Keys missing"],
                rows=rows,
                code=[4],
                note=note,
            )
        ],
        notes=[
            (
                "Each set is counted exactly from its first object. It shows that the "
                f"{unit.lower()} differ in the keys they have, not why."
            )
        ],
    )


def _bucket_label(low: int, high: int) -> str:
    return _count(low) if low == high else f"{_count(low)} to {_count(high)}"


def _digit_label(index: int) -> str:
    if index == 0:
        return "none"
    return "up to 10%" if index == 1 else f"over {(index - 1) * 10}% to {index * 10}%"


def _texts_card(
    base: str, display: str, fields: list[str], result: TextProfileResult
) -> InsightCard:
    facts = [
        InsightFact(label="Texts", value=_count(result.texts)),
        InsightFact(label="Characters", value=_count(result.characters)),
        InsightFact(
            label="Words",
            value=_count(result.words),
            note=(
                f"{_count(result.min_words)} to {_count(result.max_words)} a text, "
                f"{shown(round(result.mean_words, 1))} on average"
            ),
        ),
        InsightFact(
            label="Lines",
            value=_count(result.lines),
            note=f"up to {_count(result.max_lines)} a text",
        ),
        InsightFact(
            label="Texts on several lines",
            value=f"{_count(result.multi_line)} ({_share(result.multi_line, result.texts)})",
        ),
        InsightFact(
            label="Digits",
            value=f"{_count(result.digits)} ({result.digit_share:.1%} of the characters)",
        ),
    ]
    bars = [
        _bars(
            ((_bucket_label(item.low, item.high), item.count) for item in result.word_buckets),
            "Texts by number of words (texts)",
        ),
        _bars(
            ((_bucket_label(item.low, item.high), item.count) for item in result.line_buckets),
            "Texts by number of lines (texts)",
        ),
        _bars(
            (
                (_digit_label(index), count)
                for index, count in enumerate(result.digit_buckets)
                if count
            ),
            "Texts by share of digits (texts)",
        ),
    ]
    return InsightCard(
        id=f"{base}-texts",
        family="texts",
        title="Words, lines and digits",
        column=display,
        fields=fields,
        summary=f"{_count(result.texts)} texts, each read once and forgotten.",
        facts=facts,
        bars=bars,
        notes=[
            (
                "A word is a run of characters that are not white space, a line is one that "
                "splitting at line breaks gives, and a digit is a decimal digit of Unicode. "
                "The counts are exact, on the original texts."
            )
        ],
    )


def _fingerprint_card(
    base: str,
    display: str,
    fields: list[str],
    result: FingerprintResult,
    hidden: bool,
) -> InsightCard:
    facts = [
        InsightFact(label="Values", value=_count(result.values)),
        InsightFact(
            label="Distinct values",
            value=_count(result.distinct),
            kind="fingerprint",
            note="told apart by a 128-bit fingerprint, not by comparing the texts",
        ),
        InsightFact(
            label="Found more than once",
            value=(
                f"{_count(result.repeated)} distinct, {_count(result.repeated_occurrences)} "
                f"occurrences ({_share(result.repeated_occurrences, result.values)})"
            ),
        ),
    ]
    tables = []
    notes = [
        (
            f"Two different texts are taken for one only if their {result.bits}-bit digests "
            f"({result.algorithm}) collide. A digest is the one the Scan gives its long texts, "
            "so a listed digest can be found among the entries of its sample."
        )
    ]
    if hidden:
        notes.append("The digests are withheld by the exposure setting of the column.")
    elif result.listed:
        tables.append(
            InsightTable(
                caption="The texts found most often, by digest",
                kind="fingerprint",
                headers=["Digest", "Occurrences", "Share of the values"],
                rows=[
                    [
                        f"{item.digest[:16]}...",
                        _count(item.count),
                        _share(item.count, result.values),
                    ]
                    for item in result.listed
                ],
                code=[0],
                note=(
                    f"{_count(result.repeated - len(result.listed))} more are in the report JSON."
                    if result.truncated
                    else None
                ),
            )
        )
    return InsightCard(
        id=f"{base}-fingerprints",
        family="texts",
        title="Distinct long texts",
        column=display,
        fields=fields,
        summary=(
            "Every text is different."
            if result.unique
            else f"{_count(result.redundant)} occurrences repeat an earlier text."
        ),
        facts=facts,
        tables=tables,
        notes=notes,
    )


def _is_form(text: str) -> bool:
    """Whether a text is a mask: masking it changes nothing. A text of the data
    is not, so a document edited to carry values is not printed."""
    return mask(text) == text


def _forms_card(
    base: str, display: str, fields: list[str], result: FormsResult
) -> InsightCard | None:
    classes = result.classes
    if not all(_is_form(item.form) for item in result.listed):
        return None
    allowed = _CLASSES.get(classes.detector, ()) if classes is not None else ()
    if classes is not None and not all(item.form in allowed for item in classes.listed):
        return None
    facts = [
        InsightFact(label="Values", value=_count(result.values)),
        InsightFact(
            label="Distinct masks",
            value=_count(result.forms),
            kind="exact" if result.complete else "at_least",
        ),
        InsightFact(
            label=f"Masks of fewer than {result.min_count} values",
            value=f"{_count(result.other_forms)} ({_count(result.other_values)} values)",
        ),
    ]
    tables = [
        InsightTable(
            caption="Masks of the values (values)",
            headers=["Mask", "Values", "Share"],
            rows=[
                [item.form, _count(item.count), _share(item.count, result.values)]
                for item in result.listed
            ],
            code=[0],
            note=(
                "A letter is shown as a or A and a digit as 9: the values themselves are "
                "never listed."
            ),
        )
    ]
    if classes is not None:
        rows = [
            [item.form, _count(item.count), _share(item.count, result.values)]
            for item in classes.listed
        ]
        if classes.other:
            rows.append(["(others)", _count(classes.other), _share(classes.other, result.values)])
        if classes.unclassified:
            rows.append(
                ["(not read)", _count(classes.unclassified), _share(classes.unclassified, result.values)]
            )
        tables.append(
            InsightTable(
                caption=f"Values by class ({CLASS_WORDS[classes.detector]})",
                headers=["Class", "Values", "Share"],
                rows=rows,
                code=[0],
                note=(
                    "A class that fewer than "
                    f"{_count(result.min_count)} values take is summed up in (others)."
                ),
            )
        )
    return InsightCard(
        id=f"{base}-forms",
        family="forms",
        title="Masks and classes",
        column=display,
        fields=fields,
        summary=f"{_count(result.forms)} masks, no value listed.",
        facts=facts,
        tables=tables,
        notes=[
            (
                "Counts are exact. No figure is given about fewer than "
                f"{_count(result.min_count)} values: a mask or a class below that is summed "
                "up with the others."
            )
        ],
    )


def _card_of(
    item_id: str,
    display: str,
    fields: list[str],
    result: AnalysisOutput,
    hidden: bool,
    *,
    root: bool = False,
    mode: str | None = None,
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
    if isinstance(result, PositionDriftResult):
        return _drift_card(item_id, display, fields, result, hidden)
    if isinstance(result, MissingMatrixResult):
        return _matrix_card(item_id, display, fields, result)
    if isinstance(result, ArrayProfileResult):
        return _arrays_card(item_id, display, fields, result)
    if isinstance(result, StructureResult):
        return _structure_card(item_id, display, fields, result, root)
    if isinstance(result, TextProfileResult):
        return _texts_card(item_id, display, fields, result)
    if isinstance(result, CharacterProfileResult):
        # The character map of the column page shows it.
        return None
    if isinstance(result, FingerprintResult):
        return _fingerprint_card(item_id, display, fields, result, hidden)
    if isinstance(result, FormsResult):
        # A field that hides its values has no mask either (decision O61).
        return None if mode == "hide" else _forms_card(item_id, display, fields, result)
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
    matrices: list[tuple[str, str, MissingMatrixResult]] = []
    for item in analyses.deep.analyses:
        if item.dataset != dataset or item.result is None:
            continue
        if item.status not in ("complete", "limited"):
            continue
        fields = [item.field] + ([item.partner] if item.partner else [])
        hidden = any(exposure.get(field) in _HIDDEN for field in fields)
        result = item.result
        if isinstance(result, MissingMatrixResult):
            # A withheld column is named by no pair, whichever side it is on.
            if hidden:
                continue
            result = result.model_copy(
                update={
                    "listed": [
                        partner
                        for partner in result.listed
                        if exposure.get(partner.field) not in _HIDDEN
                    ]
                }
            )
            matrices.append((item.field, item.display, result))
        card = _card_of(
            f"i-{len(cards) + 1}-{item.analyzer.replace('_', '-')}",
            item.display,
            fields,
            result,
            hidden,
            root=item.field == ROOT_FIELD,
            mode=exposure.get(item.field),
        )
        if card is not None:
            cards.append(card)
    if matrices:
        cards.append(_dataset_matrix_card(f"i-{len(cards) + 1}", matrices))
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
