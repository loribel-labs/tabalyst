# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON report of one Dedup source: models, invariants, schema, reading and writing (design dedup 12)."""

import json
import math
from pathlib import Path
from typing import Annotated, Any, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_serializer,
    model_validator,
)

from tabalyst._version import __version__
from tabalyst.batch import write_text_atomic
from tabalyst.dedup.analysis import DedupAnalysis
from tabalyst.dedup.failures import DedupInputError, DedupReportError, FailureReason
from tabalyst.dedup.groups import GroupStats
from tabalyst.dedup.settings import DedupSettings
from tabalyst.dedup.writer import StagedOutputs
from tabalyst.errors import InputError
from tabalyst.models import ReportGenerator

FORMAT: Final = "tabalyst.dedup"
FORMAT_VERSION: Final = "0.2.0"
FORMAT_REVISION: Final = 1
SCHEMA_FILE: Final = "tabalyst.dedup.schema.json"
# Names the rule that decides when two records are the same row (design dedup 5.1).
IDENTITY: Final = "full_decoded_csv_row_v1"

Count = Annotated[int, Field(ge=0)]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class DedupDocumentError(InputError):
    """A Dedup report read from disk is not a valid document of this format.

    The message names the member and the rule that failed, never a value of the file.
    """


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceIdentity(_Model):
    """The source a complete report describes (design dedup 12.2)."""

    name: str
    size_bytes: Count
    mtime_ns: Count
    content_sha256: Sha256


class FailedSource(_Model):
    """The source of a failed report: its name, and its size and time when they could be read."""

    name: str
    size_bytes: Count | None = None
    mtime_ns: Count | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _without_none(handler(self), ("size_bytes", "mtime_ns"))


class ReportSettings(_Model):
    """What decided the result: the limit and the way the source was read."""

    max_rows: Annotated[int, Field(ge=1)]
    delimiter: str
    encoding: str
    identity: Literal["full_decoded_csv_row_v1"] = IDENTITY


class Records(_Model):
    """The exact counts of the first pass, under the names of the specification."""

    total: Count
    distinct: Count
    singletons: Count
    duplicate_groups: Count
    groups_occurring_twice: Count
    groups_occurring_three_plus: Count
    extra_copies: Count
    duplicate_group_occurrences: Count
    max_occurrences: Count
    extra_copy_percent: Annotated[float, Field(ge=0)]


class OutputFile(_Model):
    """A CSV the run published: the inventory entry that proves what it wrote."""

    file: str
    rows: Count
    size_bytes: Count
    sha256: Sha256


class Outputs(_Model):
    """The CSV files of the run; an output the run did not write is ``null`` (design dedup 6.2)."""

    csv_files_created: Annotated[int, Field(ge=0, le=3)]
    unique: OutputFile | None
    duplicates: OutputFile | None
    duplicates_all: OutputFile | None


class Run(_Model):
    """How the run went. A measure that was not taken is ``null``, never invented."""

    passes: Literal[1, 2]
    storage_mode: Literal["memory", "disk"]
    duration_seconds: Annotated[float, Field(ge=0)]
    first_pass_seconds: Annotated[float, Field(ge=0)]
    second_pass_seconds: Annotated[float, Field(ge=0)] | None
    memory_peak_bytes: Count | None


class Failure(_Model):
    """Why a source failed: a stable ``reason``, a message without path or cell, the limit if any."""

    reason: FailureReason
    message: str
    limit: Count | None = None

    @model_serializer(mode="wrap")
    def _omit_unknown(self, handler: Any) -> dict[str, Any]:
        return _without_none(handler(self), ("limit",))


class Partial(_Model):
    """What a failed run read before it stopped; its result is never certified."""

    records_read: Count | None
    certified: Literal[False] = False


class CompleteReport(_Model):
    """The report of a source that was processed (design dedup 12.2)."""

    format: Literal["tabalyst.dedup"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    generator: ReportGenerator
    status: Literal["complete"]
    source: SourceIdentity
    settings: ReportSettings
    records: Records
    outputs: Outputs
    run: Run

    @model_validator(mode="after")
    def _invariants_hold(self) -> "CompleteReport":
        broken = broken_invariants(self)
        if broken:
            raise ValueError("; ".join(broken))
        return self


class FailedReport(_Model):
    """The report of a source that failed: no count and no output (design dedup 12.4)."""

    format: Literal["tabalyst.dedup"] = FORMAT
    format_version: Literal["0.2.0"] = FORMAT_VERSION
    format_revision: Literal[1] = FORMAT_REVISION
    generator: ReportGenerator
    status: Literal["failed"]
    source: FailedSource
    settings: ReportSettings
    failure: Failure
    partial: Partial


DedupReport = Annotated[CompleteReport | FailedReport, Field(discriminator="status")]
_ADAPTER: TypeAdapter[CompleteReport | FailedReport] = TypeAdapter(DedupReport)


def broken_invariants(report: CompleteReport) -> list[str]:
    """The invariants of design dedup 12.3 that ``report`` breaks, each as a sentence."""
    records, outputs, run = report.records, report.outputs, report.run
    broken: list[str] = []

    def require(holds: bool, rule: str) -> None:
        if not holds:
            broken.append(rule)

    require(
        records.total == records.distinct + records.extra_copies,
        "total = distinct + extra_copies",
    )
    require(
        records.distinct == records.singletons + records.duplicate_groups,
        "distinct = singletons + duplicate_groups",
    )
    require(
        records.duplicate_group_occurrences
        == records.duplicate_groups + records.extra_copies,
        "duplicate_group_occurrences = duplicate_groups + extra_copies",
    )
    require(
        records.duplicate_groups
        == records.groups_occurring_twice + records.groups_occurring_three_plus,
        "duplicate_groups = groups_occurring_twice + groups_occurring_three_plus",
    )
    require(
        0 <= records.singletons <= records.distinct <= records.total,
        "0 <= singletons <= distinct <= total",
    )
    require(
        (records.max_occurrences == 0) == (records.total == 0),
        "max_occurrences is 0 exactly when total is 0",
    )
    require(
        (records.duplicate_groups == 0) == (records.max_occurrences <= 1),
        "duplicate_groups is 0 exactly when max_occurrences <= 1",
    )
    require(
        (records.groups_occurring_three_plus > 0) == (records.max_occurrences >= 3),
        "groups_occurring_three_plus > 0 exactly when max_occurrences >= 3",
    )
    require(
        math.isclose(
            records.extra_copy_percent,
            _extra_copy_percent(records.extra_copies, records.total),
            rel_tol=1e-9,
            abs_tol=1e-12,
        ),
        "extra_copy_percent = 100 * extra_copies / total",
    )
    has_duplicates = records.duplicate_groups > 0
    present = {
        "unique": outputs.unique,
        "duplicates": outputs.duplicates,
        "duplicates_all": outputs.duplicates_all,
    }
    planned = {
        "unique": has_duplicates,
        "duplicates": has_duplicates,
        "duplicates_all": records.max_occurrences >= 3,
    }
    for kind, output in present.items():
        require(
            (output is not None) == planned[kind],
            f"outputs.{kind} is present exactly when the maximum frequency calls for it",
        )
    expected_rows = {
        "unique": records.distinct,
        "duplicates": records.duplicate_groups,
        "duplicates_all": records.duplicate_group_occurrences,
    }
    for kind, output in present.items():
        if output is not None:
            require(
                output.rows == expected_rows[kind],
                f"outputs.{kind}.rows = {_ROW_RULE[kind]}",
            )
    require(
        outputs.csv_files_created == sum(o is not None for o in present.values()),
        "csv_files_created = number of outputs that are not null",
    )
    require(
        (run.passes == 1) == (records.duplicate_groups == 0),
        "passes is 1 exactly when duplicate_groups is 0",
    )
    require(
        (run.second_pass_seconds is None) == (run.passes == 1),
        "second_pass_seconds is null exactly when passes is 1",
    )
    return broken


_ROW_RULE = {
    "unique": "distinct",
    "duplicates": "duplicate_groups",
    "duplicates_all": "duplicate_group_occurrences",
}


def _extra_copy_percent(extra_copies: int, total: int) -> float:
    return 100 * extra_copies / total if total else 0.0


def _without_none(data: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    for name in names:
        if data.get(name, 0) is None:
            del data[name]
    return data


# --------------------------------------------------------------- building


def complete_report(
    source_name: str,
    analysis: DedupAnalysis,
    staged: StagedOutputs,
    settings: DedupSettings,
    *,
    duration_seconds: float,
) -> CompleteReport:
    """The report of a source whose outputs are staged and about to be published.

    The inventory comes from the staged files: their rows, sizes and digests are those
    of what is published. Raises ``DedupReportError`` (``unexpected_error``) if the
    counts break an invariant, which is a defect and is never published.
    """
    stats = analysis.stats
    by_kind = {output.kind: output for output in staged.files}

    def entry(kind: Literal["unique", "duplicates", "duplicates_all"]) -> OutputFile | None:
        output = by_kind.get(kind)
        if output is None:
            return None
        return OutputFile(
            file=output.final.name,
            rows=output.rows,
            size_bytes=output.size_bytes,
            sha256=output.sha256,
        )

    entries = {kind: entry(kind) for kind in ("unique", "duplicates", "duplicates_all")}
    try:
        return CompleteReport(
            generator=ReportGenerator(version=__version__),
            status="complete",
            source=SourceIdentity(
                name=source_name,
                size_bytes=analysis.source.size_bytes,
                mtime_ns=analysis.source.mtime_ns,
                content_sha256=analysis.source.content_sha256,
            ),
            settings=_settings(settings),
            records=_records(stats),
            outputs=Outputs(
                csv_files_created=len(by_kind),
                unique=entries["unique"],
                duplicates=entries["duplicates"],
                duplicates_all=entries["duplicates_all"],
            ),
            run=Run(
                passes=analysis.passes,
                storage_mode="disk" if analysis.storage_mode == "disk" else "memory",
                duration_seconds=duration_seconds,
                first_pass_seconds=analysis.first_pass_seconds,
                second_pass_seconds=(
                    staged.second_pass_seconds if analysis.passes == 2 else None
                ),
                memory_peak_bytes=analysis.memory_peak_bytes,
            ),
        )
    except ValidationError as exc:
        raise DedupReportError(
            "The counts of the run are inconsistent.",
            reason="unexpected_error",
            records_read=stats.total,
        ) from exc


def failed_report(
    source: Path,
    settings: DedupSettings,
    error: DedupInputError | DedupReportError,
) -> FailedReport:
    """The report of a source that failed with ``error`` (design dedup 12.4).

    The size and time of the source are named when they can still be read.
    """
    size_bytes: int | None = None
    mtime_ns: int | None = None
    try:
        status = source.stat()
        size_bytes, mtime_ns = status.st_size, status.st_mtime_ns
    except OSError:
        pass
    return FailedReport(
        generator=ReportGenerator(version=__version__),
        status="failed",
        source=FailedSource(name=source.name, size_bytes=size_bytes, mtime_ns=mtime_ns),
        settings=_settings(settings),
        failure=Failure(
            reason=error.reason,
            message=str(error),
            limit=error.limit if isinstance(error, DedupInputError) else None,
        ),
        partial=Partial(records_read=error.records_read),
    )


def _settings(settings: DedupSettings) -> ReportSettings:
    return ReportSettings(
        max_rows=settings.max_rows,
        delimiter=settings.csv.delimiter,
        encoding=settings.csv.encoding,
    )


def _records(stats: GroupStats) -> Records:
    return Records(
        total=stats.total,
        distinct=stats.distinct,
        singletons=stats.singletons,
        duplicate_groups=stats.duplicate_groups,
        groups_occurring_twice=stats.groups_occurring_twice,
        groups_occurring_three_plus=stats.groups_occurring_three_plus,
        extra_copies=stats.extra_copies,
        duplicate_group_occurrences=stats.duplicate_group_occurrences,
        max_occurrences=stats.max_occurrences,
        extra_copy_percent=_extra_copy_percent(stats.extra_copies, stats.total),
    )


# ------------------------------------------------- reading and writing


def report_json(report: CompleteReport | FailedReport) -> str:
    """The report as the file holds it: indented JSON, one trailing newline."""
    return json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def write_report(path: Path, report: CompleteReport | FailedReport) -> None:
    """Replace ``path`` with ``report`` atomically; ``OSError`` if it cannot be written."""
    write_text_atomic(path, report_json(report))


def parse_report(document: object) -> CompleteReport | FailedReport:
    """Validate a decoded JSON document, the invariants of design dedup 12.3 included.

    Raises ``DedupDocumentError`` for anything that is not a complete or failed report
    of this format and revision; a document that breaks an invariant is not a complete
    report, so the cache can treat it as unreadable.
    """
    try:
        return _ADAPTER.validate_python(document)
    except ValidationError as exc:
        raise DedupDocumentError(_describe(exc)) from exc


def read_report(path: Path) -> CompleteReport | FailedReport:
    """Read and validate the report at ``path``; ``DedupDocumentError`` if it is not valid."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DedupDocumentError("The report cannot be read.") from exc
    try:
        document = json.loads(text)
    except ValueError as exc:
        raise DedupDocumentError("The report is not valid JSON.") from exc
    return parse_report(document)


def _describe(error: ValidationError) -> str:
    # Pydantic's own text echoes the offending value, which could be a cell of a forged file.
    first = error.errors(include_input=False, include_url=False)[0]
    where = ".".join(str(part) for part in first["loc"]) or "document"
    return f"Not a valid Tabalyst Dedup report: {where}: {first['msg']}"


# ------------------------------------------------------------------ schema

_CONSTANTS = ("format", "format_version", "format_revision")


def dedup_schema() -> dict[str, Any]:
    """The schema of a report, in validation mode: what a reader accepts."""
    schema = _ADAPTER.json_schema(mode="validation")
    # An OpenAPI keyword, not JSON Schema: ``status`` is a constant in each variant.
    schema.pop("discriminator", None)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Tabalyst Dedup"
    schema["description"] = (
        f"Document {FORMAT}, format {FORMAT_VERSION} revision {FORMAT_REVISION}: "
        "the report of one source, complete or failed."
    )
    for node in schema["$defs"].values():
        properties = node.get("properties", {})
        required = node.setdefault("required", [])
        for name in _CONSTANTS:
            if name in properties and name not in required:
                required.append(name)
        if not required:
            del node["required"]
    return schema


def dedup_schema_text() -> str:
    """The schema as the committed file writes it."""
    return json.dumps(dedup_schema(), indent=2, ensure_ascii=False) + "\n"
