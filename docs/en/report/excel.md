---
title: Report Excel workbooks
description: Turn an Excel workbook (.xlsx, .xlsm) into an interactive HTML report and a JSON profile with tabalyst report, one table per report, chosen automatically or with --collection.
---

`tabalyst report` reads Excel workbooks as well as CSV and JSON files:

```console
tabalyst report sales.xlsx
```

This creates `sales.report.html` (the report), `sales.report.json` (the profile)
and `executions.json` beside `sales.xlsx`. The `.report` part keeps the profile
from replacing a source with the same stem. `-o` and `-d` work as for CSV files,
and `.xlsx` and `.xlsm` files are accepted. The workbook is never modified.

## Which table is analyzed

A report analyzes **one table**: a sheet, or a named Excel table inside a sheet.
When the workbook has one sheet with one table, the command needs nothing else.
Tabalyst finds the header of the sheet, even under a title or blank rows, and
reports the rows under it.

When several tables are plausible, the command stops with exit code `2` before
analyzing anything and lists them, as for JSON files. Choose one with
`--collection`, once, or set it in the Inspect file:

```console
tabalyst report shop.xlsx --collection Costs
tabalyst report shop.xlsx --collection '$.Sales.Orders'
```

`Costs` is a sheet, `$.Sales.Orders` the named table `Orders` of the sheet
`Sales`. A sheet name that is not a plain identifier is quoted:
`'$["Q1 2026"]'`. The command that stops lists one ready-to-run command per
table, so you only copy the one you want and run it again:

```text
Choose the table to analyze:
  tabalyst report shop.xlsx --collection Costs
  tabalyst report shop.xlsx --collection '$["Sales Q1"]'
Or report every table: tabalyst report shop.xlsx --all-collections
```

`tabalyst inspect shop.xlsx` prints the same lines. [Inspect Excel
workbooks](../inspect/excel.md) explains how the table is chosen and how to set
the header row when the detection is wrong.

## Every table of a workbook

To report all the tables in one command, add `--all-collections`:

```console
tabalyst report shop.xlsx --all-collections
tabalyst report shop.xlsx --all-collections -d reports
```

Each table gets its own pair of files, named `<file>.<collection-slug>`:
`shop.costs.html` and `shop.costs.json` for the sheet `Costs`, and
`shop.sales-q1.html` and `shop.sales-q1.json` for `Sales Q1` (lower case, without
accents, every other character a hyphen). A named table of a sheet gives
`shop.sales-orders.html`. Empty sheets, sheets without a header and hidden sheets
are left out, the last with a warning: report one with `--collection`.

`-d` chooses the folder and is optional for one workbook, which writes beside the
source; with several files it is required. `--all-collections` cannot be used
with `-o`, `--collection` or `--scan`, and existing files stop the command unless
you pass `--force`. See [tabalyst report](../reference/cli/report.md) for every
option.

## Columns

The columns of the report are the columns of the header, named by their header
cell. A repeated or empty header gets a distinct name (`id#1`, `id#2`) and an
`ambiguous_headers` issue. Every filled row under the header is a row of the
report; blank rows are skipped, and an empty cell is a missing value.

Cells keep their Excel type. Numbers are integers or decimals, booleans are
booleans, and dates are read as dates, so the report shows their formats and
ranges. Excel has one number type: a whole number is an integer, even in a column
of decimal amounts. A formula is read as its last calculated value. Merged cells
only hold their value in the top-left cell.

The report is built on [Tabalyst Scan](../scan/files.md), so the detectors, the
masking of sensitive values and every other analysis work as for CSV files. A
report of a workbook has no encoding or delimiter, and its profile `source.format`
is `excel`.

## Limits

One table per report, no recognition of blocks separated by blank rows or of
total rows under the data, and error cells read as empty. The
[known limitations](../about/limitations.md) list them with the size limits.
