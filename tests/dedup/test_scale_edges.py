# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Edges of the scale the contract does not name (lot 10): huge keys, wide rows, odd characters.

They run in a few seconds. The heavy versions of the contract (T07, T08, T09, T21) are in
``test_contract_scale.py``.
"""

import random

import pytest
from dedup_helpers import (
    analyze,
    assert_published,
    count_stats,
    load_report,
    no_temporary_files,
    reference_stats,
    run,
    write_csv,
)

pytestmark = pytest.mark.dedup_lot("10")


def _marks(analysis):
    total = analysis.stats.total
    return (
        [analysis.marks.is_extra(i) for i in range(total)],
        [analysis.marks.is_group_first(i) for i in range(total)],
    )


def test_a_single_key_larger_than_the_budget_moves_to_disk_at_the_first_record(tmp_path):
    cell = "x" * 120_000
    # A row of nine cells holds about 1.08 MB, over the 1 MiB budget.
    rows = [tuple(cell[:-4] + f"{n}{c:03d}" for c in range(9)) for n in (1, 2, 1, 3, 2, 1)]
    header = [f"c{c}" for c in range(9)]
    source = write_csv(tmp_path, "huge.csv", rows, header=header)
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    analysis = analyze(source, memory_budget_mb=1, temp_dir=scratch)
    assert analysis.storage_mode == "disk"
    assert analysis.spilled_at_record == 1
    assert count_stats(analysis) == reference_stats(rows)
    assert not list(scratch.iterdir())


def test_a_run_over_cells_of_a_hundred_thousand_characters_is_exact(tmp_path):
    rows = [(str(n % 4), "é" * 100_000, f"{n % 3}") for n in range(12)]
    source = write_csv(tmp_path, "long.csv", rows, header=["a", "b", "c"])
    run(source, memory_budget_mb=1, temp_dir=tmp_path)
    assert_published(tmp_path, "long", rows, header=["a", "b", "c"])


def test_a_cell_over_the_csv_field_limit_fails_as_invalid_csv_without_the_cell(tmp_path):
    secret = "confidential" * 12_000
    source = write_csv(tmp_path, "toolong.csv", [("1", secret), ("1", secret)], header=["a", "b"])
    outcome = run(source)
    assert outcome.status == "FAILED"
    assert outcome.reason == "invalid_csv"
    text = (tmp_path / "toolong.dedup.json").read_text(encoding="utf-8")
    assert "confidential" not in text
    assert load_report(tmp_path, "toolong")["status"] == "failed"
    assert not list(tmp_path.glob("toolong.*.csv"))
    assert no_temporary_files(tmp_path)


@pytest.mark.parametrize("budget", [1, 512])
def test_two_thousand_columns_are_counted_exactly(tmp_path, budget):
    width = 2_000
    base = [tuple(f"{row}-{column}" for column in range(width)) for row in range(40)]
    rows = base + base[:7] + base[3:5] + base[3:4]
    source = write_csv(tmp_path, "wide.csv", rows, header=[f"c{c}" for c in range(width)])
    analysis = analyze(source, memory_budget_mb=budget, temp_dir=tmp_path)
    assert count_stats(analysis) == reference_stats(rows)


def test_nul_astral_and_combining_characters_count_alike_in_memory_and_on_disk(tmp_path):
    alphabet = ["", "\x00", "a\x00b", "\U0001f600", "é", "é", "ÿ", "\x7f", "ab"]
    rng = random.Random(11)
    padding = "p" * 400
    pool = [
        (padding, rng.choice(alphabet), rng.choice(alphabet), str(rng.randrange(900)))
        for _ in range(9_000)
    ]
    rows = [rng.choice(pool) for _ in range(12_000)]
    source = write_csv(tmp_path, "odd.csv", rows, header=["p", "x", "y", "n"])
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    in_memory = analyze(source, memory_budget_mb=512)
    on_disk = analyze(source, memory_budget_mb=1, temp_dir=scratch)
    assert (in_memory.storage_mode, on_disk.storage_mode) == ("memory", "disk")
    assert count_stats(in_memory) == count_stats(on_disk) == reference_stats(rows)
    assert _marks(in_memory) == _marks(on_disk)
