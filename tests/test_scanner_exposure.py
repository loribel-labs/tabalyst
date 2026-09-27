import json

import pytest

from tabalyst import ConfigurationError
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.detectors import Detector, default_registry
from tabalyst.scanner.exposure import mask

SECRET = {"id": "secret", "regex": r"S-\d{2}", "sensitive": True}


def _write(tmp_path, content: str, name: str = "data.csv"):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8", newline="")
    return path


def _scan(path, registry=None, **settings) -> dict:
    options = {} if registry is None else {"registry": registry}
    config = ScanConfig.model_validate(settings)
    return scan(path, config=config, **options).model_dump(mode="json")


def _field(result: dict, display: str) -> dict:
    [dataset] = result["datasets"]
    [match] = [item for item in dataset["fields"] if item["display"] == display]
    return match


def _detector(field: dict, detector_id: str) -> dict:
    [match] = [item for item in field["detectors"] if item["id"] == detector_id]
    return match


@pytest.mark.parametrize(
    ("value", "masked"),
    [
        ("SECRET-1111", "AAAAAA-9999"),
        ("Québec 42", "Aaaaaa 99"),
        ("aa  bb", "aa  aa"),
        ("東京", "aa"),
    ],
)
def test_mask_keeps_other_characters_and_does_not_compress_runs(value, masked):
    assert mask(value) == masked


def test_patterns_follow_the_registry_in_configuration_order(tmp_path):
    source = _write(tmp_path, "code\nA1\n")

    result = _scan(
        source,
        patterns=[{"id": "second", "regex": "B"}, {"id": "first", "regex": "A1"}],
    )

    ids = [item["id"] for item in _field(result, "code")["detectors"]]
    assert ids[-2:] == ["pattern:second", "pattern:first"]
    assert result["engine"]["detectors"]["pattern:first"] == 1
    assert _field(result, "code")["interpretations"]["primary"] == "pattern:first"


def test_pattern_accepts_native_types_and_caps_input_length(tmp_path):
    source = _write(
        tmp_path, json.dumps([{"n": 1234}, {"n": "1234"}, {"n": "123456"}]), "d.json"
    )

    result = _scan(
        source,
        patterns=[
            {
                "id": "digits",
                "regex": r"\d+",
                "accepts": ["integer"],
                "max_input_length": 4,
            },
            {"id": "short", "regex": r"\d+", "max_input_length": 4},
        ],
    )

    field = _field(result, "n")
    digits = _detector(field, "pattern:digits")["coverage"]
    assert (digits["eligible"], digits["matched"]) == (1, 1)
    short = _detector(field, "pattern:short")["coverage"]
    assert (short["eligible"], short["matched"], short["not_tested"]) == (2, 1, 1)
    assert field["sensitive"] is False
    assert field["exposure"] is None


def test_pattern_colliding_with_a_registered_detector_is_rejected(tmp_path):
    class Colliding(Detector):
        id = "pattern:secret"
        family = "test"

        def classify(self, value):
            return None

    registry = default_registry()
    registry.register(Colliding)
    source = _write(tmp_path, "code\nS-11\n")

    with pytest.raises(ConfigurationError, match="pattern:secret"):
        _scan(source, registry=registry, patterns=[SECRET])


def test_masks_merge_in_frequencies_and_variant_groups(tmp_path):
    source = _write(tmp_path, "code\nS-11\nS-22\nS-11\ns-33\n S-44\nS-44\n")

    field = _field(_scan(source, patterns=[SECRET]), "code")

    assert field["exposure"] == "mask"
    assert field["values"]["cardinality"]["value"] == 5
    frequencies = field["values"]["frequencies"]["value"]
    assert frequencies["distinct"] == 2
    assert frequencies["listed"] == [
        {"value": "A-99", "type": "string", "count": 5},
        {"value": "a-99", "type": "string", "count": 1},
    ]
    groups = field["normalization"]["variant_groups"]["value"]
    # ``S-11``/``s-33`` never share a key; ``S-44`` and `` S-44`` do.
    assert groups["groups"] == 1
    assert groups["listed"][0]["key"] == "a-99"
    assert groups["listed"][0]["variants"] == [
        {"value": " A-99", "count": 1},
        {"value": "A-99", "count": 1},
    ]
    assert _detector(field, "pattern:secret")["evidence"]["matched"] == ["A-99"]
    assert _detector(field, "pattern:secret")["evidence"]["not_matched"] == ["a-99"]


def test_masked_groups_with_equal_masked_keys_merge(tmp_path):
    source = _write(tmp_path, "code\nS-11\n S-11\nS-22\n S-22\n")

    field = _field(_scan(source, patterns=[SECRET]), "code")

    groups = field["normalization"]["variant_groups"]["value"]
    assert groups["groups"] == 1
    [group] = groups["listed"]
    assert (group["key"], group["count"], group["distinct"]) == ("a-99", 4, 2)
    assert group["variants"] == [
        {"value": " A-99", "count": 2},
        {"value": "A-99", "count": 2},
    ]


def test_gate_applies_in_streaming_mode(tmp_path):
    source = _write(tmp_path, "code\nS-11\nS-22\nS-11\n")

    field = _field(
        _scan(
            source,
            patterns=[SECRET],
            limits={"max_distinct_per_field": 1},
        ),
        "code",
    )

    assert field["values"]["frequencies"]["status"] == "limited"
    assert field["values"]["samples"] == {
        "selection": "first_seen",
        "listed": [{"value": "A-99", "type": "string", "count": 3}],
    }
    assert field["values"]["last"]["value"] == "A-99"


def test_hide_keeps_counts_only(tmp_path):
    source = _write(tmp_path, "code\nS-11\n S-11\nS-22\n")

    field = _field(
        _scan(source, patterns=[SECRET], exposure={"sensitive_values": "hide"}),
        "code",
    )

    values = field["values"]
    assert values["first"] is None and values["last"] is None
    assert values["frequencies"]["value"] == {
        "distinct": 2,
        "listed": [],
        "truncated": True,
    }
    assert values["samples"] == {"selection": "all", "listed": []}
    groups = field["normalization"]["variant_groups"]["value"]
    assert groups == {"groups": 1, "listed": [], "truncated": True}
    coverage = _detector(field, "pattern:secret")["coverage"]
    assert coverage["matched"] == 3


def test_show_exposes_sensitive_values(tmp_path):
    source = _write(tmp_path, "code\nS-11\n")

    field = _field(
        _scan(source, patterns=[SECRET], exposure={"sensitive_values": "show"}),
        "code",
    )

    assert (field["sensitive"], field["exposure"]) == (True, "show")
    assert field["values"]["first"]["value"] == "S-11"


def test_field_without_sensitive_match_is_not_masked(tmp_path):
    source = _write(tmp_path, "code\nX-11\n")

    field = _field(_scan(source, patterns=[SECRET]), "code")

    assert field["sensitive"] is False
    assert field["values"]["first"]["value"] == "X-11"


def test_failed_sensitive_detector_makes_the_field_sensitive(tmp_path):
    class Exploding(Detector):
        id = "exploding"
        family = "test"
        sensitive = True

        def classify(self, value):
            if value == "boom":
                raise RuntimeError(value)

    registry = default_registry()
    registry.register(Exploding)
    source = _write(tmp_path, "code\nplain\nboom\n")

    result = _scan(source, registry=registry)

    field = _field(result, "code")
    assert _detector(field, "exploding")["status"] == "failed"
    assert field["exposure"] == "mask"
    assert "plain" not in json.dumps(field)


@pytest.mark.parametrize("exposure", ["mask", "hide"])
def test_statistics_that_are_values_are_withheld(tmp_path, exposure):
    source = _write(tmp_path, "id,birth\n123456789,1980-05-17\n987654321,1975-01-02\n")

    result = _scan(
        source,
        patterns=[
            {"id": "id", "regex": r"\d{9}", "sensitive": True},
            {"id": "birth", "regex": r"\d{4}-\d\d-\d\d", "sensitive": True},
        ],
        exposure={"sensitive_values": exposure},
    )

    text = json.dumps(result)
    assert "123456789" not in text
    assert "1980" not in text
    assert _field(result, "id")["numeric"] == {"status": "disabled"}
    assert _field(result, "birth")["temporal"] == {"status": "disabled"}


def test_show_keeps_statistics(tmp_path):
    source = _write(tmp_path, "id\n123456789\n")

    field = _field(
        _scan(
            source,
            patterns=[{"id": "id", "regex": r"\d{9}", "sensitive": True}],
            exposure={"sensitive_values": "show"},
        ),
        "id",
    )

    assert field["numeric"]["value"]["min"] == 123456789
