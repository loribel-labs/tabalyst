# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The sample of original values of a field, its exposure and the KMV estimate
(design 18 and 21, lot 2b)."""

import random
from collections import Counter

import pytest
from scan_helpers import dataset, field, run_scan, write_json, write_text

from tabalyst.scanner.bottomk import BottomKSampler
from tabalyst.scanner.exposure import SHOW, ExposureGate
from tabalyst.scanner.valuesample import ValueSample

pytestmark = pytest.mark.scan_json_lot("2b")

SECRET = {"id": "secret", "regex": r"S-\d{2}", "sensitive": True}


def _values(result: dict, name: str = "v") -> dict:
    return field(dataset(result, "rows"), name)["values"]


def _ids(count: int) -> list[str]:
    return [f"id{n:06d}" for n in range(count)]


def _csv(tmp_path, rows: list[str], name: str = "v.csv"):
    return write_text(tmp_path, name, "v\n" + "\n".join(rows) + "\n")


# ValueSample -----------------------------------------------------------------


def test_a_sample_of_few_values_lists_all_of_them_in_first_seen_order():
    sample = ValueSample(5, 42, 1_000)
    sample.add(["b", "a"], [2, 1], False)
    sample.add(["c", "a"], [1, 4], False)

    block = sample.samples(SHOW)

    assert block.selection == "all"
    assert [(item.value, item.count) for item in block.listed] == [
        ("b", 2),
        ("a", 5),
        ("c", 1),
    ]
    assert [item.id for item in block.listed] == [0, 1, 2]
    assert block.k is None and block.hash is None and block.threshold is None
    assert sample.sampler is None  # no hash was computed
    assert sample.estimate(SHOW) is None


def test_a_sample_switches_to_the_bottom_k_once_it_holds_more_than_k_values():
    keys = [f"v{n}" for n in range(40)]
    sample = ValueSample(8, 7, 1_000)
    sample.add(keys[:5], [1] * 5, False)
    sample.add(keys[5:], [2] * 35, False)

    block = sample.samples(SHOW)

    oracle = BottomKSampler(8, seed=7)
    oracle.update([("string", key) for key in keys], [1] * 5 + [2] * 35)
    assert block.selection == "bottom_k"
    assert [(item.value, item.count) for item in block.listed] == [
        (entry.key[1], entry.count) for entry in oracle.entries()
    ]
    assert block.threshold == f"{oracle.threshold:032x}"
    assert (block.k, block.hash.seed, block.hash.version) == (8, 7, 1)
    assert sample.estimate(SHOW)["k"] == 8


def test_other_native_types_are_sampled_by_their_canonical_text():
    sample = ValueSample(10, 42, 1_000)
    keys = ["5", ("integer", 5), ("number", "1.50"), ("boolean", True)]
    sample.add(keys, [1] * 4, True)

    listed = sample.samples(SHOW).listed

    assert [(item.type, item.value) for item in listed] == [
        ("string", "5"),
        ("integer", "5"),
        ("number", "1.50"),
        ("boolean", "true"),
    ]


def test_values_longer_than_the_stored_length_are_excluded_and_counted():
    sample = ValueSample(2, 42, 4)
    sample.add(["abc", "toolong", "xyz"], [1, 1, 1], False)

    block = sample.samples(SHOW)

    # The sample is not the whole domain any more: it says bottom_k, ordered by
    # priority, and the estimator does not claim to have seen everything.
    assert sample.excluded == 1
    assert block.selection == "bottom_k"
    assert sorted(item.value for item in block.listed) == ["abc", "xyz"]
    assert block.threshold is None
    assert sample.estimate(SHOW) is None


def test_exposure_applies_after_the_calculation_and_withholds_the_threshold():
    keys = [f"S-{n:02d}" for n in range(30)]
    sample = ValueSample(10, 42, 1_000)
    sample.add(keys, [1] * 30, False)

    shown = sample.samples(SHOW)
    masked = sample.samples(ExposureGate("mask"))
    hidden = sample.samples(ExposureGate("hide"))

    assert shown.threshold is not None and shown.kept == shown.of == 10
    # Ten originals, one mask: the sample cannot give the originals back.
    assert [(item.value, item.count) for item in masked.listed] == [("A-99", 10)]
    assert (masked.kept, masked.of, masked.threshold) == (1, 10, None)
    assert (hidden.kept, hidden.of, hidden.listed) == (0, 10, [])
    assert sample.estimate(SHOW)["theta_hex"] == shown.threshold
    assert sample.estimate(ExposureGate("mask"))["theta_hex"] is None


# Scan ------------------------------------------------------------------------


def test_the_sample_holds_original_values_while_the_frequencies_stay_analytical(
    tmp_path,
):
    source = _csv(tmp_path, ["00123", "123", " 123 ", "00123"])

    values = _values(run_scan(source))

    listed = values["samples"]["listed"]
    assert [(item["value"], item["count"]) for item in listed] == [
        ("00123", 2),
        ("123", 1),
        (" 123 ", 1),
    ]
    assert values["samples"]["selection"] == "all"
    assert [item["id"] for item in listed] == [0, 1, 2]


def test_a_complete_table_above_k_samples_without_losing_the_exact_cardinality(
    tmp_path,
):
    source = _csv(tmp_path, _ids(300) * 2)

    values = _values(run_scan(source, limits={"max_samples": 40}))

    assert values["cardinality"]["status"] == "complete"
    assert values["cardinality"]["value"] == 300
    assert values["samples"]["selection"] == "bottom_k"
    assert values["samples"]["kept"] == 40
    assert {item["count"] for item in values["samples"]["listed"]} == {2}
    assert "threshold" in values["samples"]
    assert "estimate" not in values["cardinality"]


def test_the_kmv_estimate_sits_within_its_error_of_the_true_cardinality(tmp_path):
    distinct = 20_000
    source = _csv(tmp_path, _ids(distinct))

    values = _values(
        run_scan(source, limits={"max_distinct_per_field": 2_000, "max_samples": 1_000})
    )

    cardinality = values["cardinality"]
    estimate = cardinality["estimate"]
    assert cardinality["status"] == "limited"
    assert (estimate["accuracy"], estimate["method"], estimate["k"]) == (
        "estimated",
        "kmv",
        1_000,
    )
    assert estimate["theta_hex"] == values["samples"]["threshold"]
    # Four standard errors: a fixed seed, never a bound per seed (B13).
    error = 4 * estimate["relative_standard_error"] * distinct
    assert abs(estimate["value"] - distinct) < error
    assert cardinality["lower_bound"] <= estimate["value"] <= cardinality["upper_bound"]


def test_no_estimate_is_made_when_a_value_escaped_the_sample(tmp_path):
    source = _csv(tmp_path, [*_ids(300), "x" * 50])

    values = _values(
        run_scan(
            source,
            limits={
                "max_distinct_per_field": 100,
                "max_samples": 50,
                "max_stored_value_length": 20,
            },
        )
    )

    assert "estimate" not in values["cardinality"]
    assert values["samples"]["selection"] == "bottom_k"
    assert all(len(item["value"]) <= 20 for item in values["samples"]["listed"])


def test_the_estimate_is_held_within_the_certain_bounds():
    from tabalyst.scanner.config import ScanConfig
    from tabalyst.scanner.detectors.registry import DetectorSet, default_registry
    from tabalyst.scanner.values import ValueContext, ValueTracker

    config = ScanConfig()
    context = ValueContext(config, DetectorSet(default_registry(), config))
    tracker = ValueTracker(context, 1)
    limited = {
        "status": "limited",
        "reason": "distinct_limit",
        "limit": 10,
        "lower_bound": 11,
    }
    raw = {"method": "kmv", "value": 5.0, "relative_standard_error": 0.5, "k": 5}

    below = tracker.cardinality(limited, 40, raw).estimate
    within = tracker.cardinality(limited, 40, {**raw, "value": 25.0}).estimate

    assert (below.value, below.unclamped_value) == (11, 5.0)
    assert (within.value, within.unclamped_value) == (25.0, None)


def test_a_sensitive_field_shows_neither_its_threshold_nor_its_originals(tmp_path):
    source = _csv(tmp_path, [f"S-{n:02d}" for n in range(60)])
    limits = {"max_distinct_per_field": 20, "max_samples": 20}

    values = _values(run_scan(source, limits=limits, patterns=[SECRET]))

    samples = values["samples"]
    assert [item["value"] for item in samples["listed"]] == ["A-99"]
    assert (samples["kept"], samples["of"]) == (1, 20)
    assert "threshold" not in samples
    assert "theta_hex" not in values["cardinality"]["estimate"]


def test_json_values_are_sampled_in_their_native_types(tmp_path):
    source = write_json(
        tmp_path, "v.json", [{"v": value} for value in (1, "1", True, 2.5, 1)]
    )

    result = run_scan(source)

    listed = field(dataset(result, "$[]"), "v")["values"]["samples"]["listed"]
    assert [(item["type"], item["value"], item["count"]) for item in listed] == [
        ("integer", "1", 2),
        ("string", "1", 1),
        ("boolean", "true", 1),
        ("number", "2.5", 1),
    ]


def test_the_sample_does_not_depend_on_the_reader_or_the_release(tmp_path):
    rng = random.Random(5)
    rows = [f"id{rng.randrange(400):04d}" for _ in range(6_000)]
    csv = _csv(tmp_path, rows)
    json = write_json(tmp_path, "v.json", [{"v": value} for value in rows])
    limits = {"max_samples": 60, "max_distinct_per_field": 100}

    from_csv = _values(run_scan(csv, limits=limits))["samples"]
    from_json = field(dataset(run_scan(json, limits=limits), "$[]"), "v")["values"][
        "samples"
    ]
    unreleased = _values(run_scan(csv, limits={"max_samples": 60}))["samples"]

    oracle = Counter(rows)
    assert from_csv == from_json == unreleased
    assert from_csv["selection"] == "bottom_k"
    assert all(item["count"] == oracle[item["value"]] for item in from_csv["listed"])
