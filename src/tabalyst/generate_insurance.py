# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Packaged synthetic Insurance references and coherent customer rows."""

from __future__ import annotations

import random
import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal

from tabalyst.errors import ConfigurationError
from tabalyst.generate_anomalies import ContextualValue
from tabalyst.generate_canonical import (
    canonical_date,
    canonical_decimal,
    canonical_text,
)
from tabalyst.generate_draws import truncated_lognormal
from tabalyst.generate_package import DatasetPackage
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
# A monthly payment is an automatic one: no cheque or transfer every month.
MONTHLY_METHODS = frozenset({"prélèvement", "carte"})
# A travel contract covers one trip, started in the last three years.
TRIP_DAYS = (3, 90)
TRIP_WINDOW_DAYS = 3 * 365
# A claim older than a year is settled; one under a month is still being handled.
SETTLED_CLAIM_DAYS = 365
FRESH_CLAIM_DAYS = 30
# Spread of the claim amounts around the geometric mean of the product's range.
CLAIM_SIGMA = 1.0


def _pick(rng: random.Random, rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        raise ConfigurationError("Insurance resource has no candidates")
    return rng.choices(rows, weights=[int(row["weight"]) for row in rows], k=1)[0]


def _day(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _age(birth: date, as_of: date) -> int:
    return as_of.year - birth.year - ((as_of.month, as_of.day) < (birth.month, birth.day))


def _premium_factor(product: str, age: int) -> Decimal:
    """Price a premium by age: young and old drivers, life cover that grows with age."""
    if product == "auto":
        return Decimal("1.8") if age < 25 else Decimal("1.3") if age < 30 else (
            Decimal("1.2") if age >= 70 else Decimal(1))
    if product == "vie":
        return Decimal("0.5") + Decimal(max(age - 18, 0)) / 40
    if product == "voyage" and age >= 65:
        return Decimal("1.5")
    return Decimal(1)


def _email_missing(age: int) -> float:
    """Older customers leave their email empty more often."""
    return 0.02 if age < 50 else 0.08 if age < 70 else 0.25


def _claim_amount(rng: random.Random, low: str, high: str) -> str:
    """Many small claims and a few large ones, within the product's range."""
    left, right = Decimal(low), Decimal(high)
    if not 0 < left <= right:
        raise ConfigurationError("Insurance claim range must be above 0 and ordered")
    median = float((left * right).sqrt())
    drawn = Decimal(str(truncated_lognormal(rng, median, CLAIM_SIGMA, float(left), float(right))))
    return f"{min(max(drawn.quantize(Decimal('0.01')), left), right):.2f}"


def _money(rng: random.Random, low: str, high: str) -> str:
    left, right = int(Decimal(low) * 100), int(Decimal(high) * 100)
    if left > right:
        raise ConfigurationError("Insurance amount range is reversed")
    return f"{Decimal(rng.randint(left, right)) / 100:.2f}"


class InsuranceReferences:
    """Validate insurance editorial data once for each generation."""

    def __init__(self, common: CommonReferences, package: DatasetPackage) -> None:
        self.tables: dict[str, list[dict[str, str]]] = {}
        for name, schema in SCHEMAS.items():
            table = package.tables.get(name.removesuffix(".csv"))
            if table is None or table.role != "resource" or tuple(
                column.name for column in table.columns
            ) != schema:
                raise ConfigurationError(f"PACKAGE_PROVIDER: invalid Insurance resource {name}")
            rows = [{key: "" if value is None else str(value).lower() if isinstance(value, bool)
                     else str(value) for key, value in row.items()} for row in table.rows]
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
        if not {"actif", "expiré"} <= {row["status"] for row in tables["contract_statuses.csv"]}:
            raise ConfigurationError("Insurance contract statuses need actif and expiré for travel")
        if not MONTHLY_METHODS <= {row["payment_method"] for row in tables["payment_methods.csv"]}:
            raise ConfigurationError("Insurance payment methods lack a monthly method")
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
    """Generate coherent branch rows from declared Insurance resources."""

    def __init__(self, common: CommonReferences, package: DatasetPackage) -> None:
        self.common: CommonProvider = CommonProvider(common)
        self.refs: InsuranceReferences = InsuranceReferences(common, package)

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
        statuses = {row["status"]: row for row in self.refs.tables["contract_statuses.csv"]}
        adult = birth + timedelta(days=18 * 365 + 5)
        end: date | None
        if product_id == "voyage":
            start = _day(rng, max(adult, as_of - timedelta(days=TRIP_WINDOW_DAYS)),
                         as_of - timedelta(days=1))
            end = start + timedelta(days=rng.randint(*TRIP_DAYS))
            status = statuses["expiré" if end < as_of else "actif"]
        else:
            status = _pick(rng, self.refs.tables["contract_statuses.csv"])
            start = _day(rng, max(adult, as_of - timedelta(days=3650)), as_of - timedelta(days=1))
            terminal = status["date_end_policy"] == "required_past"
            end = (_day(rng, start + timedelta(days=1), as_of) if terminal else
                   _day(rng, as_of + timedelta(days=30), as_of + timedelta(days=365))
                   if rng.random() < 0.80 else None)
        creation = _day(rng, max(birth + timedelta(days=18 * 365 + 5),
                                 start - timedelta(days=30)), start)
        claim_date: date | str = ""
        claim_amount, claim_status = "", ""
        last_event = creation
        if rng.random() < float(product["claim_probability"]):
            claim_day = _day(rng, start, min(end or as_of, as_of))
            claim_date, last_event = claim_day, max(creation, claim_day)
            age_days = (as_of - claim_day).days
            claims = self.refs.tables["claim_statuses.csv"]
            if age_days > SETTLED_CLAIM_DAYS:
                claims = [row for row in claims if row["is_terminal"] == "true"] or claims
            elif age_days < FRESH_CLAIM_DAYS:
                claims = [row for row in claims if row["is_terminal"] == "false"] or claims
            claim = _pick(rng, claims)
            claim_status = claim["status"]
            if claim["amount_policy"] == "required" or rng.random() < 0.65:
                claim_amount = _claim_amount(rng, product["claim_amount_min"],
                                             product["claim_amount_max"])
        modification = _day(rng, last_event, as_of)
        frequency = _pick(rng, self.refs.tables["payment_frequencies.csv"])["frequency"]
        methods = self.refs.tables["payment_methods.csv"]
        if frequency == "mensuelle":
            methods = [row for row in methods if row["payment_method"] in MONTHLY_METHODS]
        method = _pick(rng, methods)["payment_method"]
        # The agency of the customer's city, else of the province, else of the branch.
        agencies = [r for r in self.refs.tables["agencies.csv"] if r["filiale"] == branch]
        agency = _pick(rng, [r for r in agencies if r["city_id"] == address["city_id"]]
                       or [r for r in agencies if r["province_code"] == province] or agencies)
        age = _age(birth, as_of)
        premium = Decimal(_money(rng, product["annual_premium_min"], product["annual_premium_max"]))
        premium = (premium * _premium_factor(product_id, age)).quantize(Decimal("0.01"))
        email = "" if rng.random() < _email_missing(age) else contact["email"]
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
            "courriel": email, "telephone": contact["phone"],
            "id_contrat": f"CTR-{contract_prefix}{number:09d}",
            "type_contrat": product_id, "date_debut": start, "date_fin": end or "",
            "statut_contrat": status["status"],
            "prime_annuelle": f"{premium:.2f}",
            "frequence_paiement": frequency, "mode_paiement": method,
            "agence_code": agency["agency_code"], "date_creation": creation,
            "date_modification": modification, "date_reclamation": claim_date,
            "montant_reclamation": claim_amount, "reclamation_status": claim_status,
        }
        return {key: value.strftime(date_format) if isinstance(value, date) else value
                for key, value in result.items()}


DEFAULT_FIELDS: tuple[str, ...] = FIELDS
EXTENDED_FIELDS: tuple[str, ...] = (
    "date_sinistre", "montant_couverture", "franchise", "montant_indemnise",
    "date_resiliation", "statut_paiement", "canal_acquisition", "courtier_id",
    "produit_code", "nombre_reclamations",
)
TRANCHE_B_FIELDS: tuple[str, ...] = (
    "taux_remboursement", "consentement_communication", "gestionnaire_id",
    "segment_client",
)
TRANCHE_C_FIELDS: tuple[str, ...] = (
    "date_observation", "version_source", "source_system",
)
OUTPUT_PROFILES: dict[str, tuple[str, ...]] = {
    "default": DEFAULT_FIELDS,
    "extended": (*DEFAULT_FIELDS, *EXTENDED_FIELDS),
    "complete": (*DEFAULT_FIELDS, *EXTENDED_FIELDS, *TRANCHE_B_FIELDS, *TRANCHE_C_FIELDS),
}

# Contract insurance-v2.md 4.5: the type of each column decides how its clean cell is normalized.
DATE_COLUMNS = frozenset({"date_naissance", "date_debut", "date_fin", "date_creation",
                          "date_modification", "date_reclamation", "date_sinistre",
                          "date_resiliation", "date_observation"})
AMOUNT_COLUMNS = frozenset({"prime_annuelle", "montant_reclamation", "montant_couverture",
                            "franchise", "montant_indemnise", "taux_remboursement"})
IDENTIFIER_COLUMNS = frozenset({"id_client", "id_contrat", "agence_code", "courtier_id",
                                "gestionnaire_id"})
BRANCH_COLUMN = "filiale"


def insurance_canonical(column: str, value: str, row: Mapping[str, str]) -> str:
    """Return the canonical value of a clean Insurance cell (contract insurance-v2.md 4.5).

    A date is read with the convention of the branch of its row (``filiale``) and written as
    ISO 8601, so ``05-10-2026`` of a Quebec row is ``2026-10-05`` even where a defect rewrites
    it in another convention. An amount is a plain decimal, an identifier stays as it is and any
    other text is NFC and trimmed. Raises ValueError for a date whose row has no known branch
    or does not follow its convention.
    """
    if column in IDENTIFIER_COLUMNS or not value:
        return value
    if column in DATE_COLUMNS:
        branch = BRANCHES.get(row.get(BRANCH_COLUMN, ""))
        if branch is None:
            raise ValueError(f"canonical value of {column}: unknown {BRANCH_COLUMN} "
                             f"{row.get(BRANCH_COLUMN)!r}")
        return canonical_date(value, branch[2])
    if column in AMOUNT_COLUMNS:
        return canonical_decimal(value)
    return canonical_text(value)


POSTAL_CODE = re.compile(r"([A-Z]\d[A-Z]) (\d[A-Z]\d)\Z")


def insurance_contextual(references: CommonReferences) -> dict[str, ContextualValue]:
    """Return the ``format`` values of Insurance that need the whole row (contract 6.2).

    ``postal_other_province`` (R07) replaces the forward sortation area of a postal code with one
    of a province whose codes never start with a letter of the customer's province, and keeps
    the three characters after the space, so the code stays well formed and only its province
    is wrong. A cell that is not a postal code is left as it is.
    """
    prefixes = sorted(row["prefix"] for row in references.tables["geography/postal_prefixes_ca.csv"])
    letters: dict[str, set[str]] = {}
    for row in references.tables["geography/postal_prefixes_ca.csv"]:
        letters.setdefault(row["province_code"], set()).add(row["prefix"][0])
    elsewhere = {province: [prefix for prefix in prefixes if prefix[0] not in own]
                 for province, own in letters.items()}

    def postal_other_province(row: Mapping[str, str], rng: random.Random) -> str:
        province = row.get("province_code")
        if province not in elsewhere:
            raise ValueError("postal_other_province needs a province_code column with a known "
                             f"province, got {province!r}")
        postal = row.get("code_postal", "")
        found = POSTAL_CODE.match(postal)
        if found is None:
            return postal
        return f"{rng.choice(elsewhere[province])} {found[2]}"

    return {"postal_other_province": postal_other_province}


COVERAGE_CAPS: dict[str, tuple[list[int], list[int]]] = {
    "auto": ([50000, 100000, 250000, 500000, 1000000, 2000000], [10, 30, 30, 20, 8, 2]),
    "habitation": ([150000, 250000, 500000, 750000, 1000000, 1500000], [15, 30, 35, 12, 6, 2]),
    "vie": ([50000, 100000, 250000, 500000, 1000000], [20, 30, 30, 15, 5]),
    "voyage": ([25000, 50000, 100000, 1000000, 5000000], [25, 35, 25, 10, 5]),
}
DEDUCTIBLES: dict[str, tuple[list[int], list[int]]] = {
    "auto": ([250, 500, 1000], [25, 50, 25]),
    "habitation": ([500, 1000, 2500], [40, 45, 15]),
    "vie": ([0], [1]),
    "voyage": ([0, 50, 100], [60, 20, 20]),
}
PRODUCT_CODES: dict[str, tuple[list[str], list[int]]] = {
    "auto": (["AUT_BASE", "AUT_CONFORT", "AUT_TOURISME", "AUT_PREMIUM"], [30, 40, 20, 10]),
    "habitation": (["HAB_LOCATAIRE", "HAB_PROPRIETAIRE", "HAB_COPROPRIETE", "HAB_PRESTIGE"], [25, 45, 20, 10]),
    "vie": (["VIE_TEMPORAIRE", "VIE_PERMANENTE", "VIE_UNIVERSELLE"], [50, 35, 15]),
    "voyage": (["VOY_INDIVIDUEL", "VOY_FAMILLE", "VOY_ANNULATION", "VOY_MULTI"], [40, 30, 20, 10]),
}
PAYMENT_STATUSES: dict[str, tuple[list[str], list[int]]] = {
    "actif": (["payé", "partiel", "en_retard", "impayé"], [88, 6, 4, 2]),
    "suspendu": (["en_retard", "impayé", "partiel"], [60, 35, 5]),
    "résilié": (["impayé", "payé", "en_retard"], [55, 35, 10]),
    "expiré": (["payé", "impayé"], [95, 5]),
}
ACQUISITION_CHANNELS: tuple[list[str], list[int]] = (
    ["web", "courtier", "agence", "téléphone"], [40, 25, 25, 10],
)
CLAIM_COUNTS: tuple[list[int], list[int]] = (
    [1, 2, 3], [85, 12, 3],
)


def _parse_branch_date(text: str, fmt: str) -> date:
    return datetime.strptime(text, fmt).date()  # noqa: DTZ007 - a date has no zone


def extend_insurance_row(row: Mapping[str, str], branch: str,
                         streams: Mapping[str, random.Random],
                         as_of_date: str) -> dict[str, str]:
    """Extend a 34-column Insurance row with the 10 columns of the extended profile (contract 7).

    Each column draws exclusively from its dedicated stream in ``streams``, so draws remain
    deterministic and independent of other columns.
    """
    if branch not in BRANCHES:
        raise ConfigurationError(f"unknown Insurance branch {branch!r}")
    date_format = BRANCHES[branch][2]
    product = row["type_contrat"]

    # 1. date_sinistre
    rng_sin = streams["date_sinistre"]
    if row.get("date_reclamation"):
        start_date = _parse_branch_date(row["date_debut"], date_format)
        decl_date = _parse_branch_date(row["date_reclamation"], date_format)
        diff = (decl_date - start_date).days
        offset = rng_sin.randint(0, diff) if diff > 0 else 0
        date_sinistre = (start_date + timedelta(days=offset)).strftime(date_format)
    else:
        date_sinistre = ""

    # 2. montant_couverture
    rng_cov = streams["montant_couverture"]
    cov_opts, cov_weights = COVERAGE_CAPS.get(product, ([100000], [1]))
    cap_val = rng_cov.choices(cov_opts, weights=cov_weights, k=1)[0]
    montant_couverture = f"{Decimal(cap_val):.2f}"

    # 3. franchise
    rng_ded = streams["franchise"]
    ded_opts, ded_weights = DEDUCTIBLES.get(product, ([0], [1]))
    ded_val = rng_ded.choices(ded_opts, weights=ded_weights, k=1)[0]
    franchise = f"{Decimal(ded_val):.2f}"

    # 4. montant_indemnise
    rng_ind = streams["montant_indemnise"]
    if row.get("date_reclamation") and row.get("montant_reclamation"):
        rec_amt = Decimal(row["montant_reclamation"])
        cov_amt = Decimal(montant_couverture)
        ded_amt = Decimal(franchise)
        status = row.get("reclamation_status", "")
        max_pay = min(cov_amt, max(Decimal("0.00"), rec_amt - ded_amt))
        if status in {"rejeté", "ouvert"}:
            montant_indemnise = "0.00"
        elif status == "fermé":
            montant_indemnise = f"{max_pay:.2f}"
        else:
            shares = [Decimal("0.00"), (max_pay * Decimal("0.5")).quantize(Decimal("0.01")), max_pay]
            montant_indemnise = f"{rng_ind.choices(shares, weights=[50, 30, 20], k=1)[0]:.2f}"
    else:
        montant_indemnise = ""

    # 5. date_resiliation
    rng_res = streams["date_resiliation"]
    if row.get("statut_contrat") == "résilié" and row.get("date_fin"):
        start_date = _parse_branch_date(row["date_debut"], date_format)
        end_date = _parse_branch_date(row["date_fin"], date_format)
        diff = (end_date - start_date).days
        offset = rng_res.randint(1, diff) if diff > 0 else 0
        date_resiliation = (start_date + timedelta(days=offset)).strftime(date_format)
    else:
        date_resiliation = ""

    # 6. statut_paiement
    rng_pay = streams["statut_paiement"]
    pay_opts, pay_weights = PAYMENT_STATUSES.get(
        row.get("statut_contrat", ""), (["payé"], [1]),
    )
    statut_paiement = rng_pay.choices(pay_opts, weights=pay_weights, k=1)[0]

    # 7. canal_acquisition
    rng_acq = streams["canal_acquisition"]
    canal_acquisition = rng_acq.choices(ACQUISITION_CHANNELS[0], weights=ACQUISITION_CHANNELS[1], k=1)[0]

    # 8. courtier_id
    rng_crt = streams["courtier_id"]
    if canal_acquisition == "courtier":
        courtier_id = f"CRT-{rng_crt.randint(101, 300):04d}"
    else:
        courtier_id = ""

    # 9. produit_code
    rng_prd = streams["produit_code"]
    prd_opts, prd_weights = PRODUCT_CODES.get(product, (["STD"], [1]))
    produit_code = rng_prd.choices(prd_opts, weights=prd_weights, k=1)[0]

    # 10. nombre_reclamations
    rng_cnt = streams["nombre_reclamations"]
    if row.get("date_reclamation"):
        nombre_reclamations = str(rng_cnt.choices(CLAIM_COUNTS[0], weights=CLAIM_COUNTS[1], k=1)[0])
    else:
        nombre_reclamations = "0"

    extended = {
        "date_sinistre": date_sinistre,
        "montant_couverture": montant_couverture,
        "franchise": franchise,
        "montant_indemnise": montant_indemnise,
        "date_resiliation": date_resiliation,
        "statut_paiement": statut_paiement,
        "canal_acquisition": canal_acquisition,
        "courtier_id": courtier_id,
        "produit_code": produit_code,
        "nombre_reclamations": nombre_reclamations,
    }
    return {**row, **extended}


REIMBURSEMENT_RATES: dict[str, str] = {
    "AUT_BASE": "0.70",
    "AUT_CONFORT": "0.80",
    "AUT_TOURISME": "0.85",
    "AUT_PREMIUM": "1.00",
    "HAB_LOCATAIRE": "0.80",
    "HAB_PROPRIETAIRE": "0.85",
    "HAB_COPROPRIETE": "0.85",
    "HAB_PRESTIGE": "1.00",
    "VIE_TEMPORAIRE": "1.00",
    "VIE_PERMANENTE": "1.00",
    "VIE_UNIVERSELLE": "1.00",
    "VOY_INDIVIDUEL": "0.80",
    "VOY_FAMILLE": "0.85",
    "VOY_ANNULATION": "0.90",
    "VOY_MULTI": "1.00",
}
CLIENT_SEGMENTS: tuple[list[str], list[int]] = (
    ["particulier", "professionnel", "entreprise", "vip"], [70, 15, 10, 5],
)


def extend_tranche_b_row(row: Mapping[str, str],
                         streams: Mapping[str, random.Random]) -> dict[str, str]:
    """Extend an Insurance row with the 4 columns of tranche B (contract 7).

    Each column draws exclusively from its dedicated stream in ``streams``, so draws remain
    deterministic and independent of other columns.
    """
    # 1. taux_remboursement
    rng_taux = streams["taux_remboursement"]
    prod_code = row.get("produit_code", "")
    if prod_code in REIMBURSEMENT_RATES:
        taux_remboursement = REIMBURSEMENT_RATES[prod_code]
    else:
        taux_remboursement = rng_taux.choices(
            ["0.70", "0.80", "0.85", "0.90", "1.00"],
            weights=[20, 35, 20, 15, 10], k=1,
        )[0]

    # 2. consentement_communication
    rng_cst = streams["consentement_communication"]
    consentement = rng_cst.choices(["true", "false"], weights=[70, 30], k=1)[0]

    # 3. gestionnaire_id
    rng_ges = streams["gestionnaire_id"]
    gestionnaire_id = f"GES-{rng_ges.randint(1, 50):03d}"

    # 4. segment_client
    rng_seg = streams["segment_client"]
    segment_client = rng_seg.choices(CLIENT_SEGMENTS[0], weights=CLIENT_SEGMENTS[1], k=1)[0]

    tranche_b = {
        "taux_remboursement": taux_remboursement,
        "consentement_communication": consentement,
        "gestionnaire_id": gestionnaire_id,
        "segment_client": segment_client,
    }
    return {**row, **tranche_b}


def extend_tranche_c_row(row: Mapping[str, str], branch: str,
                         streams: Mapping[str, random.Random],
                         as_of_date: str) -> dict[str, str]:
    """Extend an Insurance row with the 3 columns of tranche C (contract 7, lot 12).

    Each column draws exclusively from its dedicated stream in ``streams``, so draws remain
    deterministic and independent of other columns.
    """
    if branch not in BRANCHES:
        raise ConfigurationError(f"unknown Insurance branch {branch!r}")
    date_format = BRANCHES[branch][2]
    as_of = date.fromisoformat(as_of_date)

    # 1. date_observation: fixed to as_of_date, formatted in branch date format
    date_obs = as_of.strftime(date_format)

    # 2. version_source: software schema version evolution over time
    creation_str = row.get("date_creation", "")
    if creation_str:
        creation_date = _parse_branch_date(creation_str, date_format)
        if creation_date < date(2024, 1, 1):
            ver = "v1.0"
        elif creation_date < date(2025, 7, 1):
            ver = "v2.0"
        else:
            ver = "v2.1"
    else:
        ver = "v2.0"

    # 3. source_system: system origin simulation
    if branch == "principal":
        src = "SYS_PRI"
    elif branch == "quebec":
        src = "SYS_QC"
    else:  # ontario
        if creation_str:
            creation_date = _parse_branch_date(creation_str, date_format)
            src = "SYS_ON_LEGACY" if creation_date < date(2023, 6, 1) else "SYS_ON_CORE"
        else:
            src = "SYS_ON_CORE"

    tranche_c = {
        "date_observation": date_obs,
        "version_source": ver,
        "source_system": src,
    }
    return {**row, **tranche_c}


COLUMN_TRANSLATIONS_EN: dict[str, str] = {
    # Default fields
    "id_client": "customer_id",
    "civilite": "title",
    "prenom": "first_name",
    "nom": "last_name",
    "date_naissance": "birth_date",
    "sexe": "gender",
    "langue_preferee": "preferred_language",
    "numero_voie": "street_number",
    "type_voie": "street_type",
    "nom_voie": "street_name",
    "orientation": "street_direction",
    "appartement": "unit_number",
    "ville": "city",
    "province_code": "province_code",
    "province_nom": "province_name",
    "code_postal": "postal_code",
    "pays_code": "country_code",
    "courriel": "email",
    "telephone": "phone",
    "id_contrat": "contract_id",
    "type_contrat": "contract_type",
    "date_debut": "start_date",
    "date_fin": "end_date",
    "statut_contrat": "contract_status",
    "prime_annuelle": "annual_premium",
    "frequence_paiement": "payment_frequency",
    "mode_paiement": "payment_method",
    "agence_code": "agency_code",
    "date_creation": "creation_date",
    "date_modification": "modification_date",
    "date_reclamation": "claim_date",
    "montant_reclamation": "claim_amount",
    "reclamation_status": "claim_status",
    "filiale": "branch",
    # Extended fields (Tranche A)
    "date_sinistre": "loss_date",
    "montant_couverture": "coverage_amount",
    "franchise": "deductible",
    "montant_indemnise": "indemnity_amount",
    "date_resiliation": "cancellation_date",
    "statut_paiement": "payment_status",
    "canal_acquisition": "acquisition_channel",
    "courtier_id": "broker_id",
    "produit_code": "product_code",
    "nombre_reclamations": "claim_count",
    # Tranche B
    "taux_remboursement": "reimbursement_rate",
    "consentement_communication": "communication_consent",
    "gestionnaire_id": "manager_id",
    "segment_client": "customer_segment",
    # Tranche C
    "date_observation": "observation_date",
    "version_source": "source_version",
    "source_system": "source_system",
    # Relational model fields
    "id_menage": "household_id",
    "id_reclamation": "claim_id",
    "id_paiement": "payment_id",
    "date_paiement": "payment_date",
    "montant": "amount",
    "previous_contract_id": "previous_contract_id",
}

CATEGORICAL_TRANSLATIONS_EN: dict[str, dict[str, str]] = {
    "civilite": {
        "M.": "Mr.",
        "Mme": "Ms.",
    },
    "type_contrat": {
        "auto": "auto",
        "habitation": "home",
        "vie": "life",
        "voyage": "travel",
    },
    "statut_contrat": {
        "actif": "active",
        "expiré": "expired",
        "suspendu": "suspended",
        "résilié": "cancelled",
    },
    "frequence_paiement": {
        "mensuelle": "monthly",
        "trimestrielle": "quarterly",
        "semestrielle": "semi-annual",
        "annuelle": "annual",
    },
    "mode_paiement": {
        "prélèvement": "direct_debit",
        "carte": "credit_card",
        "virement": "bank_transfer",
        "chèque": "cheque",
    },
    "reclamation_status": {
        "ouvert": "open",
        "en_cours": "in_progress",
        "fermé": "closed",
        "rejeté": "rejected",
    },
    "statut_paiement": {
        "payé": "paid",
        "partiel": "partial",
        "en_retard": "late",
        "impayé": "unpaid",
    },
    "canal_acquisition": {
        "web": "web",
        "courtier": "broker",
        "agence": "agency",
        "téléphone": "phone",
    },
    "segment_client": {
        "particulier": "individual",
        "professionnel": "professional",
        "entreprise": "business",
        "vip": "vip",
    },
}


def localize_insurance_headers(headers: Sequence[str], english: bool = False) -> list[str]:
    """Translate Insurance column headers to English if english is True, else preserve headers."""
    if not english:
        return list(headers)
    return [COLUMN_TRANSLATIONS_EN.get(col, col) for col in headers]


def localize_insurance_row(row: Mapping[str, str], english: bool = False) -> dict[str, str]:
    """Translate Insurance column names and categorical values to English if english is True."""
    if not english:
        return dict(row)
    localized: dict[str, str] = {}
    for col, val in row.items():
        translated_col = COLUMN_TRANSLATIONS_EN.get(col, col)
        cat_map = CATEGORICAL_TRANSLATIONS_EN.get(col)
        translated_val = cat_map.get(val, val) if cat_map and val in cat_map else val
        localized[translated_col] = translated_val
    return localized
