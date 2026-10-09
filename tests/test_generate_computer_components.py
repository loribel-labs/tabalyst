# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Verify Computer component choices, compatibility, and weighted correlations."""

import shutil
from collections import Counter
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


def _rows(package: DatasetPackage, count: int,
          profile: str = "balanced") -> list[dict[str, Cell]]:
    return [select_catalog_row(package, "computers", 42, index, profile)
            for index in range(count)]


def _pairs(package: DatasetPackage, table: str,
           first: str, second: str) -> set[tuple[Cell, Cell]]:
    return {(row[first], row[second]) for row in package.tables[table].rows}


def test_components_obey_generation_compatibility_and_exclusions() -> None:
    package = load_generate_package(PACKAGE)
    rows = _rows(package, 1500)
    for component in COMPONENTS:
        assert {row[f"{component}_id"] for row in rows} == {
            entry["id"] for entry in package.tables[component].rows
        }
    for row in rows:
        for component in COMPONENTS:
            assert (row["generation_id"], row[f"{component}_id"]) in _pairs(
                package, f"generation_{component}", "generation_id",
                f"{component}_id",
            )
        assert (row["gpu_id"], row["display_id"]) in _pairs(
            package, "gpu_display", "gpu_id", "display_id",
        )
        assert (row["cpu_id"], row["operating_system_id"]) in _pairs(
            package, "cpu_operating_system", "cpu_id", "operating_system_id",
        )
        if str(row["gpu_id"]).endswith("discrete"):
            assert row["memory_id"] == "mem_32"
    assert _rows(package, 100) == _rows(load_generate_package(PACKAGE), 100)
    assert {row["computer_type_id"] for row in _rows(
        package, 100, "portable_only",
    )} == {"laptop"}


def test_component_weights_and_correlations_shape_distributions() -> None:
    package = load_generate_package(PACKAGE)
    rows = _rows(package, 5000)
    laptop = [row for row in rows if row["computer_type_id"] == "laptop"]
    desktop = [row for row in rows if row["computer_type_id"] == "desktop"]
    laptop_cpu = Counter(row["cpu_id"] for row in laptop)
    desktop_gpu = Counter(row["gpu_id"] for row in desktop)
    assert 2.5 < laptop_cpu["aster_c4"] / laptop_cpu["aster_c8"] < 3.5
    assert 2.5 < desktop_gpu["brindle_discrete"] / desktop_gpu["brindle_integrated"] < 3.5

    laptop_integrated = [
        row for row in laptop if row["gpu_id"] == "aster_integrated"
    ]
    laptop_discrete = [
        row for row in laptop if row["gpu_id"] == "aster_discrete"
    ]
    integrated_memory = Counter(row["memory_id"] for row in laptop_integrated)
    assert integrated_memory["mem_16"] > 5 * integrated_memory["mem_32"]
    integrated_storage = Counter(row["storage_id"] for row in laptop_integrated)
    discrete_storage = Counter(row["storage_id"] for row in laptop_discrete)
    assert integrated_storage["ssd_512"] > 4 * integrated_storage["ssd_1024"]
    assert discrete_storage["ssd_1024"] > discrete_storage["ssd_512"]
    assert {row["display_id"] for row in laptop_integrated} == {"panel_14_fhd"}
    assert {row["operating_system_id"] for row in rows
            if row["cpu_id"] == "aster_c4"} == {"libre_os"}


def test_missing_influence_is_neutral_and_does_not_exclude_candidate(
    tmp_path: Path,
) -> None:
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/gpu_storage_weight.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "aster_discrete,ssd_1024,4\n", "",
        ),
        encoding="utf-8",
    )
    rows = _rows(load_generate_package(root), 1000)
    assert any(
        row["gpu_id"] == "aster_discrete"
        and row["storage_id"] == "ssd_1024"
        for row in rows
    )


@pytest.mark.parametrize(("table", "context_field", "context_id", "target_field", "target_id"), [
    ("cpu_memory_weight", "cpu_id", "aster_c8", "memory_id", "mem_32"),
    ("gpu_memory_weight", "gpu_id", "aster_integrated", "memory_id", "mem_16"),
    ("gpu_storage_weight", "gpu_id", "aster_discrete", "storage_id", "ssd_1024"),
    ("product_segment_memory_weight", "product_segment_id", "mobile_work",
     "memory_id", "mem_16"),
])
def test_each_influence_increases_its_target_frequency(
    tmp_path: Path, table: str, context_field: str, context_id: str,
    target_field: str, target_id: str,
) -> None:
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    before = _rows(load_generate_package(root), 3000)
    path = root / f"data/{table}.csv"
    path.write_text(
        path.read_text(encoding="utf-8").splitlines()[0] + "\n",
        encoding="utf-8",
    )
    after = _rows(load_generate_package(root), 3000)
    def count(rows: list[dict[str, Cell]]) -> int:
        return sum(
            row[context_field] == context_id and row[target_field] == target_id
            for row in rows
        )
    assert count(before) > count(after)


def test_missing_required_generation_choice_fails_at_load(tmp_path: Path) -> None:
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/generation_memory.csv"
    path.write_text(
        "generation_id,memory_id,weight\n"
        "brindle_bay_desk_g1,mem_16,1\n"
        "brindle_bay_desk_g1,mem_32,3\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="PACKAGE_REQUIRED_CHOICE"):
        load_generate_package(root)


def test_exhausted_technical_compatibility_fails_without_retry(
    tmp_path: Path,
) -> None:
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    (root / "data/gpu_display.csv").write_text(
        "gpu_id,display_id\n", encoding="utf-8",
    )
    package = load_generate_package(root)
    with pytest.raises(ConfigurationError, match="GENERATION_IMPOSSIBLE_CONFIGURATION"):
        select_catalog_row(package, "computers", 42, 0)


def test_unknown_component_reference_fails_at_load(tmp_path: Path) -> None:
    root = tmp_path / "computer"
    shutil.copytree(PACKAGE, root)
    path = root / "data/generation_cpu.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("aster_c4", "unknown_cpu"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="PACKAGE_REFERENCE_UNKNOWN"):
        load_generate_package(root)
