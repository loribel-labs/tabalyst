# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for Dedup: options, progress, the summaries of design dedup 13.2 and the exit codes."""

import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.terminal import ProgressPrinter, batch_exit_code, error_exit_code
from tabalyst.dedup.report import CompleteReport
from tabalyst.dedup.settings import DedupSettings, resolve_dedup_settings
from tabalyst.dedup_service import BatchDedupResult, DedupResult, execute_dedups
from tabalyst.errors import TabalystError
from tabalyst.progress import ProgressEvent, ProgressPhase

RULE = "-" * 63
LABEL_WIDTH = 22
BLOCK_LABEL_WIDTH = 14
MIB = 1 << 20


def _is_terminal() -> bool:
    """Whether the progress line can be rewritten: only a terminal shows it."""
    return sys.stderr.isatty()


class _DedupProgress(ProgressPrinter):
    """The progress line of Dedup, which also tells how a source ended."""

    def _label(self, event: ProgressEvent) -> str:
        label = super()._label(event)
        if event.detail and event.phase in {ProgressPhase.COMPLETE, ProgressPhase.FAILED}:
            label = f"{label} ({event.detail})"
        return label


def _display(path: Path) -> str:
    """A path relative to the working folder when it is inside it, absolute otherwise."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def _mib(size: int) -> str:
    return f"{size / MIB:,.1f} MiB"


def _labels(sources: list[Path]) -> list[str]:
    """The name of each source, with its folder when two sources share a name."""
    names = [path.name for path in sources]
    return [
        name if names.count(name) == 1 else _display(path)
        for name, path in zip(names, sources, strict=True)
    ]


# ------------------------------------------------------------------- table


def _counts(result: DedupResult) -> tuple[str, str, str]:
    """Rows, extra copies and outputs of a source as the table prints them."""
    if result.status == "FAILED":
        return "-", "-", "-"
    report = result.report
    rows = extra = "-"
    if isinstance(report, CompleteReport):
        rows = f"{report.records.total:,}"
        extra = f"{report.records.extra_copies:,}"
    outputs = "0 new" if result.status == "SKIPPED" else str(len(result.files))
    return rows, extra, outputs


def _table(results: tuple[DedupResult, ...]) -> list[str]:
    labels = _labels([item.source for item in results])
    counts = [_counts(item) for item in results]
    file_width = max([16, *(len(label) for label in labels)])
    rows_width = max([7, *(len(row[0]) for row in counts)])
    extra_width = max([12, *(len(row[1]) for row in counts)])
    width = max(len(RULE), file_width + 2 + 8 + 2 + rows_width + 4 + extra_width + 2 + 7)
    rule = "-" * width
    lines = [
        rule,
        (
            f"{'File':<{file_width}}  {'Status':<8}  {'Rows':<{rows_width}}    "
            f"{'Extra copies':<{extra_width}}  Outputs"
        ),
        rule,
    ]
    for label, item, (rows, extra, outputs) in zip(labels, results, counts, strict=True):
        lines.append(
            f"{label:<{file_width}}  {item.status:<8}  {rows:>{rows_width}}    "
            f"{extra:<{extra_width}}  {outputs}".rstrip()
        )
    lines.append(rule)
    return lines


def _field(label: str, value: object, width: int = LABEL_WIDTH) -> str:
    return f"{label:<{width}}{value}"


def _batch_result(batch: BatchDedupResult) -> str:
    if not batch.results or not batch.failures:
        return "COMPLETE"
    return "FAILED" if len(batch.failures) == len(batch.results) else "PARTIAL"


def _batch_lines(batch: BatchDedupResult, *, verbose: bool) -> list[str]:
    results = batch.results
    done = [item for item in results if item.status == "DONE"]
    skipped = [item for item in results if item.status == "SKIPPED"]
    reports = [item for item in results if item.report_path is not None]
    updated = [item for item in reports if item.status != "SKIPPED"]
    lines = ["Tabalyst Dedup"]
    if results:
        lines += _table(results)
    else:
        lines += [RULE, "No file to process.", RULE]
    lines.append(_field("Eligible files:", len(results)))
    if batch.excluded:
        lines.append(_field("Excluded:", len(batch.excluded)))
    lines += [
        _field("Processed:", len(done)),
        _field("Already processed:", len(skipped)),
        _field("Failed:", len(batch.failures)),
        _field("New CSV files:", sum(len(item.files) for item in results)),
        _field("JSON reports:", f"{len(reports)} available ({len(updated)} updated)"),
        _field(
            "Batch report:",
            _display(batch.batch_report)
            if batch.batch_report is not None
            else ("not written" if batch.batch_report_error is not None else "none"),
        ),
        _field("Result:", _batch_result(batch)),
    ]
    if verbose:
        lines += ["", "Details"]
        for item, label in zip(
            results, _labels([item.source for item in results]), strict=True
        ):
            lines.append(f"  {label}: {_detail(item)}")
        for path, reason in batch.excluded:
            lines.append(f"  {path.name}: excluded ({reason})")
        lines.append(f"Duration: {batch.duration_seconds:.2f}s")
    return lines


def _detail(result: DedupResult) -> str:
    """What --verbose adds for one source: how it ended and, if run, the measures."""
    if result.status == "FAILED":
        return f"failed ({result.reason})"
    if result.status == "SKIPPED":
        return f"already processed, verified by {result.verification}"
    report = result.report
    if not isinstance(report, CompleteReport):
        return "processed"
    run = report.run
    parts = [f"storage {run.storage_mode}", f"{run.passes} pass{'es' if run.passes > 1 else ''}"]
    parts.append(f"first pass {run.first_pass_seconds:.2f}s")
    if run.second_pass_seconds is not None:
        parts.append(f"second pass {run.second_pass_seconds:.2f}s")
    if run.memory_peak_bytes is not None:
        parts.append(f"memory peak {_mib(run.memory_peak_bytes)}")
    return ", ".join(parts)


# ------------------------------------------------------------ one source


def _block_field(label: str, value: object) -> str:
    return _field(label, value, BLOCK_LABEL_WIDTH)


def _single_lines(result: DedupResult, *, verbose: bool) -> list[str]:
    lines = ["Tabalyst Dedup", RULE, _block_field("File:", result.source.name)]
    report = result.report
    failed = result.status == "FAILED"
    if isinstance(report, CompleteReport):
        counts = report.records
        lines += [
            _block_field("Source rows:", f"{counts.total:,}"),
            _block_field("Distinct:", f"{counts.distinct:,}"),
            _block_field("Groups:", f"{counts.duplicate_groups:,}"),
            _block_field("Extra copies:", f"{counts.extra_copies:,}"),
        ]
        if verbose and result.status == "DONE":
            run = report.run
            lines += [
                _block_field("Storage:", run.storage_mode),
                _block_field("Passes:", run.passes),
                _block_field("First pass:", f"{run.first_pass_seconds:.2f}s"),
            ]
            if run.second_pass_seconds is not None:
                lines.append(_block_field("Second pass:", f"{run.second_pass_seconds:.2f}s"))
            if run.memory_peak_bytes is not None:
                lines.append(_block_field("Memory peak:", _mib(run.memory_peak_bytes)))
            lines.append(_block_field("Duration:", f"{run.duration_seconds:.2f}s"))
        lines.append("")
        if result.status == "SKIPPED":
            lines.append(f"Already processed, verified by {result.verification}.")
        elif counts.extra_copies == 0:
            lines.append("No duplicate records found.")
        else:
            lines.append("Duplicate records found.")
        if result.files:
            lines.append("CSV files generated:")
            lines += [f"  {_display(path)}" for path in result.files]
        else:
            lines.append("No CSV files generated.")
    else:
        lines += ["", f"Failed: {result.reason}. No CSV files generated."]
    if result.report_path is not None:
        lines.append(f"Report: {_display(result.report_path)}")
    lines.append(f"Status: {'FAILED' if failed else 'COMPLETE'}")
    return lines


# ----------------------------------------------------------------- command


def _error_lines(batch: BatchDedupResult) -> list[str]:
    """One line per failed source: its reason and its message, never a cell."""
    return [
        f"Error [{item.source.name}]: {item.error} ({item.reason})"
        for item in batch.failures
    ]


def exit_code(batch: BatchDedupResult) -> int:
    """Exit code of design dedup 13.4 for a batch that ran.

    The class of each error decides: 4 when every failure is an input error, 1 as soon as
    one is not. A source refused just before its run (``output_refused``) keeps the class
    of its refusal: a collision with a source is 4, a foreign file is 1, as at the plan.
    A batch report that cannot be written is 1, whatever the sources did.
    """
    errors: list[TabalystError] = [
        item.error for item in batch.failures if item.error is not None
    ]
    if batch.batch_report_error is not None:
        errors.append(batch.batch_report_error)
    return batch_exit_code(errors) if errors else 0


def dedup_command(
    inputs: Annotated[
        list[str],
        typer.Argument(
            metavar="INPUT...",
            help="One or more CSV files or non-recursive glob patterns. Quote a "
            "pattern so that Tabalyst expands it.",
        ),
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-d",
            help="Directory for the outputs and the batch report. Default: beside "
            "each source.",
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="JSON configuration file."),
    ] = None,
    max_rows: Annotated[
        int | None,
        typer.Option(
            "--max-rows",
            help="Most data records a source may hold; more fails that source "
            "(default 10,000,000).",
        ),
    ] = None,
    delimiter: Annotated[
        str | None,
        typer.Option("--delimiter", help="One-character CSV delimiter."),
    ] = None,
    encoding: Annotated[
        str | None,
        typer.Option("--encoding", help="CSV text encoding."),
    ] = None,
    memory_budget_mb: Annotated[
        int | None,
        typer.Option(
            "--memory-budget-mb",
            help="Memory the rows may take before the run continues on disk "
            "(default 512).",
        ),
    ] = None,
    temp_dir: Annotated[
        Path | None,
        typer.Option(
            "--temp-dir",
            help="Folder for the temporary store used when the budget is reached.",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Reprocess sources that are already processed and replace output "
            "files that Dedup did not write. Never replaces a source.",
        ),
    ] = False,
    verify_content: Annotated[
        bool,
        typer.Option(
            "--verify-content",
            help="Decide that a source is already processed from its SHA-256 and "
            "that of its outputs, not from size and modification time. Cannot be "
            "combined with --force.",
        ),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option(
            "--quiet",
            help="Print only the final status, and the errors. Hides the progress.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            help="Add the storage mode, the passes, the durations and the memory "
            "peak, and list the excluded files. Measuring the memory peak "
            "makes the first pass two to four times slower and doubles "
            "the memory used.",
        ),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="Hide the progress line. It is also hidden outside a terminal.",
        ),
    ] = False,
) -> None:
    """Remove exact duplicate rows from CSV files without modifying them.

    For each source, writes <name>.unique.csv (every distinct row once, at its first place), <name>.duplicates.csv (each repeated row once) and, when a row occurs three times or more, <name>.duplicates_all.csv (every occurrence of the repeated rows), plus a JSON report <name>.dedup.json. A source without duplicate gets its report only. A pattern or several inputs also write dedup.summary.json. Two rows are the same only when all their cells are identical: case, spaces and leading zeros count.

    A source that is already processed and unchanged is skipped. A source that fails does not stop the others. Nothing is ever asked: outside a terminal the command behaves the same.

    Exit codes: 0 nothing failed; 1 a failure that is not an input error, or an unwritable batch report; 2 invalid option or configuration; 4 a missing source or only input errors (invalid CSV, row limit, changed source).
    """
    if quiet and no_progress:
        raise typer.BadParameter(
            "--no-progress is redundant with --quiet, which already hides the progress."
        )
    try:
        settings = resolve_dedup_settings(
            config,
            delimiter=delimiter,
            encoding=encoding,
            max_rows=max_rows,
            memory_budget_mb=memory_budget_mb,
            temp_dir=temp_dir,
            output_dir=output_dir,
            force=force,
            verify_content=verify_content,
            quiet=quiet,
            verbose=verbose,
        )
        batch = _run(inputs, settings, no_progress=no_progress)
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc

    for line in _error_lines(batch):
        typer.echo(line, err=True)
    if batch.batch_report_error is not None:
        typer.echo(f"Error: {batch.batch_report_error}", err=True)
    _print_summary(batch, settings)
    code = exit_code(batch)
    if code:
        raise typer.Exit(code)


def _run(
    inputs: list[str], settings: DedupSettings, *, no_progress: bool
) -> BatchDedupResult:
    show = not (settings.quiet or no_progress) and _is_terminal()
    return execute_dedups(
        [os.fspath(item) for item in inputs],
        settings,
        on_progress=_DedupProgress(enabled=show) if show else None,
    )


def _print_summary(batch: BatchDedupResult, settings: DedupSettings) -> None:
    single = not batch.plan.writes_batch_report and len(batch.results) == 1
    if single:
        result = batch.results[0]
        lines = _single_lines(result, verbose=settings.verbose)
        status = lines[-1]
    else:
        lines = _batch_lines(batch, verbose=settings.verbose)
        status = lines[next(i for i, line in enumerate(lines) if line.startswith("Result:"))]
    for line in [status] if settings.quiet else lines:
        typer.echo(line)
