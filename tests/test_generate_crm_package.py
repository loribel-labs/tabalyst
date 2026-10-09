# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Verify CRM package parity, account relations, and CLI behavior."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.cli.app import app
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.generate_service import (
    build_generate_plan,
    generate_datasets,
    validate_generate_package,
)

PACKAGE = Path(__file__).resolve().parents[1] / "examples/generate/crm"
BASELINE_CSV_SHA256 = "6530498b8cb9a82b486dbcfcf93fa9c1e858e3f1aba465405629079f9f532a13"


def test_package_matches_v1_scenario_at_same_seed_and_volume(tmp_path: Path) -> None:
    """Keep the frozen v1 CRM scenario byte-for-byte during migration."""
    result = generate_datasets(build_generate_plan(
        PACKAGE, rows=500, seed=42, anomaly_profile="dirty_realistic", output_dir=tmp_path,
    ))
    assert result.row_counts == {"crm-contacts": 500}
    assert len(result.paths) == 4
    clean = tmp_path / "crm-contacts.csv"
    summary = tmp_path / "crm-contacts.dirty_realistic.summary.json"
    assert hashlib.sha256(clean.read_bytes()).hexdigest() == BASELINE_CSV_SHA256
    with clean.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows[0]) == 26
    accounts = Counter(row["company_id"] for row in rows)
    assert len(accounts) == 400
    assert set(accounts.values()) == {1, 2}
    assert 0.30 <= sum(row["opportunity_stage"] != "None" for row in rows) / 500 <= 0.42
    assert all(row["email"] == "" or row["email"].endswith(".example") for row in rows)
    measured = json.loads(summary.read_text(encoding="utf-8"))
    assert measured["events"] == measured["changed_cells"] == 209
    assert sum(item["applied_rows"] for item in measured["operations"]) == 209
    assert (measured["format"], measured["format_version"], measured["package_version"]) == (
        "tabalyst.generate.package", "0.1.0", "0.1.0",
    )


def test_visible_and_packaged_crm_are_identical_and_cli_works(tmp_path: Path) -> None:
    """Ship the same manifest through the local path and packaged example."""
    packaged = Path(__file__).resolve().parents[1] / "src/tabalyst/generate_examples/crm"
    for visible in PACKAGE.rglob("*.yaml"):
        assert visible.read_bytes() == (packaged / visible.relative_to(PACKAGE)).read_bytes()
    runner = CliRunner()
    assert runner.invoke(app, ["generate", str(PACKAGE), "--validate-only"]).exit_code == 0
    assert validate_generate_package(PACKAGE).package_id == "crm"
    created = runner.invoke(app, ["generate", "--example", "crm", "--rows", "4",
                                  "-o", str(tmp_path / "contacts.csv")])
    assert created.exit_code == 0, created.output
    with (tmp_path / "contacts.csv").open(encoding="utf-8", newline="") as stream:
        assert len(list(csv.DictReader(stream))) == 4


def test_package_rejects_invalid_provider_and_protects_schemas(tmp_path: Path) -> None:
    """Validate provider registration and every schema path before publication."""
    package = tmp_path / "crm"
    shutil.copytree(PACKAGE, package)
    schema = package / "schemas/contacts.yaml"
    schema.write_text(schema.read_text(encoding="utf-8").replace(
        "name: common.person", "name: unknown.person", 1), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="PACKAGE_PROVIDER"):
        validate_generate_package(package)
    shutil.copy2(PACKAGE / "schemas/contacts.yaml", schema)
    with pytest.raises(InputError, match="inside its source package"):
        build_generate_plan(package, output_dir=package, force=True)
