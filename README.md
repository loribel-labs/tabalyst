# Tabalyst

**Tools for unfamiliar data.**

Tabalyst is an open-source, local-first toolkit for understanding and working
with structured data.

Its first tool is **Tabalyst Report**. The current CSV implementation,
**Tabalyst CSV Report**, analyzes a CSV file and produces both a structured JSON
profile and a self-contained interactive HTML report.

Tabalyst is in active alpha development. Its interfaces may still change while
the shared toolkit architecture is being established.

## Install

Tabalyst supports Python 3.11, 3.12, 3.13, and 3.14.

```console
pip install tabalyst
```

## Tabalyst Report

| Use case | Command | Destination |
| --- | --- | --- |
| One file, automatic name | `tabalyst report data.csv` | `data.html` beside the source |
| One file, custom name | `tabalyst report data.csv -o report.html` | The file `report.html` |
| Several files, automatic names | `tabalyst report *.csv` | Beside each source |
| Several files, one directory | `tabalyst report *.csv -d reports/` | The directory `reports/` |

The simplest command keeps the source filename:

```console
tabalyst report customers.csv
```

It creates these files beside the source:

```text
customers.csv
customers.html
customers.json
executions.json
```

Use `-o` to choose a different HTML filename for one source:

```console
tabalyst report customers.csv -o customer-analysis.html
```

### Multiple files

Report several CSV files at once:

```console
tabalyst report *.csv
```

Each report is created beside its source and keeps the source stem:

```text
customers.csv → customers.html
orders.csv    → orders.html
products.csv  → products.html
```

Use `-d` to place all reports in one directory:

```console
tabalyst report *.csv -d reports/
```

This produces:

```text
reports/
├── customers.html
├── customers.json
├── orders.html
├── orders.json
├── products.html
├── products.json
└── executions.json
```

Both `-d reports/` and `-d reports` are accepted. Quotes are only needed when a
path contains spaces.

`-o` always names one output file and therefore accepts only one input. `-d`
always names an output directory and accepts one or many inputs.

This is invalid because several inputs cannot share one output file:

```console
tabalyst report *.csv -o report.html
```

Tabalyst rejects the command before processing any file. Use `-d reports/`
instead.

### Safe batch behavior

Before processing begins, Tabalyst resolves every input and planned output. It
stops the entire batch if output names collide or if an output already exists.
Use `--force` only when replacing all matching report artifacts is intentional:

```console
tabalyst report *.csv -d reports/ --force
```

If one CSV is malformed during analysis, Tabalyst reports that error, continues
with the remaining files, and returns a non-zero exit code at the end.

Interactive terminals show accurate file and phase progress:

```text
[2/8] orders.csv - Analyzing
```

Progress and diagnostics use standard error. Progress is disabled automatically
outside a terminal and can be disabled explicitly with `--no-progress` or
`--quiet`.

### Useful options

```console
tabalyst report data.csv --delimiter ";"
tabalyst report data.csv --encoding cp1252
tabalyst report data.csv --config tabalyst.json
tabalyst report data.csv --verbose
tabalyst report --help
tabalyst --version
```

`python -m tabalyst` accepts the same commands.

## What the report analyzes

- Dataset dimensions, missing cells, duplicates, and quality observations.
- Physical and semantic types with confidence and error rates.
- Numeric, date, string-length, normalization, and value distributions.
- Distinct values, representative examples, enum candidates, and date formats.
- CSV record widths, quoting, encoding, and delimiter configuration.
- A bounded raw-data preview while every record is analyzed.

The HTML report is self-contained and works without a CDN or network connection.
The JSON profile contains the same canonical analysis result for scripts and
future Tabalyst tools.

## Python API

The same operations are available without the CLI:

```python
import tabalyst

result = tabalyst.analyze(
    "customers.csv",
    "customers.html",
    separator=";",
)

batch = tabalyst.generate_reports(
    ["*.csv"],
    output_dir="reports",
)
```

`analyze()` returns the JSON-serializable profile for one report.
`generate_reports()` returns the complete batch plan, successes, and failures.
Expected failures derive from `tabalyst.TabalystError`.

Existing artifacts are never replaced silently. Pass `force=True` when
replacement is intentional.

## Configuration

Configuration files are strict JSON. A minimal file is:

```json
{
  "csv": {
    "delimiter": ";",
    "encoding": "cp1252"
  }
}
```

Explicit CLI or Python arguments override the configuration file, which overrides
Tabalyst defaults. See the
[configuration reference](https://github.com/loribel-labs/tabalyst/blob/main/docs/configuration.md)
for all analysis settings.

## Local-first behavior and current limits

Tabalyst performs analysis locally and adds no telemetry or remote processing.
Generated JSON and HTML may contain source values and should be shared
accordingly.

The complete CSV is currently loaded into memory. File and phase progress is
available now; row percentages, throughput estimates, recursive directory input,
and parallel batch execution will require later ingestion work.

## Examples and development

The repository includes small and synthetic public examples under `examples/`.
See the [examples README](https://github.com/loribel-labs/tabalyst/blob/main/examples/README.md)
for regeneration commands.

```console
python -m pytest
python -m ruff check .
python -m build
```

Additional documentation:

- [Architecture](https://github.com/loribel-labs/tabalyst/blob/main/docs/architecture.md)
- [Configuration](https://github.com/loribel-labs/tabalyst/blob/main/docs/configuration.md)
- [Release procedure](https://github.com/loribel-labs/tabalyst/blob/main/RELEASING.md)

Please report defects and feature requests through the
[GitHub issue tracker](https://github.com/loribel-labs/tabalyst/issues).

## License

Tabalyst is released under the [MIT License](LICENSE).

Created by Gregory Borelli — Catalyseur Numérique.
