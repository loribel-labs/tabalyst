# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check the Generate anomaly engine: transformations, row copies, classes and counts."""

from __future__ import annotations

import csv
import json
import shutil
from importlib.resources import files
from pathlib import Path
from typing import Any, cast

import pytest
from generate_package_fixture import write_columns_package

from tabalyst.errors import ConfigurationError
from tabalyst.generate_anomalies import CHANGE_FIELDS, inject_anomalies
from tabalyst.generate_service import build_generate_plan, generate_datasets

COMPUTER = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))


def _inject(tmp_path: Path, rows: list[dict[str, str]], operations: list[dict[str, object]],
            ) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, object]]:
    clean = tmp_path / "clean.csv"
    with clean.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    summary = inject_anomalies(
        clean, tmp_path / "altered.csv", tmp_path / "changes.csv", dataset="demo",
        profile={"id": "p", "operations": operations}, seed=7, count=len(rows), delimiter=",")
    with (tmp_path / "altered.csv").open(encoding="utf-8", newline="") as stream:
        altered = list(csv.DictReader(stream))
    with (tmp_path / "changes.csv").open(encoding="utf-8", newline="") as stream:
        changes = list(csv.DictReader(stream))
    return altered, changes, summary


def _each_row(values: list[str]) -> list[dict[str, str]]:
    return [{"id": f"R{i:03d}", "v": value} for i, value in enumerate(values)]


@pytest.mark.parametrize(("transform", "value", "expected"), [
    ("double_space", "Jean Paul", "Jean  Paul"),
    ("double_hyphen", "AG-PR-001", "AG--PR-001"),
    ("suffix_x", "Auto", "Auto_X"),
    ("strip_accents", "Québec Été", "Quebec Ete"),
    ("negate", "125.50", "-125.50"),
    ("leading_apostrophe", "Dupont", "'Dupont"),
])
def test_text_transformation_changes_the_cell_as_documented(
        tmp_path: Path, transform: str, value: str, expected: str) -> None:
    altered, changes, summary = _inject(
        tmp_path, _each_row([value] * 5),
        [{"kind": "format", "column": "v", "value": transform, "count": 5}])
    assert [row["v"] for row in altered] == [expected] * 5
    assert [(c["before"], c["after"]) for c in changes] == [(value, expected)] * 5
    assert summary["changed_cells"] == 5


@pytest.mark.parametrize(("transform", "value"), [
    ("double_space", "Jean"),
    ("double_hyphen", "AG_PR"),
    ("suffix_x", ""),
    ("strip_accents", "Quebec"),
    ("negate", "0.00"),
    ("negate", "-5"),
    ("negate", "abc"),
    ("leading_apostrophe", ""),
    ("insert_space", "a"),
    ("insert_space", "a b"),
    ("drop_char", "A"),
])
def test_ineligible_cell_is_counted_as_skipped_and_left_unchanged(
        tmp_path: Path, transform: str, value: str) -> None:
    altered, changes, summary = _inject(
        tmp_path, _each_row([value] * 4),
        [{"kind": "format", "column": "v", "value": transform, "count": 4}])
    assert [row["v"] for row in altered] == [value] * 4
    assert changes == []
    entry = summary["operations"][0]  # type: ignore[index]
    assert (entry["requested_rows"], entry["applied_rows"], entry["skipped_rows"]) == (4, 0, 4)


def test_insert_space_splits_a_word_without_touching_its_letters(tmp_path: Path) -> None:
    altered, _, _ = _inject(
        tmp_path, _each_row(["Tremblay"] * 6),
        [{"kind": "format", "column": "v", "value": "insert_space", "count": 6}])
    for row in altered:
        assert row["v"].count(" ") == 1
        assert row["v"].replace(" ", "") == "Tremblay"
        assert not row["v"].startswith(" ") and not row["v"].endswith(" ")


def test_drop_char_removes_exactly_one_character(tmp_path: Path) -> None:
    altered, _, _ = _inject(
        tmp_path, _each_row(["H3A1B2"] * 6),
        [{"kind": "format", "column": "v", "value": "drop_char", "count": 6}])
    for row in altered:
        assert len(row["v"]) == 5
        assert any(row["v"] == "H3A1B2"[:i] + "H3A1B2"[i + 1:] for i in range(6))


def test_duplicate_row_copies_an_earlier_output_row_without_changing_the_row_count(
        tmp_path: Path) -> None:
    rows = _each_row([f"value-{i}" for i in range(30)])
    altered, changes, summary = _inject(
        tmp_path, rows, [{"kind": "duplicate_row", "count": 30, "class": "copies"}])
    assert len(altered) == 30
    entry = summary["operations"][0]  # type: ignore[index]
    # The first row has no earlier row to copy.
    assert (entry["applied_rows"], entry["skipped_rows"]) == (29, 1)
    assert "column" not in entry
    assert altered[0] == rows[0]
    for position, row in enumerate(altered[1:], 1):
        assert row in altered[:position]
    for change in changes:
        source = int(change["cause"].rsplit("copy_of_row=", 1)[1])
        assert source < int(change["row_number"])
        assert change["kind"] == "duplicate_row"
        assert change["after"] == altered[source - 2][change["column"]]


def test_duplicate_row_respects_its_absolute_count_and_when_condition(tmp_path: Path) -> None:
    rows = [{"id": f"R{i:03d}", "v": "a" if i % 2 else "b"} for i in range(40)]
    altered, changes, summary = _inject(
        tmp_path, rows, [{"kind": "duplicate_row", "count": 6, "when": {"v": "a"}}])
    entry = summary["operations"][0]  # type: ignore[index]
    assert entry["requested_rows"] == 6
    assert entry["applied_rows"] + entry["skipped_rows"] == 6
    assert len(altered) == 40
    assert len({change["event_id"] for change in changes}) == entry["applied_rows"]


def test_class_is_copied_to_journal_and_summary_only_when_declared(tmp_path: Path) -> None:
    with_class = tmp_path / "with"
    with_class.mkdir()
    _, changes, summary = _inject(
        with_class, _each_row(["x"] * 10),
        [{"kind": "set_missing", "column": "v", "count": 3, "class": "blank_value"},
         {"kind": "replace", "column": "id", "value": "Z", "count": 2}])
    assert list(changes[0]) == [*CHANGE_FIELDS, "class"]
    assert sorted({(c["operation_index"], c["class"]) for c in changes}) == [
        ("1", "blank_value"), ("2", "")]
    assert [entry.get("class") for entry in summary["operations"]] == ["blank_value", None]  # type: ignore[attr-defined]
    without = tmp_path / "without"
    without.mkdir()
    _, changes, summary = _inject(
        without, _each_row(["x"] * 10),
        [{"kind": "set_missing", "column": "v", "rate": 0.3}])
    assert list(changes[0]) == CHANGE_FIELDS
    assert set(summary["operations"][0]) == {  # type: ignore[index]
        "index", "kind", "column", "rate", "requested_rows", "applied_rows",
        "skipped_rows", "applied_rate"}


COUNT_DEFINITION = """\
definition_version: 1
id: counts
defaults: {{seed: 5}}
datasets:
  - id: people
    rows: {rows}
    columns:
      - {{name: id, type: string, generate: {{kind: sequence, prefix: P, width: 7}}}}
      - {{name: city, type: string, generate: {{kind: choice, weights: {{Paris: 1, Rome: 1}}}}}}
anomaly_profiles:
  - id: stress
    targets: [people]
    operations:
      - {{kind: set_missing, column: city, count: 7, class: missing_city}}
      - {{kind: format, column: id, value: double_hyphen, count: 2}}
      - {{kind: replace, column: city, value: Oslo, count: 1, class: lone_city,
         when: {{city: Rome}}}}
"""


def _run_counts(tmp_path: Path, rows: int) -> list[dict[str, Any]]:
    package = write_columns_package(tmp_path, COUNT_DEFINITION.format(rows=rows))
    out = tmp_path / "out"
    generate_datasets(build_generate_plan(package, output_dir=out, anomaly_profile="stress"))
    summary = json.loads((out / "people.stress.summary.json").read_text(encoding="utf-8"))
    return cast(list[dict[str, Any]], summary["operations"])


def test_absolute_count_touches_the_same_rows_at_any_file_size(tmp_path: Path) -> None:
    small = _run_counts(tmp_path / "small", 300)
    large = _run_counts(tmp_path / "large", 3000)
    for entries in (small, large):
        assert [e["count"] for e in entries] == [7, 2, 1]
        assert [e["requested_rows"] for e in entries] == [7, 2, 1]
        assert all("rate" not in e for e in entries)
        assert [e["applied_rows"] + e["skipped_rows"] for e in entries] == [7, 2, 1]
    assert small[0]["applied_rows"] == large[0]["applied_rows"] == 7
    # The id column holds no hyphen: the request is made and reported as skipped.
    assert (large[1]["applied_rows"], large[1]["skipped_rows"]) == (0, 2)


@pytest.mark.parametrize(("operation", "message"), [
    ("{kind: set_missing, column: city, rate: 0.1, count: 3}", "exactly one of rate and count"),
    ("{kind: set_missing, column: city}", "exactly one of rate and count"),
    ("{kind: set_missing, column: city, count: 0}", "positive integer"),
    ("{kind: set_missing, column: city, count: 1.5}", "positive integer"),
    ("{kind: set_missing, column: city, count: true}", "positive integer"),
    ("{kind: set_missing, column: city, rate: 1.5}", "from 0 to 1"),
    ("{kind: set_missing, column: city, count: 1, class: Bad-Name}", "operation.class"),
    ("{kind: set_missing, column: city, count: 1, class: 7}", "operation.class"),
    ("{kind: duplicate_row, column: city, count: 1}", "operation.column is unused"),
    ("{kind: duplicate_row, value: x, count: 1}", "operation.value is unused"),
    ("{kind: set_missing, count: 1}", "operation.column must name a column"),
    ("{kind: format, column: city, value: shout, count: 1}", "unknown format"),
])
def test_definition_rejects_invalid_quantity_class_and_row_options(
        tmp_path: Path, operation: str, message: str) -> None:
    text = COUNT_DEFINITION.format(rows=10).split("    operations:")[0] + (
        f"    operations:\n      - {operation}\n")
    package = write_columns_package(tmp_path, text)
    with pytest.raises(ConfigurationError, match=message):
        build_generate_plan(package, output_dir=tmp_path / "out")


def test_count_larger_than_the_dataset_fails_before_any_write(tmp_path: Path) -> None:
    package = write_columns_package(tmp_path, COUNT_DEFINITION.format(rows=5))
    with pytest.raises(ConfigurationError, match="count 7 but the dataset has 5 rows"):
        build_generate_plan(package, output_dir=tmp_path / "out", anomaly_profile="stress")
    assert not (tmp_path / "out").exists()
    # The same profile is valid when it is not selected.
    assert build_generate_plan(package, output_dir=tmp_path / "out").rows == {"people": 5}


def test_computer_profile_accepts_counts_classes_and_new_transforms_and_checks_them(
        tmp_path: Path) -> None:
    copied = tmp_path / "package"
    shutil.copytree(COMPUTER, copied)
    manifest = copied / "dataset.yaml"
    source = manifest.read_text(encoding="utf-8")
    anchor = "  dirty_realistic:\n"
    extra = (anchor
             + "    targets: [computers]\n    operations:\n"
             + "      - {kind: format, column: cpu_model, value: suffix_x, count: 4,"
             + " class: tagged_cpu}\n"
             + "      - {kind: duplicate_row, count: 2}\n")
    manifest.write_text(source.replace(
        anchor + "    targets: [computers]\n    operations:\n", extra, 1), encoding="utf-8")
    out = tmp_path / "out"
    generate_datasets(build_generate_plan(
        copied, output_dir=out, rows=50, seed=3, output_profile="extended",
        anomaly_profile="dirty_realistic"))
    summary = json.loads((out / "computers-en.dirty_realistic.summary.json").read_text(
        encoding="utf-8"))
    first = summary["operations"][0]
    assert (first["count"], first["class"], first["requested_rows"]) == (4, "tagged_cpu", 4)
    assert summary["operations"][1]["kind"] == "duplicate_row"
    with pytest.raises(ConfigurationError, match="count 4 but the dataset has 3 rows"):
        build_generate_plan(copied, output_dir=tmp_path / "small", rows=3,
                            output_profile="extended", anomaly_profile="dirty_realistic")
    assert not (tmp_path / "small").exists()
