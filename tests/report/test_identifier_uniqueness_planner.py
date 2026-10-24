# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The Report that settles the uniqueness of an identifier by itself (Unique ID lot 8, UID-011)."""

import json

import pytest
from identifier_uniqueness_helpers import population, uniqueness_of, write_csv

from tabalyst import generate_reports
from tabalyst.dedup_service import dedup_csv
from tabalyst.scanner.config import ScanConfig

pytestmark = pytest.mark.uid_lot("8")

HEADER = ("customer_id", "status", "region")


def _rows(**kinds):
    # Three columns: a record of two costs more than the automatic limit a cell (design 20.42).
    return [(a, b, f"r{a[-1]}") for a, b in population(**kinds)]


def _config(tmp_path, **limits):
    path = tmp_path / "config.json"
    scan = ScanConfig.model_validate({"limits": {"max_tracked_records": 500, **limits}})
    document = {"scan": scan.model_dump(by_alias=True, mode="json", exclude_defaults=True)}
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _report(tmp_path, source, **options):
    generate_reports([source], output_dir=tmp_path / "out", config_path=_config(tmp_path), **options)
    return json.loads((tmp_path / "out" / f"{source.stem}.json").read_text(encoding="utf-8"))


def test_a_plain_report_counts_the_copies_the_scan_could_only_bound(tmp_path):
    source = write_csv(tmp_path, "r.csv", _rows(distinct_ids=2_000, copies=600), HEADER)

    document = _report(tmp_path, source)

    item = uniqueness_of(document, "customer_id")
    assert item["status"] == "complete"
    assert item["interpretation"] == "unique_after_row_deduplication"
    assert item["explanation"]["duplicate_row_extra_copies"] == 600
    assert item["evidence"]["duplicate_rows"]["source"] == "deep.duplicate_rows_count"
    assert document["analyses"]["mode"] == "auto"


def test_a_valid_dedup_report_spares_the_count(tmp_path):
    source = write_csv(tmp_path, "r.csv", _rows(distinct_ids=2_000, copies=600), HEADER)
    outcome = dedup_csv(source, output_dir=tmp_path)

    document = _report(tmp_path, source, dedup_report=outcome.report_path)

    item = uniqueness_of(document, "customer_id")
    assert item["status"] == "complete"
    assert item["evidence"]["duplicate_rows"]["source"] == "dedup.report"
    deep = document["analyses"].get("deep")
    counted = [
        a for a in (deep["analyses"] if deep else []) if a["analyzer"] == "duplicate_rows_count"
    ]
    assert counted == []


def test_a_table_of_two_columns_is_left_to_a_forced_pass(tmp_path):
    from identifier_uniqueness_helpers import HEADER as TWO

    source = write_csv(tmp_path, "r.csv", population(distinct_ids=2_000, copies=600), TWO)

    document = _report(tmp_path, source)

    item = uniqueness_of(document, "customer_id")
    assert item["status"] == "limited"
    assert item["reason"] == "duplicates_limited"


def test_a_second_report_of_the_same_file_reuses_the_count(tmp_path):
    source = write_csv(tmp_path, "r.csv", _rows(distinct_ids=2_000, copies=600), HEADER)

    first = _report(tmp_path, source)
    second = _report(tmp_path, source, force=True)

    assert first["analyses"]["outcome"] == "ran"
    assert second["analyses"]["outcome"] == "reused"
    assert uniqueness_of(second, "customer_id") == uniqueness_of(first, "customer_id")
