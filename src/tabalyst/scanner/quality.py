# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Observations, quality issues and limits of a finished scan (design 18.13).

Computed from the facts and from ``derived``, once, after the scan: no value
is read and none is written, only counts and references.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field

from pydantic import BaseModel

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.models import (
    Complete,
    DatasetResult,
    DerivedPatterns,
    Diagnostic,
    FieldPatterns,
    FieldPatternsComplete,
    FieldPatternsFailed,
    FieldResult,
    Limit,
    Limited,
    NormalizationStage,
    Observation,
    ObservationAccuracy,
    ObservationPopulation,
    Observations,
    QualitySummary,
    Scope,
    SourceInfo,
)
from tabalyst.scanner.patterninfer import MAX_VALUES

OBSERVATIONS_VERSION = 1
# A minority pattern (``minority_pattern``): a candidate that covers at most
# this share of the distinct values next to a principal one that covers at
# least ``PRINCIPAL_MIN_SHARE``. Constants of the rule version, not settings.
PRINCIPAL_MIN_SHARE = 0.8
MINORITY_MAX_SHARE = 0.05
# Diagnostics of records excluded under the tolerant error policy.
EXCLUSION_CODES = frozenset(
    {
        "csv_width_mismatch",
        "record_too_large",
        "json_duplicate_key",
        "jsonl_invalid_line",
        "jsonl_record_not_object",
        "jsonl_line_too_long",
    }
)
# Stages whose output is the analytical value (design section 10).
ANALYTICAL_STAGES = ("nfc", "trim", "collapse_whitespace")
# Rule -> (category, status): fixed by the version of the rules (QUAL-02).
RULES: dict[str, tuple[str, str]] = {
    "excluded_records": ("records", "confirmed_issue"),
    "ambiguous_header": ("names", "confirmed_issue"),
    "duplicate_rows": ("records", "candidate_anomaly"),
    "mixed_types": ("types", "candidate_anomaly"),
    "type_outliers": ("types", "candidate_anomaly"),
    "ambiguous_dates": ("dates", "candidate_anomaly"),
    "variant_groups": ("normalization", "candidate_anomaly"),
    "minority_pattern": ("patterns", "candidate_anomaly"),
    "missing_values": ("presence", "informational"),
    "empty_column": ("presence", "informational"),
    "constant_column": ("values", "informational"),
    "trimmed_cells": ("normalization", "informational"),
    "collapsed_whitespace": ("normalization", "informational"),
}
_RANK = {"confirmed_issue": 0, "candidate_anomaly": 1, "informational": 2}


def limited_envelopes(model: object, location: str) -> Iterator[tuple[str, Limited]]:
    """Every ``limited`` envelope under a scan model, with its location. The
    ``value`` of a complete envelope is left out of locations; the stages of
    the normalization are named by their stage.

    Lists other than the stages are not entered: the samples, listings and
    histograms hold up to thousands of entries and no envelope.
    """
    if isinstance(model, Limited):
        yield location, model
    elif isinstance(model, BaseModel):
        for name in type(model).model_fields:
            if isinstance(model, Complete):
                inner = location
            else:
                inner = f"{location}.{name}" if location else name
            yield from limited_envelopes(getattr(model, name), inner)
    elif isinstance(model, list):
        for item in model:
            if isinstance(item, NormalizationStage):
                yield from limited_envelopes(item, f"{location}.{item.stage}")


def value_slots(field: FieldResult) -> int:
    """Occurrences plus the parent objects where the member is absent."""
    return field.occurrences + (field.presence.absent or 0)


def analytical_distinct(field: FieldResult) -> int | None:
    """Distinct analytical values when exact, ``None`` otherwise."""
    measure = field.values.cardinality
    for stage in field.normalization.stages:
        if stage.stage in ANALYTICAL_STAGES and stage.enabled:
            measure = stage.cardinality
    return measure.value if isinstance(measure, Complete) else None


def _best_family_count(field: FieldResult) -> int:
    """Values of the family that comes closest to the technical type."""
    counts = field.technical_type.counts
    integers = counts.get("integer", 0)
    return max(
        integers,
        integers + counts.get("number", 0),
        counts.get("date", 0),
        counts.get("boolean", 0),
        counts.get("text", 0),
    )


@dataclass
class _Draft:
    """An observation before it is ranked and numbered."""

    rule: str
    population: ObservationPopulation
    count: int
    accuracy: ObservationAccuracy = "exact"
    dataset: str | None = None
    field: str | None = None
    of: int | None = None
    records: list[int] = dataclass_field(default_factory=list)
    patterns: list[str] = dataclass_field(default_factory=list)
    diagnostics: list[int] = dataclass_field(default_factory=list)
    limited_by: list[str] = dataclass_field(default_factory=list)


@dataclass
class _Collected:
    limits: list[Limit] = dataclass_field(default_factory=list)
    drafts: list[_Draft] = dataclass_field(default_factory=list)

    def limit(
        self,
        dataset: str | None,
        field_id: str | None,
        measure: str,
        reason: str,
        limit: int | None = None,
        lower_bound: int | None = None,
        diagnostic: int | None = None,
    ) -> str:
        """Record a limit and return its identifier."""
        identifier = f"l{len(self.limits) + 1}"
        self.limits.append(
            Limit(
                id=identifier,
                dataset=dataset,
                field=field_id,
                measure=measure,
                reason=reason,
                limit=limit,
                lower_bound=lower_bound,
                diagnostic=diagnostic,
            )
        )
        return identifier


def build_observations(
    *,
    datasets: list[DatasetResult],
    diagnostics: list[Diagnostic],
    scope: Scope,
    source: SourceInfo,
    config: ScanConfig,
    patterns: DerivedPatterns | None,
) -> Observations:
    """The observations, quality issues and limits of a scan.

    Deterministic: the same facts give the same document.
    """
    entries = {
        (entry.dataset, entry.field): entry
        for entry in (patterns.fields if patterns is not None else ())
    }
    found = _Collected()
    for dataset in datasets:
        duplicates = _dataset_limits(dataset, config, found)
        _dataset_observations(dataset, duplicates, found)
        for field_result in dataset.fields:
            pattern_limits = _field_limits(
                dataset, field_result, entries.get((dataset.id, field_result.id)), config, found
            )
            _field_observations(
                dataset,
                field_result,
                entries.get((dataset.id, field_result.id)),
                pattern_limits,
                source,
                found,
            )
    _excluded_records(scope, diagnostics, config, found)
    # A stable sort keeps the order of the datasets and fields within a status.
    drafts = sorted(
        found.drafts, key=lambda draft: _RANK[RULES[draft.rule][1]]
    )
    maximum = config.observations.max_items
    items = [_observation(number, draft) for number, draft in enumerate(drafts[:maximum], 1)]
    summaries = _summaries(datasets, drafts, found.limits)
    return Observations(
        version=OBSERVATIONS_VERSION,
        truncated=len(drafts) > maximum or len(found.limits) > maximum,
        summary=summaries[0],
        datasets=summaries[1:],
        items=items,
        limits=found.limits[:maximum],
    )


def _observation(number: int, draft: _Draft) -> Observation:
    category, status = RULES[draft.rule]
    return Observation(
        id=f"o{number}",
        rule=draft.rule,
        category=category,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        dataset=draft.dataset,
        field=draft.field,
        population=draft.population,
        count=draft.count,
        of=draft.of,
        accuracy=draft.accuracy,
        records=draft.records,
        patterns=draft.patterns,
        diagnostics=draft.diagnostics,
        limited_by=draft.limited_by,
    )


def _summaries(
    datasets: list[DatasetResult], drafts: list[_Draft], limits: list[Limit]
) -> list[QualitySummary]:
    """The whole scan first, then each dataset in order."""
    by_dataset: dict[str, tuple[list[_Draft], list[Limit]]] = {
        dataset.id: ([], []) for dataset in datasets
    }
    for draft in drafts:
        if draft.dataset in by_dataset:
            by_dataset[draft.dataset][0].append(draft)
    for limit in limits:
        if limit.dataset in by_dataset:
            by_dataset[limit.dataset][1].append(limit)
    groups: list[tuple[str | None, list[_Draft], list[Limit]]] = [
        (None, drafts, limits)
    ] + [(dataset_id, *found) for dataset_id, found in by_dataset.items()]
    summaries = []
    for dataset_id, selected, listed in groups:
        statuses = [RULES[draft.rule][1] for draft in selected]
        confirmed = statuses.count("confirmed_issue")
        candidates = statuses.count("candidate_anomaly")
        remarks = statuses.count("informational")
        summaries.append(
            QualitySummary(
                dataset=dataset_id,
                informational=remarks,
                candidate_anomalies=candidates,
                confirmed_issues=confirmed,
                limits=len(listed),
                has_observations=bool(selected),
                has_quality_issues=bool(confirmed or candidates),
                has_limits=bool(listed),
            )
        )
    return summaries


# Limits ------------------------------------------------------------------------


def _dataset_limits(
    dataset: DatasetResult, config: ScanConfig, found: _Collected
) -> list[str]:
    """Limits of the structure and of the records of a dataset; returns the ids
    of those that stop its duplicate count from being exact."""
    duplicates: list[str] = []
    for part in ("structure", "records"):
        for location, measure in limited_envelopes(getattr(dataset, part), part):
            identifier = found.limit(
                dataset.id,
                None,
                location,
                measure.reason,
                measure.limit,
                measure.lower_bound,
            )
            if location == "records.duplicates.count":
                duplicates.append(identifier)
    structure = dataset.structure
    if structure.depth_truncated_observations:
        found.limit(
            dataset.id,
            None,
            "structure.depth_truncated_observations",
            "max_depth",
            config.limits.max_depth,
        )
    sample = dataset.records.sample
    if sample is not None:
        if sample.reason is not None:
            found.limit(dataset.id, None, "records.sample", sample.reason, sample.middle_k)
        if sample.fields_limited:
            found.limit(
                dataset.id,
                None,
                "records.sample.fields",
                "max_fields",
                config.limits.max_fields,
            )
    return duplicates


def _field_limits(
    dataset: DatasetResult,
    field_result: FieldResult,
    entry: FieldPatterns | None,
    config: ScanConfig,
    found: _Collected,
) -> list[str]:
    """Limits of a field; returns the ids of those of its pattern inference."""
    where = (dataset.id, field_result.id)
    # The raw stage repeats ``values.cardinality`` and a stage that changed
    # nothing repeats the limit of its input: each limit is listed once.
    repeated = tuple(
        f"normalization.stages.{stage.stage}."
        for stage in field_result.normalization.stages
        if stage.equals is not None or stage.stage == "raw"
    )
    for location, measure in limited_envelopes(field_result, ""):
        if location.startswith(repeated):
            continue
        found.limit(
            *where, location, measure.reason, measure.limit, measure.lower_bound
        )
    samples = field_result.values.samples
    if samples.reason is not None:
        found.limit(*where, "values.samples", samples.reason, samples.k)
    if samples.kept < samples.of:
        found.limit(*where, "values.samples", "exposure")
    if samples.long_texts is not None and samples.long_texts.requested_k is not None:
        found.limit(
            *where, "values.samples.long_texts", "memory_budget", samples.long_texts.k
        )
    strata = samples.by_length
    if strata is not None:
        if strata.requested_max_lengths is not None:
            found.limit(
                *where, "values.samples.by_length", "memory_budget", strata.max_lengths
            )
        elif strata.limited:
            found.limit(
                *where, "values.samples.by_length", "max_length_strata", strata.max_lengths
            )
    identifiers: list[str] = []
    if isinstance(entry, FieldPatternsFailed):
        found.limit(*where, "derived.patterns", entry.reason, diagnostic=entry.diagnostic)
    elif isinstance(entry, FieldPatternsComplete):
        sizes = {
            "max_patterns": config.pattern_inference.max_patterns,
            "max_values": MAX_VALUES,
        }
        for reason in entry.limits:
            identifiers.append(
                found.limit(*where, "derived.patterns", reason, sizes[reason])
            )
    return identifiers


# Observations ------------------------------------------------------------------


def _dataset_observations(
    dataset: DatasetResult, duplicate_limits: list[str], found: _Collected
) -> None:
    duplicates = dataset.records.duplicates
    count = duplicates.count
    if isinstance(count, Complete) and count.value:
        found.drafts.append(
            _Draft(
                "duplicate_rows",
                "records",
                count.value,
                dataset=dataset.id,
                of=dataset.record_count,
                records=list(duplicates.records),
            )
        )
    elif isinstance(count, Limited) and count.lower_bound:
        found.drafts.append(
            _Draft(
                "duplicate_rows",
                "records",
                count.lower_bound,
                accuracy="lower_bound",
                dataset=dataset.id,
                of=dataset.record_count,
                records=list(duplicates.records),
                limited_by=duplicate_limits,
            )
        )


def _excluded_records(
    scope: Scope,
    diagnostics: list[Diagnostic],
    config: ScanConfig,
    found: _Collected,
) -> None:
    """Records the tolerant error policy left out of the analysis."""
    if not scope.records_excluded:
        return
    indices = [
        index
        for index, diagnostic in enumerate(diagnostics)
        if diagnostic.code in EXCLUSION_CODES
    ]
    records = sorted(
        location["record"]
        for index in indices
        for location in diagnostics[index].locations
        if "record" in location
    )
    found.drafts.append(
        _Draft(
            "excluded_records",
            "records",
            scope.records_excluded,
            of=scope.records_read,
            records=records[: config.limits.max_listed_records],
            diagnostics=indices,
        )
    )


def _field_observations(
    dataset: DatasetResult,
    field_result: FieldResult,
    entry: FieldPatterns | None,
    pattern_limits: list[str],
    source: SourceInfo,
    found: _Collected,
) -> None:
    add = found.drafts.append
    where = {"dataset": dataset.id, "field": field_result.id}
    slots = value_slots(field_result)
    values = field_result.values.count
    technical = field_result.technical_type
    if technical.type == "empty":
        if slots:
            add(_Draft("empty_column", "value_slots", slots, of=slots, **where))
    elif field_result.missing.count:
        add(
            _Draft(
                "missing_values",
                "value_slots",
                field_result.missing.count,
                of=slots,
                **where,
            )
        )
    if technical.type != "empty" and values >= 2 and analytical_distinct(field_result) == 1:
        add(_Draft("constant_column", "value_slots", values, of=slots, **where))
    if technical.type == "mixed":
        add(
            _Draft(
                "mixed_types",
                "occurrences",
                values - _best_family_count(field_result),
                of=values,
                **where,
            )
        )
    elif technical.outside_count and technical.type not in ("text", "empty"):
        add(
            _Draft(
                "type_outliers", "occurrences", technical.outside_count, of=values, **where
            )
        )
    temporal = field_result.temporal
    if isinstance(temporal, Complete) and temporal.value.ambiguous:
        add(
            _Draft(
                "ambiguous_dates",
                "occurrences",
                temporal.value.ambiguous,
                # The date values: ``count`` leaves the ambiguous ones out.
                of=temporal.value.count + temporal.value.ambiguous,
                **where,
            )
        )
    for stage in field_result.normalization.stages:
        rule = {"trim": "trimmed_cells", "collapse_whitespace": "collapsed_whitespace"}.get(
            stage.stage
        )
        if rule is not None and stage.changed:
            add(
                _Draft(
                    rule,
                    "content_strings",
                    stage.changed,
                    of=field_result.strings.content,
                    **where,
                )
            )
    groups = field_result.normalization.variant_groups
    if isinstance(groups, Complete) and groups.value.groups:
        add(_Draft("variant_groups", "groups", groups.value.groups, **where))
    header = source.header
    if header is not None and dataset.kind == "table":
        name = field_result.name
        written = header.count(name)
        if not name.strip() or written > 1:
            add(_Draft("ambiguous_header", "columns", written, **where))
    if isinstance(entry, FieldPatternsComplete):
        _minority_pattern(entry, pattern_limits, where, add)


def _minority_pattern(
    entry: FieldPatternsComplete,
    limits: list[str],
    where: dict[str, str],
    add: Callable[[_Draft], None],
) -> None:
    """Rare structures next to a dominant one, in the distinct values the
    inference read: an atypical form worth a look, never an error by itself."""
    candidates = entry.candidates
    if len(candidates) < 2 or candidates[0].coverage.share < PRINCIPAL_MIN_SHARE:
        return
    minority = [
        candidate
        for candidate in candidates[1:]
        if candidate.coverage.share <= MINORITY_MAX_SHARE
    ]
    if not minority:
        return
    exact = candidates[0].coverage.basis == "all_distinct"
    add(
        _Draft(
            "minority_pattern",
            "distinct_values",
            sum(candidate.coverage.distinct for candidate in minority),
            accuracy="exact" if exact else "sample",
            of=entry.population.distinct,
            patterns=[candidate.id for candidate in minority],
            limited_by=limits,
            **where,
        )
    )
