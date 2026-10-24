# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reads and validates a Dedup report as proof of the extra row copies (contract 7).

Only the JSON report is read: never the source CSV, never the Dedup outputs, and nothing is written.
"""

from __future__ import annotations

import codecs
from pathlib import Path
from typing import Literal

from tabalyst.dedup.discovery import REPORT_SUFFIX
from tabalyst.dedup.report import (
    CompleteReport,
    DedupDocumentError,
    broken_invariants,
    read_report,
)
from tabalyst.errors import InputError
from tabalyst.scanner.models import ScanResult

from .models import DedupReportRef, DuplicateEvidence, RejectedProof

_REJECTED_SOURCE = "dedup.report"


def find_dedup_report(
    source_or_scan_dir: Path,
    option: Path | None = None,
    *,
    stem: str | None = None,
) -> Path | None:
    """Locate the Dedup report to try (contract 7.1); never searches other folders.

    ``option`` is the user's explicit file or folder: a file is used as given, a folder is searched
    for ``<stem>.dedup.json`` only, and a missing target raises ``InputError`` (the user named it).
    Without ``option`` the colocated ``<stem>.dedup.json`` is returned, or ``None`` when absent.
    ``source_or_scan_dir`` is the source file (its stem is used) or, for ``report --scan`` without
    a source, the folder of the scan document, with ``stem`` the recorded source stem.
    """
    if source_or_scan_dir.is_dir():
        if not stem:
            raise ValueError("A folder needs the source stem to look for its Dedup report.")
        folder, name = source_or_scan_dir, stem
    else:
        folder, name = source_or_scan_dir.parent, stem or source_or_scan_dir.stem
    expected = name + REPORT_SUFFIX
    if option is not None:
        if option.is_dir():
            found = option / expected
            if not found.is_file():
                raise InputError(f"The folder given to --dedup-report has no {expected}.")
            return found
        if not option.is_file():
            raise InputError("The file given to --dedup-report does not exist.")
        return option
    colocated = folder / expected
    return colocated if colocated.is_file() else None


def load_dedup_proof(
    path: Path,
    *,
    scan: ScanResult,
    dataset: str,
    origin: Literal["colocated", "explicit"],
) -> DuplicateEvidence | RejectedProof:
    """Check the Dedup report at ``path`` against the Scan; the first failed check refuses it.

    A refusal is a returned ``RejectedProof``, never an exception. ``dataset`` is the id of the
    Scan dataset the proof must cover.
    """
    try:
        report = read_report(path)
    except (DedupDocumentError, OSError, RecursionError):
        return _reject("dedup_unreadable")
    if not isinstance(report, CompleteReport):
        return _reject("dedup_not_complete")
    source = scan.source
    if report.source.content_sha256 != source.sha256:
        return _reject("dedup_source_mismatch")
    if source.format != "csv" or source.csv is None or len(scan.datasets) != 1:
        return _reject("dedup_not_csv")
    if not _same_dialect(report, scan):
        return _reject("dedup_dialect_mismatch")
    if report.settings.identity != "full_decoded_csv_row_v1":
        return _reject("dedup_identity_unsupported")
    records = next((d.record_count for d in scan.datasets if d.id == dataset), None)
    if records is None or report.records.total != records:
        return _reject("dedup_total_mismatch")
    if broken_invariants(report):
        return _reject("dedup_invariants_broken")
    return DuplicateEvidence(
        value=report.records.extra_copies,
        source="dedup.report",
        accuracy="exact",
        identity="full_decoded_csv_row_v1",
        report=DedupReportRef(
            name=path.name,
            format_revision=report.format_revision,
            settings_identity=report.settings.identity,
            content_sha256=report.source.content_sha256,
            origin=origin,
        ),
    )


def _reject(reason: str) -> RejectedProof:
    return RejectedProof(source=_REJECTED_SOURCE, reason=reason)  # type: ignore[arg-type]


def _same_dialect(report: CompleteReport, scan: ScanResult) -> bool:
    csv_info = scan.source.csv
    if csv_info is None or report.settings.delimiter != csv_info.delimiter:
        return False
    return _encoding(report.settings.encoding) == _encoding(scan.source.encoding)


def _encoding(name: str | None) -> str | None:
    # Aliases are equal ("utf8" and "UTF-8"); utf-8 and utf-8-sig stay different codecs.
    if name is None:
        return None
    try:
        return codecs.lookup(name).name
    except LookupError:
        return name.lower()
