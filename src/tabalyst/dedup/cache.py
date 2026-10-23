# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Ownership of the managed outputs and the SKIPPED decision (design dedup 7.4, 11.2, 11.3)."""

import dataclasses
import hashlib
import os
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from tabalyst.batch import validate_outputs
from tabalyst.dedup.analysis import STAGE, OutputKind
from tabalyst.dedup.discovery import OwnershipTest, PlannedSource, foreign_output_error
from tabalyst.dedup.report import (
    AnyReport,
    CompleteReport,
    DedupDocumentError,
    InventoryEntry,
    inventory_of,
    read_report,
)
from tabalyst.dedup.settings import DedupSettings
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    byte_progress,
    emit_progress,
)

CSV_KINDS: Final[tuple[OutputKind, ...]] = ("unique", "duplicates", "duplicates_all")
Verification = Literal["metadata", "digest"]

_HASH_CHUNK = 1 << 20


def file_sha256(path: Path, on_bytes: Callable[[int], None] | None = None) -> str:
    """SHA-256 of the bytes of ``path``; ``on_bytes`` gets the running total of bytes read."""
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(_HASH_CHUNK):
            digest.update(chunk)
            total += len(chunk)
            if on_bytes is not None:
                on_bytes(total)
    return digest.hexdigest()


@dataclass(frozen=True)
class Assessment:
    """What the report beside a source proves about its managed names (design dedup 11.3).

    ``report`` is the parsed report, ``None`` when there is none or it is not a Dedup
    report of this format. ``owned`` maps each CSV that exists under a managed name and
    that the report vouches for to the inventory entry that matched it; ``foreign``
    lists every other existing managed name, the report included when it does not read
    as a Dedup report. ``verified`` says that the owned files were also matched by
    their SHA-256.
    """

    report: AnyReport | None
    owned: Mapping[OutputKind, InventoryEntry]
    foreign: tuple[Path, ...]
    verified: bool = False


def assess(names: Mapping[str, Path], *, verify_content: bool = False) -> Assessment:
    """Read the report beside the source and sort the managed names that exist.

    A CSV is owned when the report (complete, or in progress: both of its inventories)
    lists its name and the file on disk has the recorded size, and the recorded SHA-256
    too with ``verify_content``. The names of the entries are only compared with the
    managed names of the source, never used as paths. Nothing is written or deleted.
    """
    report_path = names["report"]
    report: AnyReport | None = None
    foreign: list[Path] = []
    if os.path.lexists(report_path):
        try:
            report = read_report(report_path)
        except DedupDocumentError:
            foreign.append(report_path)
    listed: dict[str, list[InventoryEntry]] = {}
    if report is not None:
        for entry in inventory_of(report):
            listed.setdefault(entry.file, []).append(entry)
    owned: dict[OutputKind, InventoryEntry] = {}
    for kind in CSV_KINDS:
        path = names[kind]
        if not os.path.lexists(path):
            continue
        proof = _proof(path, listed.get(path.name, []), verify_content)
        if proof is None:
            foreign.append(path)
        else:
            owned[kind] = proof
    return Assessment(report, owned, tuple(foreign), verified=verify_content)


def _proof(
    path: Path, entries: list[InventoryEntry], verify_content: bool
) -> InventoryEntry | None:
    try:
        status = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(status.st_mode):
        return None
    digest: str | None = None
    for entry in entries:
        if entry.size_bytes != status.st_size:
            continue
        if verify_content:
            try:
                digest = digest or file_sha256(path)
            except OSError:
                return None
            if digest != entry.sha256:
                continue
        return entry
    return None


def is_owned(path: Path, planned: PlannedSource, *, verify_content: bool = False) -> bool:
    """Whether ``path``, a managed name of ``planned``, is proven to be a Dedup output.

    This is the ownership test that ``discovery.plan_batch`` takes (design dedup 7.4).
    """
    assessment = assess(planned.names, verify_content=verify_content)
    return os.path.lexists(path) and path not in assessment.foreign


def ownership_test(*, verify_content: bool = False) -> OwnershipTest:
    """The ownership test for ``plan_batch``, reading each source's report once.

    ``plan_batch`` asks about the four names of a source one by one; the report and,
    with ``verify_content``, the SHA-256 of the outputs are read for the first name
    only. The answers are not kept beyond the plan this test was made for.
    """
    assessments: dict[Path, Assessment] = {}

    def owned(path: Path, planned: PlannedSource) -> bool:
        assessment = assessments.get(planned.source)
        if assessment is None:
            assessment = assess(planned.names, verify_content=verify_content)
            assessments[planned.source] = assessment
        return os.path.lexists(path) and path not in assessment.foreign

    return owned


def refuse_unsafe_outputs(
    source: Path, names: Mapping[str, Path], assessment: Assessment, *, force: bool
) -> None:
    """Refuse, before any write, outputs that a run must not touch (design dedup 7.4).

    A managed name that is the source or a directory is an ``InputError`` even with
    ``force``; an existing name that the report does not prove is a ``ReportError``
    unless ``force`` allows replacing it. ``force`` never deletes a foreign file: the
    run only replaces the names it writes.
    """
    validate_outputs(
        ((source, path) for path in names.values()),
        sources=[source],
        force=True,
        label="Dedup output",
    )
    if assessment.foreign and not force:
        raise foreign_output_error(assessment.foreign)


@dataclass(frozen=True)
class SkipDecision:
    """A source whose result is current: its report and how far it was verified."""

    report: CompleteReport
    verification: Verification


def decide_skip(
    source: Path,
    settings: DedupSettings,
    names: Mapping[str, Path],
    assessment: Assessment,
    *,
    on_progress: ProgressCallback | None = None,
) -> SkipDecision | None:
    """The ``SKIPPED`` decision of design dedup 11.2, ``None`` when the source is reprocessed.

    The conditions are evaluated in the order of the design and stop at the first one
    that fails. The source is read only when its size matches and either its
    ``mtime_ns`` differs or ``settings.verify_content`` asks (level ``digest``); the
    outputs are then hashed too, unless ``assessment`` already matched them by SHA-256.
    Nothing is written. An unreadable file means reprocess, not an error.
    """
    report = assessment.report
    if not isinstance(report, CompleteReport) or assessment.foreign:
        return None
    recorded = report.settings
    if (
        recorded.delimiter != settings.csv.delimiter
        or recorded.encoding != settings.csv.encoding
        or report.records.total > settings.max_rows
    ):
        return None
    try:
        status = source.stat()
    except OSError:
        return None
    identity = report.source
    if (
        not stat.S_ISREG(status.st_mode)
        or identity.name != source.name
        or identity.size_bytes != status.st_size
    ):
        return None
    level: Verification = (
        "metadata"
        if identity.mtime_ns == status.st_mtime_ns and not settings.verify_content
        else "digest"
    )
    expected = {
        kind: entry
        for kind in CSV_KINDS
        if (entry := getattr(report.outputs, kind)) is not None
    }
    if set(assessment.owned) != set(expected):
        return None
    if level == "digest":
        if not _same_content(source, identity.content_sha256, status.st_size, on_progress):
            return None
        if not assessment.verified:
            for kind, entry in expected.items():
                if not _same_content(names[kind], entry.sha256, entry.size_bytes, None):
                    return None
    return SkipDecision(report, level)


def _same_content(
    path: Path, sha256: str, size: int, on_progress: ProgressCallback | None
) -> bool:
    on_bytes = None
    if on_progress is not None:
        forward = _staged(on_progress)
        emit_progress(
            forward,
            path,
            ProgressPhase.READING,
            detail="verifying the content of the source",
        )
        on_bytes = byte_progress(forward, path, size)
    try:
        return file_sha256(path, on_bytes) == sha256
    except OSError:
        return False


def _staged(callback: ProgressCallback) -> ProgressCallback:
    def forward(event: ProgressEvent) -> None:
        callback(dataclasses.replace(event, stage=STAGE))

    return forward
