---
title: tabalyst report
description: Every option of tabalyst report and examples for CSV, JSON and Excel files, including how to choose a table with --collection and report every table with --all-collections.
---

```console
tabalyst report INPUT... [OPTIONS]
```

Analyzes CSV, JSON, JSONL or Excel (`.xlsx`, `.xlsm`) files and writes, for each
one, an interactive HTML report and a JSON profile, plus an `executions.json`
history in the same folder. With `--scan`, the inputs are scan documents. The
sources are never modified. See [Tabalyst Report](../../report/index.md) for what
the report contains.

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

| Option | Description |
| --- | --- |
| `INPUT...` | One or more files, scan documents with `--scan`, or non-recursive glob patterns (required) |
| `-o`, `--output PATH` | HTML filename ending in `.html`, for a single input. The profile takes the same name with `.json`. Not with `-d` or `--all-collections` |
| `-d`, `--output-dir PATH` | Folder for the reports, named after their sources. Required by `--all-collections` with several inputs |
| `--collection TEXT` | JSON: the array to analyze, such as `data.items` or `'$.data.items[]'`; `.` is the root array; repeatable. Excel: the sheet or table, such as `Sales`, `Sales.Orders` or `'$["Q1 2026"]'`; once. Not with `--scan` or `--all-collections`. See [Choosing a collection or a table](index.md#collection) |
| `--all-collections` | Report every visible collection of each JSON file or workbook, as `<name>.<collection>.html` and `.json`. Not with `-o`, `--collection` or `--scan` |
| `--delimiter TEXT` | One-character CSV delimiter, instead of the detected one |
| `--encoding TEXT` | CSV text encoding, instead of the detected one |
| `-c`, `--config PATH` | JSON [configuration file](../configuration.md) |
| `--scan` | Build the reports from scan documents written by `tabalyst scan`, without reading the sources again. Not with `--delimiter`, `--encoding`, `--collection`, `--all-collections` or `--workers` |
| `-f`, `--force` | Replace existing report files |
| `--details`, `--no-details` | One standalone HTML page per column (off by default) |
| `-q`, `--quiet` | Suppress success messages; warnings and errors remain |
| `-v`, `--verbose` | Also show the profile and history paths, the encoding and the delimiter |
| `--no-progress` | Disable the progress line |
| `--workers N` | Worker processes that analyze values: `1` for one process. Files of 16 MiB or more use one per spare processor by default. Not with `--scan` |
| `--help` | Show the options and exit |

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

## Exit codes

| Code | When |
| --- | --- |
| `0` | Every report was written |
| `1` | A report could not be analyzed, rendered or written |
| `2` | Invalid options, or a JSON or Excel source whose collection or table must be chosen |
| `4` | A source is missing, unreadable or invalid |

See also [Report Excel workbooks](../../report/excel.md),
[Report JSON files](../../report/json.md) and [Inspect](inspect.md).
