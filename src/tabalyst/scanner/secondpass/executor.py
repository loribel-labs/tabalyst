# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Executor of the second pass (design 20.7, PASS2-01 to PASS2-05).

It reads the source once, with the configuration the Scan recorded, hands each
selected field to its analyses, and publishes nothing until the digest of the
bytes it read has been compared with the Scan's. A result that disagrees with
the Scan, or an analysis that raises, fails alone with its reason.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from tabalyst.config import DeepSettings
from tabalyst.progress import (
    ProgressCallback,
    ProgressPhase,
    byte_progress,
    emit_progress,
)
from tabalyst.scanner.measures import Unrepresentable
from tabalyst.scanner.models import DatasetResult, FieldResult, ScanResult
from tabalyst.scanner.observations import StreamItem
from tabalyst.scanner.paths import FieldPath
from tabalyst.scanner.planner.costmodel import EXACT_SET_STATE_PREFIX
from tabalyst.scanner.planner.models import AnalysisPlan, Candidate
from tabalyst.scanner.planner.registry import default_registry
from tabalyst.scanner.process import peak_memory_bytes
from tabalyst.scanner.readers.factory import open_reader
from tabalyst.scanner.secondpass.accumulators import (
    BinAccumulator,
    DenseAccumulator,
    LengthAccumulator,
    ScanMismatch,
)
from tabalyst.scanner.secondpass.boundaries import place_edges
from tabalyst.scanner.secondpass.document import analysis_domain, analysis_key
from tabalyst.scanner.secondpass.exactset import MEMORY_BUDGET, ExactPool, ExactSet
from tabalyst.scanner.secondpass.frequencies import FrequencyAccumulator
from tabalyst.scanner.secondpass.models import (
    AnalysisOutput,
    AnalysisResult,
    AnalysisStatus,
    DeepResult,
    DeepRun,
    DeepTimings,
    DistinctLimited,
)
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.routing import FieldRoute, Router, field_path
from tabalyst.source_guard import SourceGuard, check_plan_base, prepare_second_pass

# The analyzers this executor can run: those the registry marks ``available``.
EXECUTABLE = frozenset(analyzer.id for analyzer in default_registry().runnable())

Accumulator = (
    DenseAccumulator | BinAccumulator | LengthAccumulator | ExactSet | FrequencyAccumulator
)


@dataclass(frozen=True)
class SecondPassOutcome:
    """A finished second pass: the document and what each analysis did.
    ``read_source`` is false when every result was reused."""

    document: DeepResult
    executed: tuple[str, ...]
    reused: tuple[str, ...]
    skipped: tuple[str, ...]
    read_source: bool


@dataclass(frozen=True)
class _Finished:
    """The end of an analysis that ran: its result, or a limit it met."""

    status: AnalysisStatus
    output: AnalysisOutput
    reason: str | None = None
    detail: str | None = None


@dataclass
class _Job:
    candidate: Candidate
    key: str
    dataset: DatasetResult
    field: FieldResult
    route: FieldRoute | None = None
    accumulator: Accumulator | None = None
    # Why the job could not be set up: it fails without reading.
    failure: tuple[str, str] | None = None


def _timed(items: Iterable[StreamItem], spent: list[float]) -> Iterator[StreamItem]:
    """Items as read, adding to ``spent[0]`` the time the source took to produce
    them."""
    iterator = iter(items)
    while True:
        started = perf_counter()
        try:
            item = next(iterator)
        except StopIteration:
            spent[0] += perf_counter() - started
            return
        spent[0] += perf_counter() - started
        yield item


def _entry(
    candidate: Candidate,
    key: str,
    status: AnalysisStatus,
    *,
    reason: str | None = None,
    detail: str | None = None,
    result: AnalysisOutput | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        id=candidate.id,
        analyzer=candidate.analyzer,
        analyzer_version=candidate.analyzer_version,
        dataset=candidate.dataset,
        field=candidate.field,
        display=candidate.display,
        method=candidate.method or "",
        parameters=candidate.parameters,
        domain=analysis_domain(candidate.analyzer),
        key=key,
        status=status,
        reason=reason,
        detail=detail,
        result=result,
    )


def _grant(candidate: Candidate) -> int:
    """Bytes the plan gave the exact set of a candidate: the firm bound of its
    state."""
    assert candidate.costs is not None
    return sum(
        state.memory.max
        for state in candidate.costs.states
        if state.key.startswith(EXACT_SET_STATE_PREFIX)
    )


def _setup(job: _Job, cells: CellReader, pool: ExactPool) -> None:
    """The accumulator of an analysis, with the route of its field."""
    candidate, field, dataset = job.candidate, job.field, job.dataset
    if candidate.analyzer == "length_distribution":
        job.accumulator = LengthAccumulator()
        return
    if candidate.analyzer == "exact_distinct":
        job.accumulator = ExactSet(pool)
        return
    if candidate.analyzer == "exact_frequencies":
        frequencies = field.values.frequencies
        if frequencies.status != "complete":
            job.failure = ("scan_mismatch", "the frequencies of the scan are not complete")
            return
        job.accumulator = FrequencyAccumulator(frequencies.value.distinct)
        return
    stats = field.numeric.value if field.numeric.status == "complete" else None
    if stats is None:
        job.failure = ("scan_mismatch", "the numeric measure of the scan is not complete")
        return
    if candidate.method == "dense_counts":
        if not isinstance(stats.min, int):
            job.failure = ("scan_mismatch", "the minimum of the scan is not an integer")
            return
        job.accumulator = DenseAccumulator(stats.min, int(candidate.parameters["domain"]))
        return
    placement = place_edges(
        dataset,
        field,
        stats,
        int(candidate.parameters["bins"]),
        str(candidate.parameters["strategy"]),
        cells,
    )
    job.accumulator = BinAccumulator(
        placement.edges,
        strategy=placement.strategy,
        requested=placement.requested,
        source=placement.source,
        reason=placement.reason,
        tight=placement.tight,
    )


def _finish(job: _Job) -> _Finished:
    """The result of an analysis, checked against the Scan."""
    accumulator, field = job.accumulator, job.field
    if isinstance(accumulator, LengthAccumulator):
        return _Finished("complete", accumulator.result(field.strings.content))
    if isinstance(accumulator, ExactSet):
        cardinality = field.values.cardinality
        bound = cardinality.lower_bound if cardinality.status == "limited" else None
        counted = accumulator.result(field.values.count, bound)
        if isinstance(counted, DistinctLimited):
            return _Finished(
                "limited",
                counted,
                reason=MEMORY_BUDGET,
                detail=(
                    f"stopped after {counted.values_read} values, "
                    f"at least {counted.lower_bound} distinct"
                ),
            )
        return _Finished("complete", counted)
    if isinstance(accumulator, FrequencyAccumulator):
        frequencies = field.values.frequencies
        assert frequencies.status == "complete"
        return _Finished(
            "complete", accumulator.result(frequencies.value, field.values.count)
        )
    assert field.numeric.status == "complete" and accumulator is not None
    return _Finished("complete", accumulator.result(field.numeric.value))


def _fail(job: _Job, exc: Exception) -> AnalysisResult:
    if isinstance(exc, ScanMismatch):
        return _entry(job.candidate, job.key, "failed", reason="scan_mismatch", detail=str(exc))
    if isinstance(exc, Unrepresentable):
        return _entry(job.candidate, job.key, "failed", reason="unrepresentable")
    return _entry(
        job.candidate, job.key, "failed", reason="analysis_error", detail=type(exc).__name__
    )


def _conclude(job: _Job) -> AnalysisResult:
    """The entry of a job once the source has been read."""
    candidate, key = job.candidate, job.key
    if job.failure is not None:
        reason, detail = job.failure
        return _entry(candidate, key, "failed", reason=reason, detail=detail)
    assert job.route is not None
    if job.route.failure is not None:
        return _entry(candidate, key, "failed", reason="analysis_error", detail=job.route.failure)
    try:
        finished = _finish(job)
    except Exception as exc:  # noqa: BLE001 - one analysis fails alone
        return _fail(job, exc)
    return _entry(
        candidate,
        key,
        finished.status,
        reason=finished.reason,
        detail=finished.detail,
        result=finished.output,
    )


def pending_candidates(plan: AnalysisPlan, previous: DeepResult | None) -> list[Candidate]:
    """The selected analyses that a run has to compute: those with an executor
    whose result ``previous`` does not hold under the same key (CACHE-04)."""
    usable = (
        {a.key for a in previous.analyses if a.status == "complete"}
        if previous is not None and previous.base == plan.base
        else set()
    )
    return [
        candidate
        for candidate in plan.candidates
        if candidate.selection.state == "selected"
        and candidate.execution.available
        and candidate.analyzer in EXECUTABLE
        and analysis_key(plan.base, candidate) not in usable
    ]


def run_second_pass(
    scan: ScanResult,
    source: Path,
    plan: AnalysisPlan,
    *,
    settings: DeepSettings | None = None,
    previous: DeepResult | None = None,
    on_progress: ProgressCallback | None = None,
) -> SecondPassOutcome:
    """Run the selected analyses of ``plan`` over ``source`` and return the
    second-pass document, writing nothing.

    Results of ``previous`` with the same key are kept, and the source is not
    read at all when nothing is left to compute (CACHE-04). Selected analyses
    that have no executor are ``skipped``. Raises ``StalePlan``, ``StaleSource``
    or ``SourceNotReadable`` (design 20.6) before and after the reading: no
    document is returned then.
    """
    check_plan_base(plan, scan)
    settings = DeepSettings() if settings is None else settings
    started_at = datetime.now(UTC)
    start = perf_counter()
    selected = [c for c in plan.candidates if c.selection.state == "selected"]
    usable = (
        {a.key: a for a in previous.analyses if a.status == "complete"}
        if previous is not None and previous.base == plan.base
        else {}
    )
    entries: dict[str, AnalysisResult] = {}
    jobs: list[_Job] = []
    reused: list[str] = []
    skipped: list[str] = []
    fields = {(d.id, f.id): (d, f) for d in scan.datasets for f in d.fields}
    for candidate in selected:
        key = analysis_key(plan.base, candidate)
        if not candidate.execution.available or candidate.analyzer not in EXECUTABLE:
            entries[candidate.id] = _entry(candidate, key, "skipped", reason="not_available")
            skipped.append(candidate.id)
        elif key in usable:
            entries[candidate.id] = usable[key]
            reused.append(candidate.id)
        else:
            dataset, field = fields[(candidate.dataset, candidate.field)]
            jobs.append(_Job(candidate, key, dataset, field))

    reading = [0.0]
    consume = 0.0
    router = Router({})
    verified = False
    if jobs:
        guard: SourceGuard = prepare_second_pass(plan, scan, source)
        cells = CellReader(scan.config)
        # The exact sets of the run share what the plan gave them (MEM-06).
        pool = ExactPool(
            sum(
                _grant(job.candidate)
                for job in jobs
                if job.candidate.analyzer == "exact_distinct"
            )
        )
        routes: dict[tuple[str, FieldPath], FieldRoute] = {}
        for job in jobs:
            try:
                _setup(job, cells, pool)
            except Exception as exc:  # noqa: BLE001 - one analysis fails alone
                job.failure = ("analysis_error", type(exc).__name__)
                continue
            where = (job.dataset.id, field_path(job.field.path))
            route = routes.get(where)
            if route is None:
                route = routes[where] = FieldRoute(cells, None, None)
            accumulator = job.accumulator
            if isinstance(accumulator, LengthAccumulator):
                route.lengths = accumulator
            elif isinstance(accumulator, ExactSet):
                route.distinct = accumulator
            elif isinstance(accumulator, FrequencyAccumulator):
                route.frequencies = accumulator
            else:
                route.numeric = accumulator
            job.route = route
        emit_progress(
            on_progress,
            source,
            ProgressPhase.READING,
            detail="second pass",
            bytes_read=0,
            bytes_total=scan.source.size_bytes,
        )
        reader = open_reader(
            source, scan.config, byte_progress(on_progress, source, scan.source.size_bytes)
        )
        router = Router(routes)
        consume_started = perf_counter()
        router.consume(_timed(reader, reading))
        consume = perf_counter() - consume_started
        summary = reader.summary()
        guard.finish(summary.sha256, summary.bytes_read)
        verified = True
        for job in jobs:
            entries[job.candidate.id] = _conclude(job)

    analyses = [entries[candidate.id] for candidate in selected]
    duration = perf_counter() - start
    analysis_time = max(0.0, consume - reading[0])
    document = DeepResult(
        status="complete" if all(a.status == "complete" for a in analyses) else "partial",
        base=plan.base,
        settings=settings,
        settings_sha256=settings.sha256(),
        plan=plan,
        run=DeepRun(
            started_at=started_at,
            duration_seconds=round(duration, 6),
            timings=DeepTimings(
                reading=round(reading[0], 6),
                analysis=round(analysis_time, 6),
                other=round(max(0.0, duration - reading[0] - analysis_time), 6),
            ),
            workers=1,
            peak_memory_bytes=peak_memory_bytes(),
            source_read=bool(jobs),
            source_verified=verified,
            records_read=router.records_read,
            cells_read=router.cells_read,
            executed=len(jobs),
            reused=len(reused),
            skipped=len(skipped),
        ),
        analyses=analyses,
    )
    return SecondPassOutcome(
        document=document,
        executed=tuple(job.candidate.id for job in jobs),
        reused=tuple(reused),
        skipped=tuple(skipped),
        read_source=bool(jobs),
    )

