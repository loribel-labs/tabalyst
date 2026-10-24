# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Views of the second pass that the report pages read (design 20, 18.14).

Everything here is computed when a page is rendered, from the ``analyses`` member
of the document: no source, no recomputation (HTML-01). A document without that
member is shown as having none, never rebuilt.
"""

from __future__ import annotations

from collections import Counter

from tabalyst.models import AnalysesBlock
from tabalyst.report_labels import (
    ANALYSIS_LABELS,
    DEEP_REASONS,
    EXACT,
    FEATURE_WORDS,
    FINGERPRINT,
    PEARSON_REASONS,
    SHAPE_REASONS,
    STATS_REASONS,
    TABLE_REASONS,
    WEEKDAYS,
)
from tabalyst.report_views import (
    ColumnAnalyses,
    SecondPassMetrics,
    SecondPassRow,
    SecondPassView,
)
from tabalyst.scanner.planner.reasons import reason_text
from tabalyst.scanner.secondpass.models import (
    AnalysisOutput,
    AnalysisResult,
    AnalyticalDistinctCount,
    ArrayProfileResult,
    BinnedHistogram,
    CharacterProfileResult,
    CrosstabResult,
    DateOrderResult,
    DateResolution,
    DenseHistogram,
    DistinctCount,
    DistinctLimited,
    DuplicateResult,
    DuplicateRowsResult,
    DuplicatesLimited,
    FingerprintResult,
    FormsResult,
    FrequencyTable,
    LengthDistribution,
    MeasureResult,
    MissingMatrixResult,
    NumberResolution,
    PartsResult,
    PatternCounts,
    PearsonResult,
    PeriodCounts,
    PositionDriftResult,
    ResidualResult,
    ShapeResult,
    StatsResult,
    StructureResult,
    TextProfileResult,
)

_NOT_COMPUTED = "not_computed"
_AT_LEAST = "at_least"


def _plural(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def column_analyses(
    analyses: AnalysesBlock | None,
) -> dict[tuple[str, str], ColumnAnalyses]:
    """The results of each column, by dataset and field id."""
    if analyses is None or analyses.deep is None:
        return {}
    found: dict[tuple[str, str], dict[str, AnalysisOutput]] = {}
    for item in analyses.deep.analyses:
        if item.result is None or item.status not in ("complete", "limited"):
            continue
        found.setdefault((item.dataset, item.field), {})[item.analyzer] = item.result
    views: dict[tuple[str, str], ColumnAnalyses] = {}
    for key, results in found.items():
        views[key] = ColumnAnalyses(
            distinct=results.get("exact_distinct"),  # type: ignore[arg-type]
            patterns=results.get("pattern_validation"),  # type: ignore[arg-type]
            periods=results.get("temporal_distribution"),  # type: ignore[arg-type]
            histogram=results.get("numeric_histogram"),  # type: ignore[arg-type]
            lengths=results.get("length_distribution"),  # type: ignore[arg-type]
            frequencies=results.get("exact_frequencies"),  # type: ignore[arg-type]
            characters=results.get("character_profile"),  # type: ignore[arg-type]
        )
    return views


def shown(value: float) -> str:
    """A number as the report prints it: an integer with all its digits."""
    return f"{value:,}" if isinstance(value, int) else f"{value:,.4f}".rstrip("0").rstrip(".")


def result_summary(result: AnalysisOutput) -> tuple[str, str]:
    """What a result says, in a sentence, and the accuracy of its figures."""
    if isinstance(result, DenseHistogram):
        median = result.median
        return (
            (
                f"{_plural(result.distinct, 'distinct integer')} counted one by one; "
                f"median {shown(median.value)}"
            ),
            EXACT,
        )
    if isinstance(result, BinnedHistogram):
        median = result.median
        bounds = (
            f" (between {shown(median.lower)} and {shown(median.upper)})"
            if median.lower is not None and median.upper is not None
            else ""
        )
        return (
            (
                f"{_plural(len(result.counts), 'bin')}, counts exact; median "
                f"estimated at {shown(median.value)}{bounds}"
            ),
            EXACT,
        )
    if isinstance(result, LengthDistribution):
        return (
            (
                f"lengths {result.min_length} to {result.max_length} characters, "
                f"mean {shown(round(result.mean_length, 2))}"
            ),
            EXACT,
        )
    if isinstance(result, DistinctCount):
        return (
            f"{result.distinct:,} distinct values among {result.values:,}"
            + (", all different" if result.unique else ""),
            EXACT,
        )
    if isinstance(result, AnalyticalDistinctCount):
        return (
            f"{result.distinct:,} distinct values among {result.values:,} after normalization"
            + (", all different" if result.unique else ""),
            EXACT,
        )
    if isinstance(result, DistinctLimited):
        return (
            (
                f"at least {result.lower_bound:,} distinct values; stopped after "
                f"{result.values_read:,} values"
            ),
            _AT_LEAST,
        )
    if isinstance(result, FrequencyTable):
        return (
            f"{_plural(result.distinct, 'value')} counted, the most frequent "
            f"{result.values[0].count:,} times"
            if result.values
            else "no value",
            EXACT,
        )
    if isinstance(result, PatternCounts):
        excluded = sum(result.excluded.model_dump().values())
        return (
            f"{result.matched:,} of {result.values:,} values read by "
            f"{_plural(len(result.all_patterns()), 'pattern')}, "
            f"{result.outside_patterns():,} by none"
            + (f", {excluded:,} not tested" if excluded else ""),
            EXACT,
        )
    if isinstance(result, PearsonResult):
        left_out = sum(result.excluded.model_dump().values())
        tail = f"; {left_out:,} of {result.rows:,} rows lack a number in one column" if left_out else ""
        if result.coefficient is None:
            why = PEARSON_REASONS.get(result.reason or "", result.reason or "undefined")
            return f"no coefficient: {why} ({_plural(result.pairs, 'common row')}){tail}", EXACT
        line = f"; slope {result.slope:+.4g}" if result.slope is not None else ""
        rank = result.rank
        ranked = (
            f"; rank {rank.coefficient:+.3f} (between {rank.lower:+.3f} and {rank.upper:+.3f})"
            if rank is not None and rank.coefficient is not None
            else ""
        )
        head = f"r = {result.coefficient:+.3f} over {_plural(result.pairs, 'common row')}"
        return f"{head}{line}{ranked}{tail}", EXACT
    if isinstance(result, CrosstabResult):
        word = FEATURE_WORDS.get(result.feature.kind, result.feature.kind)
        head = f"{result.counted:,} of {result.rows:,} rows by {word}"
        found = result.association
        if found.corrected is None:
            why = TABLE_REASONS.get(found.reason or "", found.reason or "undefined")
            return f"{head}; no score: {why}", EXACT
        forward = result.purity.forward.value
        purity_text = "" if forward is None else f"; purity {forward:.1%}"
        caution = "" if found.stable else " (low counts)"
        return (
            f"{head}; Cramér's V {found.cramers_v:.2f}{caution}{purity_text}"
            + (f"; {len(result.rules):,} candidate rules" if result.rules else ""),
            EXACT,
        )
    if isinstance(result, StatsResult):
        return _stats_summary(result), EXACT
    if isinstance(result, MeasureResult):
        return _measures_summary(result), EXACT
    if isinstance(result, ShapeResult):
        return _shape_summary(result), EXACT
    if isinstance(result, PartsResult):
        return _parts_summary(result), EXACT
    if isinstance(result, PositionDriftResult):
        return _drift_summary(result), EXACT
    if isinstance(result, MissingMatrixResult):
        return _matrix_summary(result), EXACT
    if isinstance(result, DateOrderResult):
        return _order_summary(result), EXACT
    if isinstance(result, ArrayProfileResult):
        return _arrays_summary(result), EXACT
    if isinstance(result, StructureResult):
        return _structure_summary(result), _exact_unless_partial(result.complete)
    if isinstance(result, TextProfileResult):
        return _texts_summary(result), EXACT
    if isinstance(result, CharacterProfileResult):
        return _characters_summary(result), EXACT
    if isinstance(result, FingerprintResult):
        return _fingerprint_summary(result), FINGERPRINT
    if isinstance(result, FormsResult):
        return _forms_summary(result), _exact_unless_partial(result.complete)
    if isinstance(result, ResidualResult):
        return _residuals_summary(result), EXACT
    if isinstance(result, DuplicateResult):
        return _duplicates_summary(result), EXACT
    if isinstance(result, DuplicateRowsResult):
        return (
            f"{result.extra_copies:,} extra copies of whole rows in "
            f"{_plural(result.records, 'record')}, {result.distinct_rows:,} distinct"
            + ("" if result.accuracy == "exact" else "; stopped before the end of the file"),
            EXACT if result.accuracy == "exact" else _AT_LEAST,
        )
    if isinstance(result, DuplicatesLimited):
        return (
            (
                f"at least {result.repeated:,} repeated values among "
                f"{result.distinct:,} distinct; stopped after {result.values_read:,} values"
            ),
            _AT_LEAST,
        )
    assert isinstance(result, PeriodCounts)
    return (
        f"{result.count:,} dates by {result.granularity}, {result.first} to {result.last}"
        + (f"; {result.ambiguous:,} ambiguous not placed" if result.ambiguous else "")
        + _resolution_text(result.resolution, result.resolved),
        EXACT,
    )


# What the numbers of each detector of values with a marker are, and the word
# for their markers.
_MEASURE_WORDS = {
    "currency": ("amount", "currency"),
    "percentage": ("percentage", "sign"),
    "quantity": ("quantity", "unit"),
}


def _stats_summary(result: StatsResult) -> str:
    described = sum(1 for group in result.groups if group.count)
    noun = "category" if described == 1 else "categories"
    head = f"{result.counted:,} of {result.rows:,} rows described by {described:,} {noun}"
    found = result.association
    if found.epsilon_squared is None or found.eta_squared is None:
        why = STATS_REASONS.get(found.reason or "", found.reason or "undefined")
        return f"{head}; no score: {why}"
    return (
        f"{head}; the categories explain {found.eta_squared:.1%} of the variance "
        f"({found.epsilon_squared:.1%} once corrected)"
    )


def _measures_summary(result: MeasureResult) -> str:
    noun, marker = _MEASURE_WORDS[result.detector]
    nouns = "quantities" if noun == "quantity" else f"{noun}s"
    markers = result.markers
    plural = "currencies" if marker == "currency" else f"{marker}s"
    text = f"{result.parsed:,} {noun if result.parsed == 1 else nouns}"
    if result.detector != "percentage":
        text += f" in {markers.distinct:,} {marker if markers.distinct == 1 else plural}"
        text += f"; {markers.modes[0]} {markers.dominant_share:.0%}"
    median = result.overall.numeric.median
    if result.homogeneous and median.status == "complete":
        text += f"; median {shown(median.value)}"
    if result.percent_range is not None and result.percent_range.above:
        text += f"; {result.percent_range.above:,} above 100"
    if result.ambiguous:
        text += f"; {result.ambiguous:,} ambiguous not placed"
    text += _number_resolution_text(result.resolution, result.resolved)
    if result.storage == "grid":
        text += "; quantiles estimated"
    return text


CONVENTION_WORDS = {"dot": "decimal point", "comma": "decimal comma"}


def _number_resolution_text(resolution: NumberResolution | None, resolved: int) -> str:
    """The sentence that says the numbers written ambiguously were read by the
    evidence of the column."""
    if resolution is None:
        return ""
    proof = resolution.evidence.get(resolution.convention, 0)
    return (
        f"; {resolved:,} read with the {CONVENTION_WORDS[resolution.convention]} "
        f"convention (proved by {proof:,} unambiguous values)"
    )


def _shape_summary(result: ShapeResult) -> str:
    moments = result.moments
    if moments.skewness is not None and moments.excess_kurtosis is not None:
        text = f"skewness {moments.skewness:+.2f}, kurtosis {moments.excess_kurtosis:+.2f}"
    else:
        text = f"no skewness: {SHAPE_REASONS.get(moments.reason or '', moments.reason or 'undefined')}"
    mild = result.tukey.fences[0]
    if result.tukey.accuracy == "exact":
        outliers = f"{mild.below.certain + mild.above.certain:,}"
    else:
        low = mild.below.certain + mild.above.certain
        high = mild.below.possible + mild.above.possible
        outliers = f"{low:,} to {high:,}"
    text += f"; {outliers} outliers beyond 1.5 interquartile ranges"
    if result.scale.mixed:
        text += f"; decimals vary up to {result.scale.max_places}"
    if result.storage == "grid":
        text += "; quartiles estimated"
    return text


def _parts_summary(result: PartsResult) -> str:
    text = f"{result.count:,} {'times' if result.temporal_kind == 'time' else 'dates'}"
    if result.year_months:
        text += f", {result.year_months[0].period} to {result.year_months[-1].period}"
    if result.weekdays is not None:
        day = max(result.weekdays, key=lambda part: (part.count, -part.value))
        text += f"; busiest weekday {WEEKDAYS[day.value]}"
    if result.hours:
        hour = max(result.hours, key=lambda part: (part.count, -part.value))
        text += f"; busiest hour {hour.value:02d}h"
    if result.after_as_of is not None:
        text += f"; {result.after_as_of:,} after {result.as_of}"
    if result.invalid:
        text += f"; {result.invalid:,} invalid"
    if result.simulation is not None:
        text += f"; {result.ambiguous:,} ambiguous read under {len(result.simulation.readings)} orders"
    return text + _resolution_text(result.resolution, result.resolved)


def _drift_summary(result: PositionDriftResult) -> str:
    shares = [s.missing / s.records for s in result.slices if s.records]
    text = f"{result.values:,} values in {result.records:,} records"
    if result.missing:
        text += f"; missing {min(shares):.1%} to {max(shares):.1%} by tenth of the file"
        found = result.missing_association
        if found.corrected is not None:
            text += f" (V {found.corrected:.2f})"
    if result.followed is not None:
        late = sum(s.new_values or 0 for s in result.slices[1:])
        text += f"; {_plural(result.followed.distinct, 'value')} followed"
        if late:
            text += f", {late:,} first seen after the first tenth"
        found = result.followed.association
        if found.corrected is not None:
            text += f" (V {found.corrected:.2f})"
    return text


def _matrix_summary(result: MissingMatrixResult) -> str:
    others = result.columns - 1
    text = f"{result.missing:,} records without a value; {result.partners:,} of {others:,} other columns lack one in the same records"
    if result.listed:
        top = result.listed[0]
        text += f", most with {top.display} ({top.both:,})"
    return text


def _order_summary(result: DateOrderResult) -> str:
    text = f"{result.compared:,} records compared, {result.broken:,} with the first date after the second"
    skipped = sum(result.excluded.model_dump().values())
    if skipped:
        text += f"; {skipped:,} not compared"
    return text


def _exact_unless_partial(complete: bool) -> str:
    """The accuracy of a result whose lists stopped growing when ``complete`` is false."""
    return EXACT if complete else _AT_LEAST


def _arrays_summary(result: ArrayProfileResult) -> str:
    text = (
        f"{result.arrays:,} arrays of {result.min_length:,} to {result.max_length:,} items, "
        f"median {shown(result.quantiles[2].value)}, mean {shown(round(result.mean_length, 2))}"
    )
    if result.empty:
        text += f"; {result.empty:,} empty"
    return text


def _structure_summary(result: StructureResult) -> str:
    sets = "at least " if not result.complete else ""
    return (
        f"{result.objects:,} objects with {sets}{_plural(result.distinct, 'set')} of keys; "
        f"{result.always:,} of {result.keys:,} keys are in every one"
    )


def _texts_summary(result: TextProfileResult) -> str:
    text = (
        f"{result.texts:,} texts of {shown(round(result.mean_words, 1))} words on average "
        f"(up to {result.max_words:,}); {result.digit_share:.1%} of the characters are digits"
    )
    if result.multi_line:
        text += f"; {result.multi_line:,} on several lines"
    return text


def _characters_summary(result: CharacterProfileResult) -> str:
    text = f"{result.characters:,} characters, {result.distinct:,} of them different"
    if result.top:
        text += f"; the most frequent is U+{result.top[0].codepoint:04X}"
    if result.with_emoji:
        text += f"; {result.with_emoji:,} values with an emoji"
    return text


def _fingerprint_summary(result: FingerprintResult) -> str:
    text = f"{result.distinct:,} distinct values among {result.values:,}"
    if result.unique:
        return text + ", all different"
    return text + f"; {_plural(result.repeated, 'text')} found more than once"


def _forms_summary(result: FormsResult) -> str:
    text = f"{result.forms:,} masks over {result.values:,} values"
    if not result.complete:
        text = f"at least {text}"
    if result.classes is not None:
        text += f"; {_plural(len(result.classes.listed), 'class')} of {result.classes.detector}"
    return text


def _resolution_text(resolution: DateResolution | None, resolved: int) -> str:
    """The sentence that says the ambiguous dates were read by the evidence."""
    if resolution is None:
        return ""
    proof = resolution.evidence.get(resolution.order, 0)
    return (
        f"; {resolved:,} ambiguous now valid, read as {resolution.order} "
        f"(proved by {proof:,} unambiguous dates)"
    )


def _residuals_summary(result: ResidualResult) -> str:
    # A value can be left out by the pattern and by a detector: the sources are
    # not added, and the states of one detector are disjoint.
    sources: dict[str | None, int] = {}
    for table in result.tables:
        sources[table.detector] = sources.get(table.detector, 0) + table.occurrences
    left = max(sources.values(), default=0)
    text = f"at least {left:,} values left out"
    if result.tables:
        text += f" ({_plural(len(result.tables), 'table')})"
    if result.patterns is not None:
        text += f"; {_plural(len(result.patterns), 'pattern')} profiled"
    if any(not table.complete for table in result.tables):
        text += "; lists bounded"
    return text


def _duplicates_summary(result: DuplicateResult) -> str:
    if result.unique:
        return f"{result.values:,} values, all different"
    repeated = result.repeated
    return (
        f"{_plural(repeated.distinct, 'value')} found more than once, "
        f"{result.redundant:,} extra occurrences"
        + ("" if repeated.complete else "; list bounded")
    )


def _row(item: AnalysisResult) -> SecondPassRow:
    label = ANALYSIS_LABELS.get(item.analyzer, item.analyzer)
    if item.result is not None and item.status in ("complete", "limited"):
        summary, kind = result_summary(item.result)
        if item.status == "limited" and item.reason:
            summary += f" ({DEEP_REASONS.get(item.reason, item.reason)})"
        return SecondPassRow(
            column=item.display,
            dataset_id=item.dataset,
            field_id=item.field,
            analysis=label,
            status=item.status,
            kind=kind,  # type: ignore[arg-type]
            summary=summary,
        )
    why = DEEP_REASONS.get(item.reason or "", item.reason or "not computed")
    return SecondPassRow(
        column=item.display,
        dataset_id=item.dataset,
        field_id=item.field,
        analysis=label,
        status=item.status,
        kind=_NOT_COMPUTED,
        summary=f"Not computed: {why}",
    )


def second_pass_view(analyses: AnalysesBlock | None, dataset: str) -> SecondPassView:
    """What the second pass did for one dataset."""
    if analyses is None:
        return SecondPassView()
    document = analyses.deep
    if document is None:
        return SecondPassView(
            available=True, mode=analyses.mode, outcome=analyses.outcome, reason=analyses.reason
        )
    rows = [_row(item) for item in document.analyses if item.dataset == dataset]
    plan = [c for c in document.plan.candidates if c.dataset == dataset]
    states = Counter(c.selection.state for c in plan)
    left_out: Counter[str] = Counter()
    for candidate in plan:
        if candidate.selection.state != "rejected":
            continue
        code = candidate.selection.reason or ""
        if code == "not_applicable" and candidate.applicability.reasons:
            code = candidate.applicability.reasons[0]
        left_out[reason_text(code)] += 1
    statuses = Counter(row.status for row in rows)
    run = document.run
    return SecondPassView(
        available=True,
        mode=analyses.mode,
        outcome=analyses.outcome,
        reason=analyses.reason,
        metrics=SecondPassMetrics(
            computed=statuses["complete"] + statuses["limited"],
            skipped=statuses["skipped"],
            failed=statuses["failed"],
            already_answered=states["already_satisfied"],
            not_selected=states["rejected"],
        ),
        rows=rows,
        left_out=left_out.most_common(),
        source_read=run.source_read,
        source_verified=run.source_verified,
        seconds=run.duration_seconds,
        executed=run.executed,
        reused=run.reused,
    )
