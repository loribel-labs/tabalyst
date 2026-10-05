---
title: Report CSV files
description: Create HTML reports and JSON profiles from one or many CSV files with tabalyst report, choose output names, use column pages and understand the batch safety rules.
---

`tabalyst report` analyzes a CSV file and writes an HTML report and a JSON
profile. The simplest command keeps the source name:

```console
tabalyst report customers.csv
```

```text
customers.csv
customers.html
customers.json
executions.json
```

Use `-o` to choose a different HTML filename for one source. The profile takes
the same name with `.json`:

```console
tabalyst report customers.csv -o customer-analysis.html
```

## Report several files

```console
tabalyst report *.csv
```

Each report is created beside its source and keeps the source stem:
`customers.csv` gives `customers.html`, `orders.csv` gives `orders.html`.

Use `-d` to place every report in one directory:

```console
tabalyst report *.csv -d reports/
```

```text
reports/
├── customers.html
├── customers.json
├── orders.html
├── orders.json
└── executions.json
```

`-o` names one output file and accepts only one input. `-d` names an output
directory and accepts one or many inputs. `tabalyst report *.csv -o report.html`
is rejected before any file is processed. Quotes are only needed when a path
contains spaces. On Windows, Tabalyst expands wildcards itself.

## One page per column

```console
tabalyst report customers.csv --details
```

The **Columns** table of the report then links to one self-contained HTML page
per column, with its values, counts and detected formats. The pages are in a
subfolder named after the HTML file without `.html` (`customers/`, or `report/`
for `-o report.html`), named `col-01-` followed by a shortened slug of the
column name, in source order. Details are off by default. With `--force`,
`--no-details` removes the column pages generated earlier and keeps other files
of the folder.

## Safe batch behavior

Before processing begins, Tabalyst resolves every input and every planned HTML
and JSON output. It stops the whole batch when two outputs collide or when an
output already exists. With `--details`, each column page is checked after its
profile is built and before that report's files are written. Replace existing
reports only on purpose:

```console
tabalyst report *.csv -d reports/ --force
```

If one CSV is malformed, Tabalyst reports the error, continues with the other
files and returns a non-zero exit code at the end.

Interactive terminals show file and phase progress on standard error:

```text
[2/8] orders.csv - Analyzing
```

Progress is turned off outside a terminal, and by `--no-progress` or
`--quiet`.

## Useful options

```console
tabalyst report data.csv --delimiter ";"
tabalyst report data.csv --encoding cp1252
tabalyst report data.csv --config tabalyst.json
tabalyst report data.csv --verbose
tabalyst report data.csv --workers 4
```

Files of 16 MiB or more are analyzed by several worker processes with the same
result; `--workers 1` keeps one process. All options are in the
[command line reference](../reference/cli/report.md), and the
analysis settings in the [configuration reference](../reference/configuration.md).

## Reuse a scan

`tabalyst report` reuses the stored scan of a source when its content and the
requested scan settings are current, and creates or replaces it otherwise. To
build a report from a scan document without reading the source again:

```console
tabalyst report --scan customers.scan.json
```

Tabalyst refuses a scan whose source changed since it was written. See
[Scan CSV and JSON files](../scan/files.md).
