# Tabalyst

**Open-source Python toolkit for data profiling and data quality analysis.**

*Tools for unfamiliar data.*

Tabalyst helps you understand CSV, Excel, JSON and JSONL datasets with minimal
configuration. Detect missing values, duplicates, mixed types, data formats and
quality issues. Generate interactive HTML reports and structured JSON profiles,
entirely on your computer.

**Simple. Clear. Smart.**

## Quick start

Tabalyst supports Python 3.11, 3.12, 3.13, and 3.14.

```console
pip install --upgrade tabalyst
tabalyst report insurance-customers.csv
```

Save [`insurance-customers.csv`](https://github.com/loribel-labs/tabalyst/blob/main/examples/datasets/insurance-customers.csv),
a synthetic example, in your working folder, or use your own file. Explore the
interactive HTML report or use the generated JSON profile in your own
workflows. The same `pip` command installs Tabalyst or updates it.

Tabalyst is in beta. Commands and interfaces may change between releases.
Update before each new test.

## Tabalyst Websites

- [tabalyst.com](https://tabalyst.com/): the official website, with an interactive demo.
- [docs.tabalyst.com](https://docs.tabalyst.com/): the documentation, for people and for AI assistants.
- [Interactive report](https://tabalyst.com/examples/report.html): a real Tabalyst report you can explore in your browser.

## What can Tabalyst do?

| Tool | Purpose |
| --- | --- |
| [**Tabalyst Report**](https://docs.tabalyst.com/report/) | Generate interactive HTML profiling reports and JSON profiles |
| [**Tabalyst Scan**](https://docs.tabalyst.com/scan/) | Profile datasets and generate JSON and HTML scan summaries |
| [**Tabalyst Inspect**](https://docs.tabalyst.com/inspect/) | Discover and configure JSON collections and Excel tables |
| [**Tabalyst Sample**](https://docs.tabalyst.com/sample/) | Create random, stratified and smart CSV samples |
| [**Tabalyst Generate**](https://docs.tabalyst.com/generate/) | Generate synthetic CSV datasets for testing and demos |

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

Details: [Tabalyst Report](https://docs.tabalyst.com/report/),
[JSON and JSONL](https://docs.tabalyst.com/report/json/),
[Excel](https://docs.tabalyst.com/report/excel/),
[CSV batches and options](https://docs.tabalyst.com/report/csv/) and the
[`report` command reference](https://docs.tabalyst.com/reference/cli/report/).

### What the report analyzes

- Dataset dimensions, missing cells, duplicates, and quality observations.
- A family and a type for each column (identifier, text, date, boolean...),
  with the evidence behind them, and the technical type with its error rates.
- A summary table with one row per column: its type, a sentence about its
  values, the missing share, its Errors and Issues with a preview of each, and
  its details; above it, the Column quality and Signals cards.
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
[how to read the report](https://docs.tabalyst.com/report/read-report/).

## Tabalyst Scan

Describe every field of a CSV, JSON, JSONL or Excel file in one JSON document:

```console
tabalyst scan customers.csv
tabalyst scan orders.json --collection "$.customers[]"
tabalyst scan sales.xlsx --collection Orders
```

Scan reads a text file once as a stream, with bounded memory. An Excel sheet is
loaded into memory. It records for each
field its types, missing values, frequencies, statistics and the result of every
detector (dates, numbers with decimal commas, emails, URLs, phone numbers,
postal codes, currencies, UUIDs, IP addresses and more). It also writes
`customers.scan.html`, a page that shows the scan (`--no-html` skips it).

A second reading can provide exact distinct counts, frequencies, histograms,
medians, patterns, correlations and more, within the limits of your data. `--plan` shows what it would add and
cost without running it, and `--deep` runs it:

```console
tabalyst scan customers.csv --plan
tabalyst scan customers.csv --deep
```

`tabalyst report` decides by itself whether that second reading is worth its
cost, and says what it added. `tabalyst report` also reuses a stored scan
while the source is unchanged.

Details: [Scan CSV and JSON files](https://docs.tabalyst.com/scan/files/),
[the second reading](https://docs.tabalyst.com/scan/deep/),
[reading exact, estimated and limited results](https://docs.tabalyst.com/scan/reading-results/),
[scan storage and cache](https://docs.tabalyst.com/scan/cache/) and the
[scan format](https://docs.tabalyst.com/scan/format/).

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

Details: [Inspect JSON and JSONL files](https://docs.tabalyst.com/inspect/json/),
[Inspect Excel workbooks](https://docs.tabalyst.com/inspect/excel/) and the
[Inspect format](https://docs.tabalyst.com/inspect/format/).

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

Details: [Tabalyst Sample](https://docs.tabalyst.com/sample/).

## Tabalyst Generate

Generate synthetic CSV data from a packaged example (`crm`, `insurance` or
`computer`) or from a Generate package:

```console
tabalyst generate --example crm -o crm-contacts.csv
tabalyst generate --example insurance --rows 3000 -d insurance-output/
tabalyst generate --example computer --rows 10000 -d computer-output/
tabalyst generate --example insurance --rows 3000 --anomaly-profile dirty_realistic -d insurance-dirty/
```

An anomaly profile writes an altered CSV, a cell change log and a summary
beside the untouched clean CSV.

Details: [Tabalyst Generate](https://docs.tabalyst.com/generate/),
[`examples/generate/README.md`](examples/generate/README.md) and the
[Computer package contract](docs/dev/generate/computer.md).

## Python API

The same operations are available without the CLI:

```python
import tabalyst

result = tabalyst.analyze("customers.csv", "customers.html")
batch = tabalyst.generate_reports(["*.csv"], output_dir="reports")
sample = tabalyst.sample_csv("customers.csv", method="random", rows=1000, seed=42)
scan = tabalyst.scan("orders.json")
inspection = tabalyst.inspect("orders.json")
```

Existing artifacts are never replaced silently: pass `force=True` when
replacement is intentional. Expected failures derive from
`tabalyst.TabalystError`. See the
[Python API reference](https://docs.tabalyst.com/reference/python-api/).

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
[configuration reference](https://docs.tabalyst.com/reference/configuration/).

## Local-first behavior and current limits

Tabalyst performs analysis locally and adds no telemetry or remote processing.
Generated JSON and HTML may contain source values and should be shared
accordingly.

Reports, samples, and scans read CSV, JSON and JSONL files as a stream, with
memory bounded by configurable limits. An Excel workbook is read by sheet into
memory, and a sheet above 1 GiB of XML is refused. See
[limitations](https://docs.tabalyst.com/about/limitations/).

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
