# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect contract: the document, its zones and its ``config`` (lot JI-5).

Design sections 4 and 5: layout and order of the zones, defaults of ``config``,
validation without coercion, and the projection onto the ``ScanConfig`` layer.
"""

import copy
import json

import pytest
from inspect_helpers import inspect_document, rows, write_json, write_jsonl
from pydantic import ValidationError

import tabalyst
from tabalyst.scanner.config import config_sha256, scan_config_from_layer

pytestmark = pytest.mark.inspect_lot("JI-5")

ZONES = [
    "format",
    "format_version",
    "format_revision",
    "inspect",
    "source",
    "detection",
    "warnings",
    "config",
]

DEFAULT_CONFIG = {
    "flatten": {"enabled": True, "separator": ".", "max_depth": None},
    "arrays": {"mode": "preserve"},
    "errors": {"policy": "strict"},
}


@pytest.fixture
def document(tmp_path):
    source = write_json(tmp_path, "orders.json", {"export": {"v": 1}, "orders": rows(3)})
    return inspect_document(source)


def _models():
    from tabalyst.inspector.models import InspectConfig, InspectDocument

    return InspectDocument, InspectConfig


def test_zones_and_their_order(document):
    assert list(document) == ZONES
    assert document["format"] == "tabalyst.inspect"
    assert document["format_version"] == "0.2.0"
    assert document["format_revision"] == 1
    assert list(document["inspect"]) == ["kind", "tabalyst_version", "generated_at", "note"]
    assert document["inspect"]["kind"] == "json"
    assert document["inspect"]["tabalyst_version"] == tabalyst.__version__
    assert "config" in document["inspect"]["note"]


def test_source_zone(document):
    source = document["source"]

    assert list(source) == ["name", "format", "size_bytes", "sha256"]
    assert source["name"] == "orders.json"
    assert source["format"] == "json"


def test_no_absolute_path_is_written(tmp_path):
    source = write_json(tmp_path, "orders.json", rows(2))

    text = json.dumps(inspect_document(source))

    assert str(tmp_path) not in text
    assert tmp_path.name not in text


def test_config_defaults_and_selection(document):
    assert document["config"] == {
        "structure": {"dataset_path": "$.orders[]"},
        **DEFAULT_CONFIG,
    }


def test_jsonl_config_is_tolerant_and_names_the_implicit_dataset(tmp_path):
    source = write_jsonl(tmp_path, "events.jsonl", rows(2))

    document = inspect_document(source)

    assert document["source"]["format"] == "jsonl"
    assert document["config"]["errors"] == {"policy": "tolerant"}
    assert document["config"]["structure"] == {"dataset_path": "$[]"}


def test_config_is_seeded_from_the_layers_below_the_file(tmp_path):
    source = write_json(tmp_path, "orders.json", rows(2))

    document = inspect_document(
        source,
        json={"flatten": {"separator": "/", "max_depth": 3}},
        errors={"policy": "tolerant"},
    )

    assert document["config"]["flatten"] == {
        "enabled": True,
        "separator": "/",
        "max_depth": 3,
    }
    assert document["config"]["errors"] == {"policy": "tolerant"}


def test_document_round_trips_through_the_model(document):
    InspectDocument, _ = _models()

    assert InspectDocument.model_validate(document).model_dump(mode="json") == document


def test_models_refuse_unknown_keys(document):
    InspectDocument, _ = _models()
    extra = copy.deepcopy(document)
    extra["config"]["flatten"]["sepator"] = "/"
    with pytest.raises(ValidationError):
        InspectDocument.model_validate(extra)

    extra = copy.deepcopy(document)
    extra["surprise"] = 1
    with pytest.raises(ValidationError):
        InspectDocument.model_validate(extra)


@pytest.mark.parametrize(
    "config",
    [
        {"flatten": {"enabled": "true"}},
        {"flatten": {"enabled": 1}},
        {"flatten": {"separator": ".."}},
        {"flatten": {"separator": "a"}},
        {"flatten": {"separator": "_"}},
        {"flatten": {"max_depth": 0}},
        {"flatten": {"max_depth": "3"}},
        {"flatten": {"max_depth": 1001}},
        {"arrays": {"mode": "explode"}},
        {"arrays": {"mode": "ignore"}},
        {"errors": {"policy": "lenient"}},
        {"structure": {"dataset_path": 3}},
        {"structure": {"dataset_path": "customers"}},
        {"structure": {"dataset_path": "$.customers"}},
        {"structure": {"dataset_path": ["$.a[]"]}},
        {"structure": {"record_type": "object"}},
        {"types": {"mixed_types": "preserve"}},
        {"limits": {"max_depth": 3}},
    ],
)
def test_invalid_config_values_are_refused_without_coercion(config):
    _, InspectConfig = _models()

    with pytest.raises(ValidationError):
        InspectConfig.model_validate(config)


def test_omitted_keys_default_and_an_empty_config_is_valid():
    _, InspectConfig = _models()

    config = InspectConfig.model_validate({})

    assert config.model_dump(mode="json") == {
        "structure": {"dataset_path": None},
        "flatten": {"enabled": True, "separator": ".", "max_depth": None},
        "arrays": {"mode": "preserve"},
        "errors": {"policy": None},
    }


def test_paths_are_accepted_in_any_spelling():
    _, InspectConfig = _models()

    config = InspectConfig.model_validate({"structure": {"dataset_path": '$["orders"][]'}})

    assert config.structure.dataset_path == "$.orders[]"


def test_projection_onto_a_scan_layer():
    _, InspectConfig = _models()
    config = InspectConfig.model_validate(
        {
            "structure": {"dataset_path": "$.customers[]"},
            "flatten": {"enabled": True, "separator": "/", "max_depth": None},
            "arrays": {"mode": "preserve"},
            "errors": {"policy": "tolerant"},
        }
    )

    assert config.to_scan_layer() == {
        "json": {
            "collections": ["$.customers[]"],
            "flatten": {"enabled": True, "separator": "/", "max_depth": None},
            "arrays": {"mode": "preserve"},
        },
        "errors": {"policy": "tolerant"},
    }


def test_projection_holds_only_the_keys_that_are_present():
    _, InspectConfig = _models()

    assert InspectConfig.model_validate({}).to_scan_layer() == {}
    layer = InspectConfig.model_validate(
        {"structure": {"dataset_path": None}, "flatten": {"separator": "/"}}
    ).to_scan_layer()
    # An undecided path never selects the automatic discovery mode.
    assert layer == {"json": {"flatten": {"separator": "/"}}}


def test_a_present_null_is_a_choice_for_the_policy_and_the_depth():
    _, InspectConfig = _models()

    layer = InspectConfig.model_validate(
        {"flatten": {"max_depth": None}, "errors": {"policy": None}}
    ).to_scan_layer()

    assert layer == {
        "json": {"flatten": {"max_depth": None}},
        "errors": {"policy": None},
    }


def test_dates_and_warnings_do_not_change_the_configuration_hash(document):
    InspectDocument, _ = _models()
    changed = copy.deepcopy(document)
    changed["inspect"]["generated_at"] = "2001-01-01T00:00:00Z"
    changed["warnings"].append({"code": "candidate_not_eligible", "level": "info", "message": "x"})

    def sha(doc):
        layer = InspectDocument.model_validate(doc).config.to_scan_layer()
        return config_sha256(scan_config_from_layer(layer))

    assert sha(changed) == sha(document)
