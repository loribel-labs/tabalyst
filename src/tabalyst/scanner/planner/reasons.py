# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The codes the planner writes and their sentences (design 20.5).

The plan holds codes; the words live here and nowhere else, so a reader of the
JSON and the text of ``tabalyst scan --plan`` agree.
"""

from __future__ import annotations

# Why an analysis does not apply to a field.
NOT_APPLICABLE = {
    "no_values": "the field has no value to analyze",
    "sensitive_exposure": "exposure keeps the values of this field out of the document",
    "long_texts_only": "its values are long texts, which are sampled and not counted",
    "measure_unavailable": "the scan did not compute the measure it starts from",
    "unreliable_type": "the field mixes types, so a typed analysis would be unreliable",
    "high_cardinality": "too many distinct values for a table of frequencies",
    "not_compactable": "the values are too long to be held in an exact set",
    "patterns_unavailable": "the scan inferred no pattern for this field",
    "too_few_distinct": "too few distinct values to infer patterns",
    "no_candidates": "no pattern candidate was found",
    "mixed_temporal_kinds": "the dates mix kinds (date, datetime, time zones)",
    "time_only": "the values are times of day, without a date",
    "not_numeric": "a pair needs two numeric columns",
    "repeated_path": "the field repeats in a record, which a pair cannot align",
    "no_frequencies": "the scan does not hold the exact frequencies of the column",
    "single_value": "the column has a single value",
    "too_many_categories": "too many distinct values for a category",
    "identifier_like": "the column looks like an identifier, not a category",
    "near_unique": "almost every value is distinct, so no value repeats enough to be a category",
    "not_text": "the feature reads text and integer columns",
    "same_column": "a table needs two different columns",
    "no_pattern": "the scan inferred no pattern for this column",
    "no_lengths": "the scan has no length histogram for this column",
    "few_lengths": "the column has a single length",
    "no_values_listed": "the scan lists no value of this column",
    "few_prefixes": "the listed values share a single prefix",
    "unknown_feature": "no such feature",
    "not_a_category": "the column cannot be a category",
    "low_coverage": "fewer than half of the values carry a currency marker, a percent sign or a unit",
    "repeated_field": "a column inside the items of an array has several values in one record",
    "nothing_left_out": "no pattern leaves values out and no detector that reads most of the column finds invalid or unmatched ones",
}

# Why an analysis needs no further reading.
SATISFIED = {
    "counts_complete": "every distinct value is already counted in the scan",
    "counts_in_samples": "the scan lists every distinct value with its exact count",
    "constant_value": "the field has a single value, already in the scan statistics",
    "lengths_complete": "the exact length histogram is already in the scan",
    "distinct_exact": "the distinct values are already counted exactly",
    "years_counted": "the scan already counts the values by year",
}

# The decision on a candidate that is not satisfied.
SELECTION = {
    "requested": "asked for explicitly",
    "forced": "selected because the whole second pass was forced",
    "automatic": "useful and cheap enough to be chosen automatically",
    "not_applicable": "does not apply to this field",
    "not_requested": "automatic selection is off and it was not requested",
    "low_utility": "too little expected benefit for an automatic choice",
    "cpu_class": "its CPU class is above the automatic limit",
    "cells_budget": "the shared reading exceeds the automatic cell budget",
    "pairs_budget": "enough pairs were already chosen automatically",
    "tables_budget": "enough tables were already chosen automatically",
    "redundant_feature": "another feature of the same two columns says more",
    "budget": "its memory does not fit in the budget with the analyses already selected",
}

# Why a selection asks for a confirmation before it starts (R1).
CONFIRMATION = {
    "memory_over_automatic": "its memory is above what an automatic choice may take",
    "cells_over_automatic": "it reads more cells than an automatic choice may",
    "cpu_over_automatic": "its CPU class is above the automatic limit",
    "time_over_threshold": "its estimated time is above the threshold",
}

UTILITY = {
    "partial_counts": "the scan lists only the most frequent values",
    "numeric_distribution": "shows how the numbers are spread",
    "same_state_exact_median": "gives the exact median, mode and quantiles from one state",
    "identifier_like": "looks like an identifier, whose spread is not a quantity",
    "near_unique": "almost every value is distinct",
    "identifier_name": "the name looks like an identifier",
    "integer_key": "an integer key",
    "length_distribution": "the length histogram is missing",
    "candidates_unvalidated": "pattern shares come from a sample of the distinct values",
    "values_outside_candidates": "some values take no candidate pattern",
    "temporal_distribution": "shows how the dates are spread",
    "values_with_unit": "the scan counts the values with a unit but has no number for them",
    "requested_only": "a combination of columns is only searched when it is asked for",
    "repeated_identifier": "the values are almost all different, so those found more than once are worth a mention",
    "values_left_out": "the scan counts values that patterns or detectors leave out but keeps only a few of them",
    "derivable_from_samples": "follows from the exact counts the scan already lists",
    "base_value": "a common analysis",
    "exploratory_correlation": "the sample suggests a linear relation between the two columns",
    "not_explored": "the sample could not score this pair",
    "exploratory_association": "the sample suggests that the category determines the feature",
}

# The advice on stratified sampling (design 20.14). Kept apart: a code such as
# ``near_unique`` has another sentence for a key of strata than for a category.
STRATIFICATION = {
    "no_values": "the column has no value",
    "sensitive_exposure": "exposure keeps its values out of the document",
    "repeated_path": "the column repeats inside a record, so a row has no single stratum",
    "identifier": "it looks like an identifier: nearly every row would be a stratum of its own",
    "near_unique": "almost every value is distinct, so strata would hold one row each",
    "single_value": "a single value makes a single stratum",
    "too_many_strata": "too many distinct values for a stratification key",
    "cardinality_unknown": "the scan stopped counting its distinct values, so the strata are unknown",
    "estimated_strata": "the number of strata is an estimate, not a certain count",
    "no_exact_frequencies": "the scan holds no complete frequencies, so the balance is unknown",
    "rare_strata": "some strata are rare and can be absent from a small proportional sample",
    "capped_by_records": "the product of the columns exceeds the records, which cap it",
    "bound_exceeds_states": "the possible combinations exceed the states a sample may hold",
    "many_strata": "many strata: each gets few rows",
    "exact_from_sample": "the row sample holds every row, so its exact count replaces the saturated bound",
    "mean_quota_below_one": "on average a stratum gets less than one row",
    "too_few_rows": "the row sample has too few rows to show the combinations",
    "no_sample": "the scan holds no row sample",
    "sample_reduced": "the row sample was reduced, as in a Report",
    "sample_does_not_cover": "the row sample does not hold these columns whole",
    "reduce_fields": "stratify by fewer or less detailed columns",
    "set_explicit_limit": "set an explicit limit of strata (--max-strata) and accept the stop",
    "use_smart": "use smart sampling, which covers diversity without a table of strata",
}

REASONS = {**NOT_APPLICABLE, **SATISFIED, **SELECTION, **CONFIRMATION, **UTILITY}


def reason_text(code: str) -> str:
    """The sentence of a code, or the code itself when it is unknown."""
    return REASONS.get(code, code)
