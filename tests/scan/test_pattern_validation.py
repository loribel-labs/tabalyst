# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The executor of the validation of patterns and of the period counts (design
20.9 and 20.10)."""

import pytest
from planner_helpers import scan_csv
from second_pass_helpers import deep_csv, entry, forced_plan, pattern_accumulator

from tabalyst.scanner.models import FieldPatternsComplete
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.patterns import (
    derive_from_samples,
)
from tabalyst.scanner.secondpass.periods import PeriodAccumulator


def _entry(tmp_path, rows, **settings):
    result = scan_csv(tmp_path, "code", rows, **settings)
    patterns = result.derived.patterns.fields[0]
    assert isinstance(patterns, FieldPatternsComplete)
    return result, patterns


def test_a_value_with_a_non_ascii_letter_goes_through_the_token_matcher(tmp_path):
    rows = [f"é{n * 37 % 1000:03d}" for n in range(100)] + [f"E{n * 37 % 1000:03d}" for n in range(100)]
    result, patterns = _entry(tmp_path, rows, limits={"max_samples": 30})
    accumulator = pattern_accumulator(result, patterns)

    accumulator.add_strings(["é123", "É999", "e123"], [2, 1, 1])
    counts = accumulator.result(4, "source")

    assert counts.matched + counts.outside_patterns() == 4
    assert counts.matched >= 2


def test_validation_fails_alone_when_the_scan_has_no_pattern_entry(tmp_path):
    rows = [f"AB{n:04d}" for n in range(300)]
    result = scan_csv(tmp_path, "code", rows, limits={"max_samples": 30})
    plan = forced_plan(result)
    scanless = result.model_copy(update={"derived": None})

    outcome = run_second_pass(scanless, tmp_path / "data.csv", plan.model_copy())

    failed = entry(outcome, "pattern_validation", "code")
    assert failed.status == "failed" and failed.reason == "scan_mismatch"
    # The other analysis of the pass is not touched by it.
    assert entry(outcome, "exact_frequencies", "code").status == "complete"


def test_a_sample_is_not_enough_to_derive_the_counts_without_reading(tmp_path):
    result, patterns = _entry(tmp_path, [f"AB{n:04d}" for n in range(300)], limits={"max_samples": 30})
    field = result.datasets[0].fields[0]

    with pytest.raises(ScanMismatch, match="every distinct value"):
        derive_from_samples(pattern_accumulator(result, patterns, unique=True), field)


def test_the_counts_that_do_not_match_the_scan_are_a_failure_and_never_a_result(tmp_path):
    result, patterns = _entry(tmp_path, [f"AB{n:04d}" for n in range(300)])
    accumulator = pattern_accumulator(result, patterns)
    accumulator.add_strings(["AB0001"], [1])

    with pytest.raises(ScanMismatch, match="values"):
        accumulator.result(2, "source")


def test_period_counts_of_another_total_than_the_scan_are_refused():
    accumulator = PeriodAccumulator("day", "date")

    with pytest.raises(ScanMismatch):
        accumulator.result(1, 0)


def test_a_date_field_is_counted_with_the_source_read_once(tmp_path):
    rows = [f"2024-0{n % 9 + 1}-1{n % 9}" for n in range(500)]
    _, _, outcome = deep_csv(tmp_path, "day", rows)

    periods = entry(outcome, "temporal_distribution", "day")
    assert periods.status == "complete" and periods.result.count == 500
    assert outcome.document.run.source_read is True


def test_a_column_of_dates_reads_each_distinct_date_once_for_the_whole_file(tmp_path, monkeypatch):
    from datetime import date, timedelta

    from planner_helpers import scan_csv
    from second_pass_helpers import forced_plan

    from tabalyst.scanner.detectors.temporal import DateDetector

    rows = [(date(2023, 1, 1) + timedelta(days=n % 700)).isoformat() for n in range(60_000)]
    result = scan_csv(tmp_path, "day", rows)
    plan = forced_plan(result)
    read = []
    original = DateDetector.classify_many

    def counting(self, values):
        read.append(len(values))
        return original(self, values)

    monkeypatch.setattr(DateDetector, "classify_many", counting)

    outcome = run_second_pass(result, tmp_path / "data.csv", plan)

    assert entry(outcome, "temporal_distribution", "day").status == "complete"
    # 700 distinct dates over many batches: each is read once, not once a batch.
    assert sum(read) == 700
