# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Catalogue of the classification's families and types, and of the report's findings.

A typed Python module, not a user format (ADR catalogue in Python). A change of a
family or type increases ``CATALOGUE_VERSION``; findings are render-time views and do not.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CATALOGUE_VERSION = 4
# Names of the versions ``classification_versions()`` returns, in order:
# ``names`` is ``names.NAME_RULES_VERSION``, the registry of the name rules.
VERSION_NAMES = ("catalogue", "names")


@dataclass(frozen=True, slots=True)
class Family:
    """A family of types with its stable code."""

    code: str
    types: tuple[str, ...]


FAMILIES = (
    Family("identifier", ("id", "unique_id")),
    Family("categorical", ("enum", "boolean", "constant")),
    Family("numeric", ("integer", "number", "currency", "percentage", "quantity")),
    Family("temporal", ("date", "datetime", "time")),
    Family("contact", ("email", "phone")),
    Family("geographic", ("postal_code",)),
    Family("web_network", ("url", "ip_address", "uuid")),
    # ``text`` alone is the Text of a column whose median length is not known.
    Family(
        "text",
        (
            "text_very_short",
            "text_short",
            "text_medium",
            "text_long",
            "text_very_long",
            "text",
        ),
    ),
    Family("other", ("mixed", "empty", "unknown")),
)

# The codes of the secondary properties (contract 3.4). A lot adds the traits it
# emits; none is emitted before the rule that decides it exists.
TRAITS = (
    "single_pattern",
    "multiple_patterns",
    "constant",
    "high_cardinality",
    "observed_unique",
    "first_column",
    "fixed_length",
)

_PAIRS = frozenset((family.code, code) for family in FAMILIES for code in family.types)


# Findings (contract 6.2). The catalogue is not part of any document: findings are
# views computed when a page is rendered (ADR findings computed at render), so a
# change here does not change ``CATALOGUE_VERSION``, which identifies the rules that
# write a classification into a Scan.
FindingClass = Literal["error", "issue", "information"]
FindingStatus = Literal["active", "recommended"]
FindingUnit = Literal[
    "occurrences",
    "distinct_values",
    "categories",
    "patterns",
    "groups",
    "positions",
    "records",
    "formats",
]
# What a count is out of: the denominator of its share (contract 6.3).
PopulationKind = Literal[
    "positions",
    "present_values",
    "content_strings",
    "occurrences",
    "distinct_values",
    "groups",
    "records",
    "eligible_values",
]


@dataclass(frozen=True, slots=True)
class FindingCode:
    """One finding the report can state about a column.

    ``status`` is ``active`` once the rule has an algorithm, a threshold if it
    needs one, and a source in the Scan; a ``recommended`` entry is documented
    but produces nothing in a real report (CA-29). ``downgrades_to_issue`` marks
    an Error that is an Issue on a classification that is not ``established``
    (RF-13). ``unit`` is the usual unit of the count; a finding may carry
    another one when the source measures another (``groups`` for a repetition).
    """

    code: str
    cls: FindingClass
    status: FindingStatus
    unit: FindingUnit
    population: PopulationKind
    algorithm: str
    prerequisites: tuple[str, ...] = ()
    downgrades_to_issue: bool = False


_ESTABLISHED = "classification:established"

FINDINGS = (
    # Errors: a deterministic rule proves an invalidity and the meaning is established.
    FindingCode(
        "temporal.invalid_calendar",
        "error",
        "active",
        "occurrences",
        "eligible_values",
        "detectors[date].coverage.invalid, every reason of the detector",
        (_ESTABLISHED, "family:temporal"),
        downgrades_to_issue=True,
    ),
    FindingCode(
        "semantic.invalid",
        "error",
        "active",
        "occurrences",
        "eligible_values",
        "detectors[].coverage.invalid of an email, phone, postal_code, url,"
        " ip_address or uuid detector",
        (_ESTABLISHED, "detector:semantic"),
        downgrades_to_issue=True,
    ),
    FindingCode(
        "type.outside_family",
        "error",
        "active",
        "occurrences",
        "present_values",
        "technical_type.outside_count of an Integer or a Number",
        (_ESTABLISHED, "type:integer_or_number"),
        downgrades_to_issue=True,
    ),
    # Issues: an ambiguity, a variant or a deviation to inspect.
    FindingCode(
        "temporal.ambiguous_date",
        "issue",
        "active",
        "occurrences",
        "occurrences",
        "observation ambiguous_dates",
    ),
    FindingCode(
        "number.ambiguous",
        "issue",
        "active",
        "occurrences",
        "eligible_values",
        "detectors[number].coverage.ambiguous",
    ),
    FindingCode(
        "categorical.case_variants",
        "issue",
        "active",
        "groups",
        "groups",
        "observation variant_groups",
    ),
    FindingCode(
        "pattern.minority",
        "issue",
        "active",
        "distinct_values",
        "distinct_values",
        "observation minority_pattern",
    ),
    FindingCode(
        "length.minority",
        "issue",
        "active",
        "occurrences",
        "content_strings",
        "observation minority_length",
    ),
    FindingCode(
        "type.mixed",
        "issue",
        "active",
        "occurrences",
        "present_values",
        "observation mixed_types",
    ),
    FindingCode(
        "identifier.repetition",
        "issue",
        "active",
        "occurrences",
        "present_values",
        "N - D of an identifier whose distinct count is exact",
        ("family:identifier", "cardinality:exact"),
    ),
    FindingCode(
        "text.surrounding_whitespace",
        "issue",
        "active",
        "occurrences",
        "content_strings",
        "observation trimmed_cells",
    ),
    FindingCode(
        "text.repeated_whitespace",
        "issue",
        "active",
        "occurrences",
        "content_strings",
        "observation collapsed_whitespace",
    ),
    # Information: facts for the Overview, never a badge.
    FindingCode(
        "presence.empty_column",
        "information",
        "active",
        "positions",
        "positions",
        "observation empty_column",
    ),
    FindingCode(
        "values.constant_column",
        "information",
        "active",
        "positions",
        "positions",
        "observation constant_column",
    ),
    # Recommended: no algorithm or no threshold yet (backlog L1b, L1c and L2).
    FindingCode(
        "categorical.rare",
        "issue",
        "recommended",
        "categories",
        "distinct_values",
        "cumulated tail and break in the frequencies (backlog L1b, to measure)",
    ),
    FindingCode(
        "pattern.rare",
        "issue",
        "recommended",
        "patterns",
        "distinct_values",
        "rare patterns by frequency (backlog L1b, to measure)",
    ),
    FindingCode(
        "format.rare",
        "issue",
        "recommended",
        "formats",
        "occurrences",
        "rare formats of a typed value (backlog L1b, to measure)",
    ),
    FindingCode(
        "text.confusable_letters",
        "issue",
        "recommended",
        "occurrences",
        "content_strings",
        "letters that look alike (backlog L1c)",
    ),
    FindingCode(
        "text.formula_risk",
        "issue",
        "recommended",
        "occurrences",
        "content_strings",
        "values a spreadsheet would read as a formula (backlog L1c)",
    ),
    FindingCode(
        "text.lost_leading_zeros",
        "issue",
        "recommended",
        "occurrences",
        "present_values",
        "codes that lost their leading zeros (backlog L1c)",
    ),
    FindingCode(
        "temporal.two_digit_year",
        "issue",
        "recommended",
        "occurrences",
        "eligible_values",
        "dates with a year on two digits (backlog L1c)",
    ),
    FindingCode(
        "temporal.excel_serial",
        "issue",
        "recommended",
        "occurrences",
        "present_values",
        "spreadsheet serial numbers read as numbers (backlog L1c)",
    ),
    FindingCode(
        "temporal.rounded_midnight",
        "issue",
        "recommended",
        "occurrences",
        "eligible_values",
        "times rounded to midnight (backlog L1c)",
    ),
    FindingCode(
        "text.atypical_length",
        "issue",
        "recommended",
        "occurrences",
        "content_strings",
        "lengths far from the others (backlog L1c)",
    ),
    FindingCode(
        "constraint.required_missing",
        "error",
        "recommended",
        "positions",
        "positions",
        "declared obligation of presence (backlog L2, needs a configuration format)",
    ),
    FindingCode(
        "constraint.pattern_violated",
        "error",
        "recommended",
        "occurrences",
        "present_values",
        "declared pattern (backlog L2, needs a configuration format)",
    ),
    FindingCode(
        "constraint.domain_violated",
        "error",
        "recommended",
        "occurrences",
        "present_values",
        "declared closed domain (backlog L2, needs a configuration format)",
    ),
)

FINDING_CODES = {entry.code: entry for entry in FINDINGS}


def is_catalogued(family: str, type_: str) -> bool:
    """Whether the pair is an active entry of the catalogue."""
    return (family, type_) in _PAIRS
