# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan contract: normalization version 1 and variant groups (lot 2b)."""

import pytest
from scan_helpers import dataset, field, run_scan, stages, write_json, write_text

pytestmark = pytest.mark.lot("2b")

DECOMPOSED_QUEBEC = "Québec"
PROVINCES = ["Québec", "QUÉBEC", "Quebec", "  Québec  ", "Ontario", DECOMPOSED_QUEBEC]


def _provinces(tmp_path):
    return write_text(tmp_path, "provinces.csv", "province\n" + "\n".join(PROVINCES) + "\n")


def _cardinality(value):
    return {"status": "complete", "value": value}


def test_variants_are_grouped_while_raw_values_are_preserved(tmp_path):
    """CA15, EF33-EF37: every stage is counted and raw variants stay visible."""
    province = field(dataset(run_scan(_provinces(tmp_path)), "rows"), "province")

    normalization = province["normalization"]
    assert normalization["version"] == 1
    assert [item["stage"] for item in normalization["stages"]] == [
        "raw",
        "nfc",
        "trim",
        "collapse_whitespace",
        "casefold",
        "strip_accents",
    ]
    by_stage = stages(province)
    assert by_stage["raw"] == {
        "stage": "raw",
        "enabled": True,
        "changed": None,
        "cardinality": _cardinality(6),
    }
    assert (by_stage["nfc"]["changed"], by_stage["nfc"]["cardinality"]) == (
        1,
        _cardinality(5),
    )
    assert (by_stage["trim"]["changed"], by_stage["trim"]["cardinality"]) == (
        1,
        _cardinality(4),
    )
    assert by_stage["collapse_whitespace"]["changed"] == 0
    assert (by_stage["casefold"]["changed"], by_stage["casefold"]["cardinality"]) == (
        6,
        _cardinality(3),
    )
    assert (
        by_stage["strip_accents"]["changed"],
        by_stage["strip_accents"]["cardinality"],
    ) == (4, _cardinality(2))

    groups = normalization["variant_groups"]
    assert groups["status"] == "complete"
    assert (groups["value"]["groups"], groups["value"]["truncated"]) == (1, False)
    [quebec] = groups["value"]["listed"]
    assert quebec["key"] == "quebec"
    assert (quebec["count"], quebec["distinct"], quebec["truncated"]) == (5, 5, False)
    assert {item["value"]: item["count"] for item in quebec["variants"]} == {
        "Québec": 1,
        "QUÉBEC": 1,
        "Quebec": 1,
        "  Québec  ": 1,
        DECOMPOSED_QUEBEC: 1,
    }
    assert province["values"]["cardinality"] == _cardinality(6)


def test_disabled_stage_no_longer_influences_results(tmp_path):
    """CA16: without trim, surrounding spaces keep a separate comparison key."""
    province = field(
        dataset(run_scan(_provinces(tmp_path), normalization={"trim": False}), "rows"),
        "province",
    )

    by_stage = stages(province)
    assert by_stage["trim"] == {
        "stage": "trim",
        "enabled": False,
        "changed": None,
        "cardinality": None,
    }
    assert by_stage["collapse_whitespace"]["changed"] == 1
    assert by_stage["strip_accents"]["cardinality"] == _cardinality(3)
    [quebec] = province["normalization"]["variant_groups"]["value"]["listed"]
    assert quebec["key"] == "quebec"
    assert quebec["count"] == 4


def test_change_counters_continue_when_tables_are_limited(tmp_path):
    """CA17, ET08 and ET09."""
    province = field(
        dataset(
            run_scan(_provinces(tmp_path), limits={"max_distinct_per_field": 2}),
            "rows",
        ),
        "province",
    )

    assert province["values"]["cardinality"]["status"] == "limited"
    assert province["values"]["cardinality"]["lower_bound"] == 3
    assert province["normalization"]["variant_groups"]["status"] == "limited"
    by_stage = stages(province)
    assert by_stage["nfc"]["changed"] == 1
    assert by_stage["trim"]["changed"] == 1
    assert by_stage["casefold"]["changed"] == 6


def _changed(field_result):
    return {name: item["changed"] for name, item in stages(field_result).items()}


def test_streaming_after_release_gives_the_same_change_counters(tmp_path):
    """Design section 13: only table-based measures differ after release."""
    lines = PROVINCES + ["a \t b", " x ", "10", "ÉCOLE"]
    source = write_text(tmp_path, "mixed.csv", "value\n" + "\n".join(lines * 3) + "\n")

    default = field(dataset(run_scan(source), "rows"), "value")
    streaming = field(
        dataset(run_scan(source, limits={"max_distinct_per_field": 1}), "rows"), "value"
    )

    assert _changed(streaming) == _changed(default)
    assert _changed(default)["collapse_whitespace"] == 3
    released = stages(streaming)
    assert released["raw"]["cardinality"] == streaming["values"]["cardinality"]
    for stage in ("nfc", "trim", "collapse_whitespace", "casefold", "strip_accents"):
        assert released[stage]["cardinality"] == {
            "status": "limited",
            "reason": "distinct_limit",
            "limit": 1,
        }
    assert streaming["normalization"]["variant_groups"] == {
        "status": "limited",
        "reason": "distinct_limit",
        "limit": 1,
    }


def test_stage_cardinalities_cover_every_value_type(tmp_path):
    """Other native types pass through the stages; only strings are grouped."""
    source = write_json(
        tmp_path,
        "mixed.json",
        [{"v": 123}, {"v": "123"}, {"v": " 123"}, {"v": True}, {"v": "ABC"}, {"v": "abc"}],
    )
    v = field(dataset(run_scan(source), "$[]"), "v")

    by_stage = stages(v)
    assert {name: item["cardinality"]["value"] for name, item in by_stage.items()} == {
        "raw": 6,
        "nfc": 6,
        "trim": 5,
        "collapse_whitespace": 5,
        "casefold": 4,
        "strip_accents": 4,
    }
    assert _changed(v) == {
        "raw": None,
        "nfc": 0,
        "trim": 1,
        "collapse_whitespace": 0,
        "casefold": 1,
        "strip_accents": 0,
    }
    groups = v["normalization"]["variant_groups"]["value"]
    assert [(group["key"], group["count"]) for group in groups["listed"]] == [
        ("123", 2),
        ("abc", 2),
    ]
    assert [item["value"] for item in groups["listed"][0]["variants"]] == [" 123", "123"]


LINE_SEPARATOR = chr(0x2028)


def test_line_breaks_are_not_collapsed(tmp_path):
    values = [f"a{LINE_SEPARATOR}b", "a\nb", "a  b"]
    source = write_json(tmp_path, "breaks.json", [{"v": value} for value in values])
    v = field(dataset(run_scan(source), "$[]"), "v")

    assert _changed(v)["collapse_whitespace"] == 1
    listed = v["values"]["frequencies"]["value"]["listed"]
    assert [item["value"] for item in listed] == ["a\nb", "a b", f"a{LINE_SEPARATOR}b"]


def test_fields_without_strings_or_values(tmp_path):
    """Design 9.9: no values, no measures."""
    source = write_text(tmp_path, "empty.csv", "number,empty\n1,\n2,\n")
    rows = dataset(run_scan(source), "rows")

    empty = field(rows, "empty")["normalization"]
    assert empty["variant_groups"] == {"status": "not_applicable", "reason": "no_values"}
    for item in empty["stages"]:
        assert item["cardinality"] == {"status": "not_applicable", "reason": "no_values"}
        assert item["changed"] == (None if item["stage"] == "raw" else 0)

    numbers = write_json(tmp_path, "numbers.json", [{"v": 1}, {"v": 2}])
    v = field(dataset(run_scan(numbers), "$[]"), "v")["normalization"]
    assert v["variant_groups"] == {"status": "not_applicable", "reason": "no_values"}
    assert {item["cardinality"]["value"] for item in v["stages"]} == {2}


def test_every_stage_disabled(tmp_path):
    disabled = dict.fromkeys(
        ["nfc", "trim", "collapse_whitespace", "casefold", "strip_accents"], False
    )
    province = field(
        dataset(run_scan(_provinces(tmp_path), normalization=disabled), "rows"),
        "province",
    )

    assert [item["enabled"] for item in province["normalization"]["stages"]] == [
        True
    ] + [False] * 5
    assert province["normalization"]["variant_groups"] == {
        "status": "complete",
        "value": {"groups": 0, "listed": [], "truncated": False},
    }
    listed = province["values"]["frequencies"]["value"]["listed"]
    assert "  Québec  " in [item["value"] for item in listed]


def test_variant_limits_truncate_listings_only(tmp_path):
    """Design 11: group and variant limits bound the output, not the measure."""
    values = ["a", "a", "a", "A", "A", "á", "b", "b", "B", "c"]
    source = write_text(tmp_path, "letters.csv", "v\n" + "\n".join(values) + "\n")
    result = run_scan(
        source, limits={"max_variant_groups": 1, "max_variants_per_group": 2}
    )
    v = field(dataset(result, "rows"), "v")

    groups = v["normalization"]["variant_groups"]
    assert groups["status"] == "complete"
    assert (groups["value"]["groups"], groups["value"]["truncated"]) == (2, True)
    assert groups["value"]["listed"] == [
        {
            "key": "a",
            "count": 6,
            "distinct": 3,
            "variants": [{"value": "a", "count": 3}, {"value": "A", "count": 2}],
            "truncated": True,
        }
    ]
    assert "measures_limited" not in {item["code"] for item in result["diagnostics"]}


def test_long_values_release_the_table_but_not_the_counters(tmp_path):
    """Design 11: the first value too long releases the table."""
    source = _provinces(tmp_path)
    default = field(dataset(run_scan(source), "rows"), "province")
    released = field(
        dataset(run_scan(source, limits={"max_stored_value_length": 8}), "rows"),
        "province",
    )

    assert _changed(released) == _changed(default)
    assert released["normalization"]["variant_groups"] == {
        "status": "limited",
        "reason": "value_too_long",
        "limit": 8,
    }
