# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Long texts, the memory budget of the samples and their counters (design 18.6,
18.10, lot 2c)."""

import math
import random
import tracemalloc

import pytest
from scan_helpers import dataset, field, run_scan, write_json, write_text

from tabalyst.scanner.bottomk import BottomKSampler, priority
from tabalyst.scanner.longtext import LongTextSampler, digest_of
from tabalyst.scanner.memory import (
    SampleBudget,
    long_entry_bytes,
    sample_entry_bytes,
)
from tabalyst.scanner.validation import check_scan

pytestmark = pytest.mark.scan_json_lot("2c")

SECRET = {"id": "secret", "regex": r"S-\d{2}", "sensitive": True}


def _text(index: int, length: int = 1_500) -> str:
    return f"{index:06d}" + "x" * (length - 6)


def _csv(tmp_path, rows: list[str], header: str = "v", name: str = "v.csv"):
    return write_text(tmp_path, name, header + "\n" + "\n".join(rows) + "\n")


def _values(result: dict, name: str = "v") -> dict:
    return field(dataset(result, "rows"), name)["values"]


def _facts(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "run"}


# LongTextSampler ------------------------------------------------------------


def test_the_long_text_sample_is_the_k_smallest_priorities_of_the_digests():
    sampler = LongTextSampler(8, preview_chars=10, seed=3)
    texts = [_text(index) for index in range(60)]
    for text in texts + texts[:10]:
        sampler.add(text)

    expected = sorted(
        (priority(("digest", digest_of("string", text)[0]), seed=3), text)
        for text in texts
    )[:8]
    entries = sampler.entries()
    assert [entry.priority for entry in entries] == [value for value, _ in expected]
    assert [entry.original_length_chars for entry in entries] == [1_500] * 8
    assert not sampler.distinct_exact and sampler.retained == 8
    assert sampler.occurrences == 70
    # A retained key was admitted at its first occurrence: its count is exact.
    firsts = {digest_of("string", text)[0]: text for text in texts[:10]}
    for entry in entries:
        assert entry.count == (2 if entry.digest in firsts else 1)


def test_the_long_text_sample_does_not_depend_on_the_order_of_the_texts():
    texts = [_text(index) for index in range(40)]
    left, right = LongTextSampler(6, preview_chars=5), LongTextSampler(6, preview_chars=5)
    for text in texts:
        left.add(text)
    shuffled = texts[:]
    random.Random(4).shuffle(shuffled)
    for text in shuffled:
        right.add(text)

    assert [(e.digest, e.count) for e in left.entries()] == [
        (e.digest, e.count) for e in right.entries()
    ]


def test_a_digest_ignores_the_seed_and_tells_types_apart():
    first = LongTextSampler(4, preview_chars=5, seed=1)
    second = LongTextSampler(4, preview_chars=5, seed=2)
    for sampler in (first, second):
        sampler.add("a" * 50)
    third = LongTextSampler(4, preview_chars=5)
    third.add("a" * 50, native_type="number")

    assert first.entries()[0].digest == second.entries()[0].digest
    assert first.entries()[0].digest != third.entries()[0].digest
    assert third.entries()[0].type == "number"


def test_a_long_text_with_lone_surrogates_is_sampled():
    sampler = LongTextSampler(4, preview_chars=3)
    sampler.add("\ud800" * 40)

    (entry,) = sampler.entries()
    assert entry.original_length_chars == 40
    assert entry.original_length_bytes == 120


def test_the_long_text_sample_estimates_its_distinct_texts():
    sampler = LongTextSampler(64, preview_chars=4)
    for index in range(2_000):
        sampler.add(_text(index, 40))

    kmv = sampler.kmv()
    assert kmv is not None and kmv.k == 64
    assert abs(kmv.estimate / 2_000 - 1) < 4 * kmv.relative_standard_error
    assert sampler.hashed_texts == 2_000
    assert sampler.hashed_bytes == 2_000 * 40


def test_a_long_text_sampler_needs_a_preview_of_at_least_one_character():
    with pytest.raises(ValueError, match="preview_chars"):
        LongTextSampler(4, preview_chars=0)
    with pytest.raises(ValueError, match="count"):
        LongTextSampler(4, preview_chars=1).add("x", 0)


# Long texts in a scan -------------------------------------------------------


def test_a_scan_samples_long_texts_apart_from_the_stored_values(tmp_path):
    rows = [f"short{index % 3}" for index in range(30)]
    rows += [_text(index % 4) for index in range(40)]
    result = run_scan(_csv(tmp_path, rows))

    samples = _values(result)["samples"]
    assert samples["selection"] == "all"
    assert sorted(item["value"] for item in samples["listed"]) == [
        "short0",
        "short1",
        "short2",
    ]
    long = samples["long_texts"]
    assert long["selection"] == "all" and "threshold" not in long
    assert (long["k"], long["preview_chars"], long["occurrences"]) == (100, 200, 40)
    assert (long["kept"], long["of"]) == (4, 4)
    assert {item["count"] for item in long["listed"]} == {10}
    assert all(item["truncated"] and len(item["preview"]) == 200 for item in long["listed"])
    assert all(item["identity_accuracy"] == "fingerprint_based" for item in long["listed"])
    assert long["digest"] == {"algorithm": "blake2b", "bits": 128}


def test_a_field_without_long_values_has_no_long_text_block(tmp_path):
    result = run_scan(_csv(tmp_path, ["a", "b", "c"]))

    assert "long_texts" not in _values(result)["samples"]


def test_long_texts_are_sampled_the_same_with_one_and_several_workers(tmp_path):
    from tabalyst import ScanConfig, scan

    rng = random.Random(5)
    rows = [
        _text(rng.randrange(400)) if index % 2 else f"id{rng.randrange(900):04d}"
        for index in range(4_000)
    ]
    source = _csv(tmp_path, rows)
    config = ScanConfig.model_validate(
        {
            "limits": {
                "max_distinct_per_field": 100,
                "max_samples": 50,
                "max_long_samples": 20,
            }
        }
    )

    documents = [
        scan(source, config=config, workers=workers).model_dump(mode="json")
        for workers in (1, 1, 2)
    ]

    assert _facts(documents[0]) == _facts(documents[1]) == _facts(documents[2])
    long = _values(documents[0])["samples"]["long_texts"]
    assert long["selection"] == "bottom_k" and len(long["listed"]) == 20
    assert long["threshold"] and long["hash"]["algorithm"] == "blake2b"


def test_the_cardinality_estimate_covers_the_values_and_the_long_texts(tmp_path):
    short = 3_000
    longs = 600
    rows = [f"id{index:05d}" for index in range(short)]
    rows += [_text(index) for index in range(longs)]
    result = run_scan(
        _csv(tmp_path, rows),
        limits={
            "max_distinct_per_field": 200,
            "max_samples": 128,
            "max_long_samples": 64,
        },
    )

    estimate = _values(result)["cardinality"]["estimate"]
    first, second = estimate["parts"]
    assert (first["domain"], first["accuracy"], first["k"]) == ("values", "estimated", 128)
    assert (second["domain"], second["accuracy"], second["k"]) == (
        "long_texts",
        "estimated",
        64,
    )
    assert abs(first["value"] / short - 1) < 4 * first["relative_standard_error"]
    assert abs(second["value"] / longs - 1) < 4 * second["relative_standard_error"]
    raw = estimate.get("unclamped_value", estimate["value"])
    assert raw == pytest.approx(first["value"] + second["value"])
    combined = math.hypot(
        first["value"] * first["relative_standard_error"],
        second["value"] * second["relative_standard_error"],
    ) / raw
    assert estimate["relative_standard_error"] == pytest.approx(combined)
    assert check_scan(_scan(tmp_path, rows)) == []


def _scan(tmp_path, rows):
    from tabalyst import ScanConfig, scan

    config = ScanConfig.model_validate(
        {
            "limits": {
                "max_distinct_per_field": 200,
                "max_samples": 128,
                "max_long_samples": 64,
            }
        }
    )
    return scan(_csv(tmp_path, rows, name="again.csv"), config=config)


def test_a_sensitive_field_withholds_its_long_texts(tmp_path):
    rows = ["S-11", "S-12", _text(1), _text(2), _text(1)]
    result = run_scan(_csv(tmp_path, rows), patterns=[SECRET])

    values = _values(result)
    assert field(dataset(result, "rows"), "v")["sensitive"]
    long = values["samples"]["long_texts"]
    assert (long["occurrences"], long["kept"], long["of"]) == (3, 0, 2)
    assert long["listed"] == [] and "threshold" not in long


def test_without_a_long_text_sample_the_long_values_are_counted_only(tmp_path):
    rows = [f"id{index:04d}" for index in range(200)] + [_text(1), _text(2)]
    result = run_scan(
        _csv(tmp_path, rows),
        limits={"max_distinct_per_field": 50, "max_samples": 20, "max_long_samples": 0},
    )

    values = _values(result)
    long = values["samples"]["long_texts"]
    assert (long["k"], long["kept"], long["of"], long["occurrences"]) == (0, 0, 0, 2)
    assert long["selection"] == "bottom_k"
    assert "estimate" not in values["cardinality"]


def test_the_preview_never_exceeds_the_stored_value_length(tmp_path):
    result = run_scan(
        _csv(tmp_path, ["abcdefghijklmnop"] * 3),
        limits={"max_stored_value_length": 8, "long_preview_chars": 500},
    )

    long = _values(result)["samples"]["long_texts"]
    assert long["preview_chars"] == 8
    assert long["listed"][0]["preview"] == "abcdefgh"


def _with_long_texts(result, **changes):
    """The scan with fields of the first field's ``long_texts`` replaced."""
    first = result.datasets[0].fields[0]
    long = first.values.samples.long_texts.model_copy(update=changes)
    samples = first.values.samples.model_copy(update={"long_texts": long})
    values = first.values.model_copy(update={"samples": samples})
    fields = [first.model_copy(update={"values": values}), *result.datasets[0].fields[1:]]
    dataset0 = result.datasets[0].model_copy(update={"fields": fields})
    return result.model_copy(update={"datasets": [dataset0, *result.datasets[1:]]})


def test_check_scan_refuses_inconsistent_long_text_blocks(tmp_path):
    from tabalyst import scan

    result = scan(_csv(tmp_path, [_text(1), _text(2), "a"]))
    long = result.datasets[0].fields[0].values.samples.long_texts
    assert check_scan(result) == []

    too_many = _with_long_texts(result, occurrences=99)
    assert any("occurrences" in problem for problem in check_scan(too_many))
    twin = long.listed[0].model_copy(update={"id": 1})
    same_digest = _with_long_texts(result, listed=[long.listed[0], twin])
    assert any("digests" in problem for problem in check_scan(same_digest))


# Memory budget ----------------------------------------------------------------


def test_a_field_never_takes_more_than_its_share_of_the_sample_budget():
    budget = SampleBudget(8_000_000)
    cost = sample_entry_bytes(10)

    first = budget.grant_sample(10_000, None, 10, 4)

    assert first == (budget.limit // 4) // cost
    assert budget.reserved == first * cost


def test_the_sample_budget_is_spent_in_the_order_of_the_grants():
    budget = SampleBudget(16_000_000)
    cost = sample_entry_bytes(10)
    grants = [budget.grant_sample(10_000, None, 10, 1) for _ in range(4)]

    assert grants[0] == 10_000
    assert sum(grants) * cost <= budget.limit
    assert grants[-1] < grants[0]
    again = SampleBudget(16_000_000)
    assert grants == [again.grant_sample(10_000, None, 10, 1) for _ in range(4)]


def test_a_complete_table_only_reserves_its_distinct_values():
    budget = SampleBudget(100_000_000)

    granted = budget.grant_sample(10_000, 12, 5, 2)

    assert granted == 10_000
    assert budget.reserved == 12 * sample_entry_bytes(5)


def test_the_long_text_budget_is_first_come_first_served():
    budget = SampleBudget(8_000_000)
    cost = long_entry_bytes(200)
    first = budget.grant_long(100, 200)
    second = budget.grant_long(100, 200)

    assert first == 100 and budget.long_reserved <= budget.long_limit
    assert second == min(100, (budget.long_limit - 100 * cost) // cost)


def test_the_cost_model_covers_the_measured_size_of_a_full_sample():
    k = 10_000
    texts = [f"{index:020d}" for index in range(30_000)]
    counts = [1] * len(texts)
    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    sampler = BottomKSampler(k, seed=1)
    for start in range(0, len(texts), 4_096):
        sampler.update_strings(texts[start : start + 4_096], counts[start : start + 4_096])
    sampler.entries()
    peak = tracemalloc.get_traced_memory()[1] - base
    tracemalloc.stop()

    modelled = k * sample_entry_bytes(20)
    # Strings are shared with the table the sample was drawn from, so the model
    # counts them and the measure does not: it must still be of the same order.
    assert 0.7 * peak < modelled < 1.8 * peak


def _wide_csv(tmp_path, columns: int, rows: int):
    header = ",".join(f"c{n}" for n in range(columns))
    lines = [
        ",".join(f"{column}-{row:05d}" for column in range(columns))
        for row in range(rows)
    ]
    return write_text(tmp_path, "wide.csv", header + "\n" + "\n".join(lines) + "\n")


def test_a_small_sample_budget_cuts_every_sample_alike_and_says_so(tmp_path):
    from tabalyst import ScanConfig, scan

    source = _wide_csv(tmp_path, 6, 4_000)
    config = ScanConfig.model_validate(
        {
            "limits": {
                "max_distinct_per_field": 100,
                "max_samples": 100,
                "max_sample_memory": 240_000,
            }
        }
    )

    documents = [
        scan(source, config=config, workers=workers).model_dump(mode="json")
        for workers in (1, 2)
    ]

    assert _facts(documents[0]) == _facts(documents[1])
    ks = []
    for column in range(6):
        values = field(dataset(documents[0], "rows"), f"c{column}")["values"]
        samples = values["samples"]
        ks.append(samples["k"])
        assert samples["requested_k"] == 100 and samples["reason"] == "memory_budget"
        assert samples["k"] < 100 and samples["of"] == samples["k"]
        assert values["cardinality"]["estimate"]["k"] == samples["k"]
    assert len(set(ks)) == 1
    warning = [d for d in documents[0]["diagnostics"] if d["code"] == "sample_budget"]
    assert len(warning) == 1 and warning[0]["count"] == 6
    assert check_scan(scan(source, config=config)) == []


def test_a_sample_budget_that_cannot_hold_an_entry_omits_the_samples(tmp_path):
    source = _wide_csv(tmp_path, 3, 400)
    result = run_scan(
        source,
        limits={
            "max_distinct_per_field": 100,
            "max_samples": 50,
            "max_sample_memory": 1_000,
        },
    )

    samples = field(dataset(result, "rows"), "c0")["values"]["samples"]
    assert (samples["k"], samples["kept"], samples["of"]) == (0, 0, 0)
    assert samples["reason"] == "memory_budget"
    assert "estimate" not in field(dataset(result, "rows"), "c0")["values"]["cardinality"]


def test_the_default_budget_does_not_touch_a_realistic_wide_scan(tmp_path):
    result = run_scan(_wide_csv(tmp_path, 34, 300))

    assert [d for d in result["diagnostics"] if d["code"] == "sample_budget"] == []
    for column in range(34):
        samples = field(dataset(result, "rows"), f"c{column}")["values"]["samples"]
        assert "requested_k" not in samples


# Bounded memory -----------------------------------------------------------------


def test_the_pending_batch_of_a_streamed_field_is_bounded_by_size(
    tmp_path, monkeypatch
):
    from tabalyst import ScanConfig, scan
    from tabalyst.scanner import values

    rows = [{"v": _text(index % 900, 1_200)} for index in range(3_000)]
    source = write_json(tmp_path, "v.json", rows)
    config = ScanConfig.model_validate({"limits": {"max_samples": 40}})
    default = scan(source, config=config, workers=1).model_dump(mode="json")

    flushes = []
    original = values.ValueTracker.flush

    def counting(self):
        flushes.append(self.pending_chars)
        original(self)

    monkeypatch.setattr(values, "PENDING_CHARS", 20_000)
    monkeypatch.setattr(values.ValueTracker, "flush", counting)
    small = scan(source, config=config, workers=1).model_dump(mode="json")

    # Batch boundaries never change a result (design 13).
    assert _facts(small) == _facts(default)
    assert len(flushes) > 100 and len(flushes) > 10
    assert max(flushes) < 20_000 + 1_200


def test_memory_does_not_grow_with_unique_long_texts(tmp_path, monkeypatch):
    from tabalyst.scanner import values
    from tabalyst.scanner.readers import csv_reader

    # Small limits reach the plateau with small files: a batch of rows and a
    # batch of streamed values are bounded by size, whatever the row count.
    monkeypatch.setattr(csv_reader, "BATCH_BYTES", 262_144)
    monkeypatch.setattr(values, "PENDING_CHARS", 262_144)

    def peak(rows: int) -> int:
        directory = tmp_path / str(rows)
        directory.mkdir()
        source = _csv(directory, [_text(index, 4_000) for index in range(rows)])
        tracemalloc.start()
        try:
            run_scan(
                source,
                limits={
                    "max_distinct_per_field": 1_000,
                    "max_samples": 200,
                    "max_long_samples": 50,
                },
                records={"duplicates": False},
                detection={"warmup_values": 200},
            )
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    peak(500)  # lazy imports and compiled patterns are one-time
    small = peak(1_500)
    large = peak(6_000)

    # Four times the rows must not mean four times the memory. The traced peak
    # varies with the CPython version (3.11 measured 1.39 on CI, the incremental
    # collector of 3.14 frees later); linear growth would give about 4.
    assert large < small * 2.0


def test_a_csv_batch_is_bounded_by_bytes_and_changes_no_result(tmp_path, monkeypatch):
    from tabalyst import scan
    from tabalyst.scanner.readers import csv_reader

    rows = [f"{_text(index % 50, 3_000)},{index}" for index in range(1_200)]
    source = _csv(tmp_path, rows, header="v,n")
    default = scan(source, workers=1).model_dump(mode="json")

    batches = []
    original = csv_reader.RecordBatch

    def counting(dataset, first, batch_rows, lines):
        batches.append(len(batch_rows))
        return original(dataset, first, batch_rows, lines)

    monkeypatch.setattr(csv_reader, "BATCH_BYTES", 100_000)
    monkeypatch.setattr(csv_reader, "RecordBatch", counting)
    small = scan(source, workers=1).model_dump(mode="json")

    assert _facts(small) == _facts(default)
    assert len(batches) > 20 and max(batches) < 100


# Counters -----------------------------------------------------------------------


def test_the_counters_are_written_only_on_request(tmp_path):
    from tabalyst import scan

    source = _csv(tmp_path, [f"id{index:04d}" for index in range(300)])

    assert "counters" not in scan(source).model_dump(mode="json")["run"]
    counters = scan(source, counters=True).model_dump(mode="json")["run"]["counters"]
    assert set(counters) == {"sampling"}


def test_the_sampling_counters_add_up_and_do_not_depend_on_workers(tmp_path):
    from tabalyst import ScanConfig, scan

    rng = random.Random(8)
    rows = [f"id{rng.randrange(700):04d}" for _ in range(3_000)]
    rows += [_text(rng.randrange(30)) for _ in range(200)]
    source = _csv(tmp_path, rows)
    config = ScanConfig.model_validate(
        {"limits": {"max_distinct_per_field": 200, "max_samples": 60}}
    )

    runs = [
        scan(source, config=config, workers=workers, counters=True).run.counters
        for workers in (1, 2)
    ]

    assert runs[0] == runs[1]
    sampling = runs[0].sampling
    assert sampling.bottom_k_fields == 1 and sampling.reduced_fields == 0
    assert sampling.hashed_keys == (
        sampling.admitted_keys + sampling.rejected_keys + sampling.hit_keys
    )
    assert sampling.evicted_keys == sampling.admitted_keys - 60
    assert (sampling.k_effective_min, sampling.k_effective_max) == (60, 60)
    assert sampling.long_texts_hashed > 0 and sampling.long_bytes_hashed > 0
    assert sampling.sample_model_bytes > 0 and sampling.long_model_bytes > 0


def test_a_scan_with_counters_passes_the_schema_and_the_invariants(tmp_path):
    import json

    from jsonschema import Draft202012Validator

    from tabalyst import scan
    from tabalyst.scanner.schema import scan_schema

    result = scan(
        _csv(tmp_path, [_text(1), "a", "b"]), counters=True
    )

    assert check_scan(result) == []
    Draft202012Validator(scan_schema()).validate(
        json.loads(result.model_dump_json())
    )


def test_the_scan_command_writes_counters_only_with_the_option(tmp_path, monkeypatch):
    import json

    from typer.testing import CliRunner

    from tabalyst.cli import app

    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "home"))
    source = _csv(tmp_path, [f"id{index:03d}" for index in range(120)])
    runner = CliRunner()
    plain, counted = tmp_path / "plain.scan.json", tmp_path / "counted.scan.json"

    first = runner.invoke(app, ["scan", str(source), "-o", str(plain), "--no-progress"])
    second = runner.invoke(
        app, ["scan", str(source), "-o", str(counted), "--counters", "--no-progress"]
    )

    assert first.exit_code == 0 and second.exit_code == 0, (first.output, second.output)
    assert "counters" not in json.loads(plain.read_text(encoding="utf-8"))["run"]
    run = json.loads(counted.read_text(encoding="utf-8"))["run"]
    assert run["counters"]["sampling"]["bottom_k_fields"] == 0
