# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Reusable planning and batch execution for Tabalyst Report."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from tabalyst.batch import (
    output_directory,
    path_key,
    plan_outputs,
    resolve_input_specs,
    validate_outputs,
)
from tabalyst.config import load_config_layers, settings_from_layer
from tabalyst.deep_store import ConfirmationRequired
from tabalyst.errors import ConfigurationError, InputError, ReportError, TabalystError
from tabalyst.execution_log import EXECUTION_LOG_NAME
from tabalyst.inspector.choices import collection_slug
from tabalyst.inspector.models import ExcelCandidate, InspectDocument
from tabalyst.inspector.resolution import detect_collections
from tabalyst.option_notices import ignored_options
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.report_chain import ChainPlan
from tabalyst.report_config import resolve_report_config
from tabalyst.scan_reuse import read_scan_document, source_name
from tabalyst.scanner.identity import source_format_of
from tabalyst.scanner.planner import Confirmation, combine_confirmations
from tabalyst.service import (
    ConfigPath,
    ScannedReport,
    _config_paths,
    _scan_document_resolved,
    _scan_resolved,
    plan_report_chain,
    write_scanned_report,
)


@dataclass(frozen=True)
class ReportJob:
    # The source, or the scan document when reusing a scan.
    source: Path
    output: Path
    # The source of a scan document, looked for beside it.
    scanned: Path | None = None
    # Why a scan document cannot be reported, found while planning: the job
    # fails without stopping the batch.
    error: TabalystError | None = None
    # The collection this job reports, set by ``all_collections``: it outranks
    # ``collections`` and the Inspect file, like ``--collection``.
    collection: str | None = None

    @property
    def profile_output(self) -> Path:
        return self.output.with_suffix(".json")

    @property
    def execution_output(self) -> Path:
        return self.output.parent / EXECUTION_LOG_NAME


@dataclass(frozen=True)
class ReportPlan:
    jobs: tuple[ReportJob, ...]
    # What planning left out or could not do, as (source, sentence): the hidden
    # sheets that ``all_collections`` skips.
    warnings: tuple[tuple[Path, str], ...] = ()


@dataclass(frozen=True)
class ReportSuccess:
    job: ReportJob
    result: dict[str, Any]
    # Reports of scan documents: whether the source was found beside the
    # document and checked for staleness.
    source_checked: bool | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReportFailure:
    job: ReportJob
    error: TabalystError


@dataclass(frozen=True)
class BatchReportResult:
    plan: ReportPlan
    successes: tuple[ReportSuccess, ...]
    failures: tuple[ReportFailure, ...]

    @property
    def succeeded(self) -> bool:
        return not self.failures


def report_name(source: Path) -> str:
    """``data.html`` for ``data.csv``; ``data.report.html`` for ``data.json``,
    ``data.jsonl`` and ``data.ndjson``, whose profile ``data.report.json`` must
    not replace the source."""
    if source_format_of(source) != "csv":
        return f"{source.stem}.report.html"
    return f"{source.stem}.html"


def collection_report_name(source: Path, slug: str) -> str:
    """``shop.costs.html`` for the collection ``costs`` of ``shop.xlsx``."""
    return f"{source.stem}.{slug}.html"


def _reportable(document: InspectDocument) -> tuple[list[str], list[str]]:
    """The paths of the collections that ``all_collections`` reports, and the
    hidden sheets it leaves out: the eligible candidates, visible ones only."""
    reported: list[str] = []
    hidden: list[str] = []
    for candidate in document.detection.candidates:
        if not candidate.eligible:
            continue
        if isinstance(candidate, ExcelCandidate) and not candidate.visible:
            hidden.append(candidate.path)
        else:
            reported.append(candidate.path)
    return reported, hidden


def _nothing_to_report(source: Path, hidden: Sequence[str]) -> ConfigurationError:
    if hidden:
        return ConfigurationError(
            f"{source.name} has no visible sheet or table to report; its hidden "
            f"sheets are not reported by --all-collections ({', '.join(hidden)}). "
            "Choose one with --collection. Nothing was analyzed."
        )
    noun = "table" if source_format_of(source) == "excel" else "collection"
    return ConfigurationError(
        f"No supported {noun} was found in {source.name}, so there is nothing to "
        "report. `tabalyst inspect` explains what the file holds. Nothing was "
        "analyzed."
    )


def _collection_jobs(
    source: Path, directory: Path, scan_layer: dict
) -> tuple[list[ReportJob], list[tuple[Path, str]]]:
    """One job per collection of a JSON file or workbook, named
    ``<stem>.<slug>``; a source with one dataset keeps its usual name.

    A source that cannot be inspected, or holds nothing to report, gives one
    job that fails alone."""
    usual = directory / report_name(source)
    if source_format_of(source) not in ("json", "excel"):
        return [ReportJob(source=source, output=usual)], []
    try:
        document, notices = detect_collections(source, scan_layer=scan_layer)
    except TabalystError as exc:
        return [ReportJob(source=source, output=usual, error=exc)], []
    paths, hidden = _reportable(document)
    warnings = [(source, notice) for notice in notices]
    if not paths:
        failure = _nothing_to_report(source, hidden)
        return [ReportJob(source=source, output=usual, error=failure)], warnings
    warnings.extend(
        (source, f"hidden sheet {path} is not reported; choose it with --collection.")
        for path in hidden
    )
    if document.detection.scope.candidates == "truncated":
        warnings.append(
            (
                source,
                (
                    "more sheets, tables or collections than the detection lists; "
                    "only the listed ones are reported."
                ),
            )
        )
    used: set[str] = set()
    jobs = []
    for position, path in enumerate(paths, start=1):
        base = collection_slug(path, position)
        slug, number = base, 1
        while slug in used:
            number += 1
            slug = f"{base}-{number}"
        used.add(slug)
        jobs.append(
            ReportJob(
                source=source,
                output=directory / collection_report_name(source, slug),
                collection=path,
            )
        )
    return jobs, warnings


def _plan_all_collections(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None,
    output_dir: str | Path | None,
    scan_layer: dict,
) -> tuple[tuple[ReportJob, ...], tuple[tuple[Path, str], ...]]:
    if output is not None:
        raise ConfigurationError(
            "--output cannot be used with --all-collections: each collection "
            "gets its own file, named after the source and the collection. Use "
            "--output-dir to choose the folder."
        )
    sources = resolve_input_specs(input_specs)
    if len(sources) > 1 and output_dir is None:
        raise ConfigurationError(
            "--all-collections needs --output-dir (-d) with several inputs, so "
            "that the reports of every file land in one folder."
        )
    destination = output_directory(output_dir)
    jobs: list[ReportJob] = []
    warnings: list[tuple[Path, str]] = []
    for source in sources:
        found, notes = _collection_jobs(
            source,
            destination if destination is not None else source.parent,
            scan_layer,
        )
        jobs.extend(found)
        warnings.extend(notes)
    return tuple(jobs), tuple(warnings)


def build_report_plan(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    force: bool = False,
    from_scan: bool = False,
    all_collections: bool = False,
    scan_layer: dict | None = None,
) -> ReportPlan:
    """Resolve all report paths and reject the whole batch on unsafe plans.

    With ``from_scan``, the inputs are scan documents: reports are named after
    the source each one records, and must not replace that source either. A
    document that cannot be read is named after its own file and fails alone.

    With ``all_collections``, a JSON file or workbook is inspected (with
    ``scan_layer``, the ``scan`` section of the configuration) and gets one job
    per visible, eligible collection, named ``<stem>.<slug>.html``.
    """
    if all_collections:
        jobs, warnings = _plan_all_collections(
            input_specs,
            output=output,
            output_dir=output_dir,
            scan_layer=scan_layer or {},
        )
        _validate_report_plan(jobs, force=force)
        return ReportPlan(jobs=jobs, warnings=warnings)
    names: dict[str, str | TabalystError] = {}

    def recorded(scan_path: Path) -> str | TabalystError:
        key = path_key(scan_path)
        if key not in names:
            try:
                names[key] = source_name(read_scan_document(scan_path))
            except TabalystError as exc:
                names[key] = exc
        return names[key]

    def scan_report_name(scan_path: Path) -> str:
        name = recorded(scan_path)
        if isinstance(name, str):
            return report_name(Path(name))
        stem = scan_path.name.removesuffix(".json").removesuffix(".scan")
        return f"{stem}.html"

    def scan_job(source: Path, target: Path) -> ReportJob:
        name = recorded(source)
        if isinstance(name, str):
            return ReportJob(source=source, output=target, scanned=source.parent / name)
        return ReportJob(source=source, output=target, error=name)

    jobs = tuple(
        scan_job(source, target)
        if from_scan
        else ReportJob(source=source, output=target)
        for source, target in plan_outputs(
            input_specs,
            output=output,
            output_dir=output_dir,
            output_name=scan_report_name if from_scan else report_name,
        )
    )
    _validate_report_plan(jobs, force=force)
    return ReportPlan(jobs=jobs)


def _validate_report_plan(jobs: tuple[ReportJob, ...], *, force: bool) -> None:
    for job in jobs:
        if job.output.suffix.lower() != ".html":
            raise InputError("--output must be a complete filename ending in .html")
        execution_key = path_key(job.execution_output)
        for artifact in (job.output, job.profile_output):
            if path_key(artifact) == execution_key:
                raise ReportError(
                    f"Report artifact conflicts with execution history: {artifact}"
                )
    validate_outputs(
        (
            (job.source, artifact)
            for job in jobs
            for artifact in (job.output, job.profile_output)
        ),
        sources=(
            path
            for job in jobs
            for path in (job.source, job.scanned)
            if path is not None
        ),
        force=force,
        label="Report",
    )


@dataclass(frozen=True)
class _Waiting:
    """A scanned job whose second pass and files come next."""

    index: int
    job: ReportJob
    scanned: ScannedReport
    chain: ChainPlan
    forward: ProgressCallback | None


def generate_reports(
    input_specs: Sequence[str | Path],
    *,
    output: str | Path | None = None,
    output_dir: str | Path | None = None,
    separator: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
    details: bool = False,
    on_progress: ProgressCallback | None = None,
    from_scan: bool = False,
    workers: int | None = None,
    all_collections: bool = False,
    deep: bool = False,
    confirmed: bool = False,
    confirm: Callable[[Confirmation], bool] | None = None,
    dedup_report: str | Path | None = None,
) -> BatchReportResult:
    """Plan and execute one or more reports without depending on the CLI.

    With ``from_scan``, the inputs are scan documents written by
    ``tabalyst scan``: each report is built from its document without reading
    the source again, after the staleness checks of ``tabalyst.scan_reuse``.
    Otherwise ``workers`` is passed to ``tabalyst.scan()``, and ``collections``
    (absolute paths such as ``$.products[]``) choose the JSON collections to
    analyze, over the Inspect file and the configuration.
    Set ``details=True`` to write a standalone HTML page for each column.
    ``all_collections`` reports every visible collection of each JSON file or
    workbook, one pair of files per collection (see ``build_report_plan``).

    The planner decides whether a second pass has a benefit and a low cost and
    adds its analyses to each report (``analyses``, design 20.1); ``deep=True``
    forces it and the ``deep.mode`` setting can turn it off or force it. A
    forced second pass whose estimate passes the thresholds of rule R1 is not
    started before it is confirmed, once for the whole batch: ``confirmed=True``
    says it was, ``confirm`` is asked with the total otherwise, and without
    either ``ConfirmationRequired`` is raised after the sources are scanned and
    before any is read again. This function never prompts. With ``from_scan``
    no source is read unless ``deep`` forces it.

    ``dedup_report`` is a Dedup report (a file, for one source) or a folder holding
    ``<source stem>.dedup.json``: when it is valid for the Scan it proves the copies of rows
    behind ``identifier_uniqueness`` (it replaces the ``report.dedup_report`` setting). A source
    that is not a CSV, or a path that does not exist, is an error, not a silence. Without it a
    ``<stem>.dedup.json`` beside the source is tried.
    """
    if from_scan and (separator is not None or encoding is not None):
        raise ConfigurationError(
            "--delimiter and --encoding cannot be used with --scan: the scan "
            "document records how its source was read."
        )
    if from_scan and workers is not None:
        raise ConfigurationError(
            "--workers cannot be used with --scan: the report reads the scan "
            "document, not its source."
        )
    if from_scan and collections:
        raise ConfigurationError(
            "--collection cannot be used with --scan: the scan document records "
            "which collection it analyzed."
        )
    if all_collections and from_scan:
        raise ConfigurationError(
            "--all-collections cannot be used with --scan: a scan document "
            "records the one collection it analyzed."
        )
    if all_collections and collections:
        raise ConfigurationError(
            "--collection and --all-collections cannot be used together: "
            "choose one collection, or report all of them."
        )
    config_paths = _config_paths(config_path)
    plan = build_report_plan(
        input_specs,
        output=output,
        output_dir=output_dir,
        force=force,
        from_scan=from_scan,
        all_collections=all_collections,
        scan_layer=load_config_layers(config_paths)[1] if all_collections else None,
    )
    if not from_scan:
        sources = dict.fromkeys(job.source for job in plan.jobs)
        notices = tuple(
            (source, notice)
            for source in sources
            for notice in ignored_options(
                source,
                delimiter=separator,
                encoding=encoding,
                collections=collections,
                all_collections=all_collections,
            )
        )
        plan = replace(plan, warnings=(*plan.warnings, *notices))
    top_level, scan_layer = load_config_layers(config_paths)
    settings = settings_from_layer(top_level)
    deep_section = settings.deep
    dedup_option = str(dedup_report) if dedup_report is not None else None
    effective_option = dedup_option if dedup_option is not None else settings.report.dedup_report
    if effective_option is not None and not Path(effective_option).is_dir() and len(plan.jobs) > 1:
        raise ConfigurationError(
            "--dedup-report names one file, which proves one source: give a folder "
            "to report several sources."
        )
    if not from_scan:
        config = resolve_report_config(
            config_paths,
            separator=separator,
            encoding=encoding,
        )
        if dedup_option is not None:
            config = config.model_copy(update={"dedup_report": dedup_option})
    successes: list[ReportSuccess] = []
    failures: list[ReportFailure] = []
    total = len(plan.jobs)
    # Scanned jobs that wait for the confirmation of a forced second pass, which
    # is asked once for the batch (R1). An automatic pass never waits.
    waiting: list[_Waiting] = []

    def forwarder(index: int) -> ProgressCallback | None:
        if on_progress is None:
            return None

        def forward(event: ProgressEvent) -> None:
            on_progress(
                ProgressEvent(
                    source=event.source,
                    phase=event.phase,
                    index=index,
                    total=total,
                    detail=event.detail,
                    bytes_read=event.bytes_read,
                    bytes_total=event.bytes_total,
                    duration_seconds=event.duration_seconds,
                    stage=event.stage,
                )
            )

        return forward

    def fail(index: int, job: ReportJob, exc: TabalystError) -> None:
        failures.append(ReportFailure(job=job, error=exc))
        emit_progress(
            on_progress,
            job.source,
            ProgressPhase.FAILED,
            index=index,
            total=total,
            detail=str(exc),
        )

    def finish(item: _Waiting) -> None:
        try:
            result, warnings = write_scanned_report(
                item.scanned,
                item.chain,
                force=force,
                details=details,
                on_progress=item.forward,
            )
        except TabalystError as exc:
            fail(item.index, item.job, exc)
        else:
            successes.append(
                ReportSuccess(
                    job=item.job,
                    result=result,
                    source_checked=item.scanned.checked,
                    warnings=warnings,
                )
            )

    for index, job in enumerate(plan.jobs, start=1):
        forward = forwarder(index)
        try:
            if job.error is not None:
                raise job.error
            if from_scan:
                scanned = _scan_document_resolved(
                    job.source,
                    job.output,
                    settings,
                    scan_layer,
                    config_paths,
                    force=force,
                    on_progress=forward,
                    dedup_report=dedup_option,
                )
            else:
                scanned = _scan_resolved(
                    job.source,
                    job.output,
                    config,
                    config_paths,
                    force=force,
                    on_progress=forward,
                    workers=workers,
                    scan_layer=scan_layer,
                    separator=separator,
                    encoding=encoding,
                    collections=[job.collection] if job.collection else collections,
                )
            chain = plan_report_chain(scanned, deep_section, deep=deep)
        except TabalystError as exc:
            fail(index, job, exc)
            continue
        item = _Waiting(index, job, scanned, chain, forward)
        if chain.mode == "forced":
            waiting.append(item)
        else:
            finish(item)

    if waiting:
        needing = [
            item.chain.confirmation
            for item in waiting
            if item.chain.confirmation is not None
        ]
        if needing and not confirmed:
            everything = combine_confirmations(needing)
            if everything.required and not (confirm is not None and confirm(everything)):
                raise ConfirmationRequired(everything)
        for item in waiting:
            finish(item)

    return BatchReportResult(
        plan=plan,
        successes=tuple(successes),
        failures=tuple(failures),
    )
