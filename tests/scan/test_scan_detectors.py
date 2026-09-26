"""Scan contract: detector framework, coverage and ambiguity (lot 3a)."""

import pytest
from scan_helpers import dataset, detector, field, run_scan, write_json, write_text

pytestmark = pytest.mark.lot("3a")

WHEN = ["2026-09-26", "26/09/2026", "x"]


def test_technical_type_includes_a_late_anomaly(tmp_path):
    """CA01: the anomaly in the last record is part of the inference."""
    numbers = "\n".join(str(number) for number in range(1, 20))
    source = write_text(tmp_path, "amounts.csv", f"amount\n{numbers}\nabc\n")

    amount = field(dataset(run_scan(source), "rows"), "amount")

    assert amount["technical_type"] == {
        "type": "integer",
        "confidence": 0.95,
        "counts": {"integer": 19, "text": 1},
        "outside_count": 1,
    }


def test_csv_and_json_strings_get_the_same_detection(tmp_path):
    """CA02 and CA10: one engine, several readers, formats counted."""
    csv_source = write_text(tmp_path, "when.csv", "when\n" + "\n".join(WHEN) + "\n")
    json_source = write_json(tmp_path, "when.json", [{"when": value} for value in WHEN])

    from_csv = detector(field(dataset(run_scan(csv_source), "rows"), "when"), "date")
    from_json = detector(field(dataset(run_scan(json_source), "$[]"), "when"), "date")

    assert from_csv["coverage"] == from_json["coverage"]
    assert from_csv["formats"] == from_json["formats"]
    assert from_csv["coverage"] == {
        "eligible": 3,
        "tested": 3,
        "matched": 2,
        "ambiguous": 0,
        "invalid": 0,
        "not_matched": 1,
        "not_tested": 0,
        "share_tested": pytest.approx(2 / 3, abs=1e-4),
        "share_eligible": pytest.approx(2 / 3, abs=1e-4),
    }
    assert sorted((item["format"], item["count"]) for item in from_csv["formats"]) == [
        ("DD/MM/YYYY", 1),
        ("YYYY-MM-DD", 1),
    ]


def test_coverage_denominators_are_explicit(tmp_path):
    """CA11: one date among many values is never a global match."""
    values = ["text"] * 99 + ["2026-09-26"]
    source = write_text(tmp_path, "notes.csv", "note\n" + "\n".join(values) + "\n")

    note = field(dataset(run_scan(source), "rows"), "note")
    coverage = detector(note, "date")["coverage"]

    assert coverage["eligible"] == 100
    assert coverage["tested"] == coverage["eligible"] - coverage["not_tested"]
    assert coverage["tested"] == (
        coverage["matched"]
        + coverage["ambiguous"]
        + coverage["invalid"]
        + coverage["not_matched"]
    )
    assert coverage["matched"] == 1
    assert coverage["share_tested"] == pytest.approx(0.01)
    assert coverage["share_eligible"] == pytest.approx(0.01)
    assert note["interpretations"] == {"primary": None, "candidates": []}


def test_ambiguous_dates_stay_ambiguous_without_explicit_configuration(tmp_path):
    """CA12, O06 and specification 12.1: evidence is exposed, never applied."""
    source = write_text(tmp_path, "dates.csv", "day\n01/02/2026\n13/02/2026\n")

    implicit = detector(field(dataset(run_scan(source), "rows"), "day"), "date")
    configured = detector(
        field(
            dataset(
                run_scan(source, detectors={"date": {"ambiguous_order": "DMY"}}), "rows"
            ),
            "day",
        ),
        "date",
    )

    assert (implicit["coverage"]["matched"], implicit["coverage"]["ambiguous"]) == (1, 1)
    ambiguity = implicit["details"]["ambiguity"]
    assert ambiguity["count"] == 1
    assert ambiguity["candidates"] == [
        {"formats": ["DD/MM/YYYY", "MM/DD/YYYY"], "count": 1}
    ]
    assert ambiguity["evidence"] == {"DMY": 1, "MDY": 0}
    assert ambiguity["resolution"] is None
    assert (configured["coverage"]["matched"], configured["coverage"]["ambiguous"]) == (
        2,
        0,
    )
    assert configured["details"]["ambiguity"]["resolution"] == {
        "order": "DMY",
        "source": "config",
    }


def test_a_failing_detector_is_isolated(tmp_path):
    """CA19: a failure is a diagnostic, not a set of non-matching values."""
    from tabalyst.scanner.detectors import Detector, default_registry

    class ExplodingDetector(Detector):
        id = "test_exploding"
        family = "test"

        def classify(self, value):
            """Match nothing, and fail on one value."""
            if value == "boom":
                raise RuntimeError("boom")

    registry = default_registry()
    registry.register(ExplodingDetector)
    source = write_text(tmp_path, "values.csv", "value\n2026-09-26\nboom\nx\n")

    result = run_scan(source, registry=registry)

    value = field(dataset(result, "rows"), "value")
    exploding = detector(value, "test_exploding")
    assert exploding["status"] == "failed"
    assert exploding.get("coverage") is None
    assert detector(value, "date")["status"] == "complete"
    diagnostic = result["diagnostics"][exploding["diagnostic"]]
    assert diagnostic["code"] == "detector_failed"
    assert diagnostic["level"] == "error"
    assert diagnostic["detector"] == "test_exploding"
    assert result["status"] == "complete"


def test_execution_modes_give_identical_results(tmp_path):
    """Design principle 6: releasing tables changes speed, never results."""
    lines = ["10", "2026-09-26", " Québec ", "QUÉBEC", "01/02/2026", "4.5", "x"] * 3
    source = write_text(tmp_path, "mixed.csv", "value\n" + "\n".join(lines) + "\n")

    default = field(dataset(run_scan(source), "rows"), "value")
    streaming = field(
        dataset(run_scan(source, limits={"max_distinct_per_field": 1}), "rows"), "value"
    )

    for block in (
        "presence",
        "native_types",
        "strings",
        "string_characteristics",
        "string_lengths",
        "technical_type",
        "interpretations",
    ):
        assert streaming[block] == default[block], block
    assert [(item["stage"], item["changed"]) for item in streaming["normalization"]["stages"]] == [
        (item["stage"], item["changed"]) for item in default["normalization"]["stages"]
    ]
    for name in ("count", "min", "max", "sum", "mean", "population_variance"):
        assert streaming["numeric"]["value"][name] == default["numeric"]["value"][name]
    assert [
        (item["id"], item["coverage"], item["formats"]) for item in streaming["detectors"]
    ] == [(item["id"], item["coverage"], item["formats"]) for item in default["detectors"]]
