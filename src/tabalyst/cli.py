"""Thin command-line adapters over the public Tabalyst API."""

import json
import sys
import tempfile
from pathlib import Path
from typing import Annotated

import typer

from tabalyst import __version__
from tabalyst.config import load_config
from tabalyst.errors import TabalystError
from tabalyst.execution_log import EXECUTION_LOG_NAME
from tabalyst.reporting import load_profile, render_report
from tabalyst.service import analyze as analyze_report

PROJECT_CONFIG_NAME = "tabalyst.json"

# The official 0.1.0 interface is a single command with two positional paths.
official_app = typer.Typer(
    add_completion=False,
    help="Analyze CSV data and generate sibling JSON and HTML reports.",
)

# Keep the alpha subcommands available during the transition to the stable CLI.
app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Legacy alpha commands retained for compatibility.",
)


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
    """Protect legacy commands from overwriting inputs or aliased outputs."""
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
    """Write a UTF-8 text artifact for the legacy render command."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _print_success(result: dict, report_path: Path) -> None:
    summary = result["summary"]
    typer.echo(
        f"Analyzed {summary['row_count']:,} rows and "
        f"{summary['column_count']} columns."
    )
    typer.echo(f"JSON: {report_path.with_suffix('.json').resolve()}")
    typer.echo(f"HTML: {report_path.resolve()}")
    execution_path = (report_path.parent / EXECUTION_LOG_NAME).resolve()
    typer.echo(f"Execution history: {execution_path}")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@official_app.command()
def run(
    csv_path: Annotated[Path, typer.Argument(help="CSV source file.")],
    report_path: Annotated[
        Path, typer.Argument(help="Complete output filename ending in .html.")
    ],
    separator: Annotated[
        str | None, typer.Option("--separator", help="One-character CSV separator.")
    ] = None,
    encoding: Annotated[
        str | None, typer.Option("--encoding", help="CSV text encoding.")
    ] = None,
    config: Annotated[
        Path | None, typer.Option("--config", help="JSON configuration file.")
    ] = None,
    show_version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the installed Tabalyst version and exit.",
            is_eager=True,
            callback=_version_callback,
        ),
    ] = False,
) -> None:
    """Analyze CSV_PATH into REPORT_PATH and its sibling JSON profile."""
    try:
        result = analyze_report(
            csv_path,
            report_path,
            separator=separator,
            encoding=encoding,
            config_path=config,
        )
    except TabalystError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    _print_success(result, report_path)


@app.command("analyze")
def analyze_legacy(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("report.html"),
    delimiter: Annotated[
        str | None, typer.Option("--delimiter", "--separator")
    ] = None,
    encoding: Annotated[str | None, typer.Option("--encoding")] = None,
    preview_rows: Annotated[
        int | None, typer.Option("--preview-rows", min=0, max=100)
    ] = None,
    config: Annotated[
        list[Path] | None, typer.Option("--config", exists=True, dir_okay=False)
    ] = None,
) -> None:
    """Run the alpha command and retain its cumulative execution history."""
    json_output = output.with_suffix(".json")
    execution_output = output.parent / EXECUTION_LOG_NAME
    temporary_config: Path | None = None
    try:
        config_paths = analysis_config_paths(config or [])
        check_outputs(
            [source, *config_paths], [output, json_output, execution_output]
        )
        effective_config = config_paths
        if preview_rows is not None:
            settings = load_config(config_paths).model_dump()
            settings["preview_rows"] = preview_rows
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".json", delete=False
            ) as stream:
                json.dump(settings, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
                temporary_config = Path(stream.name)
            effective_config = [temporary_config]

        result = analyze_report(
            source,
            output,
            separator=delimiter,
            encoding=encoding,
            config_path=effective_config,
        )
    except (TabalystError, OSError, ValueError, LookupError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    finally:
        if temporary_config is not None:
            temporary_config.unlink(missing_ok=True)

    _print_success(result, output)
    if config_paths:
        typer.echo(
            "Configuration: "
            + ", ".join(str(path.resolve()) for path in config_paths)
        )


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


def main() -> None:
    """Dispatch stable syntax while preserving the two alpha subcommands."""
    if len(sys.argv) > 1 and sys.argv[1] in {"analyze", "render"}:
        app()
    else:
        official_app()
