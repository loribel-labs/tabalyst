"""Public analysis boundary shared by Python callers and the CLI."""

import json
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.execution_log import (
    EXECUTION_LOG_NAME,
    append_execution,
    build_execution_entry,
)
from tabalyst.models import DatasetProfile
from tabalyst.progress import (
    ProgressCallback,
    ProgressEvent,
    ProgressPhase,
    emit_progress,
)
from tabalyst.report_config import ReportConfig, resolve_report_config
from tabalyst.report_profile import RowFacts, build_profile
from tabalyst.reporting import render_report
from tabalyst.scanner import scan

ConfigPath = str | Path | Sequence[str | Path]


def analyze_csv(
    path: str | Path,
    config: ReportConfig | None = None,
    on_progress: ProgressCallback | None = None,
) -> DatasetProfile:
    """Scan one CSV and build its report profile, without coupling callers to
    the CLI. The CSV is read once."""
    config = config or ReportConfig()
    if not isinstance(config, ReportConfig):
        raise TypeError(
            "analyze_csv() expects a ReportConfig; the analysis settings of "
            "reports moved to ReportConfig.scan (a ScanConfig)."
        )
    source = Path(path)
    if source.suffix.lower() == ".json":
        raise InputError(
            f"Reports of JSON sources are not supported yet: {source}. "
            "Use tabalyst scan to analyze JSON files."
        )
    started = perf_counter()

    def forward(event: ProgressEvent) -> None:
        # The profile is not complete when the scan is.
        if on_progress is not None and event.phase != ProgressPhase.COMPLETE:
            on_progress(event)

    rows = RowFacts(config.scan, config.preview_rows)
    result = scan(source, config=config.scan, on_progress=forward, on_record=rows)
    emit_progress(on_progress, source, ProgressPhase.ANALYZING)
    profile = build_profile(result, rows, config)
    profile.processing_seconds = round(perf_counter() - started, 4)
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
    config_paths: list[Path],
    *,
    force: bool,
) -> tuple[Path, Path]:
    if not source.exists():
        raise InputError(f"CSV file does not exist: {source}")
    if not source.is_file():
        raise InputError(f"CSV path is not a file: {source}")
    if report.suffix.lower() != ".html":
        raise InputError("report_path must be a complete filename ending in .html")
    if report.exists() and report.is_dir():
        raise InputError(f"Report path is a directory: {report}")

    json_report = report.with_suffix(".json")
    execution_report = report.parent / EXECUTION_LOG_NAME
    inputs = {source.resolve(), *(path.resolve() for path in config_paths)}
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


def _analyze_resolved(
    source: Path,
    report: Path,
    config: ReportConfig,
    config_paths: list[Path],
    *,
    force: bool,
    on_progress: ProgressCallback | None,
) -> dict[str, Any]:
    started = perf_counter()
    json_report, execution_report = _validate_paths(
        source,
        report,
        config_paths,
        force=force,
    )

    try:
        profile = analyze_csv(source, config, on_progress=on_progress)
    except InputError:
        raise
    except OSError as exc:
        raise InputError(f"Cannot read CSV file {source}: {exc}") from exc

    result = profile.model_dump(mode="json")
    json_text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    emit_progress(on_progress, source, ProgressPhase.RENDERING)
    try:
        html = render_report(profile)
    except OSError as exc:
        raise ReportError(f"Cannot render HTML report {report}: {exc}") from exc

    emit_progress(on_progress, source, ProgressPhase.WRITING)
    _write_text(json_report, json_text)
    _write_text(report, html)
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
    emit_progress(on_progress, source, ProgressPhase.COMPLETE)
    return result


def analyze(
    csv_path: str | Path,
    report_path: str | Path,
    separator: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Analyze one CSV, write sibling JSON/HTML reports and return the result.

    The analysis settings come from the ``scan`` object of the configuration
    files. Explicit ``separator`` and ``encoding`` values override their
    ``scan.csv`` values, which in turn override Tabalyst's built-in defaults.
    Existing report artifacts require ``force=True`` before replacement.
    """
    source = Path(csv_path)
    report = Path(report_path)
    config_paths = _config_paths(config_path)
    config = resolve_report_config(
        config_paths,
        separator=separator,
        encoding=encoding,
    )
    return _analyze_resolved(
        source,
        report,
        config,
        config_paths,
        force=force,
        on_progress=None,
    )
