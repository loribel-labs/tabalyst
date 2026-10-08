# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Samples by length of the original text: the sampler, its output in the Scan,
its memory budget and its exposure (design 18.7, lot 3a)."""

import json
import random
import tracemalloc
from collections import Counter, defaultdict

import pytest
from scan_helpers import dataset, field, run_scan, write_text

from tabalyst.scanner import bottomk
from tabalyst.scanner.lengthsample import LengthStrataSampler
from tabalyst.scanner.validation import check_scan

pytestmark = pytest.mark.scan_json_lot("3a")

SECRET = {"id": "secret", "regex": r"S-\d{2}", "sensitive": True}
K = 5


def _key(text: str, type_: str = "string") -> tuple[str, str]:
    return (type_, text)


def _stream(sampler, texts, counts=None):
    counts = counts or [1] * len(texts)
    keys = [_key(text) for text in texts]
    sampler.update(keys, counts, bottomk.priorities(keys, seed=sampler.seed))


def _oracle(texts, counts, per_length_k, seed=0):
    """Per length: the k smallest priorities with their exact counts."""
    by_length = defaultdict(Counter)
    for text, count in zip(texts, counts, strict=True):
        by_length[len(text)][_key(text)] += count
    return {
        length: [
            (key, table[key])
            for key in sorted(
                table, key=lambda key: (bottomk.priority(key, seed=seed), key)
            )[:per_length_k]
        ]
        for length, table in by_length.items()
    }


def _csv(tmp_path, rows, name="v.csv"):
    return write_text(tmp_path, name, "v\n" + "\n".join(rows) + "\n")


def _values(result, name="v"):
    return field(dataset(result, "rows"), name)["values"]


def _mixed(rng: random.Random, count: int) -> list[str]:
    """Many identifiers of 8 characters, a few of other lengths."""
    rare = ["ab", "abc", "abcd", "abcde", "abcdef"]
    rows = [f"id{n:06d}" for n in range(count)]
    rows += [rng.choice(rare) + "x" * (n % 3) for n in range(10)]
    rng.shuffle(rows)
    return rows


# The sampler ---------------------------------------------------------------------


def test_a_stratum_keeps_the_smallest_priorities_of_its_length_with_exact_counts():
    rng = random.Random(3)
    texts = [f"{rng.randrange(10**6):06d}"[: rng.choice([3, 5, 6])] for _ in range(600)]
    texts = list(dict.fromkeys(texts))
    counts = [rng.randrange(1, 5) for _ in texts]
    sampler = LengthStrataSampler(per_length_k=K, max_lengths=10)

    _stream(sampler, texts, counts)

    expected = _oracle(texts, counts, K)
    assert sorted(sampler.strata()) == sorted(expected)
    for length, stratum in sampler.strata().items():
        assert [(entry.key, entry.count) for entry in stratum.entries()] == expected[length]
        assert stratum.count_accuracy == "exact"
    assert not sampler.limited


def test_the_strata_and_other_add_up_to_every_occurrence_even_after_a_drop():
    sampler = LengthStrataSampler(per_length_k=2, max_lengths=3)
    texts = ["a", "bb", "ccc", "dddd", "eeeee", "a", "dddd", "bb"]
    _stream(sampler, texts, [2, 1, 3, 4, 5, 1, 1, 1])

    def total():
        held = sum(s.occurrences for s in sampler.strata().values())
        return held + sampler.other.occurrences

    assert total() == sampler.occurrences == 18
    sampler.drop(2)
    assert total() == 18
    assert sampler.other.occurrences == 10 + 2 and sampler.other.lengths == 3
    assert sampler.limited


def test_an_untracked_length_is_admitted_late_after_a_drop():
    sampler = LengthStrataSampler(per_length_k=2, max_lengths=1)
    _stream(sampler, ["a", "bb", "bb", "a"])
    assert sorted(sampler.strata()) == [1] and sampler.other.lengths == 1

    sampler.drop(1)
    _stream(sampler, ["bb"])

    late = sampler.strata()[2]
    assert late.count_accuracy == "partial"
    assert late.tracking_started_at_occurrence == 5
    assert [entry.count for entry in late.entries()] == [1]
    assert sampler.other.lengths == 1  # the length 1 is untracked now


def test_dropping_a_length_that_is_not_tracked_does_nothing():
    sampler = LengthStrataSampler(per_length_k=2, max_lengths=2)
    _stream(sampler, ["a"])

    sampler.drop(9)

    assert sorted(sampler.strata()) == [1] and not sampler.limited


@pytest.mark.parametrize("typed", [False, True])
def test_seeding_from_an_exact_table_equals_streaming_the_same_values(typed):
    rng = random.Random(8)
    texts = list(dict.fromkeys(f"{rng.randrange(10**7)}"[: rng.randint(1, 7)] for _ in range(800)))
    counts = [rng.randrange(1, 6) for _ in texts]
    keys = [_key(text) for text in texts]
    values = bottomk.priorities(keys)

    streamed = LengthStrataSampler(per_length_k=4, max_lengths=4)
    streamed.update(keys, counts, values)
    if typed:
        seeded = LengthStrataSampler.from_exact(4, 4, keys, counts, values)
    else:
        seeded = LengthStrataSampler.from_exact_strings(4, 4, texts, counts, values)

    assert seeded.occurrences == streamed.occurrences
    assert (seeded.other.lengths, seeded.other.occurrences) == (
        streamed.other.lengths,
        streamed.other.occurrences,
    )
    assert sorted(seeded.strata()) == sorted(streamed.strata())
    for length, stratum in streamed.strata().items():
        mine = seeded.strata()[length]
        assert mine.entries() == stratum.entries()
        assert mine.occurrences == stratum.occurrences
        assert mine.count_accuracy == stratum.count_accuracy
        assert mine.tracking_started_at_occurrence == stratum.tracking_started_at_occurrence


def test_the_batch_boundaries_do_not_change_the_strata():
    rng = random.Random(1)
    texts = list(dict.fromkeys(f"{rng.randrange(10**6)}"[: rng.randint(1, 6)] for _ in range(900)))
    whole = LengthStrataSampler(per_length_k=3, max_lengths=3)
    pieces = LengthStrataSampler(per_length_k=3, max_lengths=3)

    _stream(whole, texts)
    for start in range(0, len(texts), 37):
        _stream(pieces, texts[start : start + 37])

    for length, stratum in whole.strata().items():
        assert pieces.strata()[length].entries() == stratum.entries()
    assert pieces.other.lengths == whole.other.lengths
    assert pieces.other.occurrences == whole.other.occurrences


def test_a_sampler_needs_a_positive_size_and_length_cap():
    with pytest.raises(ValueError):
        LengthStrataSampler(per_length_k=0, max_lengths=1)
    with pytest.raises(ValueError):
        LengthStrataSampler(per_length_k=1, max_lengths=0)


# In the Scan ---------------------------------------------------------------------

LIMITS = {"max_distinct_per_field": 100, "max_samples": 50}


def _check_block(result, values, count):
    """Every id points to a value of the stratum's length; the strata and
    ``other`` add up to the stored values."""
    samples = values["samples"]
    block = samples["by_length"]
    entries = {item["id"]: item for item in samples["listed"] + block["listed"]}
    for stratum in block["strata"]:
        for entry_id in stratum["ids"]:
            assert len(entries[entry_id]["value"]) == stratum["length"]
    held = sum(stratum["occurrences"] for stratum in block["strata"])
    assert held + block.get("other", {"occurrences": 0})["occurrences"] == count
    assert check_scan_document(result) == []
    return block


def check_scan_document(result):
    from tabalyst.scanner.models import ScanResult

    return check_scan(ScanResult.model_validate(result))


def test_a_rare_length_is_visible_in_a_bottom_k_field(tmp_path):
    rows = _mixed(random.Random(2), 3_000)
    result = run_scan(_csv(tmp_path, rows), limits=LIMITS)

    values = _values(result)
    block = _check_block(result, values, len(rows))
    samples = values["samples"]
    assert samples["selection"] == "bottom_k"
    strata = {stratum["length"]: stratum for stratum in block["strata"]}
    # 3,000 identifiers against 50 sampled values: the rare lengths are listed
    # by their own strata, with exact counts.
    rare = [length for length in strata if length != 8]
    assert rare and all(strata[length]["count_accuracy"] == "exact" for length in rare)
    assert all(strata[length]["selection"] == "all" for length in rare)
    assert sum(strata[length]["occurrences"] for length in rare) == 10
    assert block["domain"] == "original" and block["unit"] == "characters"
    assert (block["per_length_k"], block["max_lengths"]) == (100, 64)
    assert block["limited"] is False and "other" not in block
    # The stratum of the identifiers is full: a bottom-k with a threshold, its
    # values are already in the sample for the most part, not copied.
    ids = strata[8]
    assert ids["selection"] == "bottom_k" and ids["threshold"]
    assert (ids["kept"], ids["of"]) == (100, 100)
    pool = {item["id"] for item in block["listed"]}
    sample_ids = {item["id"] for item in samples["listed"]}
    assert pool and pool.isdisjoint(sample_ids)
    assert min(pool) == len(samples["listed"])


def test_strata_exact_counts_equal_the_exhaustive_counts(tmp_path):
    rows = _mixed(random.Random(4), 2_000)
    result = run_scan(_csv(tmp_path, rows), limits=LIMITS)

    values = _values(result)
    block = _check_block(result, values, len(rows))
    entries = {item["id"]: item for item in values["samples"]["listed"] + block["listed"]}
    truth = Counter(rows)
    for stratum in block["strata"]:
        for entry_id in stratum["ids"]:
            entry = entries[entry_id]
            assert entry["count"] == truth[entry["value"]]
    lengths = Counter(len(row) for row in rows)
    for stratum in block["strata"]:
        assert stratum["occurrences"] == lengths[stratum["length"]]


def test_a_field_whose_sample_lists_every_value_has_no_strata(tmp_path):
    result = run_scan(_csv(tmp_path, ["a", "bb", "ccc", "a"]), limits=LIMITS)

    assert "by_length" not in _values(result)["samples"]


def test_typed_values_get_strata_by_the_length_of_their_text(tmp_path):
    rows = list(range(1, 300)) + [7] * 4
    source = write_text(tmp_path, "v.json", json.dumps([{"v": row} for row in rows]))
    result = run_scan(source, limits=LIMITS)

    values = field(dataset(result, "$[]"), "v")["values"]
    block = _check_block(result, values, len(rows))
    assert [stratum["length"] for stratum in block["strata"]] == [1, 2, 3]
    assert {item["type"] for item in values["samples"]["listed"]} == {"integer"}


def test_the_samples_by_length_can_be_turned_off(tmp_path):
    rows = _mixed(random.Random(2), 500)
    for limits in (
        {**LIMITS, "max_samples_per_length": 0},
        {**LIMITS, "max_length_strata": 0},
    ):
        result = run_scan(_csv(tmp_path, rows), limits=limits)

        assert "by_length" not in _values(result)["samples"]


def test_lengths_beyond_the_cap_are_summed_in_other(tmp_path):
    rows = ["x" * length for length in range(1, 41) for _ in range(3)]
    result = run_scan(
        _csv(tmp_path, rows), limits={**LIMITS, "max_samples": 30, "max_length_strata": 8}
    )

    values = _values(result)
    block = _check_block(result, values, len(rows))
    assert block["limited"] is True and block["tracked"] == 8
    assert [stratum["length"] for stratum in block["strata"]] == list(range(1, 9))
    assert block["other"] == {"lengths": 32, "occurrences": 96}
    assert "requested_max_lengths" not in block  # the cap is the setting, not the budget


@pytest.mark.parametrize("source", ["csv", "json"])
def test_the_strata_do_not_depend_on_the_workers(tmp_path, source):
    from tabalyst import ScanConfig, scan

    rows = _mixed(random.Random(6), 5_000)
    if source == "csv":
        path = _csv(tmp_path, rows)
    else:
        path = write_text(
            tmp_path, "v.json", json.dumps([{"v": row} for row in rows])
        )
    config = ScanConfig.model_validate({"limits": LIMITS})

    documents = [
        scan(path, config=config, workers=workers).model_dump(mode="json")
        for workers in (1, 2)
    ]

    def block(document):
        name = "rows" if source == "csv" else "$[]"
        return field(dataset(document, name), "v")["values"]["samples"]["by_length"]

    assert block(documents[0]) == block(documents[1])
    assert block(documents[0])["strata"]


def test_a_sensitive_field_lists_no_value_of_its_strata(tmp_path):
    rows = [f"S-{n:02d}" for n in range(60)] + ["S-1", "S-22222"]
    result = run_scan(_csv(tmp_path, rows), limits=LIMITS, patterns=[SECRET])

    values = _values(result)
    assert field(dataset(result, "rows"), "v")["sensitive"]
    block = values["samples"]["by_length"]
    assert block["listed"] == []
    assert all(stratum["kept"] == 0 and stratum["ids"] == [] for stratum in block["strata"])
    assert all("threshold" not in stratum for stratum in block["strata"])
    assert sum(stratum["of"] for stratum in block["strata"]) > 0
    assert check_scan_document(result) == []


def test_values_longer_than_the_stored_length_stay_out_of_the_strata(tmp_path):
    rows = [f"id{n:05d}" for n in range(300)] + ["z" * 1_500, "y" * 1_600]
    result = run_scan(_csv(tmp_path, rows), limits=LIMITS)

    values = _values(result)
    block = values["samples"]["by_length"]
    assert [stratum["length"] for stratum in block["strata"]] == [7]
    held = sum(stratum["occurrences"] for stratum in block["strata"])
    assert held == 300 and values["samples"]["long_texts"]["occurrences"] == 2
    assert check_scan_document(result) == []


# The memory budget ---------------------------------------------------------------


def _wide(tmp_path, columns, rows):
    header = ",".join(f"c{n}" for n in range(columns))
    lines = []
    for row in range(rows):
        cells = [
            f"{column}-{row:05d}-xxxxxxxxxxxxxxx"[: 6 + (row % 9)]
            for column in range(columns)
        ]
        lines.append(",".join(cells))
    return write_text(tmp_path, "wide.csv", header + "\n" + "\n".join(lines) + "\n")


def test_a_small_budget_tracks_fewer_lengths_and_says_so(tmp_path):
    from tabalyst import ScanConfig, scan

    source = _wide(tmp_path, 4, 3_000)
    config = ScanConfig.model_validate(
        {
            "limits": {
                "max_distinct_per_field": 100,
                "max_samples": 50,
                "max_samples_per_length": 20,
                "max_length_strata": 40,
                "max_sample_memory": 2_000_000,
            }
        }
    )

    documents = [
        scan(source, config=config, workers=workers).model_dump(mode="json")
        for workers in (1, 2)
    ]

    blocks = [
        field(dataset(documents[0], "rows"), f"c{n}")["values"]["samples"]["by_length"]
        for n in range(4)
    ]
    granted = {block["max_lengths"] for block in blocks}
    assert len(granted) == 1 and 0 < granted.pop() < 40
    for block in blocks:
        assert block["requested_max_lengths"] == 40
        assert block["reason"] == "memory_budget" and block["limited"] is True
        assert block["other"]["occurrences"] > 0
    assert [
        field(dataset(documents[1], "rows"), f"c{n}")["values"]["samples"]["by_length"]
        for n in range(4)
    ] == blocks
    warning = [d for d in documents[0]["diagnostics"] if d["code"] == "sample_budget"]
    assert len(warning) == 1 and warning[0]["count"] == 4
    assert check_scan_document(documents[0]) == []


def test_a_field_that_fits_the_lengths_granted_loses_nothing_and_says_nothing(tmp_path):
    rows = _mixed(random.Random(2), 800)
    result = run_scan(
        _csv(tmp_path, rows),
        limits={**LIMITS, "max_length_strata": 40, "max_sample_memory": 9_000_000},
    )

    block = _values(result)["samples"]["by_length"]
    assert block["max_lengths"] < 40 and block["limited"] is False
    assert "requested_max_lengths" not in block and "reason" not in block
    assert [d for d in result["diagnostics"] if d["code"] == "sample_budget"] == []


def test_a_budget_that_cannot_hold_a_stratum_tracks_no_length(tmp_path):
    rows = _mixed(random.Random(2), 800)
    result = run_scan(
        _csv(tmp_path, rows), limits={**LIMITS, "max_sample_memory": 300_000}
    )

    block = _values(result)["samples"]["by_length"]
    assert block["max_lengths"] == 0 and block["tracked"] == 0
    assert block["strata"] == [] and block["limited"] is True
    assert block["reason"] == "memory_budget" and "other" not in block
    assert check_scan_document(result) == []


def test_a_table_that_fits_its_sample_reserves_nothing_for_strata(tmp_path):
    from tabalyst import scan
    from tabalyst.scanner.memory import SampleBudget

    result = scan(_csv(tmp_path, [f"id{n}" for n in range(30)]), counters=True)
    assert result.run.counters.sampling.length_model_bytes == 0

    budget = SampleBudget(512 << 20)
    assert budget.grant_strata(64, 100, 30, 10, 1) == 64
    assert budget.length_reserved == 30 * (600 + 20)


def test_the_strata_budget_is_a_share_of_the_sample_memory():
    from tabalyst.scanner.memory import LENGTH_SHARE, LONG_SHARE, SampleBudget

    budget = SampleBudget(8_000_000)

    assert budget.length_limit == 8_000_000 // LENGTH_SHARE
    assert budget.long_limit == 8_000_000 // LONG_SHARE
    assert budget.limit + budget.long_limit + budget.length_limit == 8_000_000


def test_a_field_never_takes_more_than_its_share_of_the_strata_budget():
    from tabalyst.scanner.memory import SampleBudget

    budget = SampleBudget(512 << 20)
    cost = 100 * 620

    grants = [budget.grant_strata(64, 100, None, 10, fields) for fields in (4, 4, 4, 4)]

    assert all(grant == min(64, budget.length_limit // 4 // cost) for grant in grants)
    assert sum(grants) * cost <= budget.length_limit
    again = SampleBudget(512 << 20)
    assert grants == [again.grant_strata(64, 100, None, 10, 4) for _ in range(4)]


# Counters, Report and documents --------------------------------------------------


def test_the_counters_say_how_many_fields_have_strata(tmp_path):
    from tabalyst import scan

    rows = _mixed(random.Random(2), 500)
    sampling = scan(_csv(tmp_path, rows), config=None, counters=True).run.counters.sampling
    assert sampling.strata_fields == 0  # the default K lists every value

    from tabalyst import ScanConfig

    config = ScanConfig.model_validate(
        {"limits": {**LIMITS, "max_length_strata": 2}}
    )
    sampling = scan(_csv(tmp_path, rows), config=config, counters=True).run.counters.sampling
    assert (sampling.strata_fields, sampling.strata_limited_fields) == (1, 1)
    assert sampling.length_model_bytes > 0


def test_the_report_base_keeps_the_counts_of_the_strata_and_drops_their_members(tmp_path):
    from tabalyst import ScanConfig, scan
    from tabalyst.report_profile import report_base

    rows = _mixed(random.Random(2), 1_000)
    config = ScanConfig.model_validate({"limits": LIMITS})
    result = scan(_csv(tmp_path, rows), config=config)

    base = report_base(result, 20)

    block = base.datasets[0].fields[0].values.samples.by_length
    assert block.listed == []
    assert all(stratum.kept == 0 and stratum.ids == [] for stratum in block.strata)
    assert sum(stratum.occurrences for stratum in block.strata) == len(rows)
    assert check_scan(base) == []
    original = result.datasets[0].fields[0].values.samples.by_length
    assert original.strata[0].kept > 0  # the scan itself is untouched


def test_a_document_with_strata_passes_the_json_schema(tmp_path):
    from jsonschema import Draft202012Validator

    from tabalyst.scanner.schema import scan_schema

    result = run_scan(_csv(tmp_path, _mixed(random.Random(2), 600)), limits=LIMITS)

    Draft202012Validator(scan_schema()).validate(result)


def _mutated(tmp_path, change):
    from tabalyst.scanner.models import ScanResult

    result = run_scan(_csv(tmp_path, _mixed(random.Random(2), 600)), limits=LIMITS)
    block = _values(result)["samples"]["by_length"]
    change(block)
    return check_scan(ScanResult.model_validate(result))


@pytest.mark.parametrize(
    "change",
    [
        lambda block: block["strata"][0].update(ids=[10**6]),
        lambda block: block["strata"][0].update(count_accuracy="partial"),
        lambda block: block.update(tracked=block["tracked"] + 1),
        lambda block: block.update(limited=True),
        lambda block: block.update(requested_max_lengths=100),
        lambda block: block["strata"][0].update(occurrences=1_000_000),
        lambda block: block["strata"].reverse(),
        lambda block: block.update(max_lengths=10**6),
    ],
)
def test_check_scan_refuses_inconsistent_strata(tmp_path, change):
    assert _mutated(tmp_path, change)


def test_check_scan_accepts_a_late_stratum_with_its_start(tmp_path):
    def late(block):
        stratum = block["strata"][0]
        stratum.update(count_accuracy="partial", tracking_started_at_occurrence=7)

    assert _mutated(tmp_path, late) == []


# Bounded memory ------------------------------------------------------------------


def test_memory_does_not_grow_with_the_number_of_lengths_met(tmp_path):
    def rows(count: int) -> list[str]:
        rng = random.Random(count)
        return [
            "".join(rng.choices("abcdefghij", k=1 + index % 40)) + str(index)
            for index in range(count)
        ]

    def peak(count: int) -> int:
        directory = tmp_path / str(count)
        directory.mkdir()
        source = _csv(directory, rows(count))
        tracemalloc.start()
        try:
            run_scan(
                source,
                limits={
                    "max_distinct_per_field": 1_000,
                    "max_samples": 200,
                    "max_length_strata": 30,
                    "max_samples_per_length": 20,
                },
                records={"duplicates": False},
                detection={"warmup_values": 200},
            )
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    peak(500)  # lazy imports and compiled patterns are one-time
    # 30 strata of 20 values fill after 600 distinct values per length.
    small = peak(8_000)
    large = peak(32_000)

    assert large < small * 1.1


def test_a_base_without_the_members_of_its_strata_is_not_a_complete_sample(tmp_path):
    from tabalyst import ScanConfig, scan
    from tabalyst.report_profile import report_base
    from tabalyst.scan_document import complete_samples

    config = ScanConfig.model_validate({"limits": LIMITS})
    result = scan(_csv(tmp_path, _mixed(random.Random(2), 1_000)), config=config)

    # The sample has 50 values, fewer than the Report keeps: only the strata differ.
    assert complete_samples(result)
    assert not complete_samples(report_base(result, 100))


def test_the_strata_of_a_scan_do_not_depend_on_the_batches_of_streamed_values(
    tmp_path, monkeypatch
):
    from tabalyst.scanner import values

    rows = _mixed(random.Random(9), 3_000)
    source = _csv(tmp_path, rows)
    reference = _values(run_scan(source, limits=LIMITS))["samples"]["by_length"]

    monkeypatch.setattr(values, "BATCH_SIZE", 7)
    small = _values(run_scan(source, limits=LIMITS))["samples"]["by_length"]

    assert small == reference
