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
from tabalyst.scanner.planner.costmodel import (
    EXACT_SET_STATE_PREFIX,
    PERIOD_MEMO_ENTRIES,
)
from tabalyst.scanner.planner.models import AnalysisPlan, Candidate
from tabalyst.scanner.planner.registry import default_registry
from tabalyst.scanner.planner.relations import column_floats
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
from tabalyst.scanner.secondpass.patterns import (
    PatternAccumulator,
    derive_from_samples,
    pattern_entry,
)
from tabalyst.scanner.secondpass.pearson import ColumnFeed, PairAccumulator
from tabalyst.scanner.secondpass.periods import PeriodAccumulator
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.routing import FieldRoute, Router, field_path
from tabalyst.source_guard import SourceGuard, check_plan_base, prepare_second_pass

# The analyzers this executor can run: those the registry marks ``available``.
EXECUTABLE = frozenset(analyzer.id for analyzer in default_registry().runnable())

Accumulator = (
    DenseAccumulator
    | BinAccumulator
    | LengthAccumulator
    | ExactSet
    | FrequencyAccumulator
    | PatternAccumulator
    | PeriodAccumulator
    | PairAccumulator
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
    # The second column of a pair, which reads through feeds and no route.
    partner: FieldResult | None = None
    reads_pair: bool = False
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
        partner=candidate.partner,
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


def _setup_pair(
    job: _Job,
    cells: CellReader,
    feeds: dict[tuple[str, FieldPath], ColumnFeed],
) -> None:
    """The accumulator of a pair. A pair whose rows the complete sample of the
    Scan holds is counted from them now and reads nothing; the others get the
    feed of each column, shared with the other pairs that use it."""
    candidate, dataset = job.candidate, job.dataset
    first, second = job.field, job.partner
    assert second is not None
    min_pairs = int(candidate.parameters["min_pairs"])
    if not candidate.execution.requires_source:
        sample = dataset.records.sample
        ids = [first.id, second.id]
        if sample is None or not sample.complete or not sample.covers(ids):
            raise ScanMismatch("the scan no longer holds every row of the pair")
        columns = [column_floats(sample.rows, field_id, cells, lenient=False) for field_id in ids]
        left, right = ColumnFeed(cells), ColumnFeed(cells)
        left.numbers, right.numbers = columns[0][1], columns[1][1]
        pair = PairAccumulator(left, right, min_pairs)
        pair.add(columns[0][0], columns[1][0])
        job.accumulator = pair
        return
    columns_of = []
    for field in (first, second):
        where = (dataset.id, field_path(field.path))
        feed = feeds.get(where)
        if feed is None:
            feed = feeds[where] = ColumnFeed(cells)
        columns_of.append(feed)
    job.accumulator = PairAccumulator(columns_of[0], columns_of[1], min_pairs)
    job.reads_pair = True


def _setup(job: _Job, cells: CellReader, pool: ExactPool, scan: ScanResult) -> None:
    """The accumulator of an analysis, with the route of its field."""
    candidate, field, dataset = job.candidate, job.field, job.dataset
    if candidate.analyzer == "pattern_validation":
        entry = (
            pattern_entry(scan.derived.patterns.fields, dataset.id, field.id)
            if scan.derived is not None and scan.derived.patterns is not None
            else None
        )
        if entry is None:
            job.failure = ("scan_mismatch", "the scan has no inferred patterns for the field")
            return
        accumulator = PatternAccumulator(entry, scan.config.pattern_inference.max_value_length)
        job.accumulator = accumulator
        if not candidate.execution.requires_source:
            derive_from_samples(accumulator, field)
        return
    if candidate.analyzer == "temporal_distribution":
        temporal = field.temporal.value if field.temporal.status == "complete" else None
        if temporal is None or len(temporal.kinds) != 1:
            job.failure = ("scan_mismatch", "the scan has no single temporal kind for the field")
            return
        job.accumulator = PeriodAccumulator(
            str(candidate.parameters["granularity"]), temporal.kinds[0].kind
        )
        return
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
    if isinstance(accumulator, PatternAccumulator):
        source = "source" if job.candidate.execution.requires_source else "samples"
        return _Finished("complete", accumulator.result(field.values.count, source))
    if isinstance(accumulator, PairAccumulator):
        partner = job.partner
        assert partner is not None
        if field.numeric.status != "complete" or partner.numeric.status != "complete":
            raise ScanMismatch("the numeric measure of the scan is not complete")
        accumulator.check(field.numeric.value, partner.numeric.value)
        source = "source" if job.candidate.execution.requires_source else "samples"
        return _Finished("complete", accumulator.result(source))
    if isinstance(accumulator, PeriodAccumulator):
        assert field.temporal.status == "complete"
        stats = field.temporal.value
        return _Finished(
            "complete", accumulator.result(stats.kinds[0].count, stats.ambiguous)
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
    if job.route is not None and job.route.failure is not None:
        return _entry(candidate, key, "failed", reason="analysis_error", detail=job.route.failure)
    pair = job.accumulator
    if isinstance(pair, PairAccumulator):
        broken = pair.failure or pair.first.failure or pair.second.failure
        if broken is not None:
            return _entry(candidate, key, "failed", reason="analysis_error", detail=broken)
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


def reading_candidates(plan: AnalysisPlan, previous: DeepResult | None) -> list[Candidate]:
    """The pending analyses that need the source: the others are answered by the
    Scan alone (the patterns of a field whose every distinct value it holds)."""
    return [
        candidate
        for candidate in pending_candidates(plan, previous)
        if candidate.execution.requires_source
    ]


def run_second_pass(
    scan: ScanResult,
    source: Path,
    plan: AnalysisPlan,
    *,
    settings: DeepSettings | None = None,
    previous: DeepResult | None = None,
    skip_reading: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> SecondPassOutcome:
    """Run the selected analyses of ``plan`` over ``source`` and return the
    second-pass document, writing nothing.

    Results of ``previous`` with the same key are kept, and the source is not
    read at all when nothing is left to compute (CACHE-04). Selected analyses
    that have no executor are ``skipped``; so are those that need the source
    when ``skip_reading`` is given (a reason code such as ``source_unavailable``):
    the source is then neither opened nor checked, and what the Scan or the
    stored results can answer is still computed. Raises ``StalePlan``, ``StaleSource``
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
        elif skip_reading is not None and candidate.execution.requires_source:
            entries[candidate.id] = _entry(candidate, key, "skipped", reason=skip_reading)
            skipped.append(candidate.id)
        else:
            dataset, field = fields[(candidate.dataset, candidate.field)]
            partner = (
                None
                if candidate.partner is None
                else fields[(candidate.dataset, candidate.partner)][1]
            )
            jobs.append(_Job(candidate, key, dataset, field, partner=partner))

    read_jobs: list[_Job] = []
    reading = [0.0]
    consume = 0.0
    router = Router({})
    verified = False
    if jobs:
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
        feeds: dict[tuple[str, FieldPath], ColumnFeed] = {}
        # An analysis the Scan can answer alone (the patterns of a field whose
        # every distinct value it holds) does not read the source.
        for job in jobs:
            try:
                if job.candidate.analyzer == "pearson_correlation":
                    _setup_pair(job, cells, feeds)
                    continue
                _setup(job, cells, pool, scan)
            except ScanMismatch as exc:
                job.failure = ("scan_mismatch", str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 - one analysis fails alone
                job.failure = ("analysis_error", type(exc).__name__)
                continue
            if not job.candidate.execution.requires_source:
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
            elif isinstance(accumulator, PatternAccumulator):
                route.patterns = accumulator
            elif isinstance(accumulator, PeriodAccumulator):
                route.periods = accumulator
                route.memo_entries = PERIOD_MEMO_ENTRIES
            else:
                route.numeric = accumulator
            job.route = route
        read_jobs = [job for job in jobs if job.route is not None or job.reads_pair]
        if read_jobs:
            guard: SourceGuard = prepare_second_pass(plan, scan, source)
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
            pairs = [
                (job.dataset.id, job.accumulator)
                for job in read_jobs
                if isinstance(job.accumulator, PairAccumulator) and job.reads_pair
            ]
            router = Router(routes, feeds, pairs)
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
            source_read=bool(read_jobs),
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
        read_source=bool(read_jobs),
    )

