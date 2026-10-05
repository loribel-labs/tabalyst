"""Orchestration: reader selection, engine, timing and the result document."""

from __future__ import annotations

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
    EngineInfo,
    ExcelSourceInfo,
    ScanResult,
    Scope,
    SourceInfo,
)
from tabalyst.scanner.observations import (
    DatasetOpened,
    Record,
    RecordBatch,
    StreamItem,
)
from tabalyst.scanner.paths import format_absolute, parse_path
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


def scan(
    source: str | Path,
    *,
    config: ScanConfig | None = None,
    registry: DetectorRegistry | None = None,
    on_progress: ProgressCallback | None = None,
    on_record: Callable[[Record], None] | None = None,
    workers: int | None = None,
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
    try:
        engine.consume(reader if on_record is None else _observed(reader, on_record))
        datasets = engine.finalize()
    finally:
        if engine.values.pool is not None:
            engine.values.pool.close()
    summary = reader.summary()

    excluded = engine.records_excluded
    result = ScanResult(
        engine=EngineInfo(
            version=__version__,
            normalization_version=NORMALIZATION_VERSION,
            detectors=detectors.versions(),
        ),
        status="partial" if excluded else "complete",
        started_at=started_at,
        duration_seconds=round(perf_counter() - start, 6),
        source=SourceInfo(
            format=summary.format,
            name=path.name,
            size_bytes=summary.bytes_read,
            modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            sha256=summary.sha256,
            encoding=summary.encoding,
            csv=(
                None
                if summary.csv is None
                else CsvSourceInfo(
                    delimiter=summary.csv.delimiter, header=summary.csv.header
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
    )
    emit_progress(on_progress, path, ProgressPhase.COMPLETE)
    return result
