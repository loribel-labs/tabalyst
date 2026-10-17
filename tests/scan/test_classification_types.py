# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Types carried by the detectors (Report overview lot R1b): one test per type of
the contract 3.3, the priority of a detector type, the explicit fallback of a
conflict and the pattern traits."""

import pytest
from scan_helpers import field, run_scan, write_text

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.classify import ClassifyContext, classify_field
from tabalyst.scanner.models import InterpretationCandidate, Interpretations


def _classification(tmp_path, header, values, **settings):
    source = write_text(
        tmp_path, "data.csv", "\n".join([header, *map(str, values)]) + "\n"
    )
    return field(run_scan(source, **settings)["datasets"][0], header)["classification"]


def _pair(classification):
    return classification["family"], classification["type"]


def _traits(classification):
    """The traits of the type itself, without the facts of the position and the
    uniqueness every first column of these one-column files has (lot R3)."""
    return [
        item
        for item in classification["traits"]
        if item not in {"first_column", "observed_unique"}
    ]


def _supports(classification, source, identifier):
    return any(
        item["source"] == source
        and item["id"] == identifier
        and item["role"] == "supports"
        for item in classification["evidence"]
    )


# --- One test per type -----------------------------------------------------------


def test_the_enumeration_detector_gives_enum(tmp_path):
    classification = _classification(tmp_path, "colour", ["red", "green", "blue"] * 200)

    assert _pair(classification) == ("categorical", "enum")
    assert classification["state"] == "established"
    assert _supports(classification, "detector", "enumeration")


def test_a_textual_boolean_detector_gives_boolean(tmp_path):
    classification = _classification(tmp_path, "active", ["yes", "no"] * 5)

    assert _pair(classification) == ("categorical", "boolean")
    assert classification["basis"] == "inferred"
    assert _supports(classification, "detector", "boolean")


def test_a_technical_boolean_gives_boolean(tmp_path):
    classification = _classification(tmp_path, "active", ["true", "false"] * 5)

    assert _pair(classification) == ("categorical", "boolean")
    assert _supports(classification, "technical_type", "boolean")


def test_a_text_with_a_single_value_is_constant(tmp_path):
    classification = _classification(tmp_path, "currency", ["N/A"] * 5)

    assert _pair(classification) == ("categorical", "constant")
    assert _traits(classification) == []
    assert _supports(classification, "measure", "values.cardinality")


def test_one_present_value_is_not_a_constant(tmp_path):
    classification = _classification(tmp_path, "currency", ["N/A"])

    assert _pair(classification) == ("text", "text_very_short")


def test_integers_and_numbers_keep_their_technical_type(tmp_path):
    assert _pair(_classification(tmp_path, "n", [10, 20, 35, 120])) == (
        "numeric",
        "integer",
    )
    assert _pair(_classification(tmp_path, "x", ["1.5", "2.25", "3.75"])) == (
        "numeric",
        "number",
    )


def test_the_currency_detector_gives_currency(tmp_path):
    classification = _classification(tmp_path, "amount", ["$12.50", "$3.00", "$45.10"] * 5)

    assert _pair(classification) == ("numeric", "currency")
    assert _supports(classification, "detector", "currency")


def test_the_percentage_detector_gives_percentage(tmp_path):
    classification = _classification(tmp_path, "rate", ["12%", "5%", "40.5%"] * 5)

    assert _pair(classification) == ("numeric", "percentage")


def test_the_quantity_detector_gives_quantity(tmp_path):
    classification = _classification(tmp_path, "size", ["10m", "20 m", "5km"] * 4)

    assert _pair(classification) == ("numeric", "quantity")


def test_calendar_dates_give_date(tmp_path):
    classification = _classification(
        tmp_path, "day", ["2026-10-06", "2026-10-07", "2026-10-08"] * 3
    )

    assert _pair(classification) == ("temporal", "date")


@pytest.mark.parametrize(
    "values",
    [
        ["2026-10-06T12:30:00Z", "2026-10-07T13:30:00Z", "2026-10-08T14:30:00Z"],
        ["2026-10-06 12:30:00", "2026-10-07 13:30:00", "2026-10-08 14:30:00"],
    ],
    ids=["with a time zone", "without a time zone"],
)
def test_date_times_give_datetime_with_or_without_a_time_zone(tmp_path, values):
    classification = _classification(tmp_path, "at", values * 3)

    assert _pair(classification) == ("temporal", "datetime")
    assert _supports(classification, "measure", "temporal.kinds")


def test_times_of_day_give_time(tmp_path):
    classification = _classification(tmp_path, "at", ["12:30", "13:45", "08:10"] * 3)

    assert _pair(classification) == ("temporal", "time")


def test_a_date_and_datetime_mix_keeps_the_dominant_nature(tmp_path):
    values = ["2026-10-06", "2026-10-07", "2026-10-08T10:00:00"] * 3

    classification = _classification(tmp_path, "day", values)

    assert _pair(classification) == ("temporal", "date")
    assert classification["state"] == "established"
    assert [(item["type"], item["reason"]) for item in classification["alternatives"]] == [
        ("datetime", "minority_kind")
    ]


def test_two_temporal_natures_of_the_same_weight_give_the_fallback(tmp_path):
    classification = _classification(
        tmp_path, "at", ["12:30", "2026-10-06 10:00:00"] * 5
    )

    assert _pair(classification) == ("other", "unknown")
    assert classification["state"] == "undetermined"
    assert {item["type"] for item in classification["alternatives"]} == {
        "datetime",
        "time",
    }


def test_the_email_detector_gives_email(tmp_path):
    classification = _classification(
        tmp_path, "contact", [f"user{n}@example.com" for n in range(30)]
    )

    assert _pair(classification) == ("contact", "email")


def test_the_phone_detector_gives_phone(tmp_path):
    classification = _classification(
        tmp_path, "tel", ["0612345678", "0145678901", "0298765432"] * 4
    )

    assert _pair(classification) == ("contact", "phone")


def test_the_postal_code_detector_gives_postal_code(tmp_path):
    classification = _classification(tmp_path, "area", ["K1A 0B1", "H2X 1Y4"] * 5)

    assert _pair(classification) == ("geographic", "postal_code")


def test_a_postal_code_column_with_letters_does_not_need_the_name(tmp_path):
    classification = _classification(tmp_path, "x", ["12345", "K1A 0B1"] * 30)

    assert _pair(classification) == ("geographic", "postal_code")


def test_the_url_detector_gives_url(tmp_path):
    classification = _classification(
        tmp_path, "link", ["https://a.example/x", "https://b.example/y"] * 5
    )

    assert _pair(classification) == ("web_network", "url")


def test_the_ip_address_detector_gives_ip_address(tmp_path):
    classification = _classification(tmp_path, "host", ["10.0.0.1", "192.168.1.5"] * 5)

    assert _pair(classification) == ("web_network", "ip_address")


def test_the_uuid_detector_gives_uuid(tmp_path):
    values = [
        "123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-12d3-a456-426614174001",
    ]

    classification = _classification(tmp_path, "key", values * 4)

    assert _pair(classification) == ("web_network", "uuid")


# --- Priority --------------------------------------------------------------------


def test_a_detector_type_outranks_enum(tmp_path):
    classification = _classification(
        tmp_path, "contact", ["a@example.com", "b@example.org"] * 300
    )

    assert _pair(classification) == ("contact", "email")
    assert [(item["type"], item["reason"]) for item in classification["alternatives"]] == [
        ("enum", "outranked_by_email")
    ]


def test_two_categories_stay_enum_even_for_a_boolean_looking_name(tmp_path):
    classification = _classification(tmp_path, "is_member", ["M", "F"] * 300)

    assert _pair(classification) == ("categorical", "enum")


def test_a_numeric_column_with_few_values_keeps_its_type_and_lists_enum(tmp_path):
    classification = _classification(tmp_path, "grade", [1, 2, 3] * 250)

    assert _pair(classification) == ("numeric", "integer")
    assert classification["state"] == "established"
    assert [(item["type"], item["reason"]) for item in classification["alternatives"]] == [
        ("enum", "numeric_type_kept")
    ]


def test_a_single_value_is_a_trait_of_a_typed_column(tmp_path):
    assert _traits(_classification(tmp_path, "n", [42] * 5)) == ["constant"]
    email = _classification(tmp_path, "mail", ["a@example.com"] * 5)
    assert _pair(email) == ("contact", "email")
    assert "constant" in email["traits"]


def test_bare_numbers_are_never_currency_nor_percentage(tmp_path):
    for values in ([10, 20, 35], ["12.5", "30.2", "99.1"]):
        classification = _classification(tmp_path, "price", values * 3)

        assert classification["family"] == "numeric"
        assert classification["type"] in {"integer", "number"}


# --- Conflicts -------------------------------------------------------------------


def test_digits_read_by_number_and_a_detector_keep_the_technical_type_undetermined(
    tmp_path,
):
    classification = _classification(
        tmp_path, "code", ["12345", "90210", "10001", "60601"] * 10
    )

    assert _pair(classification) == ("numeric", "integer")
    assert classification["state"] == "undetermined"
    assert classification["basis"] == "fallback"
    assert {item["type"] for item in classification["alternatives"]} == {
        "integer",
        "postal_code",
    }
    assert {item["role"] for item in classification["evidence"]} == {"context"}


def test_ten_digits_are_a_conflict_between_number_and_phone(tmp_path):
    classification = _classification(tmp_path, "digits", ["5145551234", "6135559876"] * 5)

    assert classification["state"] == "undetermined"
    assert {item["type"] for item in classification["alternatives"]} == {
        "integer",
        "phone",
    }


def _two_detectors(tmp_path, first, second):
    """A scanned field whose interpretations name two credible detectors."""
    source = write_text(tmp_path, "data.csv", "x\n" + "a@example.com\n" * 4)
    result = scan(source)
    chosen = result.datasets[0].fields[0]
    candidates = [
        InterpretationCandidate(detector=name, matched=4, share_eligible=1.0)
        for name in (first, second)
    ]
    # The detector results stay those of the scan: only the credible ids change.
    return chosen.model_copy(
        update={"interpretations": Interpretations(primary=None, candidates=candidates)}
    )


def test_two_detector_types_that_cannot_be_told_apart_give_other_unknown(tmp_path):
    chosen = _two_detectors(tmp_path, "email", "url")

    classification = classify_field(chosen, ClassifyContext(ScanConfig().classification))

    assert (classification.family, classification.type) == ("other", "unknown")
    assert classification.state == "undetermined"
    assert {item.type for item in classification.alternatives} == {"email", "url"}


def test_the_order_of_the_detectors_never_decides_a_conflict(tmp_path):
    context = ClassifyContext(ScanConfig().classification)

    forward = classify_field(_two_detectors(tmp_path, "email", "url"), context)
    backward = classify_field(_two_detectors(tmp_path, "url", "email"), context)

    assert forward == backward


# --- Traits ----------------------------------------------------------------------


def test_one_discovered_pattern_gives_the_trait_single_pattern(tmp_path):
    classification = _classification(
        tmp_path, "ref", [f"AB-{n:03d}" for n in range(60)]
    )

    assert _traits(classification) == ["single_pattern"]
    assert _pair(classification)[0] == "text"


def test_several_discovered_patterns_give_the_trait_multiple_patterns(tmp_path):
    values = [f"AB-{n:03d}" for n in range(30)] + [f"X{n}" for n in range(30)]

    classification = _classification(tmp_path, "ref", values)

    assert _traits(classification) == ["multiple_patterns"]


def test_without_the_pattern_discovery_there_is_no_pattern_trait(tmp_path):
    classification = _classification(
        tmp_path,
        "ref",
        [f"AB-{n:03d}" for n in range(60)],
        pattern_inference={"enabled": False},
    )

    assert _traits(classification) == []


def test_the_traits_never_change_the_primary_pair(tmp_path):
    values = [f"AB-{n:03d}" for n in range(60)]

    with_traits = _classification(tmp_path, "ref", values)
    without = _classification(tmp_path, "ref", values, pattern_inference={"enabled": False})

    assert _pair(with_traits) == _pair(without)
