# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""The batch report ``dedup.summary.json``: models, invariants, schema and writing (design dedup 13.1)."""

import json
import os
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tabalyst._version import __version__
from tabalyst.batch import write_text_atomic
from tabalyst.dedup.discovery import BATCH_REPORT_NAME, ExclusionReason
from tabalyst.dedup.failures import FailureReason
from tabalyst.models import ReportGenerator

FORMAT: Final = "tabalyst.dedup.batch"
FORMAT_VERSION: Final = "0.2.0"
FORMAT_REVISION: Final = 1
SCHEMA_FILE: Final = "tabalyst.dedup.batch.schema.json"

Count = Annotated[int, Field(ge=0)]
SourceStatus = Literal["DONE", "SKIPPED", "FAILED", "EXCLUDED"]
BatchStatus = Literal["complete", "partial", "failed"]
# A source refused by a check that ran again just before its own run (a race with another
# process after the plan) fails with this reason and writes no report (design dedup 11.5).
BatchReason = (
    ExclusionReason | FailureReason | Literal["already_processed", "output_refused"]
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Counters(_Model):
    """How many files the batch found and what became of each one (nothing counted twice)."""

    found: Count
    eligible: Count
    excluded: Count
    done: Count
    skipped: Count
    failed: Count


class SourceRecords(_Model):
    """The main counts of one source, as its own report states them."""

    total: Count
    distinct: Count
    extra_copies: Count
    duplicate_groups: Count


class Tally(_Model):
    """The sources of one kind and the sum of their counts."""

    sources: Count
    records: Count
    extra_copies: Count
    duplicate_groups: Count


class Totals(_Model):
    """The counts of the sources this run processed and, apart, of the ones it reused.

    A reused source (``SKIPPED``) brings the counts of the report that already existed;
    a failed source brings none. Each source is in at most one of the two tallies.
    """

    processed: Tally
    reused: Tally


class BatchOutputs(_Model):
    """The files of this run: CSV created now, and the reports a reader can open."""

    csv_files_created: Count
    reports_available: Count
    reports_updated: Count


class BatchSource(_Model):
    """One file of the batch. An excluded file has no report and no count."""

    file: str
    status: SourceStatus
    reason: BatchReason | None
    verification: Literal["metadata", "digest"] | None
    report: str | None
    records: SourceRecords | None
    csv_files_created: Count


class BatchReport(_Model):
    """The report of a batch of sources (design dedup 13.1)."""

    format: Literal["tabalyst.dedup.batch"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    generator: ReportGenerator
    status: BatchStatus
    inputs: list[str]
    output_dir: str | None
    counters: Counters
    totals: Totals
    outputs: BatchOutputs
    duration_seconds: Annotated[float, Field(ge=0)]
    sources: list[BatchSource]
    diagnostics: list[str]

    @model_validator(mode="after")
    def _counts_agree(self) -> "BatchReport":
        broken = broken_batch_invariants(self)
        if broken:
            raise ValueError("; ".join(broken))
        return self


def broken_batch_invariants(report: BatchReport) -> list[str]:
    """The rules that tie the counters, the tallies and the source list together."""
    counters, totals = report.counters, report.totals
    by_status = {
        status: sum(1 for item in report.sources if item.status == status)
        for status in ("DONE", "SKIPPED", "FAILED", "EXCLUDED")
    }
    broken: list[str] = []

    def require(holds: bool, rule: str) -> None:
        if not holds:
            broken.append(rule)

    require(
        counters.found == counters.eligible + counters.excluded,
        "found = eligible + excluded",
    )
    require(
        counters.eligible == counters.done + counters.skipped + counters.failed,
        "eligible = done + skipped + failed",
    )
    require(
        (counters.done, counters.skipped, counters.failed, counters.excluded)
        == (
            by_status["DONE"],
            by_status["SKIPPED"],
            by_status["FAILED"],
            by_status["EXCLUDED"],
        ),
        "the counters match the statuses of the sources",
    )
    require(len(report.sources) == counters.found, "one entry per file found")
    require(
        (totals.processed.sources, totals.reused.sources)
        == (counters.done, counters.skipped),
        "the tallies hold the done and the skipped sources",
    )
    require(
        report.outputs.csv_files_created
        == sum(item.csv_files_created for item in report.sources),
        "csv_files_created is the sum over the sources",
    )
    require(
        all(
            item.csv_files_created == 0
            for item in report.sources
            if item.status != "DONE"
        ),
        "only a DONE source creates a CSV file",
    )
    require(
        report.outputs.reports_updated <= report.outputs.reports_available,
        "reports_updated <= reports_available",
    )
    expected: BatchStatus = (
        "complete"
        if counters.failed == 0
        else "failed"
        if counters.failed == counters.eligible
        else "partial"
    )
    require(report.status == expected, f"status is {expected} for these counters")
    return broken


def batch_report_json(report: BatchReport) -> str:
    """The report as the file holds it: indented JSON, one trailing newline."""
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def write_batch_report(path: Path, report: BatchReport) -> None:
    """Replace ``path`` with ``report`` atomically; ``OSError`` if it cannot be written."""
    write_text_atomic(path, batch_report_json(report))


def generator() -> ReportGenerator:
    """The generator member of a report written now."""
    return ReportGenerator(version=__version__)


def is_batch_report(path: Path) -> bool:
    """Whether ``path`` is a file that announces itself as a Tabalyst Dedup batch report.

    Only the ``format`` member decides, so a report of another revision of this
    format is still ours to replace (design dedup 13.1, open point 7).
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(document, dict) and document.get("format") == FORMAT


def relative_path(path: str | os.PathLike[str], base: Path) -> str:
    """``path`` relative to the folder ``base``, with ``/`` separators.

    On another drive no relative path exists: the name alone is given, never an
    absolute path (design dedup 13.1).
    """
    try:
        return Path(os.path.relpath(path, base)).as_posix()
    except ValueError:
        return Path(os.fspath(path)).name


def batch_schema() -> dict[str, Any]:
    """The schema of the batch report, in validation mode: what a reader accepts."""
    schema = BatchReport.model_json_schema(mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Tabalyst Dedup batch"
    schema["description"] = (
        f"Document {FORMAT}, format {FORMAT_VERSION} revision {FORMAT_REVISION}: "
        f"the summary {BATCH_REPORT_NAME} of a batch of sources."
    )
    nodes = [schema, *schema.get("$defs", {}).values()]
    for node in nodes:
        properties = node.get("properties", {})
        required = node.setdefault("required", [])
        for name in ("format", "format_version", "format_revision"):
            if name in properties and name not in required:
                required.append(name)
        if not required:
            del node["required"]
    return schema


def batch_schema_text() -> str:
    """The schema as the committed file writes it."""
    return json.dumps(batch_schema(), indent=2, ensure_ascii=False) + "\n"
