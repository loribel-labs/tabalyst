---
title: "CLI: tabalyst scan"
description: Every option of tabalyst scan and examples for CSV, JSON, JSONL and Excel files, including how to choose a JSON collection or an Excel table with --collection.
---

```console
tabalyst scan INPUT... [OPTIONS]
```

Describes CSV, JSON, JSONL or Excel (`.xlsx`, `.xlsm`) files in a JSON scan
document: every field, its presence, values, statistics and detected meanings.
Without `-o` or `-d`, the scan is stored in Tabalyst's local storage, ready to be
reused by `tabalyst report`; with them, a standalone `<stem>.scan.json` is
written. The sources are never modified. See [Scan CSV and JSON
files](../../scan/files.md) for what a scan analyzes.

## Options

`INPUT...` is required: one or more files or non-recursive glob patterns. The
table at the end of this section shows which options each kind of file uses.

### Options for every format

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | Scan filename ending in `.json`, for a single input. Not with `-d` |
| `-d`, `--output-dir PATH` | Folder for standalone scans named `<stem>.scan.json` |
| `-c`, `--config PATH` | JSON [configuration file](../configuration.md); repeat to merge several, in order |
| `-f`, `--force` | Replace existing scan files |
| `-q`, `--quiet` | Suppress success messages; warnings and errors remain |
| `-v`, `--verbose` | Show the format, encoding, delimiter or table, status, diagnostics and duration |
| `--no-progress` | Disable the progress line |
| `--workers N` | Worker processes that analyze values: `1` for one process. Files of 16 MiB or more use one per spare processor by default |
| `--help` | Show the options and exit |

### Options for CSV files

| Option | Description |
| --- | --- |
| `--delimiter TEXT` | One-character delimiter, instead of the detected one |
| `--encoding TEXT` | Text encoding, instead of the detected one |

### Option for JSON and Excel files

| Option | Description |
| --- | --- |
| `--collection TEXT` | The part of the file to analyze. JSON: an array, such as `data.items` or `'$.data.items[]'`; `.` is the root array; repeatable, one dataset each. Excel: a sheet or table, such as `Costs`, `Sales.Orders` or `'$["Q1 2026"]'`; once. See [Choosing a collection or a table](index.md#collection) |

A JSONL file has one dataset, its lines, so it has no collection to choose.

### Options by format

| Option | CSV | JSON | JSONL | Excel |
| --- | :---: | :---: | :---: | :---: |
| `-o`, `-d`, `-c`, `-f`, `-q`, `-v`, `--no-progress`, `--workers` | yes | yes | yes | yes |
| `--delimiter`, `--encoding` | yes | - | - | - |
| `--collection` | - | yes, repeatable | - | yes, once |

An option that a kind of file cannot use is ignored, with a warning, and the
scan is still made: `scan sales.xlsx --delimiter ";"` prints
`Warning [sales.xlsx]: --delimiter is ignored: sales.xlsx is not a CSV file.`

## Examples

### CSV and JSON files

```console
tabalyst scan customers.csv
tabalyst scan data/*.csv -d scans
tabalyst scan customers.csv -o scans/customers-2026.scan.json --force
tabalyst scan orders.json
```

### Choosing a collection

```console
tabalyst scan orders.json --collection customers
tabalyst scan orders.json --collection customers --collection products
```

When several arrays are equally plausible, `scan` stops with exit code `2` and
offers one command per array:

```text
Choose the collection to analyze:
  tabalyst scan shop.json --collection customers
  tabalyst scan shop.json --collection orders
```

### Excel workbooks

```console
tabalyst scan sales.xlsx
tabalyst scan shop.xlsx --collection Costs
tabalyst scan shop.xlsx --collection '$["Sales Q1"]' -d scans
```

A scan analyzes one table of a workbook. When several tables are equally
plausible, `scan` offers the same choices as `report`:

```text
Choose the table to analyze:
  tabalyst scan shop.xlsx --collection Costs
  tabalyst scan shop.xlsx --collection '$["Sales Q1"]'
```

To report every table of a workbook, use
[`tabalyst report --all-collections`](report.md).

### Reuse in a report

```console
tabalyst scan data/*.csv -d scans
tabalyst report scans/*.scan.json --scan -d reports
```

## Exit codes

| Code | When |
| --- | --- |
| `0` | Every scan was written |
| `1` | A scan could not be analyzed or written |
| `2` | Invalid options, or a JSON or Excel source whose collection or table must be chosen |
| `4` | A source is missing, unreadable or invalid |
