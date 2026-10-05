# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect contract: new Scan settings and their validation (lot JI-2).

Design sections 5.2, 5.4 and 5.5: ``json.flatten``, ``json.arrays`` and the
nullable ``errors.policy`` of ``ScanConfig``.
"""

import pytest
from pydantic import ValidationError

from tabalyst.scanner import ScanConfig

pytestmark = pytest.mark.inspect_lot("JI-2")


def _config(**settings) -> ScanConfig:
    return ScanConfig.model_validate(settings)


def test_defaults_keep_todays_behavior():
    config = ScanConfig()

    assert config.json_.flatten.model_dump() == {
        "enabled": True,
        "separator": ".",
        "max_depth": None,
    }
    assert config.json_.arrays.model_dump() == {"mode": "preserve"}
    assert config.errors.policy is None
    assert config.errors.max_locations == 10


def test_new_settings_are_serialized_under_json():
    document = ScanConfig().model_dump(mode="json", by_alias=True)

    assert document["json"]["flatten"] == {
        "enabled": True,
        "separator": ".",
        "max_depth": None,
    }
    assert document["json"]["arrays"] == {"mode": "preserve"}


@pytest.mark.parametrize("separator", [".", "/", "-", ":", "|", "#", "~"])
def test_valid_separators(separator):
    config = _config(json={"flatten": {"separator": separator}})

    assert config.json_.flatten.separator == separator


@pytest.mark.parametrize(
    "separator",
    ["", "..", "ab", "a", "Z", "7", "_", " ", "\t", "\n", "[", "]", '"', "\\", "$"],
)
def test_invalid_separators(separator):
    with pytest.raises(ValidationError):
        _config(json={"flatten": {"separator": separator}})


@pytest.mark.parametrize("depth", [1, 2, 64, 1000])
def test_valid_flatten_depths(depth):
    assert _config(json={"flatten": {"max_depth": depth}}).json_.flatten.max_depth == depth


@pytest.mark.parametrize("depth", [0, -1, 1001, 1.5, "2"])
def test_invalid_flatten_depths(depth):
    with pytest.raises(ValidationError):
        _config(json={"flatten": {"max_depth": depth}})


@pytest.mark.parametrize("mode", ["ignore", "explode", "Preserve", ""])
def test_unsupported_array_modes_are_refused(mode):
    with pytest.raises(ValidationError):
        _config(json={"arrays": {"mode": mode}})


@pytest.mark.parametrize("policy", ["strict", "tolerant", None])
def test_error_policy_values(policy):
    assert _config(errors={"policy": policy}).errors.policy == policy


def test_unknown_flatten_or_array_key_is_refused():
    with pytest.raises(ValidationError):
        _config(json={"flatten": {"depth": 2}})
    with pytest.raises(ValidationError):
        _config(json={"arrays": {"explode": True}})


def test_scan_config_from_layer_accepts_the_inspect_projection():
    from tabalyst.scanner.config import scan_config_from_layer

    layer = {
        "json": {
            "collections": ["$.customers[]"],
            "flatten": {"enabled": True, "separator": "/", "max_depth": 3},
            "arrays": {"mode": "preserve"},
        },
        "errors": {"policy": "tolerant"},
    }

    config = scan_config_from_layer(layer)

    assert config.json_.collections == ["$.customers[]"]
    assert config.json_.flatten.separator == "/"
    assert config.json_.flatten.max_depth == 3
    assert config.errors.policy == "tolerant"
