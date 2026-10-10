# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Verify Computer component compatibility and catalog validation."""

import shutil
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_package import Cell, DatasetPackage, load_generate_package
from tabalyst.generate_selection import select_catalog_row

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))
COMPONENTS = (
    "cpu", "gpu", "memory", "storage", "display", "operating_system", "color",
)


def _pairs(package: DatasetPackage, table: str,
           first: str, second: str) -> set[tuple[Cell, Cell]]:
    return {(row[first], row[second]) for row in package.tables[table].rows}


def test_selected_components_obey_generation_and_pair_compatibility() -> None:
    """Every sampled configuration follows the declared component relations."""
    package = load_generate_package(PACKAGE)
    gpu_display = _pairs(package, "gpu_display", "gpu_id", "display_id")
    cpu_os = _pairs(package, "cpu_operating_system", "cpu_id", "operating_system_id")
    relations = {
        component: _pairs(
            package, f"generation_{component}", "generation_id", f"{component}_id",
        )
        for component in COMPONENTS
    }
    exclusions = [
        row for row in package.tables["profile_exclusions"].rows
        if row["scope_id"] == "global"
    ]
    for index in range(250):
        row = select_catalog_row(package, "computers", 42, index)
        for component in COMPONENTS:
            assert (row["generation_id"], row[f"{component}_id"]) in relations[component]
        assert (row["gpu_id"], row["display_id"]) in gpu_display
        assert (row["cpu_id"], row["operating_system_id"]) in cpu_os
        assert not any(
            row[rule["condition_field"]] == rule["condition_id"]
            and row[rule["target_field"]] == rule["target_id"]
            for rule in exclusions
        )


def test_missing_influence_keeps_generation_choices_available(tmp_path: Path) -> None:
    """An absent preference factor does not remove a valid storage choice."""
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/gpu_storage_weight.csv"
    path.write_text("gpu_id,storage_id,weight\n", encoding="utf-8")
    package = load_generate_package(root)
    storage = _pairs(package, "generation_storage", "generation_id", "storage_id")
    for index in range(50):
        row = select_catalog_row(package, "computers", 42, index)
        assert (row["generation_id"], row["storage_id"]) in storage


def test_missing_required_generation_choice_fails_at_load(tmp_path: Path) -> None:
    """A catalog missing memory choices for generations cannot be loaded."""
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    (root / "data/generation_memory.csv").write_text(
        "generation_id,memory_id,weight\n"
        "thinkpad_t14_gen5,ddr5_16gb,1\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="PACKAGE_REQUIRED_CHOICE"):
        load_generate_package(root)


def test_unknown_component_reference_fails_at_load(tmp_path: Path) -> None:
    """A typo in a CPU ID fails before selecting any offer."""
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/generation_cpu.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "intel_core_ultra_5_225u", "unknown_cpu", 1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="PACKAGE_REFERENCE_UNKNOWN"):
        load_generate_package(root)


def test_unknown_global_exclusion_id_fails_at_load(tmp_path: Path) -> None:
    """An exclusion may reserve an unused component, but cannot contain a typo."""
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/profile_exclusions.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("ddr4_4gb", "unknown_memory", 1),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="PACKAGE_CONSTRAINT"):
        load_generate_package(root)
