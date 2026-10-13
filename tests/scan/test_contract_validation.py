# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Validation of patterns and distribution of dates in the second pass (plan
tests C11 and D12; design 20.9 and 20.10)."""

import json
import random
import re
from collections import Counter
from datetime import date, timedelta

import pytest
from planner_helpers import scan_csv
from scan_helpers import write_text
from second_pass_helpers import deep_csv, entry, forced_plan

from tabalyst.scanner import ScanConfig, pattern_eligibility, scan
from tabalyst.scanner.models import PatternEligibility
from tabalyst.scanner.patterninfer import MAX_TOKENS, candidate_order, tokenize
from tabalyst.scanner.secondpass import run_second_pass
from tabalyst.scanner.secondpass.patterns import PatternAccumulator, derive_from_samples

_CLASS = {
    "digit_ascii": "[0-9]",
    "upper_ascii": "[A-Z]",
    "lower_ascii": "[a-z]",
    "letter_unicode": "[^\\W\\d_]",
    "upper_digit": "[0-9A-Z]",
    "lower_digit": "[0-9a-z]",
    "alphanumeric": "[0-9A-Za-z]",
}


def _oracle_regex(signature):
    """A backtracking regular expression of a signature, written apart from the
    matcher of the grammar: the oracle the counts are compared with."""
    parts = []
    for token in signature:
        unit = (
            f"(?:{re.escape(token.text)})" if token.kind == "literal" else _CLASS[token.kind]
        )
        parts.append(f"{unit}{{{token.min},{token.max}}}")
    return re.compile("".join(parts))


def _oracle(candidates, max_length, values):
    """Exclusive counts of ``values`` by brute force."""
    order = sorted(
        range(len(candidates)),
        key=lambda n: candidate_order(candidates[n].signature, 0, n),
    )
    regexes = [_oracle_regex(c.signature) for c in candidates]
    occurrences = [0] * len(candidates)
    other = 0
    excluded = Counter()
    overlaps = Counter()
    for value in values:
        if len(value) > max_length:
            excluded["too_long"] += 1
        elif len(tokenize(value)) > MAX_TOKENS:
            excluded["too_complex"] += 1
        else:
            reading = [n for n in order if regexes[n].fullmatch(value)]
            if not reading:
                other += 1
            else:
                occurrences[reading[0]] += 1
                if len(reading) > 1:
                    overlaps[tuple(sorted(reading))] += 1
    return occurrences, other, excluded, overlaps


def _codes(count, seed=3):
    rng = random.Random(seed)
    rows = []
    for n in range(count):
        kind = rng.randrange(8)
        if kind == 0:
            rows.append(f"AB{rng.randrange(10_000):04d}")
        elif kind == 1:
            rows.append(f"CD{rng.randrange(10_000):04d}X")
        elif kind == 2:
            rows.append(f"zz-{rng.randrange(100)}")
        elif kind == 3:
            rows.append(f"{rng.randrange(10**6):06d}")
        elif kind == 4:
            rows.append(f"ab{rng.randrange(1000)}")
        elif kind == 5:
            rows.append(f" AB{rng.randrange(10_000):04d} ")
        elif kind == 6:
            rows.append("é" + "".join(rng.choice("ab9") for _ in range(rng.randrange(1, 6))))
        else:
            rows.append(rng.choice(["?", "!!", "x" * 70, "a-b-c-d-e-f-g-h-i-j-k-l-m-n-o-p-q-r-s-t-u"]))
    return rows


# C11 ---------------------------------------------------------------------------


@pytest.fixture
def every_field_eligible(monkeypatch):
    """The messy columns of these tests take too many formats to be eligible
    for patterns (design 18.12); they exercise the counting, so they are forced."""
    eligible = PatternEligibility(state="eligible", score=1.0, reasons=["regular_structure"])
    monkeypatch.setattr(pattern_eligibility, "assess", lambda *args: eligible)


@pytest.mark.scan_json_lot("7c")
def test_C11_every_occurrence_is_counted_once_and_the_counts_reconcile(
    tmp_path, every_field_eligible
):
    rows = _codes(4_000)
    # K = 60 keeps the patterns a discovery on a sample: the source is read.
    result, _, outcome = deep_csv(tmp_path, "code", rows, limits={"max_samples": 60})
    counts = entry(outcome, "pattern_validation", "code").result

    candidates = result.derived.patterns.fields[0].candidates
    occurrences, other, excluded, overlaps = _oracle(
        candidates, result.config.pattern_inference.max_value_length, rows
    )

    assert counts.computed_from == "source" and outcome.read_source
    assert [t.occurrences for t in counts.candidates] == occurrences
    assert counts.other == other
    assert counts.excluded.too_long == excluded["too_long"]
    assert counts.excluded.too_complex == excluded["too_complex"]
    assert counts.excluded.non_string == 0
    assert {tuple(o.patterns): o.occurrences for o in counts.overlaps} == {
        tuple(candidates[n].id for n in key): value for key, value in overlaps.items()
    }
    # The identity of the specification: tested + other + excluded is the population.
    assert counts.values == len(rows) == result.datasets[0].fields[0].values.count
    assert counts.matched + counts.other + sum(counts.excluded.model_dump().values()) == counts.values
    assert counts.matched == sum(occurrences)


@pytest.mark.scan_json_lot("7c")
def test_C11_a_value_read_by_two_patterns_counts_for_the_most_specific_only(tmp_path):
    # `AB` + digits is read by the literal-prefixed pattern and by the broad one.
    rows = [f"AB{n:04d}" for n in range(300)] + [f"{chr(65 + n % 26)}{chr(66 + n % 20)}{n:04d}" for n in range(300)]
    _, _, outcome = deep_csv(tmp_path, "code", rows, limits={"max_samples": 40})
    counts = entry(outcome, "pattern_validation", "code").result

    assert counts.matched == sum(t.occurrences for t in counts.candidates) == len(rows)
    assert counts.overlaps == [] or all(len(o.patterns) > 1 for o in counts.overlaps)
    # No occurrence is counted twice, overlaps or not.
    assert counts.matched + counts.other + sum(counts.excluded.model_dump().values()) == counts.values


@pytest.mark.scan_json_lot("7c")
def test_C11_the_exact_counts_of_a_complete_scan_give_the_same_result_without_reading(tmp_path):
    rows = [
        value
        for value in _codes(1_500, seed=9)
        if len(value) <= 40 and len(tokenize(value)) <= MAX_TOKENS
    ]
    result = scan_csv(tmp_path, "code", rows)
    field = result.datasets[0].fields[0]
    patterns = result.derived.patterns.fields[0]
    assert patterns.candidates[0].coverage.basis == "all_distinct"
    plan = forced_plan(result)
    candidate = next(c for c in plan.candidates if c.analyzer == "pattern_validation")
    assert candidate.execution.requires_source is False

    local = run_second_pass(result, tmp_path / "data.csv", plan)
    read = PatternAccumulator(patterns, result.config.pattern_inference.max_value_length)
    counted = Counter(rows)
    read.add_strings(list(counted), list(counted.values()))
    from_source = read.result(field.values.count, "source")

    answer = entry(local, "pattern_validation", "code")
    assert local.read_source is False and answer.status == "complete"
    assert answer.result.computed_from == "samples"
    assert answer.result.model_dump(exclude={"computed_from"}) == from_source.model_dump(
        exclude={"computed_from"}
    )
    # Counted once each, the distinct values give the shares of the discovery.
    once = PatternAccumulator(patterns, result.config.pattern_inference.max_value_length)
    once.add_strings(list(counted), [1] * len(counted))
    assert once.occurrences == [c.coverage.distinct for c in patterns.candidates]
    assert once.other == patterns.other.d
    derived = PatternAccumulator(patterns, result.config.pattern_inference.max_value_length)
    derive_from_samples(derived, field)
    assert derived.occurrences == read.occurrences


@pytest.mark.scan_json_lot("7c")
def test_C11_json_numbers_are_excluded_and_counted(tmp_path):
    # Decimal numbers: an integer is read as its decimal text (design 20.9).
    records = [{"code": f"AB{n:04d}"} for n in range(120)] + [{"code": n + 0.5} for n in range(30)]
    source = write_text(tmp_path, "data.json", json.dumps(records))
    result = scan(source, config=ScanConfig.model_validate({"limits": {"max_samples": 40}}))
    plan = forced_plan(result)
    chosen = [c for c in plan.candidates if c.analyzer == "pattern_validation"]
    if not chosen:  # a mixed field the Scan gave no patterns: nothing to validate
        pytest.skip("the scan inferred no pattern for this field")

    outcome = run_second_pass(result, source, plan)

    counts = entry(outcome, "pattern_validation", chosen[0].display).result
    assert counts.excluded.non_string == 30
    assert counts.values == 150


@pytest.mark.scan_json_lot("7c")
def test_C11_an_unmatched_value_is_an_observation_and_never_an_error(tmp_path):
    rows = [f"AB{n:04d}" for n in range(200)] + ["???", "n/a"] * 10
    # One family only: the structures of the other two values are not published.
    _, _, outcome = deep_csv(
        tmp_path, "code", rows, limits={"max_samples": 40}, pattern_inference={"max_families": 1}
    )

    answer = entry(outcome, "pattern_validation", "code")

    assert answer.status == "complete" and answer.reason is None
    assert answer.result.other == 20
    assert outcome.document.status == "complete"


# D12 ---------------------------------------------------------------------------


def _dates(tmp_path, values, header="day", **settings):
    result, _, outcome = deep_csv(tmp_path, header, values, **settings)
    return result, entry(outcome, "temporal_distribution", header)


def _span(start, days, count, seed=5):
    rng = random.Random(seed)
    return [start + timedelta(days=rng.randrange(days + 1)) for _ in range(count)]


@pytest.mark.scan_json_lot("7c")
def test_D12_dates_are_counted_per_day_with_the_counts_of_the_scan(tmp_path):
    days = _span(date(2024, 1, 1), 300, 2_000)
    result, answer = _dates(tmp_path, [d.isoformat() for d in days])

    periods = answer.result
    kind = result.datasets[0].fields[0].temporal.value.kinds[0]
    assert periods.granularity == "day" and periods.temporal_kind == "date"
    assert {p.period: p.count for p in periods.periods} == {
        key.isoformat(): n for key, n in Counter(days).items()
    }
    assert periods.count == kind.count == 2_000 and periods.ambiguous == 0 and periods.unplaced == 0
    assert (periods.first, periods.last) == (min(days).isoformat(), max(days).isoformat())
    assert [p.period for p in periods.periods] == sorted(p.period for p in periods.periods)


@pytest.mark.scan_json_lot("7c")
def test_D12_a_long_span_is_counted_per_month(tmp_path):
    months = _span(date(2015, 1, 1), 365 * 8, 3_000)

    _, by_month = _dates(tmp_path, [d.isoformat() for d in months])

    assert by_month.result.granularity == "month"
    assert {p.period: p.count for p in by_month.result.periods} == {
        f"{k[0]:04d}-{k[1]:02d}": n for k, n in Counter((d.year, d.month) for d in months).items()
    }


@pytest.mark.scan_json_lot("7c")
def test_D12_a_very_long_span_is_already_counted_per_year_by_the_scan(tmp_path):
    years = _span(date(1900, 1, 1), 365 * 100, 3_000, seed=6)
    result = scan_csv(tmp_path, "day", [d.isoformat() for d in years])

    plan = forced_plan(result)

    candidate = next(c for c in plan.candidates if c.analyzer == "temporal_distribution")
    assert candidate.selection.state == "already_satisfied"
    assert candidate.selection.reason == "years_counted"
    assert {y.year: y.count for y in result.datasets[0].fields[0].temporal.value.kinds[0].years} == dict(
        Counter(d.year for d in years)
    )


@pytest.mark.scan_json_lot("7c")
def test_D12_ambiguous_dates_are_counted_and_never_placed(tmp_path):
    # 13/02 is day first and 02/25 month first: the column proves both orders, so
    # 02/03, 04/05 and 05/06 could be read either way and stay ambiguous. (With only
    # one order proved they are read that way: lot 17, design 20.26.)
    rows = [
        "13/02/2024", "14/02/2024", "02/25/2024", "02/03/2024", "04/05/2024", "05/06/2024", "30/01/2024",
    ]
    result, answer = _dates(tmp_path, rows)

    scanned = result.datasets[0].fields[0].temporal.value
    periods = answer.result
    assert scanned.ambiguous == periods.ambiguous == 3
    assert periods.count == scanned.kinds[0].count == 4 and periods.resolution is None
    assert periods.resolved == 0
    assert periods.values == 7 and periods.unplaced == 0
    assert {p.period for p in periods.periods} == {
        "2024-01-30", "2024-02-13", "2024-02-14", "2024-02-25"
    }


@pytest.mark.scan_json_lot("7c")
def test_D12_a_configured_order_resolves_the_ambiguity_as_the_scan_did(tmp_path):
    rows = ["02/03/2024", "04/05/2024", "13/02/2024"]
    _, answer = _dates(tmp_path, rows, detectors={"date": {"ambiguous_order": "DMY"}})

    assert answer.result.ambiguous == 0 and answer.result.count == 3
    assert {p.period for p in answer.result.periods} == {"2024-03-02", "2024-05-04", "2024-02-13"}


@pytest.mark.scan_json_lot("7c")
def test_D12_a_datetime_is_placed_by_the_date_it_is_written_with_whatever_the_offset(tmp_path):
    rows = [
        # Before and after the change of hour of New York on 2024-03-10.
        "2024-03-10T01:30:00-05:00",
        "2024-03-10T03:30:00-04:00",
        # Written late in the evening west of Greenwich: UTC would be the next day.
        "2024-03-10T23:30:00-05:00",
        "2024-03-11T00:15:00+09:00",
        "2024-11-03T01:30:00-04:00",
        "2024-11-03T01:30:00-05:00",
    ]
    result, answer = _dates(tmp_path, rows)

    kind = result.datasets[0].fields[0].temporal.value.kinds[0]
    assert kind.kind == "datetime_aware" and answer.result.temporal_kind == "datetime_aware"
    assert {p.period: p.count for p in answer.result.periods} == {
        "2024-03-10": 3,
        "2024-03-11": 1,
        "2024-11-03": 2,
    }
    assert answer.result.zone == "as_written" and answer.result.count == kind.count == 6


@pytest.mark.scan_json_lot("7c")
def test_D12_values_that_are_not_dates_are_counted_apart(tmp_path):
    rows = [d.isoformat() for d in _span(date(2024, 1, 1), 200, 300)] + ["n/a", "2024-02-30"] * 3
    _, answer = _dates(tmp_path, rows)

    assert answer.result.unplaced == 6 and answer.result.count == 300
    assert answer.result.values == 306


@pytest.mark.scan_json_lot("7c")
def test_D12_a_field_with_two_temporal_kinds_is_not_placed_without_a_policy(tmp_path):
    rows = ["2024-01-05", "2024-02-06", "2024-03-07T10:00:00", "2024-04-08T11:30:00"] * 20
    result = scan_csv(tmp_path, "day", rows)

    plan = forced_plan(result)

    candidate = next(c for c in plan.candidates if c.analyzer == "temporal_distribution")
    assert candidate.selection.state == "rejected"
    # A date and a datetime are not merged without a policy (TIME-03).
    assert candidate.applicability.reasons in (["mixed_temporal_kinds"], ["unreliable_type"])


@pytest.mark.scan_json_lot("7c")
def test_D12_the_periods_are_the_same_whatever_the_order_of_the_rows(tmp_path):
    days = [d.isoformat() for d in _span(date(2023, 6, 1), 500, 800)]
    _, one = _dates(tmp_path, days)
    other = tmp_path / "shuffled"
    other.mkdir()
    random.Random(1).shuffle(days)
    _, two = _dates(other, days)

    assert one.result == two.result
