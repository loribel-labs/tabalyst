# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract of the bottom-k samplers (Scan and JSON plan, tests B01 to B13).

The behavior is specified in ``docs/dev/scan/design.md`` section 18 (decision
O26). Each test names the lot that delivers it; it is expected to fail until
that lot is added to ``SCAN_JSON_ENABLED_LOTS`` (see ``conftest.py``). The
oracles are exhaustive counts computed by the test itself.

Interfaces named here are the contract of lots 2a to 3a: a lot may refine a
name together with the design document, never silently.
"""

import math
import os
import random
import statistics
import subprocess
import sys
import tracemalloc
from collections import Counter
from pathlib import Path

import pytest
from scan_helpers import dataset, field, run_scan, write_text

K = 5
SRC = str(Path(__file__).resolve().parents[2] / "src")


def _key(text: str, type_: str = "string") -> tuple[str, str]:
    return (type_, text)


def _stream(sampler, keys) -> None:
    for item in keys:
        sampler.add(item)


def _oracle(keys, k, *, seed=0, priority=None):
    """The k smallest priorities among the distinct keys, with exact counts."""
    from tabalyst.scanner import bottomk

    rank = priority or (lambda item: bottomk.priority(item, seed=seed))
    counts = Counter(keys)
    ordered = sorted(counts, key=lambda item: (rank(item), item))[:k]
    return [(item, rank(item), counts[item]) for item in ordered]


def _entries(sampler):
    return [(item.key, item.priority, item.count) for item in sampler.entries()]


def _distinct_keys(count: int) -> list[tuple[str, str]]:
    return [_key(f"id-{index:08d}") for index in range(count)]


@pytest.mark.scan_json_lot("2a")
@pytest.mark.parametrize("distinct", [0, 1, K - 1, K, K + 1])
def test_B01_exact_up_to_k_then_explicit_overflow(distinct):
    from tabalyst.scanner.bottomk import BottomKSampler

    keys = _distinct_keys(distinct)
    stream = keys + keys[: distinct // 2]
    sampler = BottomKSampler(K)
    _stream(sampler, stream)

    assert sampler.occurrences == len(stream)
    if distinct <= K:
        assert sampler.distinct_exact is True
        assert sampler.overflow_at_occurrence is None
        assert sampler.threshold is None
        # Everything is kept, with exact counts.
        assert _entries(sampler) == _oracle(stream, K)
    else:
        # The first occurrence of the (K + 1)th distinct value proves overflow.
        assert sampler.distinct_exact is False
        assert sampler.overflow_at_occurrence == K + 1
        assert len(sampler.entries()) == K
        assert _entries(sampler) == _oracle(stream, K)
        assert sampler.threshold == sampler.entries()[-1].priority


@pytest.mark.scan_json_lot("2a")
def test_B01_a_larger_exact_table_gives_the_sample_of_streaming_its_keys():
    from tabalyst.scanner.bottomk import BottomKSampler

    rng = random.Random(9)
    stream = [_key(f"v{rng.randrange(60)}") for _ in range(900)]
    streamed = BottomKSampler(K)
    _stream(streamed, stream)

    seeded = BottomKSampler.from_exact(K, Counter(stream))

    assert _entries(seeded) == _entries(streamed) == _oracle(stream, K)
    assert seeded.distinct_exact is False
    assert seeded.threshold == streamed.threshold
    assert seeded.occurrences == len(stream)
    # Later occurrences continue as if the sample had been streamed.
    more = [_key(f"v{rng.randrange(120)}") for _ in range(300)]
    _stream(seeded, more)
    _stream(streamed, more)
    assert _entries(seeded) == _entries(streamed) == _oracle(stream + more, K)


@pytest.mark.scan_json_lot("2a")
def test_B02_same_stream_and_seed_give_the_same_sample_in_any_process():
    from tabalyst.scanner.bottomk import BottomKSampler

    rng = random.Random(7)
    stream = [_key(f"v{rng.randrange(400)}") for _ in range(3000)]
    first, second = BottomKSampler(20, seed=3), BottomKSampler(20, seed=3)
    _stream(first, stream)
    _stream(second, stream)
    assert _entries(first) == _entries(second)
    assert _entries(first) != _entries(_fed(BottomKSampler(20, seed=4), stream))

    # The priority never depends on the process (no builtin hash()).
    code = (
        "from tabalyst.scanner.bottomk import priority;"
        "print(priority(('string', 'caf\\u00e9'), seed=3))"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            env={
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONPATH": os.pathsep.join([SRC, os.environ.get("PYTHONPATH", "")]),
            },
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2")
    }
    assert len(outputs) == 1


def _fed(sampler, stream):
    _stream(sampler, stream)
    return sampler


@pytest.mark.scan_json_lot("2a")
def test_B03_permuting_the_stream_gives_the_same_sample_and_counts():
    from tabalyst.scanner.bottomk import BottomKSampler

    rng = random.Random(11)
    stream = [_key(f"v{int(rng.paretovariate(1.2))}") for _ in range(3000)]
    shuffled = stream[:]
    random.Random(12).shuffle(shuffled)

    first, second = BottomKSampler(30), BottomKSampler(30)
    _stream(first, stream)
    _stream(second, shuffled)

    assert _entries(first) == _entries(second)


@pytest.mark.scan_json_lot("2a")
def test_B04_an_evicted_value_never_comes_back_and_no_count_is_wrong():
    from tabalyst.scanner.bottomk import BottomKSampler

    priorities = {_key("a"): 100, _key("b"): 200, _key("c"): 300, _key("z"): 50}
    sampler = BottomKSampler(2, priority=priorities.__getitem__)
    # "c" is the worst of the first three and leaves at overflow; it is then
    # frequent, but a rejected identity does not re-enter.
    stream = [_key("a"), _key("b"), _key("c")] + [_key("c")] * 5 + [_key("a")]
    _stream(sampler, stream)
    assert _entries(sampler) == [(_key("a"), 100, 2), (_key("b"), 200, 1)]

    # A better value replaces the worst retained one; "b" does not come back.
    _stream(sampler, [_key("z"), _key("b"), _key("z")])
    assert _entries(sampler) == [(_key("z"), 50, 2), (_key("a"), 100, 2)]
    assert sampler.threshold == 100


@pytest.mark.scan_json_lot("2a")
def test_B05_final_occurrences_equal_the_exhaustive_oracle_at_any_prefix():
    from tabalyst.scanner.bottomk import BottomKSampler

    rng = random.Random(5)
    stream = [_key(f"v{int(rng.paretovariate(0.9)) % 2000}") for _ in range(6000)]
    sampler = BottomKSampler(100)
    done = 0
    for prefix in (60, 400, 2500, 6000):  # before and after the overflow
        _stream(sampler, stream[done:prefix])
        done = prefix
        assert _entries(sampler) == _oracle(stream[:prefix], 100)


@pytest.mark.scan_json_lot("2a")
def test_B06_equal_priorities_keep_distinct_values_apart_with_a_stable_tie_break():
    from tabalyst.scanner.bottomk import BottomKSampler

    sampler = BottomKSampler(2, priority=lambda item: 7)
    stream = [
        _key("b"),
        _key("a"),
        _key("c"),
        _key("a"),
        _key("1", "integer"),
        _key("1"),
    ]
    _stream(sampler, stream)

    # Ties break on the complete key, (type, text) ascending: never a merge.
    assert _entries(sampler) == [(_key("1", "integer"), 7, 1), (_key("1"), 7, 1)]
    reversed_run = BottomKSampler(2, priority=lambda item: 7)
    _stream(reversed_run, stream[::-1])
    assert _entries(reversed_run) == _entries(sampler)


@pytest.mark.scan_json_lot("3a")
def test_B11_more_length_strata_than_the_cap_are_limited_and_visible():
    # The exact scalar min, max and mean of lengths stay with the engine's
    # `string_lengths` block, covered by tests/scan/test_scan_measures.py.
    from tabalyst.scanner.lengthsample import LengthStrataSampler

    sampler = LengthStrataSampler(per_length_k=2, max_lengths=3)
    for length in range(1, 7):
        sampler.add(_key("x" * length))

    assert sorted(sampler.strata()) == [1, 2, 3]
    assert sampler.limited is True
    assert sampler.other.lengths == 3
    assert sampler.other.occurrences == 3
    assert 4 not in sampler.strata()


@pytest.mark.scan_json_lot("3a")
def test_B12_a_stratum_admitted_late_never_claims_exact_counts():
    from tabalyst.scanner.lengthsample import LengthStrataSampler

    sampler = LengthStrataSampler(per_length_k=2, max_lengths=2)
    for text in ("a", "bb", "a"):
        sampler.add(_key(text))
    exact = sampler.strata()[1]
    assert exact.count_accuracy == "exact"
    assert exact.tracking_started_at_occurrence == 1

    sampler.drop(1)  # the memory budget gives a stratum up
    sampler.add(_key("c"))
    sampler.add(_key("c"))
    late = sampler.strata()[1]
    assert late.count_accuracy == "partial"
    assert late.tracking_started_at_occurrence == 4  # the first "c"
    assert [item.count for item in late.entries()] == [2]
    assert sampler.strata()[2].count_accuracy == "exact"


@pytest.mark.scan_json_lot("2a")
def test_B09_k_can_shrink_to_the_smallest_priorities_but_never_grow():
    from tabalyst.scanner.bottomk import BottomKSampler

    stream = _distinct_keys(30) + _distinct_keys(10)
    sampler = BottomKSampler(8)
    _stream(sampler, stream)
    before = _entries(sampler)

    sampler.reduce(3)

    assert sampler.k == 3
    assert _entries(sampler) == before[:3]
    assert sampler.threshold == before[2][1]
    assert sampler.distinct_exact is False
    with pytest.raises(ValueError):
        sampler.reduce(4)


@pytest.mark.scan_json_lot("2a")
def test_B13_kmv_formula_normalization_and_invalid_parameters():
    from tabalyst.scanner.bottomk import BottomKSampler, kmv_estimate

    half = kmv_estimate(threshold=2**127, k=11)
    assert half.estimate == 20.0  # (k - 1) / theta, theta = 1/2
    assert half.relative_standard_error == pytest.approx(1 / 3)
    assert half.theta_hex == "8" + "0" * 31

    tiny = kmv_estimate(threshold=1, k=1000)  # theta near zero stays finite
    assert math.isfinite(tiny.estimate)
    assert tiny.estimate == 999 * 2.0**128
    assert tiny.theta_hex == "0" * 31 + "1"

    for threshold, k in [(0, 10), (2**128, 10), (5, 2), (5, 0)]:
        with pytest.raises(ValueError):
            kmv_estimate(threshold=threshold, k=k)

    exact = BottomKSampler(10)
    _stream(exact, _distinct_keys(4))
    assert exact.kmv() is None  # still exact: no estimate (KMV-01)
    assert BottomKSampler(2).kmv() is None  # k too small


@pytest.mark.scan_json_lot("2a")
def test_B13_kmv_errors_follow_the_model_over_several_datasets_and_seeds():
    from tabalyst.scanner.bottomk import BottomKSampler

    k, seeds = 128, range(30)
    rse = 1 / math.sqrt(k - 2)
    for distinct in (3000, 10000):
        keys = _distinct_keys(distinct)
        errors = []
        for seed in seeds:
            sampler = BottomKSampler(k, seed=seed)
            _stream(sampler, keys)
            errors.append(sampler.kmv().estimate / distinct - 1)
        # Tolerant statistical control, reproducible (fixed seeds): the
        # estimator is unbiased, and about 95% of errors fall within 2 RSE.
        assert abs(statistics.fmean(errors)) < 4 * rse / math.sqrt(len(errors))
        within = sum(abs(error) <= 2 * rse for error in errors)
        assert within >= 0.8 * len(errors)


@pytest.mark.scan_json_lot("2c")
def test_B07_long_texts_with_one_prefix_keep_distinct_fingerprint_identities():
    from tabalyst.scanner.longtext import LongTextSampler

    prefix = "p" * 500
    texts = [prefix + suffix for suffix in ("alpha", "beta", "gamma")]
    sampler = LongTextSampler(10, preview_chars=100)
    for text in texts + [texts[0]]:
        sampler.add(text)

    entries = sampler.entries()
    assert len(entries) == 3
    assert len({item.digest for item in entries}) == 3
    assert {item.count for item in entries} == {1, 2}
    for item in entries:
        assert item.preview == prefix[:100]
        assert item.truncated is True
        assert item.identity_accuracy == "fingerprint_based"
    assert sorted(item.original_length_chars for item in entries) == [504, 505, 505]


@pytest.mark.scan_json_lot("2c")
def test_B08_previews_cut_on_code_points_and_report_original_lengths():
    from tabalyst.scanner.longtext import LongTextSampler

    text = "a" + "\N{GRINNING FACE}" * 50 + "é́"
    sampler = LongTextSampler(5, preview_chars=10)
    sampler.add(text)

    (item,) = sampler.entries()
    assert item.preview == text[:10]
    assert item.preview.encode("utf-8").decode("utf-8") == item.preview
    assert item.truncated is True
    assert item.original_length_chars == len(text)
    assert item.original_length_bytes == len(text.encode("utf-8"))

    short = LongTextSampler(5, preview_chars=100)
    short.add("café")
    (kept,) = short.entries()
    assert kept.truncated is False
    assert (kept.original_length_chars, kept.original_length_bytes) == (4, 5)


def _identifier_csv(tmp_path, rows):
    lines = "\n".join(f"{value}" for value in rows)
    return write_text(tmp_path, "ids.csv", f"id\n{lines}\n")


def _samples(result):
    return field(dataset(result, "rows"), "id")["values"]["samples"]


@pytest.mark.scan_json_lot("2b")
def test_B02_scan_sample_is_identical_across_runs_and_worker_counts(tmp_path):
    from tabalyst import ScanConfig, scan

    rng = random.Random(21)
    source = _identifier_csv(
        tmp_path, [f"id{rng.randrange(300):04d}" for _ in range(2000)]
    )
    config = ScanConfig.model_validate(
        {"limits": {"max_distinct_per_field": 50, "max_samples": 50}}
    )

    documents = [
        scan(source, config=config, workers=workers).model_dump(mode="json")
        for workers in (1, 1, 2)
    ]

    samples = [_samples(document) for document in documents]
    assert samples[0]["selection"] == "bottom_k"
    assert len(samples[0]["listed"]) == 50
    assert samples[0] == samples[1] == samples[2]


@pytest.mark.scan_json_lot("2b")
def test_B03_scan_sample_does_not_depend_on_row_order(tmp_path):
    rng = random.Random(22)
    values = [f"id{int(rng.paretovariate(1.1)):05d}" for _ in range(3000)]
    shuffled = values[:]
    random.Random(23).shuffle(shuffled)
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    limits = {"max_distinct_per_field": 30, "max_samples": 30}

    left = _samples(run_scan(_identifier_csv(first, values), limits=limits))
    right = _samples(run_scan(_identifier_csv(second, shuffled), limits=limits))

    assert left["selection"] == "bottom_k"
    assert left["listed"] == right["listed"]


@pytest.mark.scan_json_lot("2b")
def test_B05_scan_sample_counts_equal_the_exhaustive_oracle(tmp_path):
    rng = random.Random(24)
    values = [f"id{int(rng.paretovariate(0.9)) % 1500:05d}" for _ in range(5000)]
    oracle = Counter(values)

    samples = _samples(
        run_scan(
            _identifier_csv(tmp_path, values),
            limits={"max_distinct_per_field": 80, "max_samples": 80},
        )
    )

    assert samples["selection"] == "bottom_k"
    assert len(samples["listed"]) == 80
    for entry in samples["listed"]:
        assert entry["count"] == oracle[entry["value"]]
        assert entry["count_accuracy"] == "exact"


@pytest.mark.scan_json_lot("2b")
def test_B10_scan_analytical_memory_does_not_grow_with_unique_values(tmp_path):
    def peak(rows: int) -> tuple[int, dict]:
        directory = tmp_path / str(rows)
        directory.mkdir()
        source = _identifier_csv(directory, [f"id{index:09d}" for index in range(rows)])
        tracemalloc.start()
        try:
            result = run_scan(
                source,
                limits={"max_distinct_per_field": 1000, "max_samples": 1000},
                records={"duplicates": False},
            )
            return tracemalloc.get_traced_memory()[1], result
        finally:
            tracemalloc.stop()

    peak(2_000)  # warm-up: lazy imports and compiled patterns are one-time
    small, _ = peak(30_000)
    large, result = peak(120_000)

    assert _samples(result)["selection"] == "bottom_k"
    assert len(_samples(result)["listed"]) == 1000
    # Four times the unique values, about the same analytical memory.
    assert large < small * 1.1


@pytest.mark.scan_json_lot("2b")
def test_A18_samples_keep_the_original_variants_while_frequencies_merge_them(tmp_path):
    variants = ["Café", "Cafe\u0301", " Café ", "CAFÉ", "Cafe"]
    source = write_text(tmp_path, "v.csv", "v\n" + "\n".join(variants * 2) + "\n")

    values = field(dataset(run_scan(source), "rows"), "v")["values"]

    assert values["cardinality"]["value"] == 5
    assert values["cardinality"]["domain"] == "original"
    assert [item["value"] for item in values["samples"]["listed"]] == variants
    assert {item["count"] for item in values["samples"]["listed"]} == {2}
    # The analytical value (NFC, trim, collapse) merges the first three.
    assert values["frequencies"]["value"]["distinct"] == 3
    assert values["frequencies"]["value"]["listed"][0] == {
        "value": "Café",
        "type": "string",
        "count": 6,
    }
