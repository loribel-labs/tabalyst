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
    "automatic": "useful and cheap enough to be chosen automatically",
    "not_applicable": "does not apply to this field",
    "not_requested": "automatic selection is off and it was not requested",
    "low_utility": "too little expected benefit for an automatic choice",
    "cpu_class": "its CPU class is above the automatic limit",
    "cells_budget": "the shared reading exceeds the automatic cell budget",
    "budget": "its memory does not fit in the budget with the analyses already selected",
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
    "derivable_from_samples": "follows from the exact counts the scan already lists",
    "base_value": "a common analysis",
}

REASONS = {**NOT_APPLICABLE, **SATISFIED, **SELECTION, **UTILITY}


def reason_text(code: str) -> str:
    """The sentence of a code, or the code itself when it is unknown."""
    return REASONS.get(code, code)
