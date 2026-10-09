# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The relationships the report shows (HTML-06, REL-13 to REL-16, design 20.13).

Everything here is computed when a page is rendered, from the ``analyses`` member
of the document: no source, no recomputation (HTML-01). The page shows counts and
conditional percentages first, then the scores, and the exceptions without
requiring anyone to know what Cramér's V or Pearson's r is.
"""

from __future__ import annotations

from tabalyst.models import AnalysesBlock
from tabalyst.report_labels import (
    FEATURE_WORDS,
    PEARSON_REASONS,
    STRENGTH_LIMITS,
    TABLE_REASONS,
)
from tabalyst.report_views import (
    CorrelationRow,
    RelationCell,
    RelationException,
    RelationGroup,
    RelationRow,
    RelationRule,
    RelationsView,
    RelationTable,
)
from tabalyst.scanner.features import FEATURES
from tabalyst.scanner.planner.models import AnalysisPlan
from tabalyst.scanner.secondpass.models import (
    AnalysisResult,
    CrosstabResult,
    PearsonResult,
)

# Groups of two columns a page prints, strongest first.
MAX_GROUPS = 20


def strength_word(score: float) -> str:
    """The word for a bias-corrected Cramér's V."""
    for limit, word in STRENGTH_LIMITS:
        if score < limit:
            return word
    return "strong"


def _feature_label(result: CrosstabResult) -> str:
    word = FEATURE_WORDS.get(result.feature.kind, result.feature.kind)
    if result.feature.kind == "prefix" and result.feature.prefix_length:
        return f"{word} of {result.feature.prefix_length} characters"
    return word


def _left_out(result: CrosstabResult) -> str:
    excluded = result.excluded
    parts = []
    if excluded.feature_missing:
        parts.append(f"{excluded.feature_missing:,} have no value in {result.classes.display}")
    if excluded.category_missing:
        parts.append(f"{excluded.category_missing:,} have no {result.categories.display}")
    if excluded.both_missing:
        parts.append(f"{excluded.both_missing:,} have neither column")
    if excluded.unclassified:
        parts.append(f"{excluded.unclassified:,} have a value the feature does not classify")
    return "; ".join(parts)


def _table(item: AnalysisResult, result: CrosstabResult, leading: bool) -> RelationTable:
    categories, classes = result.categories.classes, result.classes.classes
    # An empty `other` axis is not printed: it was not needed (REL-12).
    keep_rows = [
        i for i, c in enumerate(categories) if c.kind != "other" or result.row_totals[i]
    ]
    keep_columns = [
        j for j, c in enumerate(classes) if c.kind != "other" or result.column_totals[j]
    ]
    rows: list[RelationRow] = []
    for i in keep_rows:
        summary = result.by_category[i]
        cells = []
        for j in keep_columns:
            count = result.counts[i][j]
            cells.append(
                RelationCell(
                    count=count,
                    share=None if summary.classified == 0 else count / summary.classified,
                    dominant=count > 0 and j == summary.dominant,
                    exception=count > 0 and j != summary.dominant,
                )
            )
        rows.append(
            RelationRow(
                label=categories[i].label,
                other=categories[i].kind == "other",
                cells=cells,
                classified=summary.classified,
                rows=summary.rows,
                coverage=summary.coverage,
                dominant=None if summary.dominant is None else classes[summary.dominant].label,
                purity=summary.purity,
                exceptions=summary.exceptions,
            )
        )
    found = result.association
    strength: str | None = None
    note: str | None = None
    score = found.corrected
    if score is None:
        note = f"No score: {TABLE_REASONS.get(found.reason or '', found.reason or 'undefined')}."
    elif found.stable is False:
        strength = "unstable"
        note = (
            f"The expected counts are below 5 in {found.low_share or 0:.0%} of the cells: "
            "this score is not reliable and says little."
        )
    else:
        strength = strength_word(score)
    word = _feature_label(result)
    forward = result.purity.forward.value
    baseline = result.purity.baseline
    if forward is None:
        sentence = "No row has both a category and a value to classify."
    else:
        sentence = (
            f"{result.counted:,} of {result.rows:,} rows are classified. The dominant "
            f"{word} of each {result.categories.display} holds {forward:.1%} of them"
            + (
                f"; the most frequent {word} overall holds {baseline:.1%}."
                if baseline is not None
                else "."
            )
        )
    exceptions = [
        RelationException(
            category=categories[cell.category].label,
            label=classes[cell.column].label,
            count=cell.count,
            examples=[(e.record, e.value) for e in cell.examples],
        )
        for cell in result.exceptions.listed
    ]
    rules = [
        RelationRule(
            category=categories[rule.category].label,
            label=classes[rule.column].label,
            support=rule.support,
            confidence=rule.confidence,
            exceptions=rule.exceptions,
        )
        for rule in result.rules
    ]
    return RelationTable(
        feature=result.feature.kind,
        feature_label=word,
        leading=leading,
        source=result.source,
        sentence=sentence,
        classes=[classes[j].label for j in keep_columns],
        other_class=any(classes[j].kind == "other" for j in keep_columns),
        rows=rows,
        column_totals=[result.column_totals[j] for j in keep_columns],
        total=result.counted,
        counted=result.counted,
        examined=result.rows,
        left_out=_left_out(result),
        purity=forward,
        reverse_purity=result.purity.reverse.value,
        baseline=baseline,
        score=score,
        strength=strength,
        note=note,
        exceptions=exceptions,
        exception_count=result.exceptions.count,
        exception_cells=result.exceptions.cells,
        rules=rules,
    )


def _groups(analyses: list[AnalysisResult]) -> list[RelationGroup]:
    grouped: dict[tuple[str, str], list[tuple[AnalysisResult, CrosstabResult]]] = {}
    for item in analyses:
        if item.analyzer != "category_crosstab" or item.partner is None:
            continue
        if item.status != "complete" or not isinstance(item.result, CrosstabResult):
            continue
        grouped.setdefault((item.field, item.partner), []).append((item, item.result))
    groups: list[tuple[float, RelationGroup]] = []
    for members in grouped.values():
        # The feature that says most leads; the others stay, collapsed (REL-16).
        members.sort(
            key=lambda pair: (
                -(pair[1].association.corrected if pair[1].association.corrected is not None else -1.0),
                FEATURES.index(pair[1].feature.kind),
            )
        )
        first = members[0][1]
        best = first.association.corrected
        tables = [
            _table(item, result, leading=number == 0)
            for number, (item, result) in enumerate(members)
        ]
        groups.append(
            (
                -1.0 if best is None else best,
                RelationGroup(
                    category=first.categories.display,
                    column=first.classes.display,
                    tables=tables,
                ),
            )
        )
    groups.sort(key=lambda pair: -pair[0])
    return [group for _, group in groups[:MAX_GROUPS]]


def _correlations(analyses: list[AnalysisResult]) -> list[CorrelationRow]:
    rows = []
    for item in analyses:
        result = item.result
        if (
            item.analyzer != "pearson_correlation"
            or item.status != "complete"
            or not isinstance(result, PearsonResult)
        ):
            continue
        left_out = sum(result.excluded.model_dump().values())
        if result.coefficient is None:
            note = f"No coefficient: {PEARSON_REASONS.get(result.reason or '', result.reason or 'undefined')}."
        elif left_out:
            note = f"{left_out:,} of {result.rows:,} rows lack a number in one column."
        else:
            note = ""
        rows.append(
            CorrelationRow(
                pair=item.display,
                coefficient=result.coefficient,
                pairs=result.pairs,
                rows=result.rows,
                note=note,
            )
        )
    rows.sort(key=lambda row: -abs(row.coefficient if row.coefficient is not None else 0.0))
    return rows


def _plural(count: int, noun: str) -> str:
    return f"{count:,} {noun}{'' if count == 1 else 's'}"


def _reasons(counts: dict[str, int]) -> str:
    return ", ".join(
        f"{number:,} {TABLE_REASONS.get(reason, PEARSON_REASONS.get(reason, reason))}"
        for reason, number in counts.items()
    )


def _explored(plan: AnalysisPlan, dataset: str) -> list[str]:
    """What the planner looked at before it proposed tables and pairs: a relation
    not detected in a sample may still exist in the file (REL-05)."""
    notes: list[str] = []
    relations = plan.relations
    if relations is None:
        return notes
    for block in relations.tables:
        if block.dataset != dataset or block.unavailable:
            continue
        where = "every row" if block.scope == "all_rows" else "the sampled rows of the interior"
        note = (
            f"{_plural(block.possible, 'table')} of a category against a feature "
            f"{'was' if block.possible == 1 else 'were'} explored on {where} "
            f"({block.rows:,} rows): {block.listed:,} listed"
        )
        if block.undefined:
            note += f", {_reasons(block.undefined_reasons)}"
        notes.append(note + ". A relation not found in a sample may still exist in the file.")
    for pairs in relations.datasets:
        if pairs.dataset != dataset or pairs.unavailable or not pairs.possible:
            continue
        where = "every row" if pairs.scope == "all_rows" else "the sampled rows of the interior"
        notes.append(
            f"{_plural(pairs.possible, 'pair')} of numeric columns "
            f"{'was' if pairs.possible == 1 else 'were'} explored on {where} "
            f"({pairs.rows:,} rows): {pairs.listed:,} listed."
        )
    return notes


def relations_view(analyses: AnalysesBlock | None, dataset: str) -> RelationsView:
    """The relationships of one dataset that the second pass computed."""
    if analyses is None or analyses.deep is None:
        return RelationsView()
    items = [item for item in analyses.deep.analyses if item.dataset == dataset]
    return RelationsView(
        groups=_groups(items),
        correlations=_correlations(items),
        notes=_explored(analyses.deep.plan, dataset),
    )
