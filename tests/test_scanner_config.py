# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import pytest

from tabalyst.scanner import ScanConfig
from tabalyst.scanner.config import HARD_CAPS, config_sha256


def test_defaults_serialize_with_the_documented_section_names():
    document = ScanConfig().model_dump(mode="json")

    assert list(document) == [
        "csv",
        "json",
        "excel",
        "errors",
        "values",
        "normalization",
        "limits",
        "records",
        "types",
        "classification",
        "detection",
        "detectors",
        "patterns",
        "exposure",
        "pattern_inference",
        "observations",
        "random_seed",
    ]
    assert document["json"] == {
        "collections": None,
        "discovery_max_depth": 3,
        "flatten": {"enabled": True, "separator": ".", "max_depth": None},
        "arrays": {"mode": "preserve"},
    }
    assert ScanConfig.model_validate(document) == ScanConfig()


def test_fingerprint_changes_with_the_effective_configuration():
    default = config_sha256(ScanConfig())

    assert default == config_sha256(ScanConfig.model_validate({}))
    assert default != config_sha256(ScanConfig.model_validate({"random_seed": 1}))


@pytest.mark.parametrize("name", sorted(HARD_CAPS))
def test_every_limit_accepts_its_cap_and_rejects_more(name):
    limits = {name: HARD_CAPS[name]}
    if name == "max_distinct_per_field":
        limits["max_tracked_values"] = HARD_CAPS["max_tracked_values"]

    config = ScanConfig.model_validate({"limits": limits})
    assert getattr(config.limits, name) == HARD_CAPS[name]
    with pytest.raises(ValueError):
        ScanConfig.model_validate({"limits": {name: HARD_CAPS[name] + 1}})


@pytest.mark.parametrize(
    "settings",
    [
        {"values": {"null_markers": [""]}},
        {"values": {"null_markers": [" NULL "]}},
        {"values": {"missing": ["null", "null"]}},
        {"values": {"missing": ["unknown"]}},
        {"errors": {"policy": "lenient"}},
        {"json": {"collections": ["customers[]"]}},
        {"json": {"collections": ["$.a[", "$"]}},
        {"json": {"collections": ["$[]", "$[]"]}},
        {"json": {"collections": ["$"]}},
        {"json": {"collections": ["$.customers"]}},
        {"json_": {}},
        {"csv": {"delimiter": ";;"}},
        {"detectors": {"date": {"ambiguous_order": "DMY", "orders": ["YMD"]}}},
        {"patterns": [{"id": "bad id", "regex": "x"}]},
        {"patterns": [{"id": "x", "regex": "x", "max_input_length": 10_001}]},
        {"patterns": [{"id": f"p{index}", "regex": "x"} for index in range(201)]},
        {"exposure": {"sensitive_values": "blur"}},
        {"limits": {"max_fields": 0}},
    ],
)
def test_invalid_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        ScanConfig.model_validate(settings)


def test_valid_collections_and_patterns_are_kept():
    config = ScanConfig.model_validate(
        {
            "json": {"collections": ["$.customers[].orders[]", '$["a.b"][]']},
            "patterns": [{"id": "customer_number", "regex": r"C-\d{4}"}],
        }
    )

    assert config.json_.collections == ["$.customers[].orders[]", '$["a.b"][]']
    assert config.patterns[0].accepts == ["string"]


def test_the_sample_size_defaults_to_ten_thousand_beside_the_tracking_limit():
    limits = ScanConfig().limits

    assert limits.max_distinct_per_field == 100_000
    assert limits.max_samples == 10_000


def test_the_sample_size_is_capped():
    ScanConfig.model_validate({"limits": {"max_samples": HARD_CAPS["max_samples"]}})

    with pytest.raises(ValueError, match="max_samples"):
        ScanConfig.model_validate(
            {"limits": {"max_samples": HARD_CAPS["max_samples"] + 1}}
        )


def test_an_explicit_sample_size_above_the_tracking_limit_is_refused():
    with pytest.raises(ValueError, match="max_samples cannot exceed"):
        ScanConfig.model_validate(
            {"limits": {"max_distinct_per_field": 500, "max_samples": 501}}
        )


def test_a_sample_size_left_unset_follows_a_lower_tracking_limit():
    lowered = ScanConfig.model_validate({"limits": {"max_distinct_per_field": 500}})
    raised = ScanConfig.model_validate({"limits": {"max_distinct_per_field": 200_000}})
    explicit = ScanConfig.model_validate(
        {"limits": {"max_distinct_per_field": 500, "max_samples": 20}}
    )

    assert lowered.limits.max_samples == 500
    assert raised.limits.max_samples == 10_000
    assert explicit.limits.max_samples == 20
    # The document records the effective size, and so does its fingerprint.
    spelled = ScanConfig.model_validate(
        {"limits": {"max_distinct_per_field": 500, "max_samples": 500}}
    )
    assert config_sha256(lowered) == config_sha256(spelled)
