# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The plan of a smart sample of one dataset (design 20.15, specification 15.3).

Reads a finished Scan and, when it is current, its second-pass document; reads no
source and writes nothing. It says what the sample would aim to cover, the sizes,
the candidate rows to hold, and how many times the source would be read.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from tabalyst.config import SmartSettings
from tabalyst.errors import ConfigurationError
from tabalyst.scan_document import load_document
from tabalyst.scanner.models import DatasetResult, ScanResult
from tabalyst.scanner.planner.models import AnalysisPlan
from tabalyst.scanner.planner.planner import plan_base
from tabalyst.scanner.secondpass.document import load_deep
from tabalyst.scanner.secondpass.models import DeepResult
from tabalyst.scanner.smart.models import (
    FAMILIES,
    Awaiting,
    CandidateBudget,
    Catalog,
    DeepStatus,
    Enrichment,
    FamilySummary,
    Passes,
    PassStep,
    Reserve,
    SamplingPlan,
    SelectionMethod,
    Sizes,
    Summary,
    Target,
)
from tabalyst.scanner.smart.targets import ENRICHES, build_targets
from tabalyst.scanner.smart.weights import WEIGHTS_VERSION

CATALOG_KINDS = frozenset({"value_equals", "value_missing", "pattern_matches", "pattern_other"})


@dataclass(frozen=True, slots=True)
class Smart:
    """What to plan a smart sample for: the ``dataset`` (needed when the Scan has
    several), the ``size`` in rows asked for and the ``seed`` of the selection
    (the seed of the Scan by default)."""

    dataset: str | None = None
    size: int | None = None
    seed: int | None = None


def _dataset(scan: ScanResult, name: str | None) -> DatasetResult:
    """The dataset to sample; raises ``ConfigurationError`` when it cannot be
    told which one."""
    if name is not None:
        for dataset in scan.datasets:
            if dataset.id == name:
                return dataset
        raise ConfigurationError(f"The Scan has no dataset named {name!r}.")
    if len(scan.datasets) != 1:
        raise ConfigurationError(
            "The Scan has several datasets; name the one to sample (on the command line, "
            "choose it with --collection): "
            + ", ".join(dataset.id for dataset in scan.datasets)
            + "."
        )
    return scan.datasets[0]


def _deep_status(scan: ScanResult, deep: DeepResult | None) -> DeepStatus:
    if deep is None:
        return "absent"
    return "current" if deep.base == plan_base(scan) else "stale"


def _order(target: Target) -> tuple[bool, float, str]:
    return (target.obligation != "mandatory", -target.weight.value, target.id)


def _budget(
    targets: list[Target], catalogs: list[Catalog], limit: int
) -> tuple[list[Target], list[Catalog], Counter[str]]:
    """Keep the ``limit`` first targets and say what the catalogs lost."""
    ordered = sorted(targets, key=_order)
    kept, left = ordered[:limit], ordered[limit:]
    dropped = Counter(target.family for target in left)
    if not left:
        return kept, catalogs, dropped
    # Lengths and the like are not part of a catalog: only the targets that list
    # the values or the patterns of a column are.
    lost = Counter(
        (target.family, target.fields[0])
        for target in left
        if target.fields and target.predicate.kind in CATALOG_KINDS
    )
    updated: list[Catalog] = []
    for catalog in catalogs:
        missing = lost.get((catalog.family, catalog.field), 0)
        if missing and catalog.targets:
            updated.append(
                catalog.model_copy(
                    update={
                        "complete": False,
                        "guarantee": "known_values_only" if catalog.targets > missing else "none",
                        "targets": catalog.targets - missing,
                        "reasons": [*catalog.reasons, "target_budget"],
                    }
                )
            )
        else:
            updated.append(catalog)
    return kept, updated, dropped


def _summary(targets: list[Target], dropped: Counter[str]) -> Summary:
    families: list[FamilySummary] = []
    for family in FAMILIES:
        own = [target for target in targets if target.family == family]
        if not own and not dropped[family]:
            continue
        families.append(
            FamilySummary(
                family=family,
                targets=len(own),
                mandatory=sum(t.obligation == "mandatory" for t in own),
                not_evaluable=sum(t.feasibility == "not_evaluable" for t in own),
                dropped=dropped[family],
                total_weight=round(sum(t.weight.value for t in own), 6),
            )
        )
    return Summary(
        targets=len(targets),
        mandatory=sum(t.obligation == "mandatory" for t in targets),
        optional=sum(t.obligation == "optional" for t in targets),
        not_evaluable=sum(t.feasibility == "not_evaluable" for t in targets),
        dropped=sum(dropped.values()),
        total_weight=round(sum(t.weight.value for t in targets), 6),
        families=families,
    )


def _enrichment(
    dataset: DatasetResult,
    deep: DeepResult | None,
    status: DeepStatus,
    analysis_plan: AnalysisPlan | None,
    enumerated: set[str],
) -> Enrichment:
    used = (
        sum(1 for a in deep.analyses if a.dataset == dataset.id and a.status == "complete")
        if deep is not None and status == "current"
        else 0
    )
    awaiting: list[Awaiting] = []
    if analysis_plan is not None and status != "current":
        counts = Counter(
            candidate.analyzer
            for candidate in analysis_plan.candidates
            if candidate.selection.state == "selected"
            and candidate.dataset == dataset.id
            and candidate.analyzer in ENRICHES
            # A column whose every value has a target takes no numeric or pattern
            # target, so what the second pass would count on it adds nothing.
            and not (
                candidate.analyzer in ("numeric_histogram", "pattern_validation")
                and candidate.field in enumerated
            )
        )
        awaiting = [
            Awaiting(family=ENRICHES[analyzer], analyzer=analyzer, analyses=count)
            for analyzer, count in sorted(counts.items())
        ]
    return Enrichment(
        deep=status, used=used, requested=analysis_plan is not None, awaiting=awaiting
    )


def _passes(enrichment: Enrichment, *, scan_stored: bool) -> Passes:
    """The readings of the source between now and the sample, in order. The
    second pass and the selection are never merged (specification 15.6)."""
    if enrichment.deep == "current":
        second = PassStep(
            name="second_pass", needed=False, reads_source=True, reason="enrichment_current"
        )
    elif not enrichment.requested:
        second = PassStep(
            name="second_pass", needed=False, reads_source=True, reason="no_enrichment"
        )
    elif not enrichment.awaiting:
        second = PassStep(
            name="second_pass", needed=False, reads_source=True, reason="nothing_to_add"
        )
    else:
        second = PassStep(
            name="second_pass", needed=True, reads_source=True, reason="enrichment_needed"
        )
    steps = [
        PassStep(
            name="scan",
            needed=not scan_stored,
            reads_source=True,
            reason="scan_stored" if scan_stored else "scan_needed",
        ),
        second,
        PassStep(name="selection", needed=True, reads_source=True, reason="selection"),
    ]
    return Passes(total=sum(step.needed for step in steps), steps=steps)


def _plan_id(plan: SamplingPlan) -> str:
    document = plan.model_dump(mode="json", exclude={"plan_id"})
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def plan_sampling(
    scan: ScanResult,
    *,
    deep: DeepResult | None = None,
    dataset: str | None = None,
    size: int | None = None,
    seed: int | None = None,
    settings: SmartSettings | None = None,
    enrichment: AnalysisPlan | None = None,
    scan_stored: bool = True,
) -> SamplingPlan:
    """Plan a smart sample of one dataset of a finished Scan.

    ``deep`` is the second-pass document of that Scan; it feeds the targets only
    when it is current for the Scan (a stale one is ignored and reported).
    ``enrichment`` is the plan of a second pass the caller accepts to run before
    the sample: when its analyses are not stored yet, the plan announces that
    pass and the targets they would bring as ``awaiting``, and does not list them.
    ``scan_stored`` says that the Scan is stored and will not be read again.
    ``size`` is the number of rows asked for. Raises ``ConfigurationError`` for an
    unknown or ambiguous dataset or a size below 1. Reads nothing else and runs
    nothing.
    """
    if size is not None and size < 1:
        raise ConfigurationError("The size of a sample is at least 1 row.")
    settings = SmartSettings() if settings is None else settings
    target_dataset = _dataset(scan, dataset)
    status = _deep_status(scan, deep)
    usable = deep if status == "current" else None
    built = build_targets(scan, target_dataset, usable, settings, size)
    kept, catalogs, dropped = _budget(built.targets, built.catalogs, settings.max_targets)
    dropped["quality"] += built.capped

    ready = [target for target in kept if target.feasibility == "ready"]
    records = target_dataset.record_count
    # One row each is enough, and a dataset has no more rows than it has.
    mandatory = min(records, sum(target.obligation == "mandatory" for target in ready))
    share = settings.reserve_share
    useful = min(records, math.ceil(len(ready) / (1 - share))) if ready else 0
    reserve_rows = math.ceil(share * size) if size is not None else None
    granted = (
        None
        if size is None or reserve_rows is None
        else min(reserve_rows, max(0, size - mandatory))
    )
    reserve = Reserve(
        share=share,
        rows_requested=reserve_rows,
        rows_granted=granted,
        reduced_by_mandatory=granted is not None and reserve_rows is not None and granted < reserve_rows,
    )

    pool = len(ready) * settings.candidates_per_target
    reserve_pool = granted if granted is not None else math.ceil(useful * share)
    rows = min(records, pool + reserve_pool)
    total_records = sum(d.record_count for d in scan.datasets)
    row_bytes = scan.source.size_bytes // total_records if total_records else None
    expected = None if row_bytes is None else rows * row_bytes
    fits = expected is None or expected <= settings.max_candidate_bytes
    effective = settings.candidates_per_target
    if not fits and row_bytes and ready:
        room = settings.max_candidate_bytes // row_bytes - reserve_pool
        effective = max(1, min(effective, room // len(ready)))

    analysis_plan = enrichment
    enumerated = {
        c.field for c in built.catalogs if c.family == "low_cardinality" and c.complete
    }
    enriched = _enrichment(target_dataset, deep, status, analysis_plan, enumerated)
    plan = SamplingPlan(
        weights_version=WEIGHTS_VERSION,
        plan_id="",
        base=plan_base(scan),
        settings=settings,
        settings_sha256=settings.sha256(),
        dataset=target_dataset.id,
        size=Sizes(
            requested=size, mandatory_bound=mandatory, useful_maximum=useful, records=records
        ),
        reserve=reserve,
        candidates=CandidateBudget(
            per_target=settings.candidates_per_target,
            per_target_effective=effective,
            rows=rows,
            row_bytes=row_bytes,
            bytes_expected=expected,
            budget_bytes=settings.max_candidate_bytes,
            fits=fits,
        ),
        method=SelectionMethod(seed=scan.config.random_seed if seed is None else seed),
        enrichment=enriched,
        passes=_passes(enriched, scan_stored=scan_stored),
        summary=_summary(kept, dropped),
        catalogs=catalogs,
        targets=kept,
    )
    return plan.model_copy(update={"plan_id": _plan_id(plan)})


def plan_sampling_document(
    document: Path | str | dict,
    *,
    deep: DeepResult | Path | None = None,
    dataset: str | None = None,
    size: int | None = None,
    seed: int | None = None,
    settings: SmartSettings | None = None,
    enrichment: AnalysisPlan | None = None,
    scan_stored: bool = True,
) -> SamplingPlan:
    """Plan a smart sample from a Scan document, given as a path or a JSON
    object, and the path of its second-pass document if any.

    Raises ``InputError`` for a Report, which keeps fewer sample values than its
    Scan and cannot be planned from (design 19.4).
    """
    loaded = load_document(document)
    loaded.require_complete_samples("plan a sample")
    stored = load_deep(deep) if isinstance(deep, Path) else deep
    return plan_sampling(
        loaded.base,
        deep=stored,
        dataset=dataset,
        size=size,
        seed=seed,
        settings=settings,
        enrichment=enrichment,
        scan_stored=scan_stored,
    )

