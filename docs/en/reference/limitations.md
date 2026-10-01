---
title: Known limitations
description: What Tabalyst does not do yet during its beta, including JSON report limits, the duplicate detection budget and experimental JSON formats.
---

Tabalyst is in beta. This page lists what it does not do yet, so you can decide
whether it fits your data. Limitations are removed from this page when a
published release lifts them.

## Input

- **CSV, JSON and JSONL only.** `tabalyst report` and `tabalyst scan` read CSV,
  JSON and JSONL files (`.jsonl`, `.ndjson`); `tabalyst inspect` reads JSON and
  JSONL files; `tabalyst sample` reads CSV files only. Excel workbooks, XML,
  GeoJSON, compressed JSON, Parquet and databases are not supported; export
  them to CSV first.
- **One collection per JSON source by default.** Tabalyst analyzes the one
  collection of records that [Inspect](../inspect/json.md) selects.
  When several arrays are equally plausible, `scan` and `report` stop until you
  choose one with `--collection` or in the Inspect file. A JSON file that is a
  single object, a scalar or an array of plain values has no collection and is
  not turned into a one-row dataset. Inspect looks for arrays only through
  object keys, at most `scan.json.discovery_max_depth` (3) deep, and when it
  finds more than 100 it selects none. The relations between collections are not
  analyzed.
- **Inspect selects by size, not by name.** A collection is selected on its own
  when it is the only array of objects, or has at least 10 times more elements
  than the next one. A large table next to a much larger one, as in a relational
  export, can be selected without being the one you want: check the `selection`
  in the Inspect file.
- **Inspect observes the first records.** Its fields, depths and nesting come
  from the first 1,000 records of each collection; a field that appears later is
  found by the scan, not listed in the Inspect file. Inspect reads the whole
  source, so its time grows with the file size; on synthetic benchmarks, roughly
a tenth of the time of a scan.
- **No array explosion, no JSONPath.** Arrays never add records
  (`arrays.mode` is `preserve`), and collection paths use a limited syntax: keys
  from the root, ending with `[]`.
- **Inspect is for JSON and JSONL.** `tabalyst inspect` refuses CSV files.
- **JSON reports show scalar fields.** A JSON report lists the fields holding
  strings, numbers, booleans or nulls; the structure of objects and arrays
  (nesting, array lengths) appears only in `tabalyst scan` results. A record
  with a missing value is counted in `missing_values` only for nulls and empty
  values, not for absent fields.
- **JSON integers.** Integers of more than 4,300 digits, the Python limit, make
  a JSON file invalid.
- **Invalid JSON stops everything.** A syntax error anywhere in a `.json` file,
  even after the records Inspect observed, fails the inspection and the scan:
  Tabalyst does not recover a damaged document. In a JSONL file, only the
  affected lines are excluded.
- **JSONL lines.** A line is read as UTF-8 and parsed as a whole, up to
  `scan.limits.max_line_bytes` (16 MiB, at most 256 MiB); parsing a line needs
  about 7 to 13 times its size in memory. A file of compressed or non-UTF-8
  text is not read.
- **One header row.** The first record is always the header.
- **Strict structure.** A record with too few or too many fields, or a blank
  line inside the data, stops the analysis of that file with an error.
  `tabalyst scan` and `tabalyst report` can exclude such records instead with
  the `tolerant` error policy (`scan.errors.policy`); the report then lists
  them in its `excluded_records` issue.
- **No recursive search.** `tabalyst report *.csv` reads the matching files of
  one folder; it does not search subfolders. The same applies to `sample` and
  `scan`.

## Size and performance

- **Duplicate rows have a budget.** Reports and scans read the file once as a
  stream, with memory bounded by the scan limits. Duplicate row detection
  stores about 80 bytes per distinct row, up to
  `scan.limits.max_tracked_records` (2,000,000 rows by default). Beyond it,
  later rows are compared only with the stored ones, so the report shows a
  lower bound such as `≥ 12`. Raise the limit for an exact count, or set
  `scan.records.duplicates` to `false` to skip the detection.
- **No row-level progress.** Report and scan progress show the share of the
  file read, not a number of rows.
- **One reader per file.** Files of 16 MiB or more are analyzed by worker
  processes, but each file is read by a single process, which bounds the
  speed on very large files. Several files are processed one after another,
  not in parallel.

## Analysis

- **Types are hints.** Detected types describe the values; Tabalyst never
  converts or validates data against business rules.
- **Detector evidence not in reports.** The report shows what each detector
  recognized, with its formats, and the normalization variant groups of each
  column. The evidence examples and details of each detector are only in
  `tabalyst scan` documents.
- **Ambiguous dates stay ambiguous.** Values such as `02/03/2025` are never
  resolved from other values of the column; set
  `scan.detectors.date.ambiguous_order` to read them one way.
- **Syntax only.** Detectors check the form of values, never whether an
  address, number or code exists.
- **Rare late values on large columns.** On a column with more than
  `scan.detection.warmup_values` distinct values (10,000 by default), a
  detector that recognized none of the first ones, or only a few early ones
  (`scan.detection.rare_share`), stops testing the others, except about one
  value in 100. A rare email address, phone number or code that appears only
  later can go unnoticed, and a sensitive one is then not masked. Set
  `scan.detection.warmup_values` to `0` to test every value.
- **Missing values.** By default only empty and whitespace-only cells are
  missing. `NA`, `NULL` or `NaN` stay text unless you declare them in
  `scan.values.null_markers` in a [configuration file](configuration.md).

## Output and interfaces

- **Experimental JSON formats.** The [JSON profile](../report/profile.md), the
  [scan format](../scan/format.md) and the [Inspect format](../inspect/format.md) may
  change incompatibly between releases. No migration tool is provided: an
  Inspect file of another version is refused, and `tabalyst inspect --force`
  writes a new one. Check `format_version` and `format_revision` before reading
  a profile, a scan or an Inspect file.
- **Inspect files are yours to keep.** `tabalyst scan` and `tabalyst report`
  never write or change the Inspect file beside a source; only
  `tabalyst inspect` does. A source whose own name ends in `-inspect.json`
  cannot be used until renamed.
- **Changing commands.** Commands and options may change incompatibly while
  Tabalyst is in beta. Update often with `pip install --upgrade tabalyst`: this
  documentation describes the latest release.
- **English report.** The HTML report is only available in English.
- **Raw data in outputs.** The report, the JSON profile and scan documents
  contain values from the source file, including a preview of the first rows
  in reports. Values of sensitive fields, such as email addresses and phone
  numbers, are masked by default, but values of every other field are listed.
  Share them as you would share the data.
- **Patterns are trusted.** Regular expressions of scan patterns run without a
  timeout.
