# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

import tabalyst
from tabalyst.batch import write_text_atomic
from tabalyst.cli import app
from tabalyst.cli.terminal import ProgressPrinter
from tabalyst.config import load_config
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.progress import ProgressEvent, ProgressPhase
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner.config import resolve_scan_config
from tabalyst.scanner.readers.json_reader import _has_long_digit_run

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolated_project_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage"))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _config(path, document):
    return _write(path, json.dumps(document))


# Command and outputs ------------------------------------------------------


def test_scan_writes_shared_scan_document_without_database(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    source = _write(tmp_path / "customers.csv", "id,city\n1,Montréal\n2,Laval\n")

    result = runner.invoke(app, ["scan", str(source)])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    assert "Scanned 2 records: 1 dataset, 2 fields." in result.stderr
    location = StorageLocation.local()
    scan_path = location.shared_scan_path(source)
    assert not location.projects_dir.exists()
    document = json.loads(scan_path.read_text(encoding="utf-8"))
    assert document["format"] == "tabalyst.scan"
    assert document["source"]["name"] == "customers.csv"
    assert document["config"]["json"]["collections"] is None
    assert [field["name"] for field in document["datasets"][0]["fields"]] == [
        "id",
        "city",
    ]
    # Nothing else, such as a temporary file, is left beside the source.
    assert sorted(path.name for path in tmp_path.iterdir()) == ["customers.csv", "storage"]


def test_scan_accepts_json_sources_and_collections(tmp_path):
    source = _write(
        tmp_path / "orders.json",
        json.dumps({"customers": [{"id": 1}, {"id": 2}], "meta": {"v": 1}}),
    )
    output = tmp_path / "out" / "orders-scan.json"

    result = runner.invoke(
        app,
        ["scan", str(source), "-o", str(output), "--collection", "$.customers[]"],
    )

    assert result.exit_code == 0, result.output
    document = json.loads(output.read_text(encoding="utf-8"))
    assert [dataset["id"] for dataset in document["datasets"]] == ["$.customers[]"]
    assert document["scope"]["collections"] == {
        "mode": "explicit",
        "requested": ["$.customers[]"],
    }


def test_scan_output_directory_names_scans_after_sources(tmp_path):
    first = _write(tmp_path / "a.csv", "x\n1\n")
    second = _write(tmp_path / "b.json", '[{"x": 1}, {"x": 2}]')
    destination = tmp_path / "scans"

    result = runner.invoke(
        app, ["scan", str(tmp_path / "*.*"), "-d", str(destination), "-v"]
    )

    assert result.exit_code == 0, result.output
    assert (destination / "a.scan.json").is_file()
    assert (destination / "b.scan.json").is_file()
    assert f"Scan: {first} ->" in result.stderr
    assert f"Scan: {second} ->" in result.stderr
    assert "2 succeeded, 0 failed" in result.stderr


def test_scan_rejects_unsafe_plans_before_scanning(tmp_path):
    csv_source = _write(tmp_path / "data.csv", "x\n1\n")
    json_source = _write(tmp_path / "data.json", "[1]")

    collision = runner.invoke(
        app, ["scan", str(csv_source), str(json_source), "-d", str(tmp_path / "scans")]
    )
    assert collision.exit_code == 1
    assert "Output name collision" in collision.stderr
    assert not (tmp_path / "data.scan.json").exists()

    overwrite = runner.invoke(
        app, ["scan", str(json_source), "-o", str(json_source), "--force"]
    )
    assert overwrite.exit_code == 4
    assert "would overwrite an input file" in overwrite.stderr

    suffix = runner.invoke(app, ["scan", str(csv_source), "-o", str(tmp_path / "x")])
    assert suffix.exit_code == 4
    assert "ending in .json" in suffix.stderr

    single = runner.invoke(
        app, ["scan", str(csv_source), str(json_source), "-o", str(tmp_path / "x.json")]
    )
    assert single.exit_code == 2


def test_scan_never_replaces_a_configuration_file(tmp_path):
    source = _write(tmp_path / "data.csv", "x\n1\n")
    config = _config(tmp_path / "data.scan.json", {})

    result = runner.invoke(
        app, ["scan", str(source), "-c", str(config), "-o", str(config), "--force"]
    )

    assert result.exit_code == 4
    assert "would overwrite an input file" in result.stderr
    assert json.loads(config.read_text(encoding="utf-8")) == {}


def test_existing_scan_requires_force(tmp_path):
    source = _write(tmp_path / "data.csv", "x\n1\n")
    output = _write(tmp_path / "data.scan.json", "previous")

    refused = runner.invoke(app, ["scan", str(source), "-o", str(output)])
    assert refused.exit_code == 1
    assert "Use --force" in refused.stderr
    assert output.read_text(encoding="utf-8") == "previous"

    replaced = runner.invoke(
        app, ["scan", str(source), "-o", str(output), "--force", "-q"]
    )
    assert replaced.exit_code == 0, replaced.output
    assert replaced.stderr == ""
    assert json.loads(output.read_text(encoding="utf-8"))["format"] == "tabalyst.scan"


def test_failed_source_does_not_stop_the_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    broken = _write(tmp_path / "broken.json", "[1,")
    valid = _write(tmp_path / "valid.csv", "x\n1\n")

    result = runner.invoke(app, ["scan", str(broken), str(valid)])

    assert result.exit_code == 4
    assert f"Error [{broken}]: Invalid JSON in broken.json" in result.stderr
    assert "1 succeeded, 1 failed" in result.stderr
    assert not (tmp_path / "broken.scan.json").exists()
    assert StorageLocation.local().shared_scan_path(valid).is_file()


def test_partial_scan_succeeds_with_a_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    source = _write(tmp_path / "data.csv", "a,b\n1,2\n3\n4,5\n")
    config = _config(tmp_path / "tolerant.json", {"scan": {"errors": {"policy": "tolerant"}}})

    result = runner.invoke(app, ["scan", str(source), "-c", str(config), "-q"])

    assert result.exit_code == 0, result.output
    assert "partial scan, 1 record excluded (width_mismatch: 1)" in result.stderr
    document = json.loads(
        StorageLocation.local()
        .shared_scan_path(source)
        .read_text(encoding="utf-8")
    )
    assert document["status"] == "partial"


def test_strict_csv_error_exits_with_input_code(tmp_path):
    source = _write(tmp_path / "data.csv", "a,b\n1,2\n3\n")

    result = runner.invoke(app, ["scan", str(source)])

    assert result.exit_code == 4
    assert not (tmp_path / "data.scan.json").exists()


def test_atomic_write_keeps_the_previous_file_on_failure(tmp_path, monkeypatch):
    target = _write(tmp_path / "result.json", "previous")

    def fail(source, destination):
        raise OSError("disk full")

    monkeypatch.setattr("tabalyst.batch.os.replace", fail)
    with pytest.raises(OSError, match="disk full"):
        write_text_atomic(target, "new")

    assert target.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.iterdir()) == [target]


# Configuration layers -----------------------------------------------------


def test_scan_configuration_files_merge_in_order(tmp_path):
    first = _config(
        tmp_path / "first.json",
        {
            "value_examples": {"inline_display_size": 5},
            "scan": {
                "values": {"null_markers": ["N/A", "NULL"]},
                "detectors": {"number": {"conventions": ["dot"]}},
                "limits": {"max_samples": 5},
            },
        },
    )
    second = _config(
        tmp_path / "second.json",
        {
            "scan": {
                "values": {"null_markers": ["-"]},
                "detectors": {"number": {"enabled": False}},
            }
        },
    )

    config = resolve_scan_config([first, second], delimiter=";")

    assert config.values.null_markers == ["-"]
    assert config.detectors.number.enabled is False
    assert config.detectors.number.conventions == ["dot"]
    assert config.limits.max_samples == 5
    assert config.csv.delimiter == ";"
    assert config.csv.encoding == "utf-8-sig"


def test_command_line_collections_replace_configured_ones(tmp_path):
    config = _config(
        tmp_path / "config.json",
        {"scan": {"json": {"collections": ["$.a[]", "$.b[]"]}}},
    )

    resolved = resolve_scan_config([config], collections=["$.c[]"])

    assert resolved.json_.collections == ["$.c[]"]
    assert resolve_scan_config([config]).json_.collections == ["$.a[]", "$.b[]"]


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ({"scan": {"limits": {"max_fieldz": 1}}}, "scan.limits.max_fieldz"),
        ({"scan": {"limits": {"max_samples": 10**9}}}, "scan.limits.max_samples"),
        ({"scan": None}, "scan: Input should be a valid dictionary"),
        ({"scan": {"detectors": {"unknown": {}}}}, "scan.detectors.unknown"),
        ({"preview_rowz": 1, "scan": {}}, "preview_rowz"),
    ],
)
def test_invalid_configuration_names_file_and_key(tmp_path, document, message):
    config = _config(tmp_path / "config.json", document)

    with pytest.raises(ConfigurationError, match="config.json") as scan_error:
        resolve_scan_config([config])
    assert message in str(scan_error.value)
    # The report validates the scan section too, and the scan the rest.
    with pytest.raises(ConfigurationError) as report_error:
        load_config([config])
    assert message in str(report_error.value)


def test_report_ignores_a_valid_scan_section(tmp_path):
    config = _config(
        tmp_path / "config.json",
        {"value_examples": {"inline_display_size": 4}, "scan": {"csv": {"delimiter": ";"}}},
    )

    report_config = load_config([config])

    assert report_config.value_examples.inline_display_size == 4
    assert report_config.csv.delimiter == ","
    assert resolve_scan_config([config]).csv.delimiter == ";"


def test_configuration_file_must_hold_a_json_object(tmp_path):
    invalid = _write(tmp_path / "invalid.json", "{")
    array = _write(tmp_path / "array.json", "[]")

    with pytest.raises(ConfigurationError, match="invalid JSON"):
        resolve_scan_config([invalid])
    with pytest.raises(ConfigurationError, match="JSON object"):
        load_config([array])


# Workers --------------------------------------------------------------------


def _scan_document(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    document.pop("started_at")
    document.pop("duration_seconds")
    return document


def test_scan_workers_do_not_change_the_document(tmp_path):
    rows = "".join(f"{i},name{i % 7},{i % 3 == 0}\n" for i in range(200))
    source = _write(tmp_path / "data.csv", "id,name,flag\n" + rows)

    single = runner.invoke(app, ["scan", str(source), "-o", str(tmp_path / "a.json")])
    parallel = runner.invoke(
        app, ["scan", str(source), "-o", str(tmp_path / "b.json"), "--workers", "2"]
    )

    assert single.exit_code == 0, single.output
    assert parallel.exit_code == 0, parallel.output
    assert _scan_document(tmp_path / "b.json") == _scan_document(tmp_path / "a.json")


def test_scan_workers_must_be_positive(tmp_path):
    source = _write(tmp_path / "data.csv", "x\n1\n")

    result = runner.invoke(app, ["scan", str(source), "--workers", "0"])

    assert result.exit_code == 2
    with pytest.raises(ConfigurationError, match="workers"):
        tabalyst.scan(source, workers=0)


def test_report_workers_cannot_be_used_with_scan_documents(tmp_path):
    source = _write(tmp_path / "data.csv", "x\n1\n")
    assert runner.invoke(
        app, ["scan", str(source), "-o", str(tmp_path / "data.scan.json")]
    ).exit_code == 0

    result = runner.invoke(
        app, ["report", "--scan", str(tmp_path / "data.scan.json"), "--workers", "2"]
    )

    assert result.exit_code == 2
    assert "--workers cannot be used with --scan" in result.stderr


def test_report_accepts_workers(tmp_path):
    source = _write(tmp_path / "data.csv", "x,y\n1,a\n2,b\n")

    result = runner.invoke(app, ["report", str(source), "--workers", "2"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "data.html").exists()


# Python API and progress --------------------------------------------------


def test_top_level_scan_returns_a_result_without_writing(tmp_path):
    source = _write(tmp_path / "data.csv", "x\n1\n2\n")

    result = tabalyst.scan(source, config=tabalyst.ScanConfig())

    assert isinstance(result, tabalyst.ScanResult)
    assert result.scope.records_analyzed == 2
    assert list(tmp_path.iterdir()) == [source]


def test_generate_scans_reports_byte_progress_then_completion(tmp_path):
    source = _write(tmp_path / "data.csv", "x\n" + "1\n" * 10)
    events: list[ProgressEvent] = []

    batch = tabalyst.generate_scans([source], on_progress=events.append)

    assert batch.succeeded
    assert batch.successes[0].job.output == tmp_path / "data.scan.json"
    phases = [event.phase for event in events]
    assert phases == [
        ProgressPhase.READING,
        ProgressPhase.WRITING,
        ProgressPhase.COMPLETE,
    ]
    assert events[0].bytes_read == 0
    assert events[0].bytes_total == source.stat().st_size
    assert all(event.index == 1 and event.total == 1 for event in events)


def test_scan_reports_reading_progress_by_bytes(tmp_path):
    source = _write(tmp_path / "data.csv", "x\n" + "123456789\n" * 250_000)
    events: list[ProgressEvent] = []

    tabalyst.scan(source, on_progress=events.append)

    reading = [event for event in events if event.phase == ProgressPhase.READING]
    size = source.stat().st_size
    assert reading[0].bytes_read == 0
    assert len(reading) >= 2
    assert all(event.bytes_total == size for event in reading)
    counts = [event.bytes_read for event in reading]
    assert counts == sorted(counts)
    assert counts[-1] <= size


def test_progress_printer_shows_the_share_read(capsys):
    printer = ProgressPrinter(enabled=True)
    printer(
        ProgressEvent(
            source=Path("data.csv"),
            phase=ProgressPhase.READING,
            index=1,
            total=2,
            bytes_read=512,
            bytes_total=1024,
        )
    )

    assert "[1/2] data.csv - Reading 50%" in capsys.readouterr().err


# Oversized JSON numbers ---------------------------------------------------


def test_long_digit_runs_are_found_across_read_chunks(tmp_path):
    chunk = 1 << 20
    limit = sys.get_int_max_str_digits()
    spanning = tmp_path / "spanning.json"
    spanning.write_bytes(b"[" + b" " * (chunk - 101) + b"1" * (limit + 1) + b"]")
    short = tmp_path / "short.json"
    short.write_bytes(b"[" + b" " * (chunk - 101) + b"1" * limit + b", 1]")

    assert _has_long_digit_run(spanning)
    assert not _has_long_digit_run(short)


@pytest.mark.parametrize(
    "text",
    [
        "1" * 5000,
        '["' + "a" * 65530 + '",' + "1" * 5000 + "]",
        "[-" + "1" * 5000 + "]",
    ],
    ids=["scalar", "straddling-buffers", "negative"],
)
def test_oversized_integers_are_input_errors_not_crashes(tmp_path, text):
    source = _write(tmp_path / "big.json", text)
    code = (
        "from tabalyst.errors import InputError\n"
        "from tabalyst.scanner import scan\n"
        "try:\n"
        f"    scan({str(source)!r})\n"
        "except InputError as exc:\n"
        "    print('InputError', len(str(exc)))\n"
    )

    # A subprocess: the compiled parser used to crash the interpreter.
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    kind, length = completed.stdout.split()
    assert kind == "InputError"
    assert int(length) < 400


def test_integers_within_the_limit_still_scan(tmp_path):
    limit = sys.get_int_max_str_digits()
    source = _write(tmp_path / "big.json", "[" + "7" * limit + "]")

    result = tabalyst.scan(source)

    assert result.status == "complete"


def test_out_of_range_exponent_is_an_input_error(tmp_path):
    source = _write(tmp_path / "exponent.json", "[1e9999999999999999999]")

    with pytest.raises(InputError, match="exponent out of range"):
        tabalyst.scan(source)
