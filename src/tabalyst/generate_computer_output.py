# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Render Computer rows and stream paired localized development CSVs."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
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
LABEL_FIELDS = {
    "brand": ("brand", "brand_id"),
    "product_family": ("product_family", "product_family_id"),
    "model": ("product_model", "product_model_id"),
    "generation": ("model_generation", "generation_id"),
    "computer_type": ("computer_type", "computer_type_id"),
    "form_factor": ("form_factor", "form_factor_id"),
    "product_segment": ("product_segment", "product_segment_id"),
    "cpu_brand": ("brand", "cpu_brand_id"),
    "gpu_brand": ("brand", "gpu_brand_id"),
    "operating_system": ("operating_system", "operating_system_id"),
    "color": ("color", "color_id"),
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
                        locale: str, profile: str = "compact") -> dict[str, str]:
    """Project one derived row without changing its canonical values.

    Only the compact profile is populated in the first Computer milestone.
    """
    if locale not in {"en", "fr"}:
        raise ValueError(f"unsupported locale {locale!r}")
    if profile != "compact":
        raise ValueError(f"unsupported Computer output profile {profile!r}")
    rendered: dict[str, str] = {}
    for column in COMPACT_COLUMNS:
        if column in LABEL_FIELDS:
            table_id, key = LABEL_FIELDS[column]
            rendered[column] = _label(package, table_id, row[key], locale)
        else:
            if column not in row:
                raise ConfigurationError(f"PACKAGE_OUTPUT: missing Computer field {column!r}")
            rendered[column] = _cell(row[column])
    return rendered


def write_computer_csvs(package: DatasetPackage, outputs: dict[str, Path],
                        metadata_path: Path, *, dataset_id: str = "computers",
                        rows: int = 10, seed: int = 42,
                        as_of_date: date = date(2026, 9, 30),
                        generation_profile: str = "balanced",
                        output_profile: str = "compact", market: str = "ca") -> dict[str, object]:
    """Write paired CSVs and reproducible metadata to caller supplied paths.

    The caller owns path planning, staging, collision checks, and publication.
    One selected and derived record feeds both locale writers per iteration.
    """
    if set(outputs) != {"en", "fr"} or len(set(outputs.values()) | {metadata_path}) != 3:
        raise ValueError("Computer outputs need distinct en, fr, and metadata paths")
    if type(rows) is not int or rows < 1:
        raise ValueError("rows must be positive")
    if output_profile != "compact":
        raise ValueError(f"unsupported Computer output profile {output_profile!r}")
    profiles = package.manifest.get("output_profiles")
    if not isinstance(profiles, dict) or profiles.get("compact") != list(COMPACT_COLUMNS):
        raise ConfigurationError("PACKAGE_OUTPUT: compact profile differs from Computer register")
    with ExitStack() as stack:
        writers: dict[str, csv.DictWriter] = {}
        for locale in ("en", "fr"):
            stream = stack.enter_context(outputs[locale].open("w", encoding="utf-8", newline=""))
            writer = csv.DictWriter(stream, fieldnames=COMPACT_COLUMNS,
                                    extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            writers[locale] = writer
        for index in range(rows):
            selected = select_catalog_row(package, dataset_id, seed, index,
                                          generation_profile)
            internal = derive_computer_row(package, selected, dataset_id, seed,
                                           index, as_of_date, market)
            for locale in ("en", "fr"):
                writers[locale].writerow(render_computer_row(
                    package, internal, locale, output_profile,
                ))
    resources: dict[str, str] = {}
    for path in sorted(package.input_paths):
        with path.open("rb") as stream:
            resources[path.relative_to(package.root).as_posix()] = (
                hashlib.file_digest(stream, "sha256").hexdigest()
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
                    "output_profile": output_profile, "locales": ["en", "fr"],
                    "market": market},
        "outputs": {locale: {"rows": rows, "profile": output_profile,
                             "columns": len(COMPACT_COLUMNS)} for locale in ("en", "fr")},
        "engine_version": __version__,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                                        indent=2) + "\n", encoding="utf-8", newline="\n")
    return metadata
