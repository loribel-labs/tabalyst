# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check Computer joins, stable identities, and synthetic offer invariants."""

import shutil
from collections import defaultdict
from datetime import date
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_computer import derive_computer_row
from tabalyst.generate_package import Cell, DatasetPackage, load_generate_package
from tabalyst.generate_selection import select_catalog_row

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))
AS_OF = date(2026, 9, 30)


def _row(package: DatasetPackage, index: int, market: str = "ca") -> dict[str, Cell]:
    selected = select_catalog_row(package, "computers", 42, index, "balanced")
    return derive_computer_row(package, selected, "computers", 42, index, AS_OF, market)


def test_component_specifications_join_selected_catalog_rows() -> None:
    package = load_generate_package(PACKAGE)
    for index in range(100):
        row = _row(package, index)
        for table, columns in {
            "cpu": {"brand_id": "cpu_brand_id", "family": "cpu_family",
                    "model": "cpu_model", "cores": "cpu_cores", "threads": "cpu_threads"},
            "gpu": {"brand_id": "gpu_brand_id", "family": "gpu_family",
                    "model": "gpu_model", "gpu_type": "gpu_type", "vram_gb": "gpu_vram_gb"},
            "memory": {"memory_type": "memory_type", "capacity_gb": "memory_gb"},
            "storage": {"storage_type": "storage_type", "capacity_gb": "storage_gb"},
            "display": {"size_in": "display_size_in", "display_type": "display_type",
                        "resolution": "display_resolution",
                        "refresh_rate_hz": "display_refresh_rate_hz",
                        "touch": "display_touch"},
            "operating_system": {"os_family": "os_family"},
        }.items():
            source = next(entry for entry in package.tables[table].rows
                          if entry["id"] == row[f"{table}_id"])
            for source_column, result_column in columns.items():
                assert row[result_column] == source[source_column]
        assert isinstance(row["storage_gb"], int) and row["storage_gb"] > 0
        assert type(row["display_touch"]) is bool


def test_standard_fields_join_catalog_and_obey_component_rules() -> None:
    package = load_generate_package(PACKAGE)
    for index in range(100):
        row = _row(package, index)
        cpu = next(entry for entry in package.tables["cpu"].rows if entry["id"] == row["cpu_id"])
        display = next(entry for entry in package.tables["display"].rows
                       if entry["id"] == row["display_id"])
        specs = next(entry for entry in package.tables["standard_specs"].rows
                     if entry["id"] == row["generation_id"])
        subcategory = next(entry for entry in package.tables["product_subcategory"].rows
                           if entry["id"] == row["product_subcategory_id"])
        assert row["product_subcategory_id"] == subcategory["id"]
        assert row["product_category_id"] == subcategory["product_category_id"]
        assert row["cpu_architecture"] == cpu["architecture"]
        assert row["cpu_max_clock_ghz"] == cpu["max_clock_ghz"]
        assert row["npu_tops"] == cpu["npu_tops"]
        assert row["display_brightness_nits"] == display["brightness_nits"]
        assert row["display_finish"] == display["finish"]
        for field in ("wifi_standard", "bluetooth_version", "ethernet_speed",
                      "usb_a_ports", "usb_c_ports", "hdmi_ports", "battery_wh",
                      "power_adapter_w", "chassis_material", "camera_type",
                      "biometric_type", "warranty_period"):
            assert row[field] == specs[field]
        assert row["condition"] == "new"
        assert row["price_tier"] in {"entry", "premium"}
        assert row["product_lifecycle_status"] == (
            "current" if row["product_age_months"] < 24 else "mature"
        )

    selected = select_catalog_row(package, "computers", 42, 0, "balanced")
    older = derive_computer_row(package, selected, "computers", 42, 0,
                                date(2029, 9, 30), "us")
    assert older["product_age_months"] >= 24
    assert older["product_lifecycle_status"] == "mature"
    assert older["language"] == "en"
    assert older["keyboard_layout"] == "us_english"


def test_extended_fields_join_components_and_reject_impossible_hardware() -> None:
    package = load_generate_package(PACKAGE)
    for index in range(100):
        row = _row(package, index)
        cpu = next(entry for entry in package.tables["cpu"].rows
                   if entry["id"] == row["cpu_id"])
        display = next(entry for entry in package.tables["display"].rows
                       if entry["id"] == row["display_id"])
        specs = next(entry for entry in package.tables["extended_specs"].rows
                     if entry["id"] == row["generation_id"])
        assert row["npu_brand"] == cpu["npu_brand"]
        assert row["npu_family"] == cpu["npu_family"]
        npu_tops = row["npu_tops"]
        assert type(npu_tops) is int
        assert (row["npu_brand"] is None) == (npu_tops == 0)
        assert row["copilot_plus_pc"] == (npu_tops >= 40)
        assert row["display_aspect_ratio"] == display["aspect_ratio"]
        assert row["display_hdr"] == display["hdr"]
        assert row["display_color_gamut"] == display["color_gamut"]
        for field in ("cellular_type", "docking_support", "thunderbolt_ports",
                      "displayport_ports", "ethernet_port", "card_reader_type",
                      "memory_slots_total", "memory_slots_used", "m2_slots_total",
                      "m2_slots_used", "upgradeability_level", "width_mm",
                      "depth_mm", "height_mm", "chassis_finish", "microphone_type",
                      "speaker_configuration", "keyboard_type", "trusted_platform"):
            assert row[field] == specs[field]
    selected = select_catalog_row(package, "computers", 42, 0, "balanced")
    generation_id = selected["generation_id"]
    specs = next(entry for entry in package.tables["extended_specs"].rows
                 if entry["id"] == generation_id)
    original = specs["memory_slots_used"]
    specs["memory_slots_used"] = 9
    with pytest.raises(ConfigurationError, match="inconsistent Computer extended"):
        derive_computer_row(package, selected, "computers", 42, 0, AS_OF)
    specs["memory_slots_used"] = original
    cpu = next(entry for entry in package.tables["cpu"].rows
               if entry["id"] == selected["cpu_id"])
    original_npu = cpu["npu_family"]
    cpu["npu_family"] = None if original_npu is not None else "invalid"
    with pytest.raises(ConfigurationError, match="inconsistent Computer NPU"):
        derive_computer_row(package, selected, "computers", 42, 0, AS_OF)


def test_optional_subcategory_reference_rejects_unknown_id(tmp_path: Path) -> None:
    copied = tmp_path / "computer"
    shutil.copytree(PACKAGE, copied)
    segment = copied / "data/product_segment.csv"
    segment.write_text(segment.read_text(encoding="utf-8").replace(
        "general_purpose,General purpose,Usage général,",
        "general_purpose,General purpose,Usage général,unknown",
    ), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unknown"):
        load_generate_package(copied)


def test_configuration_variant_and_offer_identities_are_stable_and_unique() -> None:
    package = load_generate_package(PACKAGE)
    rows = [_row(package, index) for index in range(500)]
    assert rows == [_row(load_generate_package(PACKAGE), index) for index in range(500)]
    assert len({row["product_id"] for row in rows}) == len(rows)
    by_variant: dict[Cell, list[dict[str, Cell]]] = defaultdict(list)
    for row in rows:
        by_variant[row["variant_id"]].append(row)
        assert all(len(str(row[field]).split("_")[-1]) >= 32
                   for field in ("configuration_id", "variant_id", "product_id"))
    assert any(len(group) > 1 for group in by_variant.values())
    for group in by_variant.values():
        assert len({row["sku"] for row in group}) == 1
        assert len({row["mpn"] for row in group}) == 1
        assert len({row["configuration_id"] for row in group}) == 1
    us = _row(package, 0, "us")
    assert us["configuration_id"] == rows[0]["configuration_id"]
    assert us["variant_id"] != rows[0]["variant_id"]
    assert us["product_id"] == rows[0]["product_id"]


def test_commercial_values_obey_price_stock_date_and_review_rules() -> None:
    package = load_generate_package(PACKAGE)
    rows = [_row(package, index) for index in range(500)]
    for row in rows:
        assert row["currency"] == "CAD"
        assert isinstance(row["list_price"], Decimal)
        assert Decimal(0) <= row["current_price"] <= row["list_price"]
        assert row["discount_percent"] in {0, 5, 10, 15}
        assert row["current_price"] == (
            row["list_price"] * (Decimal(100 - row["discount_percent"]) / 100)
        ).quantize(Decimal("0.01"))
        assert isinstance(row["stock_quantity"], int) and row["stock_quantity"] >= 0
        assert (row["stock_status"] == "out_of_stock") == (row["stock_quantity"] == 0)
        assert date(row["model_year"], 1, 1) <= row["release_date"] <= AS_OF
        assert 0 <= row["review_count"] <= 500
        assert (row["rating"] is None) == (row["review_count"] == 0)
        if row["rating"] is not None:
            assert Decimal(1) <= row["rating"] <= Decimal(5)
    assert len({row["current_price"] for row in rows}) > 1
    assert len({row["stock_quantity"] for row in rows}) > 1


def test_commercial_derivation_rejects_unsupported_market_and_future_model() -> None:
    package = load_generate_package(PACKAGE)
    selected = select_catalog_row(package, "computers", 42, 0, "balanced")
    with pytest.raises(ValueError, match="unsupported market"):
        derive_computer_row(package, selected, "computers", 42, 0, AS_OF, "xx")
    with pytest.raises(ConfigurationError, match="GENERATION_DATE"):
        derive_computer_row(package, selected, "computers", 42, 0, date(2020, 12, 31))


def test_extended_commerce_obeys_price_sales_and_distribution_rules() -> None:
    package = load_generate_package(PACKAGE)
    rows = [_row(package, index) for index in range(500)]
    for row in rows:
        low = row["lowest_price_30d"]
        high = row["highest_price_30d"]
        average = row["average_price_30d"]
        assert isinstance(low, Decimal)
        assert low <= row["current_price"] <= high <= row["list_price"]
        assert low <= average <= high
        assert Decimal(-100) <= row["price_change_30d_percent"] <= Decimal(100)
        assert (row["promotion_status"] == "active") == (row["discount_percent"] > 0)
        assert (row["promotion_type"] == "none") == (row["discount_percent"] == 0)
        assert row["product_generation"] == (
            "current" if row["product_age_months"] < 12 else
            "previous" if row["product_age_months"] < 36 else "legacy"
        )
        assert isinstance(row["sales_rank"], int) and row["sales_rank"] >= 1
        assert isinstance(row["units_sold_30d"], int) and row["units_sold_30d"] >= 0
        assert Decimal("0.005") <= row["conversion_rate"] <= Decimal("0.15")
        assert Decimal("0.01") <= row["return_rate"] <= Decimal("0.25")
        assert row["shipping_availability"] == (
            "unavailable" if row["stock_quantity"] == 0 else
            "limited" if row["stock_quantity"] < 5 else "available"
        )
        if row["stock_quantity"] == 0:
            assert row["units_sold_30d"] <= 5
        seller = next(entry for entry in package.tables["seller"].rows
                      if entry["id"] == row["seller"])
        warehouse = next(entry for entry in package.tables["warehouse"].rows
                         if entry["id"] == row["warehouse"])
        assert seller["market"] == warehouse["market"] == row["market"]
        assert row["seller_type"] == seller["seller_type_id"]
    assert len({row["promotion_type"] for row in rows}) >= 3
    assert len({row["popularity_level"] for row in rows}) >= 2


def test_extended_commerce_uses_market_currency_and_date_bounded_history() -> None:
    package = load_generate_package(PACKAGE)
    selected = select_catalog_row(package, "computers", 42, 0, "balanced")
    us = derive_computer_row(package, selected, "computers", 42, 0, AS_OF, "us")
    assert us["currency"] == "USD"
    assert us["seller"].endswith("_us")
    assert us["warehouse"].startswith("us_")
    model_year = next(
        row["model_year"] for row in package.tables["model_generation"].rows
        if row["id"] == selected["generation_id"]
    )
    assert type(model_year) is int
    just_released = derive_computer_row(package, selected, "computers", 42, 0,
                                        date(model_year, 1, 1))
    assert just_released["release_date"] == date(model_year, 1, 1)
    assert just_released["lowest_price_30d"] == just_released["current_price"]
    assert just_released["highest_price_30d"] == just_released["current_price"]
    assert just_released["price_change_30d_percent"] == Decimal(0)
