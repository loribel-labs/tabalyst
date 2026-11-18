# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Machine learning targets, synthetic fraud generation and separate label files.

The contract is ``docs/dev/generate/insurance-v2.md`` and SRS sections 8, 14, 15.
Produces ``<dataset>.<profile>.ml_labels.csv`` and documents synthetic fraud patterns
without trivial artifacts (no 0 premiums, no 999 999 amounts, no explicit fraud flags).
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
ML_LABELS_COLUMNS: Final = (
    "row_number",
    "id_contrat",
    "is_fraud",
    "observed_label",
    "confirmation_date",
    "fraud_type",
    "latent_probability",
)
FRAUD_TYPES: Final = (
    "phantom_claim",
    "inflated_claim",
    "collusion",
    "organized_fraud",
)

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


def is_ml_profile(profile: Mapping[str, object], operations: Sequence[Mapping[str, object]]) -> bool:
    """Tell whether a profile is an ML scenario profile producing ml_labels.csv."""
    profile_id = str(profile.get("id", ""))
    if profile_id.startswith("ml_") or profile.get("ml_labels") is True:
        return True
    return any(
        "fraud_type" in op or str(op.get("scenario_id", "")).startswith("ML")
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


def _format_confirmation_date(
    clean_row: Mapping[str, str],
    as_of_date_str: str,
    pseudo_rand: float,
) -> str:
    """Compute a realistic investigation confirmation date <= as_of_date."""
    as_of = _parse_iso_date(as_of_date_str) or date(2026, 9, 16)
    ref_date = _parse_iso_date(clean_row.get("date_reclamation", ""))
    if ref_date is None:
        ref_date = _parse_iso_date(clean_row.get("date_debut", ""))
    if ref_date is None or ref_date > as_of:
        ref_date = as_of - timedelta(days=120)

    # Delay between declaration and fraud investigation conclusion: 30 to 180 days
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

    for idx, (clean_row, altered_row) in enumerate(zip(clean_rows, altered_rows, strict=True)):
        physical_row_number = idx + 2
        id_contrat = altered_row.get("id_contrat") or clean_row.get("id_contrat") or f"ROW-{physical_row_number}"
        row_events = events_by_row.get(physical_row_number, [])

        p_rand = _pseudo_random_float(seed, dataset, id_contrat, "prob")
        p_rand2 = _pseudo_random_float(seed, dataset, id_contrat, "date")

        # Check whether any event on this row belongs to an ML / fraud scenario
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
            # Genuine fraud case (ML01, ML02, ML03, ML04, ML05, ML08)
            is_fraud = 1
            true_frauds += 1
            ft = str(fraud_op.get("fraud_type") or "phantom_claim")
            if ft not in FRAUD_TYPES:
                ft = "phantom_claim"
            fraud_type_counts[ft] += 1

            if is_delayed:
                # ML08: Delayed investigation - operational status unresolved
                observed_label = ""
                confirmation_date = ""
                delayed_labels += 1
                latent_prob = round(0.65 + 0.28 * p_rand, 4)
            elif is_hard_case:
                # ML05: Hard case near the decision boundary
                observed_label = "1"
                confirmation_date = _format_confirmation_date(clean_row, as_of_date, p_rand2)
                observed_frauds += 1
                latent_prob = round(0.45 + 0.15 * p_rand, 4)
            else:
                # Clear confirmed fraud
                observed_label = "1"
                confirmation_date = _format_confirmation_date(clean_row, as_of_date, p_rand2)
                observed_frauds += 1
                latent_prob = round(0.72 + 0.24 * p_rand, 4)

        elif is_noisy:
            # ML07: Label noise
            noisy_labels += 1
            if p_rand > 0.5:
                # Fraud not detected (false negative in operational label)
                is_fraud = 1
                true_frauds += 1
                ft = "phantom_claim"
                fraud_type_counts[ft] += 1
                observed_label = "0"
                confirmation_date = ""
                latent_prob = round(0.62 + 0.22 * p_rand, 4)
            else:
                # Clean case flagged erroneously (false positive in operational label)
                is_fraud = 0
                ft = ""
                observed_label = "1"
                observed_frauds += 1
                confirmation_date = _format_confirmation_date(clean_row, as_of_date, p_rand2)
                latent_prob = round(0.50 + 0.16 * p_rand, 4)

        elif is_plausible_fp or is_atypical_valid:
            # ML06, ML20: Plausible false positives & valid atypicals
            is_fraud = 0
            ft = ""
            observed_label = "0"
            confirmation_date = ""
            atypical_normal += 1
            # Latent probability in the overlap zone [0.46, 0.62]
            latent_prob = round(0.46 + 0.16 * p_rand, 4)

        else:
            # Regular normal policyholder
            is_fraud = 0
            ft = ""
            observed_label = "0"
            confirmation_date = ""
            # Strongly skewed towards 0, bounded in [0.001, 0.28]
            latent_prob = round(0.001 + 0.279 * (p_rand**2), 4)

        labels.append(
            MLLabelRow(
                row_number=physical_row_number,
                id_contrat=id_contrat,
                is_fraud=is_fraud,
                observed_label=observed_label,
                confirmation_date=confirmation_date,
                fraud_type=ft,
                latent_probability=latent_prob,
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


def write_ml_labels_csv(path: Path, labels: Sequence[MLLabelRow]) -> None:
    """Write the separate ml_labels.csv file with deterministic LF line endings."""
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(ML_LABELS_COLUMNS)
        for row in labels:
            writer.writerow([
                row.row_number,
                row.id_contrat,
                row.is_fraud,
                row.observed_label,
                row.confirmation_date,
                row.fraud_type,
                f"{row.latent_probability:.4f}",
            ])


def ml_labels_document(
    dataset: str,
    profile: str,
    rows: int,
    metrics: MLFraudMetrics,
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

    return MLLabelsDocument(
        dataset=dataset,
        profile=profile,
        rows=rows,
        columns=col_specs,
        fraud_types=list(FRAUD_TYPES),
        metrics=metrics,
    )
