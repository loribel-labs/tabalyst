"""Scan contract: parallel scans (lot 6, design 13).

Worker processes analyze the values of fields; a scan gives the same result
with any number of workers.
"""

import json

import pytest
from scan_helpers import write_json, write_text

from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner import workers as scan_workers
from tabalyst.scanner.detectors import default_registry

pytestmark = pytest.mark.lot("6")

WORDS = ["alpha", "Beta", " gamma ", "DELTA", "Montréal", "MONTREAL", "x" * 1_200]
VALUES = [
    *WORDS,
    "12",
    "1,5",
    "1.234",
    "2026-09-26",
    "01/02/2026",
    "a@example.com",
    "a b@example.com",
    "http://example.com/a",
    "514-555-0100",
    "H2X 1Y4",
    "yes",
    "N/A",
    "",
    "  ",
]


def _rows(count: int) -> str:
    lines = ["id,value,mixed,code"]
    for index in range(count):
        value = VALUES[index % len(VALUES)]
        mixed = VALUES[(index * 7) % len(VALUES)] if index % 5 else f"w{index}"
        lines.append(f'{index},"{value}","{mixed}",C-{index % 97:04d}')
    return "\n".join(lines) + "\n"


def _document(source, workers: int, **settings) -> dict:
    result = scan(source, config=ScanConfig.model_validate(settings), workers=workers)
    document = result.model_dump(mode="json")
    document.pop("started_at")
    document.pop("duration_seconds")
    return document


SETTINGS = [
    {},
    {"limits": {"max_distinct_per_field": 5, "max_tracked_values": 40}},
    {"detection": {"warmup_values": 8, "probe_interval": 2, "rare_share": 0.2}},
    {
        "exposure": {"sensitive_values": "hide"},
        "values": {"null_markers": ["N/A"]},
        "patterns": [{"id": "code", "regex": "C-\\d{4}", "sensitive": True}],
    },
    {"limits": {"max_stored_value_length": 100, "max_tracked_records": 50}},
]


@pytest.mark.parametrize("settings", SETTINGS)
def test_csv_scans_are_identical_with_workers(tmp_path, settings):
    source = write_text(tmp_path, "rows.csv", _rows(400))

    assert _document(source, 3, **settings) == _document(source, 1, **settings)


@pytest.mark.parametrize("settings", SETTINGS)
def test_json_scans_are_identical_with_workers(tmp_path, settings):
    records = [
        {
            "id": index,
            "value": VALUES[index % len(VALUES)],
            "amount": index / 4,
            "flag": index % 3 == 0,
            "nested": {"tags": [VALUES[index % 5], index]} if index % 4 else None,
        }
        for index in range(300)
    ]
    source = write_json(tmp_path, "rows.json", {"records": records})

    assert _document(source, 2, **settings) == _document(source, 1, **settings)


def test_probe_warnings_keep_their_indices(tmp_path):
    values = [f"word{i}" for i in range(12)] + [f"u{i}@example.com" for i in range(20)]
    source = write_text(tmp_path, "rows.csv", "a,b\n" + "".join(
        f"{value},{value.upper()}\n" for value in values
    ))
    settings = {"detection": {"warmup_values": 6, "probe_interval": 1}}

    parallel = _document(source, 2, **settings)

    assert parallel == _document(source, 1, **settings)
    codes = [item["code"] for item in parallel["diagnostics"]]
    assert codes.count("detector_skipped_reacted") >= 2


def test_custom_registries_scan_in_one_process(tmp_path, monkeypatch):
    source = write_text(tmp_path, "rows.csv", _rows(50))

    def refuse(*args, **kwargs):
        raise AssertionError("a worker pool was created")

    monkeypatch.setattr("tabalyst.scanner.api.WorkerPool", refuse)
    result = scan(source, registry=default_registry(), workers=4)

    assert result.scope.records_analyzed == 50


def test_workers_that_cannot_start_leave_the_scan_in_one_process(
    tmp_path, monkeypatch
):
    source = write_text(tmp_path, "rows.csv", _rows(60))
    expected = _document(source, 1)

    def fail(*args, **kwargs):
        raise OSError("no processes here")

    monkeypatch.setattr(scan_workers.subprocess, "Popen", fail)

    assert _document(source, 2) == expected


def test_workers_that_stop_at_start_leave_the_scan_in_one_process(
    tmp_path, monkeypatch
):
    source = write_text(tmp_path, "rows.csv", _rows(60))
    expected = _document(source, 1)
    monkeypatch.setattr(scan_workers, "_BOOTSTRAP", "import sys; sys.exit(3)")

    assert _document(source, 2) == expected


def test_worker_count_is_automatic_for_large_sources():
    small = scan_workers.MIN_PARALLEL_BYTES - 1
    assert scan_workers.worker_count(None, small) == 1
    assert scan_workers.worker_count(1, 10 * scan_workers.MIN_PARALLEL_BYTES) == 1
    assert scan_workers.worker_count(3, small) == 3
    assert 1 <= scan_workers.worker_count(None, scan_workers.MIN_PARALLEL_BYTES) <= (
        scan_workers.MAX_WORKERS
    )


def test_diagnostics_of_workers_are_reported_in_field_order():
    blocks = {
        "detectors": [
            {"id": "a", "status": "failed", "diagnostic": -2},
            {"id": "b", "status": "complete", "adaptive": {"diagnostic": -1}},
            {"id": "c", "status": "complete", "adaptive": None},
        ],
        "temporal": {"status": "failed", "diagnostic": -2},
    }

    remapped = scan_workers._with_diagnostics(json.loads(json.dumps(blocks)), [7, 9])

    assert remapped["detectors"][0]["diagnostic"] == 9
    assert remapped["detectors"][1]["adaptive"]["diagnostic"] == 7
    assert remapped["temporal"]["diagnostic"] == 9
