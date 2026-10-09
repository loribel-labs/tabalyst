# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the second pass and its histograms (lot 7a): A07, A12, A15, D03,
D09 to D11 and the executor halves of D04 and D05."""

import hashlib
import json
import random
from decimal import Decimal
from fractions import Fraction

import pytest
from planner_helpers import scan_csv, with_field
from scan_helpers import write_text
from second_pass_helpers import deep_csv, entry, forced_plan, true_quantile

from tabalyst import generate_scans
from tabalyst.config import DeepSettings
from tabalyst.deep_service import execute_deep, generate_deep, prepare_deep
from tabalyst.errors import InputError
from tabalyst.scanner.models import Disabled
from tabalyst.scanner.secondpass import (
    deep_document,
    deep_path_for,
    load_deep,
    run_second_pass,
)
from tabalyst.source_guard import SourceNotReadable, StaleSource

LEVELS = {0.05: Fraction(5, 100), 0.25: Fraction(1, 4), 0.5: Fraction(1, 2),
          0.75: Fraction(3, 4), 0.95: Fraction(95, 100)}  # fmt: skip


def _home(monkeypatch, tmp_path):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))


def _people(tmp_path):
    rng = random.Random(11)
    lines = ["age,price,name"]
    for n in range(600):
        lines.append(f"{rng.randint(18, 90)},{rng.random() * 900:.2f},name {n % 25}")
    return write_text(tmp_path, "people.csv", "\n".join(lines) + "\n")


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


# A07 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7a")
def test_A07_a_limited_median_gets_a_distinct_estimate_from_the_histogram(tmp_path):
    rows = [f"{100 + (n * 37) % 900}.{n % 100:02d}" for n in range(400)]
    result, _, outcome = deep_csv(
        tmp_path, "prime_annuelle", rows, limits={"max_distinct_per_field": 50}
    )

    scanned = result.datasets[0].fields[0].numeric.value.median
    histogram = entry(outcome, "numeric_histogram", "prime_annuelle")

    # The Scan could not give the median; the second pass does, and says it is
    # an estimate with bounds that hold the true value.
    assert scanned.status == "limited"
    assert histogram.status == "complete"
    median = histogram.result.median
    assert median.accuracy == "estimated"
    truth = true_quantile([Fraction(Decimal(r)) for r in rows], Fraction(1, 2))
    assert median.lower <= float(truth) <= median.upper
    assert median.lower <= median.value <= median.upper
    # The Scan itself is not rewritten with the estimate.
    assert result.datasets[0].fields[0].numeric.value.median.status == "limited"


# A12 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7a")
def test_A12_the_second_pass_is_a_separate_result_and_leaves_the_scan_file_alone(
    tmp_path, monkeypatch
):
    _home(monkeypatch, tmp_path)
    source = _people(tmp_path)
    scanned = generate_scans([source], project_storage=True)
    scan_path = scanned.successes[0].job.output
    before = (scan_path.read_bytes(), _sha256(scan_path), scan_path.stat().st_mtime_ns)

    result = generate_deep([source])

    assert result.successes[0].job.scan.reused is True
    assert (scan_path.read_bytes(), _sha256(scan_path), scan_path.stat().st_mtime_ns) == before
    deep_path = result.successes[0].job.deep_path
    assert deep_path == scan_path.with_name("deep.json") and deep_path.exists()
    document = json.loads(deep_path.read_text(encoding="utf-8"))
    assert document["format"] == "tabalyst.scan.deep"
    assert document["base"]["source_sha256"] == scanned.successes[0].result.source.sha256


@pytest.mark.scan_json_lot("7a")
def test_A12_a_scan_written_to_a_chosen_file_has_its_second_pass_beside_it(tmp_path):
    source = _people(tmp_path)
    target = tmp_path / "out" / "people.scan.json"

    result = generate_deep([source], output=target)

    assert result.successes[0].job.deep_path == tmp_path / "out" / "people.deep.json"
    assert deep_path_for(tmp_path / "x" / "scan.json") == tmp_path / "x" / "deep.json"
    assert deep_path_for(tmp_path / "x" / "any.json") == tmp_path / "x" / "any.deep.json"


# A15 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7a")
def test_A15_a_complete_cache_reads_nothing_and_a_partial_one_computes_only_the_missing(
    tmp_path, monkeypatch
):
    _home(monkeypatch, tmp_path)
    source = _people(tmp_path)
    config = write_text(tmp_path, "deep.json", json.dumps({"deep": {"bins": 50}}))

    first = generate_deep([source]).successes[0]
    again = generate_deep([source]).successes[0]
    changed = generate_deep([source], config_path=config).successes[0]

    ids = {e.display: e.id for e in first.outcome.document.analyses}
    # Two histograms, the patterns of the names (which the Scan answers alone) and
    # the table of the names against the first characters of the ages.
    assert len(first.outcome.executed) == 4 and first.outcome.read_source
    # Complete: every result is valid, so the source is not read and the file is not rewritten.
    assert again.outcome.read_source is False and again.written is False
    assert again.outcome.reused == first.outcome.executed
    # Settings that change only the bins recompute the histogram that uses them.
    assert changed.outcome.executed == (ids["price"],)
    assert set(changed.outcome.reused) == {ids["age"], ids["name"], ids["name and age (prefix)"]}

    # A partial cache: a missing entry and a failed one are computed again.
    path = changed.job.deep_path
    stored = load_deep(path)
    kept = [
        a.model_copy(update={"status": "failed", "reason": "analysis_error", "result": None})
        if a.display == "age"
        else a
        for a in stored.analyses
        if a.display != "price"
    ]
    path.write_text(
        deep_document(stored.model_copy(update={"analyses": kept})), encoding="utf-8"
    )
    repaired = generate_deep([source], config_path=config).successes[0]
    assert set(repaired.outcome.executed) == {ids["age"], ids["price"]}
    assert all(a.status == "complete" for a in repaired.outcome.document.analyses)


@pytest.mark.scan_json_lot("7a")
def test_A15_a_budget_never_makes_a_stored_result_unusable(tmp_path):
    result = scan_csv(tmp_path, "n", [str(n % 40) for n in range(400)])
    plan = forced_plan(result)
    first = run_second_pass(result, tmp_path / "data.csv", plan)
    cheaper = plan.model_copy(
        update={"budgets": plan.budgets.model_copy(update={"memory_bytes": 10**9})}
    )

    again = run_second_pass(
        result, tmp_path / "data.csv", cheaper, previous=first.document
    )

    assert again.read_source is False and again.reused == first.executed


# D03 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7a")
def test_D03_a_plan_of_several_analyses_reads_the_source_once(tmp_path, monkeypatch):
    lines = ["age,price,note"] + [f"{18 + n % 70},{n * 1.37:.2f},note {n}" for n in range(500)]
    write_text(tmp_path, "data.csv", "\n".join(lines) + "\n")
    scanned = scan_csv(tmp_path, "age,price,note", lines[1:])
    # The Scan's length histogram is turned off, so the length analysis applies too.
    scanned = with_field(scanned, "note", string_lengths=Disabled())
    plan = forced_plan(scanned)
    opened = []
    from tabalyst.scanner.readers import factory
    from tabalyst.scanner.secondpass import executor

    def counting(path, config, on_bytes):
        opened.append(path)
        return factory.open_reader(path, config, on_bytes)

    monkeypatch.setattr(executor, "open_reader", counting)

    outcome = run_second_pass(scanned, tmp_path / "data.csv", plan)

    assert {a.analyzer for a in outcome.document.analyses} == {
        "numeric_histogram",
        "length_distribution",
        "pattern_validation",
    }
    # The patterns of `note` come from the exact counts of the Scan: no reading.
    assert len(outcome.executed) == 4 and len(opened) == 1
    assert outcome.document.run.records_read == 500


@pytest.mark.scan_json_lot("7c")
def test_D03_patterns_and_dates_share_the_one_reading_of_the_other_analyses(
    tmp_path, monkeypatch
):
    lines = ["age,code,day"] + [
        f"{18 + n % 70},AB{n % 900 + 100},2024-{n % 12 + 1:02d}-{n % 28 + 1:02d}"
        for n in range(500)
    ]
    # K = 50 leaves the patterns of `code` a sample, so they need the source.
    scanned = scan_csv(tmp_path, "age,code,day", lines[1:], limits={"max_samples": 50})
    plan = forced_plan(scanned)
    opened = []
    from tabalyst.scanner.readers import factory
    from tabalyst.scanner.secondpass import executor

    def counting(path, config, on_bytes):
        opened.append(path)
        return factory.open_reader(path, config, on_bytes)

    monkeypatch.setattr(executor, "open_reader", counting)

    outcome = run_second_pass(scanned, tmp_path / "data.csv", plan)

    found = {(a.analyzer, a.display) for a in outcome.document.analyses}
    assert ("pattern_validation", "code") in found
    assert ("temporal_distribution", "day") in found
    assert ("numeric_histogram", "age") in found
    assert all(a.status == "complete" for a in outcome.document.analyses)
    assert len(opened) == 1 and outcome.document.run.records_read == 500


# D04 and D05, the executor halves -----------------------------------------------


@pytest.mark.scan_json_lot("7a")
def test_D04_a_source_changed_between_the_plan_and_the_reading_publishes_nothing(
    tmp_path, monkeypatch
):
    _home(monkeypatch, tmp_path)
    source = write_text(
        tmp_path, "ids.csv", "n\n" + "\n".join(str(1000 + n) for n in range(300)) + "\n"
    )
    prepared = prepare_deep([source])
    deep_path = prepared.jobs[0].deep_path

    # Same size, other content: only the digest of the reading can tell.
    source.write_text(
        "n\n" + "\n".join(str(2000 + n) for n in range(300)) + "\n", encoding="utf-8", newline=""
    )
    assert source.stat().st_size == prepared.jobs[0].scan.result.source.size_bytes
    result = execute_deep(prepared)

    assert not result.successes
    assert isinstance(result.failures[0].error, StaleSource)
    assert "discarded" in str(result.failures[0].error)
    assert not deep_path.exists()

    # A longer file is refused before any reading.
    source.write_text(source.read_text(encoding="utf-8") + "9999\n", encoding="utf-8", newline="")
    longer = execute_deep(prepared)
    assert isinstance(longer.failures[0].error, StaleSource) and not deep_path.exists()


@pytest.mark.scan_json_lot("7a")
def test_D05_a_source_that_cannot_be_read_again_leaves_the_scan_and_no_document(
    tmp_path, monkeypatch
):
    _home(monkeypatch, tmp_path)
    source = write_text(
        tmp_path, "ids.csv", "n\n" + "\n".join(str(1000 + n) for n in range(300)) + "\n"
    )
    prepared = prepare_deep([source])
    scan_path = prepared.jobs[0].scan.job.output
    before = sorted(p.name for p in scan_path.parent.iterdir())
    source.unlink()

    result = execute_deep(prepared)

    error = result.failures[0].error
    assert isinstance(error, SourceNotReadable) and isinstance(error, InputError)
    assert "still valid" in str(error)
    # The Scan and its plan are there; nothing was written or copied.
    assert scan_path.exists() and prepared.jobs[0].second.plan.summary.selected
    assert sorted(p.name for p in scan_path.parent.iterdir()) == before


# D09 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7a")
def test_D09_a_histogram_counts_every_value_once_and_the_maximum_in_the_last_bin(tmp_path):
    rows = [f"{n / 10:.1f}" for n in range(11)] * 3 + ["0.3", "0.3"]
    _, _, outcome = deep_csv(tmp_path, "x", rows, deep=DeepSettings(bins=10))

    histogram = entry(outcome, "numeric_histogram", "x").result

    assert histogram.kind == "bins" and histogram.count == len(rows)
    assert sum(histogram.counts) == len(rows) and histogram.outside.below == histogram.outside.above == 0
    assert (histogram.min, histogram.max) == (0, 1)
    assert histogram.edges == [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]
    # 0.3 sits exactly on an edge: it starts the bin it opens, not the one it closes.
    assert histogram.counts[2] == 3 and histogram.counts[3] == 5
    # The maximum has its place in the last bin (no bin of its own).
    assert histogram.counts[9] == 3 + 3 and len(histogram.counts) == 10


@pytest.mark.scan_json_lot("7a")
def test_D09_every_value_lands_in_the_bin_an_exhaustive_oracle_gives_it(tmp_path):
    rng = random.Random(5)
    rows = [f"{rng.uniform(-50, 5000):.3f}" for _ in range(1500)]
    _, _, outcome = deep_csv(tmp_path, "x", rows, deep=DeepSettings(bins=37))

    histogram = entry(outcome, "numeric_histogram", "x").result

    low, high = Fraction(histogram.edges[0]), Fraction(histogram.edges[-1])
    expected = [0] * 37
    for text in rows:
        position = int((Fraction(Decimal(text)) - low) * 37 / (high - low))
        expected[min(37 - 1, max(0, position))] += 1
    assert histogram.counts == expected


@pytest.mark.scan_json_lot("7a")
def test_D09_integers_beyond_float64_are_placed_exactly(tmp_path):
    base = 10**30
    step = 10**20  # a domain far too wide for counters: the field is binned
    rows = [str(base + n * step) for n in range(200)]
    _, _, outcome = deep_csv(tmp_path, "big", rows, deep=DeepSettings(bins=8))

    histogram = entry(outcome, "numeric_histogram", "big").result

    low = base
    expected = [0] * 8
    for n in range(200):
        value = base + n * step
        expected[min(7, (value - low) * 8 // (199 * step))] += 1
    assert histogram.counts == expected and histogram.min == base


@pytest.mark.scan_json_lot("7a")
def test_D09_a_constant_or_empty_field_asks_for_no_histogram(tmp_path):
    result = scan_csv(tmp_path, "constant,empty", ["5,", "5,", "5,"])

    plan = forced_plan(result)

    assert not [c for c in plan.candidates if c.analyzer == "numeric_histogram"
                and c.selection.state == "selected"]  # fmt: skip
    from tabalyst.scanner.secondpass.bins import BinEdges, linear_edges

    # A degenerate range still has one bin and never divides by zero.
    edges = BinEdges(linear_edges(Fraction(5), Fraction(5), 10))
    assert edges.bins == 1 and edges.index(5) == 0 and edges.index(6) == 1


# D10 ---------------------------------------------------------------------------


@pytest.mark.scan_json_lot("7a")
def test_D10_a_dense_integer_domain_gives_the_exact_mode_median_and_quantiles(tmp_path):
    values = [3, 1, 2, 2, 5, 5, 4, 9, 9, 9, 9, 1, 2, 2]
    _, _, outcome = deep_csv(tmp_path, "n", [str(v) for v in values])

    histogram = entry(outcome, "numeric_histogram", "n").result

    assert histogram.kind == "dense_counts" and histogram.count == len(values)
    counts = {v: values.count(v) for v in set(values)}
    assert {(item.value, item.count) for item in histogram.values} == set(counts.items())
    assert histogram.distinct == len(counts)
    # The mode is the most frequent value, all of them when they tie.
    assert histogram.modes == [v for v in sorted(counts) if counts[v] == max(counts.values())]
    # The median of an even count is the mean of the two central values.
    assert histogram.median.accuracy == "exact"
    assert histogram.median.value == true_quantile([Fraction(v) for v in values], Fraction(1, 2))
    for quantile in histogram.quantiles:
        truth = true_quantile([Fraction(v) for v in values], LEVELS[quantile.level])
        assert (quantile.value, quantile.accuracy) == (float(truth), "exact") or quantile.value == truth


@pytest.mark.scan_json_lot("7a")
def test_D10_ties_for_the_mode_are_all_listed(tmp_path):
    _, _, outcome = deep_csv(tmp_path, "n", ["1", "1", "2", "2", "3"])

    histogram = entry(outcome, "numeric_histogram", "n").result

    assert histogram.modes == [1, 2] and histogram.modes_truncated is False
    assert histogram.median.value == 2


# D11 ---------------------------------------------------------------------------


def _skewed(count=3000, seed=21):
    rng = random.Random(seed)
    return [f"{rng.expovariate(1 / 40):.2f}" for _ in range(count)]


@pytest.mark.scan_json_lot("7a")
def test_D11_grouped_bins_keep_exact_counts_and_bound_the_estimated_quantiles(tmp_path):
    rows = _skewed()
    _, _, outcome = deep_csv(tmp_path, "x", rows, deep=DeepSettings(bins=20))

    histogram = entry(outcome, "numeric_histogram", "x").result

    exact = [Fraction(Decimal(r)) for r in rows]
    assert histogram.count == len(rows) and sum(histogram.counts) == len(rows)
    for quantile in histogram.quantiles:
        truth = float(true_quantile(exact, LEVELS[quantile.level]))
        assert quantile.accuracy == "estimated"
        assert quantile.lower <= truth <= quantile.upper
        assert quantile.lower <= quantile.value <= quantile.upper


@pytest.mark.scan_json_lot("7a")
def test_D11_bounds_from_the_sample_follow_a_skewed_distribution_with_exact_counts(tmp_path):
    rows = _skewed()
    deep = DeepSettings(bins=20, bin_strategy="sample_quantile")
    _, _, outcome = deep_csv(tmp_path, "x", rows, deep=deep, records={"sample": {"rows": 500}})

    histogram = entry(outcome, "numeric_histogram", "x").result

    assert histogram.strategy == "sample_quantile" and histogram.bounds_source == "rows"
    edges = [Fraction(Decimal(repr(edge))) for edge in histogram.edges]
    assert edges == sorted(set(edges)) and len(histogram.counts) == len(edges) - 1
    # The counts are those of the whole source, whatever the sample was.
    expected = [0] * len(histogram.counts)
    for text in rows:
        x = Fraction(Decimal(text))
        index = max(i for i in range(len(edges) - 1) if edges[i] <= x)
        expected[index] += 1
    assert histogram.counts == expected
    # Equal widths would pile the skewed values into the first bins.
    (tmp_path / "linear").mkdir()
    other = deep_csv(tmp_path / "linear", "x", rows, deep=DeepSettings(bins=20))[2]
    linear = entry(other, "numeric_histogram", "x").result
    assert max(histogram.counts) < max(linear.counts)


@pytest.mark.scan_json_lot("7a")
def test_D11_a_sample_too_small_falls_back_to_equal_widths_and_says_why(tmp_path):
    rows = [f"{n * 1.5:.1f}" for n in range(300)]
    deep = DeepSettings(bins=100, bin_strategy="sample_quantile")
    _, _, outcome = deep_csv(
        tmp_path, "x", rows, deep=deep, records={"sample": {"rows": 20, "edge": 5}},
        limits={"max_samples": 20},
    )  # fmt: skip

    histogram = entry(outcome, "numeric_histogram", "x").result

    assert (histogram.requested_strategy, histogram.strategy) == ("sample_quantile", "linear")
    assert histogram.bounds_source == "range" and histogram.reason == "sample_too_small"
