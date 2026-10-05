# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Scan-only document shared by the CSV Scan and Report commands.

DuckDB project generations remain available to the private project API, but
ordinary scans do not need to materialize a database to serve a report.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from tabalyst.batch import write_text_atomic
from tabalyst.config import merge_settings
from tabalyst.errors import InputError, ReportError
from tabalyst.projects._locks import workspace_writer
from tabalyst.projects.location import StorageLocation
from tabalyst.scan_reuse import (
    SourceState,
    UnsupportedScanDocument,
    compare_source,
    load_scan,
)
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
    source_sha256: str | None = None,
    check: Callable[[ScanResult], tuple[str, ...]] | None = None,
) -> SharedScan:
    """Reuse a current scan document, or atomically replace it after scanning.

    ``source_sha256`` is the hash of the source when the caller already has it.
    ``check`` receives the result, reused or just scanned and not yet written:
    it may raise to refuse it, which leaves the stored document as it is, and
    its notices join the warnings of the outcome (design inspect 11.5, 11.6).
    """
    source = source.resolve()
    location = location or StorageLocation.local()
    path = location.shared_scan_path(source)
    with workspace_writer(location):
        effective = config
        stored = None
        if path.exists() and not refresh:
            try:
                stored = load_scan(path)
            except UnsupportedScanDocument:
                # Written by a release with another scan format: out of date,
                # so scanned again like any stale cache.
                stored = None
        if stored is not None:
            result = stored
            if result.source.name != source.name:
                raise InputError("Stored scan source binding differs from the requested file")
            if config_sha256(result.config) != result.config_sha256:
                raise InputError("Stored scan configuration fingerprint is invalid")
            fresh = compare_source(source, result.source, sha256=source_sha256)
            if scan_layer is not None:
                recorded = result.config.model_dump(mode="json", by_alias=True)
                effective = scan_config_from_layer(
                    merge_settings(recorded, scan_layer),
                    delimiter=delimiter,
                    encoding=encoding,
                )
            # Reuse only when source content, applied rules and engine
            # version are all those of the document (design inspect 10.1).
            if fresh.state is SourceState.FRESH and fresh.sha256 is not None:
                wanted = expected_identity(
                    fresh.sha256, effective, source_format=source_format_of(source)
                )
                if wanted == scan_identity(result):
                    notices = () if check is None else check(result)
                    return SharedScan(result, path, True, notices)

        result = scan(source, config=effective, workers=workers, on_progress=on_progress)
        notices = () if check is None else check(result)
        try:
            write_text_atomic(path, scan_document(result))
        except OSError as exc:
            raise ReportError(f"Cannot write scan file {path}: {exc}") from exc
        return SharedScan(result, path, False, notices)
