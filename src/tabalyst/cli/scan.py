# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""CLI adapter for Tabalyst Scan."""

import sys
from pathlib import Path
from typing import Annotated

import typer

from tabalyst.cli.confirm import (
    EXIT_CONFIRMATION_REQUIRED,
    Decision,
    confirm_second_pass,
)
from tabalyst.cli.terminal import (
    COLLECTION_HELP,
    ProgressPrinter,
    batch_exit_code,
    collection_paths,
    error_exit_code,
    error_text,
    plural,
)
from tabalyst.deep_service import (
    BatchDeepResult,
    DeepPreparation,
    execute_deep,
    prepare_deep,
)
from tabalyst.errors import TabalystError
from tabalyst.plan_service import BatchPlanResult, generate_plans
from tabalyst.scan_service import BatchScanResult, ScanSuccess, generate_scans
from tabalyst.scanner.planner import Stratify, plan_text
from tabalyst.scanner.planner.render import confirmation_lines, estimate_text
from tabalyst.scanner.smart import Smart, sampling_plan_text


def _counts(success: ScanSuccess) -> tuple[str, str, str]:
    result = success.result
    fields = sum(len(dataset.fields) for dataset in result.datasets)
    return (
        plural(result.scope.records_analyzed, "record"),
        plural(len(result.datasets), "dataset"),
        plural(fields, "field"),
    )


def _print_success(success: ScanSuccess, *, verbose: bool) -> None:
    records, datasets, fields = _counts(success)
    typer.echo(f"Scanned {records}: {datasets}, {fields}.", err=True)
    typer.echo(f"Scan: {success.job.output.resolve()}", err=True)
    if verbose:
        result = success.result
        typer.echo(f"Format: {result.source.format}", err=True)
        if result.source.encoding is not None:
            typer.echo(f"Encoding: {result.source.encoding}", err=True)
        if result.source.excel is not None:
            typer.echo(f"Table: {result.source.excel.dataset_path}", err=True)
        if result.source.csv is not None:
            typer.echo(f"Delimiter: {result.source.csv.delimiter!r}", err=True)
        typer.echo(f"Status: {result.status}", err=True)
        typer.echo(f"Diagnostics: {len(result.diagnostics)}", err=True)
        typer.echo(f"Duration: {result.run.duration_seconds:.2f} s", err=True)


def _print_partial(success: ScanSuccess) -> None:
    scope = success.result.scope
    reasons = ", ".join(
        f"{reason}: {count:,}" for reason, count in sorted(scope.exclusions.items())
    )
    typer.echo(
        f"Warning [{success.job.source}]: partial scan, "
        f"{plural(scope.records_excluded, 'record')} excluded ({reasons}).",
        err=True,
    )


def _print_batch_result(
    batch: BatchScanResult, *, quiet: bool, verbose: bool
) -> None:
    if not quiet:
        if len(batch.plan.jobs) == 1 and batch.successes:
            _print_success(batch.successes[0], verbose=verbose)
        else:
            for success in batch.successes:
                typer.echo(
                    f"Scan: {success.job.source} -> {success.job.output.resolve()}",
                    err=True,
                )
                if verbose:
                    records, datasets, fields = _counts(success)
                    typer.echo(
                        f"  {records} | {datasets} | {fields} | "
                        f"{success.result.source.format} | "
                        f"{success.result.status}",
                        err=True,
                    )

    for source, warning in batch.plan.warnings:
        typer.echo(f"Warning [{source}]: {warning}", err=True)
    for success in batch.successes:
        if success.result.status == "partial":
            _print_partial(success)
        for warning in success.warnings:
            typer.echo(f"Warning [{success.job.source}]: {warning}", err=True)
    for failure in batch.failures:
        typer.echo(
            f"Error [{failure.job.source}]: {error_text(failure.error, 'scan')}",
            err=True,
        )

    if len(batch.plan.jobs) > 1 and (not quiet or batch.failures):
        typer.echo(
            f"{len(batch.successes)} succeeded, {len(batch.failures)} failed",
            err=True,
        )


def _print_plans(batch: BatchPlanResult, *, quiet: bool) -> None:
    """The plans on standard output, what produced them on standard error."""
    for warning_source, warning in batch.warnings:
        typer.echo(f"Warning [{warning_source}]: {warning}", err=True)
    for index, success in enumerate(batch.successes):
        if not quiet:
            how = "reused" if success.reused else "scanned"
            typer.echo(f"Scan: {success.job.output} ({how})", err=True)
        for warning in success.warnings:
            typer.echo(f"Warning [{success.job.source}]: {warning}", err=True)
        if index:
            typer.echo("")
        typer.echo(
            plan_text(success.plan, success.job.source.name, success.confirmation)
        )
        if success.sampling is not None:
            typer.echo("")
            typer.echo(sampling_plan_text(success.sampling, success.job.source.name))
    if len(batch.successes) > 1 and batch.confirmation is not None:
        typer.echo("")
        typer.echo("All together:")
        for line in confirmation_lines(batch.confirmation):
            typer.echo(f"  {line}")
    for failure in batch.failures:
        typer.echo(
            f"Error [{failure.job.source}]: {error_text(failure.error, 'scan')}",
            err=True,
        )


def _announce(preparation: DeepPreparation, *, quiet: bool) -> None:
    """Name the second pass before it starts: it reads each source again."""
    if quiet:
        return
    for job in preparation.jobs:
        count = job.pending
        if not count:
            if job.second.plan.summary.selected:
                typer.echo(
                    f"Second pass [{job.source.name}]: every result is already "
                    "stored, the source is not read again.",
                    err=True,
                )
            continue
        estimate = job.second.estimate
        timing = "" if estimate is None else f", estimated {estimate_text(estimate)}"
        typer.echo(
            f"Second pass [{job.source.name}]: reading the source again for "
            f"{plural(count, 'analysis')}{timing}.",
            err=True,
        )


def _print_deep_result(result: BatchDeepResult, *, quiet: bool, verbose: bool) -> None:
    for success in result.successes:
        document = success.outcome.document
        source = success.job.source
        for entry in document.analyses:
            if entry.status in ("failed", "limited"):
                detail = f" ({entry.detail})" if entry.detail else ""
                typer.echo(
                    f"Warning [{source}]: {entry.id} is {entry.status}: "
                    f"{entry.reason}{detail}.",
                    err=True,
                )
        skipped = [entry.analyzer for entry in document.analyses if entry.status == "skipped"]
        if skipped:
            typer.echo(
                f"Warning [{source}]: {plural(len(skipped), 'analysis')} cannot run "
                f"in this version and {'was' if len(skipped) == 1 else 'were'} skipped.",
                err=True,
            )
        if quiet:
            continue
        if not document.analyses:
            typer.echo(
                f"Second pass [{source.name}]: nothing to add, the scan already "
                "answers what a second pass could.",
                err=True,
            )
            continue
        run = document.run
        typer.echo(
            f"Second pass: {success.job.deep_path.resolve()} "
            f"({plural(len(document.analyses), 'analysis')}: {run.executed} computed, "
            f"{run.reused} reused"
            f"{'' if success.written else ', unchanged'})",
            err=True,
        )
        if verbose:
            typer.echo(
                f"  Source read: {'yes' if run.source_read else 'no'}; verified: "
                f"{'yes' if run.source_verified else 'no'}; "
                f"{run.cells_read:,} cells in {run.duration_seconds:.2f} s",
                err=True,
            )
    for failure in result.failures:
        typer.echo(
            f"Error [{failure.job.source}]: {error_text(failure.error, 'scan')}",
            err=True,
        )


def _run_deep(
    inputs: list[str],
    *,
    output: Path | None,
    output_dir: Path | None,
    config: list[Path] | None,
    delimiter: str | None,
    encoding: str | None,
    collection: list[str] | None,
    force: bool,
    quiet: bool,
    verbose: bool,
    progress: ProgressPrinter,
    workers: int | None,
    counters: bool,
    yes: bool,
) -> None:
    """``tabalyst scan --deep``: the first pass unless the stored Scan is
    current, then the second pass, asking first when the rule R1 says so."""
    try:
        preparation = prepare_deep(
            inputs,
            output=output,
            output_dir=output_dir,
            config_path=config,
            delimiter=delimiter,
            encoding=encoding,
            collections=collection_paths(collection),
            force=force,
            on_progress=progress,
            workers=workers,
            counters=counters,
        )
    except TabalystError as exc:
        typer.echo(f"Error: {error_text(exc, 'scan')}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc
    for warning_source, warning in preparation.warnings:
        typer.echo(f"Warning [{warning_source}]: {warning}", err=True)
    for job in preparation.jobs:
        if not quiet:
            how = "reused" if job.scan.reused else "scanned"
            typer.echo(f"Scan: {job.scan.job.output} ({how})", err=True)
        if job.scan.result.status == "partial":
            _print_partial(job.scan)
        for warning in job.scan.warnings:
            typer.echo(f"Warning [{job.source}]: {warning}", err=True)
    for failure in preparation.failures:
        typer.echo(
            f"Error [{failure.job.source}]: {error_text(failure.error, 'scan')}",
            err=True,
        )
    errors = [failure.error for failure in preparation.failures]
    if preparation.jobs:
        assert preparation.confirmation is not None
        decision = confirm_second_pass(preparation.confirmation, assume_yes=yes)
        if decision is Decision.DECLINED:
            typer.echo("Nothing was started.", err=True)
        if decision is not Decision.PROCEED:
            raise typer.Exit(EXIT_CONFIRMATION_REQUIRED)
        _announce(preparation, quiet=quiet)
        try:
            result = execute_deep(preparation, confirmed=True, on_progress=progress)
        except TabalystError as exc:
            typer.echo(f"Error: {error_text(exc, 'scan')}", err=True)
            raise typer.Exit(error_exit_code(exc)) from exc
        _print_deep_result(result, quiet=quiet, verbose=verbose)
        errors += [failure.error for failure in result.failures]
    if errors:
        raise typer.Exit(batch_exit_code(errors))


def scan_command(
    inputs: Annotated[
        list[str],
        typer.Argument(
            metavar="INPUT...",
            help="One or more CSV or JSON files, or non-recursive glob patterns.",
        ),
    ],
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Explicit scan filename ending in .json, for a single input.",
        ),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output-dir",
            "-d",
            help="Directory for scans named after their source files.",
        ),
    ] = None,
    config: Annotated[
        list[Path] | None,
        typer.Option(
            "--config",
            "-c",
            help="JSON configuration file; repeat to merge several, in order.",
        ),
    ] = None,
    collection: Annotated[
        list[str] | None,
        typer.Option(
            "--collection",
            help=COLLECTION_HELP,
        ),
    ] = None,
    delimiter: Annotated[
        str | None,
        typer.Option("--delimiter", help="Override the one-character CSV delimiter."),
    ] = None,
    encoding: Annotated[
        str | None,
        typer.Option("--encoding", help="Override the CSV text encoding."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Replace existing scan files."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress success messages."),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detected source details."),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Disable interactive progress."),
    ] = False,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers",
            min=1,
            help=(
                "Processes that analyze values: 1 for one process. By default, "
                "files of 16 MiB or more use one per spare processor."
            ),
        ),
    ] = None,
    counters: Annotated[
        bool,
        typer.Option(
            "--counters",
            help="Add the work counters of the samplers to run.counters.",
        ),
    ] = False,
    plan: Annotated[
        bool,
        typer.Option(
            "--plan",
            help=(
                "Show the analyses a second pass could add, without running "
                "them. Uses the current stored scan or makes one."
            ),
        ),
    ] = False,
    stratify: Annotated[
        bool,
        typer.Option(
            "--stratify",
            help=(
                "With --plan, add advice on stratified sampling: which columns "
                "make good keys and how many strata each makes."
            ),
        ),
    ] = False,
    stratify_by: Annotated[
        list[str] | None,
        typer.Option(
            "--stratify-by",
            metavar="FIELDS",
            help=(
                "With --plan, assess the strata of several columns together, "
                "given as a comma-separated list. Repeat it for other "
                "combinations. Implies --stratify."
            ),
        ),
    ] = None,
    smart: Annotated[
        bool,
        typer.Option(
            "--smart",
            help=(
                "With --plan, add the plan of a smart sample: the targets it "
                "would aim to cover, their weights and the readings of the "
                "source it would take. With --deep, the second pass counts "
                "among them."
            ),
        ),
    ] = False,
    sample_size: Annotated[
        int | None,
        typer.Option(
            "--sample-size",
            min=1,
            help=(
                "With --stratify, --stratify-by or --smart, the number of rows "
                "the sample would hold."
            ),
        ),
    ] = None,
    deep: Annotated[
        bool,
        typer.Option(
            "--deep",
            help=(
                "Run the second pass: read each source again and add the "
                "histograms the scan lacks, in <name>.deep.json. Asks first when "
                "it is costly. With --plan, show that plan without running it."
            ),
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help=(
                "With --deep, start a costly second pass without asking. "
                "Outside a terminal, a costly second pass needs it (exit code 3)."
            ),
        ),
    ] = False,
) -> None:
    """Scan CSV and JSON files into a complete JSON description of their data."""
    if quiet and verbose:
        raise typer.BadParameter("--quiet and --verbose cannot be used together.")
    if yes and (not deep or plan):
        raise typer.BadParameter(
            "--yes only goes with --deep, to start the second pass without asking."
        )
    advise = stratify or bool(stratify_by)
    if (advise or smart or sample_size is not None) and not plan:
        raise typer.BadParameter(
            "--stratify, --smart and --sample-size go with --plan: "
            "the advice is part of the plan."
        )
    if sample_size is not None and not (advise or smart):
        raise typer.BadParameter(
            "--sample-size goes with --stratify, --stratify-by or --smart."
        )
    if plan:
        for name, given in (
            ("--output", output is not None),
            ("--output-dir", output_dir is not None),
            ("--force", force),
            ("--counters", counters),
        ):
            if given:
                raise typer.BadParameter(f"{name} cannot be used with --plan: a plan writes nothing.")

    progress = ProgressPrinter(
        enabled=not quiet and not no_progress and sys.stderr.isatty()
    )
    if deep and not plan:
        _run_deep(
            inputs,
            output=output,
            output_dir=output_dir,
            config=config,
            delimiter=delimiter,
            encoding=encoding,
            collection=collection,
            force=force,
            quiet=quiet,
            verbose=verbose,
            progress=progress,
            workers=workers,
            counters=counters,
            yes=yes,
        )
        return
    if plan:
        try:
            plans = generate_plans(
                inputs,
                config_path=config,
                delimiter=delimiter,
                encoding=encoding,
                collections=collection_paths(collection),
                on_progress=progress,
                workers=workers,
                forced=deep,
                stratify=(
                    Stratify(
                        combinations=tuple(
                            tuple(name.strip() for name in item.split(",") if name.strip())
                            for item in stratify_by or ()
                        ),
                        sample_size=sample_size,
                    )
                    if advise
                    else None
                ),
                smart=Smart(size=sample_size) if smart else None,
            )
        except TabalystError as exc:
            typer.echo(f"Error: {error_text(exc, 'scan')}", err=True)
            raise typer.Exit(error_exit_code(exc)) from exc
        _print_plans(plans, quiet=quiet)
        if plans.failures:
            raise typer.Exit(
                batch_exit_code(failure.error for failure in plans.failures)
            )
        return
    try:
        batch = generate_scans(
            inputs,
            output=output,
            output_dir=output_dir,
            config_path=config,
            delimiter=delimiter,
            encoding=encoding,
            collections=collection_paths(collection),
            force=force,
            on_progress=progress,
            workers=workers,
            counters=counters,
            project_storage=True,
        )
    except TabalystError as exc:
        typer.echo(f"Error: {error_text(exc, 'scan')}", err=True)
        raise typer.Exit(error_exit_code(exc)) from exc

    _print_batch_result(batch, quiet=quiet, verbose=verbose)
    if batch.failures:
        raise typer.Exit(
            batch_exit_code(failure.error for failure in batch.failures)
        )
