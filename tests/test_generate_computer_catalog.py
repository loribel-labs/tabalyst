# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check that the expanded Computer catalog has reachable complete generations."""

from datetime import date
from importlib.resources import files
from pathlib import Path

from tabalyst.generate_computer import derive_computer_row
from tabalyst.generate_computer_output import render_computer_row
from tabalyst.generate_package import load_generate_package
from tabalyst.generate_selection import select_catalog_row

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))
COMPONENTS = (
    "cpu", "gpu", "memory", "storage", "display", "operating_system", "color",
)


def test_every_model_has_a_reachable_complete_generation() -> None:
    """Every model has an edition with hierarchy and seven technical choices."""
    package = load_generate_package(PACKAGE)
    tables = package.tables
    models = {row["id"]: row for row in tables["product_model"].rows}
    families = {row["id"]: row for row in tables["product_family"].rows}
    generations = tables["model_generation"].rows
    assert {model["product_family_id"] for model in models.values()} == set(families)
    assert {row["product_model_id"] for row in generations} == set(models)
    assert all("demo" not in str(row["id"]).lower() for row in generations)
    generation_ids = {row["id"] for row in generations}
    for component in COMPONENTS:
        assert generation_ids <= {
            row["generation_id"] for row in tables[f"generation_{component}"].rows
        }
    for table in ("standard_specs", "extended_specs"):
        assert generation_ids <= {row["id"] for row in tables[table].rows}

    family_types = {
        (row["product_family_id"], row["computer_type_id"])
        for row in tables["product_family_computer_type"].rows
    }
    family_segments = {
        (row["product_family_id"], row["product_segment_id"])
        for row in tables["product_family_product_segment"].rows
    }
    type_segments = {
        (row["computer_type_id"], row["product_segment_id"])
        for row in tables["computer_type_product_segment"].rows
    }
    segment_brands = {
        (row["product_segment_id"], row["brand_id"])
        for row in tables["product_segment_brand"].rows
    }
    type_forms = {
        (row["computer_type_id"], row["form_factor_id"])
        for row in tables["computer_type_form_factor"].rows
    }
    model_forms = {
        (row["product_model_id"], row["form_factor_id"])
        for row in tables["model_form_factor"].rows
    }
    for model_id, model in models.items():
        family_id = model["product_family_id"]
        brand_id = families[family_id]["brand_id"]
        assert any(
            (family_id, kind) in family_types
            and (kind, segment) in type_segments
            and (family_id, segment) in family_segments
            and (segment, brand_id) in segment_brands
            and (kind, form) in type_forms
            and (model_id, form) in model_forms
            for kind, segment in type_segments
            for _, form in model_forms
        ), model_id


def test_every_generation_has_compatible_cpu_os_and_gpu_display() -> None:
    """Each edition has a compatible CPU/OS and GPU/display pair."""
    tables = load_generate_package(PACKAGE).tables
    cpu_os = {
        (row["cpu_id"], row["operating_system_id"])
        for row in tables["cpu_operating_system"].rows
    }
    gpu_display = {
        (row["gpu_id"], row["display_id"])
        for row in tables["gpu_display"].rows
    }
    for generation in tables["model_generation"].rows:
        generation_id = generation["id"]
        choices = {
            component: {
                row[f"{component}_id"]
                for row in tables[f"generation_{component}"].rows
                if row["generation_id"] == generation_id
            }
            for component in ("cpu", "gpu", "display", "operating_system")
        }
        assert any(
            (cpu, os) in cpu_os
            for cpu in choices["cpu"]
            for os in choices["operating_system"]
        ), generation_id
        assert any(
            (gpu, display) in gpu_display
            for gpu in choices["gpu"]
            for display in choices["display"]
        ), generation_id


def test_all_six_computer_types_generate_extended_rows() -> None:
    """A deterministic sample reaches each type and renders an extended offer."""
    package = load_generate_package(PACKAGE)
    seen: set[str] = set()
    for index in range(250):
        selected = select_catalog_row(package, "computers", 42, index)
        kind = str(selected["computer_type_id"])
        if kind in seen:
            continue
        row = derive_computer_row(
            package, selected, "computers", 42, index, date(2026, 9, 30),
        )
        rendered = render_computer_row(package, row, "en", "extended")
        assert rendered["model"] and rendered["generation"]
        assert rendered["cpu_model"] and rendered["gpu_model"]
        assert rendered["memory_gb"] and rendered["storage_gb"]
        assert rendered["operating_system"] and rendered["color"]
        if kind in {"laptop", "all_in_one"}:
            assert rendered["display_type"] != "none"
        else:
            assert rendered["display_type"] == "none"
        seen.add(kind)
    assert seen == {
        "laptop", "desktop", "all_in_one", "mini_pc",
        "single_board_computer", "server",
    }


def test_portable_only_generates_laptops() -> None:
    """The portable profile excludes all five other computer types."""
    package = load_generate_package(PACKAGE)
    assert {
        select_catalog_row(package, "computers", 42, index, "portable_only")[
            "computer_type_id"
        ]
        for index in range(50)
    } == {"laptop"}
