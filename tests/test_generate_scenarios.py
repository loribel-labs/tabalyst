# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check the pure parts of Insurance V2: scenario keys, rarity bands and canonical values."""

from __future__ import annotations

import pytest

from tabalyst.generate_canonical import (
    canonical_date,
    canonical_decimal,
    canonical_text,
)
from tabalyst.generate_insurance import insurance_canonical
from tabalyst.generate_rarity import RARITY_BANDS, band_of, level_of
from tabalyst.generate_scenarios import conflict_map, scenario_option_error

BASE = {"kind": "set_missing", "column": "nom", "count": 1, "scenario_id": "S1",
        "category": "format_invalid", "severity": "minor"}


def test_operation_without_scenario_keys_is_a_legacy_operation() -> None:
    assert scenario_option_error({"kind": "set_missing", "column": "nom", "rate": 0.1}) is None


def test_complete_scenario_operation_is_accepted() -> None:
    complete = {**BASE, "rule_id": "M17", "rarity_level": "single", "root_cause_id": "import_ok",
                "requires": ["nom"], "conflicts_with": ["S2"], "can_overlap": True,
                "expected_detection": "syntactic|domain"}
    assert scenario_option_error(complete) is None


@pytest.mark.parametrize(("change", "message"), [
    ({"scenario_id": "s1"}, "operation.scenario_id must match"),
    ({"scenario_id": "S" * 17}, "operation.scenario_id must match"),
    ({"category": "weird"}, "operation.category must be one of"),
    ({"severity": "huge"}, "operation.severity must be one of"),
    ({"rarity_level": "common"}, "operation.rarity_level must be one of"),
    ({"rule_id": "m17"}, "operation.rule_id must match"),
    ({"root_cause_id": "Import"}, "operation.root_cause_id must match"),
    ({"requires": ["a", "a"]}, "operation.requires must be a list of distinct names"),
    ({"conflicts_with": "S2"}, "operation.conflicts_with must be a list"),
    ({"can_overlap": "yes"}, "operation.can_overlap must be true or false"),
    ({"expected_detection": "magic"}, "operation.expected_detection must join"),
    ({"expected_detection": "none|domain"}, "none stands alone"),
    ({"expected_detection": "domain|domain"}, "operation.expected_detection must join"),
])
def test_invalid_scenario_key_is_refused_with_its_name(change: dict[str, object],
                                                       message: str) -> None:
    problem = scenario_option_error({**BASE, **change})
    assert problem is not None and message in problem


def test_empty_requires_and_conflicts_with_lists_mean_nothing_and_are_accepted() -> None:
    assert scenario_option_error({**BASE, "requires": [], "conflicts_with": []}) is None


def test_scenario_key_without_scenario_id_names_the_key() -> None:
    problem = scenario_option_error({"kind": "set_missing", "column": "nom", "count": 1,
                                     "can_overlap": True})
    assert problem == ("operation.can_overlap needs operation.scenario_id "
                       "(a legacy operation has no scenario keys)")


def test_conflicts_are_symmetric_across_scenarios() -> None:
    operations = [{**BASE, "conflicts_with": ["S2"]}, {**BASE, "scenario_id": "S2"},
                  {**BASE, "scenario_id": "S3", "conflicts_with": ["S2"]}]
    assert conflict_map(operations) == {"S1": {"S2"}, "S2": {"S1", "S3"}, "S3": {"S2"}}


def test_rarity_bands_cover_every_total_exactly_once() -> None:
    assert [level_of(total) for total in (1, 2, 9, 10, 74, 75, 199, 200, 999, 1000, 10**6)] == [
        "single", "extremely_rare", "extremely_rare", "very_rare", "very_rare", "rare", "rare",
        "uncommon", "uncommon", "frequent", "frequent"]
    assert band_of("frequent") == RARITY_BANDS["frequent"] == (1000, None)
    with pytest.raises(ValueError, match="at least 1"):
        level_of(0)


@pytest.mark.parametrize(("value", "date_format", "expected"), [
    ("05-10-2026", "%d-%m-%Y", "2026-10-05"),
    ("05-10-2026", "%m-%d-%Y", "2026-05-10"),
    ("2026-10-05", "%Y-%m-%d", "2026-10-05"),
])
def test_canonical_date_is_iso_in_the_convention_of_the_branch(
        value: str, date_format: str, expected: str) -> None:
    assert canonical_date(value, date_format) == expected


def test_canonical_date_fails_on_a_value_the_convention_cannot_read() -> None:
    with pytest.raises(ValueError, match="does not match format"):
        canonical_date("2026-13-40", "%Y-%m-%d")
    with pytest.raises(ValueError, match="unknown filiale"):
        insurance_canonical("date_debut", "2026-10-05", {"filiale": "mars"})
    with pytest.raises(ValueError, match="unknown filiale"):
        insurance_canonical("date_debut", "2026-10-05", {})


@pytest.mark.parametrize(("value", "expected"), [
    ("1234.50", "1234.50"), ("1 234,50 $", "1234.50"), ("12,5", "12.5"),
    ("1234.50 CAD", "1234.50"), ("N/A", "N/A"), ("-3", "-3"),
])
def test_canonical_decimal_is_a_plain_amount_or_the_trimmed_text(
        value: str, expected: str) -> None:
    assert canonical_decimal(value) == expected


def test_canonical_text_is_nfc_and_trimmed() -> None:
    assert canonical_text(" Montréal ") == "Montréal"


def test_insurance_canonical_reads_the_date_by_branch_and_keeps_identifiers() -> None:
    quebec = {"filiale": "quebec"}
    assert insurance_canonical("date_debut", "05-10-2026", quebec) == "2026-10-05"
    assert insurance_canonical("date_debut", "05-10-2026", {"filiale": "ontario"}) == "2026-05-10"
    assert insurance_canonical("date_debut", "2026-10-05", {"filiale": "principal"}) == "2026-10-05"
    assert insurance_canonical("date_fin", "", quebec) == ""
    assert insurance_canonical("id_client", " QC-0001 ", quebec) == " QC-0001 "
    assert insurance_canonical("prime_annuelle", "1234.50", quebec) == "1234.50"
    assert insurance_canonical("ville", "Montréal", quebec) == "Montréal"
