# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""``tabalyst sample --sample-method smart`` and the report it writes (design
20.16, lot 10b)."""

import csv
import json
from pathlib import Path

import pytest
from scan_helpers import write_text
from smart_helpers import NORMAL, SINGLETONS, region_rows
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.errors import InputError
from tabalyst.sampling_service import generate_samples
from tabalyst.scanner.planner.secondpass import Confirmation, TimeEstimate
from tabalyst.scanner.smart.result import FORMAT, sample_schema
from tabalyst.smart_service import SelectionConfirmationRequired

runner = CliRunner()


@pytest.fixture(autouse=True)
def _storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-storage"))


def _source(tmp_path: Path, rows: list[str] | None = None) -> Path:
    body = region_rows() if rows is None else rows
    return write_text(tmp_path, "data.csv", "region,n\n" + "\n".join(body) + "\n")


def _read(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.reader(stream))


def test_a_smart_sample_writes_the_rows_and_a_report_beside_it(tmp_path):
    source = _source(tmp_path)

    batch = generate_samples([source], method="smart", rows=60)

    [success] = batch.successes
    result = success.result
    rows = _read(result.output)
    assert rows[0] == ["region", "n"] and len(rows) == 61
    assert {row[0] for row in rows[1:]} == set(NORMAL) | set(SINGLETONS)
    # In the order of the source, without a column added.
    numbers = [int(row[1]) for row in rows[1:]]
    assert numbers == sorted(numbers)
    assert result.report == result.output.with_suffix(".json")
    document = json.loads(result.report.read_text(encoding="utf-8"))
    assert document["format"] == FORMAT and document["coverage"]["scope"] == "target_catalog"
    assert document["output"]["rows"] == 60
    assert result.smart is not None and result.smart.mandatory_covered == 23
    assert result.smart.scan_ran and result.smart.passes == 2


def test_the_report_follows_its_json_schema(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    source = _source(tmp_path)

    [success] = generate_samples([source], method="smart", rows=40).successes

    document = json.loads(success.result.report.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(sample_schema()).validate(document)


def test_the_same_seed_gives_the_same_file_and_a_current_scan_is_not_read_again(tmp_path):
    source = _source(tmp_path)
    first = generate_samples([source], method="smart", rows=50, seed=7, output=tmp_path / "a.csv")
    second = generate_samples([source], method="smart", rows=50, seed=7, output=tmp_path / "b.csv")

    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()
    assert first.successes[0].result.smart.scan_ran
    again = second.successes[0].result.smart
    assert not again.scan_ran and again.passes == 1


def test_percent_asks_for_a_share_of_the_rows_and_too_many_rows_stop_the_run(tmp_path):
    source = _source(tmp_path)

    [success] = generate_samples([source], method="smart", percent=5).successes
    assert success.result.sample_rows == 66

    batch = generate_samples([source], method="smart", rows=5_000, output=tmp_path / "big.csv")
    assert isinstance(batch.failures[0].error, InputError)
    assert not (tmp_path / "big.csv").exists()


def test_a_source_that_changes_between_the_scan_and_the_selection_leaves_no_output(tmp_path):
    from tabalyst.smart_service import execute_smart_samples, prepare_smart_samples

    source = _source(tmp_path)
    preparation = prepare_smart_samples([source], rows=30)
    text = source.read_text(encoding="utf-8")
    source.write_text(text.replace("Region-A", "Region-Z", 1), encoding="utf-8", newline="")

    batch = execute_smart_samples(preparation)

    assert batch.failures and not batch.successes
    assert not list(tmp_path.glob("data.sample.*"))


def test_a_costly_selection_needs_a_confirmation_and_never_asks_through_the_api(
    tmp_path, monkeypatch
):
    source = _source(tmp_path)
    costly = Confirmation(True, ("time_over_threshold",), 1, TimeEstimate(100.0, 900.0))
    monkeypatch.setattr(
        "tabalyst.smart_service.estimate_selection", lambda plan, scan: costly
    )

    with pytest.raises(SelectionConfirmationRequired) as raised:
        generate_samples([source], method="smart", rows=30)
    assert raised.value.confirmation.reasons == costly.reasons
    assert raised.value.confirmation.estimate == costly.estimate
    assert not list(tmp_path.glob("data.sample.*"))

    [success] = generate_samples([source], method="smart", rows=30, confirmed=True).successes
    assert success.result.output.exists()


def test_the_command_writes_the_sample_and_names_what_it_covers(tmp_path):
    source = _source(tmp_path)

    done = runner.invoke(
        app, ["sample", str(source), "--sample-method", "smart", "--rows", "60"]
    )

    assert done.exit_code == 0, done.output
    assert "Targets:" in done.output and "23 of 23 covered" in done.output
    assert "not those of the population" in done.output
    assert (tmp_path / "data.sample.csv").exists() and (tmp_path / "data.sample.json").exists()


def test_outside_a_terminal_a_costly_selection_stops_with_exit_code_three(tmp_path, monkeypatch):
    source = _source(tmp_path)
    costly = Confirmation(True, ("time_over_threshold",), 1, TimeEstimate(100.0, 900.0))
    monkeypatch.setattr(
        "tabalyst.smart_service.estimate_selection", lambda plan, scan: costly
    )

    refused = runner.invoke(app, ["sample", str(source), "--sample-method", "smart", "--rows", "30"])
    assert refused.exit_code == 3 and not (tmp_path / "data.sample.csv").exists()

    allowed = runner.invoke(
        app, ["sample", str(source), "--sample-method", "smart", "--rows", "30", "--yes"]
    )
    assert allowed.exit_code == 0 and (tmp_path / "data.sample.csv").exists()


def test_yes_only_goes_with_a_smart_sample(tmp_path):
    source = _source(tmp_path)

    result = runner.invoke(app, ["sample", str(source), "--sample-method", "first", "--rows", "3", "--yes"])

    assert result.exit_code != 0


def test_a_smart_sample_reads_csv_files_only(tmp_path):
    source = write_text(tmp_path, "data.json", json.dumps([{"a": i} for i in range(20)]))

    batch = generate_samples([source], method="smart", rows=5, output=tmp_path / "x.csv")

    assert batch.failures and not batch.successes


def _wide_strata(tmp_path: Path) -> Path:
    """110,000 rows whose two columns make 110,000 distinct pairs."""
    rows = (f"{i % 400},{(i // 400) % 400},{i}" for i in range(110_000))
    return write_text(tmp_path, "wide.csv", "a,b,n\n" + "\n".join(rows) + "\n")


def test_a_stored_scan_stops_a_stratification_with_too_many_strata_before_reading(tmp_path):
    from tabalyst.scan_service import generate_scans

    source = _wide_strata(tmp_path)
    generate_scans([source], project_storage=True, refresh=False)

    with pytest.raises(InputError, match="Nothing was read"):
        generate_samples([source], method="stratified", rows=100, field=["a", "b"])
    assert not (tmp_path / "wide.sample.csv").exists()

    # An explicit limit allows it: the bound proves a risk, not an explosion.
    [success] = generate_samples(
        [source], method="stratified", rows=100, field=["a", "b"], max_strata=200_000
    ).successes
    assert success.result.strata_known == 110_000


def test_without_a_stored_scan_a_stratified_sample_makes_none_and_reads_the_file(tmp_path):
    source = _wide_strata(tmp_path)

    batch = generate_samples([source], method="stratified", rows=100, field=["a", "b"])

    # No Scan was stored, so nothing was advised and none was made: the runtime
    # cap of the sample is what stops it.
    assert batch.failures and "more than" in str(batch.failures[0].error)


def test_a_semicolon_file_with_a_byte_order_mark_comes_out_the_same_way(tmp_path):
    body = "\n".join(f"{name};{number}" for number, name in enumerate(NORMAL * 12))
    source = tmp_path / "data.csv"
    source.write_bytes(b"\xef\xbb\xbf" + f"region;n\n{body}\n".encode())

    [success] = generate_samples(
        [source], method="smart", rows=30, delimiter=";"
    ).successes

    raw = success.result.output.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and b";" in raw and b"," not in raw
    with success.result.output.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream, delimiter=";"))
    assert rows[0] == ["region", "n"] and len(rows) == 31
    assert {row[0] for row in rows[1:]} == set(NORMAL)


def test_records_the_tolerant_policy_excludes_are_never_chosen(tmp_path):
    config = write_text(tmp_path, "config.json", json.dumps({"scan": {"errors": {"policy": "tolerant"}}}))
    rows = region_rows()
    rows.insert(5, "BROKEN,1,extra,field")
    source = _source(tmp_path, rows)

    [success] = generate_samples(
        [source], method="smart", rows=40, config_path=config
    ).successes

    chosen = _read(success.result.output)
    assert all(len(row) == 2 for row in chosen) and not any("BROKEN" in row for row in chosen)
    assert success.result.source_rows == 1310


def test_the_readings_are_reported_as_they_happen(tmp_path):
    source = _source(tmp_path)
    events = []

    generate_samples([source], method="smart", rows=30, on_progress=events.append)

    phases = [event.phase.value for event in events]
    assert "reading" in phases and phases[-1] == "complete"
    assert all(event.index == 1 and event.total == 1 for event in events)


def test_a_sample_whose_report_cannot_be_written_is_not_left_behind(tmp_path, monkeypatch):
    source = _source(tmp_path)

    def refuse(path, text):
        raise OSError("disk full")

    monkeypatch.setattr("tabalyst.smart_service.write_text_atomic", refuse)

    batch = generate_samples([source], method="smart", rows=30)

    assert batch.failures and not (tmp_path / "data.sample.csv").exists()
