# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generators, in-memory oracle and builders of the identifier uniqueness tests.

The oracle deduplicates explicitly in memory and counts; it never calls Tabalyst and
is the reference of cahier 15.2 (contract ``docs/dev/report/identifier-uniqueness.md``).
Production modules are imported lazily inside the builders, so the tests can be
collected before the lots that create them.
"""

from __future__ import annotations

import csv
import json
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

Row = tuple[str, ...]
HEADER = ["customer_id", "status"]
Normalizer = Callable[[str], str]


def trim(value: str) -> str:
    return value.strip()


def identity(value: str) -> str:
    return value


# ------------------------------------------------------------------ oracle


@dataclass(frozen=True)
class Oracle:
    """What an explicit deduplication of the rows says about the ID column."""

    n: int  # records
    p: int  # records with an ID
    m: int  # records without an ID
    d: int  # distinct analytical IDs
    e: int  # extra copies of whole rows
    u: int  # distinct rows
    r_raw: int  # P - D
    r_residual: int  # repetitions of the ID among the distinct rows
    r_explained: int  # R_raw - R_residual, what the copies explain
    d_after: int  # distinct IDs among the distinct rows
    raw_unique: bool
    unique_after_dedup: bool


def oracle(
    rows: Sequence[Row],
    id_index: int = 0,
    *,
    normalize: Normalizer = identity,
    is_missing: Callable[[str], bool] = lambda value: value == "",
) -> Oracle:
    """Deduplicate ``rows`` for real and count the ID repetitions.

    ``normalize`` is the analytical domain of the ID (trim, for example); the rows are
    always compared as decoded cells, with no normalization (Dedup's identity).
    """
    distinct_rows = list(dict.fromkeys(rows))
    ids = [normalize(row[id_index]) for row in rows if not is_missing(row[id_index])]
    ids_after = [
        normalize(row[id_index])
        for row in distinct_rows
        if not is_missing(row[id_index])
    ]
    n, p = len(rows), len(ids)
    u, d = len(distinct_rows), len(set(ids))
    r_raw = p - d
    r_residual = len(ids_after) - len(set(ids_after))
    return Oracle(
        n=n,
        p=p,
        m=n - p,
        d=d,
        e=n - u,
        u=u,
        r_raw=r_raw,
        r_residual=r_residual,
        r_explained=r_raw - r_residual,
        d_after=len(set(ids_after)),
        raw_unique=n >= 2 and n == p and d == p,
        unique_after_dedup=u >= 2 and len(ids_after) == len(distinct_rows)
        and len(set(ids_after)) == len(ids_after),
    )


def formula(n: int, d: int, e: int) -> dict[str, int]:
    """The fast formula of cahier 5.2, valid when no ID is missing."""
    return {
        "U": n - e,
        "R_raw": n - d,
        "R_explained": e,
        "R_residual": (n - d) - e,
        "D_after_dedup": d,
    }


# -------------------------------------------------------------- generators


def population(
    *,
    distinct_ids: int,
    shared_id_rows: int = 0,
    copies: int = 0,
    seed: int = 1,
    shuffle: bool = True,
) -> list[Row]:
    """Rows ``(id, status)`` with known repetition numbers.

    ``distinct_ids`` rows have their own ID. ``shared_id_rows`` further rows reuse the ID
    of an earlier row with another status (a residual repetition each). ``copies`` exact
    copies of earlier rows are added (an explained repetition each). So
    ``N = distinct_ids + shared_id_rows + copies``, ``E = copies`` (copies are of rows
    that exist once), ``D = distinct_ids`` and ``R_residual = shared_id_rows``.
    """
    if distinct_ids < 1 and (shared_id_rows or copies):
        raise ValueError("shared IDs and copies need at least one distinct ID")
    rng = random.Random(seed)
    base: list[Row] = [(f"A-{i:07d}", "active") for i in range(distinct_ids)]
    for k in range(shared_id_rows):
        source = base[rng.randrange(distinct_ids)]
        base.append((source[0], f"other-{k}"))
    rows = list(base)
    for _ in range(copies):
        rows.append(rng.choice(base))
    if shuffle:
        rng.shuffle(rows)
    return rows


def random_population(rng: random.Random) -> list[Row]:
    """A small random population with copies, shared IDs and sometimes missing IDs."""
    ids = [f"I{n}" for n in range(rng.randint(1, 12))] + ([""] if rng.random() < 0.3 else [])
    statuses = ["a", "b", "c"]
    pool = [(rng.choice(ids), rng.choice(statuses)) for _ in range(rng.randint(1, 15))]
    return [rng.choice(pool) for _ in range(rng.randint(0, 60))]


def write_csv(
    directory: Path, name: str, rows: Iterable[Row], header: Sequence[str] = HEADER
) -> Path:
    path = directory / name
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(rows)
    return path


# ---------------------------------------------------- the product (lazy)


def facts(
    *,
    n: int,
    d: int | None,
    e: int | None = None,
    present: int | None = None,
    scope_complete: bool = True,
    eligible: bool = True,
    distinct_accuracy: str = "exact",
    distinct_source: str = "scan.values.cardinality",
    domain: str = "analytical",
    stages_changed_values: bool = False,
    duplicate_accuracy: str = "exact",
    duplicate_source: str = "scan.records.duplicates",
    extra_duplicates: Sequence[tuple[str, int | None, str]] = (),
    identity_name: str = "full_decoded_csv_row_v1",
    sha256: str = "0" * 64,
):
    """``UniquenessFacts`` (contract 9) for given counts; ``e=None`` means disabled.

    ``extra_duplicates`` adds sources as ``(source, value, accuracy)``.
    """
    from tabalyst.identifier_uniqueness import (
        DistinctEvidence,
        DuplicateEvidence,
        UniquenessFacts,
    )

    present = n if present is None else present
    sources = []
    if e is not None or duplicate_accuracy == "disabled":
        sources.append(
            DuplicateEvidence(
                value=e,
                source=duplicate_source,
                accuracy=duplicate_accuracy,
                identity=identity_name,
                report=None,
            )
        )
    for source, value, accuracy in extra_duplicates:
        sources.append(
            DuplicateEvidence(
                value=value,
                source=source,
                accuracy=accuracy,
                identity=identity_name,
                report=None,
            )
        )
    return UniquenessFacts(
        dataset="rows",
        eligible=eligible,
        records=n,
        present=present,
        missing=n - present,
        scope_complete=scope_complete,
        source_sha256=sha256,
        distinct=None
        if d is None
        else DistinctEvidence(
            value=d,
            source=distinct_source,
            accuracy=distinct_accuracy,
            domain=domain,
            stages_changed_values=stages_changed_values,
        ),
        duplicates=tuple(sources),
        rejected=(),
    )


def assess(**options):
    """``assess_identifier_uniqueness`` on ``facts(**options)``, as a JSON dictionary."""
    from tabalyst.identifier_uniqueness import assess_identifier_uniqueness

    result = assess_identifier_uniqueness(facts(**options))
    return None if result is None else json.loads(result.model_dump_json())


def report_document(source: Path, **options) -> dict:
    """The Report JSON of a CSV (lot 3 wires the options such as ``dedup_report``)."""
    from tabalyst import analyze_csv
    from tabalyst.report_config import ReportConfig

    profile = analyze_csv(source, ReportConfig(**options) if options else None)
    return json.loads(profile.model_dump_json())


def uniqueness_of(document: dict, column_id: str, dataset: str = "rows") -> dict | None:
    """The ``identifier_uniqueness`` object of a column in a Report document."""
    for item in document["report"]["datasets"]:
        if item["id"] != dataset:
            continue
        for column in item["columns"]:
            if column["id"] == column_id or column["name"] == column_id:
                return column["summary"].get("identifier_uniqueness")
    raise KeyError(column_id)
