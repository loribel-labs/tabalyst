# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Control comparison with the duplicate count of the Scan (design dedup 3, plan lot 10).

The Scan counts the records equal to an earlier one with a 128-bit digest and stops storing
digests at ``limits.max_tracked_records``; Dedup is its exact complement. Under that limit
the two agree on the count and on the position of every extra copy (the Scan numbers its
records from 1). Past the limit the Scan reports a proven lower bound.
"""

from pathlib import Path

import pytest
from dedup_helpers import analyze, generated_rows, write_csv

from tabalyst import scan
from tabalyst.scanner import ScanConfig

DATASET = Path(__file__).resolve().parents[2] / "examples" / "datasets" / "insurance-customers.csv"
WIDE = ["id", "c1", "c2"]


def _extra_positions(analysis):
    return [i for i in range(analysis.stats.total) if analysis.marks.is_extra(i)]


def _scan_duplicates(source, **limits):
    config = ScanConfig.model_validate({"limits": limits}) if limits else None
    return scan(source, config=config).datasets[0].records.duplicates


@pytest.mark.dedup_lot("10")
def test_the_scan_and_dedup_agree_on_the_example_dataset():
    analysis = analyze(DATASET)
    duplicates = _scan_duplicates(DATASET)
    assert duplicates.count.status == "complete"
    assert duplicates.count.value == analysis.stats.extra_copies == 8
    assert [n + 1 for n in _extra_positions(analysis)] == duplicates.records


@pytest.mark.dedup_lot("10")
@pytest.mark.parametrize("extra", [0, 300, 3_000])
def test_the_scan_and_dedup_agree_on_generated_files_under_the_scan_limit(tmp_path, extra):
    rows = list(generated_rows(5_000, extra, width=3))
    source = write_csv(tmp_path, "control.csv", rows, header=WIDE)
    analysis = analyze(source)
    duplicates = _scan_duplicates(source, max_listed_records=5_000)
    assert duplicates.count.status == "complete"
    assert duplicates.count.value == analysis.stats.extra_copies == extra
    assert [n + 1 for n in _extra_positions(analysis)] == duplicates.records


@pytest.mark.dedup_lot("10")
def test_past_the_scan_limit_the_scan_is_a_lower_bound_and_dedup_is_exact(tmp_path):
    rows = list(generated_rows(5_000, 1_500, width=3))
    source = write_csv(tmp_path, "limited.csv", rows, header=WIDE)
    analysis = analyze(source)
    duplicates = _scan_duplicates(source, max_tracked_records=1_000)
    assert duplicates.count.status == "limited"
    assert duplicates.count.reason == "record_budget"
    assert duplicates.count.lower_bound <= analysis.stats.extra_copies == 1_500
