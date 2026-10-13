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

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter

from tabalyst.config import DeepSettings
from tabalyst.progress import (
    ProgressCallback,
    ProgressPhase,
    byte_progress,
    emit_progress,
)
from tabalyst.scanner.features import CategoryCoder, feature_coder
from tabalyst.scanner.measures import Unrepresentable
from tabalyst.scanner.models import (
    CardinalityComplete,
    CardinalityLimited,
    DatasetResult,
    FieldResult,
    ScanResult,
)
from tabalyst.scanner.observations import StreamItem
from tabalyst.scanner.paths import FieldPath, Key
from tabalyst.scanner.planner.analyzers.measures import measure_memo
from tabalyst.scanner.planner.costmodel import (
    DEFAULT_MEMORY_BUDGET_BYTES,
    EXACT_SET_STATE_PREFIX,
    PERIOD_MEMO_ENTRIES,
)
from tabalyst.scanner.planner.crosstabs import code_rows
from tabalyst.scanner.planner.facts import ROOT_FIELD, date_evidence, matrix_members
from tabalyst.scanner.planner.models import AnalysisPlan, Candidate
from tabalyst.scanner.planner.registry import default_registry
from tabalyst.scanner.planner.relations import column_floats
from tabalyst.scanner.planner.samplerows import cell_text
from tabalyst.scanner.process import peak_memory_bytes
from tabalyst.scanner.readers.factory import open_reader
from tabalyst.scanner.secondpass.accumulators import (
    BinAccumulator,
    DenseAccumulator,
    LengthAccumulator,
    ScanMismatch,
)
from tabalyst.scanner.secondpass.boundaries import place_edges
from tabalyst.scanner.secondpass.crosstab import (
    MAX_EXCEPTION_CELLS,
    CodeFeed,
    CrosstabAccumulator,
)
from tabalyst.scanner.secondpass.document import analysis_domain, analysis_key
from tabalyst.scanner.secondpass.drift import DriftAccumulator
from tabalyst.scanner.secondpass.duplicates import (
    DuplicateAccumulator,
    KeyAccumulator,
    RawFeed,
)
from tabalyst.scanner.secondpass.duplicates import (
    derive_from_samples as duplicates_from_samples,
)
from tabalyst.scanner.secondpass.exactset import MEMORY_BUDGET, ExactPool, ExactSet
from tabalyst.scanner.secondpass.forms import FormsAccumulator
from tabalyst.scanner.secondpass.frequencies import FrequencyAccumulator
from tabalyst.scanner.secondpass.matrix import MatrixAccumulator
from tabalyst.scanner.secondpass.measures import MeasureAccumulator
from tabalyst.scanner.secondpass.measures import (
    derive_from_samples as measures_from_samples,
)
from tabalyst.scanner.secondpass.models import (
    AnalysisOutput,
    AnalysisResult,
    AnalysisStatus,
    DeepResult,
    DeepRun,
    DeepTimings,
    DistinctLimited,
    DuplicatesLimited,
)
from tabalyst.scanner.secondpass.parallel import (
    RemoteRoute,
    SecondPassWorkers,
    part_name,
)
from tabalyst.scanner.secondpass.parts import PartsAccumulator
from tabalyst.scanner.secondpass.patterns import (
    PatternAccumulator,
    derive_from_samples,
    pattern_entry,
)
from tabalyst.scanner.secondpass.pearson import ColumnFeed, PairAccumulator
from tabalyst.scanner.secondpass.periods import PeriodAccumulator
from tabalyst.scanner.secondpass.ranks import RankEdges, RankGrid, rank_edges
from tabalyst.scanner.secondpass.replay import CellReader
from tabalyst.scanner.secondpass.residuals import (
    PATTERN_SOURCE,
    ResidualAccumulator,
)
from tabalyst.scanner.secondpass.residuals import (
    derive_from_samples as residuals_from_samples,
)
from tabalyst.scanner.secondpass.routing import FieldRoute, Router, field_path
from tabalyst.scanner.secondpass.shape import ShapeAccumulator, make_views
from tabalyst.scanner.secondpass.stats import StatsAccumulator, StatsEdges, stats_edges
from tabalyst.scanner.secondpass.structure import (
    ArrayAccumulator,
    KeySets,
    StructureAccumulator,
)
from tabalyst.scanner.secondpass.texts import FingerprintAccumulator, TextAccumulator
from tabalyst.scanner.workers import worker_count
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
    | PartsAccumulator
    | MeasureAccumulator
    | ShapeAccumulator
    | ResidualAccumulator
    | DuplicateAccumulator
    | KeyAccumulator
    | PairAccumulator
    | CrosstabAccumulator
    | StatsAccumulator
    | DriftAccumulator
    | MatrixAccumulator
    | ArrayAccumulator
    | KeySets
    | TextAccumulator
    | FingerprintAccumulator
    | FormsAccumulator
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
    # The place of the field among the columns of a matrix of missing values.
    column: int = -1
    # The sweep that counts the sets of keys of an object, and the fields the Scan
    # named below it.
    structure: StructureAccumulator | None = None
    children: list[FieldResult] | None = None
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


Feeds = dict[tuple[str, FieldPath, str], ColumnFeed | CodeFeed | RawFeed]


def _setup_pair(
    job: _Job,
    cells: CellReader,
    feeds: Feeds,
    edge_cache: dict[tuple[str, str, int], RankEdges],
) -> None:
    """The accumulator of a pair. A pair whose rows the complete sample of the
    Scan holds is counted from them now and reads nothing; the others get the
    feed of each column, shared with the other pairs that use it."""
    candidate, dataset = job.candidate, job.dataset
    first, second = job.field, job.partner
    assert second is not None
    min_pairs = int(candidate.parameters["min_pairs"])
    rank_bins = int(candidate.parameters.get("rank_bins", 0))
    grid: RankGrid | None = None
    if rank_bins:
        if first.numeric.status != "complete" or second.numeric.status != "complete":
            raise ScanMismatch("the numeric measure of the scan is not complete")
        sides = []
        for column in (first, second):
            # The edges of a column are the same in every pair that uses it.
            edges = edge_cache.get((dataset.id, column.id, rank_bins))
            if edges is None:
                assert column.numeric.status == "complete"
                edges = rank_edges(dataset, column, column.numeric.value, rank_bins, cells)
                edge_cache[(dataset.id, column.id, rank_bins)] = edges
            sides.append(edges)
        grid = RankGrid(sides[0], sides[1])
    if not candidate.execution.requires_source:
        sample = dataset.records.sample
        ids = [first.id, second.id]
        if sample is None or not sample.complete or not sample.covers(ids):
            raise ScanMismatch("the scan no longer holds every row of the pair")
        columns = [
            column_floats(sample.rows, column, cells, lenient=False) for column in (first, second)
        ]
        left, right = ColumnFeed(cells.for_field(first)), ColumnFeed(cells.for_field(second))
        left.numbers, right.numbers = columns[0][1], columns[1][1]
        pair = PairAccumulator(left, right, min_pairs, grid)
        pair.add(columns[0][0], columns[1][0])
        job.accumulator = pair
        return
    columns_of = []
    for field in (first, second):
        where = (dataset.id, field_path(field.path))
        feed = feeds.get((*where, "number"))
        if feed is None:
            feed = feeds[(*where, "number")] = ColumnFeed(cells.for_field(field))
        assert isinstance(feed, ColumnFeed)
        columns_of.append(feed)
    job.accumulator = PairAccumulator(columns_of[0], columns_of[1], min_pairs, grid)
    job.reads_pair = True


def _setup_stats(
    job: _Job,
    cells: CellReader,
    feeds: Feeds,
    edge_cache: dict[tuple[str, str, int, str], StatsEdges],
) -> None:
    """The accumulator of the numbers by category. The classes and the edges of
    the bins come from the Scan alone, as they did when the pair was planned. A
    pair whose rows the complete sample of the Scan holds is counted from them now
    and reads nothing; the others get the feed of each column, shared with the
    other pairs and tables that use it."""
    candidate, dataset = job.candidate, job.dataset
    category, column = job.field, job.partner
    assert column is not None
    parameters = candidate.parameters
    max_categories = int(parameters["max_categories"])
    bins = int(parameters["bins"])
    strategy = str(parameters["strategy"])
    measure = category.values.frequencies
    if measure.status != "complete" or len(measure.value.listed) < min(
        measure.value.distinct, max_categories
    ):
        raise ScanMismatch("the frequencies of the scan no longer reach the categories")
    if column.numeric.status != "complete":
        raise ScanMismatch("the numeric measure of the scan is not complete")
    coder = CategoryCoder(cells, measure.value, max_categories)
    edges = edge_cache.get((dataset.id, column.id, bins, strategy))
    if edges is None:
        edges = stats_edges(dataset, column, column.numeric.value, bins, strategy, cells)
        edge_cache[(dataset.id, column.id, bins, strategy)] = edges
    if not candidate.execution.requires_source:
        sample = dataset.records.sample
        ids = [category.id, column.id]
        if sample is None or not sample.complete or not sample.covers(ids):
            raise ScanMismatch("the scan no longer holds every row of the pair")
        floats, found = column_floats(sample.rows, column, cells, lenient=False)
        left, right = CodeFeed(coder), ColumnFeed(cells.for_field(column))
        right.numbers = found
        table = StatsAccumulator(left, right, edges)
        table.add(code_rows(coder, sample.rows, category.id), floats)
        job.accumulator = table
        return
    where = (dataset.id, field_path(category.path), f"category:{max_categories}")
    feed = feeds.get(where)
    if feed is None:
        feed = feeds[where] = CodeFeed(coder)
    assert isinstance(feed, CodeFeed)
    left = feed
    where = (dataset.id, field_path(column.path), "number")
    number_feed = feeds.get(where)
    if number_feed is None:
        number_feed = feeds[where] = ColumnFeed(cells.for_field(column))
    assert isinstance(number_feed, ColumnFeed)
    job.accumulator = StatsAccumulator(left, number_feed, edges)
    job.reads_pair = True


def _setup_keys(job: _Job, cells: CellReader, feeds: Feeds, pool: ExactPool) -> None:
    """The accumulator of a combination of two columns: the feed of each column,
    shared with the other combinations that use it. The row sample of the Scan
    holds too few rows to answer, so the source is always read."""
    candidate, dataset = job.candidate, job.dataset
    first, second = job.field, job.partner
    assert second is not None
    parameters = candidate.parameters
    columns_of = []
    for field in (first, second):
        where = (dataset.id, field_path(field.path), "raw")
        feed = feeds.get(where)
        if feed is None:
            feed = feeds[where] = RawFeed(cells)
        assert isinstance(feed, RawFeed)
        columns_of.append(feed)
    job.accumulator = KeyAccumulator(
        columns_of[0],
        columns_of[1],
        DuplicateAccumulator(
            pool,
            max_listed=int(parameters["max_listed"]),
            max_tracked=int(parameters["max_tracked"]),
            columns=[first.display, second.display],
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
        ),
    )
    job.reads_pair = True


def _setup_table(job: _Job, cells: CellReader, feeds: Feeds, scan: ScanResult) -> None:
    """The accumulator of a table. The classes come from the Scan alone, as they
    did when the table was planned. A table whose rows the complete sample of the
    Scan holds is counted from them now and reads nothing; the others get the
    feed of each column, shared with the other tables that use it."""
    candidate, dataset = job.candidate, job.dataset
    category, column = job.field, job.partner
    assert column is not None
    parameters = candidate.parameters
    feature = str(parameters["feature"])
    max_classes = int(parameters.get("max_classes", 0))
    prefix_length = int(parameters.get("prefix_length", 0))
    measure = category.values.frequencies
    max_categories = int(parameters["max_categories"])
    if measure.status != "complete" or len(measure.value.listed) < min(
        measure.value.distinct, max_categories
    ):
        raise ScanMismatch("the frequencies of the scan no longer reach the categories")
    categories = CategoryCoder(cells, measure.value, max_categories)
    entry = (
        pattern_entry(scan.derived.patterns.fields, dataset.id, column.id)
        if scan.derived is not None and scan.derived.patterns is not None
        else None
    )
    coder, why = feature_coder(
        cells,
        feature,
        column,
        entry,
        max_classes=max_classes or 2,
        prefix_length=prefix_length or 1,
        max_value_length=scan.config.pattern_inference.max_value_length,
    )
    if coder is None:
        raise ScanMismatch(f"the scan no longer offers the feature: {why}")
    provided = [
        (str(category_label), str(class_label))
        for category_label, class_label in json.loads(str(parameters.get("rules", "[]")))
    ]
    rules = {
        "feature": feature,
        "prefix_length": prefix_length or None,
        "examples": int(parameters["examples"]),
        "rule_purity": int(parameters["rule_purity"]),
        "rule_support": int(parameters["rule_support"]),
        "max_exception_cells": int(parameters.get("max_exception_cells", MAX_EXCEPTION_CELLS)),
        "provided": provided,
    }
    if not candidate.execution.requires_source:
        sample = dataset.records.sample
        ids = [category.id, column.id]
        if sample is None or not sample.complete or not sample.covers(ids):
            raise ScanMismatch("the scan no longer holds every row of the table")
        left, right = CodeFeed(categories), CodeFeed(coder)
        right.raws = [cell_text(row, column.id) or "" for row in sample.rows]
        right.records = [row.record for row in sample.rows]
        table = CrosstabAccumulator(left, right, **rules)  # type: ignore[arg-type]
        table.add(
            code_rows(categories, sample.rows, category.id),
            code_rows(coder, sample.rows, column.id),
        )
        job.accumulator = table
        return
    columns_of: list[CodeFeed] = []
    for field, side, kind in (
        (category, categories, f"category:{parameters['max_categories']}"),
        (column, coder, f"{feature}:{max_classes}:{prefix_length}"),
    ):
        where = (dataset.id, field_path(field.path), kind)
        feed = feeds.get(where)
        if feed is None:
            feed = feeds[where] = CodeFeed(side)
        assert isinstance(feed, CodeFeed)
        columns_of.append(feed)
    job.accumulator = CrosstabAccumulator(columns_of[0], columns_of[1], **rules)  # type: ignore[arg-type]
    job.reads_pair = True


def _setup_matrix(
    job: _Job, cells: CellReader, matrices: dict[str, MatrixAccumulator]
) -> None:
    """The accumulator of the missing values of a dataset, shared by every column
    of the plan: the columns come from the Scan alone, as they did when the plan
    was made, so the result does not depend on which of them the plan selected."""
    candidate, dataset = job.candidate, job.dataset
    matrix = matrices.get(dataset.id)
    if matrix is None:
        matrix = matrices[dataset.id] = MatrixAccumulator(cells, matrix_members(dataset))
    if len(matrix.members) != int(candidate.parameters["columns"]):
        raise ScanMismatch("the columns that miss a value are not those the plan counted")
    ids = [member.id for member in matrix.members]
    if job.field.id not in ids:
        raise ScanMismatch("the scan no longer counts the field among the columns that miss a value")
    job.column = ids.index(job.field.id)
    job.accumulator = matrix
    job.reads_pair = True


def _root_field(dataset: DatasetResult) -> FieldResult:
    """The stand-in for the root of the records of a JSON dataset, which the Scan
    holds as no field. Only what the sets of keys read is set (design 20.33)."""
    return FieldResult.model_construct(
        id=ROOT_FIELD,
        path=[],
        display=ROOT_FIELD,
        name=ROOT_FIELD,
        parent=None,
        native_types={"object": dataset.record_count},
        exposure=None,
    )


def _setup_structure(job: _Job, structures: dict[str, StructureAccumulator]) -> None:
    """The counter of the sets of keys of an object, added to the sweep of its
    dataset: the keys are the fields the Scan named below it, as they were when the
    plan was made."""
    candidate, dataset, field = job.candidate, job.dataset, job.field
    root = field.id == ROOT_FIELD
    children = [item for item in dataset.fields if item.parent == (None if root else field.id)]
    paths = [field_path(item.path) for item in children]
    if not children or not all(path and isinstance(path[-1], Key) for path in paths):
        raise ScanMismatch("the scan no longer names the keys of the object")
    sets = KeySets(
        [path[-1].name for path in paths],  # type: ignore[union-attr]
        paths,
        int(candidate.parameters["max_variants"]),
        0 if candidate.costs is None else candidate.costs.cell_ns,
    )
    structure = structures.setdefault(dataset.id, StructureAccumulator())
    structure.track(None if root else field_path(field.path), sets)
    job.accumulator = sets
    job.structure = structure
    job.children = children
    job.reads_pair = True


def _setup(job: _Job, cells: CellReader, pool: ExactPool, scan: ScanResult) -> None:
    """The accumulator of an analysis, with the route of its field."""
    candidate, field, dataset = job.candidate, job.field, job.dataset
    if candidate.analyzer == "sensitive_forms":
        parameters = candidate.parameters
        job.accumulator = FormsAccumulator(
            min_count=int(parameters["min_count"]),
            max_listed=int(parameters["max_listed"]),
            max_tracked=int(parameters["max_tracked"]),
            detector=str(parameters["classes"]) or None,
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
        )
        return
    if candidate.analyzer == "text_profile":
        job.accumulator = TextAccumulator(
            0 if candidate.costs is None else candidate.costs.cell_ns
        )
        return
    if candidate.analyzer == "fingerprint_distinct":
        job.accumulator = FingerprintAccumulator(pool, int(candidate.parameters["max_listed"]))
        return
    if candidate.analyzer == "array_profile":
        job.accumulator = ArrayAccumulator(
            int(candidate.parameters["max_lengths"]),
            0 if candidate.costs is None else candidate.costs.cell_ns,
        )
        return
    if candidate.analyzer == "position_drift":
        parameters = candidate.parameters
        track = bool(int(parameters["values"]))
        frequencies = field.values.frequencies
        if track and frequencies.status != "complete":
            job.failure = ("scan_mismatch", "the frequencies of the scan are not complete")
            return
        job.accumulator = DriftAccumulator(
            dataset.record_count,
            track=track,
            limit=frequencies.value.distinct if track and frequencies.status == "complete" else 0,
            max_listed=int(parameters.get("max_listed", 0)),
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
        )
        return
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
            str(candidate.parameters["granularity"]),
            temporal.kinds[0].kind,
            str(candidate.parameters.get("date_order", "")) or None,
        )
        return
    if candidate.analyzer == "datetime_parts":
        temporal = field.temporal.value if field.temporal.status == "complete" else None
        if temporal is None or len(temporal.kinds) != 1:
            job.failure = ("scan_mismatch", "the scan has no single temporal kind for the field")
            return
        parameters = candidate.parameters
        as_of = str(parameters["as_of"])
        job.accumulator = PartsAccumulator(
            temporal.kinds[0].kind,
            scan.config.detectors.date.model_dump(),
            as_of=date.fromisoformat(as_of) if as_of else None,
            order=str(parameters.get("date_order", "")) or None,
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
        )
        return
    if candidate.analyzer == "measure_extraction":
        parameters = candidate.parameters
        measures = MeasureAccumulator(
            str(parameters["detector"]),
            max_groups=int(parameters["max_groups"]),
            max_values=int(parameters["max_values"]),
            bins=int(parameters["bins"]),
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
            convention=str(parameters.get("number_convention", "")) or None,
        )
        job.accumulator = measures
        if not candidate.execution.requires_source:
            measures_from_samples(measures, field, cells)
        return
    if candidate.analyzer == "numeric_shape":
        stats = field.numeric.value if field.numeric.status == "complete" else None
        if stats is None:
            job.failure = ("scan_mismatch", "the numeric measure of the scan is not complete")
            return
        parameters = candidate.parameters
        log, why, equal = make_views(dataset, field, stats, int(parameters["bins"]), cells)
        job.accumulator = ShapeAccumulator(
            log,
            why,
            equal,
            max_values=int(parameters["max_values"]),
            bins=int(parameters["bins"]),
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
        )
        return
    if candidate.analyzer == "duplicates_report":
        parameters = candidate.parameters
        # What the Scan answers alone holds at most its own distinct values, which
        # the plan did not charge to the pool of the run.
        reads = candidate.execution.requires_source
        duplicates = DuplicateAccumulator(
            pool if reads else ExactPool(DEFAULT_MEMORY_BUDGET_BYTES),
            max_listed=int(parameters["max_listed"]),
            max_tracked=int(parameters["max_tracked"]),
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
        )
        job.accumulator = duplicates
        if not candidate.execution.requires_source:
            duplicates_from_samples(duplicates, field)
        return
    if candidate.analyzer == "residual_values":
        parameters = candidate.parameters
        sources = str(parameters["sources"]).split(",")
        entry = None
        if PATTERN_SOURCE in sources:
            entry = (
                pattern_entry(scan.derived.patterns.fields, dataset.id, field.id)
                if scan.derived is not None and scan.derived.patterns is not None
                else None
            )
            if entry is None:
                job.failure = ("scan_mismatch", "the scan has no inferred patterns for the field")
                return
        residuals = ResidualAccumulator(
            entry=entry,
            pattern_max_length=scan.config.pattern_inference.max_value_length,
            detectors=[source for source in sources if source != PATTERN_SOURCE],
            pool=pool,
            max_listed=int(parameters["max_listed"]),
            max_tracked=int(parameters["max_tracked"]),
            max_value_length=int(parameters["max_value_length"]),
            cell_ns=0 if candidate.costs is None else candidate.costs.cell_ns,
        )
        job.accumulator = residuals
        if not candidate.execution.requires_source:
            residuals_from_samples(residuals, field, cells)
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


def _stopped(found: DuplicatesLimited, unit: str) -> _Finished:
    """A search for repeated values that the memory budget stopped (D08)."""
    return _Finished(
        "limited",
        found,
        reason=MEMORY_BUDGET,
        detail=f"stopped after {found.values_read} {unit}, at least {found.repeated} repeated",
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
    if isinstance(accumulator, CrosstabAccumulator):
        partner = job.partner
        assert partner is not None
        source = "source" if job.candidate.execution.requires_source else "samples"
        return _Finished("complete", accumulator.result(source, field, partner))
    if isinstance(accumulator, StatsAccumulator):
        partner = job.partner
        assert partner is not None
        if partner.numeric.status != "complete":
            raise ScanMismatch("the numeric measure of the scan is not complete")
        source = "source" if job.candidate.execution.requires_source else "samples"
        return _Finished("complete", accumulator.result(source, field, partner.numeric.value))
    if isinstance(accumulator, MeasureAccumulator):
        source = "source" if job.candidate.execution.requires_source else "samples"
        return _Finished("complete", accumulator.result(field, source))
    if isinstance(accumulator, DriftAccumulator):
        return _Finished("complete", accumulator.result(field, job.dataset.record_count))
    if isinstance(accumulator, ArrayAccumulator):
        return _Finished("complete", accumulator.result(field))
    if isinstance(accumulator, TextAccumulator):
        return _Finished("complete", accumulator.result(field.strings.content))
    if isinstance(accumulator, FormsAccumulator):
        return _Finished("complete", accumulator.result(field))
    if isinstance(accumulator, FingerprintAccumulator):
        cardinality = field.values.cardinality
        exact = cardinality.value if isinstance(cardinality, CardinalityComplete) else None
        bound = cardinality.lower_bound if isinstance(cardinality, CardinalityLimited) else None
        prints = accumulator.result(field.values.count, exact, bound)
        if isinstance(prints, DistinctLimited):
            return _Finished(
                "limited",
                prints,
                reason=MEMORY_BUDGET,
                detail=(
                    f"stopped after {prints.values_read} values, "
                    f"at least {prints.lower_bound} distinct"
                ),
            )
        return _Finished("complete", prints)
    if isinstance(accumulator, KeySets):
        assert job.children is not None
        parameters = job.candidate.parameters
        expected = (
            job.dataset.record_count
            if field.id == ROOT_FIELD
            else field.native_types.get("object", 0)
        )
        return _Finished(
            "complete",
            accumulator.result(
                expected,
                job.children,
                int(parameters["max_listed"]),
                int(parameters["max_keys"]),
            ),
        )
    if isinstance(accumulator, MatrixAccumulator):
        accumulator.check(job.dataset)
        return _Finished(
            "complete",
            accumulator.result(job.column, int(job.candidate.parameters["max_listed"])),
        )
    if isinstance(accumulator, PartsAccumulator):
        as_of = str(job.candidate.parameters["as_of"])
        return _Finished("complete", accumulator.result(field, as_of or None))
    if isinstance(accumulator, ShapeAccumulator):
        if field.numeric.status != "complete":
            raise ScanMismatch("the numeric measure of the scan is not complete")
        return _Finished("complete", accumulator.result(field.numeric.value))
    if isinstance(accumulator, KeyAccumulator):
        partner = job.partner
        assert partner is not None
        accumulator.check(field, partner, job.dataset.record_count)
        found = accumulator.duplicates.result(0, None, "source", True)
        if isinstance(found, DuplicatesLimited):
            return _stopped(found, "rows")
        return _Finished("complete", found)
    if isinstance(accumulator, DuplicateAccumulator):
        cardinality = field.values.cardinality
        exact = cardinality.value if isinstance(cardinality, CardinalityComplete) else None
        bound = cardinality.lower_bound if isinstance(cardinality, CardinalityLimited) else None
        reads = job.candidate.execution.requires_source
        found = accumulator.result(
            field.values.count,
            exact if exact is not None else bound,
            "source" if reads else "samples",
            reads,
        )
        if isinstance(found, DuplicatesLimited):
            return _stopped(found, "values")
        if exact is not None and found.distinct != exact:
            raise ScanMismatch(
                f"distinct values: the second pass found {found.distinct}, the scan {exact}"
            )
        return _Finished("complete", found)
    if isinstance(accumulator, ResidualAccumulator):
        reads = job.candidate.execution.requires_source
        return _Finished(
            "complete", accumulator.result(field, "source" if reads else "samples", reads)
        )
    if isinstance(accumulator, PeriodAccumulator):
        assert field.temporal.status == "complete"
        stats = field.temporal.value
        return _Finished(
            "complete",
            accumulator.result(stats.kinds[0].count, stats.ambiguous, date_evidence(field)),
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
    if isinstance(pair, MatrixAccumulator) and pair.failure is not None:
        return _entry(candidate, key, "failed", reason="analysis_error", detail=pair.failure)
    if isinstance(pair, KeySets) and job.structure is not None and job.structure.failure is not None:
        return _entry(candidate, key, "failed", reason="analysis_error", detail=job.structure.failure)
    if isinstance(
        pair, PairAccumulator | CrosstabAccumulator | KeyAccumulator | StatsAccumulator
    ):
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


# Fewer routes than this are not worth a worker.
MIN_PARALLEL_ROUTES = 2


def _share_out(
    jobs: list[_Job],
    routes: dict[tuple[str, FieldPath], FieldRoute],
    scan: ScanResult,
    workers: int | None,
) -> tuple[dict[tuple[str, FieldPath], RemoteRoute], SecondPassWorkers | None]:
    """The routes the workers take over, as the stand-ins the router feeds, and
    the pool that holds them; none when the run stays in the process.

    Only the batches of a CSV file with a single dataset are shared out. A route
    with an exact set stays: the sets of a run share one memory pool (MEM-06).
    """
    if scan.source.format != "csv" or len({dataset for dataset, _ in routes}) != 1:
        return {}, None
    count = worker_count(workers, scan.source.size_bytes)
    local = {
        (job.dataset.id, field_path(job.field.path))
        for job in jobs
        if (
            isinstance(job.accumulator, ExactSet | FingerprintAccumulator)
            or (
                isinstance(job.accumulator, ResidualAccumulator | DuplicateAccumulator)
                and job.accumulator.uses_pool
            )
        )
        and job.route is not None
    }
    movable = [(where, route) for where, route in routes.items() if where not in local]
    count = min(count, len(movable))
    if count < MIN_PARALLEL_ROUTES:
        return {}, None
    pool = SecondPassWorkers(scan.config.model_dump_json(by_alias=True), count)
    if not pool.start():
        return {}, None
    try:
        stand_ins = pool.place([route for _, route in movable])
    except BaseException:
        pool.close()
        raise
    return {where: stand_in for (where, _), stand_in in zip(movable, stand_ins, strict=True)}, pool


def _collect(
    pool: SecondPassWorkers,
    remote_of: dict[tuple[str, FieldPath], RemoteRoute],
    routes: dict[tuple[str, FieldPath], FieldRoute],
    jobs: list[_Job],
) -> None:
    """Take back the accumulators the workers filled: each job points to its own
    again, and its route to the failure and count of values the worker found."""
    results = pool.finish(remote_of.values())
    for where, remote in remote_of.items():
        parts, failure, values = results[remote.rid]
        remote.values = values
        local = routes[where]
        # A column the router could not cut fails the route here, before any
        # worker sees it; a worker's failure is the other way to fail.
        local.failure = remote.failure or failure
        local.values = values
        for name, accumulator in parts.items():
            setattr(local, name, accumulator)
    for job in jobs:
        route = job.route
        if route is None or job.accumulator is None:
            continue
        if any(route is routes[where] for where in remote_of):
            job.accumulator = getattr(route, part_name(job.accumulator))


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
    workers: int | None = None,
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

    The routes of a CSV file's fields run in ``workers`` processes (design
    20.18); ``None`` lets ``worker_count`` choose, 1 reads and counts in the
    process. The document does not depend on it but for ``run.workers``.
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
    for dataset in scan.datasets:
        fields[(dataset.id, ROOT_FIELD)] = (dataset, _root_field(dataset))
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
    used = 1
    verified = False
    if jobs:
        cells = CellReader(scan.config)
        # The exact sets of the run share what the plan gave them (MEM-06).
        pool = ExactPool(
            sum(
                _grant(job.candidate)
                for job in jobs
                if job.candidate.analyzer
                in (
                    "exact_distinct",
                    "residual_values",
                    "duplicates_report",
                    "fingerprint_distinct",
                )
            )
        )
        routes: dict[tuple[str, FieldPath], FieldRoute] = {}
        feeds: Feeds = {}
        edge_cache: dict[tuple[str, str, int], RankEdges] = {}
        stats_cache: dict[tuple[str, str, int, str], StatsEdges] = {}
        matrices: dict[str, MatrixAccumulator] = {}
        structures: dict[str, StructureAccumulator] = {}
        # An analysis the Scan can answer alone (the patterns of a field whose
        # every distinct value it holds) does not read the source.
        for job in jobs:
            try:
                if job.candidate.analyzer == "pearson_correlation":
                    _setup_pair(job, cells, feeds, edge_cache)
                    continue
                if job.candidate.analyzer == "category_crosstab":
                    _setup_table(job, cells, feeds, scan)
                    continue
                if job.candidate.analyzer == "category_stats":
                    _setup_stats(job, cells, feeds, stats_cache)
                    continue
                if job.candidate.analyzer == "missing_matrix":
                    _setup_matrix(job, cells, matrices)
                    continue
                if job.candidate.analyzer == "structure_variants":
                    _setup_structure(job, structures)
                    continue
                if job.candidate.analyzer == "duplicates_report" and job.partner is not None:
                    _setup_keys(job, cells, feeds, pool)
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
                route = routes[where] = FieldRoute(cells.for_field(job.field), None, None)
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
                route.memo_entries = max(route.memo_entries, PERIOD_MEMO_ENTRIES)
            elif isinstance(accumulator, ResidualAccumulator):
                route.residuals = accumulator
            elif isinstance(accumulator, DuplicateAccumulator):
                route.duplicates = accumulator
            elif isinstance(accumulator, MeasureAccumulator):
                route.measures = accumulator
                route.memo_entries = max(route.memo_entries, measure_memo(accumulator.cell_ns))
            elif isinstance(accumulator, ShapeAccumulator):
                route.shape = accumulator
            elif isinstance(accumulator, PartsAccumulator):
                route.parts = accumulator
                route.memo_entries = max(route.memo_entries, PERIOD_MEMO_ENTRIES)
            elif isinstance(accumulator, DriftAccumulator):
                route.drift = accumulator
            elif isinstance(accumulator, ArrayAccumulator):
                route.arrays = accumulator
            elif isinstance(accumulator, TextAccumulator):
                route.texts = accumulator
            elif isinstance(accumulator, FingerprintAccumulator):
                route.fingerprints = accumulator
            elif isinstance(accumulator, FormsAccumulator):
                route.forms = accumulator
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
                if isinstance(
                    job.accumulator,
                    PairAccumulator | CrosstabAccumulator | KeyAccumulator | StatsAccumulator,
                )
                and job.reads_pair
            ]
            remote_of, pool = _share_out(jobs, routes, scan, workers)
            used = pool.count if pool is not None else 1
            try:
                router = Router(
                    {**routes, **remote_of},
                    feeds,
                    pairs,
                    after_batch=None if pool is None else pool.flush,
                    matrices=[(dataset, matrix) for dataset, matrix in matrices.items()],
                    structures=[(dataset, found) for dataset, found in structures.items()],
                )
                consume_started = perf_counter()
                router.consume(_timed(reader, reading))
                if pool is not None:
                    _collect(pool, remote_of, routes, jobs)
                consume = perf_counter() - consume_started
            finally:
                if pool is not None:
                    pool.close()
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
            workers=used,
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

