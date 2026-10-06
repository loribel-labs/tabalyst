# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Packaged, validated reference tables for synthetic Canadian records."""

from __future__ import annotations

import csv
import random
import re
import unicodedata
from importlib.resources import files

from tabalyst.errors import ConfigurationError

SCHEMAS = {
    "people/first_names_fr_qc.csv": ("first_name", "sex", "profile", "weight"),
    "people/first_names_en_ca.csv": ("first_name", "sex", "profile", "weight"),
    "people/family_names_ca.csv": ("family_name", "profile", "weight"),
    "geography/provinces_ca.csv": ("province_code", "province_name_fr", "province_name_en", "country_code", "language_profile", "weight"),
    "geography/cities_ca.csv": ("city_id", "city_name", "province_code", "region", "language_profile", "weight"),
    "geography/postal_prefixes_ca.csv": ("prefix", "city_id", "province_code", "is_rural", "weight"),
    "addresses/street_types_ca.csv": ("street_type", "language", "abbreviation", "position", "weight"),
    "addresses/street_names_ca.csv": ("street_name", "language_profile", "scope", "source_type", "weight"),
    "addresses/street_directions_ca.csv": ("direction", "language", "abbreviation", "position", "weight"),
    "addresses/unit_types_ca.csv": ("unit_type", "language", "abbreviation", "weight"),
    "contact/email_providers_ca.csv": ("provider_id", "production_domain", "safe_domain", "language_profile", "weight"),
    "contact/email_patterns.csv": ("pattern_id", "template", "weight", "min_digits", "max_digits"),
    "contact/phone_area_codes_ca.csv": ("area_code", "province_code", "coverage", "weight"),
}
LANGUAGES = {"fr", "en", "bilingual", "multilingual"}
POSTAL_LETTERS = "ABCEGHJKLMNPRSTVWXYZ"
FIELDS = {
    "person": {"first_name", "family_name", "sex", "salutation", "language"},
    "address": {"street_number", "street_type", "street_type_position", "street_name", "street_direction", "street_direction_position", "street", "unit_type", "unit_number", "unit", "city_id", "city", "province_code", "province_name", "postal_prefix", "postal_code", "country_code", "language"},
    "contact": {"email", "phone"},
}


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return re.sub(r"[^a-z0-9]", "", normalized.encode("ascii", "ignore").decode().lower()) or "user"


def _pick(rng: random.Random, rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        raise ConfigurationError("Packaged Generate references have no candidates")
    return rng.choices(rows, weights=[int(row["weight"]) for row in rows], k=1)[0]


class CommonReferences:
    """One execution-local cache; no caller-supplied paths or network lookups."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, str]]] = {}
        for name, schema in SCHEMAS.items():
            resource = files("tabalyst").joinpath("generate_resources", *name.split("/"))
            try:
                with resource.open("r", encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream)
                    if tuple(reader.fieldnames or ()) != schema:
                        raise ValueError("unexpected header")
                    rows = list(reader)
            except (OSError, UnicodeError, ValueError) as exc:
                raise ConfigurationError(f"Invalid packaged Generate resource {name}: {exc}") from exc
            if not rows or any(None in row or any(not value for value in row.values())
                                   or not row["weight"].isdigit() or int(row["weight"]) <= 0
                                   for row in rows):
                raise ConfigurationError(f"Invalid rows or weights in packaged Generate resource {name}")
            key = schema[0]
            if len({row[key] for row in rows}) != len(rows):
                # First names can repeat across sex, but within each table they should not.
                raise ConfigurationError(f"Duplicate {key} in packaged Generate resource {name}")
            self.tables[name] = rows
        self._validate_links()

    def _validate_links(self) -> None:
        table = self.tables
        provinces = {r["province_code"] for r in table["geography/provinces_ca.csv"]}
        cities = {r["city_id"]: r for r in table["geography/cities_ca.csv"]}
        prefixes = table["geography/postal_prefixes_ca.csv"]
        codes = table["contact/phone_area_codes_ca.csv"]
        if any(r["province_code"] not in provinces or r["language_profile"] not in LANGUAGES
               for r in cities.values()):
            raise ConfigurationError("Invalid city/province or language link in Generate references")
        if any(r["city_id"] not in cities or cities[r["city_id"]]["province_code"] != r["province_code"]
               or not re.fullmatch(r"[ABCEGHJKLMNPRSTVWXYZ][0-9][ABCEGHJKLMNPRSTVWXYZ]", r["prefix"])
               or r["is_rural"] not in {"true", "false"} for r in prefixes):
            raise ConfigurationError("Invalid postal prefix/city/province link in Generate references")
        if {r["city_id"] for r in prefixes} != set(cities):
            raise ConfigurationError("Each Generate city needs a postal prefix")
        if {r["province_code"] for r in codes} != provinces or any(
            not re.fullmatch(r"[2-9][0-9]{2}", r["area_code"]) for r in codes
        ):
            raise ConfigurationError("Invalid area code/province link in Generate references")
        if any(r["language_profile"] not in LANGUAGES or r["country_code"] != "CA"
               for r in table["geography/provinces_ca.csv"]):
            raise ConfigurationError("Invalid province profile in Generate references")
        for name in ("people/first_names_fr_qc.csv", "people/first_names_en_ca.csv"):
            expected = "fr_qc" if "fr_qc" in name else "en_ca"
            if any(r["sex"] not in {"F", "M"} or r["profile"] != expected for r in table[name]):
                raise ConfigurationError(f"Invalid first-name profile in {name}")
        if any(r["profile"] not in {"fr_qc", "en_ca", "multicultural"}
               for r in table["people/family_names_ca.csv"]):
            raise ConfigurationError("Invalid family-name profile")
        for name in ("street_types_ca.csv", "street_directions_ca.csv"):
            if any(r["language"] not in {"fr", "en"} or r["position"] not in {"prefix", "suffix"}
                   for r in table[f"addresses/{name}"]):
                raise ConfigurationError(f"Invalid address position in {name}")
        if any(r["language_profile"] not in {"fr", "en"} or r["source_type"] != "synthetic"
               for r in table["addresses/street_names_ca.csv"]):
            raise ConfigurationError("Invalid synthetic street names")
        if any(r["language"] not in {"fr", "en"} for r in table["addresses/unit_types_ca.csv"]):
            raise ConfigurationError("Invalid unit language")
        if any(not r["safe_domain"].endswith(".example") or r["language_profile"] not in LANGUAGES
               for r in table["contact/email_providers_ca.csv"]):
            raise ConfigurationError("Unsafe Generate email provider")
        for r in table["contact/email_patterns.csv"]:
            template = r["template"].replace("{first:3}", "{first}")
            if not re.fullmatch(r"[a-z{}_.-]+", template) or re.search(
                r"\{(?!first\}|last\}|first_initial\}|last_initial\}|digits\})", template
            ) or not r["min_digits"].isdigit() or not r["max_digits"].isdigit() or (
                int(r["min_digits"]) > int(r["max_digits"]) or int(r["max_digits"]) > 8
            ):
                raise ConfigurationError("Invalid Generate email pattern")

    def select(self, name: str, rng: random.Random, **filters: str) -> dict[str, str]:
        return _pick(rng, [r for r in self.tables[name] if all(r[k] == v for k, v in filters.items())])


class CommonProvider:
    def __init__(self, refs: CommonReferences) -> None:
        self.refs = refs
        self.used_emails: set[str] = set()

    def person(self, config: dict, rng: random.Random) -> dict[str, str]:
        profile = config.get("profile", "mixed")
        language = rng.choice(("fr", "en")) if profile == "mixed" else profile
        first = self.refs.select(
            f"people/first_names_{'fr_qc' if language == 'fr' else 'en_ca'}.csv", rng,
        )
        family_profile = "fr_qc" if language == "fr" else "en_ca"
        roll = rng.random()
        if roll >= 0.95:
            family_profile = "en_ca" if language == "fr" else "fr_qc"
        elif roll >= 0.80:
            family_profile = "multicultural"
        family = self.refs.select("people/family_names_ca.csv", rng, profile=family_profile)
        return {"first_name": first["first_name"], "family_name": family["family_name"],
                "sex": first["sex"], "salutation": "Mme" if first["sex"] == "F" and language == "fr" else
                "M." if language == "fr" else "Ms" if first["sex"] == "F" else "Mr",
                "language": language}

    def address(self, config: dict, rng: random.Random) -> dict[str, str]:
        province = self.refs.select("geography/provinces_ca.csv", rng, **(
            {"province_code": config["province"]} if "province" in config else {}
        ))
        city = self.refs.select("geography/cities_ca.csv", rng, province_code=province["province_code"])
        profile = config.get("profile", "mixed")
        language = (rng.choice(("fr", "en")) if city["language_profile"] in {"bilingual", "multilingual"}
                    else city["language_profile"]) if profile == "mixed" else profile
        prefix = self.refs.select("geography/postal_prefixes_ca.csv", rng, city_id=city["city_id"])
        street_type = self.refs.select("addresses/street_types_ca.csv", rng, language=language)
        street_name = self.refs.select("addresses/street_names_ca.csv", rng, language_profile=language)
        direction = self.refs.select("addresses/street_directions_ca.csv", rng, language=language)
        unit_type = self.refs.select("addresses/unit_types_ca.csv", rng, language=language)
        number = str(rng.randint(1, 9999))
        direction_text = direction["direction"] if rng.random() < config.get("direction_probability", 0.25) else ""
        unit_number = str(rng.randint(1, 999)) if rng.random() < config.get("unit_probability", 0.35) else ""
        street_parts = [number]
        if street_type["position"] == "prefix":
            street_parts.append(street_type["street_type"])
        if direction_text and direction["position"] == "prefix":
            street_parts.append(direction_text)
        street_parts.append(street_name["street_name"])
        if street_type["position"] == "suffix":
            street_parts.append(street_type["street_type"])
        if direction_text and direction["position"] == "suffix":
            street_parts.append(direction_text)
        suffix = f"{rng.randint(0, 9)}{rng.choice(POSTAL_LETTERS)}{rng.randint(0, 9)}"
        return {
            "street_number": number, "street_type": street_type["street_type"],
            "street_type_position": street_type["position"], "street_name": street_name["street_name"],
            "street_direction": direction_text,
            "street_direction_position": direction["position"] if direction_text else "",
            "street": " ".join(street_parts), "unit_type": unit_type["unit_type"] if unit_number else "",
            "unit_number": unit_number, "unit": f"{unit_type['abbreviation']} {unit_number}" if unit_number else "",
            "city_id": city["city_id"], "city": city["city_name"],
            "province_code": province["province_code"],
            "province_name": province["province_name_fr" if language == "fr" else "province_name_en"],
            "postal_prefix": prefix["prefix"], "postal_code": f"{prefix['prefix']} {suffix}",
            "country_code": province["country_code"], "language": language,
        }

    def contact(self, config: dict, row: dict[str, str], rng: random.Random) -> dict[str, str]:
        first, last = _slug(row[config["first"]]), _slug(row[config["last"]])
        province = row[config["province"]]
        language = row[config["language"]] if "language" in config else None
        candidates = self.refs.tables["contact/email_providers_ca.csv"]
        if language in {"fr", "en"}:
            candidates = [r for r in candidates if r["language_profile"] in {
                language, "bilingual", "multilingual",
            }]
        provider = _pick(rng, candidates)
        pattern = self.refs.select("contact/email_patterns.csv", rng)
        digits = "".join(str(rng.randint(0, 9)) for _ in range(
            rng.randint(int(pattern["min_digits"]), int(pattern["max_digits"]))
        ))
        local = pattern["template"].replace("{first:3}", first[:3]).format(
            first=first, last=last, first_initial=first[0], last_initial=last[0], digits=digits,
        )
        base = f"{local}@{provider['safe_domain']}"
        email = base
        suffix = 2
        while email in self.used_emails:
            email = f"{local}.{suffix}@{provider['safe_domain']}"
            suffix += 1
        self.used_emails.add(email)
        code = self.refs.select("contact/phone_area_codes_ca.csv", rng, province_code=province)
        return {"email": email, "phone": f"+1-{code['area_code']}-555-{rng.randint(100, 199):04d}"}
