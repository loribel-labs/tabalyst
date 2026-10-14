# Tabalyst

**Open-source Python toolkit for data profiling and data quality analysis.**

*Tools for unfamiliar data.*

Tabalyst helps you understand CSV, Excel, JSON and JSONL datasets with minimal
configuration. Detect missing values, duplicates, mixed types, data formats and
quality issues. Generate interactive HTML reports and structured JSON profiles,
entirely on your computer.

**Simple. Clear. Smart.**

Tabalyst is in beta. Its interfaces may still change while the shared toolkit
architecture is being established.

## Quick start

Tabalyst supports Python 3.11, 3.12, 3.13, and 3.14.

```console
pip install --upgrade tabalyst
tabalyst report customers.csv
```

Explore the interactive HTML report or use the generated JSON profile in your
own workflows. The same `pip` command installs Tabalyst or updates it. Tabalyst
is in beta and changes often: update it before each new test.

[Live demo](https://tabalyst.com/examples/report.html) ·
[Documentation](https://docs.tabalyst.com/) ·
[Website](https://tabalyst.com/)

## What can Tabalyst do?

| Tool | Purpose |
| --- | --- |
| **Tabalyst Report** | Generate interactive HTML profiling reports and JSON profiles |
| **Tabalyst Scan** | Analyze dataset structure, types, statistics and data quality |
| **Tabalyst Inspect** | Discover and configure JSON collections and Excel tables |
| **Tabalyst Sample** | Create random, stratified and smart CSV samples |
| **Tabalyst Generate** | Generate synthetic CSV datasets for testing and demos |

## Tabalyst Report

| Use case | Command | Destination |
| --- | --- | --- |
| One file, automatic name | `tabalyst report data.csv` | `data.html` beside the source |
| One file, custom name | `tabalyst report data.csv -o report.html` | The file `report.html` |
| Several files, automatic names | `tabalyst report *.csv` | Beside each source |
| Several files, one directory | `tabalyst report *.csv -d reports/` | The directory `reports/` |
| One JSON file | `tabalyst report data.json` | `data.report.html` beside the source |
| One JSONL file | `tabalyst report events.jsonl` | `events.report.html` beside the source |
| One Excel workbook | `tabalyst report sales.xlsx` | `sales.report.html` beside the source |
| Every table of a workbook | `tabalyst report shop.xlsx --all-collections` | `shop.costs.html`, `shop.sales.html`, ... beside the source |
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

Add `--details` to generate one self-contained HTML page per column, and `-o`
to choose another HTML filename for one source:

```console
tabalyst report customers.csv --details
tabalyst report customers.csv -o customer-analysis.html
```

Existing outputs are never replaced silently: add `--force` when replacement is
intentional. A batch is checked for name collisions before any file is
processed, and a malformed file does not stop the others.

JSON, JSONL and Excel sources work the same way. When a JSON file or a workbook
holds several equally plausible collections, Tabalyst stops and prints one
command per candidate to copy, such as
`tabalyst report shop.xlsx --collection Costs`.

Useful options: `--delimiter`, `--encoding`, `--config`, `--workers`,
`--verbose`, `--quiet` and `--help`. `python -m tabalyst` accepts the same
commands.

Details: [Tabalyst Report](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/report/index.md),
[JSON and JSONL](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/report/json.md),
[Excel](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/report/excel.md),
[CSV batches and options](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/report/csv.md) and the
[`report` command reference](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/reference/cli/report.md).

## Tabalyst Scan

Describe every field of a CSV, JSON, JSONL or Excel file in one JSON document:

```console
tabalyst scan customers.csv
tabalyst scan orders.json --collection "$.customers[]"
tabalyst scan sales.xlsx --collection Orders
```

Scan reads the file once as a stream, with bounded memory, and records for each
field its types, missing values, frequencies, statistics and the result of every
detector (dates, numbers with decimal commas, emails, URLs, phone numbers,
postal codes, currencies, UUIDs, IP addresses and more). It also writes
`customers.scan.html`, a page that shows the scan (`--no-html` skips it).

A second reading gives exact distinct counts, frequencies, histograms,
medians, patterns, correlations and more. `--plan` shows what it would add and
cost without running it, and `--deep` runs it:

```console
tabalyst scan customers.csv --plan
tabalyst scan customers.csv --deep
```

`tabalyst report` decides by itself whether that second reading is worth its
cost, and says what it added. `tabalyst report` also reuses a stored scan
while the source is unchanged.

Details: [Scan CSV and JSON files](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/scan/files.md),
[the second reading](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/scan/deep.md),
[reading exact, estimated and limited results](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/scan/reading-results.md),
[scan storage and cache](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/scan/cache.md) and the
[scan format](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/scan/format.md).

## Tabalyst Inspect

A JSON file can hold several arrays, and an Excel workbook several sheets.
**Tabalyst Inspect** finds which array, sheet or table holds the records and
writes its answer in `<source>-inspect.json` beside the source:

```console
tabalyst inspect orders.json
tabalyst inspect sales.xlsx
```

The `config` section of that file holds the rules that `tabalyst scan` and
`tabalyst report` apply (collection, flatten settings, header row). Inspect is
optional: both commands inspect a source themselves, and stop with exit code
`2` and a list of candidates when the choice is ambiguous. Pass
`--collection` to choose.

Details: [Inspect JSON and JSONL files](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/inspect/json.md),
[Inspect Excel workbooks](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/inspect/excel.md) and the
[Inspect format](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/inspect/format.md).

## Tabalyst Sample

Create a smaller CSV without modifying the source:

```console
tabalyst sample customers.csv --sample-method random --rows 1000 --seed 42
tabalyst sample customers.csv --smart --rows 1000
```

Methods are `first`, `last`, `random`, `stratified` and `smart`. A smart sample
keeps the diversity of the file (rare values, extremes, formats, odd cases)
instead of its proportions, and writes a report of what it covers, so never
estimate the population from it. Sampling reads records as a stream.

Details: [Tabalyst Sample](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/sample/index.md).

## Tabalyst Generate

Generate synthetic CSV data from a packaged example (`crm`, `insurance` or
`computer`) or from a Generate package:

```console
tabalyst generate --example crm -o crm-contacts.csv
tabalyst generate --example insurance --rows 3000 -d insurance-output/
tabalyst generate --example insurance --rows 3000 --anomaly-profile dirty_realistic -d insurance-dirty/
```

An anomaly profile writes an altered CSV, a cell change log and a summary
beside the untouched clean CSV.

Details: [Tabalyst Generate](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/generate/index.md),
[`examples/generate/README.md`](examples/generate/README.md) and the
[Computer package contract](docs/dev/generate/computer.md).

## What the report analyzes

- Dataset dimensions, missing cells, duplicates, and quality observations.
- Physical and semantic types with confidence and error rates.
- Numeric, date, string-length, normalization, and value distributions.
- Distinct values, representative examples, date formats, and semantic types
  such as enumerations, email addresses, phone numbers, and postal codes.
- CSV record widths, quoting, encoding, and delimiter configuration.
- A bounded raw-data preview while every record is analyzed.

The report is built on Tabalyst Scan; values of sensitive columns can be masked
or hidden. Ambiguous dates stay
ambiguous; the report shows the evidence of the column without applying it. The
HTML report is self-contained and works without a CDN or network connection.
The JSON profile contains the same canonical analysis result for scripts and
future Tabalyst tools. See
[how to read the report](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/report/read-report.md).

## Python API

The same operations are available without the CLI:

```python
import tabalyst

result = tabalyst.analyze("customers.csv", "customers.html", separator=";")
batch = tabalyst.generate_reports(["*.csv"], output_dir="reports")
sample = tabalyst.sample_csv("customers.csv", method="random", rows=1000, seed=42)
scan = tabalyst.scan("orders.json")
inspection = tabalyst.inspect("orders.json")
```

Existing artifacts are never replaced silently: pass `force=True` when
replacement is intentional. Expected failures derive from
`tabalyst.TabalystError`. See the
[Python API reference](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/reference/python-api/index.md).

## Configuration

Configuration files are strict JSON, loaded only with `--config`:

```json
{
  "scan": {
    "csv": {"delimiter": ";", "encoding": "cp1252"},
    "values": {"null_markers": ["N/A"]}
  }
}
```

Explicit CLI or Python arguments override the configuration file, which
overrides Tabalyst defaults. See the
[configuration reference](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/reference/configuration.md).

## Local-first behavior and current limits

Tabalyst performs analysis locally and adds no telemetry or remote processing.
Generated JSON and HTML may contain source values and should be shared
accordingly.

Reports, samples, and scans read files as a stream, with memory bounded by
configurable limits. An Excel workbook is read by sheet into memory, and a
sheet above 1 GiB of XML is refused. See
[limitations](https://github.com/loribel-labs/tabalyst/blob/main/docs/en/about/limitations.md).

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

- [Documentation site](https://docs.tabalyst.com/)
- [Architecture](https://github.com/loribel-labs/tabalyst/blob/main/docs/dev/architecture.md)
- [Release procedure](https://github.com/loribel-labs/tabalyst/blob/main/RELEASING.md)

Please report defects and feature requests through the
[GitHub issue tracker](https://github.com/loribel-labs/tabalyst/issues).

## For AI assistants

To get help from an AI assistant, paste this prompt into a chat that can read
web pages:

```text
Read the complete Tabalyst documentation at
https://docs.tabalyst.com/llms-full.txt, then help me use Tabalyst well.
Ask me what my data looks like and what I want to learn from it, then suggest
the right commands and options. Base your answers only on that documentation.
```

If the assistant cannot open links, paste the content of the file instead.

The documentation site publishes plain-text versions of its pages:
[llms.txt](https://docs.tabalyst.com/llms.txt) lists every page with a
one-line description, and
[llms-full.txt](https://docs.tabalyst.com/llms-full.txt) holds the whole
documentation in one file. Every page is also available as Markdown by adding
`.md` to its URL, for example
[report.md](https://docs.tabalyst.com/report.md).

## License

Tabalyst is released under the [Mozilla Public License 2.0](LICENSE).

Created by Gregory Borelli. Open source project by Loribel Labs.
