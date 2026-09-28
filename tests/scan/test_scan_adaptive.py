"""Scan contract: adaptive detection (lot 6, design 13).

The first ``detection.warmup_values`` distinct values of a field go through
every detector; the adaptive detectors that reacted to none of them skip the
later values, except probes, which count as ``not_tested``.
"""

import pytest
from pydantic import ValidationError
from scan_helpers import dataset, detector, field, run_scan, write_text

from tabalyst.scanner.config import ScanConfig

pytestmark = pytest.mark.lot("6")

# Three words, then emails; the words come back after the warm-up.
VALUES = ["alpha", "beta", "gamma", "a@example.com", "alpha", "b@example.com", "alpha"]


def _field(tmp_path, values=VALUES, **settings) -> dict:
    source = write_text(tmp_path, "rows.csv", "value\n" + "\n".join(values) + "\n")
    return field(dataset(run_scan(source, **settings), "rows"), "value")


def test_detectors_without_reaction_skip_values_after_the_warmup(tmp_path):
    value = _field(tmp_path, detection={"warmup_values": 3, "probe_interval": 0})

    email = detector(value, "email")
    assert email["adaptive"] == {"skipped_after": 3, "not_tested": 2, "diagnostic": None}
    # Warm-up values stay tested at every occurrence.
    assert email["coverage"] == {
        "eligible": 7,
        "tested": 5,
        "matched": 0,
        "ambiguous": 0,
        "invalid": 0,
        "not_matched": 5,
        "not_tested": 2,
        "share_tested": 0.0,
        "share_eligible": 0.0,
    }
    # Every value that reacted in the warm-up keeps its detector.
    assert detector(value, "enumeration")["adaptive"] is None
    assert value["sensitive"] is False


def test_number_and_date_are_never_skipped(tmp_path):
    value = _field(tmp_path, detection={"warmup_values": 3, "probe_interval": 0})

    for identifier in ("number", "date"):
        result = detector(value, identifier)
        assert result["adaptive"] is None
        assert result["coverage"]["not_tested"] == 0


def test_fields_within_the_warmup_stay_exhaustive(tmp_path):
    value = _field(tmp_path, detection={"warmup_values": 5, "probe_interval": 0})

    assert all(item["adaptive"] is None for item in value["detectors"])
    assert detector(value, "email")["coverage"]["matched"] == 2


def test_zero_warmup_keeps_detection_exhaustive(tmp_path):
    value = _field(tmp_path, detection={"warmup_values": 0})

    assert all(item["adaptive"] is None for item in value["detectors"])
    assert detector(value, "email")["coverage"]["matched"] == 2


def test_probes_that_react_raise_a_warning(tmp_path):
    source = write_text(tmp_path, "rows.csv", "value\n" + "\n".join(VALUES) + "\n")
    # An interval of 1 probes every value after the warm-up.
    result = run_scan(source, detection={"warmup_values": 3, "probe_interval": 1})

    email = detector(field(dataset(result, "rows"), "value"), "email")
    assert email["coverage"]["matched"] == 2
    assert email["adaptive"]["not_tested"] == 0
    diagnostic = result["diagnostics"][email["adaptive"]["diagnostic"]]
    assert diagnostic["code"] == "detector_skipped_reacted"
    assert diagnostic["level"] == "warning"
    assert diagnostic["detector"] == "email"
    assert diagnostic["count"] == 2
    # A matched probe makes the field sensitive, as any match does.
    assert field(dataset(result, "rows"), "value")["sensitive"] is True


@pytest.mark.parametrize("probe_interval", [0, 1, 3])
def test_execution_modes_give_identical_adaptive_results(tmp_path, probe_interval):
    """Design principle 6 holds with adaptive detection."""
    values = [f"word{i}" for i in range(20)] + [f"u{i}@example.com" for i in range(20)]
    values = values + values[::3]
    detection = {"warmup_values": 7, "probe_interval": probe_interval}

    default = _field(tmp_path, values, detection=detection)
    streaming = _field(
        tmp_path, values, detection=detection, limits={"max_distinct_per_field": 1}
    )
    released = _field(
        tmp_path, values, detection=detection, limits={"max_distinct_per_field": 12}
    )

    def outcome(value):
        return [
            (item["id"], item["coverage"], item["formats"], item["adaptive"])
            for item in value["detectors"]
        ]

    assert outcome(streaming) == outcome(default)
    assert outcome(released) == outcome(default)
    assert streaming["technical_type"] == default["technical_type"]
    assert streaming["sensitive"] == default["sensitive"]


def test_detection_settings_are_validated():
    config = ScanConfig()
    assert config.detection.warmup_values == 10_000
    assert config.detection.probe_interval == 100
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detection": {"warmup_values": -1}})
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detection": {"probe_interval": -1}})
