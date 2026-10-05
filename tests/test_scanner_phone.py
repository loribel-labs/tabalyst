# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json

import pytest
from pydantic import ValidationError

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.detectors.phone import MAX_LENGTH, MIN_LENGTH, PhoneDetector

PHONE = PhoneDetector({})


def _write(tmp_path, content: str, name: str = "data.csv"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def _csv(tmp_path, column: str, values: list[str]):
    rows = "".join(f"{json.dumps(value)}\n" for value in values)
    return _write(tmp_path, f"{column}\n{rows}")


def _scan(path, **settings) -> dict:
    config = ScanConfig.model_validate(settings)
    return scan(path, config=config).model_dump(mode="json")


def _field(result: dict, display: str) -> dict:
    [dataset] = result["datasets"]
    [match] = [item for item in dataset["fields"] if item["display"] == display]
    return match


def _detector(field: dict, detector_id: str) -> dict:
    [match] = [item for item in field["detectors"] if item["id"] == detector_id]
    return match


@pytest.mark.parametrize(
    ("value", "format", "region"),
    [
        ("(514) 555-0100", "(999) 999-9999", "nanp"),
        ("(514)555-0100", "(999)999-9999", "nanp"),
        ("514-555-0100", "999-999-9999", "nanp"),
        ("514.555.0100", "999.999.9999", "nanp"),
        ("514 555 0100", "999 999 9999", "nanp"),
        ("5145550100", "9999999999", "nanp"),
        ("+1 514 555 0100", "+1 999 999 9999", "nanp"),
        ("+1-468-555-0110", "+1-999-999-9999", "nanp"),
        ("+1 (514) 555-0100", "+1 (999) 999-9999", "nanp"),
        ("+15145550100", "+19999999999", "nanp"),
        ("1-800-555-0199", "1-999-999-9999", "nanp"),
        ("15145550100", "19999999999", "nanp"),
        ("06 12 34 56 78", "09 99 99 99 99", "fr"),
        ("01.23.45.67.89", "09.99.99.99.99", "fr"),
        ("09-87-65-43-21", "09-99-99-99-99", "fr"),
        ("0612345678", "0999999999", "fr"),
        ("+33 6 12 34 56 78", "+33 9 99 99 99 99", "fr"),
        ("+33 (0)6 12 34 56 78", "+33 (0)9 99 99 99 99", "fr"),
        ("+33612345678", "+33999999999", "fr"),
        ("0033 1 23 45 67 89", "0033 9 99 99 99 99", "fr"),
        ("0033 (0) 6 12 34 56 78", "0033 (0) 9 99 99 99 99", "fr"),
        ("0033612345678", "0033999999999", "fr"),
    ],
)
def test_phone_matches(value, format, region):
    found = PHONE.classify(value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, region)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("123-456-7890", "invalid_area_code"),
        ("(023) 456-7890", "invalid_area_code"),
        ("061 234 5678", "invalid_area_code"),
        ("+1 123 456 7890", "invalid_area_code"),
        ("514-055-0100", "invalid_exchange_code"),
        ("514-155-0100", "invalid_exchange_code"),
        ("+33 06 12 34 56 78", "invalid_trunk_prefix"),
        ("+330612345678", "invalid_trunk_prefix"),
        ("00 12 34 56 78", "invalid_leading_digit"),
        ("+33 0 12 34 56 78", "invalid_leading_digit"),
    ],
)
def test_phone_invalid_values_have_a_reason(value, reason):
    found = PHONE.classify(value)
    assert found is not None and found.state == "invalid"
    assert found.reason == reason


@pytest.mark.parametrize(
    "value",
    [
        # Digits only carry no phone syntax: never invalid.
        "1234567890",
        "0012345678",
        "5140550100",
        # Other forms and countries.
        "555-0100",
        "+44 20 7946 0958",
        "+49 30 123456",
        "06 12 34 56 7",
        "06-12 34-56-78",
        "514-555-0100 x12",
        "514/555/0100",
        "514--555-0100",
        "(514 555-0100",
        "+1 514 555 0100 ",
        "phone 5145550100",
        "٥١٤٥٥٥٠١٠٠",
        # Values of other detectors.
        "192.168.100.200",
        "2026-09-26",
        "2026-09-26T22:00:00Z",
        "1 234 567,89",
        "12 345 678",
        "jane@example.com",
        "https://example.com",
        "",
    ],
)
def test_phone_does_not_match(value):
    assert PHONE.classify(value) is None


def test_phone_length_bounds_are_the_accepted_forms():
    shortest, longest = "0612345678", "0033 (0) 6 12 34 56 78"
    assert (len(shortest), len(longest)) == (MIN_LENGTH, MAX_LENGTH)
    assert PHONE.classify(shortest).state == "matched"
    assert PHONE.classify(longest).state == "matched"
    assert PhoneDetector.max_input_length is None
    assert PhoneDetector.shapes is None


def test_phone_regions_are_configurable():
    nanp = PhoneDetector({"regions": ["nanp"]})
    fr = PhoneDetector({"regions": ["fr"]})

    assert nanp.classify("06 12 34 56 78") is None
    assert nanp.classify("514-555-0100").state == "matched"
    assert fr.classify("514-555-0100") is None
    assert fr.classify("+33 6 12 34 56 78").state == "matched"


@pytest.mark.parametrize("regions", [[], ["nanp", "nanp"], ["us"], ["ca"]])
def test_phone_regions_are_validated(regions):
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detectors": {"phone": {"regions": regions}}})


def test_phone_formats_regions_and_interpretation(tmp_path):
    values = [
        "(514) 555-0100",
        "(418) 555-0199",
        " +1  514 555 0100 ",
        "06 12 34 56 78",
        "123-456-7890",
        "n/a",
    ]
    source = _csv(tmp_path, "phone", values)

    field = _field(_scan(source, exposure={"sensitive_values": "show"}), "phone")
    phone = _detector(field, "phone")

    assert phone["coverage"] == {
        "eligible": 6,
        "tested": 6,
        "matched": 4,
        "ambiguous": 0,
        "invalid": 1,
        "not_matched": 1,
        "not_tested": 0,
        "share_tested": 0.6667,
        "share_eligible": 0.6667,
    }
    assert phone["formats"] == [
        {"format": "(999) 999-9999", "count": 2},
        {"format": "+1 999 999 9999", "count": 1},
        {"format": "09 99 99 99 99", "count": 1},
    ]
    assert phone["details"] == {"regions": {"fr": 1, "nanp": 3}}
    assert phone["evidence"]["invalid"] == ["123-456-7890"]
    assert phone["evidence"]["matched"][2] == "+1 514 555 0100"
    assert field["sensitive"] is True
    assert field["exposure"] == "show"


def test_phone_regions_follow_the_setting(tmp_path):
    source = _csv(tmp_path, "phone", ["514-555-0100", "06 12 34 56 78"])

    field = _field(_scan(source, detectors={"phone": {"regions": ["fr"]}}), "phone")

    assert _detector(field, "phone")["details"] == {"regions": {"fr": 1}}


def test_phone_field_is_masked_by_default(tmp_path):
    source = _csv(tmp_path, "phone", ["(514) 555-0100", "(418) 555-0199", "x"])

    field = _field(_scan(source), "phone")
    phone = _detector(field, "phone")

    assert field["sensitive"] is True
    assert field["exposure"] == "mask"
    assert phone["evidence"]["matched"] == ["(999) 999-9999"]
    assert "514" not in json.dumps(field)


def test_phone_values_are_hidden_under_hide(tmp_path):
    source = _csv(tmp_path, "phone", ["(514) 555-0100", "123-456-7890"])

    field = _field(_scan(source, exposure={"sensitive_values": "hide"}), "phone")
    phone = _detector(field, "phone")

    assert phone["evidence"]["matched"] == []
    assert phone["evidence"]["invalid"] == []
    assert phone["details"] == {"regions": {"fr": 0, "nanp": 1}}
    assert "555" not in json.dumps(field)


def test_invalid_phones_alone_do_not_make_a_field_sensitive(tmp_path):
    source = _csv(tmp_path, "code", ["123-456-7890", "1234567890"])

    field = _field(_scan(source), "code")
    phone = _detector(field, "phone")

    assert phone["coverage"]["invalid"] == 1
    assert phone["coverage"]["not_matched"] == 1
    assert field["sensitive"] is False


def test_bare_nanp_numbers_are_also_integers(tmp_path):
    values = ["5145550100", "4185550199", "15145550100", "+15145550100"]
    source = _csv(tmp_path, "phone", values)

    field = _field(_scan(source), "phone")

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["number", "phone"]
    assert field["interpretations"]["primary"] is None
    # A sensitive field has no numeric statistics under ``mask``.
    assert field["numeric"]["status"] == "disabled"


def test_french_numbers_are_neither_numbers_nor_dates(tmp_path):
    values = ["0612345678", "06 12 34 56 78", "01.23.45.67.89", "+33 1 23 45 67 89"]
    source = _csv(tmp_path, "phone", values)

    field = _field(_scan(source), "phone")

    assert _detector(field, "number")["coverage"]["matched"] == 0
    assert _detector(field, "date")["coverage"]["matched"] == 0
    assert field["interpretations"]["primary"] == "phone"
    assert field["technical_type"]["type"] == "text"


def test_phones_are_not_emails_or_urls_and_other_values_are_not_phones(tmp_path):
    values = [
        "jane@example.com",
        "https://example.com",
        "192.168.100.200",
        "2026-09-26",
        "1 234 567,89",
    ]
    source = _csv(tmp_path, "value", values)

    field = _field(_scan(source), "value")

    assert _detector(field, "phone")["coverage"]["matched"] == 0
    assert _detector(field, "phone")["coverage"]["invalid"] == 0


def test_phone_overlaps_enumeration_and_patterns(tmp_path):
    values = ["06 12 34 56 78", "01 23 45 67 89", "09 87 65 43 21"] * 200
    source = _csv(tmp_path, "phone", values)

    field = _field(
        _scan(source, patterns=[{"id": "pairs", "regex": r"(\d\d ){4}\d\d"}]), "phone"
    )

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["enumeration", "pattern:pairs", "phone"]
    assert field["interpretations"]["primary"] is None


def test_phone_can_be_disabled(tmp_path):
    source = _csv(tmp_path, "phone", ["(514) 555-0100"])

    result = _scan(source, detectors={"phone": {"enabled": False}})
    field = _field(result, "phone")

    assert _detector(field, "phone") == {
        "id": "phone",
        "version": 1,
        "status": "disabled",
    }
    assert "phone" not in result["engine"]["detectors"]
    assert field["sensitive"] is False


def test_phone_ignores_native_json_values(tmp_path):
    source = _write(tmp_path, json.dumps([{"n": 5145550100}]), "d.json")

    field = _field(_scan(source), "n")

    assert _detector(field, "phone")["status"] == "not_applicable"
    assert field["sensitive"] is False
