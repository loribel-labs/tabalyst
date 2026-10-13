# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Advice on stratified sampling, from the Scan alone (design 20.14, lot 9).

One column at a time (is it a good key, how many strata, how unbalanced) and
several columns together (a saturating bound on the combinations, the ones the
row sample has seen). Nothing is read from the source and no value of the data
is written.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from tabalyst.errors import ConfigurationError
from tabalyst.scanner.models import (
    CardinalityComplete,
    CardinalityLimited,
    DatasetResult,
    FieldResult,
    ScanResult,
)
from tabalyst.scanner.planner.facts import FieldFacts, scan_facts
from tabalyst.scanner.planner.identifiers import identifier_like, uniqueness
from tabalyst.scanner.planner.samplerows import cell_text, usable_rows
from tabalyst.scanner.planner.stratmodels import (
    Basis,
    ColumnAdvice,
    CombinationAdvice,
    Risk,
    Stratification,
    StratificationLimits,
)
from tabalyst.scanner.stratify import (
    allocate_strata,
    saturating_product,
    size_for_every_stratum,
)

STRATIFICATION_VERSION = 1

# A column with more distinct values is not a good key by itself, and more
# than half of the values distinct is a column that never repeats.
MAX_STRATA_PER_COLUMN = 50
MAX_UNIQUE_SHARE = 0.5
# Strata from which the risk is called moderate, high, and excessive. The last
# is also the ceiling of the states a stratified sample may hold (STRAT-08).
MODERATE_ABOVE = 1_000
HIGH_ABOVE = 10_000
MAX_STATES = 100_000
MAX_FIELDS = 8
EXPLORE_MIN_ROWS = 30
# At or below this share a stratum is rare enough to be absent from a small sample.
RARE_SHARE = 0.01


@dataclass(frozen=True, slots=True)
class Stratify:
    """What to advise on. Every column is always assessed; each tuple of
    ``combinations`` (field ids or display paths) is assessed together.
    ``dataset`` narrows the fields to one dataset (needed when several datasets
    have the same field) and ``sample_size`` lets the advice count the strata
    the classic allocation would leave without a row."""

    combinations: tuple[tuple[str, ...], ...] = ()
    dataset: str | None = None
    sample_size: int | None = None
    max_states: int = MAX_STATES


def risk_for(strata: int, saturated: bool, max_states: int) -> Risk:
    """The risk class of a number of strata. A high bound proves a risk, not an
    explosion: the combinations that exist can be far fewer."""
    if saturated or strata > max_states:
        return "excessive"
    if strata > HIGH_ABOVE:
        return "high"
    if strata > MODERATE_ABOVE:
        return "moderate"
    return "low"


def _round(value: float) -> float:
    return round(value, 6)


def _strata(field: FieldResult) -> tuple[int | None, Basis | None, int | None]:
    """``(strata, basis, bound)``: the distinct original values and one stratum
    for the missing values when there are any (the key of ``sample`` makes an
    empty cell a stratum)."""
    extra = 1 if field.missing.count > 0 else 0
    cardinality = field.values.cardinality
    if isinstance(cardinality, CardinalityComplete):
        count = cardinality.value + extra
        return count, "exact", count
    if isinstance(cardinality, CardinalityLimited):
        bound = (
            cardinality.upper_bound if cardinality.upper_bound is not None else field.values.count
        ) + extra
        if cardinality.estimate is not None:
            return round(cardinality.estimate.value) + extra, "estimate", bound
        return None, "bound", bound
    return None, None, None


def _column(
    dataset: DatasetResult,
    field: FieldResult,
    facts: FieldFacts,
    sample_size: int | None,
    max_states: int,
) -> ColumnAdvice:
    strata, basis, bound = _strata(field)
    reasons: list[str] = []
    candidate = True
    rows = dataset.record_count
    missing_share = _round(field.missing.count / rows) if rows else None

    if facts.values == 0:
        reasons.append("no_values")
    elif facts.withheld:
        reasons.append("sensitive_exposure")
    elif facts.repeated:
        reasons.append("repeated_path")
    elif identifier_like(facts):
        reasons.append("identifier")
    else:
        share = uniqueness(facts)
        if share is not None and share > MAX_UNIQUE_SHARE:
            reasons.append("near_unique")
    if not reasons:
        if strata is None or basis == "bound":
            reasons.append("cardinality_unknown")
        elif strata < 2:
            reasons.append("single_value")
        elif strata > MAX_STRATA_PER_COLUMN:
            reasons.append("too_many_strata")
    candidate = not reasons

    smallest = largest = None
    uncovered = None
    size_all = None
    envelope = field.values.frequencies
    exact_counts = (
        envelope.status == "complete"
        and not envelope.value.truncated
        and not facts.withheld
        and facts.values > 0
    )
    if candidate:
        if exact_counts:
            counts = [item.count for item in envelope.value.listed]
            if field.missing.count > 0:
                counts.append(field.missing.count)
            total = sum(counts)
            smallest, largest = _round(min(counts) / total), _round(max(counts) / total)
            size_all = size_for_every_stratum(min(counts), total)
            if sample_size is not None:
                quotas = allocate_strata(dict(enumerate(counts)), sample_size)
                uncovered = sum(1 for quota in quotas.values() if quota == 0)
            if smallest <= RARE_SHARE or uncovered:
                reasons.append("rare_strata")
        else:
            reasons.append("no_exact_frequencies")
        if basis == "estimate":
            reasons.append("estimated_strata")
    return ColumnAdvice(
        dataset=dataset.id,
        field=field.id,
        display=field.display,
        candidate=candidate,
        reasons=reasons,
        risk=risk_for(bound, False, max_states) if candidate and bound is not None else None,
        strata=strata,
        strata_basis=basis,
        strata_bound=bound,
        missing_share=missing_share,
        smallest_share=smallest,
        largest_share=largest,
        size_for_every_stratum=size_all,
        uncovered_at_size=uncovered,
    )


def _resolve(scan: ScanResult, request: Stratify, names: Sequence[str]) -> DatasetResult:
    """The dataset that has every named field; raises ``ConfigurationError``."""
    found: list[DatasetResult] = []
    for dataset in scan.datasets:
        if request.dataset is not None and dataset.id != request.dataset:
            continue
        known = {name for field in dataset.fields for name in (field.id, field.display)}
        if set(names) <= known:
            found.append(dataset)
    if not found:
        raise ConfigurationError(
            f"No dataset has every field of the combination: {', '.join(names)}."
        )
    if len(found) > 1:
        raise ConfigurationError(
            f"Several datasets have the fields {', '.join(names)}; name the dataset."
        )
    return found[0]


def _combination(
    dataset: DatasetResult,
    names: Sequence[str],
    columns: dict[str, ColumnAdvice],
    results: dict[str, FieldResult],
    max_states: int,
    sample_size: int | None,
) -> CombinationAdvice:
    chosen = [results[name] for name in names]
    if len({field.id for field in chosen}) != len(chosen):
        raise ConfigurationError("A field is named twice in a combination.")
    if len(chosen) < 2:
        raise ConfigurationError("A combination needs at least two fields.")
    if len(chosen) > MAX_FIELDS:
        raise ConfigurationError(f"A combination takes at most {MAX_FIELDS} fields.")

    reasons: list[str] = []
    bounds: list[int] = []
    estimates: list[int] = []
    unknown = False
    for field in chosen:
        advice = columns[field.id]
        if advice.strata_bound is None:
            unknown = True
            bounds.append(dataset.record_count)
            estimates.append(dataset.record_count)
        else:
            bounds.append(advice.strata_bound)
            estimates.append(advice.strata if advice.strata is not None else advice.strata_bound)
        for code in ("sensitive_exposure", "repeated_path", "no_values"):
            if code in advice.reasons and code not in reasons:
                reasons.append(code)
    product, saturated = saturating_product(bounds)
    rows = dataset.record_count
    bound = min(product, rows) if rows else product
    capped = product > bound
    estimate_product, _ = saturating_product(estimates)
    if estimate_product != product:
        estimate_value: int | None = min(estimate_product, rows) if rows else estimate_product
    else:
        estimate_value = None
    if unknown:
        reasons.append("cardinality_unknown")
    elif estimate_value is not None or any(
        columns[field.id].strata_basis == "estimate" for field in chosen
    ):
        reasons.append("estimated_strata")
    if capped:
        reasons.append("capped_by_records")

    observed = None
    observed_exact = False
    sample_rows = None
    scope = None
    usable, why = usable_rows(dataset, EXPLORE_MIN_ROWS)
    ids = [field.id for field in chosen]
    if usable is not None and usable.sample.covers(ids):
        keys = {tuple(cell_text(row, field_id) for field_id in ids) for row in usable.rows}
        observed = len(keys)
        sample_rows = len(usable.rows)
        observed_exact = usable.complete
        scope = usable.scope
    else:
        reasons.append(why if why is not None else "sample_does_not_cover")

    # The exact number of combinations, when the sample holds every row, is a
    # better basis for the risk than the product of bounds.
    basis_count = observed if observed_exact and observed is not None else bound
    risk = risk_for(basis_count, saturated and not observed_exact, max_states)
    if saturated and observed_exact:
        reasons.append("exact_from_sample")
    if risk != "low":
        reasons.append("bound_exceeds_states" if basis_count > max_states else "many_strata")

    mean_quota = None
    if sample_size is not None and not saturated and bound > 0:
        mean_quota = _round(sample_size / bound)
        if mean_quota < 1:
            reasons.append("mean_quota_below_one")
    widest = max(chosen, key=lambda field: columns[field.id].strata_bound or 0).id
    suggestions: list[str] = []
    if risk in ("high", "excessive"):
        suggestions = ["reduce_fields", "set_explicit_limit", "use_smart"]
    elif risk == "moderate":
        suggestions = ["reduce_fields"]
    return CombinationAdvice(
        dataset=dataset.id,
        fields=ids,
        displays=[field.display for field in chosen],
        strata_bound=bound,
        saturated=saturated,
        strata_estimate=estimate_value,
        observed=observed,
        observed_exact=observed_exact,
        sample_rows=sample_rows,
        sample_scope=scope,
        risk=risk,
        reasons=reasons,
        suggestions=suggestions,
        widest_field=widest if risk != "low" else None,
        mean_quota=mean_quota,
    )


def advise_stratification(
    scan: ScanResult,
    request: Stratify | None = None,
    facts_list: Sequence[FieldFacts] | None = None,
) -> Stratification:
    """The advice for stratified sampling: every column assessed, and each
    combination of ``request`` assessed together.

    Reads the Scan only; raises ``ConfigurationError`` for a combination that
    names an unknown field, an ambiguous dataset or fewer than two fields.
    ``facts_list`` is the ``scan_facts`` the caller already built.
    """
    request = Stratify() if request is None else request
    if request.sample_size is not None and request.sample_size < 1:
        raise ConfigurationError("The sample size must be at least 1.")
    facts = {
        (item.dataset, item.field): item
        for item in (scan_facts(scan) if facts_list is None else facts_list)
    }
    columns: list[ColumnAdvice] = []
    by_dataset: dict[str, dict[str, ColumnAdvice]] = {}
    for dataset in scan.datasets:
        if request.dataset is not None and dataset.id != request.dataset:
            continue
        mapping: dict[str, ColumnAdvice] = {}
        for field in dataset.fields:
            advice = _column(
                dataset, field, facts[(dataset.id, field.id)], request.sample_size, request.max_states
            )
            columns.append(advice)
            mapping[field.id] = advice
        by_dataset[dataset.id] = mapping

    combinations: list[CombinationAdvice] = []
    for names in request.combinations:
        dataset = _resolve(scan, request, names)
        results = {
            name: field for field in dataset.fields for name in (field.id, field.display)
        }
        combinations.append(
            _combination(
                dataset,
                names,
                by_dataset[dataset.id],
                results,
                request.max_states,
                request.sample_size,
            )
        )
    return Stratification(
        version=STRATIFICATION_VERSION,
        limits=StratificationLimits(
            max_strata_per_column=MAX_STRATA_PER_COLUMN,
            moderate_above=MODERATE_ABOVE,
            high_above=HIGH_ABOVE,
            max_states=request.max_states,
            max_fields=MAX_FIELDS,
            explore_min_rows=EXPLORE_MIN_ROWS,
        ),
        sample_size=request.sample_size,
        columns=columns,
        combinations=combinations,
    )
