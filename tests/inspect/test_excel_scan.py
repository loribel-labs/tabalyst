# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests of the Excel reader and its parcours (lot X-3): scan and
report of a workbook, the resolution layers and the cache of the detection.

Workbooks are synthetic, written with ``xlsxwriter``.
"""

import datetime as dt
import json
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


def workbook(directory: Path, name: str, build) -> Path:
    path = directory / name
    book = xlsxwriter.Workbook(str(path))
    build(book)
    book.close()
    return path


def sales(book, name="Sales", count=6, top=0):
    sheet = book.add_worksheet(name)
    date = book.add_format({"num_format": "yyyy-mm-dd"})
    for column, header in enumerate(["id", "customer", "amount", "paid", "when"]):
        sheet.write(top, column, header)
    for index in range(1, count + 1):
        sheet.write_number(top + index, 0, index)
        sheet.write_string(top + index, 1, f"Customer {index}")
        sheet.write_number(top + index, 2, index * 10.5)
        sheet.write_boolean(top + index, 3, index % 2 == 0)
        sheet.write_datetime(top + index, 4, dt.date(2026, 1, index), date)
    return sheet


def scan(path: Path, **settings) -> dict:
    from tabalyst.scanner import ScanConfig
    from tabalyst.scanner import scan as run

    config = ScanConfig.model_validate(settings)
    return run(path, config=config).model_dump(mode="json")


def one_sheet(book):
    sales(book)


def two_sheets(book):
    sales(book, "Sales", 6)
    sales(book, "Costs", 4)


def fields(result: dict) -> dict[str, dict]:
    return {item["display"]: item for item in result["datasets"][0]["fields"]}


# The reader ---------------------------------------------------------------


def test_a_sheet_is_read_as_a_table_with_typed_values(tmp_path):
    path = workbook(tmp_path, "one.xlsx", one_sheet)
    result = scan(path, excel={"dataset_path": "$.Sales"})
    assert result["source"]["format"] == "excel"
    assert result["source"]["excel"] == {
        "dataset_path": "$.Sales",
        "sheet": "Sales",
        "table": None,
        "range": "A1:E7",
        "header_row": 1,
        "header": ["id", "customer", "amount", "paid", "when"],
    }
    assert result["source"]["csv"] is None
    dataset = result["datasets"][0]
    assert (dataset["id"], dataset["kind"], dataset["record_count"]) == (
        "rows",
        "table",
        6,
    )
    found = fields(result)
    # Integers stay integers, decimals numbers, booleans booleans: no text.
    # Excel has one number type: an amount that happens to be whole (21.0) is
    # an integer next to the decimals of its column (decision X-6).
    assert set(found["id"]["native_types"]) == {"integer"}
    assert set(found["amount"]["native_types"]) == {"integer", "number"}
    assert set(found["paid"]["native_types"]) == {"boolean"}


def test_dates_are_read_as_text_that_the_date_detector_recognizes(tmp_path):
    path = workbook(tmp_path, "dates.xlsx", one_sheet)
    result = scan(path, excel={"dataset_path": "$.Sales"})
    when = fields(result)["when"]
    # The engine has no date type: the cell is ISO text, and a detector says
    # what it is. The report types the column ``date`` (see the parcours below).
    assert set(when["native_types"]) == {"string"}


def test_the_header_is_found_under_a_title(tmp_path):
    def build(book):
        sheet = sales(book, "Report", 4, top=3)
        sheet.write(0, 0, "Quarterly report")

    path = workbook(tmp_path, "title.xlsx", build)
    result = scan(path, excel={"dataset_path": "$.Report"})
    assert result["source"]["excel"]["header_row"] == 4
    assert result["datasets"][0]["record_count"] == 4


def test_the_header_row_can_be_forced(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Odd")
        sheet.write(0, 0, "x")
        sheet.write(0, 1, "y")
        sheet.write(1, 0, 1)
        sheet.write(1, 1, 2)
        sheet.write(2, 0, "id")
        sheet.write(2, 1, "name")
        sheet.write(3, 0, 7)
        sheet.write(3, 1, "z")

    path = workbook(tmp_path, "forced.xlsx", build)
    result = scan(path, excel={"dataset_path": "$.Odd", "header_row": 3})
    assert result["source"]["excel"]["header"] == ["id", "name"]
    assert result["datasets"][0]["record_count"] == 1


def test_a_named_table_is_read_from_its_definition(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Tables")
        sheet.write(0, 0, "a note")
        sheet.add_table(
            2,
            1,
            5,
            3,
            {
                "name": "Orders",
                "columns": [{"header": "a"}, {"header": "b"}, {"header": "c"}],
                "data": [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
            },
        )

    path = workbook(tmp_path, "table.xlsx", build)
    result = scan(path, excel={"dataset_path": "$.Tables.Orders"})
    assert result["source"]["excel"]["table"] == "Orders"
    assert result["source"]["excel"]["range"] == "B3:D6"
    assert result["datasets"][0]["record_count"] == 3


def test_blank_rows_are_not_records(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Gaps")
        sheet.write(0, 0, "k")
        sheet.write(0, 1, "v")
        for row in (1, 2, 5):
            sheet.write(row, 0, row)
            sheet.write(row, 1, "x")

    path = workbook(tmp_path, "gaps.xlsx", build)
    result = scan(path, excel={"dataset_path": "$.Gaps"})
    assert result["datasets"][0]["record_count"] == 3
    assert result["source"]["excel"]["range"] == "A1:B6"


def test_empty_cells_are_missing_values(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Holes")
        sheet.write(0, 0, "a")
        sheet.write(0, 1, "b")
        for row in range(1, 5):
            sheet.write(row, 0, row)
        sheet.write(1, 1, "x")
        sheet.write(2, 1, "y")

    path = workbook(tmp_path, "holes.xlsx", build)
    result = scan(path, excel={"dataset_path": "$.Holes"})
    assert fields(result)["b"]["presence"]["present"] == 4


def test_duplicate_headers_get_distinct_labels(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Dup")
        sheet.write(0, 0, "id")
        sheet.write(0, 1, "id")
        sheet.write(1, 0, 1)
        sheet.write(1, 1, 2)

    path = workbook(tmp_path, "dup.xlsx", build)
    result = scan(path, excel={"dataset_path": "$.Dup"})
    assert list(fields(result)) == ["id#1", "id#2"]


def test_a_workbook_without_a_table_path_says_how_to_choose(tmp_path):
    from tabalyst.errors import ConfigurationError
    from tabalyst.scanner import scan as run

    path = workbook(tmp_path, "none.xlsx", one_sheet)
    with pytest.raises(ConfigurationError, match="excel.dataset_path"):
        run(path)


def test_a_missing_sheet_lists_the_sheets(tmp_path):
    from tabalyst.errors import ConfigurationError

    path = workbook(tmp_path, "missing.xlsx", two_sheets)
    with pytest.raises(ConfigurationError, match="'Sales', 'Costs'"):
        scan(path, excel={"dataset_path": "$.Nope"})


def test_a_table_on_another_sheet_is_refused(tmp_path):
    from tabalyst.errors import ConfigurationError

    def build(book):
        sheet = book.add_worksheet("A")
        sheet.add_table(0, 0, 2, 1, {"name": "T", "data": [[1, 2], [3, 4]]})
        book.add_worksheet("B")

    path = workbook(tmp_path, "wrong.xlsx", build)
    with pytest.raises(ConfigurationError, match="not on 'B'"):
        scan(path, excel={"dataset_path": "$.B.T"})


def test_no_header_is_an_input_error_naming_the_way_out(tmp_path):
    from tabalyst.errors import InputError

    def build(book):
        sheet = book.add_worksheet("Numbers")
        for row in range(4):
            for column in range(3):
                sheet.write(row, column, row + column)

    path = workbook(tmp_path, "numbers.xlsx", build)
    with pytest.raises(InputError, match="excel.header_row"):
        scan(path, excel={"dataset_path": "$.Numbers"})


def test_a_header_row_that_is_empty_is_refused(tmp_path):
    from tabalyst.errors import ConfigurationError

    path = workbook(tmp_path, "empty_row.xlsx", one_sheet)
    with pytest.raises(ConfigurationError, match="excel.header_row"):
        scan(path, excel={"dataset_path": "$.Sales", "header_row": 30})


def test_the_identity_covers_every_byte_and_the_table(tmp_path):
    path = workbook(tmp_path, "id.xlsx", two_sheets)
    first = scan(path, excel={"dataset_path": "$.Sales"})
    again = scan(path, excel={"dataset_path": "$.Sales"})
    other = scan(path, excel={"dataset_path": "$.Costs"})
    assert first["source"]["sha256"] == again["source"]["sha256"]
    assert first["config_sha256"] == again["config_sha256"]
    assert other["config_sha256"] != first["config_sha256"]
    assert other["source"]["sha256"] == first["source"]["sha256"]


@pytest.mark.parametrize("value", ["$.a.b.c", "Sales", "$.a[]", 3])
def test_the_scan_setting_validates_the_path(value):
    from pydantic import ValidationError

    from tabalyst.errors import ConfigurationError  # noqa: F401
    from tabalyst.scanner import ScanConfig

    with pytest.raises(ValidationError):
        ScanConfig.model_validate({"excel": {"dataset_path": value}})


# Resolution ---------------------------------------------------------------


def invoke(*args):
    return runner.invoke(app, [str(arg) for arg in args])


def test_report_reads_a_simple_workbook_without_any_inspect(tmp_path):
    path = workbook(tmp_path, "simple.xlsx", one_sheet)
    result = invoke("report", path, "--no-progress")
    assert result.exit_code == 0, result.output
    profile = json.loads((tmp_path / "simple.report.json").read_text(encoding="utf-8"))
    assert profile["source"]["format"] == "excel"
    dataset = profile["datasets"][0]
    assert (dataset["summary"]["row_count"], dataset["summary"]["column_count"]) == (
        6,
        5,
    )
    types = {c["name"]: c["inferred_type"] for c in dataset["columns"]}
    assert types == {
        "id": "integer",
        "customer": "text",
        "amount": "number",
        "paid": "boolean",
        "when": "date",
    }
    assert (tmp_path / "simple.report.html").is_file()
    assert "Analyzed 6 rows and 5 columns." in result.output


def test_scan_of_a_simple_workbook_stores_the_detection_in_the_cache(
    tmp_path, storage
):
    path = workbook(tmp_path, "cached.xlsx", one_sheet)
    result = invoke("scan", path, "--no-progress")
    assert result.exit_code == 0, result.output
    cache = storage.shared_inspect_path(path)
    assert json.loads(cache.read_text(encoding="utf-8"))["inspect"]["kind"] == "excel"
    # No visible file is created by scan or report.
    assert not (tmp_path / "cached.xlsx-inspect.json").exists()


def test_an_ambiguous_workbook_stops_with_the_candidates_and_the_exits(tmp_path):
    path = workbook(tmp_path, "two.xlsx", two_sheets)
    result = invoke("report", path, "--no-progress")
    assert result.exit_code == 2
    assert "2 tables of two.xlsx are equally plausible" in result.output
    assert "$.Sales (6 rows)" in result.output
    assert "$.Costs (4 rows)" in result.output
    assert "--collection" in result.output
    assert not (tmp_path / "two.report.html").exists()


@pytest.mark.parametrize("value", ["Costs", "$.Costs", "$.Costs[]"])
def test_collection_chooses_the_table_in_every_spelling(tmp_path, value):
    path = workbook(tmp_path, "two.xlsx", two_sheets)
    result = invoke("scan", path, "--collection", value, "--no-progress")
    assert result.exit_code == 0, result.output
    assert "Scanned 4 records" in result.output


def test_two_collections_for_a_workbook_are_refused(tmp_path):
    path = workbook(tmp_path, "two.xlsx", two_sheets)
    result = invoke(
        "scan", path, "--collection", "Sales", "--collection", "Costs", "--no-progress"
    )
    assert result.exit_code == 2
    assert "one table at a time" in result.output


def test_the_visible_inspect_file_chooses_the_table(tmp_path):
    path = workbook(tmp_path, "two.xlsx", two_sheets)
    assert invoke("inspect", path).exit_code == 0
    visible = tmp_path / "two.xlsx-inspect.json"
    written = json.loads(visible.read_text(encoding="utf-8"))
    written["config"]["structure"]["dataset_path"] = "$.Costs"
    visible.write_text(json.dumps(written), encoding="utf-8")
    result = invoke("scan", path, "--no-progress")
    assert result.exit_code == 0, result.output
    assert "Scanned 4 records" in result.output


def test_the_visible_file_header_row_applies_to_the_scan(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Odd")
        sheet.write(0, 0, "x")
        sheet.write(0, 1, "y")
        sheet.write(1, 0, 1)
        sheet.write(1, 1, 2)
        sheet.write(2, 0, "id")
        sheet.write(2, 1, "name")
        sheet.write(3, 0, 7)
        sheet.write(3, 1, "z")

    path = workbook(tmp_path, "odd.xlsx", build)
    assert invoke("inspect", path).exit_code == 0
    visible = tmp_path / "odd.xlsx-inspect.json"
    written = json.loads(visible.read_text(encoding="utf-8"))
    written["config"]["structure"]["header_row"] = 3
    visible.write_text(json.dumps(written), encoding="utf-8")
    result = invoke("scan", path, "--no-progress", "-v")
    assert result.exit_code == 0, result.output
    assert "Scanned 1 record" in result.output


def test_command_line_overrides_the_visible_file_with_a_notice(tmp_path):
    path = workbook(tmp_path, "two.xlsx", two_sheets)
    invoke("inspect", path)
    visible = tmp_path / "two.xlsx-inspect.json"
    written = json.loads(visible.read_text(encoding="utf-8"))
    written["config"]["structure"]["dataset_path"] = "$.Costs"
    visible.write_text(json.dumps(written), encoding="utf-8")
    result = invoke("scan", path, "--collection", "Sales", "--no-progress")
    assert result.exit_code == 0, result.output
    assert "--collection overrides config.structure.dataset_path" in result.output
    assert "Scanned 6 records" in result.output


def test_a_config_file_names_the_table(tmp_path):
    path = workbook(tmp_path, "two.xlsx", two_sheets)
    config = tmp_path / "tabalyst.json"
    config.write_text(
        json.dumps({"scan": {"excel": {"dataset_path": "$.Costs"}}}), encoding="utf-8"
    )
    result = invoke("scan", path, "--config", config, "--no-progress")
    assert result.exit_code == 0, result.output
    assert "Scanned 4 records" in result.output


def test_the_json_collections_of_a_shared_config_do_not_reach_a_workbook(tmp_path):
    path = workbook(tmp_path, "one.xlsx", one_sheet)
    config = tmp_path / "tabalyst.json"
    config.write_text(
        json.dumps({"scan": {"json": {"collections": ["$.items[]"]}}}),
        encoding="utf-8",
    )
    result = invoke("scan", path, "--config", config, "--no-progress")
    assert result.exit_code == 0, result.output


def test_a_chosen_sheet_that_is_gone_stops_before_any_output(tmp_path):
    path = workbook(tmp_path, "gone.xlsx", one_sheet)
    invoke("inspect", path)
    visible = tmp_path / "gone.xlsx-inspect.json"
    written = json.loads(visible.read_text(encoding="utf-8"))
    written["config"]["structure"]["dataset_path"] = "$.Missing"
    visible.write_text(json.dumps(written), encoding="utf-8")
    result = invoke("report", path, "--no-progress")
    assert result.exit_code == 2
    assert "Missing" in result.output
    assert not (tmp_path / "gone.report.html").exists()


def test_a_workbook_that_changed_is_inspected_again(tmp_path, storage):
    path = workbook(tmp_path, "changing.xlsx", one_sheet)
    assert invoke("scan", path, "--no-progress").exit_code == 0
    first = json.loads(
        storage.shared_inspect_path(path).read_text(encoding="utf-8")
    )["source"]["sha256"]
    workbook(tmp_path, "changing.xlsx", lambda book: sales(book, "Sales", 9))
    result = invoke("scan", path, "--no-progress")
    assert result.exit_code == 0, result.output
    assert "Scanned 9 records" in result.output
    second = json.loads(
        storage.shared_inspect_path(path).read_text(encoding="utf-8")
    )["source"]["sha256"]
    assert first != second


def test_report_from_a_scan_document_of_a_workbook(tmp_path):
    path = workbook(tmp_path, "doc.xlsx", one_sheet)
    document = tmp_path / "doc.scan.json"
    assert invoke("scan", path, "-o", document, "--no-progress").exit_code == 0
    result = invoke("report", document, "--scan", "--no-progress")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "doc.report.html").is_file()


def test_the_scan_document_round_trips(tmp_path):
    from tabalyst.scanner.models import ScanResult

    path = workbook(tmp_path, "round.xlsx", one_sheet)
    result = scan(path, excel={"dataset_path": "$.Sales"})
    again = ScanResult.model_validate_json(json.dumps(result))
    assert again.source.header == ["id", "customer", "amount", "paid", "when"]


def test_the_visible_config_projects_onto_the_scan_layer():
    from tabalyst.inspector.models import ExcelInspectConfig

    config = ExcelInspectConfig.model_validate(
        {"structure": {"dataset_path": "$.Sales", "header_row": 3}}
    )
    assert config.to_scan_layer() == {
        "excel": {"dataset_path": "$.Sales", "header_row": 3}
    }
    assert ExcelInspectConfig.model_validate({}).to_scan_layer() == {}
    undecided = ExcelInspectConfig.model_validate(
        {"structure": {"dataset_path": None}}
    )
    assert undecided.to_scan_layer() == {}
