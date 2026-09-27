"""Scan contract: values, frequencies, limits and statistics (lot 2a)."""

import pytest
from scan_helpers import dataset, field, run_scan, write_json, write_text

pytestmark = pytest.mark.lot("2a")


def test_frequencies_keep_native_types_apart(tmp_path):
    """CA05 and EF10: the string "123" and the integer 123 are two values."""
    source = write_json(
        tmp_path,
        "codes.json",
        [
            {"code": "123"},
            {"code": 123},
            {"code": "123"},
            {"code": "A1"},
            {"code": "123"},
        ],
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


def test_listings_use_analytical_values_and_cardinality_stays_raw(tmp_path):
    """Design 9.1: listings merge raw variants of one analytical value."""
    source = write_text(
        tmp_path, "cities.csv", "city\nParis\n Paris \nLyon\nParis\nNice\n"
    )

    city = field(
        dataset(run_scan(source, limits={"max_listed_frequencies": 2}), "rows"), "city"
    )

    assert city["values"]["cardinality"] == {"status": "complete", "value": 4}
    frequencies = city["values"]["frequencies"]["value"]
    assert frequencies["distinct"] == 3
    assert frequencies["truncated"] is True
    assert frequencies["listed"] == [
        {"value": "Paris", "type": "string", "count": 3},
        {"value": "Lyon", "type": "string", "count": 1},
    ]
    assert city["values"]["first"] == {"value": "Paris", "type": "string", "record": 1}


def test_samples_are_seeded_and_first_seen_when_the_table_is_released(tmp_path):
    lines = [f"v{index % 7}" for index in range(30)]
    source = write_text(tmp_path, "v.csv", "v\n" + "\n".join(lines) + "\n")

    sampled = [
        field(dataset(run_scan(source, limits={"max_samples": 3}), "rows"), "v")
        for _ in range(2)
    ]
    released = field(
        dataset(
            run_scan(source, limits={"max_samples": 3, "max_distinct_per_field": 2}),
            "rows",
        ),
        "v",
    )

    samples = sampled[0]["values"]["samples"]
    assert samples["selection"] == "uniform_distinct"
    assert len(samples["listed"]) == 3
    assert sampled[1]["values"]["samples"] == samples
    assert released["values"]["samples"] == {
        "selection": "first_seen",
        "listed": [
            {"value": "v0", "type": "string", "count": 5},
            {"value": "v1", "type": "string", "count": 5},
            {"value": "v2", "type": "string", "count": 4},
        ],
    }


def test_streaming_after_release_gives_the_same_measures(tmp_path):
    """Design section 13: releasing a table changes speed, never results."""
    lines = ["10", " Québec ", "QUÉBEC", "a\tb", "4.5", "x", "1e3", "-0"] * 3
    source = write_text(tmp_path, "mixed.csv", "value\n" + "\n".join(lines) + "\n")

    default = field(dataset(run_scan(source), "rows"), "value")
    streaming = field(
        dataset(run_scan(source, limits={"max_distinct_per_field": 1}), "rows"), "value"
    )

    for block in ("string_characteristics", "string_lengths", "booleans"):
        assert streaming[block] == default[block], block
    numeric, reference = streaming["numeric"]["value"], default["numeric"]["value"]
    assert numeric.pop("median")["status"] == "limited"
    assert reference.pop("median")["status"] == "complete"
    assert numeric == reference
    for name in ("first", "last", "count"):
        assert streaming["values"][name] == default["values"][name]


def test_global_budget_releases_the_largest_table(tmp_path):
    """Design 11: largest table first, ties release the latest field."""
    rows = [f"a{index},b{index % 3},c{index % 3}" for index in range(6)]
    source = write_text(tmp_path, "wide.csv", "a,b,c\n" + "\n".join(rows) + "\n")

    result = run_scan(
        source, limits={"max_tracked_values": 8, "max_distinct_per_field": 8}
    )
    rows_result = dataset(result, "rows")

    # Row 3 stores the 9th value with three tables of 3: the tie releases c.
    # Row 6 stores the 9th value again: a, with 6 values, is the largest.
    a, b, c = (field(rows_result, name) for name in "abc")
    budget = {"status": "limited", "reason": "global_budget", "limit": 8}
    assert c["values"]["cardinality"] == dict(budget, lower_bound=3)
    assert a["values"]["cardinality"] == dict(budget, lower_bound=6)
    assert b["values"]["cardinality"] == {"status": "complete", "value": 3}
    assert c["values"]["samples"]["selection"] == "first_seen"
    assert c["string_lengths"]["value"]["count"] == 6
    codes = {item["code"]: item for item in result["diagnostics"]}
    assert codes["global_budget"]["count"] == 2
    assert codes["measures_limited"]["count"] == 2
    assert codes["measures_limited"]["dataset"] == "rows"
    assert "limited: a, c." in codes["measures_limited"]["message"]


def test_native_json_numbers_and_booleans(tmp_path):
    source = write_text(
        tmp_path,
        "native.json",
        '[{"v": 1}, {"v": 1.0}, {"v": 1e3}, {"v": "2.5"}, {"v": true},'
        ' {"v": false}, {"v": true}, {"v": null}]',
    )

    v = field(dataset(run_scan(source), "$[]"), "v")

    numeric = v["numeric"]["value"]
    assert (numeric["count"], numeric["native_count"], numeric["text_count"]) == (
        4,
        3,
        1,
    )
    assert numeric["integral_decimals"] == 2
    assert numeric["sum"] == 1004.5
    assert numeric["median"] == {"status": "complete", "value": 1.75}
    assert v["booleans"] == {"status": "complete", "value": {"true": 2, "false": 1}}
    listed = {
        (item["value"], item["type"]): item["count"]
        for item in v["values"]["frequencies"]["value"]["listed"]
    }
    assert listed == {
        ("1", "integer"): 1,
        ("1.0", "number"): 1,
        ("1E+3", "number"): 1,
        ("2.5", "string"): 1,
        ("true", "boolean"): 2,
        ("false", "boolean"): 1,
    }
    assert v["string_lengths"]["value"]["count"] == 1


@pytest.mark.parametrize("value", ["1e5000", "0." + "1" * 300])
def test_numbers_beyond_exact_arithmetic_are_limited(tmp_path, value):
    """Design 9.4: an operation that would round limits the envelope."""
    source = write_text(tmp_path, "big.json", f'[{{"v": 1}}, {{"v": {value}}}]')

    v = field(dataset(run_scan(source), "$[]"), "v")

    assert v["numeric"] == {"status": "limited", "reason": "precision", "limit": 200}
    assert v["values"]["cardinality"] == {"status": "complete", "value": 2}


def test_string_characteristics_follow_their_definitions(tmp_path):
    values = [
        "ABC",
        "abc",
        "Abc",
        "123",
        " x",
        "a  b",
        "é",
        "a b",
        "a\x01b",
        "a\tb",
    ]
    source = write_text(
        tmp_path,
        "chars.json",
        "["
        + ",".join('{"v": ' + __import__("json").dumps(value) + "}" for value in values)
        + "]",
    )

    v = field(dataset(run_scan(source), "$[]"), "v")

    assert v["string_characteristics"] == {
        "non_ascii": 2,
        "with_line_breaks": 1,
        "with_control_characters": 1,
        "with_surrounding_whitespace": 1,
        "with_repeated_whitespace": 1,
        "uppercase": 1,
        "lowercase": 7,
        "mixed_case": 1,
        "no_letters": 1,
    }


def test_even_count_medians_are_the_mean_of_the_middle_values(tmp_path):
    source = write_text(tmp_path, "even.csv", "v\na\nbb\n1\n2\n")

    v = field(dataset(run_scan(source), "rows"), "v")

    assert v["string_lengths"]["value"]["median_length"] == 1
    assert v["string_lengths"]["value"]["mean_length"] == 1.25
    assert v["numeric"]["value"]["median"] == {"status": "complete", "value": 1.5}


def test_unconvertible_and_zero_numbers(tmp_path):
    """Review of lot 2a: no crash beyond ``decimal``, exact zeros stay exact."""
    huge = write_text(tmp_path, "huge.csv", "v\n1\n1e9999999999999999999999\n")
    zero = write_text(tmp_path, "zero.csv", "v\n0e-5000\n2\n")

    huge_v = field(dataset(run_scan(huge), "rows"), "v")
    zero_v = field(dataset(run_scan(zero), "rows"), "v")

    assert huge_v["numeric"] == {
        "status": "limited",
        "reason": "precision",
        "limit": 200,
    }
    assert zero_v["numeric"]["status"] == "complete"
    assert zero_v["numeric"]["value"]["zero"] == 1
    assert zero_v["numeric"]["value"]["min"] == 0


def test_global_budget_ties_follow_field_discovery(tmp_path):
    """A column discovered earlier keeps its table on a tie, even when its
    first value comes later."""
    source = write_text(tmp_path, "tie.csv", "b,c\n,c1\nb1,c2\nb2,\n")

    rows = dataset(
        run_scan(source, limits={"max_tracked_values": 3, "max_distinct_per_field": 3}),
        "rows",
    )

    # c gets its first value before b, but b is discovered first. Row 3
    # stores the 4th value with two tables of 2: the tie releases c.
    assert field(rows, "b")["values"]["cardinality"] == {
        "status": "complete",
        "value": 2,
    }
    assert field(rows, "c")["values"]["cardinality"]["reason"] == "global_budget"
