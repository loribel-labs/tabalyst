# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Render Computer rows and stream paired localized development CSVs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import tempfile
from collections.abc import Callable
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from tabalyst._version import __version__
from tabalyst.errors import ConfigurationError
from tabalyst.generate_computer import derive_computer_row
from tabalyst.generate_selection import select_catalog_row

if TYPE_CHECKING:
    from tabalyst.generate_package import Cell, DatasetPackage

COMPACT_COLUMNS = (
    "product_id", "sku", "brand", "product_family", "model", "generation",
    "model_year", "computer_type", "form_factor", "product_segment",
    "cpu_brand", "cpu_family", "cpu_model", "cpu_cores", "cpu_threads",
    "gpu_brand", "gpu_family", "gpu_model", "gpu_type", "gpu_vram_gb",
    "memory_type", "memory_gb", "storage_type", "storage_gb",
    "display_size_in", "display_type", "display_resolution",
    "display_refresh_rate_hz", "operating_system", "color", "weight_kg",
    "currency", "list_price", "current_price", "stock_quantity",
    "stock_status", "release_date", "rating", "review_count", "market",
)
STANDARD_ADDITIONS = (
    "mpn", "product_category", "product_subcategory", "cpu_architecture",
    "cpu_max_clock_ghz", "display_brightness_nits", "display_touch",
    "display_finish", "os_family", "npu_tops", "ai_pc_class",
    "wifi_standard", "bluetooth_version", "ethernet_speed", "usb_a_ports",
    "usb_c_ports", "hdmi_ports", "battery_wh", "power_adapter_w",
    "chassis_material", "camera_type", "keyboard_layout", "biometric_type",
    "discount_percent", "price_tier", "condition", "warranty_period",
    "product_age_months", "product_lifecycle_status", "language",
)
STANDARD_COLUMNS = (
    "product_id", "sku", "mpn", "brand", "product_family", "model",
    "generation", "model_year", "computer_type", "form_factor",
    "product_segment", "product_category", "product_subcategory",
    "cpu_brand", "cpu_family", "cpu_model", "cpu_architecture", "cpu_cores",
    "cpu_threads", "cpu_max_clock_ghz", "gpu_brand", "gpu_family",
    "gpu_model", "gpu_type", "gpu_vram_gb", "memory_type", "memory_gb",
    "storage_type", "storage_gb", "display_size_in", "display_type",
    "display_resolution", "display_refresh_rate_hz", "display_brightness_nits",
    "display_touch", "display_finish", "os_family", "operating_system",
    "npu_tops", "ai_pc_class", "wifi_standard", "bluetooth_version",
    "ethernet_speed", "usb_a_ports", "usb_c_ports", "hdmi_ports",
    "battery_wh", "power_adapter_w", "color", "weight_kg",
    "chassis_material", "camera_type", "keyboard_layout", "biometric_type",
    "currency", "list_price", "current_price", "discount_percent",
    "price_tier", "condition", "stock_quantity", "stock_status",
    "warranty_period", "release_date", "product_age_months",
    "product_lifecycle_status", "rating", "review_count", "market", "language",
)
EXTENDED_ADDITIONS = (
    "display_aspect_ratio", "display_hdr", "display_color_gamut",
    "npu_brand", "npu_family", "copilot_plus_pc", "cellular_type",
    "docking_support", "thunderbolt_ports", "displayport_ports",
    "ethernet_port", "card_reader_type", "memory_slots_total",
    "memory_slots_used", "m2_slots_total", "m2_slots_used",
    "upgradeability_level", "width_mm", "depth_mm", "height_mm",
    "chassis_finish", "microphone_type", "speaker_configuration",
    "keyboard_type", "trusted_platform",
    "product_generation", "popularity_level", "sales_rank",
    "conversion_rate", "seller_type", "warehouse", "units_sold_30d",
    "return_rate", "seller", "promotion_type", "promotion_status",
    "lowest_price_30d", "highest_price_30d", "average_price_30d",
    "price_change_30d_percent", "shipping_availability",
)
_EXTENDED_AFTER = {
    "display_brightness_nits": ("display_aspect_ratio",),
    "display_finish": ("display_hdr", "display_color_gamut"),
    "operating_system": ("npu_brand", "npu_family"),
    "ai_pc_class": ("copilot_plus_pc",),
    "ethernet_speed": ("cellular_type", "docking_support"),
    "usb_c_ports": ("thunderbolt_ports",),
    "hdmi_ports": (
        "displayport_ports", "ethernet_port", "card_reader_type",
        "memory_slots_total", "memory_slots_used", "m2_slots_total",
        "m2_slots_used", "upgradeability_level",
    ),
    "weight_kg": ("width_mm", "depth_mm", "height_mm"),
    "chassis_material": ("chassis_finish",),
    "camera_type": ("microphone_type", "speaker_configuration", "keyboard_type"),
    "biometric_type": ("trusted_platform",),
    "warranty_period": (
        "promotion_type", "promotion_status", "lowest_price_30d",
        "highest_price_30d", "average_price_30d", "price_change_30d_percent",
    ),
    "product_age_months": ("product_generation",),
    "review_count": (
        "popularity_level", "sales_rank", "units_sold_30d",
        "conversion_rate", "return_rate",
    ),
    "language": ("seller", "seller_type", "warehouse", "shipping_availability"),
}
EXTENDED_COLUMNS = tuple(
    field for column in STANDARD_COLUMNS
    for field in (column, *_EXTENDED_AFTER.get(column, ()))
)
PROFILE_COLUMNS = {
    "compact": COMPACT_COLUMNS,
    "standard": STANDARD_COLUMNS,
    "extended": EXTENDED_COLUMNS,
}
UNIT_COLUMNS: dict[str, tuple[str, str]] = {
    "gpu_vram_gb": ("GB", "Go"),
    "memory_gb": ("GB", "Go"),
    "storage_gb": ("GB", "Go"),
    "cpu_max_clock_ghz": ("GHz", "GHz"),
    "display_size_in": ("in", "po"),
    "display_refresh_rate_hz": ("Hz", "Hz"),
    "display_brightness_nits": ("nits", "nits"),
    "npu_tops": ("TOPS", "TOPS"),
    "battery_wh": ("Wh", "Wh"),
    "power_adapter_w": ("W", "W"),
    "weight_kg": ("kg", "kg"),
    "width_mm": ("mm", "mm"),
    "depth_mm": ("mm", "mm"),
    "height_mm": ("mm", "mm"),
}
LABEL_FIELDS = {
    "brand": ("brand", "brand_id"),
    "product_family": ("product_family", "product_family_id"),
    "model": ("product_model", "product_model_id"),
    "generation": ("model_generation", "generation_id"),
    "computer_type": ("computer_type", "computer_type_id"),
    "form_factor": ("form_factor", "form_factor_id"),
    "product_segment": ("product_segment", "product_segment_id"),
    "product_category": ("product_category", "product_category_id"),
    "product_subcategory": ("product_subcategory", "product_subcategory_id"),
    "cpu_brand": ("brand", "cpu_brand_id"),
    "gpu_brand": ("brand", "gpu_brand_id"),
    "npu_brand": ("brand", "npu_brand"),
    "operating_system": ("operating_system", "operating_system_id"),
    "color": ("color", "color_id"),
    "seller": ("seller", "seller"),
    "seller_type": ("seller_type", "seller_type"),
    "warehouse": ("warehouse", "warehouse"),
    "promotion_type": ("promotion_type", "promotion_type"),
    "promotion_status": ("promotion_status", "promotion_status"),
    "shipping_availability": ("shipping_availability", "shipping_availability"),
}


def _label(package: DatasetPackage, table_id: str, selected_id: Cell,
           locale: str) -> str:
    for entry in package.tables[table_id].rows:
        if entry["id"] == selected_id:
            value = entry.get(locale)
            if isinstance(value, str) and value:
                return value
            raise ConfigurationError(f"PACKAGE_LABEL: missing {locale} label for {table_id} {selected_id!r}")
    raise ConfigurationError(f"PACKAGE_LABEL: unknown {table_id} ID {selected_id!r}")


def _cell(value: Cell) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def render_computer_row(package: DatasetPackage, row: dict[str, Cell],
                        locale: str, profile: str = "compact",
                        unit_style: str = "numeric",
                        unit_columns: tuple[str, ...] | None = None) -> dict[str, str]:
    """Project one derived row without changing its canonical values.

    Each profile includes its predecessor in the canonical register order.
    Localized units apply only to selected measured columns when supplied.
    """
    if locale not in {"en", "fr"}:
        raise ValueError(f"unsupported locale {locale!r}")
    if profile not in PROFILE_COLUMNS:
        raise ValueError(f"unsupported Computer output profile {profile!r}")
    if unit_style not in {"numeric", "localized"}:
        raise ValueError(f"unsupported Computer unit style {unit_style!r}")
    selected_units = unit_columns if unit_columns is not None else tuple(UNIT_COLUMNS)
    rendered: dict[str, str] = {}
    for column in PROFILE_COLUMNS[profile]:
        if column in LABEL_FIELDS:
            table_id, key = LABEL_FIELDS[column]
            rendered[column] = (
                "" if column == "npu_brand" and row[key] is None
                else _label(package, table_id, row[key], locale)
            )
        else:
            if column not in row:
                raise ConfigurationError(f"PACKAGE_OUTPUT: missing Computer field {column!r}")
            value = _cell(row[column])
            if value and unit_style == "localized" and column in selected_units:
                value = f"{value} {UNIT_COLUMNS[column][0 if locale == 'en' else 1]}"
            rendered[column] = value
    return rendered


def _write_rows_in_workers(
    package: DatasetPackage, outputs: dict[str, Path], locales: tuple[str, ...],
    columns: tuple[str, ...], dataset_id: str, rows: int, seed: int, as_of_date: date,
    generation_profile: str, output_profile: str, market: str, unit_style: str,
    selected_units: tuple[str, ...], workers: int, on_rows: Callable[[int], None] | None,
) -> None:
    """Write the CSVs from rows rendered by worker processes."""
    # Imported here because the workers module imports this one.
    from tabalyst.generate_computer_parallel import SpanSettings, write_rows

    header = io.StringIO()
    csv.writer(header, lineterminator="\n").writerow(columns)
    with ExitStack() as stack:
        # The parts sit beside the outputs: millions of rows would fill a small system temp.
        directory = Path(stack.enter_context(tempfile.TemporaryDirectory(
            prefix=".generate-parts-", dir=outputs[locales[0]].parent)))
        streams = {locale: stack.enter_context(outputs[locale].open("wb")) for locale in locales}
        for stream in streams.values():
            stream.write(header.getvalue().encode("utf-8"))
        write_rows(
            SpanSettings(package.root, dataset_id, seed, as_of_date, generation_profile,
                         output_profile, market, unit_style, selected_units, locales,
                         columns, directory),
            rows, workers, streams, on_rows,
        )


def write_computer_csvs(package: DatasetPackage, outputs: dict[str, Path],
                        metadata_path: Path, *, dataset_id: str = "computers",
                        rows: int = 10, seed: int = 42,
                        as_of_date: date = date(2026, 9, 30),
                        generation_profile: str = "balanced",
                        output_profile: str = "compact", market: str = "ca",
                        unit_style: str = "numeric",
                        unit_columns: tuple[str, ...] | None = None,
                        on_rows: Callable[[int], None] | None = None,
                        workers: int = 1) -> dict[str, object]:
    """Write paired CSVs and reproducible metadata to caller supplied paths.

    The caller owns path planning, staging, collision checks, and publication.
    One selected and derived record feeds every requested locale writer per iteration.
    `outputs` holds `en`, `fr` or both; a single locale writes only that file.
    `on_rows` receives the number of rows written, about 200 times and at the end.
    With `workers` above 1 the rows are rendered by that many processes and the
    files are byte for byte those of one process; `on_rows` then moves by span.
    Localized units are recorded with the effective column selection.
    """
    locales = tuple(locale for locale in ("en", "fr") if locale in outputs)
    if (not locales or len(locales) != len(outputs)
            or len(set(outputs.values()) | {metadata_path}) != len(outputs) + 1):
        raise ValueError("Computer outputs need distinct en or fr paths and a metadata path")
    if type(rows) is not int or rows < 1:
        raise ValueError("rows must be positive")
    if output_profile not in PROFILE_COLUMNS:
        raise ValueError(f"unsupported Computer output profile {output_profile!r}")
    if unit_style not in {"numeric", "localized"}:
        raise ValueError(f"unsupported Computer unit style {unit_style!r}")
    profiles = package.manifest.get("output_profiles")
    if not isinstance(profiles, dict) or profiles.get(output_profile) != list(PROFILE_COLUMNS[output_profile]):
        raise ConfigurationError(f"PACKAGE_OUTPUT: {output_profile} profile differs from Computer register")
    columns = PROFILE_COLUMNS[output_profile]
    selected_units = (tuple(column for column in columns if column in UNIT_COLUMNS)
                      if unit_columns is None else unit_columns)
    if (len(set(selected_units)) != len(selected_units)
        or any(column not in columns or column not in UNIT_COLUMNS for column in selected_units)
        or unit_style == "numeric" and unit_columns is not None):
        raise ValueError("invalid Computer unit columns")
    if workers > 1:
        _write_rows_in_workers(package, outputs, locales, columns, dataset_id, rows, seed,
                               as_of_date, generation_profile, output_profile, market,
                               unit_style, selected_units, workers, on_rows)
    else:
        with ExitStack() as stack:
            writers: dict[str, csv.DictWriter] = {}
            for locale in locales:
                stream = stack.enter_context(outputs[locale].open("w", encoding="utf-8", newline=""))
                writer = csv.DictWriter(stream, fieldnames=columns,
                                        extrasaction="raise", lineterminator="\n")
                writer.writeheader()
                writers[locale] = writer
            report_every = max(1, rows // 200)
            for index in range(rows):
                if on_rows is not None and index % report_every == 0:
                    on_rows(index)
                selected = select_catalog_row(package, dataset_id, seed, index,
                                              generation_profile)
                internal = derive_computer_row(package, selected, dataset_id, seed,
                                               index, as_of_date, market)
                for locale in locales:
                    writers[locale].writerow(render_computer_row(
                        package, internal, locale, output_profile, unit_style, selected_units,
                    ))
        if on_rows is not None:
            on_rows(rows)
    resources: dict[str, str] = {}
    for path in sorted(package.input_paths):
        with path.open("rb") as source:
            resources[path.relative_to(package.root).as_posix()] = (
                hashlib.file_digest(source, "sha256").hexdigest()
            )
    metadata: dict[str, object] = {
        "format": "tabalyst.generate.computer.metadata",
        "format_version": "0.1.0",
        "package_id": package.id,
        "package_version": package.package_version,
        "resource_sha256": resources,
        "request": {"dataset": dataset_id, "rows": rows, "seed": seed,
                    "as_of_date": as_of_date.isoformat(),
                    "generation_profile": generation_profile,
                    "output_profile": output_profile, "locales": list(locales),
                    "market": market},
        "outputs": {locale: {"rows": rows, "profile": output_profile,
                             "columns": len(columns)} for locale in locales},
        "engine_version": __version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    if unit_style != "numeric":
        request = metadata["request"]
        assert isinstance(request, dict)
        request["unit_style"] = unit_style
        request["unit_columns"] = list(selected_units)
        metadata["unit_columns"] = {
            column: {"en": suffixes[0], "fr": suffixes[1]}
            for column, suffixes in UNIT_COLUMNS.items() if column in selected_units
        }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                                        indent=2) + "\n", encoding="utf-8", newline="\n")
    return metadata
