# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for Insurance V2 relational and flattened outputs (Lot 9, contract section 8)."""

from __future__ import annotations

import csv
import json
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_population import (
    RELATIONAL_CLIENTS_FIELDS,
    RELATIONAL_CONTRATS_FIELDS,
    RELATIONAL_PAIEMENTS_FIELDS,
    RELATIONAL_RECLAMATIONS_FIELDS,
)
from tabalyst.generate_service import build_generate_plan, generate_datasets

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_csv_headers(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        return next(reader)


def test_relational_generation_creates_four_tables_and_truth(tmp_path: Path) -> None:
    """Relational generation writes 4 CSV tables and 4 truth suites (16 artifact files)."""
    out = tmp_path / "relational_out"
    plan = build_generate_plan(
        PACKAGE,
        relational=True,
        rows=500,
        seed=42,
        output_dir=out,
    )
    result = generate_datasets(plan)

    expected_tables = ["clients", "contrats", "reclamations", "paiements"]
    assert set(result.row_counts.keys()) == set(expected_tables)
    assert result.row_counts["contrats"] == 500
    assert result.row_counts["clients"] > 0
    assert result.row_counts["clients"] < 500  # Multi-contract customers exist

    # Verify all 4 tables exist with their headers
    assert _read_csv_headers(out / "clients.csv") == list(RELATIONAL_CLIENTS_FIELDS)
    assert _read_csv_headers(out / "contrats.csv") == list(RELATIONAL_CONTRATS_FIELDS)
    assert _read_csv_headers(out / "reclamations.csv") == list(RELATIONAL_RECLAMATIONS_FIELDS)
    assert _read_csv_headers(out / "paiements.csv") == list(RELATIONAL_PAIEMENTS_FIELDS)

    # Verify truth artifacts exist for each table
    for tbl in expected_tables:
        assert (out / f"{tbl}.csv").is_file()
        assert (out / f"{tbl}.truth.csv").is_file()
        assert (out / f"{tbl}.rules.json").is_file()
        assert (out / f"{tbl}.metrics.json").is_file()
        assert (out / f"{tbl}.manifest.json").is_file()

        manifest = json.loads((out / f"{tbl}.manifest.json").read_text(encoding="utf-8"))
        assert manifest["dataset"] == tbl
        assert manifest["rows"] == result.row_counts[tbl]
        assert len(manifest["files"]) == 4  # table.csv, truth.csv, rules.json, metrics.json


def test_relational_cardinalities_and_referential_integrity(tmp_path: Path) -> None:
    """Validate referential integrity and G01-G08 cardinalities across the 4 relational tables."""
    out = tmp_path / "cardinality_out"
    plan = build_generate_plan(
        PACKAGE,
        relational=True,
        rows=1000,
        seed=123,
        output_dir=out,
    )
    generate_datasets(plan)

    clients = _read_csv_rows(out / "clients.csv")
    contrats = _read_csv_rows(out / "contrats.csv")
    reclamations = _read_csv_rows(out / "reclamations.csv")
    paiements = _read_csv_rows(out / "paiements.csv")

    client_ids = {c["id_client"] for c in clients}
    contrat_ids = {ct["id_contrat"] for ct in contrats}
    reclamation_ids = {r["id_reclamation"] for r in reclamations}

    # Integrity: All contracts reference an existing client
    for ct in contrats:
        assert ct["id_client"] in client_ids

    # Integrity: All claims reference an existing contract
    for r in reclamations:
        assert r["id_contrat"] in contrat_ids

    # Integrity: All payments reference an existing claim and contract
    for p in paiements:
        assert p["id_reclamation"] in reclamation_ids
        assert p["id_contrat"] in contrat_ids

    # G01: Multi-contract customers exist (~28% multi-contracts)
    contracts_per_client: dict[str, int] = {}
    for ct in contrats:
        contracts_per_client[ct["id_client"]] = contracts_per_client.get(ct["id_client"], 0) + 1
    multi_contract_clients = sum(1 for count in contracts_per_client.values() if count > 1)
    ratio = multi_contract_clients / len(clients)
    assert 0.20 <= ratio <= 0.40

    # G03: Households group customers
    households: dict[str, list[str]] = {}
    for c in clients:
        households.setdefault(c["id_menage"], []).append(c["id_client"])
    multi_client_households = sum(1 for cl in households.values() if len(cl) > 1)
    assert multi_client_households > 0

    # G08: Installment disbursement payments sum to claim indemnity amount
    payments_by_claim: dict[str, float] = {}
    for p in paiements:
        amt = float(p["montant"])
        payments_by_claim[p["id_reclamation"]] = payments_by_claim.get(p["id_reclamation"], 0.0) + amt

    for r in reclamations:
        indemnite = float(r["montant_indemnise"] or 0.0)
        if indemnite > 0.0:
            total_paid = payments_by_claim.get(r["id_reclamation"], 0.0)
            assert abs(total_paid - indemnite) < 0.01


def test_relational_truth_lines_g09_g10_and_m22(tmp_path: Path) -> None:
    """Validate G09, G10 relational truth lines in clients and M22 orphan claim in reclamations."""
    out = tmp_path / "truth_out"
    # dirty_realistic profile activates M22 (1 orphan claim reference) without 100k min_rows floor
    plan = build_generate_plan(
        PACKAGE,
        relational=True,
        rows=1000,
        seed=42,
        output_dir=out,
        anomaly_profile="dirty_realistic",
    )
    generate_datasets(plan)

    client_truth = _read_csv_rows(out / "clients.dirty_realistic.truth.csv")
    reclamation_truth = _read_csv_rows(out / "reclamations.dirty_realistic.truth.csv")

    # G09 and G10 lines exist in clients.truth.csv
    g09_lines = [r for r in client_truth if r["scenario_id"] == "G09"]
    g10_lines = [r for r in client_truth if r["scenario_id"] == "G10"]

    assert len(g09_lines) > 0
    for line in g09_lines:
        assert line["kind"] == "relational"
        assert line["category"] == "valid_atypical"
        assert line["column"] == "id_menage"
        assert line["group_id"].startswith("G09-")

    assert len(g10_lines) > 0
    for line in g10_lines:
        assert line["kind"] == "relational"
        assert line["category"] == "valid_atypical"
        assert line["column"] == "nom"
        assert line["group_id"].startswith("G10-")

    # M22 lines exist in reclamations.truth.csv (orphan claim pointing to non-existent contract)
    m22_violations = [r for r in reclamation_truth if r["rule_id"] == "M22" and r["kind"] == "rule_violation"]
    m22_relational = [r for r in reclamation_truth if r["rule_id"] == "M22" and r["kind"] == "relational"]
    assert len(m22_violations) == 1
    assert len(m22_relational) == 1
    assert m22_violations[0]["column"] == "id_contrat"


def test_flattened_insurance_profiles(tmp_path: Path) -> None:
    """Validate flattened, flattened-extended and flattened-complete output profiles."""
    out = tmp_path / "flattened_out"

    # 1. Base flattened (34 columns on combined)
    plan_base = build_generate_plan(
        PACKAGE,
        output_profile="flattened",
        rows=200,
        seed=42,
        output_dir=out / "base",
    )
    generate_datasets(plan_base)
    base_headers = _read_csv_headers(out / "base" / "insurance-combined.csv")
    assert len(base_headers) == 34
    assert base_headers[0] == "id_client"
    assert "id_contrat" in base_headers
    assert "filiale" in base_headers

    # 2. Flattened extended (44 columns on combined)
    plan_ext = build_generate_plan(
        PACKAGE,
        output_profile="flattened-extended",
        rows=200,
        seed=42,
        output_dir=out / "ext",
    )
    generate_datasets(plan_ext)
    ext_headers = _read_csv_headers(out / "ext" / "insurance-combined.csv")
    assert len(ext_headers) == 44
    assert "date_sinistre" in ext_headers
    assert "courtier_id" in ext_headers

    # 3. Flattened complete (48 columns on combined)
    plan_cmp = build_generate_plan(
        PACKAGE,
        output_profile="flattened-complete",
        rows=200,
        seed=42,
        output_dir=out / "cmp",
    )
    generate_datasets(plan_cmp)
    cmp_headers = _read_csv_headers(out / "cmp" / "insurance-combined.csv")
    assert len(cmp_headers) == 48
    assert "taux_remboursement" in cmp_headers
    assert "segment_client" in cmp_headers


def test_relational_validation_refusals(tmp_path: Path) -> None:
    """Refuse --relational with -o file target or on non-insurance packages."""
    # Refusal with -o
    with pytest.raises(ConfigurationError, match="--relational generates multiple tables; use -d."):
        build_generate_plan(PACKAGE, relational=True, output=tmp_path / "single.csv")

    # Refusal with non-insurance package (e.g. computer)
    computer_pkg = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))
    with pytest.raises(ConfigurationError, match="--relational applies to the Insurance package only."):
        build_generate_plan(computer_pkg, relational=True, output_dir=tmp_path / "rel_computer")


def test_relational_atomic_publication_and_determinism(tmp_path: Path) -> None:
    """Atomic publication leaves no temporary files and produces byte-identical files for same seed."""
    out1 = tmp_path / "run1"
    out2 = tmp_path / "run2"

    plan1 = build_generate_plan(PACKAGE, relational=True, rows=300, seed=999, output_dir=out1)
    plan2 = build_generate_plan(PACKAGE, relational=True, rows=300, seed=999, output_dir=out2)

    generate_datasets(plan1)
    generate_datasets(plan2)

    # Check no temp or backup files remain
    for p in out1.iterdir():
        assert not p.name.startswith(".")
        assert not p.name.endswith(".tmp")
        assert not p.name.endswith(".bak")

    # Check byte-identical determinism
    for name in ["clients.csv", "contrats.csv", "reclamations.csv", "paiements.csv"]:
        bytes1 = (out1 / name).read_bytes()
        bytes2 = (out2 / name).read_bytes()
        assert bytes1 == bytes2
