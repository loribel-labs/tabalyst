---
title: Tabalyst Report
description: Overview of Tabalyst Report, the tool that turns a CSV, JSON, JSONL or Excel file into an interactive HTML report and a JSON profile, with commands, outputs and options.
---

**Tabalyst Report** analyzes a CSV, JSON, JSONL or Excel file and produces an
interactive, self-contained HTML report and a JSON profile of the same
analysis. It reads the file once, as a stream, on your computer.

```console
tabalyst report customers.csv
```

This creates `customers.html` (the report), `customers.json` (the profile) and
`executions.json` (the run history) beside the source. Your data is never
modified or sent anywhere.

## Commands at a glance

| Use case | Command | Destination |
| --- | --- | --- |
| One file, automatic name | `tabalyst report data.csv` | `data.html` beside the source |
| One file, custom name | `tabalyst report data.csv -o report.html` | The file `report.html` |
| Several files, automatic names | `tabalyst report *.csv` | Beside each source |
| Several files, one directory | `tabalyst report *.csv -d reports/` | The directory `reports/` |
| One JSON file | `tabalyst report data.json` | `data.report.html` beside the source |
| One JSONL file | `tabalyst report events.jsonl` | `events.report.html` beside the source |
| One Excel workbook | `tabalyst report sales.xlsx` | `sales.report.html` beside the source |
| One page per column | `tabalyst report data.csv --details` | The folder `data/` beside the report |
| From a scan document | `tabalyst report --scan data.scan.json` | `data.html` beside the scan |

## What the report shows

- Dataset dimensions, missing cells, duplicates and quality observations.
- Physical and semantic types, with confidence and error rates.
- Numeric, date and string-length analysis, normalization and value
  distributions.
- Distinct values, representative examples, date formats and detected meanings
  such as enumerations, email addresses, phone numbers and postal codes.
- CSV record widths, quoting, encoding and delimiter configuration.
- A bounded raw-data preview, while every record is analyzed.

The report is built on [Tabalyst Scan](../scan/files.md). Values of
sensitive fields, such as email addresses, are masked by default. Ambiguous
dates stay ambiguous: the report shows the evidence without applying it. The
HTML works without a network connection or a CDN.

## Pages

- [Create your first report](getting-started.md): a five-minute
  tutorial on a small CSV file.
- [Report CSV files](csv.md): names, batches, safe behavior and
  options.
- [Report JSON and JSONL files](json.md): JSON and JSONL sources, one
  collection of records per report.
- [Report Excel workbooks](excel.md): `.xlsx` and `.xlsm` sources, one table
  per report.
- [JSON profile](json-profile.md): the structure of the generated `.json` file,
  and its [changelog](profile-changelog.md).
- [Execution history](../reference/history.md): the `executions.json`
  file.
- [Configuration](../reference/configuration.md): adapt the analysis and the
  presentation.
