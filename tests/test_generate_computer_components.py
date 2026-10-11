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
DISPLAY_PREFERENCES = {
    "consumer": {"ips": 7, "oled": 2},
    "business": {"ips": 8, "oled": 1},
    "premium": {"ips": 3, "oled": 6, "mini_led": 3},
    "gaming": {"ips": 6, "oled": 4, "mini_led": 2},
    "creator": {"ips": 3, "oled": 5, "mini_led": 4},
    "workstation": {"ips": 6, "oled": 3},
}
STORAGE_PREFERENCES = {
    "consumer": {256: 1, 512: 6, 1000: 5},
    "business": {512: 5, 1000: 6, 2000: 2},
    "gaming": {512: 1, 1000: 6, 2000: 5, 4000: 2},
    "creator": {1000: 4, 2000: 6, 4000: 3},
    "workstation": {1000: 3, 2000: 6, 4000: 5, 8000: 2},
}


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
            row[str(rule["condition_field"])] == rule["condition_id"]
            and row[str(rule["target_field"])] == rule["target_id"]
            for rule in exclusions
        )


def test_segment_display_preferences_cover_matching_panels() -> None:
    """The source's type weights apply to every concrete panel of that type."""
    tables = load_generate_package(PACKAGE).tables
    expected = {
        (segment, display["id"]): weight
        for segment, preferences in DISPLAY_PREFERENCES.items()
        for display in tables["display"].rows
        if (weight := preferences.get(str(display["display_type"]))) is not None
    }
    actual = {
        (row["product_segment_id"], row["display_id"]): int(str(row["weight"]))
        for row in tables["product_segment_display_weight"].rows
    }
    assert actual == expected


def test_segment_storage_preferences_cover_matching_capacities() -> None:
    """The source's capacity weights apply to every concrete storage option."""
    tables = load_generate_package(PACKAGE).tables
    expected = {
        (segment, storage["id"]): weight
        for segment, preferences in STORAGE_PREFERENCES.items()
        for storage in tables["storage"].rows
        if (weight := preferences.get(int(str(storage["capacity_gb"])))) is not None
    }
    actual = {
        (row["product_segment_id"], row["storage_id"]): int(str(row["weight"]))
        for row in tables["product_segment_storage_weight"].rows
    }
    assert actual == expected


def test_segment_preferences_feed_storage_and_display_selection() -> None:
    """The segment rules are active on both component selection steps."""
    manifest = load_generate_package(PACKAGE).manifest
    datasets = manifest["datasets"]
    assert isinstance(datasets, list)
    steps = {step["output"]: step for step in datasets[0]["steps"]}
    for component in ("storage", "display"):
        assert {
            "source": f"product_segment_{component}_weight",
            "candidate_column": f"{component}_id",
            "where": {"product_segment_id": "product_segment_id"},
        } in steps[f"{component}_id"]["influences"]


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
