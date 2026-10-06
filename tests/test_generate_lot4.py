# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Cohort and anomaly contracts for Generate lot 4."""

import csv
import json
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_service import build_generate_plan, generate_datasets

DEFINITION = """\
definition_version: 1
id: lot4
defaults: {seed: 19}
cohorts:
  - id: current
    weight: 3
    formats: {status: {active: Active}}
  - id: legacy
    weight: 1
    formats: {status: {active: ACT}}
entities:
  - id: accounts
    count: 5
    generator: company
    columns:
      - name: account_id
        type: string
        generate: {kind: sequence, prefix: A}
datasets:
  - id: contacts
    rows: 40
    columns:
      - name: contact_id
        type: string
        generate: {kind: sequence, prefix: C}
      - name: account_id
        type: string
        generate: {kind: reference, entity: accounts, field: account_id}
      - name: status
        type: string
        generate: {kind: constant, value: active}
      - name: email
        type: string
        generate: {kind: sequence, prefix: user}
anomaly_profiles:
  - id: dirty
    targets: [contacts]
    operations:
      - {kind: set_missing, column: email, rate: 0.25}
      - {kind: duplicate, column: contact_id, rate: 0.25}
      - {kind: format, column: status, value: lower, rate: 1}
"""


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_clean_cohorts_relations_and_traced_anomalies(tmp_path: Path) -> None:
    source = tmp_path / "definition.yaml"
    source.write_text(DEFINITION, encoding="utf-8")
    clean_dir, dirty_dir = tmp_path / "clean", tmp_path / "dirty"
    generate_datasets(build_generate_plan(source, output_dir=clean_dir))
    result = generate_datasets(build_generate_plan(
        source, output_dir=dirty_dir, anomaly_profile="dirty",
    ))
    clean = _rows(clean_dir / "contacts.csv")
    assert (clean_dir / "contacts.csv").read_bytes() == (dirty_dir / "contacts.csv").read_bytes()
    assert {row["status"] for row in clean} == {"Active", "ACT"}
    assert len({row["account_id"] for row in clean}) == 5
    assert all(row["account_id"] in {"A1", "A2", "A3", "A4", "A5"} for row in clean)
    altered = _rows(dirty_dir / "contacts.dirty.csv")
    changes = _rows(dirty_dir / "contacts.dirty.changes.csv")
    summary = json.loads((dirty_dir / "contacts.dirty.summary.json").read_text(encoding="utf-8"))
    assert len(altered) == 40
    assert all(row["account_id"] == original["account_id"] for row, original in zip(altered, clean))
    assert summary["operations"][0]["requested_rows"] == 10
    assert summary["operations"][0]["applied_rows"] == 10
    assert summary["changed_cells"] == len(changes) == result.anomaly_counts["contacts"]
    assert all(item["before"] != item["after"] and item["cause"] for item in changes)
    assert all(item["profile"] == "dirty" and item["dataset"] == "contacts" for item in changes)
    assert summary["operations"][1]["skipped_rows"] >= 0
    assert not list(dirty_dir.glob(".generate-*"))


def test_anomaly_reproducible_and_impossible_mutation_counted(tmp_path: Path) -> None:
    source = tmp_path / "definition.yaml"
    source.write_text(DEFINITION.replace("column: email, rate: 0.25", "column: email, rate: 0.25")
                      .replace("column: status, value: lower", "column: status, value: strip"),
                      encoding="utf-8")
    outputs = []
    for name in ("first", "second"):
        folder = tmp_path / name
        generate_datasets(build_generate_plan(source, output_dir=folder, anomaly_profile="dirty"))
        outputs.append(folder)
    for filename in ("contacts.csv", "contacts.dirty.csv", "contacts.dirty.changes.csv",
                     "contacts.dirty.summary.json"):
        assert (outputs[0] / filename).read_bytes() == (outputs[1] / filename).read_bytes()
    summary = json.loads((outputs[0] / "contacts.dirty.summary.json").read_text(encoding="utf-8"))
    assert summary["operations"][2]["requested_rows"] == 40
    assert summary["operations"][2]["applied_rows"] == 0
    assert summary["operations"][2]["skipped_rows"] == 40


@pytest.mark.parametrize("before, after, message", [
    ("column: email, rate: 0.25", "column: missing, rate: 0.25", "unknown column"),
    ("rate: 0.25", "rate: .nan", "rate"),
])
def test_invalid_anomaly_fails_before_output(tmp_path: Path, before: str, after: str, message: str) -> None:
    source = tmp_path / "definition.yaml"
    source.write_text(DEFINITION.replace(before, after), encoding="utf-8")
    destination = tmp_path / "out"
    with pytest.raises(ConfigurationError, match=message):
        build_generate_plan(source, output_dir=destination, anomaly_profile="dirty")
    assert not destination.exists()
