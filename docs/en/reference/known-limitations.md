---
title: Known limitations
description: What Tabalyst does not do yet during its alpha, including CSV-only input, in-memory loading and an experimental JSON format.
---

Tabalyst is in alpha. This page lists what it does not do yet, so you can decide
whether it fits your data. Limitations are removed from this page when a
published release lifts them.

## Input

- **CSV only.** Tabalyst reads delimited text files. Excel workbooks, JSON,
  Parquet and databases are not supported; export them to CSV first.
- **One header row.** The first record is always the header.
- **Strict structure.** A record with too few or too many fields, or a blank
  line inside the data, stops the analysis of that file with an error.
- **No recursive search.** `tabalyst report *.csv` reads the matching files of
  one folder; it does not search subfolders.

## Size and performance

- **The whole file is loaded into memory.** Very large files can exhaust the
  available memory. There is no sampling or chunked reading yet.
- **No row-level progress.** Progress shows the current file and phase
  (reading, analyzing, rendering, writing), not a percentage of rows.
- **Sequential batches.** Several files are processed one after another, not in
  parallel.

## Analysis

- **Types are hints.** Detected types describe the values; Tabalyst never
  converts or validates data against business rules.
- **Limited number formats.** Decimal commas (`12,50`) are not recognized as
  numbers and are reported as text.
- **Few semantic types.** Only enumerations and dates are detected as semantic
  types. Email addresses, postal codes and identifiers remain text.
- **Missing values.** By default only empty and whitespace-only cells are
  missing. `NA`, `NULL` or `NaN` stay text unless you declare them in a
  [configuration file](configuration.md).

## Output and interfaces

- **Experimental JSON format.** The [JSON profile](json-profile.md) may change
  incompatibly between releases. No migration tool is provided. Check
  `format_version` and `format_revision` before reading a profile.
- **Changing commands.** Commands and options may change incompatibly while
  Tabalyst is in alpha.
- **English report.** The HTML report is only available in English.
- **Raw data in outputs.** The report and the JSON profile contain values from
  the source file, including a preview of the first rows. Share them as you
  would share the data.
