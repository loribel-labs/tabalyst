# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The report of a smart sample: the document ``tabalyst.sample`` (design 20.16,
SMART-12, SMART-13).

It carries the plan, what the selection did and the coverage obtained, by family
and weighted. The coverage is the coverage of the catalog of targets of the plan:
it says nothing of phenomena the plan had no target for, and the proportions of
the sample are not those of the population.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import model_serializer

from tabalyst.scanner.models import (
    EngineInfo,
    ScanModel,
    ScanResult,
    SourceInfo,
    _omit_none,
)
from tabalyst.scanner.smart.execute import SmartSelection
from tabalyst.scanner.smart.models import FAMILIES, Family, SamplingPlan

FORMAT = "tabalyst.sample"
FORMAT_VERSION = "0.2.0"
FORMAT_REVISION = 1
SCHEMA_FILE = "tabalyst.sample.schema.json"

# The most missing targets the coverage lists, the heaviest first.
MAX_MISSING = 20

# What a reader must not take the sample for (SMART-01, SMART-13, E13).
STATEMENTS: dict[str, str] = {
    "catalog_not_population": (
        "The coverage is that of the catalog of targets of the plan, not of every "
        "phenomenon of the data: a case no target describes may be missing."
    ),
    "proportions_not_population": (
        "The proportions of the sample are not those of the population: rare "
        "cases are chosen on purpose, so do not estimate the population from it."
    ),
    "heuristic_no_optimum": (
        "The rows are chosen by a greedy cover of a bounded pool of candidates: "
        "the coverage is measured, no optimum is promised."
    ),
}

TargetStatus = Literal["covered", "not_covered", "not_evaluable", "unresolved"]


class SampleRequest(ScanModel):
    """What was asked for: ``rows`` of the dataset, or ``percent`` of them."""

    method: Literal["smart"] = "smart"
    rows: int
    percent: float | None = None
    seed: int

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("percent",))


class SampleOutput(ScanModel):
    """The CSV file written: its name, rows (without the header), columns."""

    name: str
    rows: int
    columns: int
    encoding: str
    delimiter: str
    order: Literal["source"] = "source"


class SampleTimings(ScanModel):
    reading: float
    selection: float
    other: float


class SamplePasses(ScanModel):
    """The readings of the source this sample cost: the first pass when no
    current Scan was stored, and the selection."""

    scan: bool
    selection: bool = True
    total: int


class SampleRun(ScanModel):
    started_at: datetime
    duration_seconds: float
    timings: SampleTimings
    peak_memory_bytes: int | None
    records_read: int
    cells_read: int
    source_verified: bool
    passes: SamplePasses


class Reserve(ScanModel):
    """Ordinary rows of the sample. ``planned`` is what the plan granted;
    ``taken`` what the sample holds, more when targets needed fewer rows than
    they were given (``adjusted``)."""

    planned: int
    taken: int
    adjusted: bool


class Pool(ScanModel):
    """The candidate rows held while reading. ``refused_rows`` are those the
    budget turned away (SMART-11)."""

    per_target: int
    candidate_rows: int
    peak_bytes: int
    budget_bytes: int
    refused_rows: int


class Selection(ScanModel):
    rows: int
    by_cover: int
    by_reserve: int
    shortfall: int
    reserve: Reserve
    pool: Pool


class TargetEntry(ScanModel):
    """What happened to one target of the plan. ``expected`` is the number of
    rows the plan counted exactly, and ``agrees`` whether the reading found as
    many (a difference means the test and the Scan disagree)."""

    id: str
    status: TargetStatus
    reason: str | None = None
    observed: int | None = None
    candidates: int = 0
    expected: int | None = None
    agrees: bool | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _omit_none(handler(self), ("reason", "observed", "expected", "agrees"))


class FamilyCoverage(ScanModel):
    family: Family
    defined: int
    evaluable: int
    covered: int
    weight: float
    weight_covered: float


class Weighted(ScanModel):
    total: float
    covered: float
    share: float | None


class MandatoryCoverage(ScanModel):
    defined: int
    covered: int
    missing: list[str]


class Missing(ScanModel):
    """A target the sample does not cover, with why (SMART-11)."""

    id: str
    family: Family
    obligation: Literal["mandatory", "optional"]
    weight: float
    reason: str


class Verification(ScanModel):
    """The targets whose rows the plan counted exactly, against what the reading
    found. ``disagreed`` lists the targets that differ."""

    checked: int
    agreed: int
    disagreed: list[str]


class Coverage(ScanModel):
    """What the sample covers of the catalog of targets of the plan (SMART-12).

    ``scope`` names it: the targets of the plan, not every phenomenon of the data
    (SMART-13). ``evaluable`` leaves out the targets the sample could not test.
    """

    scope: Literal["target_catalog"] = "target_catalog"
    defined: int
    evaluable: int
    observed: int
    covered: int
    weighted: Weighted
    mandatory: MandatoryCoverage
    families: list[FamilyCoverage]
    missing: list[Missing]
    missing_total: int
    verification: Verification


class SampleDocument(ScanModel):
    """The report of a smart sample."""

    format: Literal["tabalyst.sample"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: int = FORMAT_REVISION
    status: Literal["complete"] = "complete"
    engine: EngineInfo
    source: SourceInfo
    request: SampleRequest
    output: SampleOutput
    run: SampleRun
    plan: SamplingPlan
    selection: Selection
    coverage: Coverage
    statements: list[str]
    targets: list[TargetEntry]


def _entries(plan: SamplingPlan, selection: SmartSelection) -> list[TargetEntry]:
    outcomes = selection.outcome.targets
    entries: list[TargetEntry] = []
    for position, target in enumerate(plan.targets):
        if target.feasibility != "ready":
            entries.append(TargetEntry(id=target.id, status="not_evaluable", reason=target.reason))
            continue
        reason = selection.unresolved.get(position)
        if reason is not None:
            entries.append(TargetEntry(id=target.id, status="unresolved", reason=reason))
            continue
        outcome = outcomes[position]
        expected = (
            target.frequency.count
            if target.frequency.accuracy == "exact" and target.frequency.count is not None
            else None
        )
        entries.append(
            TargetEntry(
                id=target.id,
                status="covered" if outcome.covered else "not_covered",
                reason=outcome.miss,
                observed=outcome.observed,
                candidates=outcome.candidates,
                expected=expected,
                agrees=None if expected is None else expected == outcome.observed,
            )
        )
    return entries


def _coverage(plan: SamplingPlan, entries: list[TargetEntry]) -> Coverage:
    families: dict[str, list[float]] = {family: [0, 0, 0, 0.0, 0.0] for family in FAMILIES}
    missing: list[Missing] = []
    mandatory = mandatory_covered = observed = covered = evaluable = 0
    mandatory_missing: list[str] = []
    total = weight_covered = 0.0
    checked = agreed = 0
    disagreed: list[str] = []
    for target, entry in zip(plan.targets, entries, strict=True):
        row = families[target.family]
        row[0] += 1
        is_mandatory = target.obligation == "mandatory" and entry.status in ("covered", "not_covered")
        if entry.agrees is not None:
            checked += 1
            if entry.agrees:
                agreed += 1
            else:
                disagreed.append(target.id)
        if entry.status not in ("covered", "not_covered"):
            continue
        weight = target.weight.value
        row[1] += 1
        row[3] += weight
        evaluable += 1
        total += weight
        observed += bool(entry.observed)
        if is_mandatory:
            mandatory += 1
        if entry.status == "covered":
            row[2] += 1
            row[4] += weight
            covered += 1
            weight_covered += weight
            mandatory_covered += is_mandatory
        else:
            missing.append(
                Missing(
                    id=target.id,
                    family=target.family,
                    obligation=target.obligation,
                    weight=weight,
                    reason=entry.reason or "size",
                )
            )
            if is_mandatory:
                mandatory_missing.append(target.id)
    missing.sort(key=lambda m: (m.obligation != "mandatory", -m.weight, m.id))
    return Coverage(
        defined=len(plan.targets),
        evaluable=evaluable,
        observed=observed,
        covered=covered,
        weighted=Weighted(
            total=round(total, 6),
            covered=round(weight_covered, 6),
            share=round(weight_covered / total, 6) if total else None,
        ),
        mandatory=MandatoryCoverage(
            defined=mandatory, covered=mandatory_covered, missing=mandatory_missing
        ),
        families=[
            FamilyCoverage(
                family=family,  # type: ignore[arg-type]
                defined=int(values[0]),
                evaluable=int(values[1]),
                covered=int(values[2]),
                weight=round(values[3], 6),
                weight_covered=round(values[4], 6),
            )
            for family, values in families.items()
            if values[0]
        ],
        missing=missing[:MAX_MISSING],
        missing_total=len(missing),
        verification=Verification(checked=checked, agreed=agreed, disagreed=disagreed),
    )


def build_document(
    scan: ScanResult,
    plan: SamplingPlan,
    selection: SmartSelection,
    *,
    percent: float | None,
    output_name: str,
    encoding: str,
    delimiter: str,
    started_at: datetime,
    duration_seconds: float,
    scan_ran: bool,
) -> SampleDocument:
    """The report of a smart sample once its rows are chosen."""
    size = plan.size.requested
    assert size is not None and plan.reserve.rows_granted is not None
    outcome = selection.outcome
    entries = _entries(plan, selection)
    spent = selection.reading_seconds + selection.selection_seconds
    return SampleDocument(
        engine=scan.engine,
        source=scan.source,
        request=SampleRequest(rows=size, percent=percent, seed=plan.method.seed),
        output=SampleOutput(
            name=output_name,
            rows=len(selection.rows),
            columns=len(selection.header),
            encoding=encoding,
            delimiter=delimiter,
        ),
        run=SampleRun(
            started_at=started_at,
            duration_seconds=round(duration_seconds, 6),
            timings=SampleTimings(
                reading=selection.reading_seconds,
                selection=selection.selection_seconds,
                other=round(max(0.0, duration_seconds - spent), 6),
            ),
            peak_memory_bytes=selection.peak_memory,
            records_read=selection.records_read,
            cells_read=selection.cells_read,
            source_verified=True,
            passes=SamplePasses(scan=scan_ran, total=int(scan_ran) + 1),
        ),
        plan=plan,
        selection=Selection(
            rows=len(selection.rows),
            by_cover=outcome.cover_rows,
            by_reserve=outcome.reserve_rows,
            shortfall=outcome.shortfall,
            reserve=Reserve(
                planned=plan.reserve.rows_granted,
                taken=outcome.reserve_rows,
                adjusted=outcome.reserve_rows != plan.reserve.rows_granted,
            ),
            pool=Pool(
                per_target=plan.candidates.per_target_effective,
                candidate_rows=outcome.candidate_rows,
                peak_bytes=outcome.peak_bytes,
                budget_bytes=plan.candidates.budget_bytes,
                refused_rows=outcome.refused_rows,
            ),
        ),
        coverage=_coverage(plan, entries),
        statements=list(STATEMENTS),
        targets=entries,
    )


def sample_document_text(document: SampleDocument, *, indent: bool = False) -> str:
    """The JSON text of the report, as it is written."""
    from tabalyst.json_text import dump_json

    return dump_json(document.model_dump(mode="json", by_alias=True), indent=indent)


def sample_schema() -> dict[str, Any]:
    """The JSON Schema of the report, in validation mode."""
    from tabalyst.scanner.schema import finalize_schema

    schema = SampleDocument.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Tabalyst smart sample"
    schema["description"] = (
        f"Document {FORMAT}, format {FORMAT_VERSION} revision {FORMAT_REVISION}: "
        "the report of a smart sample, with its plan and the coverage obtained."
    )
    finalize_schema(schema, {"format_revision": FORMAT_REVISION})
    return schema


def sample_schema_text() -> str:
    """The schema as the committed file writes it."""
    return json.dumps(sample_schema(), indent=2, ensure_ascii=False) + "\n"
