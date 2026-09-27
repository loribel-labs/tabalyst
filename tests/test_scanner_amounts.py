import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.detectors.currency import CODES, CurrencyDetector
from tabalyst.scanner.detectors.percentage import PercentageDetector
from tabalyst.scanner.detectors.quantity import QuantityDetector

CURRENCY = CurrencyDetector({})
PERCENTAGE = PercentageDetector({})
QUANTITY = QuantityDetector({})
DETECTORS = {"currency": CURRENCY, "percentage": PERCENTAGE, "quantity": QUANTITY}
NBSP = " "
NNBSP = " "


def _write(tmp_path, content: str, name: str = "data.csv"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def _csv(tmp_path, column: str, values: list[str]):
    rows = "".join(f"{json.dumps(value, ensure_ascii=False)}\n" for value in values)
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


# Currency


@pytest.mark.parametrize(
    ("value", "format", "number"),
    [
        ("$12.50", "$0.0", Decimal("12.50")),
        ("$1,234.56", "$#,##0.0", Decimal("1234.56")),
        ("$.99", "$0.0", Decimal("0.99")),
        ("-$12.50", "$0.0", Decimal("-12.50")),
        ("$-12.50", "$0.0", Decimal("-12.50")),
        ("+$3", "$0", 3),
        ("($1,234.56)", "$#,##0.0", Decimal("-1234.56")),
        ("(12,50 €)", "0,0 €", Decimal("-12.50")),
        ("12,50 $", "0,0 $", Decimal("12.50")),
        ("-12,50 $", "0,0 $", Decimal("-12.50")),
        ("1 234,56 €", "# ##0,0 €", Decimal("1234.56")),
        (f"1{NNBSP}234,56{NBSP}€", f"#{NNBSP}##0,0{NBSP}€", Decimal("1234.56")),
        ("$ 1 234", "$ # ##0", 1234),
        ("12€", "0€", 12),
        ("€12", "€0", 12),
        ("£0.99", "£0.0", Decimal("0.99")),
        ("¥1000", "¥0", 1000),
        ("CA$ 20", "CA$ 0", 20),
        ("C$20", "C$0", 20),
        ("US$20", "US$0", 20),
        ("USD 12.50", "USD 0.0", Decimal("12.50")),
        ("USD12", "USD0", 12),
        ("12.50 EUR", "0.0 EUR", Decimal("12.50")),
        ("-12.50 CHF", "0.0 CHF", Decimal("-12.50")),
        ("100 HRK", "0 HRK", 100),
    ],
)
def test_currency_matches(value, format, number):
    found = CURRENCY.classify(value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, number)


@pytest.mark.parametrize("value", ["$1,234", "1,234 €", "USD 1,500", "(1,234 $)"])
def test_currency_ambiguous_values(value):
    found = CURRENCY.classify(value)
    assert found is not None and found.state == "ambiguous"
    assert found.candidates == ("#,##0", "0,0")
    assert found.value is None


@pytest.mark.parametrize(
    "value", ["$12.5.0", "$1,2345.00", "€01.50", "12,50,0 €", "($1,23,4)"]
)
def test_currency_invalid_values(value):
    found = CURRENCY.classify(value)
    assert found is not None and found.state == "invalid"
    assert found.reason == "invalid_amount"


@pytest.mark.parametrize(
    "value",
    [
        # No marker, or no number.
        "12.50",
        "-12",
        "$",
        "USD",
        "$abc",
        "$.",
        ".€",
        "€012",
        "(USD 007)",
        "()",
        "(12)",
        # Unknown codes, lowercase codes and several markers.
        "ABC 123",
        "XXX 12",
        "XAU 12",
        "usd 12",
        "Usd 12",
        "$12 USD",
        "12 $ CA",
        "$$12",
        # Signs, exponents, spaces and separators the forms do not accept.
        "$1e3",
        "-$-12",
        "(-$12)",
        "($-12)",
        "$  12",
        "12 \t€",
        "$,50",
        "$12,",
        "$1'000",
        # Values of other detectors.
        "12%",
        "10 Go",
        "CLI-00000281",
        "AG-PR-001",
        "H2X 1Y4",
        "2026-09-26",
        "(514) 555-0100",
        "",
    ],
)
def test_currency_does_not_match(value):
    assert CURRENCY.classify(value) is None


def test_currency_codes_are_iso_4217():
    assert len(CODES) > 150
    assert {"USD", "CAD", "EUR", "GBP", "JPY", "CHF", "XCG", "BGN"} <= CODES
    assert not {"XXX", "XTS", "XAU", "XDR", "USN"} & CODES
    assert all(len(code) == 3 and code.isascii() and code.isupper() for code in CODES)


def test_currency_attributes():
    assert (CurrencyDetector.family, CurrencyDetector.sensitive) == ("monetary", False)
    assert CurrencyDetector.max_input_length is None
    assert CurrencyDetector.shapes is None


def test_currency_ambiguity_can_be_resolved_by_configuration():
    comma = CurrencyDetector({"ambiguous_convention": "comma"})
    dot_only = CurrencyDetector({"conventions": ["dot"]})

    found = comma.classify("$1,234")
    assert (found.state, found.value, found.format) == (
        "matched",
        Decimal("1.234"),
        "$0,0",
    )
    assert found.candidates == ("#,##0", "0,0")
    assert dot_only.classify("$1,234").value == 1234
    assert dot_only.classify("12,500 €").value == 12500  # a thousands group
    assert dot_only.classify("12,50 €").state == "invalid"


def test_currency_scan_formats_details_and_interpretation(tmp_path):
    values = [
        "$12.50",
        "$1,234.56",
        "  $1,234.56 ",
        "12,50 €",
        "USD 3",
        "$1,234",
        "$12.5.0",
        "12.50",
    ]
    source = _csv(tmp_path, "amount", values)

    field = _field(_scan(source), "amount")
    currency = _detector(field, "currency")

    assert currency["coverage"] == {
        "eligible": 8,
        "tested": 8,
        "matched": 5,
        "ambiguous": 1,
        "invalid": 1,
        "not_matched": 1,
        "not_tested": 0,
        "share_tested": 0.625,
        "share_eligible": 0.625,
    }
    assert currency["formats"] == [
        {"format": "$#,##0.0", "count": 2},
        {"format": "$0.0", "count": 1},
        {"format": "0,0 €", "count": 1},
        {"format": "USD 0", "count": 1},
    ]
    assert currency["details"] == {
        "ambiguity": {
            "count": 1,
            "candidates": [{"formats": ["#,##0", "0,0"], "count": 1}],
            "evidence": {"comma": 1, "dot": 3},
            "resolution": None,
        },
        "currencies": {"$": 4, "USD": 1, "€": 1},
    }
    assert currency["evidence"]["invalid"] == ["$12.5.0"]
    assert currency["evidence"]["ambiguous"] == ["$1,234"]
    assert field["sensitive"] is False
    # Currency amounts are not in the numeric population (design 9.4).
    assert field["numeric"]["value"]["count"] == 1


def test_currency_resolution_is_published(tmp_path):
    source = _csv(tmp_path, "amount", ["$1,234", "$1,500"])

    result = _scan(source, detectors={"currency": {"ambiguous_convention": "dot"}})
    currency = _detector(_field(result, "amount"), "currency")

    assert currency["coverage"]["matched"] == 2
    assert currency["details"]["ambiguity"]["count"] == 2
    assert currency["details"]["ambiguity"]["resolution"] == {
        "convention": "dot",
        "source": "config",
    }
    # The number detector keeps its own settings.
    assert result["config"]["detectors"]["number"]["ambiguous_convention"] is None


def test_currency_is_the_primary_interpretation(tmp_path):
    source = _csv(tmp_path, "prime", ["1 234,18 $", "1 123,69 $", "980,00 $"])

    field = _field(_scan(source), "prime")

    assert field["interpretations"]["primary"] == "currency"
    assert field["technical_type"]["type"] == "text"
    for other in ("number", "percentage", "quantity", "date", "phone", "postal_code"):
        assert _detector(field, other)["coverage"]["matched"] == 0


# Percentage


@pytest.mark.parametrize(
    ("value", "format", "number"),
    [
        ("12%", "0%", 12),
        ("12 %", "0 %", 12),
        (f"12{NBSP}%", f"0{NBSP}%", 12),
        ("12.5%", "0.0%", Decimal("12.5")),
        ("12,5 %", "0,0 %", Decimal("12.5")),
        ("-3.5%", "0.0%", Decimal("-3.5")),
        ("+2%", "0%", 2),
        ("0%", "0%", 0),
        ("150%", "0%", 150),
        (".5%", "0.0%", Decimal("0.5")),
        ("1 234 %", "# ##0 %", 1234),
    ],
)
def test_percentage_matches(value, format, number):
    found = PERCENTAGE.classify(value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, number)


def test_percentage_ambiguous_and_invalid_values():
    ambiguous = PERCENTAGE.classify("1,234%")
    assert (ambiguous.state, ambiguous.candidates) == ("ambiguous", ("#,##0", "0,0"))
    for value in ("12.5.0%", "1,2,3 %", "05.5%"):
        found = PERCENTAGE.classify(value)
        assert (found.state, found.reason) == ("invalid", "invalid_number")


@pytest.mark.parametrize(
    "value",
    [
        "05%",
        "007 %",
        ".%",
        "..5%",
        "12",
        "%",
        "12 %%",
        "%12",
        "12 pct",
        "abc%",
        "50% off",
        "12% ",
        "12  %",
        "1e3%",
        "-+2%",
        "- 2%",
        "$12",
        "12 °C",
    ],
)
def test_percentage_does_not_match(value):
    assert PERCENTAGE.classify(value) is None


def test_percentage_scan_formats_and_details(tmp_path):
    source = _csv(tmp_path, "rate", ["12%", "12.5%", "3,5 %", "1,234%", "1,2,3%"])

    field = _field(_scan(source), "rate")
    percentage = _detector(field, "percentage")

    assert percentage["coverage"]["matched"] == 3
    assert percentage["coverage"]["ambiguous"] == 1
    assert percentage["coverage"]["invalid"] == 1
    assert percentage["formats"] == [
        {"format": "0%", "count": 1},
        {"format": "0,0 %", "count": 1},
        {"format": "0.0%", "count": 1},
    ]
    assert percentage["details"] == {
        "ambiguity": {
            "count": 1,
            "candidates": [{"formats": ["#,##0", "0,0"], "count": 1}],
            "evidence": {"comma": 1, "dot": 1},
            "resolution": None,
        }
    }
    assert (PercentageDetector.family, PercentageDetector.sensitive) == ("ratio", False)


# Quantity


@pytest.mark.parametrize(
    ("value", "format", "number"),
    [
        ("10m", "0[unit]", 10),
        ("10 m", "0 [unit]", 10),
        ("10Go", "0[unit]", 10),
        ("10 Go", "0 [unit]", 10),
        ("1 024 Mo", "# ##0 [unit]", 1024),
        ("1,5 To", "0,0 [unit]", Decimal("1.5")),
        ("12.5 kg", "0.0 [unit]", Decimal("12.5")),
        ("-3 °C", "0 [unit]", -3),
        ("20°C", "0[unit]", 20),
        ("90 km/h", "0 [unit]", 90),
        ("3 m²", "0 [unit]", 3),
        ("2 m³", "0 [unit]", 2),
        ("220 V", "0 [unit]", 220),
        ("5 kWh", "0 [unit]", 5),
        ("2 µs", "0 [unit]", 2),
        ("10 kΩ", "0 [unit]", 10),
        ("4 kg·m", "0 [unit]", 4),
        ("12 ans", "0 [unit]", 12),
        ("3 mo", "0 [unit]", 3),
        # Codes whose letters syntax cannot tell from a unit.
        ("12B", "0[unit]", 12),
        ("2A", "0[unit]", 2),
        (f"10{NNBSP}km", f"0{NNBSP}[unit]", 10),
        ("1 abcdefghijkl", "0 [unit]", 1),
    ],
)
def test_quantity_matches(value, format, number):
    found = QUANTITY.classify(value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, number)


def test_quantity_ambiguous_and_invalid_values():
    ambiguous = QUANTITY.classify("1,234 km")
    assert (ambiguous.state, ambiguous.candidates) == ("ambiguous", ("#,##0", "0,0"))
    for value in ("1,2,3 kg", "01.5 m", "12.5.0 Go"):
        found = QUANTITY.classify(value)
        assert (found.state, found.reason) == ("invalid", "invalid_number")


@pytest.mark.parametrize(
    "value",
    [
        # No unit, no number, or several words.
        "10",
        "m",
        "Go 10",
        "a 10 m",
        "10 fl oz",
        "3 rue des Lilas",
        "10  m",
        # Units the rule rejects.
        "1 abcdefghijklm",
        "10 km/",
        "10 /h",
        "10 kg·",
        "10m2",
        # Digits only with leading zeros carry no number syntax (codes).
        "01 m",
        "01A",
        "0012B",
        # No digit in the number part.
        ".com",
        ".NET",
        "..5 m",
        "10 m_s",
        "10 m-s",
        "10 m.",
        "1e3m",
        # Currency markers, percentages and ordinals.
        "12 USD",
        "12 €",
        "12$",
        "12%",
        "1er",
        "1re",
        "2e",
        "3ème",
        "3eme",
        "2nd",
        "2nde",
        "21st",
        "3rd",
        "4TH",
        # Values of other detectors.
        "H2X 1Y4",
        "90210",
        "2026-09-26",
        "22:00",
        "26 sept.",
        "jane@example.com",
        "12@example.com",
        "",
    ],
)
def test_quantity_does_not_match(value):
    assert QUANTITY.classify(value) is None


def test_quantity_scan_formats_and_units(tmp_path):
    values = ["10 Go", "512 Mo", "1 024 Mo", "2To", "3 mo", "1,234 Go", "01.5 Go", "x"]
    source = _csv(tmp_path, "taille", values)

    field = _field(_scan(source), "taille")
    quantity = _detector(field, "quantity")

    assert quantity["coverage"]["matched"] == 5
    assert quantity["coverage"]["ambiguous"] == 1
    assert quantity["coverage"]["invalid"] == 1
    assert quantity["formats"] == [
        {"format": "0 [unit]", "count": 3},
        {"format": "# ##0 [unit]", "count": 1},
        {"format": "0[unit]", "count": 1},
    ]
    # Units keep their case and count matched and ambiguous values.
    assert quantity["details"]["units"] == {
        "status": "complete",
        "value": {
            "distinct": 4,
            "listed": [
                {"value": "Go", "count": 2},
                {"value": "Mo", "count": 2},
                {"value": "To", "count": 1},
                {"value": "mo", "count": 1},
            ],
            "truncated": False,
        },
    }
    assert quantity["details"]["ambiguity"]["count"] == 1
    assert field["interpretations"]["primary"] is None
    assert (QuantityDetector.family, QuantityDetector.sensitive) == (
        "measurement",
        False,
    )


def test_quantity_units_are_bounded(tmp_path):
    source = _csv(tmp_path, "q", ["1 a", "2 b", "3 c", "4 c"])

    result = _scan(
        source,
        detectors={"quantity": {"max_tracked_units": 2, "max_listed_units": 1}},
    )
    units = _detector(_field(result, "q"), "quantity")["details"]["units"]

    assert units == {
        "status": "limited",
        "reason": "max_tracked",
        "limit": 2,
        "lower_bound": 3,
    }

    listed = _scan(source, detectors={"quantity": {"max_listed_units": 1}})
    units = _detector(_field(listed, "q"), "quantity")["details"]["units"]["value"]
    assert units == {
        "distinct": 3,
        "listed": [{"value": "c", "count": 2}],
        "truncated": True,
    }


def test_quantity_units_go_through_the_exposure_gate(tmp_path):
    # An email makes the field sensitive: units are masked like any value.
    source = _csv(tmp_path, "mixed", ["10 Go", "jane@example.com"])

    field = _field(_scan(source), "mixed")

    assert field["sensitive"] is True
    units = _detector(field, "quantity")["details"]["units"]["value"]
    assert units["listed"] == [{"value": "Aa", "count": 1}]

    hidden = _field(_scan(source, exposure={"sensitive_values": "hide"}), "mixed")
    units = _detector(hidden, "quantity")["details"]["units"]["value"]
    assert (units["listed"], units["truncated"]) == ([], True)


# Shared behavior


@pytest.mark.parametrize("detector_id", ["currency", "percentage", "quantity"])
@pytest.mark.parametrize(
    "settings",
    [
        {"conventions": []},
        {"conventions": ["dot", "dot"]},
        {"conventions": ["space"]},
        {"conventions": ["dot"], "ambiguous_convention": "comma"},
        {"unknown": 1},
    ],
)
def test_amount_settings_are_validated(detector_id, settings):
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detectors": {detector_id: settings}})


@pytest.mark.parametrize(
    "settings", [{"max_tracked_units": 0}, {"max_listed_units": -1}]
)
def test_quantity_limits_are_validated(settings):
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detectors": {"quantity": settings}})


@pytest.mark.parametrize(
    "value",
    ["$12.50", "12 %", "10 Go", "1,234 €", "12,5 %", "1 024 Mo", "-3 °C", "(12 $)"],
)
def test_amount_detectors_never_match_the_same_value(value):
    matches = [
        name
        for name, detector in DETECTORS.items()
        if detector.classify(value) is not None
    ]
    assert len(matches) == 1


def test_amounts_are_never_numbers(tmp_path):
    source = _csv(tmp_path, "v", ["$12", "12%", "12 kg", "12"])

    field = _field(_scan(source), "v")

    assert _detector(field, "number")["coverage"]["matched"] == 1
    for detector_id in ("currency", "percentage", "quantity"):
        assert _detector(field, detector_id)["coverage"]["matched"] == 1


def test_amount_detectors_overlap_enumeration_and_patterns(tmp_path):
    source = _csv(tmp_path, "rate", ["5%", "10%", "15%"] * 200)

    field = _field(
        _scan(source, patterns=[{"id": "pct", "regex": r"\d+%"}]),
        "rate",
    )

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["enumeration", "pattern:pct", "percentage"]
    assert field["interpretations"]["primary"] is None


@pytest.mark.parametrize("detector_id", ["currency", "percentage", "quantity"])
def test_amount_detectors_can_be_disabled(tmp_path, detector_id):
    source = _csv(tmp_path, "v", ["$12", "12%", "12 kg"])

    result = _scan(source, detectors={detector_id: {"enabled": False}})

    assert _detector(_field(result, "v"), detector_id) == {
        "id": detector_id,
        "version": 1,
        "status": "disabled",
    }
    assert detector_id not in result["engine"]["detectors"]


def test_amount_detectors_ignore_native_json_values(tmp_path):
    source = _write(tmp_path, json.dumps([{"v": 12}, {"v": 1.5}]), "d.json")

    field = _field(_scan(source), "v")

    for detector_id in ("currency", "percentage", "quantity"):
        assert _detector(field, detector_id)["status"] == "not_applicable"


def test_streaming_mode_gives_the_same_results(tmp_path):
    values = ["$12", "$1,234", "12 Go", "12 Go", "5%", "$12.5.0", "x"] * 3
    source = _csv(tmp_path, "v", values)

    complete = _field(_scan(source), "v")
    streaming = _field(_scan(source, limits={"max_distinct_per_field": 1}), "v")

    for detector_id in ("currency", "percentage", "quantity"):
        assert _detector(complete, detector_id) == _detector(streaming, detector_id)
