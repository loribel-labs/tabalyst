# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""What produced the patterns of a Scan is part of its identity and of the key of the
validation (Patterns lot P7, FR-020, design 18.12 and 20.9)."""

from __future__ import annotations

from planner_helpers import scan_csv
from scan_helpers import write_text

from tabalyst.scan_reuse import engine_warning
from tabalyst.scanner import ScanConfig, patterninfer, scan
from tabalyst.scanner.identity import expected_identity, scan_identity
from tabalyst.scanner.planner import plan_analyses
from tabalyst.scanner.secondpass.document import analysis_key

ROWS = [f"AK-{n:04d}" for n in range(60)]


def _key(result):
    plan = plan_analyses(result, forced=True)
    [candidate] = [c for c in plan.candidates if c.analyzer == "pattern_validation"]
    return analysis_key(plan.base, candidate), candidate.parameters


def test_a_scan_carries_the_versions_of_the_discovery_in_its_identity(tmp_path):
    result = scan_csv(tmp_path, "code", ROWS)

    assert scan_identity(result).patterns == patterninfer.discovery_versions()
    wanted = expected_identity(result.source.sha256, result.config, source_format="csv")
    assert wanted == scan_identity(result)


def test_a_scan_without_discovery_is_not_expected_to_have_one(tmp_path):
    source = write_text(tmp_path, "data.csv", "code\n" + "\n".join(ROWS) + "\n")
    config = ScanConfig.model_validate({"pattern_inference": {"enabled": False}})
    result = scan(source, config=config)

    assert scan_identity(result).patterns is None
    wanted = expected_identity(result.source.sha256, config, source_format="csv")
    assert wanted == scan_identity(result)


def test_another_version_of_the_discovery_is_not_the_identity_of_the_scan(tmp_path, monkeypatch):
    result = scan_csv(tmp_path, "code", ROWS)
    before = expected_identity(result.source.sha256, result.config, source_format="csv")
    assert before == scan_identity(result)

    monkeypatch.setattr(patterninfer, "ALGORITHM_VERSION", patterninfer.ALGORITHM_VERSION + 1)

    assert expected_identity(result.source.sha256, result.config, source_format="csv") != before
    warning = engine_warning(result)
    assert warning is not None and "algorithm" in warning


def test_the_validation_is_another_analysis_when_the_discovery_changes(tmp_path):
    result = scan_csv(tmp_path, "code", ROWS)
    key, parameters = _key(result)
    assert parameters["algorithm_version"] == patterninfer.ALGORITHM_VERSION
    assert parameters["grammar_version"] == patterninfer.GRAMMAR_VERSION
    assert len(str(parameters["discovery_sha256"])) == 64

    other = scan_csv(tmp_path, "code", ROWS, pattern_inference={"max_patterns": 64})
    assert _key(other)[0] != key
