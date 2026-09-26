"""Orchestration: reader selection, engine, timing and the result document."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from tabalyst._version import __version__
from tabalyst.errors import InputError
from tabalyst.progress import ProgressCallback, ProgressPhase, emit_progress
from tabalyst.scanner.config import ScanConfig, config_sha256
from tabalyst.scanner.engine import ScanEngine
from tabalyst.scanner.models import (
    CsvSourceInfo,
    EngineInfo,
    ScanResult,
    Scope,
    SourceInfo,
)
from tabalyst.scanner.readers.base import Reader
from tabalyst.scanner.readers.csv_reader import CsvReader

NORMALIZATION_VERSION = 1


def _open_reader(path: Path, config: ScanConfig) -> Reader:
    if path.suffix.lower() == ".json":
        raise InputError(f"JSON sources are not supported yet: {path}")
    return CsvReader(path, config)


def scan(
    source: str | Path,
    *,
    config: ScanConfig | None = None,
    registry=None,
    on_progress: ProgressCallback | None = None,
) -> ScanResult:
    """Read one source completely and return its finalized scan result.

    Nothing is written. ``registry`` replaces the default detector registry
    once detectors exist (lot 3a).
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

    emit_progress(on_progress, path, ProgressPhase.READING)
    reader = _open_reader(path, config)
    engine = ScanEngine(config)
    engine.consume(reader)
    datasets = engine.finalize()
    summary = reader.summary()

    excluded = engine.records_excluded
    result = ScanResult(
        engine=EngineInfo(
            version=__version__,
            normalization_version=NORMALIZATION_VERSION,
            detectors={},
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
            collections=None,
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
