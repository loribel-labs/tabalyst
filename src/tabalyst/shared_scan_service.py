"""Scan-only document shared by the CSV Scan and Report commands.

DuckDB project generations remain available to the private project API, but
ordinary scans do not need to materialize a database to serve a report.
"""

from dataclasses import dataclass
from pathlib import Path

from tabalyst.batch import write_text_atomic
from tabalyst.config import merge_settings
from tabalyst.errors import InputError, ReportError
from tabalyst.projects._locks import workspace_writer
from tabalyst.projects.location import StorageLocation
from tabalyst.scan_reuse import SourceState, compare_source, load_scan
from tabalyst.scan_service import scan_document
from tabalyst.scanner import ScanConfig, ScanResult, scan
from tabalyst.scanner.config import config_sha256, scan_config_from_layer
from tabalyst.scanner.identity import (
    expected_identity,
    scan_identity,
    source_format_of,
)


@dataclass(frozen=True)
class SharedScan:
    result: ScanResult
    path: Path
    reused: bool
    warnings: tuple[str, ...] = ()


def current_scan(
    source: Path,
    config: ScanConfig,
    *,
    location: StorageLocation | None = None,
    workers: int | None = None,
    on_progress=None,
    refresh: bool = False,
    scan_layer: dict | None = None,
    delimiter: str | None = None,
    encoding: str | None = None,
) -> SharedScan:
    """Reuse a current scan document, or atomically replace it after scanning."""
    source = source.resolve()
    location = location or StorageLocation.local()
    path = location.shared_scan_path(source)
    with workspace_writer(location):
        effective = config
        if path.exists() and not refresh:
            result = load_scan(path)
            if result.source.name != source.name:
                raise InputError("Stored scan source binding differs from the requested file")
            if config_sha256(result.config) != result.config_sha256:
                raise InputError("Stored scan configuration fingerprint is invalid")
            check = compare_source(source, result.source)
            if scan_layer is not None:
                recorded = result.config.model_dump(mode="json", by_alias=True)
                effective = scan_config_from_layer(
                    merge_settings(recorded, scan_layer),
                    delimiter=delimiter,
                    encoding=encoding,
                )
            # Reuse only when source content, applied rules and engine
            # version are all those of the document (design inspect 10.1).
            if check.state is SourceState.FRESH and check.sha256 is not None:
                wanted = expected_identity(
                    check.sha256, effective, source_format=source_format_of(source)
                )
                if wanted == scan_identity(result):
                    return SharedScan(result, path, True)

        result = scan(source, config=effective, workers=workers, on_progress=on_progress)
        try:
            write_text_atomic(path, scan_document(result))
        except OSError as exc:
            raise ReportError(f"Cannot write scan file {path}: {exc}") from exc
        return SharedScan(result, path, False)
