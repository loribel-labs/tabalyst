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
from tabalyst.summary_models import Finding, FindingRef

# How a number is qualified. The five kinds of HTML-03: an exact result, an
# estimate, a result over a sample, a limited result (a proven lower bound) and
# a measure that was not computed. A rule that is only a candidate is a status.
EXACT = "exact"
ESTIMATED = "estimated"
SAMPLE = "sample"
AT_LEAST = "at_least"
NOT_COMPUTED = "not_computed"
# A count of the distinct values told apart by a 128-bit fingerprint.
FINGERPRINT = "fingerprint"

ACCURACY_WORDS = {
    EXACT: "exact",
    ESTIMATED: "estimated",
    SAMPLE: "sample",
    AT_LEAST: "at least",
    NOT_COMPUTED: "not computed",
    FINGERPRINT: "fingerprint",
}
ACCURACY_TITLES = {
    EXACT: "Counted on every value of the file",
    ESTIMATED: "Estimated from a sample of the values, with a known error",
    SAMPLE: "Counted on a sample of the distinct values, not on the whole file",
    AT_LEAST: "A scan limit stopped the count: the real figure is at least this",
    NOT_COMPUTED: "Not computed by this scan",
    FINGERPRINT: "Counted on every value of the file; two different values are taken for one only if their 128-bit fingerprints collide, which is as unlikely as 2^-128 for a pair",
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
    "max_values": "scan.pattern_inference.max_values",
    "max_families": "scan.pattern_inference.max_families",
    "max_patterns_per_family": "scan.pattern_inference.max_patterns_per_family",
    "max_fields": "scan.limits.max_fields",
    "max_depth": "scan.limits.max_depth",
    "max_length_strata": "scan.limits.max_length_strata",
    "inference_error": "scan.pattern_inference.enabled",
}
# The settings of a reason whose name another measure shares: `max_depth` limits the
# structure of the JSON at `structure.depth_truncated_observations` and the tree of
# the patterns at `derived.patterns`.
MEASURE_REASON_SETTINGS = {
    ("derived.patterns", "max_depth"): "scan.pattern_inference.max_depth",
}
# Reasons that are not a setting to raise.
REASON_NOTES = {
    "exposure": "Values withheld by the exposure setting of a sensitive column",
}

# Why the inference of patterns gave a field none (``FieldPatterns.reason``, the
# deciding reason of its eligibility).
PATTERN_REASONS = {
    "exposure": "The values of this column are masked or hidden",
    "booleans_only": "The values are booleans",
    "structures_only": "The values are objects or arrays",
    "samples_withheld": "The sample of values was withheld",
    "long_texts_only": "The values are long texts, kept as a preview only",
    "no_values": "The column has no usable value",
    "too_few_distinct": "Too few distinct values to infer a pattern",
    "many_fixed_lengths": "The values take too many forms of fixed length for patterns",
    "small_integers": "Small whole numbers read as counts or measures, not codes",
    "decimal_numbers": "Decimal numbers are described by their statistics, not patterns",
    "no_structural_marks": "Plain words without digits or separators",
    "few_distinct": "Too few distinct values for patterns to say more than the values",
    "semantic_detector": "A detector already says what the values are",
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
    "residual_values": "Values left out by patterns and detectors",
    "duplicates_report": "Repeated values",
    "pearson_correlation": "Correlation between two columns",
    "category_crosstab": "Category against a feature of a column",
    "category_stats": "Numbers of a column by category",
    "numeric_shape": "Shape of the numbers",
    "datetime_parts": "Parts of the dates",
    "position_drift": "A column along the file",
    "missing_matrix": "Columns missing together",
    "date_order": "Order of two dates",
    "array_profile": "Lengths of the arrays",
    "structure_variants": "Sets of keys of the objects",
    "text_profile": "Words, lines and digits of the texts",
    "character_profile": "Characters of the values",
    "fingerprint_distinct": "Distinct long texts by fingerprint",
    "sensitive_forms": "Masks and classes of a sensitive column",
    "duplicate_rows_count": "Extra copies of whole rows",
}
# The names of the days of the week, by the value of a part.
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# The features of a column that a table reads (design 20.13), as a noun phrase.
FEATURE_WORDS = {
    "pattern": "pattern",
    "length": "length",
    "prefix": "prefix",
    "value": "value",
}
# The word for a bias-corrected Cramér's V below each limit; above the last, "strong".
STRENGTH_LIMITS = ((0.10, "negligible"), (0.30, "weak"), (0.50, "moderate"))
# Why an association has no score (``TableAssociation.reason``), in words.
TABLE_REASONS = {
    "too_few_rows": "too few rows are classified in both columns",
    "single_category": "only one category has rows",
    "single_class": "only one class has rows",
}
# Why the skewness of the numbers is undefined (``ShapeMoments.reason``), in words.
SHAPE_REASONS = {
    "no_variance": "all the numbers are equal",
    "too_few_values": "fewer than 3 numbers",
    "not_representable": "a number is beyond float64",
}
# Why the categories explain no share of a number (``StatsAssociation.reason``), in words.
STATS_REASONS = {
    "too_few_rows": "too few rows have a category and a number",
    "single_category": "only one category has rows",
    "no_variance": "the number does not vary",
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


# The general categories of Unicode, as the character map names them.
CHARACTER_CATEGORIES = {
    "Lu": "Uppercase letters",
    "Ll": "Lowercase letters",
    "Lt": "Titlecase letters",
    "Lm": "Modifier letters",
    "Lo": "Other letters",
    "Mn": "Nonspacing marks",
    "Mc": "Spacing marks",
    "Me": "Enclosing marks",
    "Nd": "Decimal digits",
    "Nl": "Letter numbers",
    "No": "Other numbers",
    "Pc": "Connector punctuation",
    "Pd": "Dashes",
    "Ps": "Opening brackets",
    "Pe": "Closing brackets",
    "Pi": "Opening quotes",
    "Pf": "Closing quotes",
    "Po": "Other punctuation",
    "Sm": "Math symbols",
    "Sc": "Currency symbols",
    "Sk": "Modifier symbols",
    "So": "Other symbols",
    "Zs": "Spaces",
    "Zl": "Line separators",
    "Zp": "Paragraph separators",
    "Cc": "Control characters",
    "Cf": "Format characters",
    "Cs": "Surrogates",
    "Co": "Private use",
    "Cn": "Unassigned",
}
# Why a column has no character map.
CHARACTER_REASONS = {
    "disabled": "Its values are masked or hidden, so their characters are not listed.",
    "samples_withheld": "The scan withheld some of its values, so it cannot map their characters.",
    "no_values": "The column has no text value.",
    "failed": "The scan could not map its characters.",
}


# The words of the classification (contract docs/dev/report/summary-table.md 3.3):
# the Scan carries the codes, the Report the words.
FAMILY_LABELS = {
    "identifier": "Identifier",
    "categorical": "Categorical",
    "numeric": "Numeric",
    "temporal": "Temporal",
    "contact": "Contact",
    "geographic": "Geographic",
    "web_network": "Web / Network",
    "text": "Text",
    "other": "Other",
}
# By ``family/type``. The five lengths of a Text read as their own words under
# the family Text; ``text/text`` is a Text whose length is not determined.
TYPE_LABELS = {
    "identifier/id": "ID",
    "identifier/unique_id": "Unique ID",
    "categorical/enum": "Enum",
    "categorical/boolean": "Boolean",
    "categorical/constant": "Constant",
    "numeric/integer": "Integer",
    "numeric/number": "Number",
    "numeric/currency": "Currency",
    "numeric/percentage": "Percentage",
    "numeric/quantity": "Quantity",
    "temporal/date": "Date",
    "temporal/datetime": "Datetime",
    "temporal/time": "Time",
    "contact/email": "Email",
    "contact/phone": "Phone",
    "geographic/postal_code": "Postal code",
    "web_network/url": "URL",
    "web_network/ip_address": "IP address",
    "web_network/uuid": "UUID",
    "text/text_very_short": "Very short string",
    "text/text_short": "Short string",
    "text/text_medium": "Medium string",
    "text/text_long": "Long string",
    "text/text_very_long": "Very long string",
    "text/text": "Text",
    "other/mixed": "Mixed",
    "other/empty": "Empty",
    "other/unknown": "Unknown",
}
# The states of a classification, as a reader reads them.
STATE_LABELS = {
    "established": "Established",
    "candidate": "Candidate",
    "undetermined": "Undetermined",
}


def type_label(family: str, type_: str) -> str:
    """The name of a type alone: ``Unique ID``, ``Short``, ``Mixed``."""
    return TYPE_LABELS[f"{family}/{type_}"]


def family_type_label(family: str, type_: str) -> str:
    """The name of a type with its family where the type alone is not enough:
    ``Unique ID``, ``Text / Short``, ``Other / Mixed``."""
    name = type_label(family, type_)
    if family in ("text", "other") and name != FAMILY_LABELS[family]:
        return f"{FAMILY_LABELS[family]} / {name}"
    return name


# The words of the findings (contract summary-table.md 6): the Scan and the catalogue
# carry codes, the Report the words. The five states of an evaluation are the
# wording of decision 6; ``detected`` has no label of its own, the count with the
# finding's name says it. The dash is not used in Errors and Issues.
ASSESSMENT_LABELS = {
    "none_detected": "None detected",
    "not_assessed": "Not assessed",
    "partial": "Partially assessed",
    "not_applicable": "Not applicable",
    "failed": "Assessment failed",
}
ASSESSMENT_TITLES = {
    "none_detected": "The check ran on every eligible value and found nothing",
    "not_assessed": "The check was turned off or has not run",
    "partial": "The check covered only part of the eligible values",
    "not_applicable": "The check has no meaning for this column",
    "failed": "The check raised a diagnostic, so nothing is known",
}

# What a finding counts, singular and plural.
UNIT_NOUNS = {
    "occurrences": ("occurrence", "occurrences"),
    "distinct_values": ("distinct value", "distinct values"),
    "categories": ("category", "categories"),
    "patterns": ("pattern", "patterns"),
    "groups": ("group", "groups"),
    "positions": ("position", "positions"),
    "records": ("record", "records"),
    "formats": ("format", "formats"),
}
# What each denominator is, to read a share ("of 100 positions").
POPULATION_PHRASES = {
    "positions": ("position", "positions"),
    "present_values": ("present value", "present values"),
    "content_strings": ("text value", "text values"),
    "occurrences": ("occurrence", "occurrences"),
    "distinct_values": ("distinct value", "distinct values"),
    "groups": ("group", "groups"),
    "records": ("record", "records"),
    "eligible_values": ("eligible value", "eligible values"),
}
# The name of a finding by the unit its count is in: the label follows the metric
# the Scan really has (``N - D`` repetitions are not duplicated groups, CA-15).
FINDING_NOUNS: dict[str, dict[str, tuple[str, str]]] = {
    "temporal.invalid_calendar": {
        "occurrences": ("invalid date", "invalid dates"),
    },
    "semantic.invalid": {"occurrences": ("invalid value", "invalid values")},
    "type.outside_family": {
        "occurrences": (
            "value outside the type of the column",
            "values outside the type of the column",
        ),
    },
    "temporal.ambiguous_date": {
        "occurrences": ("ambiguous date", "ambiguous dates"),
    },
    "number.ambiguous": {"occurrences": ("ambiguous number", "ambiguous numbers")},
    "categorical.case_variants": {
        "groups": ("spelling-variant group", "spelling-variant groups"),
    },
    "pattern.minority": {
        "distinct_values": (
            "distinct value in a minority pattern",
            "distinct values in minority patterns",
        ),
        "patterns": ("minority pattern", "minority patterns"),
    },
    "length.minority": {
        "occurrences": ("value of a minority length", "values of a minority length"),
    },
    "type.mixed": {
        "occurrences": (
            "value outside the closest type",
            "values outside the closest type",
        ),
    },
    "identifier.repetition": {
        "occurrences": (
            "repetition beyond the first",
            "repetitions beyond the first",
        ),
        "groups": ("repeated identifier", "repeated identifiers"),
    },
    "text.surrounding_whitespace": {
        "occurrences": (
            "value with surrounding whitespace",
            "values with surrounding whitespace",
        ),
    },
    "text.repeated_whitespace": {
        "occurrences": (
            "value with repeated whitespace",
            "values with repeated whitespace",
        ),
    },
    "presence.empty_column": {"positions": ("empty position", "empty positions")},
    "values.constant_column": {
        "positions": ("position with the one value", "positions with the one value"),
    },
}


def plural(count: int, one: str, many: str) -> str:
    """``count`` with the noun that agrees with its real quantity: ``1 group``,
    ``0 groups``, ``1,200 groups``. Integers are never rounded."""
    return f"{count:,} {one if count == 1 else many}"


def finding_label(code: str, count: int, unit: str) -> str:
    """A count with the name of its finding: ``3 spelling-variant groups``. A code or
    a unit without a name of its own is worded by its unit alone, never hidden."""
    one, many = FINDING_NOUNS.get(code, {}).get(unit) or UNIT_NOUNS[unit]
    return plural(count, one, many)


def population_phrase(kind: str, size: int) -> str:
    """What a share is out of: ``100 positions``."""
    one, many = POPULATION_PHRASES[kind]
    return plural(size, one, many)


# Overview (contract 7.1): the nouns of a profile. Facts only: a detector type is
# "shaped" like its kind, never said to be one.
OVERVIEW_NUMERIC = {
    "integer": "Whole numbers",
    "number": "Numbers",
    "currency": "Amounts with a currency marker",
    "percentage": "Percentages",
    "quantity": "Quantities with a unit",
}
OVERVIEW_TEMPORAL = {
    "date": "Dates",
    "datetime": "Date-times",
    "time": "Times",
}
OVERVIEW_KINDS = {
    "date": "Dates",
    "datetime_naive": "Date-times without a time zone",
    "datetime_aware": "Date-times with a time zone",
    "time": "Times",
}
OVERVIEW_SHAPED = {
    "email": "Email-shaped values",
    "phone": "Phone-shaped values",
    "postal_code": "Postal-code-shaped values",
    "url": "URL-shaped values",
    "ip_address": "IP-address-shaped values",
    "uuid": "UUID-shaped values",
}
OVERVIEW_TEXT = {
    "text_very_short": "Very short text",
    "text_short": "Short text",
    "text_medium": "Medium-length text",
    "text_long": "Long text",
    "text_very_long": "Very long text",
}
# The kinds of value that a mixed column holds, as one word each.
OVERVIEW_COMPOSITION = {
    "integer": "numeric",
    "number": "numeric",
    "boolean": "boolean",
    "date": "date",
    "text": "text",
}


def format_number(number: float) -> str:
    """Keep ordinary values readable and compact only genuinely large magnitudes.
    An integer is always written with all its digits (F06); only a float, which
    already is an approximation, is shortened."""
    if isinstance(number, int):
        return f"{number:,}"
    if abs(number) > 10**10:
        return f"{number:.4e}"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


# Details (contract 7.2): the names of the complementary measures and the notes on
# the examples. A measure that lists a format, a key or a representation is named
# by that text.
DETAILS_MEASURES = {
    "mean": "Mean",
    "minimum_length": "Shortest value, in characters",
    "maximum_length": "Longest value, in characters",
    "mean_length": "Mean length, in characters",
    "fixed_length": "Fixed length, in characters",
    "matched_percent": "Share recognized by the detector",
    "resolved_order": "Day and month order",
}
DETAILS_NOTES = {
    "hidden": "The values are withheld by the exposure setting of the column.",
    "masked": (
        "The values are masked by the exposure setting of the column; equal masks "
        "are merged and are not distinct original values."
    ),
    "none": "No value is listed.",
    "sample": "A sample of the values; the list is not exhaustive.",
}


# The Columns table (contract summary-table.md 7.3). ``detected`` has no label in the
# cells (the findings are written out); the filter of a list needs a word for it.
LIST_STATE_LABELS = {"detected": "Detected", **ASSESSMENT_LABELS}
LIST_STATE_TITLES = {
    "detected": "The checks found something",
    **ASSESSMENT_TITLES,
}
# The checks of a list that found something but did not look everywhere: "2 checks
# partially assessed". Keyed by the evaluation state of the check.
CAVEAT_STATES = {
    "partial": "partially assessed",
    "not_assessed": "not assessed",
    "failed": "failed",
}
# The details of the Findings table (contract summary-table.md 22): titles, orders and
# notes by code. The formats listed come from the data; the words are these.
DATES_TITLE = "Ambiguous dates"
DATES_CANDIDATES = "Formats that fit the same values"
DATES_READINGS = "Other values, by day-month order"
DATES_FORMATS = "Formats read without doubt"
DATES_ORDERS = {"DMY": "Day first (DD/MM)", "MDY": "Month first (MM/DD)"}
DATES_UNRESOLVED = "No order was chosen: these values stay ambiguous."
DATES_JOINER = " or "
PATTERNS_TITLE = "Minority patterns"
PATTERNS_DOMINANT = "Dominant pattern"
PATTERNS_MINORITY = "Patterns that few distinct values share"
PATTERNS_SAMPLE_POPULATION = "The patterns were inferred on a sample of the distinct values."
PATTERNS_SAMPLE_EXAMPLES = "Examples are values of a sample, not every value of a pattern."
PATTERNS_NO_EXAMPLES = "The scan kept no example of these patterns."
LENGTHS_TITLE = "Minority lengths"
LENGTHS_DOMINANT = "Dominant length"
LENGTHS_MINORITY = "Lengths that few texts have"
LENGTHS_UNIT = ("character", "characters")
LENGTHS_ANALYTICAL = "Lengths count the characters of the text after normalization."
LENGTHS_NO_EXAMPLES = "The scan kept no text of these lengths."
# The cases the scan keeps for a rule (scan design 18.15): all of their distinct texts, or a
# bounded selection of them.
CASES_COMPLETE = "The scan kept every distinct text of these cases."
CASES_SAMPLE = "Examples are texts of these cases chosen by the scan; there may be others."
EXAMPLES_MASKED = "Masked values: equal masks are merged."
EXAMPLES_HIDDEN = "Values hidden by the exposure setting of the column."
# Whitespace is made visible in an example (contract summary-table.md 22.6): the stored value
# is the raw one, these marks are written when the page is rendered.
WHITESPACE_MARKS = {" ": "\u00b7", "\t": "\u2192", "\n": "\u21b5", "\r": "\u21b5"}
WHITESPACE_OTHER_MARK = "\u2423"
WHITESPACE_TITLES = {
    "trimmed_cells": "Surrounding whitespace",
    "collapsed_whitespace": "Repeated whitespace",
}
WHITESPACE_KIND_TITLES = {
    "leading": "Whitespace before the text",
    "trailing": "Whitespace after the text",
    "repeated": "Whitespace repeated inside the text",
}
WHITESPACE_NOTE = "Marks show the whitespace: \u00b7 a space, \u2192 a tab, \u21b5 a line break."
WHITESPACE_NO_EXAMPLES = "The scan kept no text of these cases."
WHITESPACE_CELLS = ("cell", "cells")
TYPES_TITLE = "Mixed types"
TYPES_COMPOSITION = "Values by technical type"
TYPES_CLOSEST = "Closest type"
TYPES_WORDS = {
    "integer": "Integers",
    "number": "Numbers",
    "date": "Dates",
    "boolean": "Booleans",
    "text": "Text",
}
TYPES_NOTE = "Each value is read as the types it can be; a value of another type may be legitimate."
TYPES_OUTSIDE = ("value is outside the closest type", "values are outside the closest type")
TABLE_MORE = "more"
TABLE_AT_LEAST = "at least"
# By the state of the Details of a column (``shown`` writes no chip).
DETAILS_STATES = {"masked": "masked", "hidden": "hidden"}
DETAILS_TITLES = {"shown": "Values", "masked": "Masked values", "hidden": "Hidden values"}

# The preview of a finding (lot R9b, contract summary-table.md 18): what the finding is,
# in a sentence that states a fact and never a verdict, and what its reading does not
# say. A code without an entry has no sentence and prints none.
FINDING_NATURES = {
    "temporal.invalid_calendar": (
        "Values the date detector reads as a date and rejects: an impossible day or "
        "month, an impossible time or offset, mixed separators or a component of the "
        "wrong width."
    ),
    "semantic.invalid": (
        "Values that do not have the shape or the syntax of the type of the column."
    ),
    "type.outside_family": (
        "Values that are not numbers in a column whose type is a number: a word, a "
        "symbol or a currency code."
    ),
    "temporal.ambiguous_date": (
        "Dates that two configured day and month orders both read as valid."
    ),
    "number.ambiguous": (
        "Numbers whose separators allow more than one reading, such as 1,234."
    ),
    "categorical.case_variants": (
        "Groups of values that differ only by case, accents or spacing."
    ),
    "pattern.minority": "Distinct values written in a pattern that few values share.",
    "length.minority": (
        "Values whose length differs from the one that nearly all the values share."
    ),
    "type.mixed": "Values that do not have the closest technical type of the column.",
    "identifier.repetition": (
        "Occurrences of an identifier beyond the first one: the values present minus "
        "the distinct values."
    ),
    "text.surrounding_whitespace": "Values with whitespace before or after the text.",
    "text.repeated_whitespace": "Values with whitespace repeated inside the text.",
}
FINDING_LIMITS = {
    "temporal.invalid_calendar": (
        "The Scan counts the invalid values without splitting them by reason. A date "
        "that passes can still be wrong."
    ),
    "semantic.invalid": (
        "Checks the syntax of the type only. A value of valid syntax can still be "
        "wrong."
    ),
    "type.outside_family": (
        "Says which values are not numbers, not what they should have been."
    ),
    "temporal.ambiguous_date": (
        "An ambiguous date is not wrong. Tabalyst does not guess the order."
    ),
    "number.ambiguous": "An ambiguous number is not wrong. Tabalyst does not guess.",
    "categorical.case_variants": (
        "Variants are groups of spellings of one text; they do not prove that the "
        "spellings mean the same thing."
    ),
    "pattern.minority": "A rare pattern is a deviation to inspect, not a constraint.",
    "length.minority": "A minority length may be legitimate.",
    "type.mixed": "A value of another type may be legitimate.",
    "identifier.repetition": (
        "Counts repetitions beyond the first, not the duplicated occurrences nor the "
        "number of identifiers that repeat."
    ),
    "text.surrounding_whitespace": (
        "Whitespace is often invisible and says nothing about what the value means."
    ),
    "text.repeated_whitespace": (
        "Whitespace is often invisible and says nothing about what the value means."
    ),
}
PREVIEW_DOWNGRADED = (
    "Counted as an Issue, not as an Error: the type of the column is not established."
)
PREVIEW_ACCURACY = {
    "exact": ("Exact", "every value the Scan read was counted"),
    "lower_bound": ("At least", "a limit or a partial check stopped the count"),
    "sample": ("Sample", "counted on a sample of the values"),
    "estimated": ("Estimate", "the figure is an estimate"),
    "unavailable": ("Unavailable", "no figure can be told"),
}
PREVIEW_EXAMPLES_NOTES = {
    "masked": "Masked by the exposure setting of the column; equal masks are merged.",
    "hidden": "Withheld by the exposure setting of the column.",
}
PREVIEW_CHECKS_TITLE = "Checks that did not look everywhere"
# Why a check did not run or did not cover everything, in words
# (``Assessment.reason``). A reason the table does not know is shown spelled out.
ASSESSMENT_REASONS = {
    "no_check": "no check is registered for this finding",
    "disabled": "the check or the detector behind it is turned off",
    "detector_missing": "the detector was not run on this column",
    "not_temporal": "the column is not a date or a time",
    "not_semantic_type": "the column has no type whose syntax can be checked",
    "not_numeric_type": "the column is not a whole number or a number",
    "not_identifier": "the column is not an identifier",
    "cardinality_not_exact": "the count of distinct values is not exact",
    "observations_unavailable": "the scan has no observations",
    "observations_truncated": "the list of observations was cut",
    "observation_not_listed": "the observation is not in the list",
    "patterns_unavailable": "the patterns were not inferred",
    "patterns_sample": "the patterns were inferred on a sample",
    "too_few_values": "there are too few values",
    "no_dominant_length": "no length is shared by nearly all the values",
    "no_values": "the column has no value",
    "no_text": "the column has no text",
    "stage_disabled": "the analytic step behind it is turned off",
}


def finding_name(code: str, unit: str) -> str:
    """The plural name of a finding without a count (``invalid dates``), for a
    finding whose count is not defined."""
    return (FINDING_NOUNS.get(code, {}).get(unit) or UNIT_NOUNS[unit])[1]


def finding_noun(code: str, unit: str, count: int) -> str:
    """The name of a finding that agrees with ``count``, without the number
    (``ambiguous dates``), for a tile that prints the figure apart."""
    one, many = FINDING_NOUNS.get(code, {}).get(unit) or UNIT_NOUNS[unit]
    return one if count == 1 else many


def finding_text(item: Finding | FindingRef) -> str:
    """A finding in words with its count: ``3 spelling-variant groups``; a lower
    bound is never worded exact."""
    if item.count is None:
        text = finding_name(item.code, item.unit)
    else:
        text = finding_label(item.code, item.count, item.unit)
    return f"{TABLE_AT_LEAST} {text}" if item.accuracy == "lower_bound" else text


# The overview tiles (contract 7.5). A note is a fact about the reading of a signal; the
# target is the section that explains it better than Findings does.
SIGNAL_NOTES = {
    "temporal.invalid_calendar": "Dates that do not exist, such as 30 February or 25:00.",
    "semantic.invalid": "Values that break the shape or the syntax of the type of the column (email, phone, postal code...).",
    "type.outside_family": "Values that are not numbers in a column of numbers.",
    "temporal.ambiguous_date": (
        "Dates that fit two day-month orders, such as 03/04/2024. "
        "Tabalyst does not guess the order."
    ),
    "number.ambiguous": "Numbers whose separators allow more than one reading, such as 1,234.",
    "categorical.case_variants": "Groups of values that differ only by case, accents or spacing.",
    "pattern.minority": "Distinct values written in a pattern that few values share.",
    "length.minority": "Values whose length differs from the one nearly all values share.",
    "type.mixed": "Values outside the closest technical type of a mixed column.",
    "identifier.repetition": "Repetitions of an identifier beyond its first occurrence.",
    "text.surrounding_whitespace": "Values with whitespace before or after the text.",
    "text.repeated_whitespace": "Values with whitespace repeated inside the text.",
}
SIGNAL_TARGETS = {
    "temporal.ambiguous_date": "dates",
    "categorical.case_variants": "transformations",
    "text.surrounding_whitespace": "transformations",
    "text.repeated_whitespace": "transformations",
}

# The title and the line under the figure of a signal tile, by finding code.
SIGNAL_TITLES = {
    "temporal.invalid_calendar": ("Invalid dates", "Dates that do not exist in the calendar"),
    "semantic.invalid": ("Invalid values", "Values failing a validation check"),
    "type.outside_family": ("Type mismatches", "Values outside the inferred column type"),
    "temporal.ambiguous_date": ("Ambiguous dates", "Values matching multiple date orders"),
    "number.ambiguous": ("Ambiguous numbers", "Values that read in more than one way"),
    "categorical.case_variants": ("Spelling variants", "Groups of different spellings"),
    "pattern.minority": ("Minority patterns", "Distinct values in less-common patterns"),
    "length.minority": ("Minority lengths", "Values with less-common lengths"),
    "type.mixed": ("Mixed types", "Values outside the closest type"),
    "identifier.repetition": ("ID repetitions", "Repetitions beyond the first occurrence"),
    "text.surrounding_whitespace": (
        "Surrounding whitespace",
        "Values with leading or trailing whitespace",
    ),
    "text.repeated_whitespace": ("Repeated whitespace", "Values with repeated whitespace"),
}
# The class of a signal tile, written before its title so that the colour is never the only cue.
SIGNAL_CLASS_WORDS = {"error": "Error", "issue": "Issue", "information": "Info"}


def visible_whitespace(text: str) -> str:
    """``text`` with its whitespace characters written as visible marks."""
    return "".join(
        WHITESPACE_MARKS.get(char, WHITESPACE_OTHER_MARK if char.isspace() else char)
        for char in text
    )


def spoken_whitespace(kind: str, text: str) -> str:
    """What a screen reader says for an example of whitespace, in words."""
    if kind == "leading":
        return plural(len(text) - len(text.lstrip()), "leading whitespace character", "leading whitespace characters")
    if kind == "trailing":
        return plural(len(text) - len(text.rstrip()), "trailing whitespace character", "trailing whitespace characters")
    return "whitespace repeated inside the text"


# The column page (contract column-page.md). Words by code, like the rest of the file.
PAGE_DATE_ORDERS = {"YMD": "Year, month, day", "DMY": "Day, month, year", "MDY": "Month, day, year"}
PAGE_NO_EXAMPLE = "The Scan keeps no value for this finding."
# Title and lead of the Shape block, by the technical type of the column; the side bar uses the
# first word group of the key.
PAGE_SHAPE = {
    "number": (
        "Numbers",
        "Shape of the numbers",
        "The range and the shape of the values, from the Scan and from the second pass.",
    ),
    "date": (
        "Dates",
        "Dates",
        (
            "How the dates are written and spread over time. An ambiguous date is not wrong; "
            "Tabalyst does not guess its order."
        ),
    ),
    "text": (
        "Text",
        "Text",
        "Lengths and characters of the values, from the Scan and from the second pass.",
    ),
    "other": (
        "Distribution",
        "Distribution",
        "What the second pass found in the values of this column.",
    ),
}
# The technical types that share a Shape block.
PAGE_SHAPE_KIND = {"integer": "number", "number": "number", "date": "date", "text": "text"}


def values_lead(shown: int, stored: int, selection: str, distinct: int | None) -> str:
    """What the list of the Values block is: every distinct value, or the part of a sample
    the page lists. Every count is exact whatever the list."""
    if selection == "complete":
        return "Every distinct value of the column, most frequent first, each with its exact count."
    total = "a limited number of" if distinct is None else f"{distinct:,}"
    kind = selection.replace("_", " ")
    return (
        f"{shown:,} of the {stored:,} distinct values the Scan stored (a {kind} out of {total}). "
        "Each count is the exact frequency of that value in the column."
    )


# Identifier uniqueness (contract identifier-uniqueness.md 8): the JSON holds codes, these are
# the words. The five cases of the specification 11.2 are keyed ``identifier_uniqueness.*``.
UNIQUENESS_CASES = {
    "A": "identifier_uniqueness.raw_unique",
    "B": "identifier_uniqueness.unique_after_row_deduplication",
    "C": "identifier_uniqueness.repeated_between_distinct_records",
    "D": "identifier_uniqueness.not_assessed",
    "E": "identifier_uniqueness.missing_ids",
}
UNIQUENESS_TITLES = {
    "identifier_uniqueness.raw_unique": "Unique ID",
    "identifier_uniqueness.unique_after_row_deduplication": "Unique after row deduplication",
    "identifier_uniqueness.repeated_between_distinct_records": "ID repetitions",
    "identifier_uniqueness.not_assessed": "Uniqueness not fully assessed",
    "identifier_uniqueness.missing_ids": "Missing IDs",
}
UNIQUENESS_STATUS_WORDS = {
    "complete": "Complete",
    "limited": "Limited",
    "not_assessed": "Not assessed",
    "failed": "Contradictory",
}
UNIQUENESS_REASONS = {
    "missing_ids": "Some records have no ID, so the repetitions among distinct rows cannot be counted.",
    "too_few_records": "The dataset has fewer than two records.",
    "too_few_distinct_records": "Fewer than two distinct rows: a conclusion needs at least two.",
    "scope_partial": "The Scan did not cover every record, so the figures are not a conclusion.",
    "distinct_estimated": "The distinct IDs are only estimated or limited.",
    "distinct_not_exact": "The exact distinct count is of the original values, and a normalization changed some of them.",
    "distinct_unavailable": "The number of distinct IDs was not computed.",
    "duplicates_limited": "The duplicate rows were counted only up to a limit, and no complete Dedup report proves the rest.",
    "duplicates_disabled": "Duplicate row comparison is disabled, and no complete Dedup report proves the copies.",
    "inconsistent_measures": "The measures contradict each other; no figure is drawn from them.",
    "evidence_conflict": "Two exact sources disagree; no figure is drawn from them.",
    "computation_error": "The rule could not run on this column.",
}
UNIQUENESS_PROOF_SOURCES = {
    "scan.records.duplicates": "the Scan's comparison of whole records",
    "dedup.report": "a Dedup report",
    "deep.duplicate_rows_count": "the second pass, which counted the copies with the engine of Dedup",
}
UNIQUENESS_CARDINALITY_SOURCES = {
    "scan.values.cardinality": "the Scan",
    "deep.exact_distinct": "the second pass",
}
UNIQUENESS_ORIGINS = {"colocated": "found beside the source", "explicit": "given with --dedup-report"}
UNIQUENESS_REJECTIONS = {
    "dedup_unreadable": "not readable as a Dedup report of a supported format",
    "dedup_not_complete": "the Dedup run is not complete",
    "dedup_source_mismatch": "it describes another file (different SHA-256)",
    "dedup_not_csv": "the source is not a single CSV dataset",
    "dedup_dialect_mismatch": "its delimiter or encoding differs from the Scan's",
    "dedup_identity_unsupported": "its row identity is not supported",
    "dedup_total_mismatch": "its record total differs from the dataset's",
    "dedup_invariants_broken": "its own counts do not add up",
}
UNIQUENESS_IDENTITIES = {
    "full_decoded_csv_row_v1": "whole decoded CSV rows",
    "scan_record_v1": "whole records (path, native type and raw value)",
}
UNIQUENESS_ACCURACY = {
    "exact": "exact",
    "lower_bound": "at least",
    "disabled": "not computed",
    "estimated": "estimated",
    "limited": "limited",
}
