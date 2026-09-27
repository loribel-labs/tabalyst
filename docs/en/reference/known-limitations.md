---
title: Known limitations
description: What Tabalyst does not do yet during its alpha, including CSV-only reports, in-memory report loading and experimental JSON formats.
---

Tabalyst is in alpha. This page lists what it does not do yet, so you can decide
whether it fits your data. Limitations are removed from this page when a
published release lifts them.

## Input

- **CSV and JSON only.** `tabalyst report` and `tabalyst sample` read
  delimited text files; `tabalyst scan` also reads JSON files. Excel
  workbooks, JSON Lines, XML, Parquet and databases are not supported; export
  them to CSV first.
- **Reports from CSV only.** A JSON file can be scanned, but not turned into an
  HTML report yet.
- **JSON integers.** Integers of more than 4,300 digits, the Python limit, make
  a JSON file invalid.
- **One header row.** The first record is always the header.
- **Strict structure.** A record with too few or too many fields, or a blank
  line inside the data, stops the analysis of that file with an error.
  `tabalyst scan` can exclude such records instead with the `tolerant` error
  policy.
- **No recursive search.** `tabalyst report *.csv` reads the matching files of
  one folder; it does not search subfolders. The same applies to `sample` and
  `scan`.

## Size and performance

- **Reports load the whole file into memory.** Very large files can exhaust
  the available memory. `tabalyst scan` and `tabalyst sample` read files as a
  stream with bounded memory.
- **No row-level report progress.** Report progress shows the current file and
  phase (reading, analyzing, rendering, writing), not a percentage of rows.
  Scan progress shows the share of the file read.
- **Sequential batches.** Several files are processed one after another, not in
  parallel.

## Analysis

- **Types are hints.** Detected types describe the values; Tabalyst never
  converts or validates data against business rules.
- **Limited number formats in reports.** Decimal commas (`12,50`) are not
  recognized as numbers by the report and are reported as text. `tabalyst scan`
  recognizes them.
- **Few semantic types in reports.** The report only detects enumerations and
  dates. `tabalyst scan` also detects email addresses, URLs, phone numbers
  (Canada, United States, France), Canadian postal codes and ZIP codes,
  currency amounts, percentages, quantities, UUIDs and IP addresses, but the
  report does not show them yet.
- **Syntax only.** Detectors check the form of values, never whether an
  address, number or code exists.
- **Missing values.** By default only empty and whitespace-only cells are
  missing. `NA`, `NULL` or `NaN` stay text unless you declare them in a
  [configuration file](configuration.md).

## Output and interfaces

- **Experimental JSON formats.** The [JSON profile](json-profile.md) and the
  [scan format](scan-format.md) may change incompatibly between releases. No
  migration tool is provided. Check `format_version` and `format_revision`
  before reading a profile or a scan.
- **Changing commands.** Commands and options may change incompatibly while
  Tabalyst is in alpha. Update often with `pip install --upgrade tabalyst`: this
  documentation describes the latest release.
- **English report.** The HTML report is only available in English.
- **Raw data in outputs.** The report and the JSON profile contain values from
  the source file, including a preview of the first rows. A scan document masks
  values of sensitive fields by default, but lists values of every other field.
  Share them as you would share the data.
- **Patterns are trusted.** Regular expressions of scan patterns run without a
  timeout.
