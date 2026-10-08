# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Orchestration: reader selection, engine, timing and the result document."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from tabalyst._version import __version__
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.progress import (
    ProgressCallback,
    ProgressPhase,
    byte_progress,
    emit_progress,
)
from tabalyst.scanner.config import ScanConfig, config_sha256, resolve_config_defaults
from tabalyst.scanner.detectors.registry import (
    DetectorRegistry,
    DetectorSet,
    default_registry,
)
from tabalyst.scanner.engine import ScanEngine
from tabalyst.scanner.identity import source_format_of
from tabalyst.scanner.models import (
    CollectionScope,
    CsvSourceInfo,
    DatasetResult,
    Derived,
    EngineInfo,
    ExcelSourceInfo,
    RunCounters,
    RunInfo,
    SamplingCounters,
    ScanResult,
    Scope,
    SourceInfo,
    SourceShape,
    Timings,
)
from tabalyst.scanner.observations import (
    DatasetOpened,
    Record,
    RecordBatch,
    StreamItem,
)
from tabalyst.scanner.paths import format_absolute, parse_path
from tabalyst.scanner.patterninfer import infer_patterns
from tabalyst.scanner.readers.base import Reader
from tabalyst.scanner.readers.csv_reader import CsvReader
from tabalyst.scanner.readers.excel_reader import ExcelReader
from tabalyst.scanner.readers.json_reader import JsonReader
from tabalyst.scanner.readers.jsonl_reader import JsonlReader
from tabalyst.scanner.workers import WorkerPool, worker_count

NORMALIZATION_VERSION = 1


def _open_reader(
    path: Path, config: ScanConfig, on_bytes: Callable[[int], None] | None
) -> Reader:
    source_format = source_format_of(path)
    if source_format == "json":
        return JsonReader(path, config, on_bytes)
    if source_format == "jsonl":
        return JsonlReader(path, config, on_bytes)
    if source_format == "excel":
        return ExcelReader(path, config, on_bytes)
    return CsvReader(path, config, on_bytes)


def _collection_scope(source_format: str, config: ScanConfig) -> CollectionScope | None:
    if source_format != "json":
        return None
    requested = config.json_.collections
    return CollectionScope(
        mode="auto" if requested is None else "explicit",
        # Canonical spellings, equal to the dataset identifiers.
        requested=(
            None
            if requested is None
            else [format_absolute(parse_path(text)) for text in requested]
        ),
    )


def _observed(
    items: Iterable[StreamItem], on_record: Callable[[Record], None]
) -> Iterator[StreamItem]:
    """Items as read, after passing each analyzed record to ``on_record``;
    records of a batch are passed one by one, as ``Record`` items."""
    declared = {}
    for item in items:
        if type(item) is Record:
            on_record(item)
        elif type(item) is RecordBatch:
            for record in item.records(declared[item.dataset]):
                on_record(record)
        elif type(item) is DatasetOpened:
            declared[item.dataset] = [field.path for field in item.fields]
        yield item


def _duplicate_records(datasets: list[DatasetResult]) -> int | None:
    """Duplicate records of every dataset, or ``None`` when one count is
    limited or disabled."""
    counts = [dataset.records.duplicates.count for dataset in datasets]
    if any(count.status != "complete" for count in counts):
        return None
    return sum(count.value for count in counts)


def _run_counters(engine: ScanEngine) -> RunCounters:
    """The optional counters of the samplers, summed over the fields."""
    values = engine.values
    sampling = values.sampling
    return RunCounters(
        sampling=SamplingCounters(
            **sampling.totals,
            k_effective_min=sampling.k_min,
            k_effective_max=sampling.k_max,
            sample_model_bytes=values.samples.reserved,
            long_model_bytes=values.samples.long_reserved,
            length_model_bytes=values.samples.length_reserved,
        )
    )


def _peak_memory_bytes() -> int | None:
    """Peak memory of this process so far, or ``None`` when unavailable."""
    try:
        import resource
    except ImportError:
        pass
    else:
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Kibibytes on Linux, bytes on macOS.
        return peak if sys.platform == "darwin" else peak * 1024
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = (
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        )

    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    kernel32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    )
    ok = psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    )
    return int(counters.PeakWorkingSetSize) if ok else None


def _timed(items: Iterable[StreamItem], spent: list[float]) -> Iterator[StreamItem]:
    """Items as read, adding to ``spent[0]`` the time the source took to
    produce them."""
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


def scan(
    source: str | Path,
    *,
    config: ScanConfig | None = None,
    registry: DetectorRegistry | None = None,
    on_progress: ProgressCallback | None = None,
    on_record: Callable[[Record], None] | None = None,
    workers: int | None = None,
    counters: bool = False,
) -> ScanResult:
    """Read one source completely and return its finalized scan result.

    Nothing is written. ``registry`` replaces the default detector registry
    (design 12.1). ``on_record`` receives each analyzed record, in reading
    order, before the engine: consumers that need record-level facts, such
    as the report's preview and duplicate rows, get them in the same pass. It
    must not modify the record.

    ``workers`` is the number of processes that analyze values: ``1`` scans
    in this process; by default, large sources use one worker per spare
    processor (``workers.worker_count``). The result does not depend on it.
    A custom ``registry`` always scans in this process.

    ``counters`` adds ``run.counters``, the work of the bottom-k samplers
    (design 18.4); they are cheap to keep and are never part of the facts.
    """
    if workers is not None and workers < 1:
        raise ConfigurationError("workers must be at least 1")
    path = Path(source)
    # A private copy: the finalized result must not share state with the caller.
    config = ScanConfig() if config is None else config.model_copy(deep=True)
    config = resolve_config_defaults(config, source_format_of(path))
    started_at = datetime.now(UTC)
    start = perf_counter()
    try:
        stat = path.stat()
    except OSError as exc:
        raise InputError(f"Cannot read source {path}: {exc}") from exc
    if not path.is_file():
        raise InputError(f"Source does not exist or is not a file: {path}")

    emit_progress(
        on_progress, path, ProgressPhase.READING, bytes_read=0, bytes_total=stat.st_size
    )
    reader = _open_reader(
        path, config, byte_progress(on_progress, path, stat.st_size)
    )
    detectors = DetectorSet(
        default_registry() if registry is None else registry, config
    )
    engine = ScanEngine(config, detectors)
    count = 1 if registry is not None else worker_count(workers, stat.st_size)
    if count > 1:
        pool = WorkerPool(config.model_dump_json(by_alias=True), count)
        if pool.start():
            engine.values.pool = pool
    reading = [0.0]
    try:
        consume_started = perf_counter()
        timed = _timed(reader, reading)
        engine.consume(timed if on_record is None else _observed(timed, on_record))
        analysis = perf_counter() - consume_started - reading[0]
        finalize_started = perf_counter()
        datasets = engine.finalize()
        finalize = perf_counter() - finalize_started
        derived_started = perf_counter()
        patterns = infer_patterns(
            datasets, config.pattern_inference, engine.diagnostics
        )
        derived = perf_counter() - derived_started
    finally:
        if engine.values.pool is not None:
            engine.values.pool.close()
    summary = reader.summary()

    excluded = engine.records_excluded
    header = (
        summary.csv.header
        if summary.csv is not None
        else None if summary.excel is None else summary.excel.header
    )
    columns = None if header is None else len(header)
    analyzed = engine.records_analyzed
    duration = perf_counter() - start
    result = ScanResult(
        engine=EngineInfo(
            version=__version__,
            normalization_version=NORMALIZATION_VERSION,
            detectors=detectors.versions(),
        ),
        status="partial" if excluded else "complete",
        run=RunInfo(
            started_at=started_at,
            duration_seconds=round(duration, 6),
            timings=Timings(
                reading=round(reading[0], 6),
                analysis=round(analysis, 6),
                finalize=round(finalize, 6),
                derived=round(derived, 6),
                other=round(
                    max(0.0, duration - reading[0] - analysis - finalize - derived),
                    6,
                ),
            ),
            workers=1 if engine.values.pool is None else count,
            peak_memory_bytes=_peak_memory_bytes(),
            counters=_run_counters(engine) if counters else None,
        ),
        source=SourceInfo(
            format=summary.format,
            name=path.name,
            size_bytes=summary.bytes_read,
            modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            sha256=summary.sha256,
            encoding=summary.encoding,
            shape=SourceShape(
                lines=None if summary.csv is None else summary.csv.lines,
                records=analyzed,
                columns=columns,
                fields=sum(len(dataset.fields) for dataset in datasets),
                datasets=len(datasets),
                cells=None if columns is None else analyzed * columns,
                missing_cells=sum(
                    field.missing.count
                    for dataset in datasets
                    for field in dataset.fields
                ),
                records_with_missing=sum(
                    dataset.records.with_missing.count for dataset in datasets
                ),
                empty_records=sum(
                    dataset.records.empty.count for dataset in datasets
                ),
                duplicate_records=_duplicate_records(datasets),
            ),
            csv=(
                None
                if summary.csv is None
                else CsvSourceInfo(
                    delimiter=summary.csv.delimiter,
                    quote=summary.csv.quote,
                    header=summary.csv.header,
                    bom=summary.csv.bom,
                    line_ending=summary.csv.line_ending,
                )
            ),
            excel=(
                None
                if summary.excel is None
                else ExcelSourceInfo(
                    dataset_path=summary.excel.dataset_path,
                    sheet=summary.excel.sheet,
                    table=summary.excel.table,
                    range=summary.excel.range,
                    header_row=summary.excel.header_row,
                    header=summary.excel.header,
                )
            ),
        ),
        config=config,
        config_sha256=config_sha256(config),
        scope=Scope(
            collections=_collection_scope(summary.format, config),
            records_read=engine.records_analyzed + excluded,
            records_analyzed=engine.records_analyzed,
            records_excluded=excluded,
            exclusions=dict(engine.exclusions),
        ),
        datasets=datasets,
        diagnostics=engine.diagnostics.finalize(),
        derived=None if patterns is None else Derived(patterns=patterns),
    )
    emit_progress(on_progress, path, ProgressPhase.COMPLETE)
    return result
