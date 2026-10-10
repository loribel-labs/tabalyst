# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Verify localized Computer projections, streaming output, and metadata."""

import csv
import hashlib
import json
import re
import tracemalloc
from datetime import date
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.generate_computer import derive_computer_row
from tabalyst.generate_computer_output import (
    COMPACT_COLUMNS,
    EXTENDED_ADDITIONS,
    EXTENDED_COLUMNS,
    LABEL_FIELDS,
    STANDARD_ADDITIONS,
    STANDARD_COLUMNS,
    render_computer_row,
    write_computer_csvs,
)
from tabalyst.generate_package import load_generate_package
from tabalyst.generate_selection import select_catalog_row

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "computer")))


def _write(directory: Path, rows: int = 10) -> tuple[Path, Path, Path]:
    package = load_generate_package(PACKAGE)
    en, fr, meta = (directory / name for name in ("en.csv", "fr.csv", "meta.json"))
    write_computer_csvs(package, {"en": en, "fr": fr}, meta, rows=rows)
    return en, fr, meta


def test_compact_profiles_align_locales_and_keep_canonical_values(tmp_path: Path) -> None:
    en, fr, _ = _write(tmp_path)
    with en.open(encoding="utf-8", newline="") as source:
        english = list(csv.DictReader(source))
    with fr.open(encoding="utf-8", newline="") as source:
        french = list(csv.DictReader(source))
    assert len(english) == len(french) == 10
    assert tuple(english[0]) == tuple(french[0]) == COMPACT_COLUMNS
    for left, right in zip(english, french, strict=True):
        for field in COMPACT_COLUMNS:
            if field not in LABEL_FIELDS:
                assert left[field] == right[field]
    assert any(left["computer_type"] != right["computer_type"]
               for left, right in zip(english, french, strict=True))
    assert [row["product_id"] for row in english] == [row["product_id"] for row in french]


def test_render_uses_only_declared_labels_and_rejects_unavailable_profiles() -> None:
    package = load_generate_package(PACKAGE)
    selected = select_catalog_row(package, "computers", 42, 0, "balanced")
    internal = derive_computer_row(package, selected, "computers", 42, 0,
                                   date(2026, 9, 30))
    english = render_computer_row(package, internal, "en")
    french = render_computer_row(package, internal, "fr")
    kind = next(row for row in package.tables["computer_type"].rows
                if row["id"] == selected["computer_type_id"])
    assert english["computer_type"] == kind["en"]
    assert french["computer_type"] == kind["fr"]
    assert english["sku"] == french["sku"] == internal["sku"]
    assert english["list_price"] == french["list_price"] == str(internal["list_price"])
    for profile in ("missing",):
        with pytest.raises(ValueError, match="unsupported Computer output profile"):
            render_computer_row(package, internal, "en", profile)
    with pytest.raises(ValueError, match="unsupported locale"):
        render_computer_row(package, internal, "de")


def test_standard_profile_preserves_register_order_types_and_locale_alignment(tmp_path: Path) -> None:
    package = load_generate_package(PACKAGE)
    contract = (Path(__file__).resolve().parents[1] / "docs/dev/generate/computer.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n([^`]+)\n```", contract)
    compact_register, additions_register, _, complete_register = (
        tuple(block.strip().split(",")) for block in blocks[-4:]
    )
    assert compact_register == COMPACT_COLUMNS
    assert additions_register == STANDARD_ADDITIONS
    assert tuple(field for field in complete_register if field in set(STANDARD_COLUMNS)) == STANDARD_COLUMNS
    assert len(COMPACT_COLUMNS) == 40
    assert len(STANDARD_ADDITIONS) == 30
    assert len(STANDARD_COLUMNS) == 70
    assert set(STANDARD_COLUMNS) == set(COMPACT_COLUMNS) | set(STANDARD_ADDITIONS)
    assert package.manifest["output_profiles"]["standard"] == list(STANDARD_COLUMNS)
    en, fr, meta = (tmp_path / name for name in ("en.csv", "fr.csv", "meta.json"))
    write_computer_csvs(package, {"en": en, "fr": fr}, meta,
                        rows=100, output_profile="standard")
    with en.open(encoding="utf-8", newline="") as stream:
        english = list(csv.DictReader(stream))
    with fr.open(encoding="utf-8", newline="") as stream:
        french = list(csv.DictReader(stream))
    assert len(english) == len(french) == 100
    assert tuple(english[0]) == tuple(french[0]) == STANDARD_COLUMNS
    for left, right in zip(english, french, strict=True):
        assert all(left[field] == right[field] for field in STANDARD_COLUMNS
                   if field not in LABEL_FIELDS)
        assert left["product_category"] in {
            str(row["en"]) for row in package.tables["product_category"].rows
        }
        assert right["product_category"] in {
            str(row["fr"]) for row in package.tables["product_category"].rows
        }
        assert left["language"] == right["language"] == "en_fr"
        assert left["display_touch"] in {"true", "false"}
        assert int(left["npu_tops"]) >= 0
        assert float(left["cpu_max_clock_ghz"]) >= 1
        if left["computer_type"] in {"Laptop", "All-in-One"}:
            assert int(left["display_brightness_nits"]) > 0
        else:
            assert left["display_brightness_nits"] == ""
        assert int(left["product_age_months"]) >= 0
        assert left["ai_pc_class"] == ("npu_capable" if int(left["npu_tops"]) >= 40 else "none")
        assert left["current_price"] == right["current_price"]
        if left["computer_type"] == "Laptop":
            assert left["battery_wh"] and left["camera_type"] != "none"
        else:
            assert left["battery_wh"] == ""
            if left["computer_type"] != "All-in-One":
                assert left["camera_type"] == "none"
    assert json.loads(meta.read_text(encoding="utf-8"))["outputs"]["en"]["columns"] == 70


def test_standard_keeps_every_compact_cell_for_the_same_request(tmp_path: Path) -> None:
    package = load_generate_package(PACKAGE)
    for profile in ("compact", "standard"):
        paths = {locale: tmp_path / f"{profile}-{locale}.csv" for locale in ("en", "fr")}
        write_computer_csvs(package, paths, tmp_path / f"{profile}.json",
                            rows=10, output_profile=profile)
    for locale in ("en", "fr"):
        with (tmp_path / f"compact-{locale}.csv").open(encoding="utf-8", newline="") as source:
            compact = list(csv.DictReader(source))
        with (tmp_path / f"standard-{locale}.csv").open(encoding="utf-8", newline="") as source:
            standard = list(csv.DictReader(source))
        for left, right in zip(compact, standard, strict=True):
            assert left == {field: right[field] for field in COMPACT_COLUMNS}


def test_extended_hardware_profile_follows_register_and_aligns_locales(tmp_path: Path) -> None:
    package = load_generate_package(PACKAGE)
    contract = (Path(__file__).resolve().parents[1] / "docs/dev/generate/computer.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n([^`]+)\n```", contract)
    _, _, extended_register, complete_register = (
        tuple(block.strip().split(",")) for block in blocks[-4:]
    )
    assert EXTENDED_ADDITIONS == extended_register[:len(EXTENDED_ADDITIONS)]
    assert len(EXTENDED_COLUMNS) == 111
    assert set(EXTENDED_COLUMNS) == set(STANDARD_COLUMNS) | set(EXTENDED_ADDITIONS)
    assert tuple(field for field in complete_register if field in set(EXTENDED_COLUMNS)) == EXTENDED_COLUMNS
    profiles = package.manifest["output_profiles"]
    assert isinstance(profiles, dict)
    assert profiles["extended"] == list(EXTENDED_COLUMNS)
    for profile in ("standard", "extended"):
        paths = {locale: tmp_path / f"{profile}-{locale}.csv" for locale in ("en", "fr")}
        write_computer_csvs(package, paths, tmp_path / f"{profile}.json",
                            rows=100, output_profile=profile)
    for locale in ("en", "fr"):
        with (tmp_path / f"standard-{locale}.csv").open(encoding="utf-8", newline="") as source:
            standard = list(csv.DictReader(source))
        with (tmp_path / f"extended-{locale}.csv").open(encoding="utf-8", newline="") as source:
            extended = list(csv.DictReader(source))
        assert tuple(extended[0]) == EXTENDED_COLUMNS
        for left, right in zip(standard, extended, strict=True):
            assert left == {field: right[field] for field in STANDARD_COLUMNS}
    with (tmp_path / "extended-en.csv").open(encoding="utf-8", newline="") as source:
        english = list(csv.DictReader(source))
    with (tmp_path / "extended-fr.csv").open(encoding="utf-8", newline="") as source:
        french = list(csv.DictReader(source))
    for left, right in zip(english, french, strict=True):
        assert all(left[field] == right[field] for field in EXTENDED_COLUMNS
                   if field not in LABEL_FIELDS)
        assert left["copilot_plus_pc"] == ("true" if int(left["npu_tops"]) >= 40 else "false")
        assert left["display_hdr"] in {
            "", "none", "hdr10", "displayhdr_400", "displayhdr_1000",
            "true_black_500",
        }
        assert left["docking_support"] in {
            "none", "usb_c", "thunderbolt", "thunderbolt_4",
        }
        assert left["ethernet_port"] == ("false" if left["ethernet_speed"] == "none" else "true")
        assert 0 <= int(left["memory_slots_used"]) <= int(left["memory_slots_total"])
        assert 0 <= int(left["m2_slots_used"]) <= int(left["m2_slots_total"])
        assert all(float(left[field]) > 0 for field in ("width_mm", "depth_mm", "height_mm"))
        if left["computer_type"] == "Laptop":
            assert left["keyboard_type"] in {
                "backlit_chiclet", "backlit_gaming", "detachable_keyboard",
            }
            assert float(left["height_mm"]) < 50
        elif left["computer_type"] == "Desktop":
            assert left["cellular_type"] == "none"
            assert left["keyboard_type"] in {
                "external_keyboard", "professional_keyboard", "mechanical_keyboard",
            }
        assert left["seller"] and right["seller"]
        assert left["warehouse"] != right["warehouse"]
        assert left["shipping_availability"] != right["shipping_availability"]
    assert {row["computer_type"] for row in english} >= {
        "Laptop", "Desktop", "All-in-One", "Mini PC", "Server",
    }
    assert {row["npu_brand"] for row in english} <= {
        "", "AMD", "Apple", "Intel",
    }


def test_csv_bytes_and_metadata_are_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_paths = _write(first)
    second_paths = _write(second)
    for left, right in zip(first_paths, second_paths, strict=True):
        assert left.read_bytes() == right.read_bytes()
    en, fr, meta = first_paths
    assert b"\r\n" not in en.read_bytes()
    assert b"\r\n" not in fr.read_bytes()
    assert en.read_bytes().startswith(b"product_id,sku,brand,")
    assert hashlib.sha256(en.read_bytes()).hexdigest() != hashlib.sha256(
        fr.read_bytes()
    ).hexdigest()
    assert "Écran" not in en.read_text(encoding="utf-8")
    metadata = json.loads(meta.read_text(encoding="utf-8"))
    assert metadata["request"] == {
        "dataset": "computers", "rows": 10, "seed": 42,
        "as_of_date": "2026-09-30", "generation_profile": "balanced",
        "output_profile": "compact", "locales": ["en", "fr"], "market": "ca",
    }
    assert metadata["outputs"]["en"] == {"rows": 10, "profile": "compact", "columns": 40}
    assert metadata["resource_sha256"]["dataset.yaml"] == hashlib.sha256(
        (PACKAGE / "dataset.yaml").read_bytes(),
    ).hexdigest()
    assert all(len(value) == 64 for value in metadata["resource_sha256"].values())


def test_streaming_memory_does_not_scale_with_row_count(tmp_path: Path) -> None:
    package = load_generate_package(PACKAGE)
    peaks = []
    for count in (10, 1000):
        tracemalloc.start()
        write_computer_csvs(package, {"en": tmp_path / "en.csv",
                                      "fr": tmp_path / "fr.csv"},
                            tmp_path / "meta.json", rows=count,
                            output_profile="extended")
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak)
    assert peaks[1] < peaks[0] + 2_000_000


def test_generation_profile_is_effective_in_both_locales(tmp_path: Path) -> None:
    package = load_generate_package(PACKAGE)
    en, fr, meta = (tmp_path / name for name in ("en.csv", "fr.csv", "meta.json"))
    write_computer_csvs(package, {"en": en, "fr": fr}, meta,
                        rows=25, generation_profile="portable_only")
    for path, label in ((en, "Laptop"), (fr, "Ordinateur portable")):
        with path.open(encoding="utf-8", newline="") as source:
            assert {row["computer_type"] for row in csv.DictReader(source)} == {label}
    assert json.loads(meta.read_text(encoding="utf-8"))["request"][
        "generation_profile"
    ] == "portable_only"
