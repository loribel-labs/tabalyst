# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json

import pytest
from pydantic import ValidationError

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.detectors.postal import LENGTHS, PostalCodeDetector

POSTAL = PostalCodeDetector({})


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
        ("H2X 1Y4", "A9A 9A9", "ca"),
        ("H2X1Y4", "A9A9A9", "ca"),
        ("h2x 1y4", "a9a 9a9", "ca"),
        ("h2X1y4", "a9A9a9", "ca"),
        ("K1A 0B1", "A9A 9A9", "ca"),
        ("X0A 0H0", "A9A 9A9", "ca"),
        ("V6B 3K9", "A9A 9A9", "ca"),
        # W and Z are allowed after the first position.
        ("T2W 1Z9", "A9A 9A9", "ca"),
        ("90210", "99999", "us"),
        ("02134", "99999", "us"),
        ("00000", "99999", "us"),
        ("12345-6789", "99999-9999", "us"),
        ("02134-0001", "99999-9999", "us"),
    ],
)
def test_postal_code_matches(value, format, region):
    found = POSTAL.classify(value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, region)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("D2X 1Y4", "invalid_first_letter"),
        ("W1A 1A1", "invalid_first_letter"),
        ("z9z9z9", "invalid_first_letter"),
        ("U2O 1Y4", "invalid_first_letter"),
        ("H2O 1Y4", "invalid_letter"),
        ("H2X 1U4", "invalid_letter"),
        ("h2d1y4", "invalid_letter"),
        ("A1Q 1F1", "invalid_letter"),
    ],
)
def test_postal_code_invalid_values_have_a_reason(value, reason):
    found = POSTAL.classify(value)
    assert found is not None and found.state == "invalid"
    assert found.reason == reason


@pytest.mark.parametrize(
    "value",
    [
        # Other separators and partial codes.
        "H2X-1Y4",
        "H2X  1Y4",
        "H2X 1Y",
        "T3A 95",
        "J1 5M4",
        "H2X 1Y4 ",
        "2134",
        "123456",
        "123456789",
        "12345 6789",
        "12345-678",
        "12345-67890",
        "1234-56789",
        "12345.6789",
        # Other countries and scripts.
        "SW1A 1AA",
        "W1A 0AX",
        "1234 AB",
        "75008 Paris",
        "É2X 1Y4",
        "H2X 1Y٤",
        "٩٠٢١٠",
        "９０２１０",
        # Values of other detectors.
        "1.234",
        "-1234",
        "12,50",
        "22:00",
        "2026-09-26",
        "(514) 555-0100",
        "jane@example.com",
        "www.x.ca",
        "Yes",
        "",
    ],
)
def test_postal_code_does_not_match(value):
    assert POSTAL.classify(value) is None


def test_postal_code_lengths_are_the_accepted_forms():
    forms = ["90210", "H2X1Y4", "H2X 1Y4", "12345-6789"]
    assert {len(value) for value in forms} == LENGTHS
    assert all(POSTAL.classify(value).state == "matched" for value in forms)
    assert PostalCodeDetector.max_input_length is None
    assert PostalCodeDetector.shapes is None
    assert PostalCodeDetector.sensitive is False


def test_postal_code_regions_are_configurable():
    ca = PostalCodeDetector({"regions": ["ca"]})
    us = PostalCodeDetector({"regions": ["us"]})

    assert ca.classify("90210") is None
    assert ca.classify("H2X 1Y4").state == "matched"
    assert ca.classify("D2X 1Y4").state == "invalid"
    assert us.classify("H2X 1Y4") is None
    assert us.classify("D2X 1Y4") is None
    assert us.classify("12345-6789").state == "matched"


@pytest.mark.parametrize("regions", [[], ["ca", "ca"], ["fr"], ["CA"]])
def test_postal_code_regions_are_validated(regions):
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detectors": {"postal_code": {"regions": regions}}})


def test_postal_code_formats_regions_and_interpretation(tmp_path):
    values = [
        "H2X 1Y4",
        "G6V 8P2",
        "  h2x   1y4 ",
        "H2X1Y4",
        "12345-6789",
        "D2X 1Y4",
        "T3A 95",
    ]
    source = _csv(tmp_path, "code_postal", values)

    field = _field(_scan(source), "code_postal")
    postal = _detector(field, "postal_code")

    assert postal["coverage"] == {
        "eligible": 7,
        "tested": 7,
        "matched": 5,
        "ambiguous": 0,
        "invalid": 1,
        "not_matched": 1,
        "not_tested": 0,
        "share_tested": 0.7143,
        "share_eligible": 0.7143,
    }
    assert postal["formats"] == [
        {"format": "A9A 9A9", "count": 2},
        {"format": "99999-9999", "count": 1},
        {"format": "A9A9A9", "count": 1},
        {"format": "a9a 9a9", "count": 1},
    ]
    assert postal["details"] == {"regions": {"ca": 4, "us": 1}}
    # The analytical value collapses whitespace; values are not masked.
    assert postal["evidence"]["matched"][2] == "h2x 1y4"
    assert postal["evidence"]["invalid"] == ["D2X 1Y4"]
    assert postal["evidence"]["not_matched"] == ["T3A 95"]
    assert field["sensitive"] is False
    assert field["exposure"] is None


def test_postal_code_regions_follow_the_setting(tmp_path):
    source = _csv(tmp_path, "code", ["H2X 1Y4", "90210"])

    field = _field(_scan(source, detectors={"postal_code": {"regions": ["us"]}}), "code")

    assert _detector(field, "postal_code")["details"] == {"regions": {"us": 1}}


def test_canadian_codes_are_the_primary_interpretation(tmp_path):
    source = _csv(tmp_path, "code_postal", ["H2X 1Y4", "G6V 8P2", "K1A 0B1"])

    field = _field(_scan(source), "code_postal")

    assert field["interpretations"]["primary"] == "postal_code"
    assert field["technical_type"]["type"] == "text"
    for other in ("number", "date", "phone", "email", "url"):
        assert _detector(field, other)["coverage"]["matched"] == 0


def test_zip_codes_are_also_integers(tmp_path):
    source = _csv(tmp_path, "zip", ["90210", "10001", "60601"])

    field = _field(_scan(source), "zip")

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["number", "postal_code"]
    assert field["interpretations"]["primary"] is None
    # Not sensitive: numeric statistics stay available.
    assert field["numeric"]["status"] == "complete"


def test_zip_codes_with_leading_zeros_or_plus4_are_not_numbers(tmp_path):
    source = _csv(tmp_path, "zip", ["02134", "01002", "12345-6789", "00501-0001"])

    field = _field(_scan(source), "zip")

    assert _detector(field, "number")["coverage"]["matched"] == 0
    assert _detector(field, "phone")["coverage"]["matched"] == 0
    assert _detector(field, "date")["coverage"]["matched"] == 0
    assert field["interpretations"]["primary"] == "postal_code"


def test_postal_code_overlaps_enumeration_and_patterns(tmp_path):
    values = ["H2X 1Y4", "G6V 8P2", "K1A 0B1"] * 200
    source = _csv(tmp_path, "code_postal", values)

    field = _field(
        _scan(source, patterns=[{"id": "ca", "regex": r"[A-Z]\d[A-Z] \d[A-Z]\d"}]),
        "code_postal",
    )

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["enumeration", "pattern:ca", "postal_code"]
    assert field["interpretations"]["primary"] is None


def test_postal_code_can_be_disabled(tmp_path):
    source = _csv(tmp_path, "code", ["H2X 1Y4"])

    result = _scan(source, detectors={"postal_code": {"enabled": False}})
    field = _field(result, "code")

    assert _detector(field, "postal_code") == {
        "id": "postal_code",
        "version": 1,
        "status": "disabled",
    }
    assert "postal_code" not in result["engine"]["detectors"]


def test_postal_code_ignores_native_json_values(tmp_path):
    source = _write(tmp_path, json.dumps([{"zip": 90210}]), "d.json")

    field = _field(_scan(source), "zip")

    assert _detector(field, "postal_code")["status"] == "not_applicable"
