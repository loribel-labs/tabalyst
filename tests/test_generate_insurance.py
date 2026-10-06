# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract checks for the packaged Insurance example."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from tabalyst.generate_insurance import FIELDS
from tabalyst.generate_service import build_generate_plan, generate_datasets


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_insurance_branches_combine_and_profile(tmp_path: Path) -> None:
    clean_dir = tmp_path / "clean"
    dirty_dir = tmp_path / "dirty"
    clean_plan = build_generate_plan(example="insurance", rows=3000, output_dir=clean_dir)
    assert clean_plan.rows == {
        "insurance-principal": 2182, "insurance-ontario": 273,
        "insurance-quebec": 545, "insurance-combined": 3000,
    }
    generate_datasets(clean_plan)
    generate_datasets(build_generate_plan(
        example="insurance", rows=3000, anomaly_profile="dirty_realistic",
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
    summary = json.loads((dirty_dir / "insurance-combined.dirty_realistic.summary.json").read_text())
    assert summary["total_rows"] == 3000
    assert summary["events"] > 0
    assert summary["changed_cells"] == summary["events"]


def test_insurance_definition_copies_match() -> None:
    root = Path(__file__).resolve().parents[1]
    assert (root / "examples/generate/input/insurance.yaml").read_bytes() == (
        root / "src/tabalyst/generate_examples/insurance.yaml").read_bytes()
