# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check the building blocks of the ``rare_events`` profile of Insurance V2 (contract 6)."""

from __future__ import annotations

import csv
import random
import shutil
from importlib.resources import files
from pathlib import Path
from typing import cast

import pytest
import yaml

from tabalyst.errors import ConfigurationError
from tabalyst.generate_anomalies import (
    FORMAT_VALUES,
    TEXT_TRANSFORMS,
    AnomalyEvent,
    inject_anomalies,
    operation_option_error,
)
from tabalyst.generate_insurance import insurance_contextual
from tabalyst.generate_references import CommonReferences
from tabalyst.generate_service import validate_generate_package

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))


def _transform(name: str, value: str) -> str:
    return TEXT_TRANSFORMS[name](value, random.Random(0))


@pytest.mark.parametrize(("value", "expected"), [
    ("95.40", "9540.00"), ("1076.00", "107600.00"), ("0.05", "5.00"), ("N/A", "N/A"),
    ("-12.00", "-12.00"), ("", ""),
])
def test_times_100_moves_the_decimal_point_two_places_and_leaves_other_text(
        value: str, expected: str) -> None:
    assert "times_100" in FORMAT_VALUES
    assert _transform("times_100", value) == expected


@pytest.mark.parametrize(("value", "expected"), [
    ("1981-07-01", "2081-07-01"),      # ISO, the year first
    ("07-01-1981", "07-01-2081"),      # day or month first: the year is last, the rest stays
    ("29-02-2000", "28-02-2100"),      # 2100 has no 29 February (day first)
    ("02-29-2000", "02-28-2100"),      # and the same in month-first order
    ("2000-02-29", "2100-02-28"),
    ("1976-02-29", "2076-02-29"),      # 2076 is a leap year, the day stays
    ("not a date", "not a date"),
])
def test_date_plus_century_moves_the_year_in_every_branch_order(value: str, expected: str) -> None:
    assert "date_plus_century" in FORMAT_VALUES
    assert _transform("date_plus_century", value) == expected


def _write(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    clean = tmp_path / "clean.csv"
    with clean.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return clean


def _operation(kind: str, column: str, count: int, **extra: object) -> dict[str, object]:
    return {"kind": kind, "column": column, "count": count, "scenario_id": "S",
            "category": "business_rule_violation", "severity": "major", **extra}


def _run(tmp_path: Path, rows: list[dict[str, str]], operation: dict[str, object],
         ) -> tuple[list[dict[str, str]], list[AnomalyEvent], dict[str, object]]:
    events: list[AnomalyEvent] = []
    summary = inject_anomalies(
        _write(tmp_path, rows), tmp_path / "altered.csv", tmp_path / "changes.csv",
        dataset="demo", profile={"id": "p", "operations": [operation]}, seed=3,
        count=len(rows), delimiter=",", on_event=events.append)
    with (tmp_path / "altered.csv").open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream)), events, summary


def test_reuse_value_repeats_the_key_of_an_earlier_row_and_names_that_row(
        tmp_path: Path) -> None:
    rows = [{"id": f"K{i:04d}", "v": str(i)} for i in range(200)]
    altered, events, summary = _run(tmp_path, rows, _operation("reuse_value", "id", 4))
    assert len(events) == 4
    for event in events:
        assert 2 <= event.related_row < event.row_number
        assert altered[event.row_number - 2]["id"] == altered[event.related_row - 2]["id"]
        # The canonical value is the key the row had: the truth can restore it.
        assert event.canonical_value == rows[event.row_number - 2]["id"] != event.after
        assert event.before == rows[event.row_number - 2]["id"]
    operations = cast("list[dict[str, object]]", summary["operations"])
    assert operations[0]["applied_rows"] == 4
    journal = (tmp_path / "changes.csv").read_text(encoding="utf-8")
    assert journal.count("reused_from_row=") == 4


def test_reuse_value_only_reaches_back_a_window_of_rows(tmp_path: Path) -> None:
    rows = [{"id": f"K{i:05d}"} for i in range(3000)]
    _, events, _ = _run(tmp_path, rows, _operation("reuse_value", "id", 200))
    assert all(0 < event.row_number - event.related_row <= 1000 for event in events)


def test_reuse_value_takes_no_value_option() -> None:
    assert operation_option_error(_operation("reuse_value", "id", 1, value="x")) == (
        "operation.value is unused for this kind")


def test_copy_column_writes_the_value_of_another_cell_only_where_both_are_present(
        tmp_path: Path) -> None:
    rows = [{"end": "2025-02-02" if i % 4 else "", "start": "2025-01-01" if i % 5 else "2025-02-02"}
            for i in range(40)]
    eligible = sum(1 for row in rows if row["end"] and row["start"] and row["end"] != row["start"])
    altered, events, _ = _run(tmp_path, rows, _operation(
        "copy_column", "end", 6, value="start", category="valid_atypical", severity="info",
        expected_detection="none"))
    assert len(events) == 6 <= eligible
    for event in events:
        row = altered[event.row_number - 2]
        assert row["end"] == row["start"] != event.before


def test_a_contextual_value_needs_its_provider(tmp_path: Path) -> None:
    rows = [{"code": "H2X 1Y4", "province_code": "QC"}] * 20
    operation = _operation("format", "code", 2, value="postal_other_province")
    with pytest.raises(ValueError, match="postal_other_province needs the row context"):
        _run(tmp_path, rows, operation)


@pytest.fixture(scope="module")
def contextual() -> dict[str, object]:
    return cast("dict[str, object]", insurance_contextual(CommonReferences()))


@pytest.mark.parametrize(("province", "postal"), [("QC", "H2X 1Y4"), ("ON", "M5V 2T6"),
                                                  ("BC", "V6B 4N7"), ("NU", "X0A 0H0")])
def test_postal_other_province_gives_a_well_formed_code_of_another_province(
        province: str, postal: str, contextual: dict[str, object]) -> None:
    from tabalyst.generate_anomalies import ContextualValue

    change = cast(ContextualValue, contextual["postal_other_province"])
    rng = random.Random(1)
    seen = set()
    for _ in range(50):
        after = change({"province_code": province, "code_postal": postal}, rng)
        assert after != postal and after[3:] == postal[3:] and after[0] != postal[0]
        seen.add(after[:3])
    assert len(seen) > 5  # not one constant: a pool


def test_postal_other_province_leaves_other_text_and_refuses_an_unknown_province(
        contextual: dict[str, object]) -> None:
    from tabalyst.generate_anomalies import ContextualValue

    change = cast(ContextualValue, contextual["postal_other_province"])
    assert change({"province_code": "QC", "code_postal": "n/a"}, random.Random(0)) == "n/a"
    with pytest.raises(ValueError, match="needs a province_code column"):
        change({"code_postal": "H2X 1Y4"}, random.Random(0))


def _profile_package(tmp_path: Path, operation: dict[str, object], **profile: object) -> Path:
    package = tmp_path / "package"
    shutil.copytree(PACKAGE, package)
    manifest = package / "dataset.yaml"
    document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    document["anomaly_profiles"] = {"p": {"targets": ["insurance-combined"],
                                         "operations": [operation], **profile}}
    manifest.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True),
                        encoding="utf-8")
    return package


@pytest.mark.parametrize("operation", [
    {"kind": "reuse_value", "column": "id_contrat", "count": 2},
    {"kind": "copy_column", "column": "date_fin", "value": "date_debut", "count": 2},
    {"kind": "format", "column": "code_postal", "value": "postal_other_province", "count": 2},
])
def test_scenario_only_kinds_and_values_are_refused_in_a_legacy_profile(
        tmp_path: Path, operation: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError, match="scenario profile kind|unknown format mutation"):
        validate_generate_package(_profile_package(tmp_path, operation))


def test_copy_column_needs_two_different_columns_of_the_dataset(tmp_path: Path) -> None:
    same = _operation("copy_column", "date_fin", 2, value="date_fin")
    with pytest.raises(ConfigurationError, match="copy_column requires two different columns"):
        validate_generate_package(_profile_package(tmp_path / "same", same))
    unknown = _operation("copy_column", "date_fin", 2, value="date_inconnue")
    with pytest.raises(ConfigurationError, match="unknown column"):
        validate_generate_package(_profile_package(tmp_path / "unknown", unknown))
