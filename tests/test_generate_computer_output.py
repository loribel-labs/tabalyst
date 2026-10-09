# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Verify localized Computer projections, streaming output, and metadata."""

import csv
import hashlib
import json
import tracemalloc
from datetime import date
from pathlib import Path

import pytest

from tabalyst.generate_computer import derive_computer_row
from tabalyst.generate_computer_output import (
    COMPACT_COLUMNS,
    LABEL_FIELDS,
    render_computer_row,
    write_computer_csvs,
)
from tabalyst.generate_package import load_generate_package
from tabalyst.generate_selection import select_catalog_row

PACKAGE = Path(__file__).resolve().parents[1] / "examples/generate/computer"


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


def test_render_uses_only_declared_labels_and_rejects_later_profiles() -> None:
    package = load_generate_package(PACKAGE)
    selected = select_catalog_row(package, "computers", 42, 0, "balanced")
    internal = derive_computer_row(package, selected, "computers", 42, 0,
                                   date(2026, 9, 30))
    english = render_computer_row(package, internal, "en")
    french = render_computer_row(package, internal, "fr")
    assert english["computer_type"] == "Laptop"
    assert french["computer_type"] == "Portable"
    assert english["sku"] == french["sku"] == internal["sku"]
    assert english["list_price"] == french["list_price"] == str(internal["list_price"])
    for profile in ("standard", "extended", "missing"):
        with pytest.raises(ValueError, match="unsupported Computer output profile"):
            render_computer_row(package, internal, "en", profile)
    with pytest.raises(ValueError, match="unsupported locale"):
        render_computer_row(package, internal, "de")


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
    assert hashlib.sha256(en.read_bytes()).hexdigest() == (
        "7a31eeacdb3d52b003ff18876e6038ea21e975938cb3b62f8ebc343de18cda76"
    )
    assert hashlib.sha256(fr.read_bytes()).hexdigest() == (
        "7454b4b0b86adfa7b4d4ab4fd66dbaf26613bc97ec3a51e62a54dcf83be7dfc5"
    )
    assert b'"Travail mobile, bureau"' in fr.read_bytes()
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
                            tmp_path / "meta.json", rows=count)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peaks.append(peak)
    assert peaks[1] < peaks[0] + 2_000_000


def test_generation_profile_is_effective_in_both_locales(tmp_path: Path) -> None:
    package = load_generate_package(PACKAGE)
    en, fr, meta = (tmp_path / name for name in ("en.csv", "fr.csv", "meta.json"))
    write_computer_csvs(package, {"en": en, "fr": fr}, meta,
                        rows=25, generation_profile="portable_only")
    for path, label in ((en, "Laptop"), (fr, "Portable")):
        with path.open(encoding="utf-8", newline="") as source:
            assert {row["computer_type"] for row in csv.DictReader(source)} == {label}
    assert json.loads(meta.read_text(encoding="utf-8"))["request"][
        "generation_profile"
    ] == "portable_only"
