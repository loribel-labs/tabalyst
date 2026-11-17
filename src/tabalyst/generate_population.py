# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""In-memory relational population model for synthetic Insurance generation (contract section 8)."""

from __future__ import annotations

import random
import sys
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from tabalyst.generate_truth import TruthLine

from tabalyst.generate_draws import (
    inflation_factor,
    power_law_weights,
    seasonal_factor,
    truncated_pareto,
)
from tabalyst.generate_insurance import (
    BRANCHES,
    CLAIM_COUNTS,
    CLIENT_SEGMENTS,
    COVERAGE_CAPS,
    DEDUCTIBLES,
    FRESH_CLAIM_DAYS,
    MONTHLY_METHODS,
    PAYMENT_STATUSES,
    PRODUCT_CODES,
    REIMBURSEMENT_RATES,
    SETTLED_CLAIM_DAYS,
    TRIP_DAYS,
    TRIP_WINDOW_DAYS,
    InsuranceReferences,
    _age,
    _claim_amount,
    _day,
    _email_missing,
    _money,
    _pick,
    _premium_factor,
)
from tabalyst.generate_package import DatasetPackage
from tabalyst.generate_references import CommonProvider, CommonReferences

HOUSEHOLD_SIZE_WEIGHTS: tuple[list[int], list[int]] = ([1, 2, 3, 4], [75, 20, 4, 1])
CUSTOMER_CONTRACT_WEIGHTS: tuple[list[int], list[int]] = ([1, 2, 3, 4], [70, 22, 6, 2])
PAYMENT_INSTALLMENT_WEIGHTS: tuple[list[int], list[int]] = ([1, 2, 3], [65, 25, 10])

# Pre-interned identifiers and codes to keep memory strictly bounded under 150 MB for 500,000 rows
_INTERNED_MANAGERS = tuple(sys.intern(f"GES-{i:03d}") for i in range(1, 51))
_INTERNED_BROKERS = tuple(sys.intern(f"CRT-{i:04d}") for i in range(101, 301))
_BROKER_ZIPF_WEIGHTS: Final[list[float]] = power_law_weights(len(_INTERNED_BROKERS), alpha=1.0)

ROW_ORDERS: Final[frozenset[str]] = frozenset({"default", "branch", "chronological", "agency", "shuffled"})


def _seasonal_day(rng: random.Random, start: date, end: date, peak_month: int) -> date:
    """Draw a day with seasonal frequency peaking at peak_month (harmonic D09)."""
    diff = (end - start).days
    if diff <= 0:
        return start
    d1 = start + timedelta(days=rng.randint(0, diff))
    d2 = start + timedelta(days=rng.randint(0, diff))
    f1 = seasonal_factor(d1, peak_month=peak_month, amplitude=0.4)
    f2 = seasonal_factor(d2, peak_month=peak_month, amplitude=0.4)
    return d1 if rng.random() * (f1 + f2) < f1 else d2


RELATIONAL_CLIENTS_FIELDS: Final[tuple[str, ...]] = (
    "id_client", "id_menage", "civilite", "prenom", "nom", "date_naissance", "sexe",
    "langue_preferee", "numero_voie", "type_voie", "nom_voie", "orientation",
    "appartement", "ville", "province_code", "province_nom", "code_postal",
    "pays_code", "courriel", "telephone", "segment_client", "consentement_communication",
)

RELATIONAL_CONTRATS_FIELDS: Final[tuple[str, ...]] = (
    "id_contrat", "id_client", "filiale", "type_contrat", "produit_code", "date_debut",
    "date_fin", "statut_contrat", "prime_annuelle", "frequence_paiement", "mode_paiement",
    "agence_code", "canal_acquisition", "courtier_id", "gestionnaire_id", "date_creation",
    "date_modification", "date_resiliation", "statut_paiement", "montant_couverture",
    "franchise", "taux_remboursement", "previous_contract_id",
)

RELATIONAL_RECLAMATIONS_FIELDS: Final[tuple[str, ...]] = (
    "id_reclamation", "id_contrat", "date_sinistre", "date_reclamation",
    "montant_reclamation", "montant_indemnise", "reclamation_status",
)

RELATIONAL_PAIEMENTS_FIELDS: Final[tuple[str, ...]] = (
    "id_paiement", "id_reclamation", "id_contrat", "date_paiement",
    "montant", "mode_paiement", "statut_paiement",
)


class Household:
    """Compact physical household entity with shared residence (G03, G09, G10)."""

    __slots__ = (
        "appartement",
        "code_postal",
        "family_name",
        "household_seq",
        "language",
        "nom_voie",
        "numero_voie",
        "orientation",
        "pays_code",
        "province_code",
        "province_nom",
        "type_voie",
        "ville",
    )

    def __init__(
        self,
        household_seq: int,
        numero_voie: str,
        type_voie: str,
        nom_voie: str,
        orientation: str,
        appartement: str,
        ville: str,
        province_code: str,
        province_nom: str,
        code_postal: str,
        pays_code: str,
        family_name: str,
        language: str,
    ) -> None:
        self.household_seq = household_seq
        self.numero_voie = sys.intern(numero_voie)
        self.type_voie = sys.intern(type_voie)
        self.nom_voie = sys.intern(nom_voie)
        self.orientation = sys.intern(orientation)
        self.appartement = sys.intern(appartement)
        self.ville = sys.intern(ville)
        self.province_code = sys.intern(province_code)
        self.province_nom = sys.intern(province_nom)
        self.code_postal = sys.intern(code_postal)
        self.pays_code = sys.intern(pays_code)
        self.family_name = sys.intern(family_name)
        self.language = sys.intern(language)

    @property
    def id_menage(self) -> str:
        return f"MEN-{self.province_code}-{self.household_seq:08d}"


class Customer:
    """Compact insured individual entity (G01)."""

    __slots__ = (
        "birth_ordinal",
        "branch",
        "civilite",
        "consentement_communication",
        "customer_seq",
        "has_email",
        "household_seq",
        "langue_preferee",
        "nom",
        "prenom",
        "province_code",
        "segment_client",
        "sexe",
    )

    def __init__(
        self,
        customer_seq: int,
        household_seq: int,
        province_code: str,
        branch: str,
        civilite: str,
        prenom: str,
        nom: str,
        date_naissance: date,
        sexe: str,
        langue_preferee: str,
        has_email: bool,
        segment_client: str,
        consentement_communication: str,
    ) -> None:
        self.customer_seq = customer_seq
        self.household_seq = household_seq
        self.province_code = sys.intern(province_code)
        self.branch = sys.intern(branch)
        self.civilite = sys.intern(civilite)
        self.prenom = sys.intern(prenom)
        self.nom = sys.intern(nom)
        self.birth_ordinal = date_naissance.toordinal()
        self.sexe = sys.intern(sexe)
        self.langue_preferee = sys.intern(langue_preferee)
        self.has_email = has_email
        self.segment_client = sys.intern(segment_client)
        self.consentement_communication = sys.intern(consentement_communication)

    @property
    def id_client(self) -> str:
        c_prefix = BRANCHES[self.branch][3]
        c_width = BRANCHES[self.branch][4]
        if self.branch == "quebec":
            raw_num = f"{self.customer_seq:0{c_width}d}"
            return f"{c_prefix}{raw_num[:4]}-{raw_num[4:]}"
        return f"{c_prefix}{self.customer_seq:0{c_width}d}"

    @property
    def id_menage(self) -> str:
        return f"MEN-{self.province_code}-{self.household_seq:08d}"

    @property
    def date_naissance(self) -> date:
        return date.fromordinal(self.birth_ordinal)

    @property
    def courriel(self) -> str:
        if not self.has_email:
            return ""
        return f"{self.prenom.lower()}.{self.nom.lower()}.{self.customer_seq}@example.ca"

    @property
    def telephone(self) -> str:
        return f"+1-555-555-{self.customer_seq % 9000 + 1000:04d}"


class Broker:
    """Compact independent insurance broker entity (G04)."""

    __slots__ = ("courtier_id", "filiale", "nom", "province_code")

    def __init__(self, courtier_id: str, nom: str, province_code: str, filiale: str) -> None:
        self.courtier_id = sys.intern(courtier_id)
        self.nom = nom
        self.province_code = sys.intern(province_code)
        self.filiale = sys.intern(filiale)


class Claim:
    """Compact insurance claim entity (G02)."""

    __slots__ = (
        "contract_id_str",
        "contract_seq",
        "decl_ordinal",
        "loss_ordinal",
        "montant_indemnise",
        "montant_reclamation",
        "payments",
        "reclamation_status",
        "sequence",
    )

    def __init__(
        self,
        contract_seq: int,
        sequence: int,
        date_sinistre: date,
        date_reclamation: date,
        montant_reclamation: str,
        montant_indemnise: str,
        reclamation_status: str,
        payments: tuple[Payment, ...] = (),
        contract_id_str: str | None = None,
    ) -> None:
        self.contract_seq = contract_seq
        self.sequence = sequence
        self.loss_ordinal = date_sinistre.toordinal()
        self.decl_ordinal = date_reclamation.toordinal()
        self.montant_reclamation = montant_reclamation
        self.montant_indemnise = montant_indemnise
        self.reclamation_status = sys.intern(reclamation_status)
        self.payments = payments
        self.contract_id_str = sys.intern(contract_id_str) if contract_id_str is not None else sys.intern(f"CTR-{contract_seq:09d}")

    @property
    def id_reclamation(self) -> str:
        return f"REC-{self.contract_seq:08d}-{self.sequence:02d}"

    @property
    def id_contrat(self) -> str:
        return self.contract_id_str

    @property
    def date_sinistre(self) -> date:
        return date.fromordinal(self.loss_ordinal)

    @property
    def date_reclamation(self) -> date:
        return date.fromordinal(self.decl_ordinal)


class Payment:
    """Compact claim indemnity installment payment entity (G08)."""

    __slots__ = (
        "claim_id_str",
        "contract_id_str",
        "mode_paiement",
        "montant",
        "pay_ordinal",
        "payment_seq",
        "sequence",
        "statut_paiement",
    )

    def __init__(
        self,
        payment_seq: int,
        claim_id_str: str,
        contract_id_str: str,
        date_paiement: date,
        montant: str,
        mode_paiement: str,
        statut_paiement: str,
        sequence: int = 1,
    ) -> None:
        self.payment_seq = payment_seq
        self.claim_id_str = claim_id_str
        self.contract_id_str = contract_id_str
        self.pay_ordinal = date_paiement.toordinal()
        self.montant = montant
        self.mode_paiement = sys.intern(mode_paiement)
        self.statut_paiement = sys.intern(statut_paiement)
        self.sequence = sequence

    @property
    def id_paiement(self) -> str:
        return f"PAY-{self.payment_seq:08d}-{self.sequence:02d}"

    @property
    def id_reclamation(self) -> str:
        return self.claim_id_str

    @property
    def id_contrat(self) -> str:
        return self.contract_id_str

    @property
    def date_paiement(self) -> date:
        return date.fromordinal(self.pay_ordinal)


class Contract:
    """Compact insurance policy contract entity (G01, G07)."""

    __slots__ = (
        "agence_code",
        "canal_acquisition",
        "claims",
        "contract_seq",
        "courtier_id",
        "creation_ordinal",
        "customer_seq",
        "end_ordinal",
        "filiale",
        "franchise",
        "frequence_paiement",
        "gestionnaire_id",
        "mode_paiement",
        "modification_ordinal",
        "montant_couverture",
        "previous_contract_id",
        "prime_annuelle",
        "produit_code",
        "resiliation_ordinal",
        "start_ordinal",
        "statut_contrat",
        "statut_paiement",
        "taux_remboursement",
        "type_contrat",
    )

    def __init__(
        self,
        contract_seq: int,
        customer_seq: int,
        filiale: str,
        type_contrat: str,
        produit_code: str,
        date_debut: date,
        date_fin: date | None,
        statut_contrat: str,
        prime_annuelle: str,
        frequence_paiement: str,
        mode_paiement: str,
        agence_code: str,
        canal_acquisition: str,
        courtier_id: str,
        gestionnaire_id: str,
        date_creation: date,
        date_modification: date,
        date_resiliation: date | None,
        statut_paiement: str,
        montant_couverture: str,
        franchise: str,
        taux_remboursement: str,
        previous_contract_id: str | None = None,
        claims: tuple[Claim, ...] = (),
    ) -> None:
        self.contract_seq = contract_seq
        self.customer_seq = customer_seq
        self.filiale = sys.intern(filiale)
        self.type_contrat = sys.intern(type_contrat)
        self.produit_code = sys.intern(produit_code)
        self.start_ordinal = date_debut.toordinal()
        self.end_ordinal = date_fin.toordinal() if date_fin is not None else None
        self.statut_contrat = sys.intern(statut_contrat)
        self.prime_annuelle = prime_annuelle
        self.frequence_paiement = sys.intern(frequence_paiement)
        self.mode_paiement = sys.intern(mode_paiement)
        self.agence_code = sys.intern(agence_code)
        self.canal_acquisition = sys.intern(canal_acquisition)
        self.courtier_id = sys.intern(courtier_id) if courtier_id else ""
        self.gestionnaire_id = sys.intern(gestionnaire_id)
        self.creation_ordinal = date_creation.toordinal()
        self.modification_ordinal = date_modification.toordinal()
        self.resiliation_ordinal = date_resiliation.toordinal() if date_resiliation is not None else None
        self.statut_paiement = sys.intern(statut_paiement)
        self.montant_couverture = sys.intern(montant_couverture)
        self.franchise = sys.intern(franchise)
        self.taux_remboursement = sys.intern(taux_remboursement)
        self.previous_contract_id = previous_contract_id
        self.claims = claims

    @property
    def id_contrat(self) -> str:
        contract_prefix = BRANCHES[self.filiale][5]
        return f"CTR-{contract_prefix}{self.contract_seq:09d}"

    @property
    def id_client(self) -> str:
        c_prefix = BRANCHES[self.filiale][3]
        c_width = BRANCHES[self.filiale][4]
        if self.filiale == "quebec":
            raw_num = f"{self.customer_seq:0{c_width}d}"
            return f"{c_prefix}{raw_num[:4]}-{raw_num[4:]}"
        return f"{c_prefix}{self.customer_seq:0{c_width}d}"

    @property
    def date_debut(self) -> date:
        return date.fromordinal(self.start_ordinal)

    @property
    def date_fin(self) -> date | None:
        return date.fromordinal(self.end_ordinal) if self.end_ordinal is not None else None

    @property
    def date_creation(self) -> date:
        return date.fromordinal(self.creation_ordinal)

    @property
    def date_modification(self) -> date:
        return date.fromordinal(self.modification_ordinal)

    @property
    def date_resiliation(self) -> date | None:
        return date.fromordinal(self.resiliation_ordinal) if self.resiliation_ordinal is not None else None


class LazyMapping(Mapping[str, Customer]):
    """Memory-efficient lazy mapping for dictionary-like access to customers or households."""

    def __init__(self, items: Sequence[Customer], key_fn: str) -> None:
        self._items = items
        self._key_fn = key_fn
        self._cached: dict[str, Customer] | None = None

    def _ensure(self) -> dict[str, Customer]:
        if self._cached is None:
            self._cached = {getattr(item, self._key_fn): item for item in self._items}
        return self._cached

    def __getitem__(self, key: str) -> Customer:
        return self._ensure()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._ensure())

    def __len__(self) -> int:
        return len(self._items)


class PopulationModel:
    """In-memory relational population generator with bounded memory (contract section 8).

    Orchestrates households, customers, brokers, contracts, renewals, claims, and payments
    in memory under 150 MB for 500,000 contracts, supporting both flattened multi-contract CSV
    projections and four relational table projections (clients, contrats, reclamations, paiements).
    """

    def __init__(
        self,
        common: CommonReferences,
        package: DatasetPackage,
        seed: int = 42,
        total_contracts: int = 1000,
        as_of_date: str = "2026-09-16",
        branch: str | None = None,
        m22_cases: int = 0,
        row_order: str = "default",
    ) -> None:
        if row_order not in ROW_ORDERS:
            from tabalyst.errors import ConfigurationError
            raise ConfigurationError(
                f"Unsupported row order: {row_order!r}. Expected one of: "
                f"{', '.join(sorted(ROW_ORDERS))}."
            )
        self.common: CommonProvider = CommonProvider(common)
        self.refs: InsuranceReferences = InsuranceReferences(common, package)
        self.seed = seed
        self.total_contracts = total_contracts
        self.as_of_date_str = as_of_date
        self.as_of = date.fromisoformat(as_of_date)
        self.target_branch = branch
        self.m22_cases = m22_cases
        self.row_order = row_order

        self._households_list: list[Household] = []
        self._customers_list: list[Customer] = []
        self._brokers_list: list[Broker] = []
        self._contracts_list: list[Contract] = []
        self._all_claims: list[Claim] = []
        self._all_payments: list[Payment] = []
        self._m22_claims: list[tuple[Claim, str]] = []

        self._build()

    @property
    def households(self) -> dict[str, Household]:
        return {h.id_menage: h for h in self._households_list}

    @property
    def customers(self) -> dict[str, Customer]:
        return {c.id_client: c for c in self._customers_list}

    @property
    def brokers(self) -> dict[str, Broker]:
        return {b.courtier_id: b for b in self._brokers_list}

    @property
    def contracts(self) -> list[Contract]:
        return self._contracts_list

    @property
    def claims(self) -> dict[str, tuple[Claim, ...]]:
        return {ctr.id_contrat: ctr.claims for ctr in self._contracts_list if ctr.claims}

    @property
    def payments(self) -> dict[str, tuple[Payment, ...]]:
        return {clm.id_reclamation: clm.payments for clm in self._all_claims if clm.payments}

    @property
    def all_claims(self) -> Sequence[Claim]:
        return self._all_claims

    @property
    def all_payments(self) -> Sequence[Payment]:
        return self._all_payments

    def _build(self) -> None:
        """Construct the relational population topology deterministically."""
        rng = random.Random(self.seed)

        # 1. Brokers pool (G04)
        self._build_brokers()

        contracts_created = 0
        household_seq = 0
        customer_seq = 0
        contract_seq = 0
        claim_seq = 0
        payment_seq = 0

        while contracts_created < self.total_contracts:
            household_seq += 1
            if self.target_branch:
                h_branch = self.target_branch
            else:
                h_branch = rng.choices(["principal", "ontario", "quebec"], weights=[200, 25, 50], k=1)[0]

            home_prov, home_share, _, _, _, _ = BRANCHES[h_branch]
            if rng.random() < home_share:
                province = home_prov
            else:
                others = [r for r in self.common.refs.tables["geography/provinces_ca.csv"]
                          if r["province_code"] != home_prov]
                province = _pick(rng, others)["province_code"]

            addr = self.common.address({"province": province}, rng)
            lang = ("en" if rng.random() < 0.80 else "fr") if h_branch == "ontario" else addr["language"]
            h_family = self.common.person({"profile": lang}, rng)["family_name"]

            household = Household(
                household_seq=household_seq,
                numero_voie=addr["street_number"],
                type_voie=addr["street_type"],
                nom_voie=addr["street_name"],
                orientation=addr["street_direction"],
                appartement=addr["unit_number"],
                ville=addr["city"],
                province_code=province,
                province_nom=addr["province_name"],
                code_postal=addr["postal_code"],
                pays_code="CA",
                family_name=h_family,
                language=lang,
            )
            self._households_list.append(household)

            num_customers = rng.choices(HOUSEHOLD_SIZE_WEIGHTS[0], weights=HOUSEHOLD_SIZE_WEIGHTS[1], k=1)[0]
            used_household_first_names: set[str] = set()

            for cust_idx in range(num_customers):
                customer_seq += 1
                c_lang = lang

                # G09 & G10
                if cust_idx == 0:
                    cust_family = h_family
                else:
                    if rng.random() < 0.50:
                        cust_family = self.common.person({"profile": c_lang}, rng)["family_name"]
                    else:
                        cust_family = h_family

                first_name_info = self.common.person({"profile": c_lang}, rng)
                first_name = first_name_info["first_name"]
                while first_name in used_household_first_names:
                    first_name_info = self.common.person({"profile": c_lang}, rng)
                    first_name = first_name_info["first_name"]
                used_household_first_names.add(first_name)

                sex = first_name_info["sex"]
                civilite = "Mme" if sex == "F" and c_lang == "fr" else "M." if c_lang == "fr" else (
                    "Ms" if sex == "F" else "Mr"
                )

                birth = _day(rng, date(1940, 1, 1), self.as_of - timedelta(days=18 * 365 + 6))
                c_age = _age(birth, self.as_of)
                has_email = rng.random() >= _email_missing(c_age)

                segment = rng.choices(CLIENT_SEGMENTS[0], weights=CLIENT_SEGMENTS[1], k=1)[0]
                consent = rng.choices(["true", "false"], weights=[70, 30], k=1)[0]

                customer = Customer(
                    customer_seq=customer_seq,
                    household_seq=household_seq,
                    province_code=province,
                    branch=h_branch,
                    civilite=civilite,
                    prenom=first_name,
                    nom=cust_family,
                    date_naissance=birth,
                    sexe=sex,
                    langue_preferee=c_lang,
                    has_email=has_email,
                    segment_client=segment,
                    consentement_communication=consent,
                )
                self._customers_list.append(customer)

                # Assign contracts (G01)
                num_contracts = rng.choices(
                    CUSTOMER_CONTRACT_WEIGHTS[0], weights=CUSTOMER_CONTRACT_WEIGHTS[1], k=1,
                )[0]
                num_contracts = min(num_contracts, self.total_contracts - contracts_created)

                chosen_products: list[str] = []
                prior_contract_for_renewal: Contract | None = None

                for contract_idx in range(num_contracts):
                    contract_seq += 1
                    contracts_created += 1

                    # G07 Renewal selection
                    is_renewal = (
                        contract_idx > 0
                        and prior_contract_for_renewal is not None
                        and prior_contract_for_renewal.date_fin is not None
                        and prior_contract_for_renewal.date_fin < self.as_of
                        and rng.random() < 0.40
                    )

                    if is_renewal and prior_contract_for_renewal is not None:
                        product_id = prior_contract_for_renewal.type_contrat
                        previous_contract_id = prior_contract_for_renewal.id_contrat
                    else:
                        branch_weights = [r for r in self.refs.tables["branch_contract_weights.csv"]
                                          if r["filiale"] == h_branch]
                        candidates = [r for r in branch_weights if r["contract_type"] not in chosen_products]
                        if not candidates:
                            candidates = branch_weights
                        product_id = _pick(rng, candidates)["contract_type"]
                        chosen_products.append(product_id)
                        previous_contract_id = None

                    product_row = next(r for r in self.refs.tables["contract_types.csv"]
                                       if r["contract_type"] == product_id)

                    adult_start = birth + timedelta(days=18 * 365 + 5)

                    end_date: date | None
                    if is_renewal and prior_contract_for_renewal and prior_contract_for_renewal.date_fin:
                        start_date = prior_contract_for_renewal.date_fin
                        end_date = start_date + timedelta(days=365)
                        c_status = "actif" if end_date >= self.as_of else "expiré"
                    elif product_id == "voyage":
                        start_date = _day(rng, max(adult_start, self.as_of - timedelta(days=TRIP_WINDOW_DAYS)),
                                          self.as_of - timedelta(days=1))
                        end_date = start_date + timedelta(days=rng.randint(*TRIP_DAYS))
                        c_status = "expiré" if end_date < self.as_of else "actif"
                    else:
                        status_pick = _pick(rng, self.refs.tables["contract_statuses.csv"])
                        c_status = status_pick["status"]
                        start_date = _day(rng, max(adult_start, self.as_of - timedelta(days=3650)),
                                          self.as_of - timedelta(days=1))
                        terminal = status_pick["date_end_policy"] == "required_past"
                        end_date = (
                            _day(rng, start_date + timedelta(days=1), self.as_of) if terminal
                            else _day(rng, self.as_of + timedelta(days=30), self.as_of + timedelta(days=365))
                            if rng.random() < 0.80 else None
                        )

                    creation_date = _day(rng, max(adult_start, start_date - timedelta(days=30)), start_date)

                    date_resiliation: date | None = None
                    if c_status == "résilié" and end_date:
                        diff = (end_date - start_date).days
                        offset = rng.randint(1, diff) if diff > 0 else 0
                        date_resiliation = start_date + timedelta(days=offset)

                    frequency = _pick(rng, self.refs.tables["payment_frequencies.csv"])["frequency"]
                    methods = self.refs.tables["payment_methods.csv"]
                    if frequency == "mensuelle":
                        methods = [row for row in methods if row["payment_method"] in MONTHLY_METHODS]
                    method = _pick(rng, methods)["payment_method"]

                    # E16 Simpson's paradox: acquisition channel distribution depends on branch
                    # Ontario has high baseline costs (+80%) and mostly direct sales (80% direct, 10% broker)
                    # Principal and Quebec have lower baseline costs and mostly broker sales (80% broker, 10% direct)
                    if h_branch == "ontario":
                        channel_weights = [80, 10, 5, 5]  # direct, courtier, en_ligne, partenaire
                    else:
                        channel_weights = [10, 80, 5, 5]  # direct, courtier, en_ligne, partenaire
                    channel = rng.choices(
                        ["direct", "courtier", "en_ligne", "partenaire"],
                        weights=channel_weights,
                        k=1,
                    )[0]

                    broker_id = ""
                    if channel == "courtier":
                        # D08 Zipf power-law distribution over brokers
                        broker_id = rng.choices(_INTERNED_BROKERS, weights=_BROKER_ZIPF_WEIGHTS, k=1)[0]

                    base_prem = Decimal(_money(rng, product_row["annual_premium_min"], product_row["annual_premium_max"]))
                    # Baseline branch pricing: Ontario is higher cost (+80%)
                    if h_branch == "ontario":
                        base_prem = (base_prem * Decimal("1.80")).quantize(Decimal("0.01"))
                    # Conditional channel pricing: within each branch, broker-advised policies
                    # carry broader coverage endorsements (+25%)
                    if channel == "courtier":
                        base_prem = (base_prem * Decimal("1.25")).quantize(Decimal("0.01"))

                    # D11: Continuous compound inflation (+2.5% / year relative to 2018)
                    inf_factor = Decimal(f"{inflation_factor(creation_date, date(2018, 1, 1), 0.025):.4f}")
                    prem = (base_prem * _premium_factor(product_id, c_age) * inf_factor).quantize(Decimal("0.01"))

                    agencies = [r for r in self.refs.tables["agencies.csv"] if r["filiale"] == h_branch]
                    agency = _pick(rng, [r for r in agencies if r["city_id"] == addr["city_id"]]
                                   or [r for r in agencies if r["province_code"] == province] or agencies)
                    agency_code = agency["agency_code"]

                    manager_id = rng.choice(_INTERNED_MANAGERS)

                    pay_opts, pay_weights = PAYMENT_STATUSES.get(c_status, (["payé"], [1]))
                    statut_paiement = rng.choices(pay_opts, weights=pay_weights, k=1)[0]

                    cov_opts, cov_weights = COVERAGE_CAPS.get(product_id, ([100000], [1]))
                    cap_val = rng.choices(cov_opts, weights=cov_weights, k=1)[0]
                    montant_couverture = f"{Decimal(cap_val):.2f}"

                    ded_opts, ded_weights = DEDUCTIBLES.get(product_id, ([0], [1]))
                    ded_val = rng.choices(ded_opts, weights=ded_weights, k=1)[0]
                    franchise = f"{Decimal(ded_val):.2f}"

                    prd_opts, prd_weights = PRODUCT_CODES.get(product_id, (["STD"], [1]))
                    # E18: Unseen category - VOY_MULTI was introduced only on 2024-01-01
                    if creation_date < date(2024, 1, 1) and "VOY_MULTI" in prd_opts:
                        valid_pairs = [(c, w) for c, w in zip(prd_opts, prd_weights) if c != "VOY_MULTI"]
                        prd_opts_eff = [p[0] for p in valid_pairs]
                        prd_weights_eff = [p[1] for p in valid_pairs]
                    else:
                        prd_opts_eff = prd_opts
                        prd_weights_eff = prd_weights
                    produit_code = rng.choices(prd_opts_eff, weights=prd_weights_eff, k=1)[0]
                    taux_remboursement = REIMBURSEMENT_RATES.get(produit_code, "0.80")

                    # Claims generation (G02)
                    contract_claims: list[Claim] = []
                    last_event_date = creation_date

                    # Dense but globally rare subpopulation cluster (§12):
                    # 200 consecutive contracts (sequences 501 to 700) exhibiting an abnormally
                    # high 20% claim rate, whereas such events represent < 0.01% globally.
                    is_dense_cluster = (501 <= contract_seq <= 700)
                    if is_dense_cluster:
                        has_claims = rng.random() < 0.20
                    else:
                        has_claims = rng.random() < float(product_row["claim_probability"])
                    if has_claims:
                        num_claims = rng.choices(CLAIM_COUNTS[0], weights=CLAIM_COUNTS[1], k=1)[0]
                        claim_ceiling_date = min(end_date or self.as_of, self.as_of)
                        contract_id_str = f"CTR-{BRANCHES[h_branch][5]}{contract_seq:09d}"

                        for c_seq in range(1, num_claims + 1):
                            claim_seq += 1
                            rec_id_str = f"REC-{contract_seq:08d}-{c_seq:02d}"

                            # D09 Seasonal loss date
                            loss_date = _seasonal_day(
                                rng, start_date, claim_ceiling_date,
                                peak_month=7 if product_id == "voyage" else 1,
                            )
                            decl_date = _day(rng, loss_date, self.as_of)
                            last_event_date = max(last_event_date, decl_date)

                            claim_age_days = (self.as_of - decl_date).days
                            avail_claims = self.refs.tables["claim_statuses.csv"]
                            if claim_age_days > SETTLED_CLAIM_DAYS:
                                avail_claims = [r for r in avail_claims if r["is_terminal"] == "true"] or avail_claims
                            elif claim_age_days < FRESH_CLAIM_DAYS:
                                avail_claims = [r for r in avail_claims if r["is_terminal"] == "false"] or avail_claims
                            picked_claim_status = _pick(rng, avail_claims)
                            c_claim_status = picked_claim_status["status"]

                            claimed_amount = ""
                            if picked_claim_status["amount_policy"] == "required" or rng.random() < 0.65:
                                c_min = float(product_row["claim_amount_min"])
                                c_max = float(product_row["claim_amount_max"])
                                # D04 & D13: 10% of settled claims have heavy-tailed Pareto amounts
                                if c_claim_status == "fermé" and rng.random() < 0.10:
                                    drawn_pareto = Decimal(truncated_pareto(rng, alpha=1.2, low=c_min, high=c_max))
                                    claimed_amount = f"{min(max(drawn_pareto.quantize(Decimal('0.01')), Decimal(c_min)), Decimal(c_max)):.2f}"
                                else:
                                    claimed_amount = _claim_amount(rng, product_row["claim_amount_min"],
                                                                   product_row["claim_amount_max"])

                            montant_indemnise = ""
                            if claimed_amount:
                                rec_amt = Decimal(claimed_amount)
                                cov_amt = Decimal(montant_couverture)
                                ded_amt = Decimal(franchise)
                                max_pay = min(cov_amt, max(Decimal("0.00"), rec_amt - ded_amt))
                                if c_claim_status in {"rejeté", "ouvert"}:
                                    montant_indemnise = "0.00"
                                elif c_claim_status == "fermé":
                                    montant_indemnise = f"{max_pay:.2f}"
                                else:
                                    shares = [Decimal("0.00"), (max_pay * Decimal("0.5")).quantize(Decimal("0.01")), max_pay]
                                    montant_indemnise = f"{rng.choices(shares, weights=[50, 30, 20], k=1)[0]:.2f}"

                            # Installments payments (G08)
                            claim_payments: list[Payment] = []
                            if montant_indemnise and Decimal(montant_indemnise) > Decimal("0.00"):
                                total_pay = Decimal(montant_indemnise)
                                num_installments = rng.choices(
                                    PAYMENT_INSTALLMENT_WEIGHTS[0], weights=PAYMENT_INSTALLMENT_WEIGHTS[1], k=1,
                                )[0]

                                split_amounts: list[Decimal] = []
                                if num_installments == 1:
                                    split_amounts = [total_pay]
                                elif num_installments == 2:
                                    p1 = (total_pay * Decimal("0.40")).quantize(Decimal("0.01"))
                                    split_amounts = [p1, total_pay - p1]
                                else:
                                    p1 = (total_pay * Decimal("0.30")).quantize(Decimal("0.01"))
                                    p2 = (total_pay * Decimal("0.30")).quantize(Decimal("0.01"))
                                    split_amounts = [p1, p2, total_pay - p1 - p2]

                                p_date = decl_date
                                for p_idx, p_amt in enumerate(split_amounts, start=1):
                                    payment_seq += 1
                                    p_date = _day(rng, p_date, self.as_of)
                                    pay_obj = Payment(
                                        payment_seq=payment_seq,
                                        claim_id_str=rec_id_str,
                                        contract_id_str=contract_id_str,
                                        date_paiement=p_date,
                                        montant=f"{p_amt:.2f}",
                                        mode_paiement=method,
                                        statut_paiement="effectué",
                                        sequence=p_idx,
                                    )
                                    claim_payments.append(pay_obj)
                                    self._all_payments.append(pay_obj)

                            claim_obj = Claim(
                                contract_seq=contract_seq,
                                sequence=c_seq,
                                date_sinistre=loss_date,
                                date_reclamation=decl_date,
                                montant_reclamation=claimed_amount,
                                montant_indemnise=montant_indemnise,
                                reclamation_status=c_claim_status,
                                payments=tuple(claim_payments),
                                contract_id_str=contract_id_str,
                            )
                            contract_claims.append(claim_obj)
                            self._all_claims.append(claim_obj)

                    modification_date = _day(rng, last_event_date, self.as_of)

                    contract_obj = Contract(
                        contract_seq=contract_seq,
                        customer_seq=customer_seq,
                        filiale=h_branch,
                        type_contrat=product_id,
                        produit_code=produit_code,
                        date_debut=start_date,
                        date_fin=end_date,
                        statut_contrat=c_status,
                        prime_annuelle=f"{prem:.2f}",
                        frequence_paiement=frequency,
                        mode_paiement=method,
                        agence_code=agency_code,
                        canal_acquisition=channel,
                        courtier_id=broker_id,
                        gestionnaire_id=manager_id,
                        date_creation=creation_date,
                        date_modification=modification_date,
                        date_resiliation=date_resiliation,
                        statut_paiement=statut_paiement,
                        montant_couverture=montant_couverture,
                        franchise=franchise,
                        taux_remboursement=taux_remboursement,
                        previous_contract_id=previous_contract_id,
                        claims=tuple(contract_claims),
                    )
                    self._contracts_list.append(contract_obj)
                    prior_contract_for_renewal = contract_obj

                    if contracts_created >= self.total_contracts:
                        break
                if contracts_created >= self.total_contracts:
                    break

        # Referential integrity breaking for M22 test cases
        if self.m22_cases > 0 and self._all_claims:
            m22_count = min(self.m22_cases, len(self._all_claims))
            for i in range(m22_count):
                claim = self._all_claims[i]
                orig_ctr_id = claim.contract_id_str
                claim.contract_id_str = sys.intern(f"CTR-ORPHAN-{i + 1:06d}")
                self._m22_claims.append((claim, orig_ctr_id))

        # Row ordering and sampling bias mechanisms (E01 to E03)
        if self.row_order == "chronological":
            self._contracts_list.sort(key=lambda c: (c.creation_ordinal, c.start_ordinal, c.contract_seq))
        elif self.row_order == "agency":
            self._contracts_list.sort(key=lambda c: (c.agence_code, c.creation_ordinal, c.contract_seq))
        elif self.row_order == "branch":
            self._contracts_list.sort(key=lambda c: (c.filiale, c.contract_seq))
        elif self.row_order == "shuffled":
            shuf_rng = random.Random(self.seed + 8888)
            shuf_rng.shuffle(self._contracts_list)
        elif self.row_order == "default":
            pass

    def _build_brokers(self) -> None:
        """Create pool of 200 brokers distributed across branches."""
        branches = list(BRANCHES.keys())
        for seq in range(101, 301):
            b_id = f"CRT-{seq:04d}"
            fil = branches[(seq - 101) % len(branches)]
            prov = BRANCHES[fil][0]
            nom = f"Cabinet Courtage {seq}"
            self._brokers_list.append(Broker(b_id, nom, prov, fil))

    def to_flattened_row(self, contract: Contract, output_profile: str = "complete") -> dict[str, str]:
        """Project a contract into the flattened multi-contract CSV row representation."""
        customer = self._customers_list[contract.customer_seq - 1]
        household = self._households_list[customer.household_seq - 1]
        date_fmt = BRANCHES[contract.filiale][2]

        contract_claims = contract.claims
        primary_claim = contract_claims[0] if contract_claims else None

        num_claims = len(contract_claims)
        date_sinistre = primary_claim.date_sinistre.strftime(date_fmt) if primary_claim else ""
        date_rec = primary_claim.date_reclamation.strftime(date_fmt) if primary_claim else ""
        rec_amount = primary_claim.montant_reclamation if primary_claim else ""
        rec_status = primary_claim.reclamation_status if primary_claim else ""
        rec_indemnite = primary_claim.montant_indemnise if primary_claim else ""

        date_res = contract.date_resiliation.strftime(date_fmt) if contract.date_resiliation else ""

        row = {
            "id_client": customer.id_client,
            "civilite": customer.civilite,
            "prenom": customer.prenom,
            "nom": customer.nom,
            "date_naissance": customer.date_naissance.strftime(date_fmt),
            "sexe": customer.sexe,
            "langue_preferee": customer.langue_preferee,
            "numero_voie": household.numero_voie,
            "type_voie": household.type_voie,
            "nom_voie": household.nom_voie,
            "orientation": household.orientation,
            "appartement": household.appartement,
            "ville": household.ville,
            "province_code": household.province_code,
            "province_nom": household.province_nom,
            "code_postal": household.code_postal,
            "pays_code": household.pays_code,
            "courriel": customer.courriel,
            "telephone": customer.telephone,
            "id_contrat": contract.id_contrat,
            "type_contrat": contract.type_contrat,
            "date_debut": contract.date_debut.strftime(date_fmt),
            "date_fin": contract.date_fin.strftime(date_fmt) if contract.date_fin else "",
            "statut_contrat": contract.statut_contrat,
            "prime_annuelle": contract.prime_annuelle,
            "frequence_paiement": contract.frequence_paiement,
            "mode_paiement": contract.mode_paiement,
            "agence_code": contract.agence_code,
            "date_creation": contract.date_creation.strftime(date_fmt),
            "date_modification": contract.date_modification.strftime(date_fmt),
            "date_reclamation": date_rec,
            "montant_reclamation": rec_amount,
            "reclamation_status": rec_status,
            "filiale": contract.filiale,
        }

        if output_profile in {"extended", "complete"}:
            row.update({
                "date_sinistre": date_sinistre,
                "montant_couverture": contract.montant_couverture,
                "franchise": contract.franchise,
                "montant_indemnise": rec_indemnite,
                "date_resiliation": date_res,
                "statut_paiement": contract.statut_paiement,
                "canal_acquisition": contract.canal_acquisition,
                "courtier_id": contract.courtier_id,
                "produit_code": contract.produit_code,
                "nombre_reclamations": str(num_claims),
            })

        if output_profile == "complete":
            row.update({
                "taux_remboursement": contract.taux_remboursement,
                "consentement_communication": customer.consentement_communication,
                "gestionnaire_id": contract.gestionnaire_id,
                "segment_client": customer.segment_client,
            })

        return row

    def to_client_row(self, customer: Customer) -> dict[str, str]:
        """Project a customer into a row of clients.csv."""
        household = self._households_list[customer.household_seq - 1]
        return {
            "id_client": customer.id_client,
            "id_menage": household.id_menage,
            "civilite": customer.civilite,
            "prenom": customer.prenom,
            "nom": customer.nom,
            "date_naissance": customer.date_naissance.isoformat(),
            "sexe": customer.sexe,
            "langue_preferee": customer.langue_preferee,
            "numero_voie": household.numero_voie,
            "type_voie": household.type_voie,
            "nom_voie": household.nom_voie,
            "orientation": household.orientation,
            "appartement": household.appartement,
            "ville": household.ville,
            "province_code": household.province_code,
            "province_nom": household.province_nom,
            "code_postal": household.code_postal,
            "pays_code": household.pays_code,
            "courriel": customer.courriel,
            "telephone": customer.telephone,
            "segment_client": customer.segment_client,
            "consentement_communication": customer.consentement_communication,
        }

    def to_relational_contract_row(self, contract: Contract) -> dict[str, str]:
        """Project a contract into a row of contrats.csv."""
        return {
            "id_contrat": contract.id_contrat,
            "id_client": contract.id_client,
            "filiale": contract.filiale,
            "type_contrat": contract.type_contrat,
            "produit_code": contract.produit_code,
            "date_debut": contract.date_debut.isoformat(),
            "date_fin": contract.date_fin.isoformat() if contract.date_fin else "",
            "statut_contrat": contract.statut_contrat,
            "prime_annuelle": contract.prime_annuelle,
            "frequence_paiement": contract.frequence_paiement,
            "mode_paiement": contract.mode_paiement,
            "agence_code": contract.agence_code,
            "canal_acquisition": contract.canal_acquisition,
            "courtier_id": contract.courtier_id,
            "gestionnaire_id": contract.gestionnaire_id,
            "date_creation": contract.date_creation.isoformat(),
            "date_modification": contract.date_modification.isoformat(),
            "date_resiliation": contract.date_resiliation.isoformat() if contract.date_resiliation else "",
            "statut_paiement": contract.statut_paiement,
            "montant_couverture": contract.montant_couverture,
            "franchise": contract.franchise,
            "taux_remboursement": contract.taux_remboursement,
            "previous_contract_id": contract.previous_contract_id or "",
        }

    def to_claim_row(self, claim: Claim) -> dict[str, str]:
        """Project a claim into a row of reclamations.csv."""
        return {
            "id_reclamation": claim.id_reclamation,
            "id_contrat": claim.id_contrat,
            "date_sinistre": claim.date_sinistre.isoformat(),
            "date_reclamation": claim.date_reclamation.isoformat(),
            "montant_reclamation": claim.montant_reclamation,
            "montant_indemnise": claim.montant_indemnise,
            "reclamation_status": claim.reclamation_status,
        }

    def to_payment_row(self, payment: Payment) -> dict[str, str]:
        """Project an indemnity payment installment into a row of paiements.csv."""
        return {
            "id_paiement": payment.id_paiement,
            "id_reclamation": payment.id_reclamation,
            "id_contrat": payment.id_contrat,
            "date_paiement": payment.date_paiement.isoformat(),
            "montant": payment.montant,
            "mode_paiement": payment.mode_paiement,
            "statut_paiement": payment.statut_paiement,
        }

    def get_table_truth_lines(self, table: str) -> list[TruthLine]:
        """Produce verifiable ground-truth lines for a specific table or flattened output.

        Covers G09 (shared household address with distinct surnames), G10 (near-identical
        household identities with shared surname), and M22 (missing contract reference).
        """
        from tabalyst.generate_truth import TruthLine

        lines: list[TruthLine] = []

        if table in {"clients", "flattened"}:
            # Group customers by household
            household_custs: dict[int, list[Customer]] = {}
            for cust in self._customers_list:
                household_custs.setdefault(cust.household_seq, []).append(cust)

            for h_seq, custs in household_custs.items():
                if len(custs) < 2:
                    continue
                household = self._households_list[h_seq - 1]
                surnames = {c.nom for c in custs}
                is_g09 = len(surnames) > 1
                scenario_id = "G09" if is_g09 else "G10"
                col = "id_menage" if is_g09 else "nom"
                canonical_val = household.id_menage if is_g09 else household.family_name

                if table == "clients":
                    for c in custs:
                        lines.append(TruthLine(
                            truth_id=0,
                            kind="relational",
                            scenario_id=scenario_id,
                            rule_id="",
                            category="valid_atypical",
                            severity="info",
                            rarity_level="uncommon",
                            root_cause_id="",
                            group_id=f"{scenario_id}-{household.id_menage}",
                            event_id=0,
                            row_number=c.customer_seq + 1,  # 1-based, header is 1
                            column=col,
                            canonical_value=canonical_val,
                            expected_detection="uniqueness",
                        ))
                elif table == "flattened":
                    cust_seqs = {c.customer_seq for c in custs}
                    for ctr in self._contracts_list:
                        if ctr.customer_seq in cust_seqs:
                            lines.append(TruthLine(
                                truth_id=0,
                                kind="relational",
                                scenario_id=scenario_id,
                                rule_id="",
                                category="valid_atypical",
                                severity="info",
                                rarity_level="uncommon",
                                root_cause_id="",
                                group_id=f"{scenario_id}-{household.id_menage}",
                                event_id=0,
                                row_number=ctr.contract_seq + 1,
                                column=col,
                                canonical_value=canonical_val,
                                expected_detection="uniqueness",
                            ))

        if table in {"reclamations", "flattened"} and self._m22_claims:
            for claim, orig_ctr_id in self._m22_claims:
                if table == "reclamations":
                    row_num = self._all_claims.index(claim) + 2
                    group = f"M22-{claim.id_reclamation}"
                    lines.append(TruthLine(
                        truth_id=0,
                        kind="rule_violation",
                        scenario_id="M22",
                        rule_id="M22",
                        category="business_rule_violation",
                        severity="critical",
                        rarity_level="single",
                        root_cause_id="",
                        group_id=group,
                        event_id=0,
                        row_number=row_num,
                        column="id_contrat",
                        canonical_value=orig_ctr_id,
                        expected_detection="cross_column",
                    ))
                    lines.append(TruthLine(
                        truth_id=0,
                        kind="relational",
                        scenario_id="M22",
                        rule_id="M22",
                        category="business_rule_violation",
                        severity="critical",
                        rarity_level="single",
                        root_cause_id="",
                        group_id=group,
                        event_id=0,
                        row_number=row_num,
                        column="id_contrat",
                        canonical_value=orig_ctr_id,
                        expected_detection="cross_column",
                    ))
                elif table == "flattened":
                    row_num = claim.contract_seq + 1
                    group = f"M22-{claim.id_reclamation}"
                    lines.append(TruthLine(
                        truth_id=0,
                        kind="rule_violation",
                        scenario_id="M22",
                        rule_id="M22",
                        category="business_rule_violation",
                        severity="critical",
                        rarity_level="single",
                        root_cause_id="",
                        group_id=group,
                        event_id=0,
                        row_number=row_num,
                        column="id_contrat",
                        canonical_value=orig_ctr_id,
                        expected_detection="cross_column",
                    ))
                    lines.append(TruthLine(
                        truth_id=0,
                        kind="relational",
                        scenario_id="M22",
                        rule_id="M22",
                        category="business_rule_violation",
                        severity="critical",
                        rarity_level="single",
                        root_cause_id="",
                        group_id=group,
                        event_id=0,
                        row_number=row_num,
                        column="id_contrat",
                        canonical_value=orig_ctr_id,
                        expected_detection="cross_column",
                    ))

        # Sort lines stably and assign sequential truth_id
        ordered = [replace(line, truth_id=idx) for idx, line in enumerate(sorted(lines, key=TruthLine.sort_key), 1)]
        return ordered
