# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Public analysis boundary shared by Python callers and the CLI."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from time import perf_counter
from typing import Any
from urllib.parse import quote

from tabalyst.config import (
    DeepSection,
    SettingsFile,
    json_indent,
    load_config_layers,
    settings_from_layer,
)
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.execution_log import (
    EXECUTION_LOG_NAME,
    append_execution,
    build_execution_entry,
)
from tabalyst.inspector.resolution import (
    check_result,
    inspect_notice,
    resolve_interpretation,
)
from tabalyst.json_text import dump_json
from tabalyst.models import AnalysesBlock, ReportProfile
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.report_chain import (
    ChainPlan,
    chain_mode,
    plan_chain,
    require_confirmation,
    run_chain,
)
from tabalyst.report_config import ReportConfig, resolve_report_config
from tabalyst.report_profile import build_profile
from tabalyst.reporting import (
    column_pages,
    dataset_views,
    render_column_report,
    render_report,
)
from tabalyst.scan_reuse import (
    check_config,
    check_source,
    engine_warning,
    load_scan,
    source_path,
)
from tabalyst.scanner import ScanResult, scan
from tabalyst.scanner.identity import source_format_of

ConfigPath = str | Path | Sequence[str | Path]


def analyze_csv(
    path: str | Path,
    config: ReportConfig | None = None,
    on_progress: ProgressCallback | None = None,
    workers: int | None = None,
) -> ReportProfile:
    """Scan one CSV or JSON file and build its report profile, without
    coupling callers to the CLI. The file is read once; ``workers`` is passed
    to ``tabalyst.scan()``."""
    config = config or ReportConfig()
    if not isinstance(config, ReportConfig):
        raise TypeError(
            "analyze_csv() expects a ReportConfig; the analysis settings of "
            "reports moved to ReportConfig.scan (a ScanConfig)."
        )
    source = Path(path)
    started = perf_counter()

    def forward(event: ProgressEvent) -> None:
        # The profile is not complete when the scan is.
        if on_progress is not None and event.phase != ProgressPhase.COMPLETE:
            on_progress(event)

    result = scan(source, config=config.scan, on_progress=forward, workers=workers)
    emit_progress(on_progress, source, ProgressPhase.ANALYZING)
    # The profile records the rules the scan applied, defaults resolved.
    profile = build_profile(result, config.model_copy(update={"scan": result.config}))
    profile.report.processing_seconds = round(perf_counter() - started, 4)
    return profile


def _profile_from_scan(
    scan_path: Path,
    result: ScanResult,
    settings: SettingsFile,
    scan_layer: dict,
    on_progress: ProgressCallback | None,
    *,
    started: float,
) -> tuple[ReportProfile, bool]:
    """The profile of a loaded scan document, after the staleness checks, and
    whether its source was found and checked. It reads no source: the second
    pass contributes what the Scan and the stored results answer (design 18.2)."""
    check_config(scan_path, result, scan_layer)
    checked = check_source(scan_path, result)
    emit_progress(on_progress, scan_path, ProgressPhase.ANALYZING)
    config = ReportConfig.from_settings(settings, result.config)
    chain = plan_chain(
        result,
        scan_path=scan_path,
        source=None,
        mode=chain_mode(settings.deep.mode, deep=False),
        settings=settings.deep.settings(),
        reads_source=False,
        shared=False,
        indent=settings.output.json_indent,
    )
    analyses = run_chain(chain, result, on_progress=on_progress, progress_source=scan_path)
    profile = build_profile(result, config, analyses=analyses)
    # The scan and the report: as long as a report of the source itself.
    profile.report.processing_seconds = round(
        result.run.duration_seconds + perf_counter() - started, 4
    )
    return profile, checked


def analyze_scan(
    scan_path: str | Path,
    config_path: ConfigPath | None = None,
    on_progress: ProgressCallback | None = None,
) -> ReportProfile:
    """Build the report profile of a scan document written by
    ``tabalyst scan``, without reading its source again.

    The presentation settings come from the configuration files. Their
    ``scan`` settings, when given, must be those of the document; a source
    found beside the document must not have changed since the scan (design
    O12). Both raise an error otherwise; a source that is not beside the
    document is not checked. The profile holds the analyses of the second pass
    that the document's stored results (``<stem>.deep.json``) and the Scan
    alone answer; the others are listed as skipped.
    """
    started = perf_counter()
    scan_path = Path(scan_path)
    top_level, scan_layer = load_config_layers(_config_paths(config_path))
    emit_progress(on_progress, scan_path, ProgressPhase.READING)
    profile, _ = _profile_from_scan(
        scan_path,
        load_scan(scan_path),
        settings_from_layer(top_level),
        scan_layer,
        on_progress,
        started=started,
    )
    return profile


def _config_paths(config_path: ConfigPath | None) -> list[Path]:
    if config_path is None:
        return []
    if isinstance(config_path, (str, Path)):
        paths = [Path(config_path)]
    else:
        paths = [Path(path) for path in config_path]
    for path in paths:
        if not path.exists():
            raise ConfigurationError(f"Configuration file does not exist: {path}")
        if not path.is_file():
            raise ConfigurationError(f"Configuration path is not a file: {path}")
    return paths


def _validate_paths(
    source: Path,
    report: Path,
    other_inputs: list[Path],
    *,
    force: bool,
) -> tuple[Path, Path]:
    if not source.exists():
        raise InputError(f"Source file does not exist: {source}")
    if not source.is_file():
        raise InputError(f"Source path is not a file: {source}")
    if report.suffix.lower() != ".html":
        raise InputError("report_path must be a complete filename ending in .html")
    if report.exists() and report.is_dir():
        raise InputError(f"Report path is a directory: {report}")

    json_report = report.with_suffix(".json")
    execution_report = report.parent / EXECUTION_LOG_NAME
    inputs = {source.resolve(), *(path.resolve() for path in other_inputs)}
    outputs = [report.resolve(), json_report.resolve(), execution_report.resolve()]
    if len(set(outputs)) != len(outputs):
        raise InputError("HTML and JSON report paths must be different.")
    for output in outputs:
        if output in inputs:
            raise InputError(f"Report would overwrite an input file: {output}")
    if not force:
        for output in (report, json_report):
            if output.exists():
                raise ReportError(
                    f"Output file already exists: {output}. "
                    "Enable overwrite explicitly to replace it."
                )
    return json_report, execution_report


def _write_text(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise ReportError(f"Cannot write report file {path}: {exc}") from exc


def _retire_column_pages(directory: Path) -> None:
    """Remove only generated column HTML when a forced report omits details."""
    if not directory.is_dir() or directory.is_symlink():
        return
    try:
        for page in directory.iterdir():
            if not re.fullmatch(r"col-\d{2,}-[a-z0-9-]+\.html", page.name):
                continue
            if not page.is_file() or page.is_symlink():
                continue
            with page.open("r", encoding="utf-8", errors="replace") as stream:
                header = stream.read(600)
            if (
                '<meta name="generator" content="Tabalyst column report">' in header
                or '<meta name="description" content="Column profile for ' in header
            ):
                page.unlink()
        if not any(directory.iterdir()):
            directory.rmdir()
    except OSError as exc:
        raise ReportError(f"Cannot remove prior column reports in {directory}: {exc}") from exc


@dataclass(frozen=True)
class ScannedReport:
    """A Report whose Scan is done and whose second pass and files are not.

    ``scan_path`` is the Scan document the second-pass document stands beside;
    ``spent`` the seconds used so far, so that a batch that waits for a
    confirmation does not count the wait in ``processing_seconds``.
    """

    source: Path
    progress_source: Path
    scan_path: Path
    result: ScanResult
    config: ReportConfig
    report: Path
    json_report: Path
    execution_report: Path
    indent: bool
    spent: float
    # Where the source of a scan document is, if it is there.
    source_found: Path | None
    shared: bool
    warnings: tuple[str, ...] = ()
    # Reports of scan documents: whether the source was checked for staleness.
    checked: bool | None = None
    from_scan: bool = False
    # The ``workers`` the Scan was asked for; the second pass honors it.
    workers: int | None = None


def _scan_resolved(
    source: Path,
    report: Path,
    config: ReportConfig,
    config_paths: list[Path],
    *,
    force: bool,
    on_progress: ProgressCallback | None,
    workers: int | None = None,
    scan_layer: dict | None = None,
    separator: str | None = None,
    encoding: str | None = None,
    collections: Sequence[str] | None = None,
) -> ScannedReport:
    """The first pass of a Report of a source: validate the paths and scan it, or
    reuse the current Scan of the shared storage."""
    started = perf_counter()
    indent = json_indent(config_paths)
    json_report, execution_report = _validate_paths(
        source,
        report,
        config_paths,
        force=force,
    )

    warnings: tuple[str, ...] = ()
    try:
        from tabalyst.shared_scan_service import current_scan

        scan_config = config.scan
        check = None
        reused_layer = scan_layer
        source_sha256 = None
        if source_format_of(source) != "csv":
            # A JSON, JSONL or NDJSON source is read with its Inspect
            # configuration, resolved here for both Scan and Report.
            interpretation = resolve_interpretation(
                source,
                scan_layer=scan_layer,
                collections=collections,
                delimiter=separator,
                encoding=encoding,
            )
            scan_config = interpretation.config
            check = partial(check_result, interpretation)
            warnings = interpretation.notices
            source_sha256 = interpretation.source_sha256
            reused_layer = None
        shared = current_scan(
            source,
            scan_config,
            workers=workers,
            json_indent=indent,
            on_progress=on_progress,
            scan_layer=reused_layer,
            delimiter=separator,
            encoding=encoding,
            source_sha256=source_sha256,
            check=check,
        )
        emit_progress(on_progress, source, ProgressPhase.ANALYZING)
        warnings += shared.warnings
    except InputError:
        raise
    except OSError as exc:
        raise InputError(f"Cannot read source file {source}: {exc}") from exc
    return ScannedReport(
        source=source,
        progress_source=source,
        scan_path=shared.path,
        result=shared.result,
        config=config.model_copy(update={"scan": shared.result.config}),
        report=report,
        json_report=json_report,
        execution_report=execution_report,
        indent=indent,
        spent=perf_counter() - started,
        source_found=source,
        shared=True,
        warnings=warnings,
        workers=workers,
    )


def _scan_document_resolved(
    scan_path: Path,
    report: Path,
    settings: SettingsFile,
    scan_layer: dict,
    config_paths: list[Path],
    *,
    force: bool,
    on_progress: ProgressCallback | None,
) -> ScannedReport:
    """The Scan of a Report of a scan document: load it and check that it is
    current. A source beside it that is not the one it read is an error; a
    source that is not there is not checked."""
    started = perf_counter()
    indent = json_indent(config_paths)
    emit_progress(on_progress, scan_path, ProgressPhase.READING)
    result = load_scan(scan_path)
    source = source_path(scan_path, result)
    json_report, execution_report = _validate_paths(
        scan_path,
        report,
        [*config_paths, source],
        force=force,
    )
    check_config(scan_path, result, scan_layer)
    checked = check_source(scan_path, result)
    emit_progress(on_progress, scan_path, ProgressPhase.ANALYZING)
    warnings = [
        warning
        for warning in (engine_warning(result), inspect_notice(source, result))
        if warning is not None
    ]
    return ScannedReport(
        source=source,
        progress_source=scan_path,
        scan_path=scan_path,
        result=result,
        config=ReportConfig.from_settings(settings, result.config),
        report=report,
        json_report=json_report,
        execution_report=execution_report,
        indent=indent,
        spent=perf_counter() - started,
        source_found=source if checked else None,
        shared=False,
        warnings=tuple(warnings),
        checked=checked,
        from_scan=True,
    )


def plan_report_chain(
    scanned: ScannedReport, deep_section: DeepSection, *, deep: bool
) -> ChainPlan:
    """The second pass of a scanned Report. A Report of a scan document reads no
    source unless the second pass is forced (``tabalyst report --scan`` promises
    not to read the sources again)."""
    mode = chain_mode(deep_section.mode, deep=deep)
    return plan_chain(
        scanned.result,
        scan_path=scanned.scan_path,
        source=scanned.source_found,
        mode=mode,
        settings=deep_section.settings(),
        reads_source=not scanned.from_scan or mode == "forced",
        shared=scanned.shared,
        indent=scanned.indent,
        workers=scanned.workers,
    )


def write_scanned_report(
    scanned: ScannedReport,
    chain: ChainPlan | None,
    *,
    force: bool,
    details: bool,
    on_progress: ProgressCallback | None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Run the second pass of a scanned Report, then build, render and write it.
    Returns the profile as a dictionary and the warnings."""
    started = perf_counter()
    analyses: AnalysesBlock | None = None
    if chain is not None:
        analyses = run_chain(
            chain,
            scanned.result,
            on_progress=on_progress,
            progress_source=scanned.progress_source,
        )
    profile = build_profile(scanned.result, scanned.config, analyses=analyses)
    scan_seconds = scanned.result.run.duration_seconds
    profile.report.processing_seconds = round(
        scan_seconds + scanned.spent + perf_counter() - started, 4
    )
    warnings = scanned.warnings
    if analyses is not None and analyses.outcome == "failed" and analyses.reason:
        warnings += (f"the second pass was left out: {analyses.reason}",)
    written = _write_report(
        profile,
        scanned.progress_source,
        scanned.source,
        scanned.report,
        scanned.json_report,
        scanned.execution_report,
        force=force,
        details=details,
        # The history counts the first pass too when it was not made now.
        started=started - scanned.spent - (scan_seconds if scanned.from_scan else 0.0),
        on_progress=on_progress,
        json_indent=scanned.indent,
    )
    return written, warnings


def _write_report(
    profile: ReportProfile,
    progress_source: Path,
    source: Path,
    report: Path,
    json_report: Path,
    execution_report: Path,
    *,
    force: bool,
    details: bool,
    started: float,
    on_progress: ProgressCallback | None,
    json_indent: bool = False,
) -> dict[str, Any]:
    """Render and write the report artifacts of ``profile``; ``source`` names
    the analyzed file in the execution history, ``progress_source`` the input
    in progress events."""
    result = profile.model_dump(mode="json")
    json_text = dump_json(result, indent=json_indent)
    emit_progress(on_progress, progress_source, ProgressPhase.RENDERING)
    views = dataset_views(profile)
    pages = column_pages(profile, report, views) if details else []
    page_dir = report.with_suffix("")
    if details and (
        page_dir.is_symlink() or (page_dir.exists() and not page_dir.is_dir())
    ):
        raise ReportError(f"Column report path is not a regular directory: {page_dir}")
    protected = {path.resolve() for path in (progress_source, source, report, json_report, execution_report)}
    for page, _, _ in pages:
        if page.resolve() in protected:
            raise ReportError(f"Column report would overwrite an input or report file: {page}")
        if page.is_symlink() or (page.exists() and (page.is_dir() or not force)):
            raise ReportError(
                f"Output file already exists: {page}. Enable overwrite explicitly to replace it."
            )
    try:
        links = {
            (dataset.id, column.id): quote(
                page.relative_to(report.parent).as_posix(), safe="/"
            )
            for page, dataset, column in pages
        }
        html = render_report(profile, column_links=links, views=views)
        column_html = [
            (
                page,
                render_column_report(
                    profile, dataset, column, f"../{quote(report.name)}"
                ),
            )
            for page, dataset, column in pages
        ]
    except OSError as exc:
        raise ReportError(f"Cannot render HTML report {report}: {exc}") from exc

    emit_progress(on_progress, progress_source, ProgressPhase.WRITING)
    _write_text(json_report, json_text)
    _write_text(report, html)
    for page, content in column_html:
        _write_text(page, content)
    if not details and force:
        _retire_column_pages(page_dir)
    try:
        entry = build_execution_entry(
            source=source,
            html_output=report,
            json_output=json_report,
            profile=profile,
            total_seconds=perf_counter() - started,
            git_directory=Path.cwd(),
        )
        append_execution(execution_report, entry)
    except (OSError, ValueError) as exc:
        raise ReportError(
            f"Cannot update execution history {execution_report}: {exc}"
        ) from exc
    emit_progress(on_progress, progress_source, ProgressPhase.COMPLETE)
    return result


def analyze(
    csv_path: str | Path,
    report_path: str | Path,
    separator: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
    details: bool = False,
    deep: bool = False,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Analyze one CSV, write sibling JSON/HTML reports and return the result.

    The planner decides whether a second pass has a benefit and a low cost and
    adds it to the report (``analyses``); ``deep=True`` forces it. A forced
    second pass that is costly raises ``ConfirmationRequired`` before it starts,
    unless ``confirmed`` is true: this function never prompts (rule R1).

    The analysis settings come from the ``scan`` object of the configuration
    files. Explicit ``separator`` and ``encoding`` values override their
    ``scan.csv`` values, which in turn override Tabalyst's built-in defaults.
    Existing report artifacts require ``force=True`` before replacement.
    Set ``details=True`` to generate standalone pages for each column.
    """
    source = Path(csv_path)
    report = Path(report_path)
    config_paths = _config_paths(config_path)
    config = resolve_report_config(
        config_paths,
        separator=separator,
        encoding=encoding,
    )
    top_level, scan_layer = load_config_layers(config_paths)
    scanned = _scan_resolved(
        source,
        report,
        config,
        config_paths,
        force=force,
        on_progress=None,
        scan_layer=scan_layer,
        separator=separator,
        encoding=encoding,
    )
    deep_section = settings_from_layer(top_level).deep
    chain = plan_report_chain(scanned, deep_section, deep=deep)
    require_confirmation(chain, confirmed=confirmed)
    result, _ = write_scanned_report(
        scanned, chain, force=force, details=details, on_progress=None
    )
    return result
