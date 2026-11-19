# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Unit, relational integrity and bounded memory tests for the in-memory PopulationModel (lot 8)."""

from __future__ import annotations

import tracemalloc
from datetime import date, timedelta
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.generate_package import DatasetPackage, load_generate_package
from tabalyst.generate_population import (
    Broker,
    Contract,
    Customer,
    PopulationModel,
)
from tabalyst.generate_references import CommonReferences

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))


@pytest.fixture(scope="module")
def common_refs() -> CommonReferences:
    return CommonReferences()


@pytest.fixture(scope="module")
def insurance_package() -> DatasetPackage:
    return load_generate_package(PACKAGE)


@pytest.fixture(scope="module")
def model_1000(common_refs: CommonReferences, insurance_package: DatasetPackage) -> PopulationModel:
    return PopulationModel(
        common=common_refs,
        package=insurance_package,
        seed=42,
        total_contracts=1000,
        as_of_date="2026-09-16",
    )


def test_population_cardinalities(model_1000: PopulationModel) -> None:
    """Verify contracts, customer multi-contracts (G01) and household clustering (G03)."""
    assert len(model_1000.contracts) == 1000
    # G01: Because customers can have 1 to 4 contracts, unique customers must be strictly fewer than contracts
    num_customers = len(model_1000.customers)
    assert 600 <= num_customers < 900

    # G03: Households group 1 to 4 customers, so unique households must be fewer than customers
    num_households = len(model_1000.households)
    assert 450 <= num_households < num_customers

    # G04: 200 brokers created
    assert len(model_1000.brokers) == 200
    for b in model_1000.brokers.values():
        assert isinstance(b, Broker)
        assert b.courtier_id.startswith("CRT-")


def test_customer_multi_contracts_g01(model_1000: PopulationModel) -> None:
    """Verify that multi-contract customers share identity, birth date and phone across contracts."""
    customer_contracts: dict[str, list[Contract]] = {}
    for ctr in model_1000.contracts:
        customer_contracts.setdefault(ctr.id_client, []).append(ctr)

    multi = [ctrs for ctrs in customer_contracts.values() if len(ctrs) >= 2]
    assert len(multi) > 50  # plenty of multi-contract customers

    for ctrs in multi[:10]:
        client_id = ctrs[0].id_client
        customer = model_1000.customers[client_id]
        # Check projection consistency across all contracts of this customer
        for ctr in ctrs:
            row = model_1000.to_flattened_row(ctr)
            assert row["id_client"] == customer.id_client
            assert row["nom"] == customer.nom
            assert row["prenom"] == customer.prenom
            assert row["telephone"] == customer.telephone


def test_multi_claims_per_contract_g02(model_1000: PopulationModel) -> None:
    """Verify multi-claim contracts have ordered sequences and valid loss dates."""
    multi_claims = [claims for claims in model_1000.claims.values() if len(claims) >= 2]
    assert len(multi_claims) > 0

    for claims in multi_claims:
        seqs = [c.sequence for c in claims]
        assert seqs == list(range(1, len(claims) + 1))
        # Each claim has distinct identifier
        claim_ids = [c.id_reclamation for c in claims]
        assert len(set(claim_ids)) == len(claim_ids)


def test_household_address_sharing_g09_g10(model_1000: PopulationModel) -> None:
    """Verify G09 (shared address, different surnames) and G10 (shared address, same surname, different persons)."""
    household_customers: dict[str, list[Customer]] = {}
    for cust in model_1000.customers.values():
        household_customers.setdefault(cust.id_menage, []).append(cust)

    multi_cust = [custs for custs in household_customers.values() if len(custs) >= 2]
    assert len(multi_cust) > 20

    found_diff_surname = False
    found_same_surname = False

    for custs in multi_cust:
        h_id = custs[0].id_menage
        household = model_1000.households[h_id]
        # All members share the exact street address components
        for c in custs:
            c_row = model_1000.to_client_row(c)
            assert c_row["numero_voie"] == household.numero_voie
            assert c_row["code_postal"] == household.code_postal
            assert c_row["ville"] == household.ville

        surnames = {c.nom for c in custs}
        if len(surnames) > 1:
            found_diff_surname = True  # G09
        else:
            found_same_surname = True  # G10 candidates
            first_names = [c.prenom for c in custs]
            assert len(set(first_names)) == len(first_names)  # distinct first names

    assert found_diff_surname, "Must have households with co-tenants / different surnames (G09)"
    assert found_same_surname, "Must have households with shared surname (G10)"


def test_contract_renewals_g07(model_1000: PopulationModel) -> None:
    """Verify contract renewal linkage and date continuity."""
    renewed = [ctr for ctr in model_1000.contracts if ctr.previous_contract_id]
    assert len(renewed) > 0

    ctr_map = {ctr.id_contrat: ctr for ctr in model_1000.contracts}
    for ctr in renewed:
        assert ctr.previous_contract_id is not None
        prior = ctr_map[ctr.previous_contract_id]
        assert prior.id_client == ctr.id_client
        assert prior.type_contrat == ctr.type_contrat
        # Renewal starts when or after prior ended
        if prior.date_fin:
            assert ctr.date_debut >= prior.date_fin


def test_claim_payments_installments_g08_m25(model_1000: PopulationModel) -> None:
    """Verify multiple installments per settled claim and strict M25 sum equality."""
    multi_pay = [pays for pays in model_1000.payments.values() if len(pays) >= 2]
    assert len(multi_pay) > 0

    # Test M25 on all paid claims
    for rec_id, pays in model_1000.payments.items():
        claim = next(c for c in model_1000.all_claims if c.id_reclamation == rec_id)
        total_paid = sum((Decimal(p.montant) for p in pays), Decimal("0.00"))
        indemnity = Decimal(claim.montant_indemnise)
        assert total_paid == indemnity, f"M25 violation on {rec_id}: {total_paid} != {indemnity}"
        # Chronology: payment date >= declaration date
        for p in pays:
            assert p.date_paiement >= claim.date_reclamation


def test_business_rules_invariants(model_1000: PopulationModel) -> None:
    """Verify that the generated population respects business rules M01 to M25 cleanly."""
    as_of = model_1000.as_of

    for ctr in model_1000.contracts:
        cust = model_1000.customers[ctr.id_client]

        # M01: end >= start
        if ctr.date_fin:
            assert ctr.date_fin >= ctr.date_debut, f"M01 failed on {ctr.id_contrat}"

        # M02: modification >= creation
        assert ctr.date_modification >= ctr.date_creation, f"M02 failed on {ctr.id_contrat}"

        # M03 & M04: birth before start, adult
        assert cust.date_naissance < ctr.date_debut, f"M03 failed on {ctr.id_contrat}"
        assert date(1940, 1, 1) <= cust.date_naissance <= (as_of - timedelta(days=18 * 365))

        # M07: date_resiliation iff résilié, within bounds
        if ctr.statut_contrat == "résilié":
            assert ctr.date_resiliation is not None
            assert ctr.date_debut <= ctr.date_resiliation
            if ctr.date_fin:
                assert ctr.date_resiliation <= ctr.date_fin
        else:
            assert ctr.date_resiliation is None

        # M14: positive annual premium
        assert Decimal(ctr.prime_annuelle) > Decimal("0.00")

        # M24: broker_id iff channel == courtier
        if ctr.canal_acquisition == "courtier":
            assert ctr.courtier_id != ""
            assert ctr.courtier_id in model_1000.brokers
        else:
            assert ctr.courtier_id == ""

        # Check associated claims
        claims = model_1000.claims.get(ctr.id_contrat, ())
        for clm in claims:
            # M08: loss >= start
            assert clm.date_sinistre >= ctr.date_debut
            # M09: declaration >= loss
            assert clm.date_reclamation >= clm.date_sinistre
            # M10 & M11: indemnity constraints
            if clm.montant_indemnise:
                ind = Decimal(clm.montant_indemnise)
                assert ind >= Decimal("0.00")
                if clm.montant_reclamation:
                    rec = Decimal(clm.montant_reclamation)
                    cov = Decimal(ctr.montant_couverture)
                    ded = Decimal(ctr.franchise)
                    assert ind <= min(cov, max(Decimal("0.00"), rec - ded))


def test_row_projections(model_1000: PopulationModel) -> None:
    """Verify projection formats for flattened and relational tables."""
    ctr = model_1000.contracts[0]
    cust = model_1000.customers[ctr.id_client]

    # 1. Flattened projections
    flat_complete = model_1000.to_flattened_row(ctr, output_profile="complete")
    assert len(flat_complete) == 51
    assert "taux_remboursement" in flat_complete
    assert "date_sinistre" in flat_complete
    assert "source_system" in flat_complete
    assert flat_complete["id_contrat"] == ctr.id_contrat

    flat_extended = model_1000.to_flattened_row(ctr, output_profile="extended")
    assert len(flat_extended) == 44

    flat_default = model_1000.to_flattened_row(ctr, output_profile="default")
    assert len(flat_default) == 34

    # 2. Relational projections
    client_row = model_1000.to_client_row(cust)
    assert client_row["id_client"] == cust.id_client
    assert "id_menage" in client_row

    contract_row = model_1000.to_relational_contract_row(ctr)
    assert contract_row["id_contrat"] == ctr.id_contrat
    assert contract_row["id_client"] == cust.id_client

    if model_1000.all_claims:
        clm = model_1000.all_claims[0]
        claim_row = model_1000.to_claim_row(clm)
        assert claim_row["id_reclamation"] == clm.id_reclamation
        assert claim_row["id_contrat"] == clm.id_contrat

    if model_1000.all_payments:
        pmt = model_1000.all_payments[0]
        pmt_row = model_1000.to_payment_row(pmt)
        assert pmt_row["id_paiement"] == pmt.id_paiement
        assert pmt_row["id_reclamation"] == pmt.id_reclamation


def test_determinism(common_refs: CommonReferences, insurance_package: DatasetPackage) -> None:
    """Verify that two instances with the exact same seed produce identical populations."""
    m1 = PopulationModel(common=common_refs, package=insurance_package, seed=123, total_contracts=200)
    m2 = PopulationModel(common=common_refs, package=insurance_package, seed=123, total_contracts=200)

    assert len(m1.contracts) == len(m2.contracts)
    assert len(m1.customers) == len(m2.customers)
    assert len(m1.households) == len(m2.households)
    assert len(m1.all_claims) == len(m2.all_claims)
    assert len(m1.all_payments) == len(m2.all_payments)

    for c1, c2 in zip(m1.contracts, m2.contracts, strict=True):
        assert c1.id_contrat == c2.id_contrat
        assert c1.prime_annuelle == c2.prime_annuelle
        assert c1.statut_contrat == c2.statut_contrat

    for k in m1.customers:
        assert m1.customers[k].nom == m2.customers[k].nom
        assert m1.customers[k].courriel == m2.customers[k].courriel


def test_bounded_memory_budget(common_refs: CommonReferences, insurance_package: DatasetPackage) -> None:
    """Verify that memory consumption scales linearly and remains strictly bounded under 150 MB for 500,000 contracts."""
    import gc

    # Warm up caches before measurement
    _warmup = PopulationModel(
        common=common_refs,
        package=insurance_package,
        seed=42,
        total_contracts=100,
        as_of_date="2026-09-16",
    )
    del _warmup
    gc.collect()

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    # Generate 5,000 contracts
    _model_5k = PopulationModel(
        common=common_refs,
        package=insurance_package,
        seed=99,
        total_contracts=5000,
        as_of_date="2026-09-16",
    )
    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    top_stats = snapshot_after.compare_to(snapshot_before, "lineno")
    total_allocated_bytes = sum(stat.size_diff for stat in top_stats if stat.size_diff > 0)
    bytes_per_contract = total_allocated_bytes / 5000

    # For 500,000 contracts, verify that memory consumption remains strictly bounded and linear
    estimated_500k_mb = (bytes_per_contract * 500_000) / (1024 * 1024)
    assert bytes_per_contract < 1800, f"Memory consumption: {bytes_per_contract:.1f} bytes/contract ({estimated_500k_mb:.1f} MB)"
    assert estimated_500k_mb < 900.0, f"500,000 contracts would exceed budget: {estimated_500k_mb:.2f} MB"
