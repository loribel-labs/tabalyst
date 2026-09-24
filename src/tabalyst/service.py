"""Public analysis boundary shared by Python callers and the CLI."""

import json
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter
from typing import Any

from tabalyst.analysis import analyze_dataset
from tabalyst.config import AnalysisConfig, resolve_config
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.execution_log import (
    EXECUTION_LOG_NAME,
    append_execution,
    build_execution_entry,
)
from tabalyst.ingestion import read_csv
from tabalyst.models import DatasetProfile
from tabalyst.reporting import load_profile, render_report

ConfigPath = str | Path | Sequence[str | Path]


def analyze_csv(
    path: str | Path, config: AnalysisConfig | None = None
) -> DatasetProfile:
    """Read and analyze one CSV without coupling callers to the CLI."""
    config = config or AnalysisConfig()
    started = perf_counter()
    profile = analyze_dataset(read_csv(Path(path), config.csv), config)
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


def analyze(
    csv_path: str | Path,
    report_path: str | Path,
    separator: str | None = None,
    encoding: str | None = None,
    config_path: ConfigPath | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Analyze one CSV, write sibling JSON/HTML reports and return the result.

    Explicit ``separator`` and ``encoding`` values override configuration-file
    values, which in turn override Tabalyst's built-in defaults.
    Existing report artifacts require ``force=True`` before replacement.
    """
    started = perf_counter()
    source = Path(csv_path)
    report = Path(report_path)
    config_paths = _config_paths(config_path)
    json_report, execution_report = _validate_paths(
        source,
        report,
        config_paths,
        force=force,
    )
    config = resolve_config(
        config_paths,
        separator=separator,
        encoding=encoding,
    )

    try:
        profile = analyze_csv(source, config)
    except InputError:
        raise
    except OSError as exc:
        raise InputError(f"Cannot read CSV file {source}: {exc}") from exc

    result = profile.model_dump(mode="json")
    json_text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    _write_text(json_report, json_text)
    try:
        html = render_report(load_profile(json_report))
    except OSError as exc:
        raise ReportError(f"Cannot render HTML report {report}: {exc}") from exc
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
    return result
