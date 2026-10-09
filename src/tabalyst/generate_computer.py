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


def _integer(value: Cell, field: str) -> int:
    if type(value) is not int:
        raise ConfigurationError(f"PACKAGE_STEP_REFERENCE: expected integer Computer field {field!r}")
    return value


def _number(value: Cell, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        raise ConfigurationError(f"PACKAGE_STEP_REFERENCE: expected numeric Computer field {field!r}")
    return Decimal(value)


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
    segment = _entry(package, "product_segment", values["product_segment_id"])
    subcategory = _entry(package, "product_subcategory", segment["product_subcategory_id"])
    standard_specs = _entry(package, "standard_specs", values["generation_id"])
    extended_specs = _entry(package, "extended_specs", values["generation_id"])
    if (family["brand_id"] != values["brand_id"]
            or model["product_family_id"] != values["product_family_id"]
            or generation["product_model_id"] != values["product_model_id"]):
        raise ConfigurationError("PACKAGE_STEP_REFERENCE: inconsistent Computer hierarchy")
    if ((values["computer_type_id"] == "laptop") != (standard_specs["battery_wh"] is not None)
            or (values["computer_type_id"] == "desktop" and standard_specs["camera_type"] != "none")):
        raise ConfigurationError("PACKAGE_STEP_REFERENCE: inconsistent Computer power or camera specification")
    npu_tops = _integer(cpu["npu_tops"], "npu_tops")
    if (cpu["npu_brand"] is None) != (npu_tops == 0) or (
        (cpu["npu_family"] is None) != (npu_tops == 0)
    ):
        raise ConfigurationError("PACKAGE_STEP_REFERENCE: inconsistent Computer NPU specification")
    if (_integer(extended_specs["memory_slots_used"], "memory_slots_used")
            > _integer(extended_specs["memory_slots_total"], "memory_slots_total")
            or _integer(extended_specs["m2_slots_used"], "m2_slots_used")
            > _integer(extended_specs["m2_slots_total"], "m2_slots_total")
            or (extended_specs["ethernet_port"] != (standard_specs["ethernet_speed"] != "none"))
            or (values["computer_type_id"] == "laptop"
                and (_number(extended_specs["height_mm"], "height_mm") >= 50
                     or extended_specs["keyboard_type"] != "integrated"))
            or (values["computer_type_id"] == "desktop"
                and (extended_specs["cellular_type"] != "none"
                     or extended_specs["keyboard_type"] != "external"))):
        raise ConfigurationError("PACKAGE_STEP_REFERENCE: inconsistent Computer extended specification")
    values.update({
        "model_year": generation["model_year"],
        "product_subcategory_id": subcategory["id"],
        "product_category_id": subcategory["product_category_id"],
        "cpu_brand_id": cpu["brand_id"], "cpu_family": cpu["family"],
        "cpu_model": cpu["model"],
        "cpu_architecture": cpu["architecture"],
        "cpu_cores": cpu["cores"], "cpu_threads": cpu["threads"],
        "cpu_max_clock_ghz": cpu["max_clock_ghz"],
        "npu_tops": cpu["npu_tops"],
        "npu_brand": cpu["npu_brand"], "npu_family": cpu["npu_family"],
        "gpu_brand_id": gpu["brand_id"], "gpu_family": gpu["family"],
        "gpu_model": gpu["model"],
        "gpu_type": gpu["gpu_type"], "gpu_vram_gb": gpu["vram_gb"],
        "memory_type": memory["memory_type"], "memory_gb": memory["capacity_gb"],
        "storage_type": storage["storage_type"], "storage_gb": storage["capacity_gb"],
        "display_size_in": display["size_in"], "display_type": display["display_type"],
        "display_touch": display["touch"],
        "display_brightness_nits": display["brightness_nits"],
        "display_finish": display["finish"],
        "display_aspect_ratio": display["aspect_ratio"],
        "display_hdr": display["hdr"],
        "display_color_gamut": display["color_gamut"],
        "display_resolution": display["resolution"],
        "display_refresh_rate_hz": display["refresh_rate_hz"],
        "os_family": operating_system["os_family"],
        "wifi_standard": standard_specs["wifi_standard"],
        "bluetooth_version": standard_specs["bluetooth_version"],
        "ethernet_speed": standard_specs["ethernet_speed"],
        "usb_a_ports": standard_specs["usb_a_ports"],
        "usb_c_ports": standard_specs["usb_c_ports"],
        "hdmi_ports": standard_specs["hdmi_ports"],
        "battery_wh": standard_specs["battery_wh"],
        "power_adapter_w": standard_specs["power_adapter_w"],
        "chassis_material": standard_specs["chassis_material"],
        "camera_type": standard_specs["camera_type"],
        "biometric_type": standard_specs["biometric_type"],
        "warranty_period": standard_specs["warranty_period"],
        "copilot_plus_pc": npu_tops >= 40,
        "keyboard_layout": "ca_multilingual" if market == "ca" else "us_english",
        "language": "en_fr" if market == "ca" else "en",
        "ai_pc_class": "npu_capable" if _integer(cpu["npu_tops"], "npu_tops") >= 40 else "none",
    })
    for field in (
        "cellular_type", "docking_support", "thunderbolt_ports",
        "displayport_ports", "ethernet_port", "card_reader_type",
        "memory_slots_total", "memory_slots_used", "m2_slots_total",
        "m2_slots_used", "upgradeability_level", "width_mm", "depth_mm",
        "height_mm", "chassis_finish", "microphone_type",
        "speaker_configuration", "keyboard_type", "trusted_platform",
    ):
        values[field] = extended_specs[field]
    configuration = tuple(str(values[field]) for field in CONFIGURATION_PARTS)
    variant = tuple(str(values[field]) for field in VARIANT_PARTS)
    values["configuration_id"] = "cfg_" + _digest(configuration)
    values["variant_id"] = "var_" + _digest(variant)
    values["sku"] = "SKU-" + _digest(variant).upper()
    values["mpn"] = "MPN-" + _digest((str(values["brand_id"]), *variant)).upper()
    values["product_id"] = "prd_" + _digest((dataset_id, str(seed), str(row_index)))

    # Offer values are synthetic; their rules encode consistency, not market estimates.
    context = (str(values["variant_id"]), market, as_of_date.isoformat())
    base = (450 + 15 * _integer(values["memory_gb"], "memory_gb")
            + _integer(values["storage_gb"], "storage_gb") // 4
            + 75 * _integer(values["cpu_cores"], "cpu_cores")
            + 20 * _integer(values["gpu_vram_gb"], "gpu_vram_gb"))
    currency_factor = Decimal("1.00") if market == "ca" else Decimal("0.75")
    price_rng = _stream(seed, dataset_id, row_index, "price", context)
    list_price = (Decimal(base + price_rng.randrange(0, 6) * 25) * currency_factor).quantize(Decimal("0.01"))
    discount_percent = _stream(seed, dataset_id, row_index, "discount", context).choice((0, 0, 5, 10, 15))
    current_price = (list_price * (Decimal(100 - discount_percent) / 100)).quantize(Decimal("0.01"))
    stock = _stream(seed, dataset_id, row_index, "stock", context).randrange(0, 51)
    year = _integer(values["model_year"], "model_year")
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
    age_months = ((as_of_date.year - release.year) * 12 + as_of_date.month
                  - release.month - (as_of_date.day < release.day))
    values.update({
        "list_price": list_price, "current_price": current_price,
        "discount_percent": discount_percent,
        "price_tier": ("entry" if list_price < Decimal(1500) * currency_factor
                       else "premium"),
        "condition": "new",
        "stock_quantity": stock,
        "stock_status": "out_of_stock" if stock == 0 else "in_stock",
        "release_date": release, "rating": rating, "review_count": review_count,
        "product_age_months": age_months,
        "product_lifecycle_status": "current" if age_months < 24 else "mature",
        "weight_kg": Decimal("1.8") if values["computer_type_id"] == "laptop" else Decimal("7.5"),
    })
    # A short synthetic history gives the extrema and change the same source.
    history_rng = _stream(seed, dataset_id, row_index, "price_history", context)
    history: list[Decimal] = [current_price]
    if (as_of_date - release).days >= 30:
        for _ in range(2):
            past_discount = history_rng.choice((0, 5, 10, 15))
            history.append((list_price * Decimal(100 - past_discount) / 100).quantize(Decimal("0.01")))
    prior_price = history[-1]
    price_change = ((current_price / prior_price - 1) * 100).quantize(Decimal("0.01"))
    sales_rng = _stream(seed, dataset_id, row_index, "sales", context)
    units_sold = (sales_rng.randrange(0, 6) if stock == 0
                  else review_count // 3 + sales_rng.randrange(0, 61))
    rating_value = rating if rating is not None else Decimal("3.5")
    conversion = (Decimal("0.02") + (rating_value - 3) * Decimal("0.012")
                  + Decimal(discount_percent) * Decimal("0.001"))
    if stock == 0:
        conversion = Decimal("0.005")
    conversion = min(Decimal("0.15"), max(Decimal("0.005"), conversion)).quantize(Decimal("0.001"))
    return_rate = (Decimal("0.10") - (rating_value - 3) * Decimal("0.02")
                   + Decimal(_stream(seed, dataset_id, row_index, "returns", context).randrange(0, 6))
                   / 1000).quantize(Decimal("0.001"))
    seller_id = _stream(seed, dataset_id, row_index, "seller", context).choice(
        ("ca_direct", "ca_retail") if market == "ca" else ("us_direct", "us_retail")
    )
    seller = _entry(package, "seller", seller_id)
    warehouse_id = _stream(seed, dataset_id, row_index, "warehouse", context).choice(
        ("ca_east", "ca_west") if market == "ca" else ("us_east", "us_west")
    )
    warehouse = _entry(package, "warehouse", warehouse_id)
    if seller["market"] != market or warehouse["market"] != market:
        raise ConfigurationError("PACKAGE_STEP_REFERENCE: inconsistent Computer distribution market")
    promotion_type = ("none" if discount_percent == 0 else
                      _stream(seed, dataset_id, row_index, "promotion", context).choice(
                          ("price_cut", "seasonal", "clearance")))
    values.update({
        "product_generation": ("current" if age_months < 12 else
                               "previous" if age_months < 36 else "legacy"),
        "popularity_level": ("high" if units_sold >= 100 else
                             "medium" if units_sold >= 30 else "low"),
        "sales_rank": max(1, 100000 - units_sold * 200 + sales_rng.randrange(0, 200)),
        "conversion_rate": conversion,
        "seller_type": seller["seller_type_id"], "warehouse": warehouse_id,
        "units_sold_30d": units_sold, "return_rate": return_rate,
        "seller": seller_id, "promotion_type": promotion_type,
        "promotion_status": "none" if discount_percent == 0 else "active",
        "lowest_price_30d": min(history), "highest_price_30d": max(history),
        "average_price_30d": (sum(history, Decimal(0)) / Decimal(len(history))).quantize(Decimal("0.01")),
        "price_change_30d_percent": price_change,
        "shipping_availability": ("unavailable" if stock == 0 else
                                  "limited" if stock < 5 else "available"),
    })
    return values
