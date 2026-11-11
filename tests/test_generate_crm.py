# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract checks for the packaged CRM demonstration."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

from tabalyst.generate_service import build_generate_plan, generate_datasets


def test_crm_example_accounts_and_profile(tmp_path: Path) -> None:
    clean_dir = tmp_path / "clean"
    dirty_dir = tmp_path / "dirty"
    generate_datasets(build_generate_plan(example="crm", rows=500, output_dir=clean_dir))
    generate_datasets(build_generate_plan(
        example="crm", rows=500, anomaly_profile="dirty_realistic",
        output_dir=dirty_dir,
    ))
    clean = clean_dir / "crm-contacts.csv"
    assert clean.read_bytes() == (dirty_dir / clean.name).read_bytes()

    with clean.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 500
    assert len({row["contact_id"] for row in rows}) == 500
    accounts: dict[str, tuple[str, ...]] = {}
    for row in rows:
        account = tuple(row[field] for field in (
            "company_name", "industry", "company_size", "country",
            "city", "province_code", "postal_code",
        ))
        assert accounts.setdefault(row["company_id"], account) == account
        assert row["email"] == "" or row["email"].endswith(".example")
        assert row["country"] == "Canada"
        if row["opportunity_stage"] == "None":
            assert not any(row[field] for field in (
                "opportunity_amount", "opportunity_probability",
                "opportunity_close_date",
            ))
    assert len(accounts) == 400

    summary = json.loads((dirty_dir / "crm-contacts.dirty_realistic.summary.json").read_text())
    assert summary["total_rows"] == 500
    assert summary["events"] > 0
    assert summary["changed_cells"] == summary["events"]
    assert summary["operations"][0]["requested_rows"] == 30


def test_crm_columns_follow_their_cross_column_rules(tmp_path: Path) -> None:
    """The clean file holds no exception to the rules a cross-column analysis may look for."""
    generate_datasets(build_generate_plan(example="crm", rows=3000, output_dir=tmp_path))
    with (tmp_path / "crm-contacts.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    probability = {"Discovery": (10, 25), "Proposal": (30, 50), "Negotiation": (60, 85),
                   "Closed Won": (100, 100), "Closed Lost": (0, 0)}
    lifecycle = {"None": {"Lead", "Qualified", "Customer"}, "Discovery": {"Opportunity"},
                 "Proposal": {"Opportunity"}, "Negotiation": {"Opportunity"},
                 "Closed Won": {"Customer"}, "Closed Lost": {"Lead", "Qualified"}}
    for row in rows:
        stage, closed = row["opportunity_stage"], row["opportunity_close_date"]
        assert row["lifecycle_stage"] in lifecycle[stage]
        if row["last_activity_at"]:
            assert row["last_activity_at"] >= row["created_at"]
            assert date.fromisoformat(row["last_activity_at"]).weekday() < 5
        if row["opportunity_probability"]:
            low, high = probability[stage]
            assert low <= int(row["opportunity_probability"]) <= high
        if closed:
            assert closed >= row["created_at"]
            assert (closed <= "2026-09-30") == stage.startswith("Closed")
        if row["owner"] and row["province_code"] == "AB":
            assert row["owner"] == "Sam Patel"
    years = Counter(row["created_at"][:4] for row in rows)
    assert years["2025"] > 2 * years["2020"]
    assert 0.31 <= sum(row["marketing_opt_in"] == "true" for row in rows) / len(rows) <= 0.39

    def median(size: str) -> float:
        return statistics.median(float(row["opportunity_amount"]) for row in rows
                                 if row["company_size"] == size and row["opportunity_amount"])

    assert median("1-10") < median("51-200") < median("1001+")


def test_crm_rule_breaks_logs_each_broken_rule_with_its_class(tmp_path: Path) -> None:
    """Each class of rule_breaks changes some rows, and its log says which cells."""
    generate_datasets(build_generate_plan(
        example="crm", rows=5000, anomaly_profile="rule_breaks", output_dir=tmp_path,
    ))
    with (tmp_path / "crm-contacts.rule_breaks.changes.csv").open(encoding="utf-8", newline="") as stream:
        changes = list(csv.DictReader(stream))
    classes = Counter(change["class"] for change in changes)
    assert set(classes) == {
        "probability_vs_stage", "lifecycle_vs_stage", "status_vs_lifecycle", "closed_in_future",
        "activity_before_creation", "owner_vs_territory", "company_name_variant",
    }
    assert all(count > 0 for count in classes.values())
    with (tmp_path / "crm-contacts.rule_breaks.csv").open(encoding="utf-8", newline="") as stream:
        dirty = list(csv.DictReader(stream))
    # row_number counts the header as line 1.
    broken = {int(change["row_number"]) - 2 for change in changes if change["class"] == "closed_in_future"}
    assert all(dirty[index]["opportunity_close_date"] == "2027-03-15"
               and dirty[index]["opportunity_stage"] == "Closed Won" for index in broken)


def test_crm_missing_values_depend_on_other_columns(tmp_path: Path) -> None:
    generate_datasets(build_generate_plan(example="crm", rows=6000, output_dir=tmp_path))
    with (tmp_path / "crm-contacts.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    def empty(column: str, keep: object) -> float:
        group = [row for row in rows if keep(row)]  # type: ignore[operator]
        return sum(not row[column] for row in group) / len(group)

    assert empty("phone", lambda row: not row["email"]) > 0.4
    assert empty("phone", lambda row: row["email"]) < 0.06
    assert empty("last_activity_at", lambda row: row["lifecycle_stage"] == "Lead") > 0.15
    assert empty("last_activity_at", lambda row: row["lifecycle_stage"] == "Customer") < 0.05
    assert empty("opportunity_amount", lambda row: row["opportunity_stage"] == "Closed Won") == 0
