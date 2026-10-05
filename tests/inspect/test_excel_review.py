# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Regression tests of the review of the Excel lots: corrupt sheets, the seed of
``header_row``, lock files, the content that is hashed, and Inspect files of
another kind.
"""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

xlsxwriter = pytest.importorskip("xlsxwriter")

from tabalyst.cli import app
from tabalyst.projects.location import StorageLocation

pytestmark = pytest.mark.inspect_lot("X-3")

runner = CliRunner()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    return StorageLocation.local()


def workbook(directory: Path, name: str, rows: int = 5) -> Path:
    path = directory / name
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Data")
    for column, header in enumerate(["a", "b"]):
        sheet.write(0, column, header)
    for row in range(1, rows + 1):
        sheet.write(row, 0, row)
        sheet.write(row, 1, f"v{row}")
    book.close()
    return path


def with_title_rows(directory: Path, name: str) -> Path:
    path = directory / name
    book = xlsxwriter.Workbook(str(path))
    sheet = book.add_worksheet("Odd")
    for column, value in enumerate(["x", "y"]):
        sheet.write(0, column, value)
        sheet.write(1, column, column)
    for column, value in enumerate(["id", "name"]):
        sheet.write(2, column, value)
    sheet.write(3, 0, 7)
    sheet.write(3, 1, "z")
    book.close()
    return path


def _alt(tmp_path: Path) -> Path:
    """A folder beside the test files for a workbook that replaces another."""
    folder = tmp_path / "alt"
    folder.mkdir(exist_ok=True)
    return folder


def corrupt(source: Path, target: Path) -> Path:
    """A copy of a workbook whose first sheet XML is cut in half."""
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                data = data[: len(data) // 2]
            zout.writestr(item, data)
    return target


def invoke(*args):
    return runner.invoke(app, [str(arg) for arg in args])


# A corrupt sheet is an input error, not a crash ---------------------------------


def test_a_corrupt_sheet_is_an_input_error_for_inspect(tmp_path):
    from tabalyst.errors import InputError
    from tabalyst.inspector.excel_inspect import inspect_workbook

    bad = corrupt(workbook(tmp_path, "good.xlsx"), tmp_path / "bad.xlsx")
    with pytest.raises(InputError, match="bad.xlsx"):
        inspect_workbook(bad)


def test_a_corrupt_workbook_fails_alone_in_a_batch(tmp_path):
    good = workbook(tmp_path, "good.xlsx")
    corrupt(good, tmp_path / "bad.xlsx")
    result = invoke("inspect", tmp_path / "bad.xlsx", good, "--no-progress")
    assert result.exit_code == 4, result.output
    assert "Error [" in result.output and "bad.xlsx" in result.output
    assert (tmp_path / "good.xlsx-inspect.json").is_file()
    assert not (tmp_path / "bad.xlsx-inspect.json").exists()


def test_report_of_a_corrupt_workbook_exits_with_an_input_error(tmp_path):
    bad = corrupt(workbook(tmp_path, "good.xlsx"), tmp_path / "bad.xlsx")
    result = invoke("report", bad, "--no-progress")
    assert result.exit_code == 4, result.output
    assert not (tmp_path / "bad.report.html").exists()


# The seed of header_row ---------------------------------------------------------


def test_the_seed_keeps_the_header_row_of_a_config_file(tmp_path):
    path = with_title_rows(tmp_path, "odd.xlsx")
    config = tmp_path / "tabalyst.json"
    config.write_text(
        json.dumps({"scan": {"excel": {"header_row": 3}}}), encoding="utf-8"
    )
    assert invoke("inspect", path, "--config", config).exit_code == 0
    written = json.loads((tmp_path / "odd.xlsx-inspect.json").read_text("utf-8"))
    assert written["config"]["structure"]["header_row"] == 3
    # The visible file now carries the choice: no --config is needed to scan.
    result = invoke("scan", path, "--no-progress")
    assert result.exit_code == 0, result.output
    assert "Scanned 1 record" in result.output


def test_the_seed_without_a_config_file_leaves_the_header_row_to_the_detection(
    tmp_path,
):
    path = workbook(tmp_path, "plain.xlsx")
    assert invoke("inspect", path).exit_code == 0
    written = json.loads((tmp_path / "plain.xlsx-inspect.json").read_text("utf-8"))
    assert written["config"]["structure"]["header_row"] is None


# Lock files ---------------------------------------------------------------------


def test_a_pattern_skips_the_lock_files_of_excel(tmp_path, monkeypatch):
    workbook(tmp_path, "sales.xlsx")
    (tmp_path / "~$sales.xlsx").write_bytes(b"\x05Greg")
    monkeypatch.chdir(tmp_path)
    result = invoke("inspect", "*.xlsx", "--no-progress")
    assert result.exit_code == 0, result.output
    assert "~$" not in result.output
    assert (tmp_path / "sales.xlsx-inspect.json").is_file()
    assert not (tmp_path / "~$sales.xlsx-inspect.json").exists()


def test_a_pattern_that_only_matches_a_lock_file_matches_nothing(tmp_path, monkeypatch):
    (tmp_path / "~$only.xlsx").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    result = invoke("report", "*.xlsx", "--no-progress")
    assert result.exit_code == 4
    assert "matched no files" in result.output


def test_report_of_a_pattern_skips_lock_files_too(tmp_path, monkeypatch):
    workbook(tmp_path, "sales.xlsx")
    (tmp_path / "~$sales.xlsx").write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    result = invoke("report", "*.xlsx", "--no-progress")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "sales.report.html").is_file()


# What is hashed is what is parsed -------------------------------------------------


def test_the_hash_is_that_of_the_content_that_was_read(tmp_path, monkeypatch):
    from tabalyst.scanner import ScanConfig, scan
    from tabalyst.scanner.readers import excel_reader

    path = workbook(tmp_path, "moving.xlsx", rows=5)
    original = path.read_bytes()
    replacement = workbook(_alt(tmp_path), "other.xlsx", rows=9).read_bytes()
    real = excel_reader.read_workbook_bytes

    def read_then_save_again(*args, **kwargs):
        data = real(*args, **kwargs)
        # Excel saves the workbook after Tabalyst has read it.
        path.write_bytes(replacement)
        return data

    monkeypatch.setattr(excel_reader, "read_workbook_bytes", read_then_save_again)
    result = scan(path, config=ScanConfig(excel={"dataset_path": "$.Data"}))
    assert result.datasets[0].record_count == 5
    assert result.source.sha256 == hashlib.sha256(original).hexdigest()
    assert result.source.size_bytes == len(original)


def test_inspect_hashes_the_content_it_parses(tmp_path, monkeypatch):
    from tabalyst.inspector.excel_inspect import build, inspect_workbook

    path = workbook(tmp_path, "moving.xlsx", rows=5)
    original = path.read_bytes()
    replacement = workbook(_alt(tmp_path), "other2.xlsx", rows=9).read_bytes()
    real = build.read_workbook_bytes

    def read_then_save_again(*args, **kwargs):
        data = real(*args, **kwargs)
        path.write_bytes(replacement)
        return data

    monkeypatch.setattr(build, "read_workbook_bytes", read_then_save_again)
    document = inspect_workbook(path)
    assert document.source.sha256 == hashlib.sha256(original).hexdigest()
    assert document.detection.candidates[0].elements == 5


# Inspect files of another kind ----------------------------------------------------


def test_a_json_kind_inspect_file_beside_a_workbook_is_refused(tmp_path):
    path = workbook(tmp_path, "data.xlsx")
    json_source = tmp_path / "other.json"
    json_source.write_text(json.dumps({"rows": [{"a": 1}]}), encoding="utf-8")
    assert invoke("inspect", json_source).exit_code == 0
    (tmp_path / "data.xlsx-inspect.json").write_text(
        (tmp_path / "other.json-inspect.json").read_text("utf-8"), encoding="utf-8"
    )
    result = invoke("scan", path, "--no-progress")
    assert result.exit_code == 2, result.output
    assert "kind 'json'" in result.output and "tabalyst inspect --force" in result.output


def test_an_excel_kind_inspect_file_beside_a_json_source_is_refused(tmp_path):
    sheet = workbook(tmp_path, "data.xlsx")
    assert invoke("inspect", sheet).exit_code == 0
    source = tmp_path / "data.json"
    source.write_text(json.dumps({"rows": [{"a": 1}]}), encoding="utf-8")
    (tmp_path / "data.json-inspect.json").write_text(
        (tmp_path / "data.xlsx-inspect.json").read_text("utf-8"), encoding="utf-8"
    )
    result = invoke("report", source, "--no-progress")
    assert result.exit_code == 2, result.output
    assert "kind 'excel'" in result.output
    assert not (tmp_path / "data.report.html").exists()


def test_report_from_a_scan_explains_a_file_of_another_kind(tmp_path):
    from tabalyst.inspector.resolution import inspect_notice
    from tabalyst.scanner import ScanConfig, scan

    path = workbook(tmp_path, "data.xlsx")
    result = scan(path, config=ScanConfig(excel={"dataset_path": "$.Data"}))
    json_source = tmp_path / "other.json"
    json_source.write_text(json.dumps({"rows": [{"a": 1}]}), encoding="utf-8")
    assert invoke("inspect", json_source).exit_code == 0
    (tmp_path / "data.xlsx-inspect.json").write_text(
        (tmp_path / "other.json-inspect.json").read_text("utf-8"), encoding="utf-8"
    )
    notice = inspect_notice(path, result)
    assert notice is not None and "kind 'json'" in notice
