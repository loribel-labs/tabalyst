"""Command-line entry points for CSV analysis and report rendering."""

from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer

from tabalyst.config import AnalysisConfig, load_config
from tabalyst.execution_log import (
    EXECUTION_LOG_NAME,
    append_execution,
    build_execution_entry,
)
from tabalyst.reporting import load_profile, render_report
from tabalyst.service import analyze_csv

app = typer.Typer(
    no_args_is_help=True, help="Analyze CSV data and generate HTML reports."
)
PROJECT_CONFIG_NAME = "tabalyst.json"


def analysis_config_paths(explicit: list[Path]) -> list[Path]:
    """Put the current project's automatic config before explicit overrides."""
    project_config = Path.cwd() / PROJECT_CONFIG_NAME
    paths = [project_config] if project_config.is_file() else []
    known = {path.resolve() for path in paths}
    for path in explicit:
        if path.resolve() not in known:
            paths.append(path)
            known.add(path.resolve())
    return paths


def check_outputs(inputs: list[Path], outputs: list[Path]) -> None:
    resolved = [path.resolve() for path in outputs]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Output paths must be different.")
    for output in outputs:
        if output.resolve() in {path.resolve() for path in inputs}:
            raise ValueError(f"Output would overwrite an input file: {output}")
        if output.exists() and any(output.samefile(path) for path in inputs):
            raise ValueError(f"Output would overwrite an input file: {output}")
        if output.is_dir():
            raise ValueError(f"Output is a directory: {output}")
    if (
        len(outputs) > 1
        and all(path.exists() for path in outputs)
        and outputs[0].samefile(outputs[1])
    ):
        raise ValueError("Outputs refer to the same file.")


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


@app.command()
def analyze(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("report.html"),
    delimiter: Annotated[str | None, typer.Option("--delimiter")] = None,
    encoding: Annotated[str | None, typer.Option("--encoding")] = None,
    preview_rows: Annotated[
        int | None, typer.Option("--preview-rows", min=0, max=100)
    ] = None,
    config: Annotated[
        list[Path] | None, typer.Option("--config", exists=True, dir_okay=False)
    ] = None,
) -> None:
    """Create a named JSON profile, HTML report and execution history."""
    started = perf_counter()
    json_output = output.with_suffix(".json")
    execution_output = output.parent / EXECUTION_LOG_NAME
    try:
        config_paths = analysis_config_paths(config or [])
        check_outputs(
            [source, *config_paths], [output, json_output, execution_output]
        )
        settings = load_config(config_paths).model_dump()
        if delimiter is not None:
            settings["csv"]["delimiter"] = delimiter
        if encoding is not None:
            settings["csv"]["encoding"] = encoding
        if preview_rows is not None:
            settings["preview_rows"] = preview_rows
        profile = analyze_csv(source, AnalysisConfig.model_validate(settings))
        write_output(json_output, profile.model_dump_json(indent=2) + "\n")
        write_output(output, render_report(load_profile(json_output)))
        entry = build_execution_entry(
            source=source,
            html_output=output,
            json_output=json_output,
            profile=profile,
            total_seconds=perf_counter() - started,
            git_directory=Path.cwd(),
        )
        append_execution(execution_output, entry)
    except (OSError, ValueError, LookupError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Analyzed {profile.summary.row_count:,} rows and {profile.summary.column_count} columns."
    )
    if config_paths:
        typer.echo("Configuration: " + ", ".join(str(path.resolve()) for path in config_paths))
    typer.echo(f"JSON: {json_output.resolve()}")
    typer.echo(f"HTML: {output.resolve()}")
    typer.echo(f"Execution history: {execution_output.resolve()}")


@app.command()
def render(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("report.html"),
) -> None:
    """Regenerate HTML from a report JSON profile without rereading the CSV."""
    try:
        check_outputs([source], [output])
        write_output(output, render_report(load_profile(source)))
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"HTML: {output.resolve()}")
