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
    "text/text_very_short": "Very short",
    "text/text_short": "Short",
    "text/text_medium": "Medium",
    "text/text_long": "Long",
    "text/text_very_long": "Very long",
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
