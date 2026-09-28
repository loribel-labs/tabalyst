"""Scan contract: adaptive detection (lot 6, design 13).

The first ``detection.warmup_values`` distinct values of a field go through
every detector; the adaptive detectors that reacted to none of them, or to at
most ``detection.rare_share`` of them and none in the second half of the
warm-up, skip the later values, except probes, which count as ``not_tested``.
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
    assert email["adaptive"] == {
        "skipped_after": 3,
        "warmup_reactions": 0,
        "not_tested": 2,
        "diagnostic": None,
    }
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
    assert config.detection.rare_share == 0.001
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detection": {"warmup_values": -1}})
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detection": {"probe_interval": -1}})
    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"detection": {"rare_share": 1.5}})


# Rare detectors: a warm-up of 20 values, where at most 2 reactions are rare
# (``rare_share`` 0.1) and the second half starts at the 11th value.
RARE = {"warmup_values": 20, "probe_interval": 0, "rare_share": 0.1}
URLS = ["http://example.com/1", "http://example.com/2"]
WORDS = [f"word{i}" for i in range(40)]


def test_rare_detectors_silent_in_the_second_half_are_skipped(tmp_path):
    # Two URLs open the warm-up, then only words.
    value = _field(tmp_path, URLS + WORDS, detection=RARE)

    url = detector(value, "url")
    assert url["adaptive"] == {
        "skipped_after": 20,
        "warmup_reactions": 2,
        "not_tested": 22,
        "diagnostic": None,
    }
    assert url["coverage"]["matched"] == 2
    assert url["coverage"]["tested"] == 20


def test_rare_detectors_reacting_in_the_second_half_stay(tmp_path):
    # The second URL is the 15th value: the reactions have not stopped.
    values = [URLS[0], *WORDS[:13], URLS[1], *WORDS[13:]]

    url = detector(_field(tmp_path, values, detection=RARE), "url")

    assert url["adaptive"] is None
    assert url["coverage"]["not_tested"] == 0


def test_detectors_above_the_rare_share_stay(tmp_path):
    values = [*URLS, "http://example.com/3", *WORDS]

    url = detector(_field(tmp_path, values, detection=RARE), "url")

    assert url["adaptive"] is None


def test_zero_rare_share_skips_only_detectors_without_reaction(tmp_path):
    value = _field(tmp_path, URLS + WORDS, detection={**RARE, "rare_share": 0})

    assert detector(value, "url")["adaptive"] is None
    assert detector(value, "email")["adaptive"]["warmup_reactions"] == 0


def test_rare_sensitive_detectors_without_match_stay(tmp_path):
    # Invalid addresses are reactions, but the field is not masked yet.
    values = ["a b@example.com", "c d@example.com", *WORDS]

    email = detector(_field(tmp_path, values, detection=RARE), "email")

    assert email["coverage"]["invalid"] == 2
    assert email["adaptive"] is None


def test_rare_sensitive_detectors_that_matched_are_skipped(tmp_path):
    values = ["a@example.com", *WORDS]

    value = _field(tmp_path, values, detection=RARE)

    assert detector(value, "email")["adaptive"]["warmup_reactions"] == 1
    assert value["sensitive"] is True


def test_rare_detectors_reacting_more_often_later_raise_a_warning(tmp_path):
    # A sorted column: URLs become frequent after the warm-up.
    urls = [f"http://example.com/{i}" for i in range(3, 33)]
    source = write_text(
        tmp_path,
        "rows.csv",
        "value\n" + "\n".join([URLS[0], *WORDS[:19], *urls]) + "\n",
    )
    result = run_scan(source, detection={**RARE, "probe_interval": 1})

    url = detector(field(dataset(result, "rows"), "value"), "url")
    assert url["adaptive"]["warmup_reactions"] == 1
    assert url["coverage"]["matched"] == 31
    diagnostic = result["diagnostics"][url["adaptive"]["diagnostic"]]
    assert diagnostic["code"] == "detector_skipped_reacted"
    assert diagnostic["count"] == 30
    assert "reacted to only 1 of the first 20" in diagnostic["message"]


def test_rare_detectors_reacting_rarely_later_raise_no_warning(tmp_path):
    # Probes react, but no more often than the warm-up allowed.
    values = [URLS[0], *WORDS[:19], URLS[1], *WORDS[19:]]
    source = write_text(tmp_path, "rows.csv", "value\n" + "\n".join(values) + "\n")
    result = run_scan(source, detection={**RARE, "probe_interval": 1})

    url = detector(field(dataset(result, "rows"), "value"), "url")
    assert url["coverage"]["matched"] == 2
    assert url["adaptive"]["diagnostic"] is None
    assert not result["diagnostics"]


@pytest.mark.parametrize("probe_interval", [0, 1, 3])
def test_execution_modes_give_identical_rare_results(tmp_path, probe_interval):
    """Design principle 6 holds with rare detectors."""
    urls = [f"http://example.com/{i}" for i in range(10)]
    values = urls[:2] + WORDS + urls[2:] + WORDS[::3] + urls[::2]
    detection = {**RARE, "probe_interval": probe_interval}

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

    assert detector(default, "url")["adaptive"]["warmup_reactions"] == 2
    assert outcome(streaming) == outcome(default)
    assert outcome(released) == outcome(default)
