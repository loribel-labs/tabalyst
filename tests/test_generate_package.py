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


def _add_reference_table(root: Path, role: str, name: str = "link") -> None:
    catalog = root / "catalog.yaml"
    catalog.write_text(
        catalog.read_text(encoding="utf-8")
        + f"  {name}:\n    role: {role}\n"
          f"    file: data/{name}.csv\n    schema: schemas/{name}.yaml\n",
        encoding="utf-8",
    )
    (root / f"schemas/{name}.yaml").write_text(
        f"type: {role}\ncolumns:\n"
        + ("  id: {type: string, required: true, unique: true}\n"
           "  en: {type: string, required: true}\n" if role == "dictionary" else "")
        +
        "  type_id: {type: string, required: true, references: computer_type.id}\n"
        "  item_id: {type: string, required: true, references: computer_type.id}\n"
        + ("  weight: {type: number, required: true}\n" if role == "weighted_relation" else ""),
        encoding="utf-8",
    )
    (root / f"data/{name}.csv").write_text(
        ("id,en," if role == "dictionary" else "")
        + "type_id,item_id" + (",weight" if role == "weighted_relation" else "")
        + "\n" + ("link,Link," if role == "dictionary" else "")
        + "laptop,laptop" + (",1" if role == "weighted_relation" else "") + "\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("role", ["dictionary", "entity", "relation", "weighted_relation", "constraint", "resource"])
def test_resolves_foreign_keys_for_table_roles(tmp_path: Path, role: str) -> None:
    _package(tmp_path)
    _add_reference_table(tmp_path, role)
    package = load_generate_package(tmp_path)
    assert package.value_index["computer_type"]["id"] == {"laptop"}
    assert len(package.relation_index["link"]["type_id"]["laptop"]) == 1


@pytest.mark.parametrize("role", ["dictionary", "entity", "relation", "weighted_relation", "constraint", "resource"])
def test_rejects_unknown_foreign_key_at_source_cell(tmp_path: Path, role: str) -> None:
    _package(tmp_path)
    _add_reference_table(tmp_path, role)
    path = tmp_path / "data/link.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("laptop,laptop", "missing,laptop"), encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"PACKAGE_REFERENCE_UNKNOWN: .*link.csv:2:type_id:.*computer_type.id.*missing"):
        load_generate_package(tmp_path)


@pytest.mark.parametrize("role", ["relation", "weighted_relation"])
def test_rejects_duplicate_relation_pair(tmp_path: Path, role: str) -> None:
    _package(tmp_path)
    _add_reference_table(tmp_path, role)
    path = tmp_path / "data/link.csv"
    value = "laptop,laptop" + (",1" if role == "weighted_relation" else "")
    path.write_text(path.read_text(encoding="utf-8") + value + "\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"PACKAGE_RELATION_DUPLICATE: .*link.csv:3:type_id,item_id:"):
        load_generate_package(tmp_path)


@pytest.mark.parametrize("missing", ["cpu", "memory", "storage", "display"])
def test_rejects_generation_without_required_component(tmp_path: Path, missing: str) -> None:
    _package(tmp_path)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(catalog.read_text(encoding="utf-8")
                       + "  generation:\n    role: dictionary\n"
                         "    file: data/generation.csv\n"
                         "    schema: schemas/dictionary.yaml\n", encoding="utf-8")
    (tmp_path / "data/generation.csv").write_text(
        "id,en,fr\ngen_one,One,Un\n", encoding="utf-8",
    )
    for component in ("cpu", "memory", "storage", "display"):
        catalog.write_text(catalog.read_text(encoding="utf-8")
                           + f"  generation_{component}:\n    role: relation\n"
                             f"    file: data/generation_{component}.csv\n"
                             f"    schema: schemas/generation_{component}.yaml\n",
                           encoding="utf-8")
        (tmp_path / f"schemas/generation_{component}.yaml").write_text(
            "type: relation\ncolumns:\n"
            "  generation_id: {type: string, required: true, references: generation.id}\n"
            f"  {component}_id: {{type: string, required: true, references: computer_type.id}}\n",
            encoding="utf-8",
        )
        (tmp_path / f"data/generation_{component}.csv").write_text(
            f"generation_id,{component}_id\n"
            + ("" if component == missing else "gen_one,laptop\n"),
            encoding="utf-8",
        )
    with pytest.raises(ConfigurationError, match=f"PACKAGE_REQUIRED_CHOICE.*{missing}"):
        load_generate_package(tmp_path)


def test_rejects_required_entity_without_relation(tmp_path: Path) -> None:
    _package(tmp_path)
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(catalog.read_text(encoding="utf-8")
                       + "  product:\n    role: entity\n"
                         "    file: data/product.csv\n    schema: schemas/product.yaml\n"
                         "  product_type:\n    role: relation\n"
                         "    file: data/product_type.csv\n"
                         "    schema: schemas/product_type.yaml\n", encoding="utf-8")
    (tmp_path / "schemas/product.yaml").write_text(
        "type: entity\ncolumns:\n"
        "  id: {type: string, required: true, unique: true}\n", encoding="utf-8",
    )
    (tmp_path / "data/product.csv").write_text("id\none\ntwo\n", encoding="utf-8")
    (tmp_path / "schemas/product_type.yaml").write_text(
        "type: relation\ncolumns:\n"
        "  product_id: {type: string, required: true, references: product.id}\n"
        "  type_id: {type: string, required: true, references: computer_type.id}\n",
        encoding="utf-8",
    )
    (tmp_path / "data/product_type.csv").write_text(
        "product_id,type_id\none,laptop\n", encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match=r"PACKAGE_REFERENCE_ORPHAN: .*product.csv:3:id:.*two"):
        load_generate_package(tmp_path)


def test_rejects_reference_to_unknown_table(tmp_path: Path) -> None:
    _package(tmp_path)
    _add_reference_table(tmp_path, "relation")
    schema = tmp_path / "schemas/link.yaml"
    schema.write_text(schema.read_text(encoding="utf-8").replace(
        "computer_type.id", "missing.id", 1,
    ), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="PACKAGE_REFERENCE_SCHEMA"):
        load_generate_package(tmp_path)


@pytest.mark.parametrize(
    "step",
    [
        "source: missing\n        candidate_column: id",
        "source: computer_type\n        candidate_column: absent",
        "source: computer_type\n        candidate_column: id\n        where: {id: future}",
    ],
)
def test_rejects_unknown_catalog_step_reference(tmp_path: Path, step: str) -> None:
    _package(tmp_path)
    manifest = tmp_path / "dataset.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        "row_source: columns\n",
        "row_source: catalog_steps\n    steps:\n"
        "      - id: select_type\n        kind: select\n"
        f"        output: computer_type_id\n        {step}\n",
    ), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="PACKAGE_STEP_REFERENCE"):
        load_generate_package(tmp_path)


def test_rejects_duplicate_candidate_in_one_selection_set(tmp_path: Path) -> None:
    _package(tmp_path)
    _add_reference_table(tmp_path, "relation")
    (tmp_path / "data/computer_type.csv").write_text(
        "id,en,fr\nlaptop,Laptop,Portable\ndesktop,Desktop,Bureau\n",
        encoding="utf-8",
    )
    (tmp_path / "data/link.csv").write_text(
        "type_id,item_id\nlaptop,laptop\ndesktop,laptop\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "dataset.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        "row_source: columns\n",
        "row_source: catalog_steps\n    steps:\n"
        "      - id: select_item\n        kind: select\n"
        "        output: item_id\n        source: link\n"
        "        candidate_column: item_id\n",
    ), encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"PACKAGE_STEP_DUPLICATE: .*link.csv:3:item_id:"):
        load_generate_package(tmp_path)


def test_rejects_empty_selected_candidate(tmp_path: Path) -> None:
    _package(tmp_path)
    _add_reference_table(tmp_path, "relation")
    schema = tmp_path / "schemas/link.yaml"
    schema.write_text(schema.read_text(encoding="utf-8").replace(
        "item_id: {type: string, required: true", "item_id: {type: string, required: false",
    ), encoding="utf-8")
    (tmp_path / "data/link.csv").write_text(
        "type_id,item_id\nlaptop,\n", encoding="utf-8",
    )
    manifest = tmp_path / "dataset.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        "row_source: columns\n",
        "row_source: catalog_steps\n    steps:\n"
        "      - id: select_item\n        kind: select\n"
        "        output: item_id\n        source: link\n"
        "        candidate_column: item_id\n",
    ), encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"PACKAGE_STEP_CANDIDATE: .*link.csv:2:item_id:"):
        load_generate_package(tmp_path)
