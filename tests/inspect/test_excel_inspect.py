"""Contract tests of Excel Inspect (lot X-2): ``docs/dev/inspect/excel.md``.

Workbooks are synthetic and written with ``xlsxwriter``; the header rule and
the dominance ratio are provisional until they are measured on real ones.
"""

import json
from pathlib import Path

import pytest

xlsxwriter = pytest.importorskip("xlsxwriter")

pytestmark = pytest.mark.inspect_lot("X-2")


def workbook(directory: Path, name: str, build) -> Path:
    path = directory / name
    book = xlsxwriter.Workbook(str(path))
    build(book)
    book.close()
    return path


def table(sheet, header, rows, *, top=0, left=0):
    for column, name in enumerate(header):
        sheet.write(top, left + column, name)
    for index, row in enumerate(rows, start=1):
        for column, value in enumerate(row):
            sheet.write(top + index, left + column, value)


def rows_of(count, width=3):
    return [[f"v{r}c{c}" for c in range(width)] for r in range(count)]


def inspect_document(path: Path) -> dict:
    from tabalyst.inspector.excel_inspect import inspect_workbook

    return inspect_workbook(path).model_dump(mode="json")


def candidates(document: dict) -> dict[str, dict]:
    return {item["path"]: item for item in document["detection"]["candidates"]}


def codes(document: dict) -> list[str]:
    return [item["code"] for item in document["warnings"]]


def selection(document: dict) -> dict:
    return document["detection"]["selection"]


def one_sheet(book, name="Data", count=5):
    sheet = book.add_worksheet(name)
    table(sheet, ["a", "b", "c"], rows_of(count))
    return sheet


# A. Workbook level --------------------------------------------------------


def test_one_sheet_one_table_is_selected_automatically(tmp_path):
    path = workbook(tmp_path, "one.xlsx", one_sheet)
    document = inspect_document(path)
    assert selection(document) == {
        "path": "$.Data",
        "basis": "only_eligible_candidate",
    }
    assert document["config"] == {
        "structure": {"dataset_path": "$.Data", "header_row": None}
    }
    assert document["inspect"]["kind"] == "excel"
    assert document["source"]["format"] == "excel"
    candidate = candidates(document)["$.Data"]
    assert candidate["range"] == "A1:C6"
    assert candidate["header_row"] == 1
    assert candidate["elements"] == 5
    assert candidate["observation"]["column_names"] == ["a", "b", "c"]


def test_xlsm_is_read_like_xlsx(tmp_path):
    path = tmp_path / "macro.xlsm"
    book = xlsxwriter.Workbook(str(path))
    one_sheet(book)
    book.close()
    assert selection(inspect_document(path))["path"] == "$.Data"


def test_other_sheets_are_listed_and_the_eligible_one_selected(tmp_path):
    def build(book):
        one_sheet(book, "Data")
        book.add_worksheet("Empty")
        notes = book.add_worksheet("Notes")
        notes.write(0, 0, "just one line")
        book.add_chartsheet("Chart")

    document = inspect_document(workbook(tmp_path, "many.xlsx", build))
    assert selection(document)["path"] == "$.Data"
    found = candidates(document)
    assert found["$.Empty"]["ineligible_reason"] == "no_cells"
    assert found["$.Chart"]["ineligible_reason"] == "no_cells"
    assert found["$.Notes"]["ineligible_reason"] == "no_header"
    assert codes(document).count("candidate_not_eligible") == 3


def test_several_eligible_sheets_are_ambiguous(tmp_path):
    def build(book):
        one_sheet(book, "Sales", 8)
        one_sheet(book, "Costs", 5)

    document = inspect_document(workbook(tmp_path, "two.xlsx", build))
    assert selection(document) == {"path": None, "basis": "ambiguous"}
    assert document["config"]["structure"]["dataset_path"] is None
    assert "ambiguous_collections" in codes(document)


def test_a_dominant_sheet_is_selected_over_the_next(tmp_path):
    from tabalyst.inspector.excel_inspect import parameters

    small = 3
    big = small * parameters.DOMINANCE_RATIO

    def build(book):
        one_sheet(book, "Big", big)
        one_sheet(book, "Small", small)

    document = inspect_document(workbook(tmp_path, "dominant.xlsx", build))
    assert selection(document) == {
        "path": "$.Big",
        "basis": "dominant_candidate",
        "over": "$.Small",
    }


def test_just_under_the_ratio_stays_ambiguous(tmp_path):
    from tabalyst.inspector.excel_inspect import parameters

    small = 3
    big = small * parameters.DOMINANCE_RATIO - 1

    def build(book):
        one_sheet(book, "Big", big)
        one_sheet(book, "Small", small)

    document = inspect_document(workbook(tmp_path, "under.xlsx", build))
    assert selection(document)["basis"] == "ambiguous"


def test_named_tables_stand_for_their_sheet(tmp_path):
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

    document = inspect_document(workbook(tmp_path, "tables.xlsx", build))
    found = candidates(document)
    assert found["$.Tables"]["ineligible_reason"] == "has_tables"
    orders = found["$.Tables.Orders"]
    assert orders["kind"] == "table"
    assert (orders["sheet"], orders["table"]) == ("Tables", "Orders")
    assert (orders["range"], orders["header_row"], orders["elements"]) == (
        "B3:D6",
        3,
        3,
    )
    assert selection(document)["path"] == "$.Tables.Orders"
    assert document["detection"]["workbook"] == {"sheets": 1, "tables": 1}


def test_a_hidden_sheet_never_competes_with_a_visible_one(tmp_path):
    def build(book):
        one_sheet(book, "Visible", 3)
        one_sheet(book, "Secret", 5).hide()

    document = inspect_document(workbook(tmp_path, "hidden.xlsx", build))
    assert selection(document)["path"] == "$.Visible"
    assert candidates(document)["$.Secret"]["visible"] is False


def test_a_hidden_sheet_is_selected_when_it_is_the_only_table(tmp_path):
    def build(book):
        one_sheet(book, "Secret", 5).hide()
        book.add_worksheet("Shown").activate()

    document = inspect_document(workbook(tmp_path, "only_hidden.xlsx", build))
    assert selection(document)["path"] == "$.Secret"


def test_no_table_at_all_is_no_collection(tmp_path):
    def build(book):
        book.add_worksheet("Empty")

    document = inspect_document(workbook(tmp_path, "none.xlsx", build))
    assert selection(document) == {"path": None, "basis": "no_eligible_candidate"}
    assert "no_collection" in codes(document)
    assert document["config"]["structure"]["dataset_path"] is None


def test_a_header_row_alone_is_not_a_table(tmp_path):
    def build(book):
        table(book.add_worksheet("Headers"), ["a", "b"], [])

    document = inspect_document(workbook(tmp_path, "headers.xlsx", build))
    found = candidates(document)["$.Headers"]
    # A header is recognized by the data row that follows it.
    assert found["ineligible_reason"] == "no_header"
    assert selection(document)["basis"] == "no_eligible_candidate"


def test_many_candidates_are_cut_and_nothing_is_selected(tmp_path, monkeypatch):
    from tabalyst.inspector.excel_inspect import parameters

    monkeypatch.setattr(parameters, "MAX_CANDIDATES", 2)

    def build(book):
        for name in "ABC":
            one_sheet(book, name, 3)

    document = inspect_document(workbook(tmp_path, "cut.xlsx", build))
    assert len(document["detection"]["candidates"]) == 2
    assert document["detection"]["scope"]["candidates"] == "truncated"
    assert selection(document) == {"path": None, "basis": "candidates_truncated"}
    assert "candidates_truncated" in codes(document)


def test_sheet_names_that_are_not_identifiers_are_quoted(tmp_path):
    def build(book):
        one_sheet(book, "Q1 2026")

    document = inspect_document(workbook(tmp_path, "names.xlsx", build))
    assert selection(document)["path"] == '$["Q1 2026"]'


# B. Table inside a sheet ----------------------------------------------------


def test_header_is_found_under_a_title_and_blank_rows(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Report")
        sheet.write(0, 0, "Quarterly report")
        table(sheet, ["id", "name", "total"], rows_of(4), top=3)

    document = inspect_document(workbook(tmp_path, "title.xlsx", build))
    found = candidates(document)["$.Report"]
    assert found["header_row"] == 4
    assert found["range"] == "A4:C8"
    assert found["elements"] == 4


def test_a_table_that_does_not_start_in_a_is_ranged_from_its_header(tmp_path):
    def build(book):
        table(book.add_worksheet("Offset"), ["a", "b"], rows_of(3, 2), top=4, left=2)

    document = inspect_document(workbook(tmp_path, "offset.xlsx", build))
    found = candidates(document)["$.Offset"]
    assert (found["range"], found["header_row"]) == ("C5:D8", 5)


def test_duplicate_and_blank_headers_are_reported_not_renamed(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Dup")
        for column, name in enumerate(["id", "id", "", "x"]):
            if name:
                sheet.write(0, column, name)
        for row in range(1, 4):
            for column in range(4):
                sheet.write(row, column, row)

    document = inspect_document(workbook(tmp_path, "dup.xlsx", build))
    found = candidates(document)["$.Dup"]
    assert found["observation"]["column_names"] == ["id", "id", "", "x"]
    assert {"duplicate_headers", "blank_headers"} <= set(codes(document))


def test_blank_rows_among_the_data_warn_and_are_not_counted(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Blocks")
        table(sheet, ["k", "v"], [[1, 2], [3, 4]])
        sheet.write(5, 0, "k2")
        sheet.write(5, 1, "v2")
        sheet.write(6, 0, 5)

    document = inspect_document(workbook(tmp_path, "blocks.xlsx", build))
    found = candidates(document)["$.Blocks"]
    assert found["elements"] == 4
    assert found["observation"]["blank_rows"] == 2
    assert "blocks_not_split" in codes(document)


def test_merged_cells_in_the_data_and_in_the_header_warn(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Merged")
        table(sheet, ["a", "b", "c"], rows_of(4))
        sheet.merge_range(2, 0, 3, 0, "tall")
        sheet.merge_range(0, 1, 0, 2, "group")

    document = inspect_document(workbook(tmp_path, "merged.xlsx", build))
    found = candidates(document)
    assert found["$.Merged"]["observation"]["merged_ranges"] == 2
    assert {"merged_cells", "multi_level_header"} <= set(codes(document))


def test_a_merged_title_above_the_table_is_not_a_warning(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Titled")
        sheet.merge_range(0, 0, 0, 2, "Big title")
        table(sheet, ["a", "b", "c"], rows_of(3), top=2)

    document = inspect_document(workbook(tmp_path, "titled.xlsx", build))
    assert candidates(document)["$.Titled"]["observation"]["merged_ranges"] == 0
    assert "merged_cells" not in codes(document)
    assert "multi_level_header" not in codes(document)


def test_a_one_column_sheet_is_a_table(tmp_path):
    def build(book):
        table(book.add_worksheet("Single"), ["only"], [["x"], ["y"]])

    document = inspect_document(workbook(tmp_path, "single.xlsx", build))
    assert candidates(document)["$.Single"]["elements"] == 2


def test_numbers_only_is_not_a_header(tmp_path):
    def build(book):
        sheet = book.add_worksheet("Numbers")
        for row in range(5):
            for column in range(3):
                sheet.write(row, column, row * 3 + column)

    document = inspect_document(workbook(tmp_path, "numbers.xlsx", build))
    assert candidates(document)["$.Numbers"]["ineligible_reason"] == "no_header"


# Errors ---------------------------------------------------------------------


def test_a_file_that_is_not_a_workbook_is_an_input_error(tmp_path):
    from tabalyst.errors import InputError

    path = tmp_path / "fake.xlsx"
    path.write_text("not a workbook", encoding="utf-8")
    with pytest.raises(InputError, match="fake.xlsx"):
        inspect_document(path)


def test_a_password_protected_workbook_is_an_input_error(tmp_path, monkeypatch):
    import python_calamine

    from tabalyst.errors import InputError
    from tabalyst.scanner.readers import excel_common

    path = workbook(tmp_path, "locked.xlsx", one_sheet)

    def refuse(*args, **kwargs):
        raise python_calamine.PasswordError

    monkeypatch.setattr(excel_common, "load_workbook", refuse)
    with pytest.raises(InputError, match="password protected"):
        inspect_document(path)


def test_a_sheet_too_large_to_read_is_refused(tmp_path, monkeypatch):
    from tabalyst.errors import InputError
    from tabalyst.scanner.readers import excel_common

    path = workbook(tmp_path, "big.xlsx", one_sheet)
    monkeypatch.setattr(excel_common, "MAX_SHEET_XML_BYTES", 10)
    with pytest.raises(InputError, match="too large"):
        inspect_document(path)


def test_an_old_spreadsheet_format_is_refused_with_a_way_out(tmp_path):
    from tabalyst.errors import ConfigurationError
    from tabalyst.inspect_service import build_inspect_plan

    path = tmp_path / "old.xls"
    path.write_bytes(b"x")
    with pytest.raises(ConfigurationError, match=r"\.xls .*not read yet"):
        build_inspect_plan([path])


def test_the_document_is_stable_between_two_inspections(tmp_path):
    path = workbook(tmp_path, "stable.xlsx", one_sheet)
    first, second = inspect_document(path), inspect_document(path)
    first["inspect"].pop("generated_at")
    second["inspect"].pop("generated_at")
    assert first == second


# Configuration and document ---------------------------------------------------


@pytest.mark.parametrize("value", ["$[]", "$.a.b.c", "Sales", "$.a[]", 3, "$"])
def test_dataset_path_must_name_a_sheet_or_a_table(value):
    from pydantic import ValidationError

    from tabalyst.inspector.models import ExcelInspectConfig

    with pytest.raises(ValidationError):
        ExcelInspectConfig.model_validate({"structure": {"dataset_path": value}})


def test_dataset_path_is_canonicalized():
    from tabalyst.inspector.models import ExcelInspectConfig

    config = ExcelInspectConfig.model_validate(
        {"structure": {"dataset_path": '$["Sales"]["Orders"]'}}
    )
    assert config.structure.dataset_path == "$.Sales.Orders"


@pytest.mark.parametrize("value", [0, -1, "3", True, 1.5])
def test_header_row_is_a_positive_integer(value):
    from pydantic import ValidationError

    from tabalyst.inspector.models import ExcelInspectConfig

    with pytest.raises(ValidationError):
        ExcelInspectConfig.model_validate({"structure": {"header_row": value}})


def test_a_key_of_another_kind_is_refused_in_the_config():
    from pydantic import ValidationError

    from tabalyst.inspector.models import ExcelInspectConfig

    with pytest.raises(ValidationError):
        ExcelInspectConfig.model_validate({"flatten": {"enabled": True}})


def test_the_document_round_trips_through_json(tmp_path):
    from tabalyst.inspector.excel_inspect import inspect_workbook
    from tabalyst.inspector.models import ExcelDetection, InspectDocument

    path = workbook(tmp_path, "round.xlsx", one_sheet)
    document = inspect_workbook(path)
    again = InspectDocument.model_validate_json(document.model_dump_json())
    assert again == document
    assert isinstance(again.detection, ExcelDetection)


def test_a_document_whose_sections_belong_to_another_kind_is_refused(tmp_path):
    from pydantic import ValidationError

    from tabalyst.inspector.excel_inspect import inspect_workbook
    from tabalyst.inspector.models import InspectDocument

    path = workbook(tmp_path, "mixed.xlsx", one_sheet)
    data = inspect_workbook(path).model_dump(mode="json")
    data["inspect"]["kind"] = "json"
    with pytest.raises(ValidationError):
        InspectDocument.model_validate(data)


# Visible file and command ---------------------------------------------------


def test_the_service_writes_the_visible_file_beside_the_workbook(tmp_path):
    from tabalyst import inspect

    path = workbook(tmp_path, "visible.xlsx", one_sheet)
    result = inspect(path)
    assert result.path == tmp_path / "visible.xlsx-inspect.json"
    written = json.loads(result.path.read_text(encoding="utf-8"))
    assert written["inspect"]["kind"] == "excel"
    assert written["config"]["structure"]["dataset_path"] == "$.Data"


def test_reinspecting_keeps_the_config_the_user_chose(tmp_path):
    from tabalyst import inspect

    def build(book):
        one_sheet(book, "Sales", 8)
        one_sheet(book, "Costs", 5)

    path = workbook(tmp_path, "keep.xlsx", build)
    first = inspect(path)
    written = json.loads(first.path.read_text(encoding="utf-8"))
    written["config"]["structure"] = {"dataset_path": "$.Costs", "header_row": 2}
    first.path.write_text(json.dumps(written), encoding="utf-8")
    second = inspect(path)
    kept = json.loads(second.path.read_text(encoding="utf-8"))["config"]
    assert kept["structure"] == {"dataset_path": "$.Costs", "header_row": 2}
    assert "configured_path_not_found" not in codes(
        second.document.model_dump(mode="json")
    )


def test_a_configured_sheet_that_is_gone_warns(tmp_path):
    from tabalyst import inspect

    path = workbook(tmp_path, "gone.xlsx", one_sheet)
    first = inspect(path)
    written = json.loads(first.path.read_text(encoding="utf-8"))
    written["config"]["structure"]["dataset_path"] = "$.Missing"
    first.path.write_text(json.dumps(written), encoding="utf-8")
    document = inspect(path).document.model_dump(mode="json")
    assert "configured_path_not_found" in codes(document)


def test_a_config_of_another_kind_in_the_visible_file_is_refused(tmp_path):
    from tabalyst import inspect
    from tabalyst.errors import ConfigurationError

    path = workbook(tmp_path, "bad.xlsx", one_sheet)
    result = inspect(path)
    written = json.loads(result.path.read_text(encoding="utf-8"))
    written["config"]["flatten"] = {"enabled": True}
    result.path.write_text(json.dumps(written), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="flatten"):
        inspect(path)


def test_an_inspect_file_of_another_kind_is_not_replaced_silently(tmp_path):
    from tabalyst import inspect
    from tabalyst.errors import ConfigurationError

    path = workbook(tmp_path, "kind.xlsx", one_sheet)
    json_file = tmp_path / "data.json"
    json_file.write_text(json.dumps({"rows": [{"a": 1}]}), encoding="utf-8")
    foreign = inspect(json_file)
    target = tmp_path / "kind.xlsx-inspect.json"
    target.write_text(foreign.path.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="kind"):
        inspect(path)
    replaced = inspect(path, force=True)
    assert replaced.document.inspect.kind == "excel"


def test_the_command_lists_the_choices_of_an_ambiguous_workbook(tmp_path):
    from typer.testing import CliRunner

    from tabalyst.cli import app

    def build(book):
        one_sheet(book, "Sales", 8)
        one_sheet(book, "Costs", 5)

    path = workbook(tmp_path, "cli.xlsx", build)
    result = CliRunner().invoke(app, ["inspect", str(path), "--verbose"])
    assert result.exit_code == 0, result.output
    output = result.output
    assert "Selection: none" in output
    assert "$.Sales (8 elements)" in output
    assert "--collection '$.Costs'" in output
    assert (tmp_path / "cli.xlsx-inspect.json").is_file()
