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
    "not_eligible": "a pattern would describe its values poorly, so the scan did not look for one",
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
    "unreadable_pattern": "the samples of the scan no longer give the patterns of this column",
    "no_lengths": "the scan has no length histogram for this column",
    "few_lengths": "the column has a single length",
    "no_values_listed": "the scan lists no value of this column",
    "few_prefixes": "the listed values share a single prefix",
    "unknown_feature": "no such feature",
    "not_a_category": "the column cannot be a category",
    "low_coverage": "fewer than half of the values carry a currency marker, a percent sign or a unit",
    "repeated_field": "a column inside the items of an array has several values in one record",
    "records_excluded": "the scan left records out, so the number of a record no longer gives its place in the file",
    "too_few_records": "the dataset has too few records to be cut in ten slices",
    "nothing_to_follow": "the field misses no value and has too many distinct values to follow by position",
    "too_many_columns": "too many columns miss a value for their pairs to be counted",
    "untracked_paths": "the scan stopped naming the paths of the dataset, so the keys of an object are not all known",
    "single_object": "the field holds a single object",
    "no_keys": "the scan names no key below the object",
    "uniform_keys": "every key is in every object, so there is one set of keys",
    "array_lengths_too_wide": "the lengths of the arrays are spread over too wide a range to be counted one by one",
    "hidden_exposure": "exposure hides the values of this field, so even their masks are kept out of the document",
    "duplicates_disabled": "the scan was set not to count the copies of rows (records.duplicates), and a second pass does not override that",
    "records_left_out": "the scan left records out of the file, which Dedup refuses to count",
    "stages_unchanged": "no analytical stage (NFC, trim, whitespace) changed a value, so the exact count of the original values is the analytical count",
    "nothing_left_out": "no pattern leaves values out and no detector that reads most of the column finds invalid or unmatched ones",
}

# Why an analysis needs no further reading.
SATISFIED = {
    "counts_complete": "every distinct value is already counted in the scan",
    "counts_in_samples": "the scan lists every distinct value with its exact count",
    "map_in_samples": "the scan lists every distinct value with its exact count, so its character map is already exact",
    "constant_value": "the field has a single value, already in the scan statistics",
    "lengths_complete": "the exact length histogram is already in the scan",
    "distinct_exact": "the distinct values are already counted exactly",
    "years_counted": "the scan already counts the values by year",
    "lengths_constant": "every array has the same length, already in the scan",
    "copies_exact": "the scan already counts the extra copies of rows exactly",
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
    "stats_budget": "enough numbers by category were already chosen automatically",
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
    "numeric_shape": "shows the asymmetry, the outliers and the decimals of the numbers",
    "ambiguous_dates_read_by_evidence": "the unambiguous dates of the column read in one order only, so the ambiguous ones are read that way and counted with the others",
    "ambiguous_numbers_read_by_evidence": "the unambiguous values of the column prove one number convention, so the values written ambiguously are read that way and counted with the others",
    "calendar_parts": "shows the years, months, weekdays and hours of the dates and what their ambiguity changes",
    "drift_by_position": "shows whether the missing values and the values of the column change along the file",
    "missing_together": "shows which columns lack a value in the same records",
    "array_lengths": "shows how long the arrays of the field are",
    "analytical_distinct": "counts the distinct values after NFC, trim and whitespace, which the scan stopped counting and the original values do not give",
    "duplicate_rows": "counts the extra copies of whole rows exactly, which the scan could only bound",
    "key_sets": "shows which keys the objects have together",
    "text_shape": "shows the words, lines and digits of the texts",
    "character_map": "shows the most frequent characters, their Unicode families, the case of the ends and the emoji of every value",
    "long_values_distinct": "counts the distinct values that are too long for an exact set, and the texts found more than once",
    "forms_without_values": "counts the masks and classes of the values without listing one",
    "exposure_counts": "counts the distinct values of a sensitive column, which exposure keeps out of the document, as two numbers",
    "values_with_unit": "the scan counts the values with a unit but has no number for them",
    "requested_only": "a combination of columns is only searched when it is asked for",
    "repeated_identifier": "the values are almost all different, so those found more than once are worth a mention",
    "values_left_out": "the scan counts values that patterns or detectors leave out but keeps only a few of them",
    "derivable_from_samples": "follows from the exact counts the scan already lists",
    "base_value": "a common analysis",
    "exploratory_correlation": "the sample suggests a linear relation between the two columns",
    "not_explored": "the sample could not score this pair",
    "exploratory_association": "the sample suggests that the category determines the feature",
    "exploratory_correlation_ratio": "the sample suggests that the category explains the number",
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
