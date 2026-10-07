# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: the qualified cardinality of a field (design 9.1, lot 1a).

The distinct count names the domain it counts, the accuracy of its identities
and, once the table stopped, the certain maximum and the records where tracking
reached its limit and passed it.
"""

import json

import pytest
from scan_helpers import (
    complete_cardinality,
    dataset,
    field,
    limited_cardinality,
    write_json,
    write_text,
)

from tabalyst.scanner import ScanConfig, scan

pytestmark = pytest.mark.scan_json_lot("1a")


def _scan(source, *, workers: int = 1, **settings) -> dict:
    config = ScanConfig.model_validate(settings)
    result = scan(source, config=config, workers=workers)
    return result.model_dump(mode="json")


def _ids(count: int) -> list[str]:
    return [f"id{n:05d}" for n in range(count)]


def _cardinality(document: dict, dataset_id: str, display: str) -> dict:
    return field(dataset(document, dataset_id), display)["values"]["cardinality"]


def test_a_complete_cardinality_is_exact_for_the_original_values(tmp_path):
    source = write_text(tmp_path, "v.csv", "v\n00123\n123\n 123 \n00123\n")

    cardinality = _cardinality(_scan(source), "rows", "v")

    # The leading zeros and the spaces are three values of the original domain.
    assert cardinality == complete_cardinality(3)


def test_the_limit_names_the_records_where_it_was_reached_and_passed(tmp_path):
    # Empty cells are not values: the 5th distinct value is at record 9.
    cells = ["a", "", "b", "", "c", "", "d", "", "e", "f", "g"]
    lines = [f"{cell},x" for cell in cells]
    source = write_text(tmp_path, "v.csv", "v,w\n" + "\n".join(lines) + "\n")

    document = _scan(source, limits={"max_distinct_per_field": 5})

    assert _cardinality(document, "rows", "v") == limited_cardinality(
        "distinct_limit", 5, 6, 7, reached=9, overflow=10
    )


def test_reaching_the_limit_exactly_keeps_the_cardinality_complete(tmp_path):
    source = write_text(tmp_path, "v.csv", "v\n" + "\n".join(_ids(10) * 2) + "\n")

    document = _scan(source, limits={"max_distinct_per_field": 10})

    assert _cardinality(document, "rows", "v") == complete_cardinality(10)


@pytest.mark.parametrize("workers", [1, 2])
def test_the_records_do_not_depend_on_the_reader_or_the_workers(tmp_path, workers):
    # 5,000 records: the CSV reader hands them over in several batches.
    ids = _ids(5_000)
    csv = write_text(tmp_path, "v.csv", "v\n" + "\n".join(ids) + "\n")
    rows = write_json(tmp_path, "v.json", [{"v": value} for value in ids])
    limits = {"max_distinct_per_field": 3_000, "max_samples": 3_000}

    from_csv = _cardinality(_scan(csv, workers=workers, limits=limits), "rows", "v")
    from_json = _cardinality(_scan(rows, workers=workers, limits=limits), "$[]", "v")

    expected = limited_cardinality(
        "distinct_limit", 3_000, 3_001, 5_000, reached=3_000, overflow=3_001
    )
    assert from_csv == expected
    assert from_json == expected


def test_a_record_with_several_occurrences_counts_once(tmp_path):
    source = write_json(
        tmp_path,
        "t.json",
        [{"tags": ["a", "b", "c"]}, {"tags": ["d", "e", "f"]}],
    )

    document = _scan(source, limits={"max_distinct_per_field": 4})

    (limited,) = [
        item["values"]["cardinality"]
        for item in dataset(document, "$[]")["fields"]
        if item["values"]["cardinality"]["status"] == "limited"
    ]
    # The 4th and the 5th distinct values both belong to record 2.
    assert limited["threshold_reached_at_record"] == 2
    assert limited["overflow_detected_at_record"] == 2
    assert limited["upper_bound"] == 6


def test_the_records_are_only_known_when_the_distinct_limit_stopped_tracking(
    tmp_path,
):
    rows = [f"a{n},b{n % 3},c{n % 3},{'x' * 30}{n}" for n in range(6)]
    source = write_text(tmp_path, "w.csv", "a,b,c,d\n" + "\n".join(rows) + "\n")

    document = _scan(
        source,
        limits={
            "max_tracked_values": 8,
            "max_distinct_per_field": 8,
            "max_stored_value_length": 20,
        },
    )

    reasons = set()
    for display in ("a", "b", "c", "d"):
        cardinality = _cardinality(document, "rows", display)
        if cardinality["status"] == "limited":
            reasons.add(cardinality["reason"])
            assert "threshold_reached_at_record" not in cardinality
            assert "overflow_detected_at_record" not in cardinality
    assert reasons == {"global_budget", "value_too_long"}


def test_members_that_are_not_known_are_absent_not_null(tmp_path):
    source = write_text(tmp_path, "v.csv", "v\n" + "\n".join(_ids(30)) + "\n")

    document = _scan(source, limits={"max_distinct_per_field": 10})
    values = field(dataset(document, "rows"), "v")["values"]
    text = json.dumps(values)

    # The estimate and the bottom-k sample belong to lot 2b.
    assert "estimate" not in values["cardinality"]
    for name in ("k", "hash", "threshold"):
        assert name not in values["samples"], name
    assert "null" not in json.dumps(values["cardinality"])
    assert '"selection": "first_seen"' in text
