"""Orchestration: reader selection, engine, timing and the result document."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from tabalyst._version import __version__
from tabalyst.errors import InputError
from tabalyst.progress import ProgressCallback, ProgressPhase, emit_progress
from tabalyst.scanner.config import ScanConfig, config_sha256
from tabalyst.scanner.detectors.registry import (
    DetectorRegistry,
    DetectorSet,
    default_registry,
)
from tabalyst.scanner.engine import ScanEngine
from tabalyst.scanner.models import (
    CollectionScope,
    CsvSourceInfo,
    EngineInfo,
    ScanResult,
    Scope,
    SourceInfo,
)
from tabalyst.scanner.paths import format_absolute, parse_path
from tabalyst.scanner.readers.base import Reader
from tabalyst.scanner.readers.csv_reader import CsvReader
from tabalyst.scanner.readers.json_reader import JsonReader

NORMALIZATION_VERSION = 1
# Reading progress is reported at most once per percent of the source, and
# never more often than every MiB.
_PROGRESS_MIN_STEP = 1 << 20


def _open_reader(
    path: Path, config: ScanConfig, on_bytes: Callable[[int], None] | None
) -> Reader:
    if path.suffix.lower() == ".json":
        return JsonReader(path, config, on_bytes)
    return CsvReader(path, config, on_bytes)


def _byte_progress(
    on_progress: ProgressCallback | None, path: Path, total: int
) -> Callable[[int], None] | None:
    if on_progress is None:
        return None
    step = max(_PROGRESS_MIN_STEP, total // 100)
    next_report = step

    def report(bytes_read: int) -> None:
        nonlocal next_report
        if bytes_read >= next_report:
            next_report = bytes_read + step
            emit_progress(
                on_progress,
                path,
                ProgressPhase.READING,
                bytes_read=bytes_read,
                bytes_total=max(total, bytes_read),
            )

    return report


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


def scan(
    source: str | Path,
    *,
    config: ScanConfig | None = None,
    registry: DetectorRegistry | None = None,
    on_progress: ProgressCallback | None = None,
) -> ScanResult:
    """Read one source completely and return its finalized scan result.

    Nothing is written. ``registry`` replaces the default detector registry
    (design 12.1).
    """
    path = Path(source)
    # A private copy: the finalized result must not share state with the caller.
    config = ScanConfig() if config is None else config.model_copy(deep=True)
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
        path, config, _byte_progress(on_progress, path, stat.st_size)
    )
    detectors = DetectorSet(
        default_registry() if registry is None else registry, config
    )
    engine = ScanEngine(config, detectors)
    engine.consume(reader)
    datasets = engine.finalize()
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
