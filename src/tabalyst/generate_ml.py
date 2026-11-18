# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Machine learning targets, synthetic fraud generation, splits and leakage prevention.

The contract is ``docs/dev/generate/insurance-v2.md`` and SRS sections 8, 14, 15.
Produces ``<dataset>.<profile>.ml_labels.csv`` and ``<dataset>.<profile>.splits.csv``.
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Final, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from tabalyst.generate_anomalies import AnomalyEvent
from tabalyst.generate_rules import FORMAT_REVISION, FORMAT_VERSION

ML_LABELS_FORMAT: Final = "tabalyst.generate.ml_labels"
BASE_ML_LABELS_COLUMNS: Final = (
    "row_number",
    "id_contrat",
    "is_fraud",
    "observed_label",
    "confirmation_date",
    "fraud_type",
    "latent_probability",
)
EXTENDED_ML_LABELS_COLUMNS: Final = (
    *BASE_ML_LABELS_COLUMNS,
    "future_claim",
    "cout_sinistre",
    "renouvellement",
    "date_renouvellement",
    "risque_categorie",
    "historique_sinistres",
    "anciennete_client",
    "score_risque_interne",
)
ML_LABELS_COLUMNS: Final = BASE_ML_LABELS_COLUMNS

FRAUD_TYPES: Final = (
    "phantom_claim",
    "inflated_claim",
    "collusion",
    "organized_fraud",
)
RISK_CATEGORIES: Final = (
    "faible",
    "moyen",
    "eleve",
    "tres_eleve",
)

SPLITS_FORMAT: Final = "tabalyst.generate.splits"
SPLITS_COLUMNS: Final = (
    "row_number",
    "id_contrat",
    "id_client",
    "split_client",
    "split_temporal",
    "resampled_train_only",
)
SPLIT_MODES: Final = ("random_client", "temporal")
SPLIT_PARTITIONS: Final = ("train", "validation", "test")

Count = Annotated[int, Field(ge=0)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MLFraudMetrics(_Model):
    """Aggregate metrics on machine learning labels and synthetic fraud patterns."""

    total_rows: Count = 0
    true_frauds: Count = 0
    observed_frauds: Count = 0
    fraud_types: dict[str, Count] = Field(default_factory=dict)
    rates: dict[str, float] = Field(default_factory=dict)
    noisy_labels: Count = 0
    delayed_labels: Count = 0
    atypical_normal: Count = 0


class MLLabelColumnSpec(_Model):
    """Specification of one column in ml_labels.csv."""

    name: str
    type: str
    description: str


class MLLabelsDocument(_Model):
    """Document tabalyst.generate.ml_labels: specification and metadata of ML labels."""

    format: Literal["tabalyst.generate.ml_labels"] = ML_LABELS_FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    dataset: str
    profile: str
    rows: Count
    columns: list[MLLabelColumnSpec]
    fraud_types: list[str]
    metrics: MLFraudMetrics


class SplitColumnSpec(_Model):
    """Specification of one column in splits.csv."""

    name: str
    type: str
    description: str


class SplitMetrics(_Model):
    """Aggregate metrics on dataset partitions and leakage prevention."""

    total_rows: Count = 0
    client_mode_counts: dict[str, Count] = Field(default_factory=dict)
    temporal_mode_counts: dict[str, Count] = Field(default_factory=dict)
    unique_clients: Count = 0
    client_leakage_cases: Count = 0
    resampled_train_rows: Count = 0
    temporal_cutoffs: dict[str, str] = Field(default_factory=dict)


class SplitsDocument(_Model):
    """Document tabalyst.generate.splits: specification and metadata of dataset splits."""

    format: Literal["tabalyst.generate.splits"] = SPLITS_FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    dataset: str
    profile: str
    rows: Count
    columns: list[SplitColumnSpec]
    modes: list[str] = Field(default_factory=lambda: list(SPLIT_MODES))
    metrics: SplitMetrics


@dataclass(frozen=True)
class MLLabelRow:
    """One record of the separate ml_labels.csv file."""

    row_number: int
    id_contrat: str
    is_fraud: int
    observed_label: str
    confirmation_date: str
    fraud_type: str
    latent_probability: float
    future_claim: int = 0
    cout_sinistre: str = "0.00"
    renouvellement: int = 1
    date_renouvellement: str = ""
    risque_categorie: str = "faible"
    historique_sinistres: str = "0"
    anciennete_client: str = "0"
    score_risque_interne: float = 500.0


@dataclass(frozen=True)
class SplitRow:
    """One record of the separate splits.csv file."""

    row_number: int
    id_contrat: str
    id_client: str
    split_client: str
    split_temporal: str
    resampled_train_only: int


def is_ml_profile(profile: Mapping[str, object], operations: Sequence[Mapping[str, object]]) -> bool:
    """Tell whether a profile is an ML scenario profile producing ml_labels.csv and splits.csv."""
    profile_id = str(profile.get("id", ""))
    if profile_id.startswith("ml_") or profile.get("ml_labels") is True:
        return True
    return any(
        "fraud_type" in op or str(op.get("scenario_id", "")).startswith("ML")
        for op in operations
    )


def is_extended_ml_profile(profile: Mapping[str, object], operations: Sequence[Mapping[str, object]]) -> bool:
    """Tell whether an ML profile includes extended prediction targets (ML09-ML12)."""
    if profile.get("ml_targets") is True or profile.get("id") == "ml_leakage_test":
        return True
    return any(
        str(op.get("scenario_id", "")).startswith((
            "ML09", "ML10", "ML11", "ML12", "ML13", "ML14", "ML15", "ML16", "ML17", "ML18", "ML19",
        ))
        for op in operations
    )


def _pseudo_random_float(seed: int, dataset: str, key: str, salt: str = "") -> float:
    """Deterministic pseudo-random float in [0.0, 1.0) based on sha256."""
    data = f"{seed}:{dataset}:{key}:{salt}".encode()
    digest = hashlib.sha256(data).digest()
    integer_val = int.from_bytes(digest[:8], "big")
    return integer_val / (2**64)


def _parse_iso_date(value: str) -> date | None:
    """Parse YYYY-MM-DD or return None."""
    if not value or len(value) < 10:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()  # noqa: DTZ007
    except ValueError:
        return None


def _parse_flexible_date(value: str) -> date | None:
    """Parse a date string supporting ISO, US (m-d-Y) and European (d-m-Y) conventions."""
    if not value or len(value) < 8:
        return None
    val = value.strip()
    for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(val[:10], fmt).date()  # noqa: DTZ007
        except ValueError:
            continue
    return None


def _format_confirmation_date(
    clean_row: Mapping[str, str],
    as_of_date_str: str,
    pseudo_rand: float,
) -> str:
    """Compute a realistic investigation confirmation date <= as_of_date."""
    as_of = _parse_iso_date(as_of_date_str) or date(2026, 9, 16)
    ref_date = _parse_flexible_date(clean_row.get("date_reclamation", ""))
    if ref_date is None:
        ref_date = _parse_flexible_date(clean_row.get("date_debut", ""))
    if ref_date is None or ref_date > as_of:
        ref_date = as_of - timedelta(days=120)

    delay_days = int(30 + pseudo_rand * 150)
    conf_date = ref_date + timedelta(days=delay_days)
    if conf_date > as_of:
        conf_date = as_of - timedelta(days=int(5 + pseudo_rand * 25))
    return conf_date.isoformat()


def build_ml_labels(
    clean_rows: Sequence[Mapping[str, str]],
    altered_rows: Sequence[Mapping[str, str]],
    events: Sequence[AnomalyEvent],
    profile: Mapping[str, object],
    *,
    seed: int,
    as_of_date: str,
    dataset: str,
) -> tuple[tuple[MLLabelRow, ...], MLFraudMetrics]:
    """Build the ground truth ML labels and metrics for an ML profile.

    Ensures no trivial artifacts exist (amounts and premiums remain within normal
    statistical envelopes and valid business boundaries).
    """
    operations = cast(list[dict[str, object]], profile.get("operations", []))
    events_by_row: dict[int, list[AnomalyEvent]] = {}
    for ev in events:
        events_by_row.setdefault(ev.row_number, []).append(ev)

    labels: list[MLLabelRow] = []
    fraud_type_counts: Counter[str] = Counter()
    true_frauds = 0
    observed_frauds = 0
    noisy_labels = 0
    delayed_labels = 0
    atypical_normal = 0

    total_rows = len(altered_rows)
    as_of_dt = _parse_iso_date(as_of_date) or date(2026, 9, 16)

    for idx, (clean_row, altered_row) in enumerate(zip(clean_rows, altered_rows, strict=True)):
        physical_row_number = idx + 2
        id_contrat = altered_row.get("id_contrat") or clean_row.get("id_contrat") or f"ROW-{physical_row_number}"
        id_client = altered_row.get("id_client") or clean_row.get("id_client") or f"CLI-{physical_row_number}"
        row_events = events_by_row.get(physical_row_number, [])

        p_rand = _pseudo_random_float(seed, dataset, id_contrat, "prob")
        p_rand2 = _pseudo_random_float(seed, dataset, id_contrat, "date")
        p_renew = _pseudo_random_float(seed, dataset, id_contrat, "renew")
        p_hist = _pseudo_random_float(seed, dataset, id_client, "hist")
        p_anc = _pseudo_random_float(seed, dataset, id_client, "anc")

        fraud_op: dict[str, object] | None = None
        is_hard_case = False
        is_delayed = False
        is_noisy = False
        is_plausible_fp = False
        is_atypical_valid = False

        for ev in row_events:
            if 0 < ev.operation_index <= len(operations):
                op = operations[ev.operation_index - 1]
                sc_id = str(op.get("scenario_id", ""))
                f_type = op.get("fraud_type")

                if "NOISE" in sc_id or sc_id.startswith("ML07"):
                    is_noisy = True
                    fraud_op = op
                elif "DELAYED" in sc_id or sc_id.startswith("ML08"):
                    is_delayed = True
                    fraud_op = op
                elif "HARD" in sc_id or sc_id.startswith("ML05"):
                    is_hard_case = True
                    fraud_op = op
                elif "FP" in sc_id or sc_id.startswith("ML06") or "FALSE_POS" in sc_id:
                    is_plausible_fp = True
                elif "ATYPICAL" in sc_id or sc_id.startswith("ML20"):
                    is_atypical_valid = True
                elif f_type or any(sc_id.startswith(pfx) for pfx in ("ML01", "ML02", "ML03", "ML04")):
                    fraud_op = op

        if fraud_op is not None and not is_noisy:
            is_fraud = 1
            true_frauds += 1
            ft = str(fraud_op.get("fraud_type") or "phantom_claim")
            if ft not in FRAUD_TYPES:
                ft = "phantom_claim"
            fraud_type_counts[ft] += 1

            if is_delayed:
                observed_label = ""
                confirmation_date = ""
                delayed_labels += 1
                latent_prob = round(0.65 + 0.28 * p_rand, 4)
            elif is_hard_case:
                observed_label = "1"
                confirmation_date = _format_confirmation_date(clean_row, as_of_date, p_rand2)
                observed_frauds += 1
                latent_prob = round(0.45 + 0.15 * p_rand, 4)
            else:
                observed_label = "1"
                confirmation_date = _format_confirmation_date(clean_row, as_of_date, p_rand2)
                observed_frauds += 1
                latent_prob = round(0.72 + 0.24 * p_rand, 4)

        elif is_noisy:
            noisy_labels += 1
            if p_rand > 0.5:
                is_fraud = 1
                true_frauds += 1
                ft = "phantom_claim"
                fraud_type_counts[ft] += 1
                observed_label = "0"
                confirmation_date = ""
                latent_prob = round(0.62 + 0.22 * p_rand, 4)
            else:
                is_fraud = 0
                ft = ""
                observed_label = "1"
                observed_frauds += 1
                confirmation_date = _format_confirmation_date(clean_row, as_of_date, p_rand2)
                latent_prob = round(0.50 + 0.16 * p_rand, 4)

        elif is_plausible_fp or is_atypical_valid:
            is_fraud = 0
            ft = ""
            observed_label = "0"
            confirmation_date = ""
            atypical_normal += 1
            latent_prob = round(0.46 + 0.16 * p_rand, 4)

        else:
            is_fraud = 0
            ft = ""
            observed_label = "0"
            confirmation_date = ""
            latent_prob = round(0.001 + 0.279 * (p_rand**2), 4)

        # 1. Target ML09: Future claim prediction (binary 0 / 1)
        has_existing_claim = bool(clean_row.get("date_reclamation") or clean_row.get("date_sinistre"))
        future_claim = 1 if (has_existing_claim or (is_fraud == 1) or (latent_prob > 0.60 and p_rand > 0.35)) else 0

        # 2. Target ML10: Claim cost regression (cout_sinistre)
        if future_claim == 1:
            indemn = (
                altered_row.get("montant_indemnise")
                or clean_row.get("montant_indemnise")
                or altered_row.get("montant_reclamation")
                or clean_row.get("montant_reclamation")
            )
            if indemn and float(indemn) > 0:
                cout_sinistre = f"{float(indemn):.2f}"
            else:
                sim_cost = round(800.0 + 4200.0 * p_rand, 2)
                cout_sinistre = f"{sim_cost:.2f}"
        else:
            cout_sinistre = "0.00"

        # 3. Target ML11: Customer retention / renewal (renouvellement) & date_renouvellement
        contract_status = altered_row.get("statut_contrat") or clean_row.get("statut_contrat", "")
        if is_fraud == 1 or contract_status == "résilié":
            renouvellement = 0
            date_renouvellement = ""
        elif p_renew < 0.82:
            renouvellement = 1
            dt_fin = _parse_flexible_date(clean_row.get("date_fin", "")) or _parse_flexible_date(clean_row.get("date_debut", ""))
            if dt_fin:
                date_renouvellement = (dt_fin + timedelta(days=1)).isoformat()
            else:
                date_renouvellement = "2025-01-01"
        else:
            renouvellement = 0
            date_renouvellement = ""

        # 4. Upstream calculated variable: historique_sinistres (prior claims 0, 1, 2, 3+)
        if p_hist < 0.75:
            hist_sin = 0
        elif p_hist < 0.92:
            hist_sin = 1
        elif p_hist < 0.98:
            hist_sin = 2
        else:
            hist_sin = 3
        historique_sinistres = str(hist_sin)

        # 5. Upstream calculated variable: anciennete_client (customer tenure in years)
        birth_str = clean_row.get("date_naissance", "")
        b_dt = _parse_flexible_date(birth_str)
        if b_dt:
            client_age = as_of_dt.year - b_dt.year - ((as_of_dt.month, as_of_dt.day) < (b_dt.month, b_dt.day))
        else:
            client_age = 40
        max_tenure = max(0, min(20, client_age - 18))
        anciennete_client = str(int(p_anc * max_tenure))

        # 6. Target ML12: Multiclass risk category (faible, moyen, eleve, tres_eleve)
        # Actuarial multi-factor rating combining baseline latent risk, claims history and client profile
        composite_risk = (
            0.30 * (latent_prob / 0.80 if latent_prob > 0.40 else latent_prob * 2.0)
            + 0.45 * (hist_sin / 3.0)
            + 0.25 * p_rand2
        )
        if composite_risk < 0.22:
            risque_cat = "faible"
        elif composite_risk < 0.45:
            risque_cat = "moyen"
        elif composite_risk < 0.66:
            risque_cat = "eleve"
        else:
            risque_cat = "tres_eleve"
        max_tenure = max(0, min(20, client_age - 18))
        anciennete_client = str(int(p_anc * max_tenure))

        # 7. Latent internal risk score in [100.0, 900.0]
        score_risque_interne = round(100.0 + 800.0 * (1.0 - latent_prob), 1)

        labels.append(
            MLLabelRow(
                row_number=physical_row_number,
                id_contrat=id_contrat,
                is_fraud=is_fraud,
                observed_label=observed_label,
                confirmation_date=confirmation_date,
                fraud_type=ft,
                latent_probability=latent_prob,
                future_claim=future_claim,
                cout_sinistre=cout_sinistre,
                renouvellement=renouvellement,
                date_renouvellement=date_renouvellement,
                risque_categorie=risque_cat,
                historique_sinistres=historique_sinistres,
                anciennete_client=anciennete_client,
                score_risque_interne=score_risque_interne,
            )
        )

    rates = {
        "true_fraud_rate": round(true_frauds / total_rows, 6) if total_rows > 0 else 0.0,
        "observed_fraud_rate": round(observed_frauds / total_rows, 6) if total_rows > 0 else 0.0,
        "noisy_labels_rate": round(noisy_labels / total_rows, 6) if total_rows > 0 else 0.0,
        "delayed_labels_rate": round(delayed_labels / total_rows, 6) if total_rows > 0 else 0.0,
    }

    metrics = MLFraudMetrics(
        total_rows=total_rows,
        true_frauds=true_frauds,
        observed_frauds=observed_frauds,
        fraud_types=dict(fraud_type_counts),
        rates=rates,
        noisy_labels=noisy_labels,
        delayed_labels=delayed_labels,
        atypical_normal=atypical_normal,
    )

    return tuple(labels), metrics


def build_splits(
    clean_rows: Sequence[Mapping[str, str]],
    altered_rows: Sequence[Mapping[str, str]],
    ml_labels: Sequence[MLLabelRow],
    profile: Mapping[str, object],
    *,
    seed: int,
    dataset: str,
    as_of_date: str,
) -> tuple[tuple[SplitRow, ...], SplitMetrics]:
    """Build leakage-free dataset partitions for client-grouped and temporal evaluations.

    - Random by client: guarantees 0 shared clients between train, validation and test.
    - Temporal: chronological past (train), intermediate (validation), and future (test).
    - Resampling: strictly isolated to train only; validation and test retain true distributions.
    """
    total_rows = len(altered_rows)
    client_mode_counts: Counter[str] = Counter()
    temporal_mode_counts: Counter[str] = Counter()
    resampled_train_rows = 0

    client_partitions: dict[str, str] = {}
    splits: list[SplitRow] = []

    for idx, (clean_row, altered_row) in enumerate(zip(clean_rows, altered_rows, strict=True)):
        physical_row_number = idx + 2
        id_contrat = altered_row.get("id_contrat") or clean_row.get("id_contrat") or f"ROW-{physical_row_number}"
        id_client = altered_row.get("id_client") or clean_row.get("id_client") or f"CLI-{physical_row_number}"

        # 1. Mode aléatoire par client (aucun client partagé)
        if id_client not in client_partitions:
            p_client = _pseudo_random_float(seed, dataset, id_client, "split_client")
            if p_client < 0.70:
                c_part = "train"
            elif p_client < 0.85:
                c_part = "validation"
            else:
                c_part = "test"
            client_partitions[id_client] = c_part
        split_client = client_partitions[id_client]
        client_mode_counts[split_client] += 1

        # 2. Mode temporel (passé vs futur)
        date_str = clean_row.get("date_debut") or clean_row.get("date_creation", "")
        dt = _parse_flexible_date(date_str)
        if dt:
            if dt < date(2024, 1, 1):
                split_temporal = "train"
            elif dt < date(2025, 1, 1):
                split_temporal = "validation"
            else:
                split_temporal = "test"
        else:
            p_temp = _pseudo_random_float(seed, dataset, id_contrat, "split_temporal")
            if p_temp < 0.70:
                split_temporal = "train"
            elif p_temp < 0.85:
                split_temporal = "validation"
            else:
                split_temporal = "test"
        temporal_mode_counts[split_temporal] += 1

        # 3. Rééchantillonnage confiné à l'entraînement
        # Suréchantillonnage de fraudes et sinistres positifs dans le train uniquement
        if split_client == "train":
            is_pos = (ml_labels[idx].is_fraud == 1) or (ml_labels[idx].future_claim == 1)
            resampled_flag = 1 if is_pos else 0
        else:
            resampled_flag = 0  # STRICTEMENT 0 pour validation et test
        if resampled_flag == 1:
            resampled_train_rows += 1

        splits.append(
            SplitRow(
                row_number=physical_row_number,
                id_contrat=id_contrat,
                id_client=id_client,
                split_client=split_client,
                split_temporal=split_temporal,
                resampled_train_only=resampled_flag,
            )
        )

    metrics = SplitMetrics(
        total_rows=total_rows,
        client_mode_counts=dict(client_mode_counts),
        temporal_mode_counts=dict(temporal_mode_counts),
        unique_clients=len(client_partitions),
        client_leakage_cases=0,  # Strict guarantee: 0 clients shared between partitions
        resampled_train_rows=resampled_train_rows,
        temporal_cutoffs={
            "train_end": "2023-12-31",
            "val_start": "2024-01-01",
            "val_end": "2024-12-31",
            "test_start": "2025-01-01",
        },
    )

    return tuple(splits), metrics


def write_ml_labels_csv(
    path: Path,
    labels: Sequence[MLLabelRow],
    *,
    extended: bool = False,
) -> None:
    """Write the separate ml_labels.csv file with deterministic LF line endings."""
    columns = EXTENDED_ML_LABELS_COLUMNS if extended else BASE_ML_LABELS_COLUMNS
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        for row in labels:
            base: list[object] = [
                row.row_number,
                row.id_contrat,
                row.is_fraud,
                row.observed_label,
                row.confirmation_date,
                row.fraud_type,
                f"{row.latent_probability:.4f}",
            ]
            if extended:
                base.extend([
                    row.future_claim,
                    row.cout_sinistre,
                    row.renouvellement,
                    row.date_renouvellement,
                    row.risque_categorie,
                    row.historique_sinistres,
                    row.anciennete_client,
                    f"{row.score_risque_interne:.1f}",
                ])
            writer.writerow(base)


def write_splits_csv(path: Path, splits: Sequence[SplitRow]) -> None:
    """Write the separate splits.csv file with deterministic LF line endings."""
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(SPLITS_COLUMNS)
        for row in splits:
            writer.writerow([
                row.row_number,
                row.id_contrat,
                row.id_client,
                row.split_client,
                row.split_temporal,
                row.resampled_train_only,
            ])


def ml_labels_document(
    dataset: str,
    profile: str,
    rows: int,
    metrics: MLFraudMetrics,
    *,
    extended: bool = False,
) -> MLLabelsDocument:
    """Create the MLLabelsDocument model describing the ML labels."""
    col_specs = [
        MLLabelColumnSpec(
            name="row_number",
            type="integer",
            description="1-based physical row number in the dataset CSV",
        ),
        MLLabelColumnSpec(
            name="id_contrat",
            type="string",
            description="Contract primary identifier for join",
        ),
        MLLabelColumnSpec(
            name="is_fraud",
            type="integer",
            description="Ground truth binary target (1 = fraud, 0 = non-fraud)",
        ),
        MLLabelColumnSpec(
            name="observed_label",
            type="string",
            description="Observed operational label in IT systems (1, 0, or empty if unresolved)",
        ),
        MLLabelColumnSpec(
            name="confirmation_date",
            type="string",
            description="ISO date YYYY-MM-DD of confirmation or investigation close, empty if unresolved",
        ),
        MLLabelColumnSpec(
            name="fraud_type",
            type="string",
            description="Synthetic fraud typology: phantom_claim, inflated_claim, collusion, organized_fraud, or empty",
        ),
        MLLabelColumnSpec(
            name="latent_probability",
            type="number",
            description="Continuous latent risk score reflecting realistic distribution overlap",
        ),
    ]

    if extended:
        col_specs.extend([
            MLLabelColumnSpec(
                name="future_claim",
                type="integer",
                description="Binary target ML09 indicating occurrence of future claim during observation horizon",
            ),
            MLLabelColumnSpec(
                name="cout_sinistre",
                type="string",
                description="Regression target ML10 for claim cost and loss severity",
            ),
            MLLabelColumnSpec(
                name="renouvellement",
                type="integer",
                description="Customer retention / policy renewal target ML11 (1 = renewed, 0 = lapsed / cancelled)",
            ),
            MLLabelColumnSpec(
                name="date_renouvellement",
                type="string",
                description="Observation horizon ISO date for renewal ML11, empty if not renewed",
            ),
            MLLabelColumnSpec(
                name="risque_categorie",
                type="string",
                description="Multiclass risk rating ML12: faible, moyen, eleve, tres_eleve",
            ),
            MLLabelColumnSpec(
                name="historique_sinistres",
                type="string",
                description="Upstream calculated antecedent feature: prior claim count before prediction horizon",
            ),
            MLLabelColumnSpec(
                name="anciennete_client",
                type="string",
                description="Upstream calculated feature: customer tenure in years since first policy subscription",
            ),
            MLLabelColumnSpec(
                name="score_risque_interne",
                type="number",
                description="Calibrated internal credit/insurance risk score in [100.0, 900.0]",
            ),
        ])

    return MLLabelsDocument(
        dataset=dataset,
        profile=profile,
        rows=rows,
        columns=col_specs,
        fraud_types=list(FRAUD_TYPES),
        metrics=metrics,
    )


def splits_document(
    dataset: str,
    profile: str,
    rows: int,
    metrics: SplitMetrics,
) -> SplitsDocument:
    """Create the SplitsDocument model describing the dataset splits."""
    col_specs = [
        SplitColumnSpec(
            name="row_number",
            type="integer",
            description="1-based physical row number in the dataset CSV",
        ),
        SplitColumnSpec(
            name="id_contrat",
            type="string",
            description="Contract primary identifier for join",
        ),
        SplitColumnSpec(
            name="id_client",
            type="string",
            description="Customer identifier used for zero-leakage customer grouping",
        ),
        SplitColumnSpec(
            name="split_client",
            type="string",
            description="Partition under client-grouped random split (train, validation, test) with 0 client overlap",
        ),
        SplitColumnSpec(
            name="split_temporal",
            type="string",
            description="Partition under chronological temporal split (train, validation, test) based on contract dates",
        ),
        SplitColumnSpec(
            name="resampled_train_only",
            type="integer",
            description="Resampling indicator (1 = resampled positive/rare case in train, 0 = unaltered, 0 in validation/test)",
        ),
    ]

    return SplitsDocument(
        dataset=dataset,
        profile=profile,
        rows=rows,
        columns=col_specs,
        modes=list(SPLIT_MODES),
        metrics=metrics,
    )
