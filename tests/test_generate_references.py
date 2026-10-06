# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reference-backed Generate contract tests (lot 3R)."""

import csv
import re
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tabalyst.cli.app import app
from tabalyst.errors import ConfigurationError
from tabalyst.generate_definition import load_generate_definition
from tabalyst.generate_references import SCHEMAS, CommonProvider, CommonReferences
from tabalyst.generate_service import build_generate_plan, generate_datasets


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_all_thirteen_resources_are_loaded_and_linked() -> None:
    refs = CommonReferences()
    assert len(refs.tables) == len(SCHEMAS) == 13
    provinces = {r["province_code"] for r in refs.tables["geography/provinces_ca.csv"]}
    cities = {r["city_id"]: r for r in refs.tables["geography/cities_ca.csv"]}
    prefixes = refs.tables["geography/postal_prefixes_ca.csv"]
    codes = refs.tables["contact/phone_area_codes_ca.csv"]
    assert len(provinces) == 13
    assert {r["province_code"] for r in cities.values()} == provinces
    assert {r["city_id"] for r in prefixes} == set(cities)
    assert {r["province_code"] for r in codes} == provinces
    assert all(cities[r["city_id"]]["province_code"] == r["province_code"] for r in prefixes)
    assert all(int(r["weight"]) > 0 for table in refs.tables.values() for r in table)
    assert all(r["safe_domain"].endswith(".example") for r in refs.tables["contact/email_providers_ca.csv"])


def test_four_families_cohere_and_reproduce(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "examples/generate/input/common-references.yaml"
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    generate_datasets(build_generate_plan(source, output=first, rows=3000))
    generate_datasets(build_generate_plan(source, output=second, rows=3000))
    assert first.read_bytes() == second.read_bytes()
    rows = _rows(first)
    assert len(rows) == 3000
    refs = CommonReferences()
    cities = {r["city_id"]: r for r in refs.tables["geography/cities_ca.csv"]}
    prefixes = {r["prefix"]: r for r in refs.tables["geography/postal_prefixes_ca.csv"]}
    area_codes = {r["area_code"]: r for r in refs.tables["contact/phone_area_codes_ca.csv"]}
    assert len({r["email"] for r in rows}) == len(rows)
    for row in rows:
        assert row["first_name"] and row["family_name"] and row["sex"] in {"F", "M"}
        assert row["person_language"] in {"fr", "en"}
        assert row["city"] == cities[row["city_id"]]["city_name"]
        assert row["province_code"] == cities[row["city_id"]]["province_code"]
        assert prefixes[row["postal_code"][:3]]["city_id"] == row["city_id"]
        assert re.fullmatch(r"[ABCEGHJKLMNPRSTVWXYZ]\d[ABCEGHJKLMNPRSTVWXYZ] \d[ABCEGHJKLMNPRSTVWXYZ]\d", row["postal_code"])
        assert re.fullmatch(r"[a-z0-9_.-]+@[a-z0-9-]+\.example", row["email"])
        assert re.fullmatch(r"\+1-2\d\d-555-01\d\d", row["phone"])
        assert area_codes[row["phone"][3:6]]["province_code"] == row["province_code"]
        assert row["street"]
    assert len({r["city_id"] for r in rows}) > 10
    assert len({r["province_code"] for r in rows}) > 2
    cli = CliRunner().invoke(app, ["generate", str(source), "-o", str(tmp_path / "cli.csv"), "--rows", "30"])
    assert cli.exit_code == 0, cli.output
    assert len(_rows(tmp_path / "cli.csv")) == 30


def test_all_provider_tables_affect_output() -> None:
    import random

    refs = CommonReferences()
    provider = CommonProvider(refs)
    seen = Counter()
    for province in (r["province_code"] for r in refs.tables["geography/provinces_ca.csv"]):
        for profile in ("fr", "en"):
            address = provider.address({"province": province, "profile": profile,
                                        "unit_probability": 1, "direction_probability": 1},
                                       random.Random(f"{province}-{profile}"))
            person = provider.person({"profile": profile}, random.Random(f"person-{province}-{profile}"))
            contact = provider.contact({"first": "first", "last": "last", "province": "province"},
                                       {"first": person["first_name"], "last": person["family_name"],
                                        "province": province}, random.Random(f"contact-{province}-{profile}"))
            assert address["unit_type"] and address["street_direction"]
            assert address["street_type"] in address["street"]
            assert address["street_name"] in address["street"]
            assert contact["email"].endswith(".example")
            assert contact["phone"].endswith(tuple(f"-{n:04d}" for n in range(100, 200)))
            seen[profile] += 1
    assert seen == {"fr": 13, "en": 13}


@pytest.mark.parametrize("bad, message", [
    ("provider: person", "common needs a supported provider"),
    ("profile: mixed", "common.profile"),
    ("group: person", "common.group"),
])
def test_common_definition_is_strict(tmp_path: Path, bad: str, message: str) -> None:
    source = Path(__file__).resolve().parents[1] / "examples/generate/input/common-references.yaml"
    text = source.read_text(encoding="utf-8")
    if bad == "provider: person":
        text = text.replace("provider: person", "provider: unknown", 1)
    elif bad == "profile: mixed":
        text = text.replace("profile: mixed", "profile: bogus", 1)
    else:
        text = text.replace("group: person", "group: ../bad", 1)
    path = tmp_path / "bad.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigurationError, match=message):
        load_generate_definition(path)
