# Tabalyst

**Tools for unfamiliar data.**

Tabalyst is an open-source, local-first toolkit for understanding and working
with structured data before you import it, build around it, or add it to a
pipeline.

Give Tabalyst a file and it helps answer the first practical questions: What is
in it? Is its structure consistent? Which values are missing? What types and
distributions does it contain? Are there quality issues worth investigating?

Tabalyst is not intended to replace pandas, DuckDB, Excel, or a general-purpose
data-science environment. It focuses on the beginning of the data workflow:

> **Understand. Explore. Clean. Validate.**

## Project status

Tabalyst is in active alpha development. Its first available tool is
**Tabalyst Report**. The current CSV implementation can be referred to more
specifically as **Tabalyst CSV Report**.

Tabalyst CSV Report reads a CSV file, produces a structured JSON profile, and
renders the same result as a self-contained interactive HTML report. Future input
formats will use the same `report` command rather than introducing a separate CLI
namespace for each format.

The command-line and Python interfaces may still change incompatibly while the
toolkit architecture is being established.

| Tool | Purpose | Status |
| --- | --- | --- |
| Tabalyst Report (`report`) | Analyze and profile a dataset | Available for CSV |
| Tabalyst Sample (`sample`) | Create a practical or representative subset | Planned |
| Tabalyst Clean (`clean`) | Detect, explain, and apply data-quality fixes | Planned |
| Tabalyst Query (`query`) | Query a dataset directly | Planned |
| Tabalyst Explore (`explore`) | Explore data interactively | Planned |
| Tabalyst Validate (`validate`) | Check data against rules or a schema | Planned |
| Tabalyst Convert (`convert`) | Convert between structured-data formats | Planned |
| Tabalyst Compare (`compare`) | Compare datasets or dataset versions | Planned |

## Install

Tabalyst supports Python 3.11, 3.12, 3.13, and 3.14.

```console
pip install tabalyst
```

For local development from a clone:

```console
python -m venv .venv
python -m pip install -e ".[dev]"
```

## Quick start: Tabalyst CSV Report

Generate a report:

```console
tabalyst report data.csv -o reports/report.html
```

A successful run creates:

```text
reports/
|-- report.html
|-- report.json
`-- executions.json
```

- `report.html` is the self-contained interactive report.
- `report.json` is the canonical, structured analysis result.
- `executions.json` records successful runs in the output directory.

The output path must end in `.html`. Parent directories are created
automatically. Existing report artifacts are protected unless replacement is
explicitly requested:

```console
tabalyst report data.csv -o reports/report.html --force
```

## Command line

The CLI follows one grammar across the toolkit:

```text
tabalyst COMMAND INPUT [OPTIONS]
```

Current report examples:

```console
tabalyst report data.csv -o report.html
tabalyst report data.csv -o report.html --delimiter ";"
tabalyst report data.csv -o report.html --encoding cp1252
tabalyst report data.csv -o report.html --config tabalyst.json
tabalyst report data.csv -o report.html --verbose
tabalyst report data.csv -o report.html --quiet
tabalyst report --help
tabalyst --version
```

`python -m tabalyst` accepts the same arguments.

Success messages, warnings, and diagnostics are written to standard error. This
keeps standard output available for future structured output and pipeline
composition. `--quiet` suppresses success messages, while `--verbose` shows
detected input details.

CLI exit codes are:

| Code | Meaning |
| ---: | --- |
| `0` | Success |
| `1` | Processing or output error |
| `2` | Invalid CLI usage or configuration |
| `4` | Input is unreadable, invalid, or unsupported |

## What Tabalyst Report analyzes

- Dataset dimensions, missing cells, duplicate rows, and quality observations.
- Physical and semantic type inference with confidence and error rates.
- Numeric, date, string-length, normalization, and value-distribution profiles.
- Distinct values, representative examples, enum candidates, and date formats.
- CSV structure, record widths, quoting, encoding, and delimiter configuration.
- A bounded raw-data preview while all records are analyzed.
- Sortable and filterable tables in the Signature HTML report.

Raw strings are preserved. The JSON profile contains the analysis semantics used
by the HTML renderer, so other tools can consume the same result without parsing
the presentation.

## Python API

The report workflow is also available without the CLI:

```python
import tabalyst

result = tabalyst.analyze(
    "data.csv",
    "reports/report.html",
    separator=";",
    encoding="cp1252",
    config_path="tabalyst.json",
)

print(tabalyst.__version__)
print(result["summary"]["row_count"])
```

`analyze()` returns a JSON-serializable dictionary matching the adjacent JSON
profile. Expected failures derive from `tabalyst.TabalystError`; callers can
distinguish `InputError`, `ConfigurationError`, and `ReportError`.

Existing report artifacts are not replaced by default. Pass `force=True` when
replacement is intentional.

## Configuration

Configuration files are strict JSON. Unknown names and invalid values are
rejected. A minimal file is:

```json
{
  "csv": {
    "delimiter": ";",
    "encoding": "cp1252"
  }
}
```

Resolution order is:

1. explicit `separator` or `encoding` Python arguments, or CLI `--delimiter` and
   `--encoding` options;
2. the file passed with `config_path` or `--config`;
3. Tabalyst defaults: comma and `utf-8-sig`.

`utf-8-sig` accepts ordinary UTF-8 and UTF-8 with a byte-order mark. See the
[configuration reference](https://github.com/loribel-labs/tabalyst/blob/main/docs/configuration.md)
for normalization, date detection, type inference, sampling, value examples, and
enum settings.

## Local-first behavior and current limits

Tabalyst performs analysis locally and adds no telemetry or remote processing.
The generated report embeds its design system, fonts, and interaction code, so it
works without a CDN or network connection.

The complete CSV is currently loaded into memory. Progress reporting and accurate
throughput estimates for very large files will be introduced with chunked
ingestion. Generated JSON and HTML may contain source values and should be shared
accordingly.

## Reproducible examples

The repository contains two public synthetic examples:

- `basic`: five rows covering common CSV values and one duplicate row.
- `insurance-customers`: 3,000 fictional customer and contract records across
  34 columns; email addresses use reserved `.example` domains.

Regenerate them from the repository root:

```console
tabalyst report examples/input/basic.csv -o examples/output/basic/report.html --config examples/config.json --force
tabalyst report examples/input/insurance-customers.csv -o examples/output/insurance-customers/report.html --config examples/config.json --force
```

See the [examples README](https://github.com/loribel-labs/tabalyst/blob/main/examples/README.md)
for the complete layout.

## Development

```console
python -m pytest
python -m ruff check .
python -m build
```

Architecture and release documentation:

- [Architecture](https://github.com/loribel-labs/tabalyst/blob/main/docs/architecture.md)
- [Configuration](https://github.com/loribel-labs/tabalyst/blob/main/docs/configuration.md)
- [Packaging and releases](https://github.com/loribel-labs/tabalyst/blob/main/docs/python-package-and-release.md)
- [Release procedure](https://github.com/loribel-labs/tabalyst/blob/main/RELEASING.md)

Please report defects and feature requests through the
[GitHub issue tracker](https://github.com/loribel-labs/tabalyst/issues).

## License

Tabalyst is released under the [MIT License](LICENSE).

Created by Gregory Borelli — Catalyseur Numérique.
