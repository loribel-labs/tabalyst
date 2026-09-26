"""Scan contract: values, frequencies, limits and statistics (lot 2a)."""

import pytest
from scan_helpers import dataset, field, run_scan, write_json, write_text

pytestmark = pytest.mark.lot("2a")


def test_frequencies_keep_native_types_apart(tmp_path):
    """CA05 and EF10: the string "123" and the integer 123 are two values."""
    source = write_json(
        tmp_path,
        "codes.json",
        [{"code": "123"}, {"code": 123}, {"code": "123"}, {"code": "A1"}, {"code": "123"}],
    )

    code = field(dataset(run_scan(source), "$[]"), "code")

    assert code["values"]["cardinality"] == {"status": "complete", "value": 3}
    frequencies = code["values"]["frequencies"]
    assert frequencies["status"] == "complete"
    assert frequencies["value"]["distinct"] == 3
    assert frequencies["value"]["truncated"] is False
    assert frequencies["value"]["listed"][0] == {
        "value": "123",
        "type": "string",
        "count": 3,
    }
    assert {
        (item["value"], item["type"], item["count"])
        for item in frequencies["value"]["listed"]
    } == {("123", "string", 3), ("123", "integer", 1), ("A1", "string", 1)}


def test_first_last_and_samples_of_a_small_field(tmp_path):
    """EF20 and EF21."""
    source = write_text(tmp_path, "letters.csv", "letter\nb\na\nb\nc\n")

    letter = field(dataset(run_scan(source), "rows"), "letter")

    assert letter["values"]["first"] == {"value": "b", "type": "string", "record": 1}
    assert letter["values"]["last"] == {"value": "c", "type": "string", "record": 4}
    samples = letter["values"]["samples"]
    assert samples["selection"] == "all"
    assert sorted(item["value"] for item in samples["listed"]) == ["a", "b", "c"]


def test_numeric_statistics_match_a_hand_computed_reference(tmp_path):
    """CA07 and EF15, with the conventions of design section 9.4."""
    source = write_text(
        tmp_path, "numbers.csv", "amount,word\n10,a\n-2.5,bb\n0,ccc\n4.5,\n1.0,\n"
    )
    rows = dataset(run_scan(source), "rows")

    numeric = field(rows, "amount")["numeric"]
    assert numeric["status"] == "complete"
    value = numeric["value"]
    assert (value["count"], value["native_count"], value["text_count"]) == (5, 0, 5)
    assert value["min"] == -2.5
    assert value["max"] == 10
    assert value["sum"] == 13
    assert value["mean"] == pytest.approx(2.6)
    assert value["population_variance"] == pytest.approx(18.74)
    assert value["population_std"] == pytest.approx(18.74**0.5)
    assert (value["positive"], value["negative"], value["zero"]) == (3, 1, 1)
    assert value["integral_decimals"] == 1
    assert value["median"] == {"status": "complete", "value": 1}


def test_string_lengths_match_a_hand_computed_reference(tmp_path):
    """CA07 and EF14: empty strings are not content."""
    source = write_text(
        tmp_path, "numbers.csv", "amount,word\n10,a\n-2.5,bb\n0,ccc\n4.5,\n1.0,\n"
    )

    lengths = field(dataset(run_scan(source), "rows"), "word")["string_lengths"]

    assert lengths == {
        "status": "complete",
        "value": {
            "count": 3,
            "min_length": 1,
            "max_length": 3,
            "mean_length": 2,
            "median_length": 2,
            "length_histogram": [
                {"length": 1, "count": 1},
                {"length": 2, "count": 1},
                {"length": 3, "count": 1},
            ],
        },
    }


def test_distinct_limit_publishes_only_a_proven_bound(tmp_path):
    """CA08: L + 1 distinct values observed, other counters continue."""
    source = write_text(tmp_path, "values.csv", "v\nv1\nv2\nv3\nv4\nv5\nv6\n")

    limited = field(
        dataset(run_scan(source, limits={"max_distinct_per_field": 5}), "rows"), "v"
    )
    exact = field(
        dataset(run_scan(source, limits={"max_distinct_per_field": 6}), "rows"), "v"
    )

    assert limited["values"]["cardinality"] == {
        "status": "limited",
        "reason": "distinct_limit",
        "limit": 5,
        "lower_bound": 6,
    }
    assert limited["values"]["frequencies"]["status"] == "limited"
    assert limited["presence"]["present"] == 6
    assert limited["values"]["count"] == 6
    assert limited["string_lengths"]["status"] == "complete"
    assert exact["values"]["cardinality"] == {"status": "complete", "value": 6}


def test_long_values_never_become_false_exact_identities(tmp_path):
    """CA09 and specification scenario 6."""
    first = "x" * 20 + "A"
    second = "x" * 20 + "B"
    source = write_text(tmp_path, "long.csv", f"v\na\n{first}\n{second}\n")

    limited = field(
        dataset(run_scan(source, limits={"max_stored_value_length": 10}), "rows"), "v"
    )
    exact = field(dataset(run_scan(source), "rows"), "v")

    assert limited["values"]["cardinality"] == {
        "status": "limited",
        "reason": "value_too_long",
        "limit": 10,
        "lower_bound": 2,
    }
    assert limited["values"]["count"] == 3
    assert exact["values"]["cardinality"] == {"status": "complete", "value": 3}


def test_measures_without_values_are_not_applicable(tmp_path):
    """O15: no division by zero, no invented value."""
    rows = dataset(run_scan(write_text(tmp_path, "empty.csv", "a\n")), "rows")

    a = field(rows, "a")
    assert a["values"]["count"] == 0
    assert a["values"]["cardinality"] == {
        "status": "not_applicable",
        "reason": "no_values",
    }
    assert a["numeric"]["status"] == "not_applicable"
    assert a["string_lengths"]["status"] == "not_applicable"
