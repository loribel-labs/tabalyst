# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Second pass of Dedup: write the outputs to temporary files and validate them (design dedup 8.4)."""

import dataclasses
import errno
import glob
import secrets
import time
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from tabalyst.config import CsvConfig
from tabalyst.csv_records import (
    CsvRecordError,
    CsvWriter,
    open_records,
    open_writer,
    output_encoding,
)
from tabalyst.dedup.analysis import (
    STAGE,
    DedupAnalysis,
    OutputKind,
    expected_rows,
    source_changed_error,
    stat_differs,
    stat_source,
)
from tabalyst.dedup.discovery import managed_names
from tabalyst.dedup.failures import DedupInputError, DedupReportError
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    byte_progress,
)


@dataclass(frozen=True)
class StagedFile:
    """An output that is written, validated and not yet published."""

    kind: OutputKind
    temporary: Path
    final: Path
    rows: int
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class StagedOutputs:
    """The outputs of a run, complete and validated, under temporary names.

    Nothing here is visible under a managed name until the publication of
    design dedup 11.5; ``discard`` deletes the temporary files that are left.
    """

    files: tuple[StagedFile, ...]
    second_pass_seconds: float

    def discard(self) -> None:
        """Delete the temporary files that were not published; harmless to repeat."""
        for staged in self.files:
            staged.temporary.unlink(missing_ok=True)


def write_outputs(
    source: str | Path,
    analysis: DedupAnalysis,
    *,
    csv: CsvConfig,
    destination: Path,
    on_progress: ProgressCallback | None = None,
) -> StagedOutputs:
    """Read ``source`` a second time and write the outputs of ``analysis`` as temporary files.

    There is nothing to do (no second reading, ``StagedOutputs`` empty) when the
    analysis found no duplicate group. Otherwise each record goes to the outputs that
    the marks of the first pass assign it (design dedup 8.4), in source order, with
    the conventions of 6.4, in ``destination`` (created if needed) so that the
    publication is an ``os.replace`` on one volume. Each file is flushed and
    ``fsync``ed.

    The set is checked before it is returned: the source is the one of the first pass
    (same size and time, same SHA-256, ``N`` records), then every file holds the
    rows that the counts announce. Raises ``DedupInputError`` (``source_changed``,
    ``source_unreadable``) and ``DedupReportError`` (``output_unwritable``,
    ``insufficient_disk_space``, and ``unexpected_error`` when a count disagrees
    although the source is unchanged). Whatever happens, no temporary file is left
    behind.
    """
    kinds = analysis.outputs
    if not kinds:
        return StagedOutputs((), 0.0)
    path = Path(source)
    started = time.perf_counter()
    temporaries: list[Path] = []
    try:
        files = _stage(path, analysis, csv, destination, kinds, temporaries, on_progress)
    except BaseException:
        # Includes Ctrl-C: an interrupted run must not leave provisional data files.
        for temporary in temporaries:
            temporary.unlink(missing_ok=True)
        raise
    return StagedOutputs(tuple(files), time.perf_counter() - started)


def remove_stale_temporaries(source: Path, destination: Path) -> None:
    """Delete the temporary files that an interrupted run left for the managed names of ``source``.

    Only ``.<managed name>.*.tmp`` files go (design dedup 11.5). A file that cannot
    be deleted is left: the next run tries again, and it must not stop this one.
    """
    for name in (final.name for final in managed_names(source, destination).values()):
        for stale in destination.glob(f".{glob.escape(name)}.*.tmp"):
            try:
                stale.unlink()
            except OSError:
                pass


def _stage(
    path: Path,
    analysis: DedupAnalysis,
    csv: CsvConfig,
    destination: Path,
    kinds: tuple[OutputKind, ...],
    temporaries: list[Path],
    on_progress: ProgressCallback | None,
) -> list[StagedFile]:
    stats = analysis.stats
    before = stat_source(path)
    if (before.st_size, before.st_mtime_ns) != (
        analysis.source.size_bytes,
        analysis.source.mtime_ns,
    ):
        raise source_changed_error(0)
    names = managed_names(path, destination)
    token = secrets.token_hex(4)
    writers: dict[OutputKind, CsvWriter] = {}
    paths: dict[OutputKind, Path] = {}
    try:
        encoding = output_encoding(path, csv.encoding)
        destination.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack, open_records(
            path,
            csv,
            hash_content=True,
            on_bytes=byte_progress(_second_pass(on_progress), path, before.st_size),
        ) as records:
            for kind in kinds:
                temporary = names[kind].with_name(f".{names[kind].name}.{token}.tmp")
                temporaries.append(temporary)
                paths[kind] = temporary
                writers[kind] = stack.enter_context(open_writer(temporary, csv, encoding))
                writers[kind].write_header(records.header)
            unique = writers.get("unique")
            duplicates = writers.get("duplicates")
            everything = writers.get("duplicates_all")
            marks = analysis.marks
            for index, row in enumerate(records):
                if index >= stats.total:
                    raise source_changed_error(index + 1)
                extra = marks.is_extra(index)
                first = marks.is_group_first(index)
                if unique is not None and not extra:
                    unique.write_record(row)
                if duplicates is not None and first:
                    duplicates.write_record(row)
                if everything is not None and (extra or first):
                    everything.write_record(row)
            digest = records.content_digest()
            bytes_read = records.bytes_read
            _check_source(analysis, records.records_read, digest, bytes_read)
    except CsvRecordError as exc:
        # The first pass read this file as a valid table: a different reading is a change.
        if exc.kind == "source_unreadable":
            raise DedupInputError(
                "The source cannot be opened or read.",
                reason="source_unreadable",
                records_read=exc.records_read,
            ) from exc
        raise source_changed_error(exc.records_read) from exc
    except OSError as exc:
        raise _unwritable(exc) from exc
    if stat_differs(before, stat_source(path)):
        raise source_changed_error(stats.total)
    staged: list[StagedFile] = []
    for kind in kinds:
        writer = writers[kind]
        if writer.rows_written != expected_rows(stats, kind):
            raise DedupReportError(
                "An output does not hold the number of rows that the counts announce.",
                reason="unexpected_error",
                records_read=stats.total,
            )
        staged.append(
            StagedFile(
                kind=kind,
                temporary=paths[kind],
                final=names[kind],
                rows=writer.rows_written,
                size_bytes=writer.size_bytes,
                sha256=writer.sha256,
            )
        )
    return staged


def _check_source(
    analysis: DedupAnalysis, records_read: int, digest: str, bytes_read: int
) -> None:
    identity = analysis.source
    if (
        records_read != analysis.stats.total
        or bytes_read != identity.size_bytes
        or digest != identity.content_sha256
    ):
        raise source_changed_error(records_read)


def _unwritable(error: OSError) -> DedupReportError:
    # The message carries no path: the failed report that holds it has none (12.1).
    if error.errno == errno.ENOSPC:
        return DedupReportError(
            "There is not enough disk space to write the outputs.",
            reason="insufficient_disk_space",
        )
    return DedupReportError(
        "An output file cannot be written.", reason="output_unwritable"
    )


def _second_pass(callback: ProgressCallback | None) -> ProgressCallback | None:
    """Name the stage and the phase on every event of the second reading."""
    if callback is None:
        return None

    def forward(event: ProgressEvent) -> None:
        callback(
            dataclasses.replace(event, stage=STAGE, phase=ProgressPhase.WRITING)
        )

    return forward
