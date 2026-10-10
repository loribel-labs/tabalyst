# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Verify the Computer hierarchy and its generation profiles."""

from collections import Counter
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_package import DatasetPackage, load_generate_package
from tabalyst.generate_selection import select_catalog_row

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))
FIELDS = (
    "computer_type_id", "product_segment_id", "brand_id",
    "product_family_id", "product_model_id", "generation_id", "form_factor_id",
)


def _draws(package: DatasetPackage, count: int, profile: str = "balanced",
           seed: int = 42) -> list[tuple[str, ...]]:
    return [tuple(str(row[field]) for field in FIELDS) for index in range(count)
            for row in [select_catalog_row(package, "computers", seed, index, profile)]]


def test_hierarchy_draws_only_declared_parent_and_compatibility_links() -> None:
    package = load_generate_package(PACKAGE)
    rows = _draws(package, 400)
    links = {
        name: {tuple(str(row[column]) for column in columns) for row in package.tables[name].rows}
        for name, columns in (
            ("computer_type_product_segment", ("computer_type_id", "product_segment_id")),
            ("product_segment_brand", ("product_segment_id", "brand_id")),
            ("product_family_computer_type", ("product_family_id", "computer_type_id")),
            ("product_family_product_segment", ("product_family_id", "product_segment_id")),
            ("model_form_factor", ("product_model_id", "form_factor_id")),
            ("computer_type_form_factor", ("computer_type_id", "form_factor_id")),
        )
    }
    parents = {
        name: {str(row["id"]): str(row[parent]) for row in package.tables[name].rows}
        for name, parent in (
            ("product_family", "brand_id"),
            ("product_model", "product_family_id"),
            ("model_generation", "product_model_id"),
        )
    }
    for kind, segment, brand, family, model, generation, form in rows:
        assert (kind, segment) in links["computer_type_product_segment"]
        assert (segment, brand) in links["product_segment_brand"]
        assert parents["product_family"][family] == brand
        assert (family, kind) in links["product_family_computer_type"]
        assert (family, segment) in links["product_family_product_segment"]
        assert parents["product_model"][model] == family
        assert parents["model_generation"][generation] == model
        assert (model, form) in links["model_form_factor"]
        assert (kind, form) in links["computer_type_form_factor"]


def test_hierarchy_covers_every_catalog_class_and_is_deterministic() -> None:
    package = load_generate_package(PACKAGE)
    first = _draws(package, 200)
    assert first == _draws(load_generate_package(PACKAGE), 200)
    assert first != _draws(package, 200, seed=43)
    assert {row[0] for row in first} == {
        str(entry["id"]) for entry in package.tables["computer_type"].rows
    }
    assert len({row[4] for row in first}) >= 40


def test_generation_profiles_control_type_proportions() -> None:
    package = load_generate_package(PACKAGE)
    balanced = Counter(row[0] for row in _draws(package, 500))
    assert 150 <= balanced["laptop"] <= 250
    assert set(balanced) == {
        "laptop", "desktop", "all_in_one", "mini_pc",
        "single_board_computer", "server",
    }
    assert {row[0] for row in _draws(package, 50, "portable_only")} == {"laptop"}


def test_labels_do_not_change_canonical_choices(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    before = _draws(load_generate_package(root), 100)
    path = root / "data/brand.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("Acer", "Acér"),
                    encoding="utf-8")
    assert _draws(load_generate_package(root), 100) == before


def test_invalid_relation_reference_fails_before_selection(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/product_segment_brand.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("consumer,acer", "consumer,unknown"),
                    encoding="utf-8")
    with pytest.raises(ConfigurationError, match="PACKAGE_REFERENCE_UNKNOWN"):
        load_generate_package(root)


def test_incompatible_form_relation_removes_its_hierarchy_branch(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/computer_type_form_factor.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("laptop,clamshell", "laptop,tower"),
                    encoding="utf-8")
    assert all(
        kind != "laptop" or form != "clamshell"
        for kind, _, _, _, _, _, form in _draws(load_generate_package(root), 100)
    )
