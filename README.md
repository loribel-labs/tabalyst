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
pip install --upgrade tabalyst
```

The same command installs Tabalyst or updates it. Tabalyst is in alpha and
changes often: update it before each new test.

## Tabalyst Report

| Use case | Command | Destination |
| --- | --- | --- |
| One file, automatic name | `tabalyst report data.csv` | `data.html` beside the source |
| One file, custom name | `tabalyst report data.csv -o report.html` | The file `report.html` |
| Several files, automatic names | `tabalyst report *.csv` | Beside each source |
| Several files, one directory | `tabalyst report *.csv -d reports/` | The directory `reports/` |
| One JSON file | `tabalyst report data.json` | `data.report.html` beside the source |
| From a scan document | `tabalyst report --scan data.scan.json` | `data.html` beside the scan |

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

### JSON files

A JSON file gets a report too, named `<stem>.report.html` so its profile
`<stem>.report.json` never replaces the source. Each collection of records,
such as the `customers` array of `{"customers": [...]}`, is a dataset of the
report, and nested fields are columns named by their path, such as
`address.city`:

```console
tabalyst report orders.json
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
tabalyst report data.csv --workers 4
tabalyst report --help
tabalyst --version
```

`python -m tabalyst` accepts the same commands.

## Tabalyst Sample

Create a smaller CSV without modifying the source:

```console
tabalyst sample customers.csv --sample-method random --rows 1000 --seed 42
```

The default output is `customers.sample.csv` beside the source. Use `-o` to
name the output for one input, or `-d` to sample several files into one
directory:

```console
tabalyst sample customers.csv --sample-method first --rows 100 -o test.csv
tabalyst sample *.csv --sample-method random --percent 5 -d samples/
```

Available methods are `first`, `last`, `random` and `stratified`. Stratified
sampling approximately preserves the distribution of a selected field:

```console
tabalyst sample customers.csv --sample-method stratified --field province --rows 1000 --seed 42
```

Sampling reads CSV records as a stream. Random and stratified sampling keep
only the requested sample, plus stratum counts, in memory. Existing outputs
require `--force`, and an input file is never overwritten.

## Tabalyst Scan

Describe every field of a CSV or JSON file in one JSON document:

```console
tabalyst scan customers.csv
tabalyst scan orders.json --collection "$.customers[]"
```

The default output is `customers.scan.json` beside the source; `-o`, `-d` and
`--force` work as for the other commands. Tabalyst Scan reads the file once as
a stream, with memory bounded by configurable limits, and records for each
field its presence, native types, missing values, frequencies, exact
statistics, normalization variants, technical type and the result of every
detector: numbers with decimal commas, dates, booleans, enumerations, email
addresses, URLs, phone numbers, postal codes, currency amounts, percentages,
quantities, UUIDs and IP addresses. Values of sensitive fields, such as email
addresses, are masked by default. Results are written atomically: an
interrupted scan never leaves a partial file. Files of 16 MiB or more are
analyzed by several worker processes, with the same result; `--workers`
chooses their number, `--workers 1` keeps one process.

Build the report from a scan document without reading the source again:

```console
tabalyst report --scan customers.scan.json
```

Tabalyst refuses a scan whose source changed since it was written, or whose
settings differ from the `scan` settings of `--config`.

See [Scan CSV and JSON files](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/how-to/scan-files.md)
and the [scan format](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/reference/scan-format.md).

## What the report analyzes

- Dataset dimensions, missing cells, duplicates, and quality observations.
- Physical and semantic types with confidence and error rates.
- Numeric, date, string-length, normalization, and value distributions.
- Distinct values, representative examples, date formats, and semantic types
  such as enumerations, email addresses, phone numbers, and postal codes.
- CSV record widths, quoting, encoding, and delimiter configuration.
- A bounded raw-data preview while every record is analyzed.

The report is built on Tabalyst Scan: it reads the CSV once as a stream and
masks values of sensitive columns, such as email addresses, by default.
Ambiguous dates stay ambiguous; the report shows the evidence of the column
without applying it. The HTML report is self-contained and works without a CDN
or network connection.
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

sample = tabalyst.sample_csv(
    "customers.csv",
    method="random",
    rows=1000,
    seed=42,
)

scan = tabalyst.scan("orders.json")
scans = tabalyst.generate_scans(["data/*.json"], output_dir="scans")
reports = tabalyst.generate_reports(["scans/*.scan.json"], from_scan=True)
```

`analyze()` returns the JSON-serializable profile for one report.
`generate_reports()` returns the complete batch plan, successes, and failures.
`scan()` returns a scan result without writing anything; `generate_scans()`
writes one `.scan.json` document per source; `from_scan=True` builds reports
from such documents.
Expected failures derive from `tabalyst.TabalystError`.

Existing artifacts are never replaced silently. Pass `force=True` when
replacement is intentional.

## Configuration

Configuration files are strict JSON. A minimal file is:

```json
{
  "scan": {
    "csv": {
      "delimiter": ";",
      "encoding": "cp1252"
    },
    "values": {"null_markers": ["N/A"]}
  }
}
```

Analysis settings, CSV reading included, go in the `scan` object, shared by
`tabalyst report` and `tabalyst scan`. Top-level settings shape the report
presentation, and `csv` configures `tabalyst sample`. Explicit CLI or Python
arguments override the configuration file, which overrides Tabalyst defaults.
No configuration file is loaded unless it is passed with `--config`. See the
[configuration reference](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/reference/configuration.md)
for all analysis settings.

## Local-first behavior and current limits

Tabalyst performs analysis locally and adds no telemetry or remote processing.
Generated JSON and HTML may contain source values and should be shared
accordingly.

Reports, samples, and scans read files as a stream, with memory bounded by
configurable limits, including duplicate-row detection
(`scan.limits.max_tracked_records`). Reports and scans show the share of the file read;
throughput estimates, recursive directory input, and parallel batch execution
will require later work.

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

- [Architecture](https://github.com/loribel-labs/tabalyst/blob/main/docs/dev/architecture.md)
- [Configuration](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/reference/configuration.md)
- [Release procedure](https://github.com/loribel-labs/tabalyst/blob/main/RELEASING.md)

Please report defects and feature requests through the
[GitHub issue tracker](https://github.com/loribel-labs/tabalyst/issues).

## License

Tabalyst is released under the [MIT License](LICENSE).

Created by Gregory Borelli — Catalyseur Numérique.
