# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect contract: Scan identity and canonical configuration (lot JI-2).

Design sections 5.5, 5.6 and 10. The identity of a Scan is the triple source
SHA-256, ``config_sha256`` of the resolved configuration and engine version.
"""

import hashlib
import json
import os

import pytest
from inspect_helpers import rows, write_json

import tabalyst
from tabalyst.errors import InputError
from tabalyst.projects.location import StorageLocation
from tabalyst.scan_reuse import SourceState, check_source, compare_source
from tabalyst.scan_service import scan_document
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.config import config_sha256
from tabalyst.shared_scan_service import current_scan

pytestmark = pytest.mark.inspect_lot("JI-2")

ORDERS = {"export": {"version": 1}, "orders": rows(3, status="paid")}


def _config(**settings) -> ScanConfig:
    return ScanConfig.model_validate(settings)


def _identity(config: ScanConfig, sha: str = "0" * 64):
    from tabalyst.scanner.identity import expected_identity

    return expected_identity(sha, config)


def _resolved_sha(config: ScanConfig, source_format: str) -> str:
    from tabalyst.scanner.config import resolve_config_defaults

    return config_sha256(resolve_config_defaults(config, source_format))


def _selected(path: str = "$.orders[]", **json_settings) -> ScanConfig:
    return _config(json={"collections": [path], **json_settings})


@pytest.fixture
def location(tmp_path):
    return StorageLocation(tmp_path / "storage")


@pytest.fixture
def source(tmp_path):
    return write_json(tmp_path, "orders.json", ORDERS)


def _replace_keeping_size_and_time(path, content: str) -> None:
    stat = path.stat()
    path.write_text(content, encoding="utf-8", newline="")
    assert path.stat().st_size == stat.st_size
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))


# CA-21 -------------------------------------------------------------------


def test_same_size_same_time_other_content_is_stale(tmp_path):
    path = write_json(tmp_path, "data.json", rows(2, city="Paris"))
    recorded = scan(path, config=_selected("$[]")).source
    _replace_keeping_size_and_time(
        path, json.dumps(rows(2, city="Lyons"), ensure_ascii=False)
    )

    check = compare_source(path, recorded)

    assert check.state is SourceState.STALE
    assert "SHA-256" in check.reason


def test_touched_source_with_same_content_stays_fresh(tmp_path):
    path = write_json(tmp_path, "data.json", rows(2))
    recorded = scan(path, config=_selected("$[]")).source
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + 10))

    assert compare_source(path, recorded).state is SourceState.FRESH


def test_report_from_scan_document_refuses_same_metadata_other_content(tmp_path):
    path = write_json(tmp_path, "data.json", rows(2, city="Paris"))
    result = scan(path, config=_selected("$[]"))
    scan_path = tmp_path / "data.scan.json"
    scan_path.write_text(scan_document(result), encoding="utf-8")
    _replace_keeping_size_and_time(
        path, json.dumps(rows(2, city="Lyons"), ensure_ascii=False)
    )

    with pytest.raises(InputError, match="Stale scan"):
        check_source(scan_path, result)


def test_cached_scan_is_not_reused_for_same_metadata_other_content(source, location):
    config = _selected()
    first = current_scan(source, config, location=location)
    changed = json.dumps({**ORDERS, "orders": rows(3, status="void")})
    _replace_keeping_size_and_time(source, changed)

    second = current_scan(source, config, location=location)

    assert first.reused is False
    assert second.reused is False
    assert second.result.source.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


# CA-22 -------------------------------------------------------------------


def test_logical_equal_configurations_have_equal_hashes():
    # Order of keys and spelling of a path are not logical differences.
    first = _config(json={"discovery_max_depth": 2, "collections": ['$["orders"][]']})
    second = _config(json={"collections": ["$.orders[]"], "discovery_max_depth": 2})

    assert _resolved_sha(first, "json") == _resolved_sha(second, "json")


def test_equal_paths_are_stored_in_canonical_spelling():
    config = _config(json={"collections": ['$["orders"][]']})

    assert config.json_.collections == ["$.orders[]"]


def test_default_policy_resolves_by_format():
    default = _config()
    strict = _config(errors={"policy": "strict"})
    tolerant = _config(errors={"policy": "tolerant"})

    assert _resolved_sha(default, "csv") == _resolved_sha(strict, "csv")
    assert _resolved_sha(default, "json") == _resolved_sha(strict, "json")
    assert _resolved_sha(default, "jsonl") == _resolved_sha(tolerant, "jsonl")
    assert _resolved_sha(default, "jsonl") != _resolved_sha(strict, "jsonl")


def test_resolved_configuration_never_has_a_null_policy():
    from tabalyst.scanner.config import resolve_config_defaults

    for source_format, expected in (("csv", "strict"), ("json", "strict"), ("jsonl", "tolerant")):
        resolved = resolve_config_defaults(_config(), source_format)
        assert resolved.errors.policy == expected


def test_scan_records_the_resolved_policy(source):
    result = scan(source, config=_selected())

    assert result.config.errors.policy == "strict"
    assert result.config_sha256 == config_sha256(result.config)


def test_unused_flatten_settings_do_not_change_the_hash():
    plain = _selected(flatten={"enabled": False})
    noisy = _selected(flatten={"enabled": False, "separator": "/", "max_depth": 3})
    used = _selected(flatten={"enabled": True, "separator": "/"})

    assert _resolved_sha(plain, "json") == _resolved_sha(noisy, "json")
    assert _resolved_sha(plain, "json") != _resolved_sha(used, "json")


# CA-23 -------------------------------------------------------------------


def test_dates_and_durations_are_outside_the_configuration_hash(source):
    first = scan(source, config=_selected())
    second = scan(source, config=_selected())

    assert first.config_sha256 == second.config_sha256
    assert "started_at" not in first.config.model_dump(mode="json")


# CA-24 -------------------------------------------------------------------


@pytest.mark.parametrize(
    "changed",
    [
        {"json": {"collections": ["$.other[]"]}},
        {"json": {"collections": ["$.orders[]"], "flatten": {"max_depth": 2}}},
        {"json": {"collections": ["$.orders[]"], "flatten": {"separator": "/"}}},
        {"json": {"collections": ["$.orders[]"], "flatten": {"enabled": False}}},
        {"json": {"collections": ["$.orders[]"]}, "errors": {"policy": "tolerant"}},
    ],
)
def test_each_interpretation_setting_changes_the_identity(changed):
    base = _selected()

    assert _identity(_config(**changed)) != _identity(base)


def test_changed_setting_makes_the_cached_scan_ineligible(source, location):
    first = current_scan(source, _selected(), location=location)
    second = current_scan(
        source, _selected(flatten={"max_depth": 2}), location=location
    )

    assert first.reused is False
    assert second.reused is False
    assert second.result.config.json_.flatten.max_depth == 2


# CA-25 -------------------------------------------------------------------


def test_engine_version_is_part_of_the_identity(source):
    from tabalyst.scanner.identity import scan_identity

    result = scan(source, config=_selected())
    identity = scan_identity(result)

    assert identity.engine_version == result.engine.version == tabalyst.__version__
    assert identity.source_sha256 == result.source.sha256
    assert identity.config_sha256 == result.config_sha256
    assert _identity(_selected(), sha=result.source.sha256) == identity


def test_cached_scan_of_another_engine_version_is_not_reused(source, location):
    config = _selected()
    current_scan(source, config, location=location)
    path = location.shared_scan_path(source)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["engine"]["version"] = "0.0.1"
    path.write_text(json.dumps(document), encoding="utf-8")

    result = current_scan(source, config, location=location)

    assert result.reused is False
    assert result.result.engine.version == tabalyst.__version__


# CA-26 -------------------------------------------------------------------


def test_equal_triple_reuses_the_cached_scan(source, location):
    config = _selected()
    first = current_scan(source, config, location=location)
    before = location.shared_scan_path(source).read_bytes()

    second = current_scan(source, config, location=location)

    assert (first.reused, second.reused) == (False, True)
    assert location.shared_scan_path(source).read_bytes() == before


def test_identity_compares_fields_not_a_concatenation():
    from tabalyst.scanner.identity import ScanIdentity

    left = ScanIdentity("ab", "c", "0.1")
    right = ScanIdentity("a", "bc", "0.1")

    assert left != right
