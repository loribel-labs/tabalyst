---
title: Known limitations
description: What Tabalyst does not do yet during its alpha, including JSON report limits, duplicate detection memory and experimental JSON formats.
---

Tabalyst is in alpha. This page lists what it does not do yet, so you can decide
whether it fits your data. Limitations are removed from this page when a
published release lifts them.

## Input

- **CSV and JSON only.** `tabalyst report` and `tabalyst scan` read CSV and
  JSON files; `tabalyst sample` reads CSV files only. Excel
  workbooks, JSON Lines, XML, Parquet and databases are not supported; export
  them to CSV first.
- **JSON reports show scalar fields.** A JSON report lists the fields holding
  strings, numbers, booleans or nulls; the structure of objects and arrays
  (nesting, array lengths) appears only in `tabalyst scan` results. A record
  with a missing value is counted in `missing_values` only for nulls and empty
  values, not for absent fields.
- **JSON integers.** Integers of more than 4,300 digits, the Python limit, make
  a JSON file invalid.
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

- **Duplicate rows use memory.** Reports read the file once as a stream,
  with memory bounded by the scan limits, except duplicate row detection,
  which keeps 16 bytes per distinct row. `tabalyst scan` does not detect
  duplicate rows.
- **No row-level progress.** Report and scan progress show the share of the
  file read, not a number of rows.
- **Sequential batches.** Several files are processed one after another, not in
  parallel.

## Analysis

- **Types are hints.** Detected types describe the values; Tabalyst never
  converts or validates data against business rules.
- **Detector details not in reports.** The report shows one semantic type
  per column, the scan's primary interpretation, such as an enumeration, email
  addresses or postal codes. The coverage, formats and evidence of each
  detector, and normalization variants, are only in `tabalyst scan` documents.
- **Ambiguous dates stay ambiguous.** Values such as `02/03/2025` are never
  resolved from other values of the column; set
  `scan.detectors.date.ambiguous_order` to read them one way.
- **Syntax only.** Detectors check the form of values, never whether an
  address, number or code exists.
- **Missing values.** By default only empty and whitespace-only cells are
  missing. `NA`, `NULL` or `NaN` stay text unless you declare them in
  `scan.values.null_markers` in a [configuration file](configuration.md).

## Output and interfaces

- **Experimental JSON formats.** The [JSON profile](json-profile.md) and the
  [scan format](scan-format.md) may change incompatibly between releases. No
  migration tool is provided. Check `format_version` and `format_revision`
  before reading a profile or a scan.
- **Changing commands.** Commands and options may change incompatibly while
  Tabalyst is in alpha. Update often with `pip install --upgrade tabalyst`: this
  documentation describes the latest release.
- **English report.** The HTML report is only available in English.
- **Raw data in outputs.** The report, the JSON profile and scan documents
  contain values from the source file, including a preview of the first rows
  in reports. Values of sensitive fields, such as email addresses and phone
  numbers, are masked by default, but values of every other field are listed.
  Share them as you would share the data.
- **Patterns are trusted.** Regular expressions of scan patterns run without a
  timeout.
