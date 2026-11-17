# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scenario metadata of Insurance V2 operations and the rules that keep a profile coherent.

The contract is ``docs/dev/generate/insurance-v2.md`` sections 3 and 4. An operation that
declares ``scenario_id`` belongs to a V2 profile; one that does not is legacy and keeps the
behavior of the earlier profiles byte for byte.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from typing import cast

from tabalyst.generate_rarity import RARITY_LEVELS, band_of

SCENARIO_ID = re.compile(r"[A-Z][A-Z0-9_]{0,15}\Z")
ROOT_CAUSE_ID = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
COLUMN_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
CATEGORIES = frozenset({
    "format_variant", "format_invalid", "semantic_invalid", "business_rule_violation",
    "contextual_invalid", "valid_atypical",
})
SEVERITIES = frozenset({"info", "minor", "major", "critical"})
DETECTION_FAMILIES = frozenset({
    "syntactic", "domain", "cross_column", "uniqueness", "contextual", "statistical", "none",
})
MISSING_MECHANISMS = frozenset({"mcar", "mar", "mnar"})
MISSING_REASONS = frozenset({
    "unreported", "client_refusal", "not_applicable", "system_omission", "unknown",
})
SCENARIO_KEYS = frozenset({
    "scenario_id", "rule_id", "category", "severity", "rarity_level", "root_cause_id",
    "requires", "conflicts_with", "can_overlap", "expected_detection", "description",
    "missing_mechanism", "missing_reason",
})
# What every operation of one scenario must say the same way: the truth file reads them per scenario.
SHARED_KEYS = ("category", "severity", "rarity_level", "rule_id", "root_cause_id",
               "expected_detection", "description", "missing_mechanism", "missing_reason")
# The free text of a scenario in manifest.json (report 15 "expected effect"), never interpreted.
MAX_DESCRIPTION = 500
# Output profiles that add columns to the 34 of the default one (contract section 7), so that a
# refusal can say which profile provides a column. Lot 4 owns the content of ``extended``.
PROVIDING_PROFILES: dict[str, str] = {
    **dict.fromkeys(
        ("date_sinistre", "montant_couverture", "franchise", "montant_indemnise",
         "date_resiliation", "statut_paiement", "canal_acquisition", "courtier_id",
         "produit_code", "nombre_reclamations"), "extended"),
    **dict.fromkeys(
        ("taux_remboursement", "consentement_communication", "gestionnaire_id",
         "segment_client", "date_observation", "version_source",
         "source_system"), "complete"),
}


def _shape(pattern: re.Pattern[str]) -> str:
    return pattern.pattern.removesuffix("\\Z")


def _text_error(operation: Mapping[str, object], key: str, pattern: re.Pattern[str]) -> str | None:
    value = operation[key]
    if not isinstance(value, str) or not pattern.fullmatch(value):
        return f"operation.{key} must match {_shape(pattern)}"
    return None


def _names_error(operation: Mapping[str, object], key: str,
                 pattern: re.Pattern[str]) -> str | None:
    value = operation[key]
    if (not isinstance(value, list) or len(value) > 64
            or any(not isinstance(item, str) or not pattern.fullmatch(item) for item in value)
            or len(set(value)) != len(value)):
        return f"operation.{key} must be a list of distinct names matching {_shape(pattern)}"
    return None


def _choice_error(operation: Mapping[str, object], key: str, allowed: Collection[str]) -> str | None:
    if operation[key] not in allowed:
        return f"operation.{key} must be one of {', '.join(sorted(allowed))}"
    return None


def _detection_error(operation: Mapping[str, object]) -> str | None:
    value = operation["expected_detection"]
    tokens = value.split("|") if isinstance(value, str) else []
    if (not tokens or any(token not in DETECTION_FAMILIES for token in tokens)
            or len(set(tokens)) != len(tokens) or ("none" in tokens and len(tokens) > 1)):
        return ("operation.expected_detection must join distinct families of "
                f"{', '.join(sorted(DETECTION_FAMILIES))} with |, and none stands alone")
    return None


def scenario_option_error(operation: Mapping[str, object]) -> str | None:
    """Return why the scenario keys of one operation are invalid, or None.

    Without ``scenario_id`` no scenario key is allowed (a legacy operation). With it, the
    operation also declares ``category`` and ``severity`` and uses ``count``, never ``rate``.
    """
    present = sorted(SCENARIO_KEYS & operation.keys())
    if not present:
        return None
    if "scenario_id" not in operation:
        return f"operation.{present[0]} needs operation.scenario_id (a legacy operation has no scenario keys)"
    problem = _text_error(operation, "scenario_id", SCENARIO_ID)
    if problem is not None:
        return problem
    if "rate" in operation:
        return "operation.rate is not allowed with scenario_id: a scenario uses count"
    for key in ("category", "severity"):
        if key not in operation:
            return f"operation.{key} is required with scenario_id"
    checks: list[str | None] = [
        _choice_error(operation, "category", CATEGORIES),
        _choice_error(operation, "severity", SEVERITIES),
    ]
    if "rarity_level" in operation:
        checks.append(_choice_error(operation, "rarity_level", RARITY_LEVELS))
    if "rule_id" in operation:
        checks.append(_text_error(operation, "rule_id", SCENARIO_ID))
    if "root_cause_id" in operation:
        checks.append(_text_error(operation, "root_cause_id", ROOT_CAUSE_ID))
    if "requires" in operation:
        checks.append(_names_error(operation, "requires", COLUMN_ID))
    if "conflicts_with" in operation:
        checks.append(_names_error(operation, "conflicts_with", SCENARIO_ID))
    if "can_overlap" in operation and type(operation["can_overlap"]) is not bool:
        checks.append("operation.can_overlap must be true or false")
    if "expected_detection" in operation:
        checks.append(_detection_error(operation))
    if "description" in operation:
        text = operation["description"]
        if (not isinstance(text, str) or not text.strip() or len(text) > MAX_DESCRIPTION
                or not text.isprintable()):
            checks.append(f"operation.description must be one line of 1 to {MAX_DESCRIPTION} "
                          "characters")
    if "missing_mechanism" in operation:
        checks.append(_choice_error(operation, "missing_mechanism", MISSING_MECHANISMS))
        if operation.get("kind") != "set_missing":
            checks.append("operation.missing_mechanism requires kind: set_missing")
        mech = operation["missing_mechanism"]
        when = operation.get("when")
        col = operation.get("column")
        if mech == "mcar" and when:
            checks.append("operation.missing_mechanism mcar must not declare when (independent missingness)")
        elif mech == "mar":
            if not when:
                checks.append("operation.missing_mechanism mar requires when condition on observed variable")
            elif isinstance(when, dict) and col in when:
                checks.append("operation.missing_mechanism mar must condition on a different column than the missing column")
        elif mech == "mnar":
            if not when:
                checks.append("operation.missing_mechanism mnar requires when condition on the missing column itself")
            elif isinstance(when, dict) and col not in when:
                checks.append("operation.missing_mechanism mnar must condition on the missing column itself")
    if "missing_reason" in operation:
        checks.append(_choice_error(operation, "missing_reason", MISSING_REASONS))
    problem = next((problem for problem in checks if problem is not None), None)
    if problem is None and operation["category"] == "valid_atypical":
        # Contract 3.1: a non-defect is harmless and no detector should be right to report it.
        if operation["severity"] != "info":
            return "operation.severity must be info for a valid_atypical scenario (not a defect)"
        if operation.get("expected_detection") != "none":
            return ("operation.expected_detection must be none for a valid_atypical scenario "
                    "(not a defect)")
    return problem


def foreign_scenario_key(operation: Mapping[str, object]) -> str | None:
    """Return a scenario key the operation carries, for a package that accepts none."""
    found = SCENARIO_KEYS & operation.keys()
    return min(found) if found else None


def is_scenario_operation(operation: Mapping[str, object]) -> bool:
    """Tell whether an operation declares a scenario."""
    return "scenario_id" in operation


def is_scenario_profile(operations: Sequence[Mapping[str, object]]) -> bool:
    """Tell whether a profile is a V2 profile: any operation declares ``scenario_id``."""
    return any(is_scenario_operation(operation) for operation in operations)


def conflict_map(operations: Sequence[Mapping[str, object]]) -> dict[str, set[str]]:
    """Return, per scenario id, the scenarios it never shares a row with (symmetric closure)."""
    conflicts: dict[str, set[str]] = {}
    for operation in operations:
        scenario = operation.get("scenario_id")
        if not isinstance(scenario, str):
            continue
        for other in cast("list[str]", operation.get("conflicts_with", [])):
            conflicts.setdefault(scenario, set()).add(other)
            conflicts.setdefault(other, set()).add(scenario)
    return conflicts


def _shared_error(operations: Sequence[Mapping[str, object]]) -> str | None:
    first: dict[str, int] = {}
    for index, operation in enumerate(operations):
        scenario = cast(str, operation["scenario_id"])
        if scenario not in first:
            first[scenario] = index
            continue
        other = operations[first[scenario]]
        for key in SHARED_KEYS:
            if operation.get(key) != other.get(key):
                return (f"operations[{index + 1}]: scenario {scenario} declares {key} "
                        f"{operation.get(key)!r} here and {other.get(key)!r} in "
                        f"operations[{first[scenario] + 1}]")
    return None


def _rarity_error(operations: Sequence[Mapping[str, object]]) -> str | None:
    totals: dict[str, int] = {}
    levels: dict[str, str] = {}
    for operation in operations:
        scenario = cast(str, operation["scenario_id"])
        totals[scenario] = totals.get(scenario, 0) + cast(int, operation["count"])
        if "rarity_level" in operation:
            levels[scenario] = cast(str, operation["rarity_level"])
    for scenario, level in levels.items():
        low, high = band_of(level)
        if totals[scenario] < low or (high is not None and totals[scenario] > high):
            band = f"{low} or more" if high is None else f"{low} to {high}"
            return (f"scenario {scenario} declares rarity_level {level} ({band} cases) "
                    f"but its operations total {totals[scenario]}")
    return None


def profile_scenario_error(operations: Sequence[Mapping[str, object]],
                           columns: Collection[str] | None = None,
                           output_profile: str = "default") -> str | None:
    """Return why the scenarios of a whole profile are incoherent, or None.

    ``columns`` are those of the target dataset in ``output_profile``; ``requires`` is checked
    against them. A legacy profile (no ``scenario_id``) is always coherent here. Each
    operation is assumed to have passed ``scenario_option_error`` already.
    """
    if not is_scenario_profile(operations):
        return None
    for index, operation in enumerate(operations, 1):
        if not is_scenario_operation(operation):
            return (f"operations[{index}]: a scenario profile declares scenario_id on every "
                    "operation (legacy and scenario operations cannot be mixed)")
    problem = _shared_error(operations) or _rarity_error(operations)
    if problem is not None:
        return problem
    scenarios = {cast(str, operation["scenario_id"]) for operation in operations}
    for index, operation in enumerate(operations, 1):
        scenario = cast(str, operation["scenario_id"])
        for other in cast("list[str]", operation.get("conflicts_with", [])):
            if other == scenario:
                return f"operations[{index}]: scenario {scenario} cannot conflict with itself"
            if other not in scenarios:
                return f"operations[{index}]: conflicts_with names the unknown scenario {other}"
        if operation.get("can_overlap") and operation["kind"] == "duplicate_row":
            return (f"operations[{index}]: duplicate_row cannot overlap another operation "
                    "(it replaces the whole row)")
        if columns is None:
            continue
        for column in cast("list[str]", operation.get("requires", [])):
            if column not in columns:
                provider = PROVIDING_PROFILES.get(column)
                return (f"operations[{index}]: scenario {scenario} requires column {column!r}, "
                        f"which the {output_profile} output profile does not have"
                        + (f" (the {provider} output profile provides it)" if provider else ""))
    return None
