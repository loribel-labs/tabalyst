# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Choosing a collection from the command line: the commands to copy when a
source is ambiguous, and ``tabalyst report --all-collections``."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.inspector.choices import (
    choice_lines,
    collection_argument,
    collection_slug,
    expand_collection,
)
from tabalyst.projects.location import StorageLocation

runner = CliRunner()


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    return StorageLocation.local()


def invoke(*args):
    return runner.invoke(app, [str(arg) for arg in args])


def write_json(directory: Path, name: str, data: object) -> Path:
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def records(count: int) -> list[dict]:
    return [{"id": index, "label": f"item {index}"} for index in range(1, count + 1)]


def workbook(directory: Path, name: str, sheets: dict, hidden: tuple[str, ...] = ()):
    xlsxwriter = pytest.importorskip("xlsxwriter")
    path = directory / name
    book = xlsxwriter.Workbook(str(path))
    for title, count in sheets.items():
        sheet = book.add_worksheet(title)
        if count:
            sheet.write_row(0, 0, ["id", "label", "amount"])
            for index in range(1, count + 1):
                sheet.write_row(index, 0, [index, f"item {index}", index * 1.5])
        if title in hidden:
            sheet.hide()
    book.close()
    return path


# The value of --collection --------------------------------------------------


@pytest.mark.parametrize(
    ("path", "argument"),
    [
        ("$.Costs", "Costs"),
        ("$.Sales.Orders", "Sales.Orders"),
        ("$.data.items[]", "data.items"),
        ("$[]", "."),
        ('$["2024"]', "2024"),
        ('$["Sales Q1"]', "'$[\"Sales Q1\"]'"),
        ('$["a.b"]', "'$[\"a.b\"]'"),
    ],
)
def test_the_shortest_value_that_names_a_collection(path, argument):
    assert collection_argument(path) == argument


@pytest.mark.parametrize("path", ["$.Costs", "$.Sales.Orders", "$.data.items[]", "$[]"])
def test_a_short_value_expands_back_to_its_path(path):
    short = collection_argument(path)
    assert expand_collection(short).removesuffix("[]") == path.removesuffix("[]")


@pytest.mark.parametrize(
    ("path", "slug"),
    [
        ('$["Sales Q1"]', "sales-q1"),
        ("$.Sales.Orders", "sales-orders"),
        ("$.data.items[]", "data-items"),
        ('$["Café 2026!"]', "cafe-2026"),
        ("$[]", "root"),
    ],
)
def test_the_slug_of_a_collection_is_a_clean_file_name_part(path, slug):
    assert collection_slug(path, 1) == slug


def test_a_name_with_nothing_to_keep_is_named_by_its_position():
    assert collection_slug('$["日本"]', 3) == "collection-3"


def test_choice_lines_quote_a_source_with_spaces():
    lines = choice_lines("report", "my shop.xlsx", ["$.Costs"], noun="table")
    assert lines == [
        "Choose the table to analyze:",
        '  tabalyst report "my shop.xlsx" --collection Costs',
        'Or report every table: tabalyst report "my shop.xlsx" --all-collections',
    ]


# The commands to copy -------------------------------------------------------


def test_an_ambiguous_workbook_offers_the_commands_to_copy(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales Q1": 5, "Notes": 0})

    result = invoke("report", path, "--no-progress")

    assert result.exit_code == 2
    assert "Choose the table to analyze:" in result.output
    assert f"tabalyst report {path} --collection Costs" in result.output
    assert f"""tabalyst report {path} --collection '$["Sales Q1"]'""" in result.output
    assert f"tabalyst report {path} --all-collections" in result.output
    assert "Notes" not in result.output.split("Choose the table")[1]


def test_scan_offers_scan_commands(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales": 5})

    result = invoke("scan", path, "--no-progress")

    assert result.exit_code == 2
    assert f"tabalyst scan {path} --collection Costs" in result.output
    assert "--all-collections" not in result.output


def test_an_ambiguous_json_file_offers_the_commands_to_copy(tmp_path):
    path = write_json(tmp_path, "shop.json", {"a": records(3), "b": records(3)})

    result = invoke("report", path, "--no-progress")

    assert result.exit_code == 2
    assert "Choose the collection to analyze:" in result.output
    assert f"tabalyst report {path} --collection a" in result.output
    assert f"tabalyst report {path} --collection b" in result.output


def test_a_workbook_with_a_dominant_table_needs_no_choice(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Orders": 30, "Regions": 2})

    result = invoke("report", path, "--no-progress")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "shop.report.html").is_file()
    assert (tmp_path / "shop.report.json").is_file()


def test_the_short_command_runs(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales": 5})

    result = invoke("report", path, "--collection", "Costs", "--no-progress")

    assert result.exit_code == 0, result.output
    assert "Analyzed 4 rows and 3 columns." in result.output


# --all-collections ----------------------------------------------------------


def test_every_table_of_a_workbook_gets_its_own_report(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales Q1": 5, "Notes": 0})

    result = invoke("report", path, "--all-collections", "--no-progress")

    assert result.exit_code == 0, result.output
    assert "2 succeeded, 0 failed" in result.output
    produced = [*tmp_path.glob("*.html"), *tmp_path.glob("*.json")]
    assert sorted(item.name for item in produced) == [
        "executions.json",
        "shop.costs.html",
        "shop.costs.json",
        "shop.sales-q1.html",
        "shop.sales-q1.json",
    ]
    costs = json.loads((tmp_path / "shop.costs.json").read_text(encoding="utf-8"))
    assert costs["datasets"][0]["summary"]["row_count"] == 4
    sales = json.loads((tmp_path / "shop.sales-q1.json").read_text(encoding="utf-8"))
    assert sales["datasets"][0]["summary"]["row_count"] == 5


def test_the_output_directory_is_optional_for_one_file_and_honored(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales": 5})

    result = invoke("report", path, "--all-collections", "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "out" / "shop.costs.html").is_file()
    assert (tmp_path / "out" / "shop.sales.json").is_file()
    assert not (tmp_path / "shop.costs.html").exists()


def test_one_table_keeps_the_collection_name(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Orders": 30, "Regions": 2})

    result = invoke("report", path, "--all-collections", "--no-progress")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "shop.orders.html").is_file()
    assert (tmp_path / "shop.regions.html").is_file()


def test_several_inputs_need_an_output_directory(tmp_path):
    first = workbook(tmp_path, "a.xlsx", {"One": 3})
    second = workbook(tmp_path, "b.xlsx", {"Two": 3})

    refused = invoke("report", first, second, "--all-collections")
    accepted = invoke("report", first, second, "--all-collections", "-d", tmp_path / "out")

    assert refused.exit_code == 2
    assert "--output-dir" in refused.output
    assert not (tmp_path / "a.one.html").exists()
    assert accepted.exit_code == 0, accepted.output
    assert (tmp_path / "out" / "a.one.html").is_file()
    assert (tmp_path / "out" / "b.two.html").is_file()


def test_equal_slugs_get_a_number(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Sales Q1": 4, "sales-q1": 5})

    result = invoke("report", path, "--all-collections", "--no-progress")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "shop.sales-q1.html").is_file()
    assert (tmp_path / "shop.sales-q1-2.html").is_file()


def test_hidden_sheets_are_left_out_with_a_warning(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Secret": 5}, hidden=("Secret",))

    result = invoke("report", path, "--all-collections", "--no-progress")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "shop.costs.html").is_file()
    assert not (tmp_path / "shop.secret.html").exists()
    assert "hidden sheet $.Secret is not reported" in result.output


def test_a_workbook_with_nothing_to_report_fails_alone(tmp_path):
    empty = workbook(tmp_path, "empty.xlsx", {"Notes": 0})
    good = workbook(tmp_path, "good.xlsx", {"Costs": 4, "Sales": 5})

    result = invoke("report", empty, good, "--all-collections", "-d", tmp_path / "out")

    assert result.exit_code == 2
    assert "nothing to report" in result.output
    assert "2 succeeded, 1 failed" in result.output
    assert (tmp_path / "out" / "good.costs.html").is_file()


def test_every_array_of_a_json_file_gets_its_own_report(tmp_path):
    path = write_json(tmp_path, "shop.json", {"a": records(3), "b": records(2)})

    result = invoke("report", path, "--all-collections", "--no-progress")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "shop.a.html").is_file()
    assert (tmp_path / "shop.b.json").is_file()


def test_sources_without_collections_keep_their_usual_report(tmp_path):
    table = tmp_path / "table.csv"
    table.write_text("id,label\n1,a\n2,b\n", encoding="utf-8")
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales": 5})

    result = invoke("report", table, path, "--all-collections", "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "out" / "table.html").is_file()
    assert (tmp_path / "out" / "shop.costs.html").is_file()


def test_existing_reports_need_force(tmp_path):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales": 5})
    assert invoke("report", path, "--all-collections").exit_code == 0

    again = invoke("report", path, "--all-collections")
    forced = invoke("report", path, "--all-collections", "--force")

    assert again.exit_code != 0
    assert "--force" in again.output
    assert forced.exit_code == 0, forced.output


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["-o", "x.html"], "--output cannot be used with --all-collections"),
        (["--collection", "Costs"], "cannot be used together"),
        (["--scan"], "cannot be used with --scan"),
    ],
)
def test_incompatible_options_are_refused(tmp_path, extra, message):
    path = workbook(tmp_path, "shop.xlsx", {"Costs": 4, "Sales": 5})

    result = invoke("report", path, "--all-collections", *extra)

    assert result.exit_code == 2
    assert message in result.output
    assert not list(tmp_path.glob("*.html"))
