# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Packaged synthetic Insurance references and coherent customer rows."""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from decimal import Decimal
from importlib.resources import files

from tabalyst.errors import ConfigurationError
from tabalyst.generate_references import CommonProvider, CommonReferences

FIELDS = (
    "id_client", "civilite", "prenom", "nom", "date_naissance", "sexe",
    "langue_preferee", "numero_voie", "type_voie", "nom_voie", "orientation",
    "appartement", "ville", "province_code", "province_nom", "code_postal",
    "pays_code", "courriel", "telephone", "id_contrat", "type_contrat",
    "date_debut", "date_fin", "statut_contrat", "prime_annuelle",
    "frequence_paiement", "mode_paiement", "agence_code", "date_creation",
    "date_modification", "date_reclamation", "montant_reclamation",
    "reclamation_status",
)
SCHEMAS = {
    "contract_types.csv": ("contract_type", "label_fr", "annual_premium_min",
                           "annual_premium_max", "claim_probability", "claim_amount_min",
                           "claim_amount_max", "weight"),
    "branch_contract_weights.csv": ("filiale", "contract_type", "weight"),
    "contract_statuses.csv": ("status", "label_fr", "date_end_policy", "weight"),
    "payment_frequencies.csv": ("frequency", "label_fr", "installments_per_year", "weight"),
    "payment_methods.csv": ("payment_method", "label_fr", "weight"),
    "claim_statuses.csv": ("status", "label_fr", "amount_policy", "is_terminal", "weight"),
    "agencies.csv": ("agency_code", "filiale", "province_code", "city_id",
                     "language_profile", "weight"),
}
BRANCHES = {"principal": ("QC", 0.80, "%Y-%m-%d", "CLI-", 8, "1"),
            "ontario": ("ON", 0.80, "%m-%d-%Y", "ONT", 7, "2"),
            "quebec": ("QC", 0.85, "%d-%m-%Y", "QC-", 8, "3")}


def _pick(rng: random.Random, rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        raise ConfigurationError("Insurance resource has no candidates")
    return rng.choices(rows, weights=[int(row["weight"]) for row in rows], k=1)[0]


def _day(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _money(rng: random.Random, low: str, high: str) -> str:
    left, right = int(Decimal(low) * 100), int(Decimal(high) * 100)
    if left > right:
        raise ConfigurationError("Insurance amount range is reversed")
    return f"{Decimal(rng.randint(left, right)) / 100:.2f}"


class InsuranceReferences:
    """Validate insurance editorial data once for each generation."""

    def __init__(self, common: CommonReferences) -> None:
        self.tables: dict[str, list[dict[str, str]]] = {}
        for name, schema in SCHEMAS.items():
            resource = files("tabalyst").joinpath("generate_resources", "insurance", name)
            try:
                with resource.open("r", encoding="utf-8", newline="") as stream:
                    reader = csv.DictReader(stream)
                    if tuple(reader.fieldnames or ()) != schema:
                        raise ValueError("unexpected header")
                    rows = list(reader)
            except (OSError, UnicodeError, ValueError) as exc:
                raise ConfigurationError(f"Invalid packaged Insurance resource {name}: {exc}") from exc
            if not rows or any(
                None in row or any(not value for value in row.values())
                or not row["weight"].isdigit() or int(row["weight"]) <= 0
                for row in rows
            ):
                raise ConfigurationError(f"Invalid rows or weights in Insurance resource {name}")
            if len({row[schema[0]] for row in rows}) != len(rows) and name not in {
                "branch_contract_weights.csv", "agencies.csv",
            }:
                raise ConfigurationError(f"Duplicate key in Insurance resource {name}")
            self.tables[name] = rows
        self._validate(common)

    def _validate(self, common: CommonReferences) -> None:
        tables = self.tables
        products = {row["contract_type"] for row in tables["contract_types.csv"]}
        cities = {row["city_id"]: row for row in common.tables["geography/cities_ca.csv"]}
        if products != {"auto", "habitation", "vie", "voyage"}:
            raise ConfigurationError("Insurance contract types are incomplete")
        for row in tables["contract_types.csv"]:
            try:
                if (Decimal(row["annual_premium_min"]) < 0
                    or Decimal(row["annual_premium_min"]) > Decimal(row["annual_premium_max"])
                    or Decimal(row["claim_amount_min"]) < 0
                    or Decimal(row["claim_amount_min"]) > Decimal(row["claim_amount_max"])
                    or not 0 <= Decimal(row["claim_probability"]) <= 1):
                    raise ValueError("invalid range")
            except (ArithmeticError, ValueError) as exc:
                raise ConfigurationError("Invalid Insurance contract range") from exc
        branches = {(row["filiale"], row["contract_type"])
                    for row in tables["branch_contract_weights.csv"]}
        if (len(branches) != len(tables["branch_contract_weights.csv"])
            or branches != {(branch, product) for branch in BRANCHES for product in products}):
            raise ConfigurationError("Insurance branch/product weights are incomplete")
        if any(row["date_end_policy"] not in {"optional_future", "required_past"}
               for row in tables["contract_statuses.csv"]):
            raise ConfigurationError("Invalid Insurance contract status policy")
        if any(row["amount_policy"] not in {"optional", "required"}
               or row["is_terminal"] not in {"true", "false"}
               for row in tables["claim_statuses.csv"]):
            raise ConfigurationError("Invalid Insurance claim status policy")
        agencies = tables["agencies.csv"]
        if (len({row["agency_code"] for row in agencies}) != len(agencies)
            or {row["filiale"] for row in agencies} != set(BRANCHES)
            or any(row["city_id"] not in cities
                   or cities[row["city_id"]]["province_code"] != row["province_code"]
                   for row in agencies)):
            raise ConfigurationError("Invalid Insurance agency/city link")


class InsuranceProvider:
    def __init__(self, common: CommonReferences) -> None:
        self.common = CommonProvider(common)
        self.refs = InsuranceReferences(common)

    def row(self, branch: str | None, number: int, rng: random.Random,
            as_of_date: str) -> dict[str, str]:
        if branch not in BRANCHES:
            raise ConfigurationError("Insurance generation requires a valid branch source")
        home, share, date_format, prefix, width, contract_prefix = BRANCHES[branch]
        as_of = date.fromisoformat(as_of_date)
        if as_of - timedelta(days=18 * 365 + 6) < date(1940, 1, 1):
            raise ConfigurationError("Insurance as_of_date is too early for adult customers")
        if rng.random() < share:
            province = home
        else:
            others = [r for r in self.common.refs.tables["geography/provinces_ca.csv"]
                      if r["province_code"] != home]
            province = _pick(rng, others)["province_code"]
        address = self.common.address({"province": province}, rng)
        language = ("en" if rng.random() < 0.80 else "fr") if branch == "ontario" else address["language"]
        person = self.common.person({"profile": language}, rng)
        contact = self.common.contact(
            {"first": "prenom", "last": "nom", "province": "province_code",
             "language": "langue_preferee"},
            {"prenom": person["first_name"], "nom": person["family_name"],
             "province_code": province, "langue_preferee": language}, rng,
        )
        birth = _day(rng, date(1940, 1, 1), as_of - timedelta(days=18 * 365 + 6))
        products = self.refs.tables["contract_types.csv"]
        branch_weights = [r for r in self.refs.tables["branch_contract_weights.csv"]
                          if r["filiale"] == branch]
        product_id = _pick(rng, branch_weights)["contract_type"]
        product = next(r for r in products if r["contract_type"] == product_id)
        status = _pick(rng, self.refs.tables["contract_statuses.csv"])
        start = _day(rng, max(birth + timedelta(days=18 * 365 + 5),
                              as_of - timedelta(days=3650)), as_of - timedelta(days=1))
        terminal = status["date_end_policy"] == "required_past"
        end = (_day(rng, start + timedelta(days=1), as_of) if terminal else
               _day(rng, as_of + timedelta(days=30), as_of + timedelta(days=365))
               if rng.random() < 0.80 else None)
        creation = _day(rng, max(birth + timedelta(days=18 * 365 + 5),
                                 start - timedelta(days=30)), start)
        modification = _day(rng, creation, as_of)
        claim_date, claim_amount, claim_status = "", "", ""
        if rng.random() < float(product["claim_probability"]):
            claim = _pick(rng, self.refs.tables["claim_statuses.csv"])
            claim_date = _day(rng, start, min(end or as_of, as_of))
            claim_status = claim["status"]
            if claim["amount_policy"] == "required" or rng.random() < 0.65:
                claim_amount = _money(rng, product["claim_amount_min"],
                                      product["claim_amount_max"])
        agency = _pick(rng, [r for r in self.refs.tables["agencies.csv"]
                             if r["filiale"] == branch])
        client_number = f"{number:0{width}d}"
        if branch == "quebec":
            client_number = f"{client_number[:4]}-{client_number[4:]}"
        result = {
            "id_client": prefix + client_number,
            "civilite": "Mme" if person["sex"] == "F" else "M.",
            "prenom": person["first_name"], "nom": person["family_name"],
            "date_naissance": birth, "sexe": person["sex"],
            "langue_preferee": language, "numero_voie": address["street_number"],
            "type_voie": address["street_type"], "nom_voie": address["street_name"],
            "orientation": address["street_direction"],
            "appartement": address["unit_number"], "ville": address["city"],
            "province_code": province, "province_nom": address["province_name"],
            "code_postal": address["postal_code"], "pays_code": "CA",
            "courriel": contact["email"], "telephone": contact["phone"],
            "id_contrat": f"CTR-{contract_prefix}{number:09d}",
            "type_contrat": product_id, "date_debut": start, "date_fin": end or "",
            "statut_contrat": status["status"],
            "prime_annuelle": _money(rng, product["annual_premium_min"],
                                      product["annual_premium_max"]),
            "frequence_paiement": _pick(rng, self.refs.tables["payment_frequencies.csv"])["frequency"],
            "mode_paiement": _pick(rng, self.refs.tables["payment_methods.csv"])["payment_method"],
            "agence_code": agency["agency_code"], "date_creation": creation,
            "date_modification": modification, "date_reclamation": claim_date,
            "montant_reclamation": claim_amount, "reclamation_status": claim_status,
        }
        return {key: value.strftime(date_format) if isinstance(value, date) else value
                for key, value in result.items()}
