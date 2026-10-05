---
title: "Python API: reports"
description: The Python functions that write or build Tabalyst reports - analyze, generate_reports, analyze_csv, analyze_scan and render_report - with their parameters, return values and examples for CSV, JSON and Excel files.
---

Reports are written by `tabalyst.analyze()` for one CSV file and by
`tabalyst.generate_reports()` for any number of CSV, JSON, JSONL or Excel files.
`analyze_csv()`, `analyze_scan()` and `render_report()` build a profile or its
HTML without writing files. The command is
[`tabalyst report`](../cli/report.md).

```python
import tabalyst

result = tabalyst.analyze("customers.csv", "customers.html", separator=";")
batch = tabalyst.generate_reports(["data/*.csv"], output_dir="reports")
batch = tabalyst.generate_reports(["shop.xlsx"], collections=["$.Costs"])
batch = tabalyst.generate_reports(["shop.xlsx"], all_collections=True)
batch = tabalyst.generate_reports(["scans/*.scan.json"], from_scan=True)
```

## tabalyst.generate_reports()

Plans and writes the reports of several sources: an HTML report and a JSON
profile for each, with an `executions.json` history in the same folder.

```python
tabalyst.generate_reports(
    input_specs,
    *,
    output=None,
    output_dir=None,
    separator=None,
    encoding=None,
    collections=None,
    config_path=None,
    force=False,
    details=False,
    on_progress=None,
    from_scan=False,
    workers=None,
    all_collections=False,
)
```

Returns a [batch result](index.md#batch-functions) whose successes hold the
profile as a dictionary in `result`. A successful job also has `warnings`.

- `input_specs`: files or non-recursive glob patterns, or scan documents with
  `from_scan=True`.
- `output`: HTML filename for a single source; the profile takes the same name
  with `.json`. Not with `output_dir` or `all_collections`.
- `output_dir`: folder for the reports, named after their sources. Required with
  `all_collections` when there are several sources.
- `separator`, `encoding`: CSV delimiter and text encoding, instead of the
  detected ones. Not with `from_scan`.
- `collections`: what to analyze in a JSON file or workbook, as absolute paths:
  arrays such as `["$.customers[]"]` for JSON, one table such as `["$.Sales"]` or
  `["$.Sales.Orders"]` for Excel. It outranks the Inspect file and the
  configuration. Not with `from_scan` or `all_collections`.
- `all_collections`: `True` reports every visible collection of each JSON file
  or workbook, one report per collection, named
  `<stem>.<collection-slug>.html`. See
  [Report Excel workbooks](../../report/excel.md#every-table-of-a-workbook).
- `config_path`, `force`, `on_progress`: see the [conventions](index.md#conventions).
- `details`: also write one HTML page per column.
- `from_scan`: the sources are scan documents written by `tabalyst scan`; the
  reports are built without reading the sources again. Not with `separator`,
  `encoding`, `collections`, `all_collections` or `workers`.
- `workers`: number of analysis processes; `1` for one. Files of 16 MiB or more
  use one per spare processor by default.

An option that a source cannot use is ignored and listed in `batch.plan.warnings`:

```python
batch = tabalyst.generate_reports(["sales.xlsx"], separator=";")
for source, notice in batch.plan.warnings:
    print(source, notice)
# sales.xlsx --delimiter is ignored: sales.xlsx is not a CSV file.
```

## tabalyst.analyze()

Analyzes one CSV file, writes its report, its sibling JSON profile and the
execution history, and returns the profile as a dictionary.

```python
tabalyst.analyze(
    csv_path,
    report_path,
    separator=None,
    encoding=None,
    config_path=None,
    force=False,
    details=False,
)
```

- `csv_path`: the CSV file.
- `report_path`: HTML filename ending in `.html`; the profile is written beside
  it with the extension `.json`.
- `separator`, `encoding`: override the delimiter and the text encoding.
- `config_path`, `force`: see the [conventions](index.md#conventions).
- `details`: also write one HTML page per column.

Raises the error of the analysis, such as an existing output without `force`.

## tabalyst.analyze_csv()

Scans a file and builds its profile without writing anything.

```python
tabalyst.analyze_csv(path, config=None, on_progress=None, workers=None)
```

Returns a `ReportProfile` model. `config` is a `tabalyst.ReportConfig`; its
`scan` setting is a `tabalyst.ScanConfig`.

## tabalyst.analyze_scan()

Builds the profile of a scan document written by `tabalyst scan`, without
reading its source again.

```python
tabalyst.analyze_scan(scan_path, config_path=None, on_progress=None)
```

Returns a `ReportProfile`. The presentation settings come from `config_path`.
The `scan` settings given there must be those of the document, and a source found
beside the document must not have changed since the scan; both raise a
`ConfigurationError` otherwise.

## tabalyst.render_report()

Renders the HTML of a report.

```python
tabalyst.render_report(profile, *, column_links=None)
```

Returns the HTML as a string. `profile` is a `ReportProfile`, such as the one
`analyze_csv()` returns. `column_links` maps `(dataset id, column id)` to the URL
of a column page.

```python
profile = tabalyst.analyze_csv("customers.csv")
html = tabalyst.render_report(profile)
```
