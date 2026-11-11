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
    "insurance-principal.csv": "eb59985ff105eed321500a0df2304b86dc7cc31d8cc95c28f5c05e752afb5bea",
    "insurance-ontario.csv": "2df6a543b016b6dc0de720827b0d688dbfa4dc9b773aac33635e76b808361066",
    "insurance-quebec.csv": "c9af71aefa79e17056f375e4e88ef71fdd803504679b7fcf4e647d4d68e26e88",
    "insurance-combined.csv": "a012c2832926b85332df9370a3814af4dcb92d8671113a4cf5039038d053afef",
    "insurance-combined.dirty_realistic.csv": "15f140afb381c52c1e0044a931e828833b3a4d96c697da44433845fd2bbb2916",
    "insurance-combined.dirty_realistic.changes.csv": "2ba6dd0b153c67358d632194f0069f64a89d60abf86ec3d2c9307cfac96119bc",
}
V1_SUMMARY_SCENARIO_SHA256 = "a39c75e5bc1b5bb113286154d6c38b3e7e957c136dd7f2e8df8aac9f7c0ee776"


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
    emails = [row["courriel"] for row in combined if row["courriel"]]
    assert len(set(emails)) == len(emails) > 2600
    assert all(email.endswith(".example") for email in emails)
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
    assert summary["events"] == summary["affected_rows"] + 44 == 618
    assert summary["changed_cells"] == summary["events"]
    assert [item["applied_rows"] for item in summary["operations"]] == [
        108, 60, 150, 60, 60, 90, 30, 60,
    ]
    # Emptying an email skips the rows whose email is already missing in the clean file.
    assert [item["skipped_rows"] for item in summary["operations"]] == [12, 0, 0, 0, 0, 0, 0, 0]
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
    assert set(package.manifest["anomaly_profiles"]) == {"dirty_realistic", "dirty_stress", "rule_breaks"}
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


def test_insurance_columns_follow_their_cross_column_rules(tmp_path: Path) -> None:
    """The principal branch (ISO dates) holds no exception to the rules between its columns."""
    from collections import Counter
    from datetime import date
    from statistics import median
    generate_datasets(build_generate_plan(example="insurance", rows=8000, seed=7, output_dir=tmp_path))
    rows = _rows(tmp_path / "insurance-principal.csv")
    as_of = date(2026, 9, 16)
    agencies = {"Montréal": "AG-PR-001", "Sherbrooke": "AG-PR-004", "Toronto": "AG-PR-005"}
    for row in rows:
        start = date.fromisoformat(row["date_debut"])
        if row["type_contrat"] == "voyage":
            end = date.fromisoformat(row["date_fin"])
            assert 3 <= (end - start).days <= 90
            assert row["statut_contrat"] == ("expiré" if end < as_of else "actif")
        if row["date_reclamation"]:
            claim = date.fromisoformat(row["date_reclamation"])
            assert row["date_modification"] >= row["date_reclamation"]
            if (as_of - claim).days > 365:
                assert row["reclamation_status"] in {"fermé", "rejeté"}
            if (as_of - claim).days < 30:
                assert row["reclamation_status"] in {"ouvert", "en_cours"}
        if row["frequence_paiement"] == "mensuelle":
            assert row["mode_paiement"] in {"prélèvement", "carte"}
        if row["ville"] in agencies:
            assert row["agence_code"] == agencies[row["ville"]]

    def age(row: dict[str, str]) -> int:
        return as_of.year - int(row["date_naissance"][:4])

    def premium(low: int, high: int) -> float:
        return median(float(row["prime_annuelle"]) for row in rows
                      if row["type_contrat"] == "auto" and low <= age(row) < high)

    assert premium(18, 25) > 1.4 * premium(30, 60)
    old = [row for row in rows if age(row) >= 70]
    assert sum(not row["courriel"] for row in old) / len(old) > 0.15
    statuses = Counter(row["reclamation_status"] for row in rows if row["date_reclamation"])
    assert statuses["fermé"] > statuses["ouvert"]


def test_insurance_rule_breaks_logs_each_broken_rule_with_its_class(tmp_path: Path) -> None:
    from collections import Counter
    generate_datasets(build_generate_plan(
        example="insurance", rows=20000, seed=7, anomaly_profile="rule_breaks", output_dir=tmp_path,
    ))
    changes = _rows(tmp_path / "insurance-combined.rule_breaks.changes.csv")
    classes = Counter(change["class"] for change in changes)
    assert set(classes) == {
        "end_before_start", "status_vs_end_date", "amount_vs_claim_status",
        "claim_status_without_date", "civilite_vs_sexe", "province_name_vs_code",
        "agency_vs_branch", "customer_under_18", "payment_vs_frequency",
    }
    assert all(count > 0 for count in classes.values())
