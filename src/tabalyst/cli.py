from pathlib import Path
from typing import Annotated

import typer

from tabalyst.config import AnalysisConfig, load_config
from tabalyst.reporting import load_profile, render_report
from tabalyst.service import analyze_csv

app = typer.Typer(
    no_args_is_help=True, help="Analyze CSV data and generate HTML reports."
)


def check_outputs(inputs: list[Path], outputs: list[Path]) -> None:
    resolved = [path.resolve() for path in outputs]
    if len(set(resolved)) != len(resolved):
        raise ValueError("JSON and HTML output paths must be different.")
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
        raise ValueError("JSON and HTML outputs refer to the same file.")


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


@app.command()
def analyze(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("report.html"),
    json_output: Annotated[Path | None, typer.Option("--json-output")] = None,
    delimiter: Annotated[str | None, typer.Option("--delimiter")] = None,
    encoding: Annotated[str | None, typer.Option("--encoding")] = None,
    preview_rows: Annotated[
        int | None, typer.Option("--preview-rows", min=0, max=100)
    ] = None,
    config: Annotated[
        list[Path] | None, typer.Option("--config", exists=True, dir_okay=False)
    ] = None,
) -> None:
    """Create dataset.json and an HTML report (UTF-8 CSV, comma delimiter by default)."""
    json_output = json_output or output.with_name("dataset.json")
    try:
        check_outputs([source, *(config or [])], [output, json_output])
        settings = load_config(config or []).model_dump()
        if delimiter is not None:
            settings["csv"]["delimiter"] = delimiter
        if encoding is not None:
            settings["csv"]["encoding"] = encoding
        if preview_rows is not None:
            settings["preview_rows"] = preview_rows
        profile = analyze_csv(source, AnalysisConfig.model_validate(settings))
        write_output(json_output, profile.model_dump_json(indent=2) + "\n")
        write_output(output, render_report(load_profile(json_output)))
    except (OSError, ValueError, LookupError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Analyzed {profile.summary.row_count:,} rows and {profile.summary.column_count} columns."
    )
    typer.echo(f"JSON: {json_output.resolve()}")
    typer.echo(f"HTML: {output.resolve()}")


@app.command()
def render(
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("report.html"),
) -> None:
    """Regenerate HTML from dataset.json without rereading the CSV."""
    try:
        check_outputs([source], [output])
        write_output(output, render_report(load_profile(source)))
    except (OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"HTML: {output.resolve()}")
