# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The executor of the validation of patterns and of the period counts (design
20.9 and 20.10)."""

import random
import string

import pytest
from planner_helpers import scan_csv
from second_pass_helpers import deep_csv, entry, forced_plan

from tabalyst.scanner import pattern_eligibility
from tabalyst.scanner.models import FieldPatternsComplete, PatternEligibility
from tabalyst.scanner.patterninfer import compile_signature, matches
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.accumulators import ScanMismatch
from tabalyst.scanner.secondpass.patterns import (
    PatternAccumulator,
    ascii_regex,
    derive_from_samples,
)
from tabalyst.scanner.secondpass.periods import PeriodAccumulator


def _entry(tmp_path, rows, **settings):
    result = scan_csv(tmp_path, "code", rows, **settings)
    patterns = result.derived.patterns.fields[0]
    assert isinstance(patterns, FieldPatternsComplete)
    return result, patterns


def test_the_compiled_expression_reads_an_ascii_value_like_the_token_matcher(
    tmp_path, monkeypatch
):
    # Random strings take too many formats to be eligible for patterns (design
    # 18.12): the field is forced so that its candidates exercise the matchers.
    eligible = PatternEligibility(state="eligible", score=1.0, reasons=["regular_structure"])
    monkeypatch.setattr(pattern_eligibility, "assess", lambda *args: eligible)
    rng = random.Random(4)
    alphabet = string.ascii_letters + string.digits + "-_ '"
    rows = [
        "".join(rng.choice(alphabet) for _ in range(rng.randrange(1, 9))) for _ in range(800)
    ]
    rows += [f"AB{n:04d}" for n in range(200)] + [f"x{n}-{n * 3}" for n in range(200)]
    _, patterns = _entry(tmp_path, rows)
    probes = rows + ["", "AB", "AB12345", "x1-", "9" * 30] + [
        "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 14))) for _ in range(2_000)
    ]

    for candidate in patterns.candidates:
        regex = ascii_regex(candidate.signature)
        matcher = compile_signature(candidate.signature)
        for probe in probes:
            assert (regex.fullmatch(probe) is not None) == matches(matcher, probe), (
                candidate.render,
                probe,
            )


def test_a_value_with_a_non_ascii_letter_goes_through_the_token_matcher(tmp_path):
    rows = [f"é{n:03d}" for n in range(100)] + [f"E{n:03d}" for n in range(100)]
    _, patterns = _entry(tmp_path, rows, limits={"max_samples": 30})
    accumulator = PatternAccumulator(patterns, 64)

    accumulator.add_strings(["é123", "É999", "e123"], [2, 1, 1])
    counts = accumulator.result(4, "source")

    assert counts.matched + counts.other == 4
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
        derive_from_samples(PatternAccumulator(patterns, 64), field)


def test_the_counts_that_do_not_match_the_scan_are_a_failure_and_never_a_result(tmp_path):
    _, patterns = _entry(tmp_path, [f"AB{n:04d}" for n in range(300)])
    accumulator = PatternAccumulator(patterns, 64)
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
