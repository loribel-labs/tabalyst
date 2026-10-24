---
title: "CLI: tabalyst report"
description: Every option of tabalyst report and examples for CSV, JSON and Excel files, including the second pass it adds by itself, --deep and --yes, how to choose a table with --collection and report every table with --all-collections.
---

```console
tabalyst report INPUT... [OPTIONS]
```

Analyzes CSV, JSON, JSONL or Excel (`.xlsx`, `.xlsm`) files and writes, for each
one, an interactive HTML report and a JSON profile, plus an `executions.json`
history in the same folder. With `--scan`, the inputs are scan documents. The
sources are never modified. See [Tabalyst Report](../../report/index.md) for what
the report contains.

The report also adds, by itself, the [exact analyses of a second
pass](../../scan/deep.md) that are useful and cheap: patterns counted on every
value, dates by period, exact distinct counts and medians. It says so after the
report path. See [Second pass](#second-pass).

## Output files

| Source | Report | Profile |
| --- | --- | --- |
| CSV: `data.csv` | `data.html` | `data.json` |
| JSON, JSONL, NDJSON or Excel: `data.json`, `data.xlsx` | `data.report.html` | `data.report.json` |
| With `--all-collections`: `shop.xlsx` | `shop.<collection>.html` | `shop.<collection>.json` |
| With `-o report.html` | `report.html` | `report.json` |

The files go beside the source, or in the folder of `-d`. `.report` keeps the
profile of a JSON or Excel file from replacing a source with the same stem. With
`--details`, the column pages are written in a folder named like the report, for
example `data/`.

## Options

`INPUT...` is required: one or more files, scan documents with `--scan`, or
non-recursive glob patterns. The table at the end of this section shows which
options each kind of file uses.

### Options for every format

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | HTML filename ending in `.html`, for a single input. The profile takes the same name with `.json`. Not with `-d` or `--all-collections` |
| `-d`, `--output-dir PATH` | Folder for the reports, named after their sources. Required by `--all-collections` with several inputs |
| `-c`, `--config PATH` | JSON [configuration file](../configuration.md) |
| `-f`, `--force` | Replace existing report files |
| `--details`, `--no-details` | One standalone HTML page per column (off by default) |
| `-q`, `--quiet` | Suppress success messages; warnings and errors remain |
| `-v`, `--verbose` | Also show the profile and history paths, and the encoding and delimiter of a CSV file |
| `--no-progress` | Disable the progress line |
| `--workers N` | Worker processes that analyze values: `1` for one process. Files of 16 MiB or more use one per spare processor by default. Not with `--scan` |
| `--deep` | Force the [second pass](#second-pass): every applicable exact analysis, whatever the planner thinks of its cost. Asks first when it is costly |
| `-y`, `--yes` | Start a costly forced second pass without asking. Outside a terminal, a costly forced second pass needs it |
| `--dedup-report PATH` | A [Dedup](../../dedup/index.md) report (`<name>.dedup.json`), or the folder holding the one of each source. When it matches the scan, it proves how many rows are exact copies, so that the report can tell the repetitions of an identifier that copies explain from the others (`identifier_uniqueness` in the [JSON profile](../../report/profile-changelog.md)). CSV sources only; a file serves a single source. Without it, the report beside each source (or beside the scan document with `--scan`) is tried. A path that does not exist, or a source that is not a CSV file, is an error |
| `--help` | Show the options and exit |

### Options for CSV files

| Option | Description |
| --- | --- |
| `--delimiter TEXT` | One-character delimiter, instead of the detected one |
| `--encoding TEXT` | Text encoding, instead of the detected one |

### Options for JSON and Excel files

| Option | Description |
| --- | --- |
| `--collection TEXT` | The part of the file to analyze. JSON: an array, such as `data.items` or `'$.data.items[]'`; `.` is the root array; repeatable. Excel: a sheet or table, such as `Sales`, `Sales.Orders` or `'$["Q1 2026"]'`; once. See [Choosing a collection or a table](index.md#collection). Not with `--scan` or `--all-collections` |
| `--all-collections` | Report every visible collection of each file, as `<name>.<collection>.html` and `.json`. Not with `-o`, `--collection` or `--scan` |

A JSONL file has one dataset, its lines, so it has no collection to choose.

### Option for scan documents

| Option | Description |
| --- | --- |
| `--scan` | Build the reports from scan documents written by `tabalyst scan`, without reading the sources again, not even for the second pass unless `--deep` is given. Not with `--delimiter`, `--encoding`, `--collection`, `--all-collections` or `--workers` |

### Options by format

| Option | CSV | JSON | JSONL | Excel |
| --- | :---: | :---: | :---: | :---: |
| `-o`, `-d`, `-c`, `-f`, `--details`, `-q`, `-v`, `--no-progress`, `--workers`, `--deep`, `--yes` | yes | yes | yes | yes |
| `--delimiter`, `--encoding` | yes | - | - | - |
| `--collection` | - | yes, repeatable | - | yes, once |
| `--all-collections` | - | yes | - | yes |
| `--scan` (the inputs are scan documents) | yes | yes | yes | yes |

An option that a kind of file cannot use is ignored, with a warning, and the
report is still written: `report sales.xlsx --delimiter ";"` prints
`Warning [sales.xlsx]: --delimiter is ignored: sales.xlsx is not a CSV file.`

## Examples

### CSV files

```console
tabalyst report customers.csv
tabalyst report data/*.csv -d reports
tabalyst report customers.csv -o out/customers-2026.html --details --force
tabalyst report semicolon.csv --delimiter ";" --encoding cp1252
```

### Excel workbook with one table

```console
tabalyst report sales.xlsx
```

When Tabalyst can tell which table to analyze, a workbook needs nothing else:
only one table is eligible, or the largest has at least 10 times the rows of the
next one. This writes `sales.report.html`, `sales.report.json` and
`executions.json`.

### Excel workbook with several tables

When several tables are equally plausible, `report` analyzes nothing, exits with
code `2` and offers the choices:

```console
tabalyst report shop.xlsx
```

```text
Error [shop.xlsx]: 2 tables of shop.xlsx are equally plausible. Nothing was analyzed.
Candidates:
  $.Costs (40 rows)
  $["Sales Q1"] (50 rows)
  $.Notes (0 rows), empty
Pass --collection with a sheet or table path such as '$.Sheet', or run `tabalyst inspect shop.xlsx` and set config.structure.dataset_path in the file it writes.
Choose the table to analyze:
  tabalyst report shop.xlsx --collection Costs
  tabalyst report shop.xlsx --collection '$["Sales Q1"]'
Or report every table: tabalyst report shop.xlsx --all-collections
```

Copy the line you want and run it:

```console
tabalyst report shop.xlsx --collection Costs
tabalyst report shop.xlsx --collection '$["Sales Q1"]'
tabalyst report shop.xlsx --collection Costs -d reports
```

The first one writes `shop.report.html` and `shop.report.json`. A named table of a
sheet is chosen with `--collection Sales.Orders`.

### Every table of a workbook

```console
tabalyst report shop.xlsx --all-collections
```

```text
Report: shop.xlsx -> D:\work\shop.costs.html
Report: shop.xlsx -> D:\work\shop.sales-q1.html
2 succeeded, 0 failed
```

Each eligible table gets its own pair of files, named
`<file>.<collection-slug>`: `shop.costs.html`, `shop.costs.json`,
`shop.sales-q1.html` and `shop.sales-q1.json`. The slug is the sheet (and table)
name in lower case, without accents, with every other character replaced by a
hyphen, and a number is added when two names give the same slug. Only the visible
sheets that [Inspect](inspect.md) finds eligible are reported: empty sheets and
sheets without a header are left out, and a hidden sheet is left out with a
warning (choose it with `--collection`).

A single file can go to a folder, and `-d` is required for several files:

```console
tabalyst report shop.xlsx --all-collections -d reports
tabalyst report shop.xlsx orders.xlsx --all-collections -d reports
tabalyst report "exports/*.xlsx" --all-collections -d reports --force
```

A source with a single dataset, such as a CSV file, keeps its usual name in the
same command. A workbook that has nothing to report fails alone, with exit code
`2`, and does not stop the others.

### JSON files

```console
tabalyst report orders.json
tabalyst report shop.json --collection orders
tabalyst report shop.json --all-collections -d reports
```

For a JSON file with a `customers` and an `orders` array, the last command writes
`shop.customers.html` and `shop.orders.html` with their `.json` profiles.

### Reusing scans

```console
tabalyst scan data/*.csv -d scans
tabalyst report scans/*.scan.json --scan -d reports
```

### Configuration

```console
tabalyst report customers.csv --config settings.json
```

## Second pass

The scan counts and samples everything in one pass. A second pass reads the file
again for what a sample cannot give: the number of occurrences each inferred
pattern reads in the whole file, the dates counted per day, month or year, the
exact number of distinct values and the exact median of a column the scan
stopped counting. `tabalyst report` decides by itself:

```console
tabalyst report customers.csv
```

```text
Analyzed 3,000 rows and 34 columns.
Report: D:\work\customers.html
Second pass (automatic): 36 analyses, 36 computed, 0 reused.
```

The planner picks an analysis only when it is useful and cheap, under budgets of
memory and cells that do not depend on your machine, so the same file gives the
same report anywhere. It never asks a question. The report says what was added,
what the scan already answered and what was left out, in its **Second pass**
section.

| What you write | What happens |
| --- | --- |
| `tabalyst report data.csv` | The planner decides |
| `tabalyst report data.csv --deep` | Every applicable analysis the memory budget holds. Asks first when the estimate may reach two minutes or goes beyond what the planner chooses by itself; `--yes` skips the question; outside a terminal it stops with exit code `3` without `--yes`. With several files it asks once, with the total |
| `tabalyst report data.csv -c off.json`, with `{"deep": {"mode": "off"}}` | No second pass: for a script that must read each file once. The report says the second pass is off |
| `{"deep": {"mode": "force"}}` | The same as `--deep` on every run |
| `tabalyst report scans/data.scan.json --scan` | The source is not read. The analyses that the scan and the stored `data.deep.json` answer are in the report; the others are listed as skipped, with the reason |
| `tabalyst report scans/data.scan.json --scan --deep` | The source next to the scan document is read. If it is not there the command fails (exit code `4`) and writes nothing |

The results are stored beside the scan, in `deep.json`, so that a second report of
the same file, or one that changes only the presentation, reads nothing again. If
the file changes while an automatic second pass runs, the report is still written
without it, with a warning; a forced second pass fails instead. See [Add
histograms and exact medians with a second pass](../../scan/deep.md).

## Exit codes

| Code | When |
| --- | --- |
| `0` | Every report was written |
| `1` | A report could not be analyzed, rendered or written |
| `2` | Invalid options, or a JSON or Excel source whose collection or table must be chosen |
| `3` | A costly forced second pass needed a confirmation and was not given: no terminal and no `--yes`, or the answer was no. Nothing was started |
| `4` | A source is missing, unreadable or invalid, or changed during a forced second pass |

See also [Report Excel workbooks](../../report/excel.md),
[Report JSON files](../../report/json.md) and [Inspect](inspect.md).
