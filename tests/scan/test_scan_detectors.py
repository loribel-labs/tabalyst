# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

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


def test_number_conventions_expose_ambiguity(tmp_path):
    """Design 12.6 and 12.10: the strict rule first, then decimal conventions."""
    values = ["1.5", "12,5", "1,234", "1.234,5", "1 234", "abc"]
    source = write_json(tmp_path, "amounts.json", [{"amount": v} for v in values])

    implicit = field(dataset(run_scan(source), "$[]"), "amount")
    resolved = field(
        dataset(
            run_scan(source, detectors={"number": {"ambiguous_convention": "comma"}}),
            "$[]",
        ),
        "amount",
    )

    number = detector(implicit, "number")
    assert (number["coverage"]["matched"], number["coverage"]["ambiguous"]) == (4, 1)
    assert number["details"]["ambiguity"] == {
        "count": 1,
        "candidates": [{"formats": ["#,##0", "0,0"], "count": 1}],
        "evidence": {"comma": 2, "dot": 1},
        "resolution": None,
    }
    assert implicit["numeric"]["value"]["count"] == 4
    assert implicit["numeric"]["value"]["sum"] == pytest.approx(
        1.5 + 12.5 + 1234.5 + 1234
    )
    assert resolved["numeric"]["value"]["sum"] == pytest.approx(
        1.5 + 12.5 + 1.234 + 1234.5 + 1234
    )
    assert detector(resolved, "number")["details"]["ambiguity"]["resolution"] == {
        "convention": "comma",
        "source": "config",
    }


def test_temporal_block_counts_kinds_and_ambiguous_values(tmp_path):
    """Design 9.6: kinds are never compared; ambiguous values are excluded."""
    values = [
        "2026-09-26",
        "26 septembre 2025",
        "01/02/2026",
        "2026-09-26T10:00:00",
        "2026-09-26T10:00:00+02:00",
        "10:30",
        "2026-02-30",
    ]
    source = write_json(tmp_path, "when.json", [{"when": value} for value in values])

    when = field(dataset(run_scan(source), "$[]"), "when")

    temporal = when["temporal"]["value"]
    assert (temporal["count"], temporal["ambiguous"]) == (5, 1)
    kinds = {item["kind"]: item for item in temporal["kinds"]}
    assert list(kinds) == ["date", "datetime_naive", "datetime_aware", "time"]
    assert (kinds["date"]["min"], kinds["date"]["max"]) == ("2025-09-26", "2026-09-26")
    assert kinds["date"]["years"] == [
        {"year": 2025, "count": 1},
        {"year": 2026, "count": 1},
    ]
    assert kinds["time"]["years"] is None
    assert detector(when, "date")["coverage"]["invalid"] == 1
    assert when["technical_type"]["counts"] == {"date": 3, "text": 4}


def test_enumeration_is_a_field_level_detector(tmp_path):
    """Design 12.10: every value matches together, or none does."""
    statuses = ["open", "closed"] * 3
    source = write_text(tmp_path, "status.csv", "status\n" + "\n".join(statuses) + "\n")

    small = field(dataset(run_scan(source), "rows"), "status")
    qualifying = field(
        dataset(
            run_scan(source, detectors={"enumeration": {"minimum_values": 6}}), "rows"
        ),
        "status",
    )

    assert detector(small, "enumeration")["coverage"]["matched"] == 0
    enumeration = detector(qualifying, "enumeration")
    assert enumeration["coverage"]["matched"] == 6
    assert enumeration["details"] == {"distinct": {"status": "complete", "value": 2}}
    assert qualifying["interpretations"]["primary"] == "enumeration"


def test_disabled_and_inapplicable_detectors_are_listed(tmp_path):
    """Design 8: disabled is distinct from not_applicable."""
    source = write_json(tmp_path, "values.json", [{"n": 1, "s": "x"}])

    result = run_scan(source, detectors={"boolean": {"enabled": False}})

    assert "boolean" not in result["engine"]["detectors"]
    n = field(dataset(result, "$[]"), "n")
    assert detector(n, "boolean") == {"id": "boolean", "version": 1, "status": "disabled"}
    assert detector(n, "number")["status"] == "not_applicable"
    assert n["technical_type"]["type"] == "integer"


def test_shape_rejection_is_an_exact_not_matched(tmp_path):
    """Design 12.5: values outside the declared shapes are never classified."""
    import re

    from tabalyst.scanner.detectors import Classification, Detector, default_registry

    seen = []

    class CodeDetector(Detector):
        id = "test_code"
        family = "test"
        shapes = re.compile(r"A-9")

        def classify(self, value):
            seen.append(value)
            return Classification("matched", format="A-9999")

    registry = default_registry()
    registry.register(CodeDetector)
    source = write_text(tmp_path, "codes.csv", "code\nC-0001\nc-0002\nC0003\n")

    code = field(dataset(run_scan(source, registry=registry), "rows"), "code")

    coverage = detector(code, "test_code")["coverage"]
    assert (coverage["matched"], coverage["not_matched"]) == (1, 2)
    assert seen == ["C-0001"]


def test_accumulators_receive_unmatched_values_unless_they_opt_out(tmp_path):
    """DetectorAccumulator: a subclass that overrides ``add`` receives the
    unmatched values even when its parent ignores them."""
    from tabalyst.scanner.detectors import Classification, Detector, default_registry
    from tabalyst.scanner.detectors.base import DetectorAccumulator

    received = []

    class Quiet(DetectorAccumulator):
        ignores_unmatched = True

        def add(self, value, classification, count):
            pass

    class Listening(Quiet):
        def add(self, value, classification, count):
            received.append((value, classification, count))

    class OddDetector(Detector):
        id = "test_odd"
        family = "test"

        def classify(self, value):
            return Classification("matched") if int(value) % 2 else None

        def accumulator(self):
            return Listening()

    registry = default_registry()
    registry.register(OddDetector)
    source = write_text(tmp_path, "numbers.csv", "n\n1\n2\n2\n")

    run_scan(source, registry=registry)

    assert [(value, classification) for value, classification, _ in received] == [
        ("1", Classification("matched")),
        ("2", None),
    ]
    assert sum(count for *_, count in received) == 3
