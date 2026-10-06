# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract checks for the packaged CRM demonstration."""

from __future__ import annotations

import csv
import json
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
