import json

import pytest
from pydantic import ValidationError

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.detectors.ip import MAX_LENGTH, MIN_LENGTH, IpAddressDetector
from tabalyst.scanner.detectors.registry import BUILT_INS
from tabalyst.scanner.detectors.uuid import LENGTHS, UuidDetector

UUID = UuidDetector({})
IP = IpAddressDetector({})
V4 = "123e4567-e89b-42d3-a456-426614174000"


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


def _others(value: str, *excluded: str) -> list[str]:
    """Ids of the other value-level built-ins that match ``value``."""
    found = []
    for cls in BUILT_INS:
        if cls.id in excluded or cls.scope == "field":
            continue
        result = cls({}).classify(value)
        if result is not None and result.state in ("matched", "ambiguous"):
            found.append(cls.id)
    return found


# UUID


@pytest.mark.parametrize(
    ("value", "format", "version"),
    [
        ("123e4567-e89b-12d3-a456-426614174000", "hyphenated", "1"),
        (V4, "hyphenated", "4"),
        ("123E4567-E89B-42D3-A456-426614174000", "hyphenated_upper", "4"),
        ("123E4567-e89b-42d3-a456-426614174000", "hyphenated_mixed", "4"),
        ("{123e4567-e89b-42d3-a456-426614174000}", "braced", "4"),
        ("{123E4567-E89B-42D3-A456-426614174000}", "braced_upper", "4"),
        ("urn:uuid:123e4567-e89b-42d3-a456-426614174000", "urn", "4"),
        ("URN:UUID:123e4567-e89b-42d3-a456-426614174000", "urn", "4"),
        ("urn:uuid:123E4567-E89B-42D3-A456-426614174000", "urn_upper", "4"),
        ("0190a8c4-7b3e-7c1d-9f00-0123456789ab", "hyphenated", "7"),
        ("0190a8c4-7b3e-8c1d-bf00-0123456789ab", "hyphenated", "8"),
        ("00000000-0000-0000-0000-000000000000", "hyphenated", "nil"),
        ("ffffffff-ffff-ffff-ffff-ffffffffffff", "hyphenated", "max"),
        ("FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF", "hyphenated_upper", "max"),
        # Other variants (NCS, Microsoft) and undefined versions.
        ("12345678-1234-1234-1234-123456789012", "hyphenated", "other"),
        ("123e4567-e89b-42d3-c456-426614174000", "hyphenated", "other"),
        ("123e4567-e89b-02d3-a456-426614174000", "hyphenated", "other"),
        ("123e4567-e89b-92d3-a456-426614174000", "hyphenated", "other"),
        # Digits only count as lowercase.
        ("12345678-1234-4234-8234-123456789012", "hyphenated", "4"),
    ],
)
def test_uuid_matches(value, format, version):
    found = UUID.classify(value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, version)


@pytest.mark.parametrize(
    "value",
    [
        "123e4567-e89b-12d3-a456-42661417400g",
        "{g23e4567-e89b-12d3-a456-426614174000}",
        "urn:uuid:123e4567-e89b-12d3-a456-zzzzzzzzzzzz",
        "abcdefgh-ijkl-mnop-qrst-uvwxyzabcdef",
    ],
)
def test_uuid_invalid_values_have_a_reason(value):
    found = UUID.classify(value)
    assert found is not None and found.state == "invalid"
    assert found.reason == "invalid_hex_digit"


@pytest.mark.parametrize(
    "value",
    [
        # Other layouts, separators and partial values.
        "123e4567e89b12d3a456426614174000",
        "123e4567-e89b-12d3-a456-4266141740",
        "123e4567-e89b-12d3-a456-4266141740000",
        "123e4567_e89b_12d3_a456_426614174000",
        "123e4567-e89b12d3-a456-4266141740000",
        "123e4567 e89b 12d3 a456 426614174000",
        "{123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-12d3-a456-426614174000}",
        "(123e4567-e89b-12d3-a456-426614174000)",
        "uuid:urn:123e4567-e89b-12d3-a456-426614174000",
        "urn:guid:123e4567-e89b-12d3-a456-426614174000",
        "123e4567-e89b-12d3-a456-426614174000 ",
        # Non-ASCII letters and digits.
        "12345678-1234-1234-1234-12345678901é",
        "12345678-1234-1234-1234-12345678901٤",
        # Values of other detectors.
        "CTR-1000000281",
        "2026-09-26",
        "2026-09-26T22:00:00.000000+00:00",
        "(514) 555-0100",
        "jane@example.com",
        "192.168.100.200",
        "",
    ],
)
def test_uuid_does_not_match(value):
    assert UUID.classify(value) is None


def test_uuid_lengths_are_the_accepted_forms():
    forms = [V4, "{" + V4 + "}", "urn:uuid:" + V4]
    assert {len(value) for value in forms} == LENGTHS
    assert all(UUID.classify(value).state == "matched" for value in forms)
    assert UuidDetector.max_input_length is None
    assert UuidDetector.shapes is None
    assert UuidDetector.sensitive is False


@pytest.mark.parametrize(
    "value",
    [
        V4,
        "{" + V4 + "}",
        "urn:uuid:" + V4,
        "00000000-0000-0000-0000-000000000000",
        "12345678-1234-1234-1234-123456789012",
        "123e4567-e89b-12d3-a456-42661417400g",
    ],
)
def test_uuid_overlaps_no_other_built_in(value):
    assert _others(value, "uuid") == []


def test_uuid_formats_versions_and_interpretation(tmp_path):
    values = [
        V4,
        "  " + V4.upper() + " ",
        "{" + V4 + "}",
        "12345678-1234-1234-1234-123456789012",
        "0190a8c4-7b3e-7c1d-9f00-0123456789ab",
        V4,
        "123e4567-e89b-12d3-a456-42661417400g",
        "n/a",
    ]
    source = _csv(tmp_path, "customer_uuid", values)

    field = _field(_scan(source), "customer_uuid")
    uuid = _detector(field, "uuid")

    assert uuid["coverage"] == {
        "eligible": 8,
        "tested": 8,
        "matched": 6,
        "ambiguous": 0,
        "invalid": 1,
        "not_matched": 1,
        "not_tested": 0,
        "share_tested": 0.75,
        "share_eligible": 0.75,
    }
    assert uuid["formats"] == [
        {"format": "hyphenated", "count": 4},
        {"format": "braced", "count": 1},
        {"format": "hyphenated_upper", "count": 1},
    ]
    assert uuid["details"] == {"versions": {"4": 4, "7": 1, "other": 1}}
    # The analytical value trims; values are not masked.
    assert uuid["evidence"]["matched"][1] == V4.upper()
    assert uuid["evidence"]["invalid"] == ["123e4567-e89b-12d3-a456-42661417400g"]
    assert uuid["evidence"]["not_matched"] == ["n/a"]
    assert field["sensitive"] is False
    assert field["exposure"] is None


def test_uuids_are_the_primary_interpretation(tmp_path):
    values = [V4, "0190a8c4-7b3e-7c1d-9f00-0123456789ab", "{" + V4 + "}"]
    source = _csv(tmp_path, "id", values)

    field = _field(_scan(source), "id")

    assert field["interpretations"]["primary"] == "uuid"
    assert field["technical_type"]["type"] == "text"


def test_uuid_overlaps_enumeration_and_patterns(tmp_path):
    values = [V4, "0190a8c4-7b3e-7c1d-9f00-0123456789ab"] * 300
    source = _csv(tmp_path, "id", values)

    field = _field(
        _scan(source, patterns=[{"id": "hex", "regex": r"[0-9a-f-]{36}"}]), "id"
    )

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["enumeration", "pattern:hex", "uuid"]
    assert field["interpretations"]["primary"] is None


def test_uuid_can_be_disabled(tmp_path):
    source = _csv(tmp_path, "id", [V4])

    result = _scan(source, detectors={"uuid": {"enabled": False}})

    assert _detector(_field(result, "id"), "uuid") == {
        "id": "uuid",
        "version": 1,
        "status": "disabled",
    }
    assert "uuid" not in result["engine"]["detectors"]


def test_uuid_settings_reject_unknown_keys():
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detectors": {"uuid": {"forms": ["urn"]}}})


# IP addresses


@pytest.mark.parametrize(
    ("value", "format", "version"),
    [
        ("192.0.2.1", "ipv4", "ipv4"),
        ("0.0.0.0", "ipv4", "ipv4"),
        ("255.255.255.255", "ipv4", "ipv4"),
        ("10.0.0.1", "ipv4", "ipv4"),
        ("192.168.100.200", "ipv4", "ipv4"),
        ("2001:db8:0:0:0:0:0:1", "ipv6", "ipv6"),
        ("2001:0DB8:0000:0000:0000:0000:0000:0001", "ipv6", "ipv6"),
        ("ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", "ipv6", "ipv6"),
        ("2001:DB8::1", "ipv6_compressed", "ipv6"),
        ("2001:db8::", "ipv6_compressed", "ipv6"),
        ("::1", "ipv6_compressed", "ipv6"),
        ("::", "ipv6_compressed", "ipv6"),
        ("fe80::", "ipv6_compressed", "ipv6"),
        ("1:2:3:4:5:6:7::", "ipv6_compressed", "ipv6"),
        ("::2:3:4:5:6:7:8", "ipv6_compressed", "ipv6"),
        ("1:2:3::6:7:8", "ipv6_compressed", "ipv6"),
        ("::ffff:192.0.2.1", "ipv6_ipv4", "ipv6"),
        ("::192.0.2.1", "ipv6_ipv4", "ipv6"),
        ("64:ff9b::192.0.2.1", "ipv6_ipv4", "ipv6"),
        ("0:0:0:0:0:ffff:192.0.2.1", "ipv6_ipv4", "ipv6"),
        ("1:2:3:4:5::192.0.2.1", "ipv6_ipv4", "ipv6"),
        ("ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255", "ipv6_ipv4", "ipv6"),
    ],
)
def test_ip_address_matches(value, format, version):
    found = IP.classify(value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, version)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("192.168.01.1", "invalid_leading_zero"),
        ("010.0.0.1", "invalid_leading_zero"),
        ("1.2.3.00", "invalid_leading_zero"),
        ("256.1.1.1", "invalid_octet"),
        ("1.1.1.999", "invalid_octet"),
        # The first failed check, from left to right.
        ("300.01.1.1", "invalid_octet"),
        ("01.300.1.1", "invalid_leading_zero"),
        ("2001:db8::1::2", "invalid_compression"),
        ("2001:::1", "invalid_compression"),
        (":::", "invalid_compression"),
        ("2001:db8:0:0:0:0:0:12345", "invalid_group"),
        ("12345::1", "invalid_group"),
        (":1:2:3:4:5:6:7", "invalid_group"),
        ("1:2:3:4:5:6:7:", "invalid_group"),
        (":1::", "invalid_group"),
        ("::ffff:1.2.3", "invalid_group"),
        ("1.2.3.4::", "invalid_group"),
        ("1.2.3.4::1", "invalid_group"),
        ("1:2:3:4:5:6:7:8:9", "invalid_group_count"),
        ("1:2:3:4::5:6:7:8", "invalid_group_count"),
        ("1:2:3:4:5:6:7::192.0.2.1", "invalid_group_count"),
        ("::ffff:192.168.1.300", "invalid_octet"),
        ("::ffff:192.168.01.1", "invalid_leading_zero"),
    ],
)
def test_ip_address_invalid_values_have_a_reason(value, reason):
    found = IP.classify(value)
    assert found is not None and found.state == "invalid"
    assert found.reason == reason


@pytest.mark.parametrize(
    "value",
    [
        # Forms not accepted in version 1.
        "192.0.2.0/24",
        "2001:db8::/32",
        "192.0.2.1:80",
        "[2001:db8::1]",
        "[2001:db8::1]:443",
        "fe80::1%eth0",
        "127.1",
        "0x7f.0.0.1",
        # Other groupings.
        "1.2.3",
        "1.2.3.4.5",
        "1234.1.1.1",
        "1..2.3",
        ".1.2.3.4",
        "1.2.3.4.",
        "2001:db8:0:0:0:0:1",
        "2001:dg8::1",
        " ::1",
        # Times and MAC addresses.
        "12:30",
        "22:00:00",
        "22:00:00.5",
        "00:1A:2B:3C:4D:5E",
        "00-1A-2B-3C-4D-5E",
        # Non-ASCII digits.
        "١٩٢.١٦٨.١.١",
        "１.２.３.４",
        # Values of other detectors.
        "514.555.0100",
        "26.09.2026",
        "1.234,5",
        "http://192.168.1.1",
        "2026-09-26",
        V4,
        "",
        ":",
    ],
)
def test_ip_address_does_not_match(value):
    assert IP.classify(value) is None


def test_ip_address_lengths_are_the_accepted_forms():
    assert len("::") == MIN_LENGTH
    assert len("ffff:ffff:ffff:ffff:ffff:ffff:255.255.255.255") == MAX_LENGTH
    # Longer values are rejected before any check, as exact ``not_matched``.
    assert IP.classify("0:" * 22 + ":") is not None
    assert IP.classify("0:" * 23) is None
    assert IpAddressDetector.max_input_length is None
    assert IpAddressDetector.shapes is None
    assert IpAddressDetector.sensitive is True


def test_ip_address_versions_are_configurable():
    ipv4 = IpAddressDetector({"versions": ["ipv4"]})
    ipv6 = IpAddressDetector({"versions": ["ipv6"]})

    assert ipv4.classify("2001:db8::1") is None
    assert ipv4.classify("192.0.2.1").state == "matched"
    assert ipv4.classify("256.1.1.1").state == "invalid"
    assert ipv6.classify("192.0.2.1") is None
    assert ipv6.classify("256.1.1.1") is None
    # Embedded IPv4 addresses belong to IPv6.
    assert ipv6.classify("::ffff:192.0.2.1").state == "matched"


@pytest.mark.parametrize("versions", [[], ["ipv4", "ipv4"], ["4"], ["IPv4"]])
def test_ip_address_versions_are_validated(versions):
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detectors": {"ip_address": {"versions": versions}}})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("192.0.2.1", []),
        ("10.0.0.1", []),
        # The ``comma`` convention reads dots as grouped thousands.
        ("192.168.100.200", ["number"]),
        ("2001:db8::1", []),
        ("::ffff:192.0.2.1", []),
        ("fe80::1", []),
    ],
)
def test_ip_address_overlaps(value, expected):
    assert _others(value, "ip_address") == expected


def test_ip_address_field_is_masked_by_default(tmp_path):
    values = ["192.168.1.1", "10.0.0.1", "2001:db8::1", "256.1.1.1", "x"]
    source = _csv(tmp_path, "ip", values)

    field = _field(_scan(source), "ip")
    ip = _detector(field, "ip_address")

    assert field["sensitive"] is True
    assert field["exposure"] == "mask"
    assert ip["coverage"]["matched"] == 3
    assert ip["coverage"]["invalid"] == 1
    assert ip["formats"] == [
        {"format": "ipv4", "count": 2},
        {"format": "ipv6_compressed", "count": 1},
    ]
    assert ip["details"] == {"versions": {"ipv4": 2, "ipv6": 1}}
    assert ip["evidence"]["matched"] == ["999.999.9.9", "99.9.9.9", "9999:aa9::9"]
    assert ip["evidence"]["invalid"] == ["999.9.9.9"]
    assert "192" not in json.dumps(field)


def test_ip_address_values_are_hidden_under_hide(tmp_path):
    source = _csv(tmp_path, "ip", ["192.168.1.1", "256.1.1.1"])

    field = _field(_scan(source, exposure={"sensitive_values": "hide"}), "ip")
    ip = _detector(field, "ip_address")

    assert ip["evidence"]["matched"] == []
    assert ip["evidence"]["invalid"] == []
    assert ip["details"] == {"versions": {"ipv4": 1, "ipv6": 0}}
    assert "192" not in json.dumps(field)


def test_ip_address_values_are_shown_under_show(tmp_path):
    source = _csv(tmp_path, "ip", ["192.168.1.1"])

    field = _field(_scan(source, exposure={"sensitive_values": "show"}), "ip")

    assert field["exposure"] == "show"
    assert _detector(field, "ip_address")["evidence"]["matched"] == ["192.168.1.1"]


def test_invalid_ip_addresses_alone_do_not_make_a_field_sensitive(tmp_path):
    source = _csv(tmp_path, "code", ["256.1.1.1", "1.2.3"])

    field = _field(_scan(source), "code")

    assert _detector(field, "ip_address")["coverage"]["invalid"] == 1
    assert field["sensitive"] is False


def test_ip_addresses_are_the_primary_interpretation(tmp_path):
    source = _csv(tmp_path, "ip", ["79.110.172.52", "136.36.87.125", "::1"])

    field = _field(_scan(source), "ip")

    assert field["interpretations"]["primary"] == "ip_address"
    assert field["technical_type"]["type"] == "text"
    for other in ("number", "date", "phone", "postal_code", "uuid"):
        assert _detector(field, other)["coverage"]["matched"] == 0


def test_ip_addresses_with_three_digit_groups_are_also_numbers(tmp_path):
    values = ["192.168.100.200", "172.160.100.101", "100.100.100.100"]
    source = _csv(tmp_path, "ip", values)

    field = _field(_scan(source), "ip")

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["ip_address", "number"]
    assert field["interpretations"]["primary"] is None
    # A sensitive field has no numeric statistics under ``mask``.
    assert field["numeric"]["status"] == "disabled"


def test_ip_address_versions_follow_the_setting(tmp_path):
    source = _csv(tmp_path, "ip", ["192.0.2.1", "::1"])

    field = _field(_scan(source, detectors={"ip_address": {"versions": ["ipv6"]}}), "ip")
    ip = _detector(field, "ip_address")

    assert ip["details"] == {"versions": {"ipv6": 1}}
    assert ip["coverage"]["not_matched"] == 1


def test_ip_address_can_be_disabled(tmp_path):
    source = _csv(tmp_path, "ip", ["192.0.2.1"])

    result = _scan(source, detectors={"ip_address": {"enabled": False}})
    field = _field(result, "ip")

    assert _detector(field, "ip_address") == {
        "id": "ip_address",
        "version": 1,
        "status": "disabled",
    }
    assert "ip_address" not in result["engine"]["detectors"]
    assert field["sensitive"] is False


def test_uuid_and_ip_address_ignore_native_json_values(tmp_path):
    source = _write(tmp_path, json.dumps([{"id": 12, "ip": 3232235777}]), "d.json")

    result = _scan(source)

    for display, detector_id in (("id", "uuid"), ("ip", "ip_address")):
        detector = _detector(_field(result, display), detector_id)
        assert detector["status"] == "not_applicable"


def test_uuid_and_ip_address_are_registered_last():
    assert [cls.id for cls in BUILT_INS][-2:] == ["uuid", "ip_address"]
