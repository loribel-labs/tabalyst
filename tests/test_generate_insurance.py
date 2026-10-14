# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract checks for the packaged Insurance example."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_insurance import FIELDS
from tabalyst.generate_package import (
    MAX_CELLS,
    MAX_COLUMNS,
    MAX_CSV_BYTES,
    MAX_DATASETS,
    MAX_PROFILES,
    MAX_ROWS,
    MAX_TABLES,
    MAX_YAML_BYTES,
    load_generate_package,
)
from tabalyst.generate_service import (
    build_generate_plan,
    generate_datasets,
    validate_generate_package,
)

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))
V1_SHA256 = {
    "insurance-principal.csv": "ae5323a64a906d0937cd54a787111e012b51d63cab99af67297c13c24d8ad3dc",
    "insurance-ontario.csv": "69252bca2b365c06213a94a01c840ae37406219834a995ffe24d8eb7059bd545",
    "insurance-quebec.csv": "4ddd34572552035106d296168692652d65a69f1582dec66bdb523402b35e390e",
    "insurance-combined.csv": "78273be501d01ee2f5bbf4e35b1a5fc0915b972e89d4913c986ec1009f16a5f8",
    "insurance-combined.dirty_realistic.csv": "869b629b7f9695ddbe14d52861422c1a9c99d90a8d614d2ff82653777107a7ff",
    "insurance-combined.dirty_realistic.changes.csv": "3c80139ef99efdbd97df9d2d848aaca9042ccf38b67270871d23e7031ef2f2f7",
}
V1_SUMMARY_SCENARIO_SHA256 = "5fe2a0293fb228bb7aacec663d02bcaa1d4414065a7631cd44162ad93a7b6170"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_insurance_branches_combine_and_profile(tmp_path: Path) -> None:
    clean_dir = tmp_path / "clean"
    dirty_dir = tmp_path / "dirty"
    clean_plan = build_generate_plan(example="insurance", rows=3000, seed=42, output_dir=clean_dir)
    assert clean_plan.rows == {
        "insurance-principal": 2182, "insurance-ontario": 273,
        "insurance-quebec": 545, "insurance-combined": 3000,
    }
    generate_datasets(clean_plan)
    generate_datasets(build_generate_plan(
        example="insurance", rows=3000, seed=42, anomaly_profile="dirty_realistic",
        output_dir=dirty_dir,
    ))
    combined = _rows(clean_dir / "insurance-combined.csv")
    assert len(combined) == 3000
    assert list(combined[0]) == [*FIELDS, "filiale"]
    assert [row["filiale"] for row in combined] == (
        ["principal"] * 2182 + ["ontario"] * 273 + ["quebec"] * 545
    )
    assert len({row["id_client"] for row in combined}) == 3000
    assert len({row["id_contrat"] for row in combined}) == 3000
    assert len({row["courriel"] for row in combined}) == 3000
    assert all(row["courriel"].endswith(".example") for row in combined)
    for branch, pattern in (
        ("principal", r"\d{4}-\d{2}-\d{2}"),
        ("ontario", r"\d{2}-\d{2}-\d{4}"),
        ("quebec", r"\d{2}-\d{2}-\d{4}"),
    ):
        rows = _rows(clean_dir / f"insurance-{branch}.csv")
        assert all(re.fullmatch(pattern, row["date_naissance"]) for row in rows)
        assert all(row["pays_code"] == "CA" for row in rows)
        assert all(row["date_reclamation"] or not row["montant_reclamation"]
                   for row in rows)
        assert all(row["agence_code"].startswith({
            "principal": "AG-PR-", "ontario": "AG-ON-", "quebec": "AG-QC-",
        }[branch]) for row in rows)
        assert (clean_dir / f"insurance-{branch}.csv").read_bytes() == (
            dirty_dir / f"insurance-{branch}.csv").read_bytes()
    assert (clean_dir / "insurance-combined.csv").read_bytes() == (
        dirty_dir / "insurance-combined.csv").read_bytes()
    assert len(list(dirty_dir.iterdir())) == 7
    for name, digest in V1_SHA256.items():
        assert hashlib.sha256((dirty_dir / name).read_bytes()).hexdigest() == digest
    summary = json.loads((dirty_dir / "insurance-combined.dirty_realistic.summary.json").read_text())
    assert summary["total_rows"] == 3000
    assert summary["events"] == summary["affected_rows"] + 47 == 630
    assert summary["changed_cells"] == summary["events"]
    assert [item["applied_rows"] for item in summary["operations"]] == [
        120, 60, 150, 60, 60, 90, 30, 60,
    ]
    assert all(item["skipped_rows"] == 0 for item in summary["operations"])
    assert summary["format"] == "tabalyst.generate.package"
    assert summary["format_version"] == summary["package_version"] == "0.1.0"
    scenario = {key: value for key, value in summary.items()
                if key not in {"format", "format_version", "package_version", "tabalyst_version"}}
    scenario_digest = hashlib.sha256(json.dumps(
        scenario, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()).hexdigest()
    assert scenario_digest == V1_SUMMARY_SCENARIO_SHA256


def test_insurance_package_quotas(tmp_path: Path) -> None:
    assert validate_generate_package(PACKAGE).package_id == "insurance"
    package = load_generate_package(PACKAGE)
    assert len(package.tables) == 7 < MAX_TABLES
    assert len(package.manifest["datasets"]) == 4 < MAX_DATASETS
    assert sum(table.file.stat().st_size for table in package.tables.values()) < MAX_CSV_BYTES
    assert sum(len(table.rows) * len(table.columns) for table in package.tables.values()) < MAX_CELLS
    assert all(path.stat().st_size <= MAX_YAML_BYTES for path in PACKAGE.rglob("*.yaml"))
    assert len(FIELDS) == 33 < MAX_COLUMNS
    assert set(package.manifest["anomaly_profiles"]) == {"dirty_realistic", "dirty_stress"}
    assert len(package.manifest["anomaly_profiles"]) < MAX_PROFILES
    plan = build_generate_plan(example="insurance", output_dir=tmp_path,
                               anomaly_profile="dirty_realistic")
    assert plan.rows == {"insurance-principal": 200000, "insurance-ontario": 25000,
                         "insurance-quebec": 50000, "insurance-combined": 275000}
    assert len(plan.artifacts) == 7
    assert plan.rows["insurance-combined"] < MAX_ROWS


def test_invalid_insurance_resource_fails_before_output(tmp_path: Path) -> None:
    package = tmp_path / "insurance"
    shutil.copytree(PACKAGE, package)
    resource = package / "data/branch_contract_weights.csv"
    lines = resource.read_text(encoding="utf-8").splitlines()
    cells = lines[1].split(",")
    cells[-1] = "0"
    lines[1] = ",".join(cells)
    resource.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Invalid rows or weights"):
        build_generate_plan(package, output_dir=tmp_path / "output")
    assert not (tmp_path / "output").exists()
