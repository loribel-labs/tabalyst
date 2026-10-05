---
title: Scan CSV and JSON files
description: Describe every field of a CSV, JSON, JSONL or Excel file in a complete JSON scan document with tabalyst scan, in one streaming pass.
---

Use `tabalyst scan` to describe a CSV, JSON, JSONL or Excel file in a JSON document: every
field, its presence, values, statistics, formats and detected meanings, such
as email addresses, dates or amounts.

```console
tabalyst scan customers.csv
```

Without `-o` or `-d`, whatever the format, this stores a reusable `scan.json` in
Tabalyst's local storage directory, under `workspaces/local/scans/` in a
directory keyed by the source path. It does not build a DuckDB database. Set `TABALYST_HOME` to choose the
storage root. The source file is never modified. **Tabalyst Scan** reads the whole file in one streaming pass,
so memory depends on the configured limits, not on the number of records. The
structure of the result is described in the
[scan format reference](format.md).

## Scan JSON files

Files ending in `.json` are read as JSON, files ending in `.jsonl` or `.ndjson`
(in any letter case) as JSONL, files ending in `.xlsx` or `.xlsm` as Excel
workbooks, and every other file as CSV.

```console
tabalyst scan orders.json
```

A scan analyzes one **collection** of records: a top-level array, or an array
inside a top-level object, such as `customers` in `{"customers": [...]}`.
Arrays inside records, such as the `orders` of each customer, stay fields of
their records. Tabalyst finds the collection with
[Inspect](../inspect/json.md), which runs by itself when the source has no
Inspect file, and keeps the choice in the Inspect file beside the source when
you ran `tabalyst inspect`. When several arrays are equally plausible, the scan
stops with exit code `2` and lists them; choose one in the Inspect file, or
pass `--collection`:

```console
tabalyst scan orders.json --collection "$.customers[]"
```

Repeat `--collection` to analyze several collections in one scan, one dataset
each:

```console
tabalyst scan orders.json --collection customers --collection products
```

A collection path starts with `$`, the document root, and ends with `[]`, the
elements of an array. The short form lists the keys that lead to the array:
`customers` is `$.customers[]` and `data.items` is `$.data.items[]`; `.` is the
root array, `$[]`, and a key made of digits, such as `groups.121`, is accepted
as it is. Nested fields are written with dots, such as
`orders[].amount`. `--collection` outranks the Inspect file. A collection set in
an Inspect file that no longer exists in the source stops the scan with exit
code `2`; `--collection` or a `--config` collection that is not found is a
warning, with an empty dataset.

A JSONL source has one dataset, `$[]`: its records are the lines. An invalid
line, or one that is not an object, is excluded and counted under the default
`tolerant` policy, and the scan is `partial`.

## Scan Excel workbooks

```console
tabalyst scan sales.xlsx
tabalyst scan shop.xlsx --collection Costs
```

A scan analyzes **one table** of a workbook: a sheet, or a named Excel table. The
table is chosen as for JSON collections, with [Inspect](../inspect/excel.md),
which runs by itself when the source has no Inspect file, or with
`--collection`, once (`Costs`, `'$.Costs'` or `'$.Sales.Orders'`). When several
tables are equally plausible, the scan stops with exit code `2` and lists them.
The header row is detected, and `excel.header_row` of the
[configuration](../reference/configuration.md#scan-settings) or the Inspect file
sets it. The scan has one dataset, `rows`, of kind `table`, whose fields are the
columns of the header. Cells keep their Excel type, and dates are read as ISO
text that the date detector recognizes. The [scan format](format.md#excel-sources)
records the table read.

## Choose output locations

Use `-o` to export a standalone scan document with a complete output filename
when scanning one source. The name
must end in `.json`:

```console
tabalyst scan customers.csv -o scans/customers.json
```

Wildcards are resolved by Tabalyst, including on shells that do not expand
them. Use `-d` to export the scans of one or more sources in a directory:

```console
tabalyst scan data/*.csv data/*.json -d scans/
```

The outputs are named `customers.scan.json`, `orders.scan.json`, and so on.
`-o` accepts only one resolved input; `-o` and `-d` cannot be combined.
Recursive `**` patterns are not supported.

## Safe batch behavior

Before writing standalone scans, Tabalyst resolves every input and output and
rejects the whole batch when:

- two sources map to the same output, such as `data.csv` and `data.json`;
- an output would replace an input or a configuration file;
- an output already exists and `--force` is not given.

Each result is written to a temporary file in the target directory, then moved
into place: an interrupted scan never leaves a partial result. When one source
fails, for example with invalid JSON, Tabalyst reports the error, continues
with the other sources and returns a non-zero exit code at the end.

A pattern such as `data/*.json` also matches earlier standalone results such as
`data/orders.scan.json`. Write scans to another directory with `-d` to keep
them apart from the sources. Patterns skip Inspect files, named
`*-inspect.json`, and an Inspect file given as an input is refused. Wildcards are resolved by
Tabalyst, including on Windows, so the same pattern skips them there too.

## Configure the scan

Scan settings live in the `scan` section of a JSON
[configuration file](../reference/configuration.md#scan-settings):

```json
{
  "scan": {
    "values": {"null_markers": ["N/A", "NULL"]},
    "errors": {"policy": "tolerant"},
    "exposure": {"sensitive_values": "hide"}
  }
}
```

```console
tabalyst scan customers.csv --config tabalyst.json
```

Repeat `--config` to combine several files: later files override earlier ones.
`--delimiter`, `--encoding` and `--collection` override every file. Unknown
settings are errors, so a misspelled name never passes silently.

The CSV delimiter is a comma and the encoding accepts UTF-8 with or without a
byte order mark by default:

```console
tabalyst scan data.csv --delimiter ";" --encoding cp1252
```

## Errors and partial scans

By default, a CSV record with the wrong number of fields, or a JSON object with
a duplicate key, stops the scan of that file with an error. A JSONL file is
tolerant by default: a line that is not valid JSON or not an object is excluded.
With `"errors": {"policy": "tolerant"}`, such records are excluded and counted,
and the scan finishes with status `partial`; `"strict"` stops at the first one.
The command then succeeds and prints a warning:

```text
Warning [data.csv]: partial scan, 2 records excluded (width_mismatch: 2).
```

Exit codes: `0` for success, including partial scans; `2` for configuration
errors; `4` for unreadable or invalid inputs; `1` for other failures, such as
an existing output without `--force`.

## Sensitive values

Fields holding email addresses, phone numbers or IP addresses are sensitive.
By default, their values are masked in the result: letters become `A` or `a`
and digits `9`, so `jane@example.com` is listed as `aaaa@aaaaaaa.aaa`. Counts
and formats stay exact. Set `exposure.sensitive_values` to `hide` to remove
these values, or to `show` to keep them. Values of other fields are always
shown: share a scan as you would share the data.

## Large files

Files of 16 MiB or more are analyzed by several processes: Tabalyst reads the
file once and hands the values of each field to a worker process, one per
spare processor, at most 8. The scan document is the same whatever the
number of workers. Choose the number with `--workers`, or keep the scan in
one process with `--workers 1`, for example on a shared machine:

```console
tabalyst scan big.csv --workers 4
```

Memory stays bounded by the scan limits in each process. `tabalyst report`
accepts `--workers` too, except with `--scan`, which does not read the source.

## Progress and messages

Interactive terminals show the file and the share of it already read:

```text
[2/8] orders.json - Reading 42%
```

Progress and messages use standard error. Progress is disabled outside a
terminal and with `--no-progress` or `--quiet`. `--verbose` adds the detected
format, encoding, delimiter, status and number of diagnostics.

## Report from a scan

`tabalyst report customers.csv` uses the stored scan, and so does a report on
a JSON or JSONL file. If none exists, it creates one. A scan is reused when the
source content is unchanged, its effective scan settings match and the same
version of Tabalyst wrote it. For a JSON file, the settings include the
collection, so editing `config.structure.dataset_path` in the
[Inspect file](../inspect/json.md) rescans. A changed source causes an atomic replacement of
`scan.json`. Existing DuckDB projects from 0.4.3 are left untouched. Before
reusing a scan, Report checks the source's SHA-256, whatever its size and
modification time. When no scan settings are requested, Report keeps the
settings recorded by the existing scan.

Build the HTML report from a standalone scan document instead of reading the source
again:

```console
tabalyst report --scan customers.scan.json
```

This writes `customers.html` and `customers.json` beside the scan document,
named after the source it records; a JSON source `orders.json` gives
`orders.report.html`. The report is the one `tabalyst report customers.csv`
writes with the same scan settings, since the scan document holds everything
it needs, including duplicate rows and the preview. `-o`, `-d`, `--force` and
wildcards work as for sources:

```console
tabalyst report --scan scans/*.scan.json -d reports/
```

Tabalyst refuses a scan that no longer describes its source. It looks for the
source beside the scan document, under the name the scan recorded:

- a source of another size, or whose content changed (compared by SHA-256,
  whatever its modification time), is an error: scan it again;
- a source that is not beside the scan document is accepted, since the scan
  stands on its own, with a warning that it was not checked. This is the case
  for scans written with `-d` to another directory;
- a scan written by another version of Tabalyst is reported, with a warning;
- for a JSON or JSONL source, an Inspect file beside the source that asks for
  settings different from the scan's, or that cannot be read, is reported with
  a warning. The report still follows the scan document.

The report uses the scan settings recorded in the document. Configuration
files passed with `--config` give the presentation settings; settings given
in their `scan` object must have the values recorded in the document,
otherwise the report stops with exit code `2`. Settings they do not give, such
as a `--delimiter` passed to `tabalyst scan`, are taken from the document.
`--delimiter` and `--encoding` cannot be used with `--scan`. A document that
cannot be read, or was written by another format revision, fails without
stopping the other reports of the batch; scan its source again.

## Python API

```python
import tabalyst

result = tabalyst.scan("orders.json")
print(result.scope.records_analyzed)

batch = tabalyst.generate_scans(["data/*.csv"], output_dir="scans")
reports = tabalyst.generate_reports(["scans/*.scan.json"], from_scan=True)
```

`tabalyst.scan()` reads one source and returns the result without writing
anything; `result.model_dump(mode="json")` gives the document. It works at the
level of the engine: it does not read an Inspect file and, for a JSON file with
no `json.collections` setting, discovers every array reachable through objects
as a collection, plus the document itself as dataset `$`. Use
`tabalyst.generate_scans()` or `tabalyst.generate_reports()` to apply Inspect. Pass
`config=tabalyst.ScanConfig(...)` to change settings, and `workers=` to choose
the number of worker processes as `--workers` does. `tabalyst.generate_scans()`
writes standalone scan documents by default and returns the plan, successes and
failures. Pass `project_storage=True` to use the command's default scan-only
storage for CSV files.
`tabalyst.generate_reports(..., from_scan=True)` builds reports from scan
documents, as `tabalyst report --scan` does.

## Query caches

`tabalyst cache` inspects and cleans the disposable query caches of existing
DuckDB projects. See [Manage query caches](cache.md).
