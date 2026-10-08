# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests for the first Generate package loading lot."""

from __future__ import annotations

from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_package import load_generate_package


def _package(root: Path) -> Path:
    (root / "schemas").mkdir()
    (root / "data").mkdir()
    (root / "dataset.yaml").write_text(
        'format: tabalyst.generate.package\nformat_version: "0.1.0"\n'
        'id: mini_computer\npackage_version: "0.1.0"\n'
        'catalog: catalog.yaml\ndefaults: {rows: 10, seed: 42}\n'
        'datasets:\n  - id: computers\n    mode: generated\n'
        '    row_source: columns\n    schema: schemas/computers.yaml\n',
        encoding="utf-8",
    )
    (root / "catalog.yaml").write_text(
        "tables:\n  computer_type:\n    role: dictionary\n"
        "    file: data/computer_type.csv\n"
        "    schema: schemas/dictionary.yaml\n",
        encoding="utf-8",
    )
    (root / "schemas/dictionary.yaml").write_text(
        "type: dictionary\ncolumns:\n"
        "  id: {type: string, required: true, unique: true}\n"
        "  en: {type: string, required: true}\n"
        "  fr: {type: string, required: false}\n",
        encoding="utf-8",
    )
    (root / "schemas/computers.yaml").write_text(
        "columns:\n  - name: computer_type\n    type: string\n"
        "    from: computer_type_id\n",
        encoding="utf-8",
    )
    (root / "data/computer_type.csv").write_text(
        "id,en,fr\nlaptop,Laptop,Portable\n",
        encoding="utf-8",
    )
    return root


def test_loads_minimal_package_without_generating_rows(tmp_path: Path) -> None:
    package = load_generate_package(_package(tmp_path))
    assert package.id == "mini_computer"
    assert package.tables["computer_type"].rows[0]["fr"] == "Portable"
    assert len(package.input_paths) == 5


@pytest.mark.parametrize(
    ("relative", "replacement", "code"),
    [
        ("catalog.yaml", "tables:\n  computer_type: {}\n", "PACKAGE_SCHEMA"),
        ("dataset.yaml", "format: a\nformat: b\n", "PACKAGE_YAML"),
        ("data/computer_type.csv", "id,en,fr\nlaptop,Laptop,Portable\nlaptop,Laptop 2,\n", "PACKAGE_CSV_DUPLICATE"),
        ("data/computer_type.csv", "id,en,en\nlaptop,Laptop,Portable\n", "PACKAGE_CSV_HEADER"),
        ("data/computer_type.csv", "id,en,fr\nlaptop,,Portable\n", "PACKAGE_CSV_REQUIRED"),
        ("data/computer_type.csv", "id,en,fr\nBad ID,Laptop,Portable\n", "PACKAGE_SCHEMA"),
        ("data/computer_type.csv", 'id,en,fr\nlaptop,"unterminated,Portable\n', "PACKAGE_CSV_PARSE"),
    ],
)
def test_rejects_invalid_package_with_code(
    tmp_path: Path, relative: str, replacement: str, code: str,
) -> None:
    _package(tmp_path)
    (tmp_path / relative).write_text(replacement, encoding="utf-8")
    with pytest.raises(ConfigurationError, match=code):
        load_generate_package(tmp_path)


def test_rejects_missing_file(tmp_path: Path) -> None:
    _package(tmp_path)
    (tmp_path / "data/computer_type.csv").unlink()
    with pytest.raises(ConfigurationError, match="PACKAGE_FILE_MISSING"):
        load_generate_package(tmp_path)


def test_rejects_resource_outside_package(tmp_path: Path) -> None:
    _package(tmp_path)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        catalog.read_text(encoding="utf-8").replace(
            "data/computer_type.csv", "../outside.csv"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="PACKAGE_PATH"):
        load_generate_package(tmp_path)


def test_rejects_nonpositive_weight_with_row_and_column(tmp_path: Path) -> None:
    _package(tmp_path)
    (tmp_path / "catalog.yaml").write_text(
        "tables:\n  generation_memory:\n    role: weighted_relation\n"
        "    file: data/computer_type.csv\n"
        "    schema: schemas/dictionary.yaml\n",
        encoding="utf-8",
    )
    (tmp_path / "schemas/dictionary.yaml").write_text(
        "type: weighted_relation\ncolumns:\n"
        "  generation_id: {type: string, required: true}\n"
        "  memory_id: {type: string, required: true}\n"
        "  weight: {type: number, required: true}\n",
        encoding="utf-8",
    )
    (tmp_path / "data/computer_type.csv").write_text(
        "generation_id,memory_id,weight\ngen_one,mem_one,0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match=r"PACKAGE_CSV_WEIGHT: .*:2:weight:"):
        load_generate_package(tmp_path)


@pytest.mark.parametrize(
    ("value", "code"),
    [("oops", "PACKAGE_CSV_TYPE"), ("3", "PACKAGE_CSV_BOUND")],
)
def test_validates_typed_cells_and_bounds(
    tmp_path: Path, value: str, code: str,
) -> None:
    _package(tmp_path)
    (tmp_path / "schemas/dictionary.yaml").write_text(
        "type: dictionary\ncolumns:\n"
        "  id: {type: string, required: true}\n"
        "  en: {type: string, required: true}\n"
        "  score: {type: integer, required: true, min: 4, max: 9}\n",
        encoding="utf-8",
    )
    (tmp_path / "data/computer_type.csv").write_text(
        f"id,en,score\nlaptop,Laptop,{value}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match=code):
        load_generate_package(tmp_path)
