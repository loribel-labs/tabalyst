import json

import pytest

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.detectors.email import EmailDetector
from tabalyst.scanner.detectors.url import UrlDetector

EMAIL = EmailDetector({})
URL = UrlDetector({})


def _classify(detector, value: str):
    """Classification as the engine sees it: input cap first."""
    if len(value) > detector.max_input_length:
        return "not_tested"
    return detector.classify(value)


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


# Email


@pytest.mark.parametrize(
    "value",
    [
        "jane@example.com",
        "Jane.Doe+tag@Mail.Example.CO.UK",
        "j@exemple.québec",
        "o'brien@example.ie",
        "x@xn--bcher-kva.example",
        "user_1-2@sub-domain.example.org",
        "a" * 64 + "@example.com",
    ],
)
def test_email_matches(value):
    found = _classify(EMAIL, value)
    assert found is not None and found.state == "matched"
    assert found.format is None


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (".jane@example.com", "invalid_local_part"),
        ("jane.@example.com", "invalid_local_part"),
        ("jane..doe@example.com", "invalid_local_part"),
        ("josé@example.com", "invalid_local_part"),
        ('"jane"@example.com', "invalid_local_part"),
        ("jane doe@example.com", "invalid_local_part"),
        ("aud 08@proton.example", "invalid_local_part"),
        ("a" * 65 + "@example.com", "local_part_too_long"),
        ("jane@-example.com", "invalid_domain"),
        ("jane@example-.com", "invalid_domain"),
        ("jane@example.123", "invalid_domain"),
        ("jane@example..com", "invalid_domain"),
        ("jane@.example.com", "invalid_domain"),
        ("jane@example.com.", "invalid_domain"),
        ("jane@" + "a" * 64 + ".com", "invalid_domain"),
        ("jane@example_x.com", "invalid_domain"),
        ("lily.wright@gmail. example", "invalid_domain"),
        ("sophia50@g mail.example", "invalid_domain"),
    ],
)
def test_email_invalid_values_have_a_reason(value, reason):
    found = _classify(EMAIL, value)
    assert found is not None and found.state == "invalid"
    assert found.reason == reason


@pytest.mark.parametrize(
    "value",
    [
        "jane",
        "jane@localhost",
        "jane@@example.com",
        "a@b@example.com",
        "@example.com",
        "Jane <jane@example.com>",
        "<jane@example.com>",
        "www.example.com/contact@x.org",
        "https://example.com/a@b.org",
        "mailto:jane@example.com",
        "https://jane@example.com",
        "jane@[192.0.2.1]",
        "jane@example.com/path",
        "jane@example.com?subject=x",
        "",
    ],
)
def test_email_does_not_match(value):
    assert _classify(EMAIL, value) is None


def test_email_input_cap_is_254_characters():
    local = "a" * 60
    domain = ".".join(["b" * 60] * 3) + ".com"  # 187 characters
    assert _classify(EMAIL, f"{local}@{domain}").state == "matched"
    assert _classify(EMAIL, "a" * 255) == "not_tested"


# URL


@pytest.mark.parametrize(
    ("value", "format", "host"),
    [
        ("https://example.com", "https", "example.com"),
        ("HTTP://Example.com:8080/a?b=c#d", "http", "example.com"),
        ("ftp://files.example.com/x.csv", "ftp", "files.example.com"),
        ("http://localhost:8000", "http", "localhost"),
        ("http://192.0.2.1/", "http", "192.0.2.1"),
        ("http://[2001:DB8::1]:443/", "http", "[2001:db8::1]"),
        ("https://user:pw@example.com", "https", "example.com"),
        ("https://exemple.québec/été", "https", "exemple.québec"),
        ("https://example.com/a%20b?q=%C3%A9", "https", "example.com"),
        ("https://example.com?x", "https", "example.com"),
        ("www.example.com/path", "www", "www.example.com"),
        ("WWW.Example.org", "www", "www.example.org"),
        ("www.example.com:8080", "www", "www.example.com"),
        ("www.example.com/contact@x.org", "www", "www.example.com"),
        ("https://Straße.de", "https", "straße.de"),
    ],
)
def test_url_matches(value, format, host):
    found = _classify(URL, value)
    assert found is not None and found.state == "matched"
    assert (found.format, found.value) == (format, host)


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("https://", "invalid_host"),
        ("https:///path", "invalid_host"),
        ("http://-example.com", "invalid_host"),
        ("http://999.1.1.1", "invalid_host"),
        ("http://1.2.3", "invalid_host"),
        ("http://[2001:db8::g]/", "invalid_host"),
        ("http://[2001:db8::1", "invalid_host"),
        ("http://example.com./", "invalid_host"),
        ("www.", "invalid_host"),
        ("http://example.com:99999", "invalid_port"),
        ("http://example.com:", "invalid_port"),
        ("http://example.com:8a", "invalid_port"),
        ("http://example.com/%zz", "invalid_percent_encoding"),
        ("http://example.com/%4", "invalid_percent_encoding"),
        ("https://exa mple.com", "invalid_character"),
        ("http://example.com/{id}", "invalid_character"),
        ("http://example.com/a|b", "invalid_character"),
        ("http://example.com/a b", "invalid_character"),
    ],
)
def test_url_invalid_values_have_a_reason(value, reason):
    found = _classify(URL, value)
    assert found is not None and found.state == "invalid"
    assert found.reason == reason


@pytest.mark.parametrize(
    "value",
    [
        "example.com",
        "mailto:x@y.z",
        "file:///tmp/x",
        "javascript:alert(1)",
        "www.jane@example.com",
        "wwwexample",
        "see https://example.com",
        "http:/example.com",
        "gopher://example.com",
        "Kttp://example.com",
        "",
    ],
)
def test_url_does_not_match(value):
    assert _classify(URL, value) is None


def test_url_schemes_and_www_are_configurable():
    detector = UrlDetector({"schemes": ["gopher"], "www": False})
    assert detector.classify("gopher://example.com").format == "gopher"
    assert detector.classify("https://example.com") is None
    assert detector.classify("www.example.com") is None


@pytest.mark.parametrize("schemes", [["HTTP"], ["http", "http"], ["svn+ssh"]])
def test_url_schemes_are_validated(schemes):
    with pytest.raises(ValueError):
        ScanConfig.model_validate({"detectors": {"url": {"schemes": schemes}}})


# Scans: variants, details, overlaps and exposure


def test_email_variants_count_domains_ignoring_case(tmp_path):
    source = _csv(
        tmp_path,
        "email",
        [
            "jane@example.com",
            " Jane@Example.COM ",
            "bob+news@example.com",
            "ann@other.org",
            "bad..dot@example.com",
            "none",
        ],
    )

    field = _field(_scan(source, exposure={"sensitive_values": "show"}), "email")
    email = _detector(field, "email")

    assert email["coverage"]["matched"] == 4
    assert email["coverage"]["invalid"] == 1
    assert email["coverage"]["not_matched"] == 1
    assert email["formats"] == []
    assert email["details"]["domains"] == {
        "status": "complete",
        "value": {
            "distinct": 2,
            "listed": [
                {"value": "example.com", "count": 3},
                {"value": "other.org", "count": 1},
            ],
            "truncated": False,
        },
    }
    assert email["evidence"]["invalid"] == ["bad..dot@example.com"]
    assert field["sensitive"] is True
    assert field["exposure"] == "show"


def test_email_field_is_masked_by_default(tmp_path):
    source = _csv(tmp_path, "email", ["jane@example.com", "bob@example.com", "x"])

    field = _field(_scan(source), "email")
    email = _detector(field, "email")

    assert field["sensitive"] is True
    assert field["exposure"] == "mask"
    assert email["evidence"]["matched"] == ["aaaa@aaaaaaa.aaa", "aaa@aaaaaaa.aaa"]
    assert email["details"]["domains"]["value"] == {
        "distinct": 1,
        "listed": [{"value": "aaaaaaa.aaa", "count": 2}],
        "truncated": False,
    }
    assert "example" not in json.dumps(field)


def test_email_domains_are_hidden_under_hide(tmp_path):
    source = _csv(tmp_path, "email", ["jane@example.com", "bob@other.org"])

    field = _field(_scan(source, exposure={"sensitive_values": "hide"}), "email")

    assert _detector(field, "email")["details"]["domains"]["value"] == {
        "distinct": 2,
        "listed": [],
        "truncated": True,
    }
    assert "example" not in json.dumps(field)


@pytest.mark.parametrize(("mode", "bound"), [("show", 3), ("hide", 3), ("mask", None)])
def test_email_domains_are_limited_beyond_the_tracked_maximum(tmp_path, mode, bound):
    source = _csv(tmp_path, "email", ["a@one.com", "b@two.com", "c@three.com"])

    field = _field(
        _scan(
            source,
            detectors={"email": {"max_tracked_domains": 2}},
            exposure={"sensitive_values": mode},
        ),
        "email",
    )

    expected = {"status": "limited", "reason": "max_tracked", "limit": 2}
    if bound is not None:
        expected["lower_bound"] = bound
    assert _detector(field, "email")["details"]["domains"] == expected


def test_listed_domains_are_truncated(tmp_path):
    source = _csv(tmp_path, "email", ["a@one.com", "b@two.com", "c@two.com"])

    field = _field(
        _scan(
            source,
            detectors={"email": {"max_listed_domains": 1}},
            exposure={"sensitive_values": "show"},
        ),
        "email",
    )

    assert _detector(field, "email")["details"]["domains"]["value"] == {
        "distinct": 2,
        "listed": [{"value": "two.com", "count": 2}],
        "truncated": True,
    }


def test_url_formats_hosts_and_interpretation(tmp_path):
    source = _csv(
        tmp_path,
        "site",
        [
            "https://example.com/a",
            "HTTPS://EXAMPLE.com/b",
            "http://other.org",
            "www.example.com",
        ],
    )

    field = _field(_scan(source), "site")
    url = _detector(field, "url")

    assert url["coverage"]["matched"] == 4
    assert url["formats"] == [
        {"format": "https", "count": 2},
        {"format": "http", "count": 1},
        {"format": "www", "count": 1},
    ]
    assert url["details"]["hosts"]["value"]["listed"][0] == {
        "value": "example.com",
        "count": 2,
    }
    assert field["interpretations"]["primary"] == "url"
    assert field["sensitive"] is False
    assert field["exposure"] is None


def test_url_hosts_are_masked_when_an_email_makes_the_field_sensitive(tmp_path):
    source = _csv(tmp_path, "contact", ["https://example.com", "jane@example.com"])

    field = _field(_scan(source), "contact")

    assert field["sensitive"] is True
    hosts = _detector(field, "url")["details"]["hosts"]["value"]
    assert hosts["listed"] == [{"value": "aaaaaaa.aaa", "count": 1}]


def test_email_and_url_never_match_the_same_value(tmp_path):
    values = [
        "https://jane@example.com",
        "www.jane@example.com",
        "jane@example.com",
        "www.example.com",
        "mailto:jane@example.com",
    ]
    source = _csv(tmp_path, "mixed", values)

    field = _field(_scan(source, exposure={"sensitive_values": "show"}), "mixed")
    email = _detector(field, "email")
    url = _detector(field, "url")

    assert email["evidence"]["matched"] == ["www.jane@example.com", "jane@example.com"]
    assert url["evidence"]["matched"] == ["https://jane@example.com", "www.example.com"]
    assert email["evidence"]["invalid"] == url["evidence"]["invalid"] == []


def test_urls_and_emails_are_neither_numbers_nor_dates(tmp_path):
    source = _csv(
        tmp_path, "value", ["http://192.0.2.1", "a@1.example.com", "www.2026.com"]
    )

    field = _field(_scan(source), "value")

    assert _detector(field, "number")["coverage"]["matched"] == 0
    assert _detector(field, "date")["coverage"]["matched"] == 0
    assert field["technical_type"]["type"] == "text"


def test_email_overlaps_enumeration_and_patterns(tmp_path):
    values = ["jane@example.com", "bob@example.com", "ann@example.com"] * 200
    source = _csv(tmp_path, "email", values)

    field = _field(_scan(source, patterns=[{"id": "at", "regex": r".+@.+"}]), "email")

    candidates = [item["detector"] for item in field["interpretations"]["candidates"]]
    assert candidates == ["email", "enumeration", "pattern:at"]
    assert field["interpretations"]["primary"] is None


def test_email_and_url_can_be_disabled(tmp_path):
    source = _csv(tmp_path, "email", ["jane@example.com"])

    result = _scan(
        source, detectors={"email": {"enabled": False}, "url": {"enabled": False}}
    )
    field = _field(result, "email")

    assert _detector(field, "email") == {
        "id": "email",
        "version": 1,
        "status": "disabled",
    }
    assert "email" not in result["engine"]["detectors"]
    assert field["sensitive"] is False


def test_email_ignores_native_json_values(tmp_path):
    source = _write(tmp_path, json.dumps([{"n": 1}, {"n": True}]), "d.json")

    field = _field(_scan(source), "n")

    assert _detector(field, "email")["status"] == "not_applicable"
    assert _detector(field, "url")["status"] == "not_applicable"
