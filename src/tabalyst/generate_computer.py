# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Derive Computer specifications, identities, and synthetic offer values."""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from tabalyst.errors import ConfigurationError
from tabalyst.generate_package import Cell

if TYPE_CHECKING:
    from tabalyst.generate_package import DatasetPackage

CONFIGURATION_PARTS = (
    "generation_id", "cpu_id", "gpu_id", "memory_id", "storage_id", "display_id",
)
VARIANT_PARTS = (*CONFIGURATION_PARTS, "color_id", "operating_system_id", "market")
MARKET_CURRENCY = {"ca": "CAD", "us": "USD"}


def _digest(parts: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for part in parts:
        encoded = part.encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()[:40]


def _stream(seed: int, dataset_id: str, row_index: int, decision: str,
            context: tuple[str, ...]) -> random.Random:
    return random.Random(int(_digest((str(seed), dataset_id, str(row_index), decision, *context)), 16))


def _entry(package: DatasetPackage, table_id: str, selected_id: Cell) -> dict[str, Cell]:
    matches = [row for row in package.tables[table_id].rows if row["id"] == selected_id]
    if len(matches) != 1:
        raise ConfigurationError(f"PACKAGE_STEP_REFERENCE: unknown {table_id} ID {selected_id!r}")
    return matches[0]


def derive_computer_row(package: DatasetPackage, selected: dict[str, Cell],
                        dataset_id: str, seed: int, row_index: int, as_of_date: date,
                        market: str = "ca") -> dict[str, Cell]:
    """Enrich one selected row without rendering localized labels or CSV.

    The selected IDs and fixed request determine every value. Commercial draws
    use separate streams so unrelated later fields cannot shift existing values.
    """
    if type(seed) is not int or type(row_index) is not int or row_index < 0:
        raise ValueError("seed must be an integer and row_index must be nonnegative")
    if type(as_of_date) is not date:
        raise ValueError("as_of_date must be a date")
    if market not in MARKET_CURRENCY:
        raise ValueError(f"unsupported market {market!r}")
    values = {**selected, "market": market, "currency": MARKET_CURRENCY[market]}
    for field in VARIANT_PARTS:
        if field not in values or not isinstance(values[field], str):
            raise ConfigurationError(f"PACKAGE_STEP_REFERENCE: missing Computer ID {field!r}")
    cpu = _entry(package, "cpu", values["cpu_id"])
    gpu = _entry(package, "gpu", values["gpu_id"])
    memory = _entry(package, "memory", values["memory_id"])
    storage = _entry(package, "storage", values["storage_id"])
    display = _entry(package, "display", values["display_id"])
    operating_system = _entry(package, "operating_system", values["operating_system_id"])
    family = _entry(package, "product_family", values["product_family_id"])
    model = _entry(package, "product_model", values["product_model_id"])
    generation = _entry(package, "model_generation", values["generation_id"])
    if (family["brand_id"] != values["brand_id"]
            or model["product_family_id"] != values["product_family_id"]
            or generation["product_model_id"] != values["product_model_id"]):
        raise ConfigurationError("PACKAGE_STEP_REFERENCE: inconsistent Computer hierarchy")
    values.update({
        "model_year": generation["model_year"],
        "cpu_brand_id": cpu["brand_id"], "cpu_family": cpu["family"],
        "cpu_model": cpu["model"],
        "cpu_cores": cpu["cores"], "cpu_threads": cpu["threads"],
        "gpu_brand_id": gpu["brand_id"], "gpu_family": gpu["family"],
        "gpu_model": gpu["model"],
        "gpu_type": gpu["gpu_type"], "gpu_vram_gb": gpu["vram_gb"],
        "memory_type": memory["memory_type"], "memory_gb": memory["capacity_gb"],
        "storage_type": storage["storage_type"], "storage_gb": storage["capacity_gb"],
        "display_size_in": display["size_in"], "display_type": display["display_type"],
        "display_touch": display["touch"],
        "display_resolution": display["resolution"],
        "display_refresh_rate_hz": display["refresh_rate_hz"],
        "os_family": operating_system["os_family"],
    })
    configuration = tuple(str(values[field]) for field in CONFIGURATION_PARTS)
    variant = tuple(str(values[field]) for field in VARIANT_PARTS)
    values["configuration_id"] = "cfg_" + _digest(configuration)
    values["variant_id"] = "var_" + _digest(variant)
    values["sku"] = "SKU-" + _digest(variant).upper()
    values["mpn"] = "MPN-" + _digest((str(values["brand_id"]), *variant)).upper()
    values["product_id"] = "prd_" + _digest((dataset_id, str(seed), str(row_index)))

    # Offer values are synthetic; their rules encode consistency, not market estimates.
    context = (str(values["variant_id"]), market, as_of_date.isoformat())
    base = (450 + 15 * int(values["memory_gb"]) + int(values["storage_gb"]) // 4
            + 75 * int(values["cpu_cores"]) + 20 * int(values["gpu_vram_gb"]))
    currency_factor = Decimal("1.00") if market == "ca" else Decimal("0.75")
    price_rng = _stream(seed, dataset_id, row_index, "price", context)
    list_price = (Decimal(base + price_rng.randrange(0, 6) * 25) * currency_factor).quantize(Decimal("0.01"))
    discount_percent = _stream(seed, dataset_id, row_index, "discount", context).choice((0, 0, 5, 10, 15))
    current_price = (list_price * (Decimal(100 - discount_percent) / 100)).quantize(Decimal("0.01"))
    stock = _stream(seed, dataset_id, row_index, "stock", context).randrange(0, 51)
    year = int(values["model_year"])
    release = date(year, 1, 1)
    if release > as_of_date:
        raise ConfigurationError("GENERATION_DATE: model year is after as_of_date")
    release += timedelta(days=_stream(seed, dataset_id, row_index, "release", context).randrange(
        min(365, (as_of_date - release).days + 1)
    ))
    review_count = _stream(seed, dataset_id, row_index, "reviews", context).randrange(0, 501)
    rating: Decimal | None = None
    if review_count:
        rating = Decimal(_stream(seed, dataset_id, row_index, "rating", context).randrange(30, 51)) / 10
    values.update({
        "list_price": list_price, "current_price": current_price,
        "discount_percent": discount_percent,
        "stock_quantity": stock,
        "stock_status": "out_of_stock" if stock == 0 else "in_stock",
        "release_date": release, "rating": rating, "review_count": review_count,
        "weight_kg": Decimal("1.8") if values["computer_type_id"] == "laptop" else Decimal("7.5"),
    })
    return values
