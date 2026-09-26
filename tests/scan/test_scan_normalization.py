"""Scan contract: normalization version 1 and variant groups (lot 2b)."""

import pytest
from scan_helpers import dataset, field, run_scan, stages, write_text

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
    [quebec] = groups["value"]
    assert quebec["key"] == "quebec"
    assert quebec["count"] == 5
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
    [quebec] = province["normalization"]["variant_groups"]["value"]
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
