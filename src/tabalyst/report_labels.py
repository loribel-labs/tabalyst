# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Words of the report: what each observation rule says, how a count is
qualified (exact, estimated, sample, limited) and the plain names of limits.

The Scan documents carry codes, never sentences. The report is the only place
that turns them into words, so a reader of the JSON alone gets the same labels
(design 18.14).
"""

from dataclasses import dataclass

from tabalyst.scanner.models import Observation
from tabalyst.scanner.patterninfer import MAX_VALUES

# How a number is qualified. The five kinds of HTML-03: an exact result, an
# estimate, a result over a sample, a limited result (a proven lower bound) and
# a measure that was not computed. A rule that is only a candidate is a status.
EXACT = "exact"
ESTIMATED = "estimated"
SAMPLE = "sample"
AT_LEAST = "at_least"
NOT_COMPUTED = "not_computed"

ACCURACY_WORDS = {
    EXACT: "exact",
    ESTIMATED: "estimated",
    SAMPLE: "sample",
    AT_LEAST: "at least",
    NOT_COMPUTED: "not computed",
}
ACCURACY_TITLES = {
    EXACT: "Counted on every value of the file",
    ESTIMATED: "Estimated from a sample of the values, with a known error",
    SAMPLE: "Counted on a sample of the distinct values, not on the whole file",
    AT_LEAST: "A scan limit stopped the count: the real figure is at least this",
    NOT_COMPUTED: "Not computed by this scan",
}
# Accuracy of an observation (``Observation.accuracy``) as a report kind.
OBSERVATION_ACCURACY = {"exact": EXACT, "lower_bound": AT_LEAST, "sample": SAMPLE}

STATUS_WORDS = {
    "confirmed_issue": "Confirmed issue",
    "candidate_anomaly": "Candidate anomaly",
    "informational": "Remark",
}
STATUS_TITLES = {
    "confirmed_issue": "A defect of the source by its structure",
    "candidate_anomaly": "Worth a look: a rule cannot confirm it is an error",
    "informational": "A finding that may be perfectly valid",
}
# CSS class of the status marker (shape and text carry it too, never the color
# alone).
STATUS_CLASSES = {
    "confirmed_issue": "warn",
    "candidate_anomaly": "cand",
    "informational": "info",
}

# What ``Observation.count`` counts, in the plural.
POPULATION_NOUNS = {
    "value_slots": "values",
    "content_strings": "text values",
    "occurrences": "values",
    "records": "records",
    "distinct_values": "distinct values",
    "groups": "groups",
    "columns": "columns",
}


@dataclass(frozen=True)
class RuleLabel:
    """How the report words one observation rule."""

    title: str
    # Section of the report where the finding is shown in detail.
    anchor: str
    # ``count`` adds the counts of the items; ``fields`` counts the fields.
    headline: str = "count"


RULES: dict[str, RuleLabel] = {
    "excluded_records": RuleLabel(
        "Records excluded by the tolerant error policy, not analyzed", "limits"
    ),
    "ambiguous_header": RuleLabel("Blank or repeated column names", "columns"),
    "duplicate_rows": RuleLabel(
        "Duplicate rows beyond their first occurrence", "overview"
    ),
    "mixed_types": RuleLabel("Values outside the closest type of a mixed column", "columns"),
    "type_outliers": RuleLabel("Values outside the type of their column", "columns"),
    "ambiguous_dates": RuleLabel(
        "Date values matching more than one day-month order", "dates"
    ),
    "variant_groups": RuleLabel(
        "Values written in several ways that normalization compares as equal",
        "transformations",
    ),
    "minority_pattern": RuleLabel(
        "Rare patterns among otherwise uniform values", "patterns"
    ),
    "minority_length": RuleLabel(
        "Rare lengths among otherwise uniform values", "patterns"
    ),
    "missing_values": RuleLabel("Missing values", "columns"),
    "empty_column": RuleLabel(
        "Columns without any present values", "columns", headline="fields"
    ),
    "constant_column": RuleLabel(
        "Columns with one distinct value", "columns", headline="fields"
    ),
    "trimmed_cells": RuleLabel(
        "Cells changed by trimming surrounding whitespace", "transformations"
    ),
    "collapsed_whitespace": RuleLabel(
        "Cells changed by collapsing repeated internal whitespace", "transformations"
    ),
}


def rule_label(rule: str) -> RuleLabel:
    """The label of a rule; a rule of a later version of the rules is shown by
    its name rather than hidden."""
    return RULES.get(rule) or RuleLabel(rule.replace("_", " ").capitalize(), "observations")


def observation_kind(observation: Observation) -> str:
    """The report's accuracy kind of one observation."""
    return OBSERVATION_ACCURACY[observation.accuracy]


# Plain names of the scan measures a limit can stop (design 8 and 11).
MEASURE_LABELS = {
    "structure.paths": "Paths",
    "records.duplicates.count": "Duplicate records",
    "records.sample": "Row sample",
    "values.cardinality": "Distinct values",
    "values.frequencies": "Value frequencies",
    "values.samples": "Sample of values",
    "values.samples.long_texts": "Sample of long texts",
    "values.samples.by_length": "Samples by length",
    "numeric.median": "Median",
    "normalization.variant_groups": "Variant groups",
    "normalization.stages.raw.cardinality": "Distinct raw values",
    "normalization.stages.nfc.cardinality": "Distinct after Unicode composition",
    "normalization.stages.trim.cardinality": "Distinct after trimming",
    "normalization.stages.collapse_whitespace.cardinality": (
        "Distinct after whitespace collapsing"
    ),
    "normalization.stages.casefold.cardinality": "Distinct after case folding",
    "normalization.stages.strip_accents.cardinality": "Distinct after accent removal",
    "derived.patterns": "Inferred patterns",
    "records.sample.fields": "Fields of the row sample",
    "structure.depth_truncated_observations": "Observations deeper than the limit",
}
# Settings behind each limit reason.
REASON_SETTINGS = {
    "distinct_limit": "scan.limits.max_distinct_per_field",
    "global_budget": "scan.limits.max_tracked_values",
    "value_too_long": "scan.limits.max_stored_value_length",
    "record_budget": "scan.limits.max_tracked_records",
    "field_limit": "scan.limits.max_fields",
    "memory_budget": "scan.limits.max_sample_memory",
    "max_patterns": "scan.pattern_inference.max_patterns",
    "max_fields": "scan.limits.max_fields",
    "max_depth": "scan.limits.max_depth",
    "max_length_strata": "scan.limits.max_length_strata",
    "inference_error": "scan.pattern_inference.enabled",
}
# Reasons that are not a setting to raise.
REASON_NOTES = {
    "exposure": "Values withheld by the exposure setting of a sensitive column",
    "max_values": f"The inference reads at most {MAX_VALUES:,} distinct values of a column",
}

# Why the inference of patterns gave a field none (``FieldPatterns.reason``).
PATTERN_REASONS = {
    "technical_type": "Only text and mixed columns have patterns",
    "exposure": "The values of this column are masked or hidden",
    "samples_withheld": "The sample of values was withheld",
    "long_texts_only": "The values are long texts, kept as a preview only",
    "no_values": "The column has no usable value",
    "too_few_distinct": "Too few distinct values to infer a pattern",
    "inference_error": "The inference failed for this column",
}

# Where a cell of the row sample comes from (``SampleRow.origins``).
ORIGIN_WORDS = {
    "start": "Start",
    "middle": "Sampled",
    "end": "End",
}

# The analyses of the second pass (design 20), in words.
ANALYSIS_LABELS = {
    "numeric_histogram": "Histogram and exact quantiles",
    "length_distribution": "Length distribution",
    "exact_frequencies": "Exact frequencies",
    "exact_distinct": "Exact distinct count",
    "pattern_validation": "Pattern validation",
    "temporal_distribution": "Distribution over time",
    "measure_extraction": "Numbers of the values with a unit",
    "pearson_correlation": "Correlation between two columns",
    "category_crosstab": "Category against a feature of a column",
}
# The features of a column that a table reads (design 20.13), as a noun phrase.
FEATURE_WORDS = {
    "pattern": "pattern",
    "length": "length",
    "prefix": "prefix",
}
# The word for a bias-corrected Cramér's V below each limit; above the last, "strong".
STRENGTH_LIMITS = ((0.10, "negligible"), (0.30, "weak"), (0.50, "moderate"))
# Why an association has no score (``TableAssociation.reason``), in words.
TABLE_REASONS = {
    "too_few_rows": "too few rows are classified in both columns",
    "single_category": "only one category has rows",
    "single_class": "only one class has rows",
}
# Why a correlation has no coefficient (``PearsonResult.reason``), in words.
PEARSON_REASONS = {
    "insufficient_pairs": "too few rows have a number in both columns",
    "zero_variance_first": "the first column does not vary over the common rows",
    "zero_variance_second": "the second column does not vary over the common rows",
}
# How a second pass ended for a Report (``analyses.outcome``), and who decided it.
OUTCOME_WORDS = {
    "ran": "The second pass computed analyses.",
    "reused": "The stored results of an earlier second pass were enough.",
    "nothing_selected": "The planner found nothing worth adding.",
    "disabled": "The second pass is turned off (deep.mode is off).",
    "unavailable": "Some analyses could not be computed because the source was not read.",
    "failed": "The second pass failed, so the report goes without it.",
}
MODE_WORDS = {
    "auto": "Automatic: the planner chose what is useful and cheap.",
    "forced": "Forced: every applicable analysis the budget holds.",
    "off": "Off.",
}
# Why an analysis of the second pass is not complete (``AnalysisResult.reason``).
DEEP_REASONS = {
    "source_not_read": "this report was built from a scan document, which reads no source",
    "source_unavailable": "the source of the scan document was not found beside it",
    "memory_budget": "the exact set did not fit in the memory the plan gave it",
    "scan_mismatch": "the second pass found other counts than the scan, so it kept no result",
    "analysis_error": "the analysis failed",
    "unrepresentable": "a value could not be represented",
    "not_available": "no executor in this version",
}
