# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Publication of the outputs of a source, recovery and deletion of the obsolete ones (design dedup 11.5)."""

import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

from tabalyst.dedup.cache import Assessment
from tabalyst.dedup.failures import DedupReportError
from tabalyst.dedup.report import AnyReport, CompleteReport, InProgressReport
from tabalyst.dedup.writer import StagedOutputs

ReportWriter = Callable[[Path, AnyReport], None]


def publish_csv(staged: StagedOutputs) -> tuple[Path, ...]:
    """Move the staged files to their managed names, one by one, with ``os.replace``.

    Returns the published paths. If a replacement fails, the files this call had
    already published and the staged files that remain are deleted, and
    ``DedupReportError`` (``output_unwritable``) is raised. This is step 3 of the
    protocol of design 11.5: ``publish_set`` makes it recoverable across a crash.
    """
    published: list[Path] = []
    try:
        for output in staged.files:
            os.replace(output.temporary, output.final)
            published.append(output.final)
    except OSError as exc:
        for path in published:
            path.unlink(missing_ok=True)
        staged.discard()
        raise DedupReportError(
            "An output file cannot be published.", reason="output_unwritable"
        ) from exc
    return tuple(published)


def delete_outputs(paths: Iterable[Path]) -> None:
    """Delete every path that exists; ``output_unwritable`` if some could not go.

    All of them are tried before the error is raised, so one locked file does not
    keep the others in place.
    """
    stuck = False
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            stuck = True
    if stuck:
        raise DedupReportError(
            "An obsolete output file cannot be deleted.", reason="output_unwritable"
        )


def publish_set(
    staged: StagedOutputs,
    *,
    names: Mapping[str, Path],
    previous: Assessment,
    recovery: InProgressReport,
    report: CompleteReport,
    write: ReportWriter,
) -> tuple[Path, ...]:
    """Steps 2 to 5 of design 11.5: recovery report, CSV, obsolete outputs, final report.

    ``previous`` holds the outputs of the earlier run that are proven. The recovery
    report is written (atomically) before the first change to the outputs, unless
    there is nothing to protect: no previous output and nothing to publish. The owned
    outputs that the new set does not contain are deleted before the final report
    replaces the recovery report. A failure leaves the recovery report in place, so
    that the files already changed stay provable; ``DedupReportError``
    (``output_unwritable``) is raised, and the caller retires the outputs (D2).
    """
    if staged.files or previous.owned:
        _write(write, names["report"], recovery)
    files = publish_csv(staged)
    kept = {output.kind for output in staged.files}
    delete_outputs(names[kind] for kind in previous.owned if kind not in kept)
    _write(write, names["report"], report)
    return files


def retire_outputs(
    *,
    names: Mapping[str, Path],
    current: Assessment,
    recovery: Callable[[], InProgressReport],
    write: ReportWriter,
) -> bool:
    """Delete the owned outputs of a source that failed (D2); whether none is left.

    ``current`` is the ownership read from disk now. The recovery report goes first,
    unless one is already in place, so that an interruption between two deletions
    leaves every file provable. When it returns ``False`` an owned output may still
    exist, and the caller must not replace the report with a failed one: that would
    make those outputs foreign.
    """
    if not current.owned:
        return True
    try:
        if not isinstance(current.report, InProgressReport):
            _write(write, names["report"], recovery())
        delete_outputs(names[kind] for kind in current.owned)
    except DedupReportError:
        return False
    return True


def _write(write: ReportWriter, path: Path, report: AnyReport) -> None:
    try:
        write(path, report)
    except OSError as exc:
        raise DedupReportError(
            "The report cannot be written.", reason="output_unwritable"
        ) from exc
