# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check Computer joins, stable identities, and synthetic offer invariants."""

from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_computer import derive_computer_row
from tabalyst.generate_package import Cell, DatasetPackage, load_generate_package
from tabalyst.generate_selection import select_catalog_row

PACKAGE = Path(__file__).resolve().parents[1] / "examples/generate/computer"
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
        assert row["storage_gb"] in {512, 1024}
        assert type(row["display_touch"]) is bool


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
        derive_computer_row(package, selected, "computers", 42, 0, date(2025, 12, 31))
