"""Where the Scan identity applies: report --scan, projects, resolved hashes.

Companion of ``test_json_inspect_identity.py`` (lot JI-2, design section 10.2).
"""

import json

import pytest
from inspect_helpers import rows, write_json

from tabalyst.projects import StorageLocation, _session, freshness
from tabalyst.projects._publication import publish_scan
from tabalyst.projects._session import inspect_project
from tabalyst.report_service import generate_reports
from tabalyst.scan_reuse import SourceState, compare_source
from tabalyst.scan_service import scan_document
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.config import config_sha256, resolve_config_defaults

pytestmark = pytest.mark.inspect_lot("JI-2")


def publish(tmp_path, text):
    source = tmp_path / "source.csv"
    source.write_text(text, encoding="utf-8", newline="")
    config = ScanConfig()
    location = StorageLocation(tmp_path / "storage")
    return location, publish_scan(source, location, config, workers=1)


def _scan_document(tmp_path, engine_version=None):
    source = write_json(tmp_path, "data.json", rows(3))
    result = scan(source, config=ScanConfig.model_validate({"json": {"collections": ["$[]"]}}))
    document = json.loads(scan_document(result))
    if engine_version is not None:
        document["engine"]["version"] = engine_version
    path = tmp_path / "data.scan.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_resolving_defaults_twice_changes_nothing():
    config = ScanConfig.model_validate({"json": {"flatten": {"enabled": False}}})

    for source_format in ("csv", "json", "jsonl"):
        once = resolve_config_defaults(config, source_format)
        assert resolve_config_defaults(once, source_format) == once
        assert config_sha256(once) == config_sha256(
            resolve_config_defaults(once, source_format)
        )


def test_resolving_does_not_modify_the_given_configuration():
    config = ScanConfig()

    resolve_config_defaults(config, "jsonl")

    assert config.errors.policy is None


def test_comparison_reports_the_hash_it_computed(tmp_path):
    path = write_json(tmp_path, "data.json", rows(2))
    recorded = scan(path, config=ScanConfig.model_validate({"json": {"collections": ["$[]"]}})).source

    check = compare_source(path, recorded)

    assert check.state is SourceState.FRESH
    assert check.sha256 == recorded.sha256


def test_report_from_a_scan_of_another_engine_version_warns_and_reports(tmp_path):
    scan_path = _scan_document(tmp_path, engine_version="0.0.1")

    batch = generate_reports([scan_path], from_scan=True)

    assert batch.succeeded
    (success,) = batch.successes
    assert any("0.0.1" in warning for warning in success.warnings)
    assert (tmp_path / "data.report.html").is_file()


def test_report_from_a_scan_of_this_engine_version_does_not_warn(tmp_path):
    scan_path = _scan_document(tmp_path)

    (success,) = generate_reports([scan_path], from_scan=True).successes

    assert success.warnings == ()


def test_scan_layer_matching_the_document_is_not_stale_whatever_the_policy_spelling(
    tmp_path,
):
    from tabalyst.scan_reuse import check_config, load_scan

    scan_path = _scan_document(tmp_path)
    result = load_scan(scan_path)

    # ``null`` resolves to the recorded ``strict``; a disabled flatten ignores
    # its other settings.
    check_config(scan_path, result, {"errors": {"policy": None}})
    check_config(scan_path, result, {"errors": {"policy": "strict"}})


def test_project_of_another_engine_version_is_not_current(tmp_path, monkeypatch):
    location, outcome = publish(tmp_path, "v\na\nb\n")
    pid = outcome.project.project_id
    assert inspect_project(location, pid).current_ready

    monkeypatch.setattr(_session, "__version__", "9.9.9")
    assessment = inspect_project(location, pid)

    assert assessment.warnings == ("engine_version_changed",)
    assert not assessment.current_ready
    assert assessment.snapshot_ready


def test_project_freshness_reports_the_engine_version(tmp_path, monkeypatch):
    location, outcome = publish(tmp_path, "v\na\nb\n")
    pid = outcome.project.project_id

    current = freshness.project_freshness(location, pid)
    monkeypatch.setattr(freshness, "__version__", "9.9.9")
    other = freshness.project_freshness(location, pid)

    assert current.engine_current
    assert not other.engine_current
    assert other.recorded_engine_version == current.recorded_engine_version
