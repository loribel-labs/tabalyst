---
title: Release notes
description: What changed in each Tabalyst release, from 0.1.0 to 0.6.0 - new commands, compatibility changes and experimental JSON format revisions.
---

Tabalyst is in beta. Interfaces and JSON formats may change between releases;
update with `pip install --upgrade tabalyst`. Each JSON format has its own
changelog: [profile](../report/profile-changelog.md),
[scan](../scan/format-changelog.md) and
[Inspect](../inspect/format-changelog.md). The full release notes of
each version are on
[GitHub](https://github.com/loribel-labs/tabalyst/tree/main/docs/dev/releases).

## 0.6.0

Adds Excel workbooks and relicenses the code under MPL-2.0.

- `tabalyst inspect`, `scan` and `report` read `.xlsx` and `.xlsm` workbooks.
  Inspect lists the sheets and named tables as candidates and selects one when
  it is clearly the largest; `dataset_path` (`$.Sheet` or `$.Sheet.Table`) and
  `header_row` choose the table.
- Profile format revision 11 and scan format revision 6: stored scans of an
  older revision are replaced by `tabalyst scan` and `tabalyst report`. The
  Inspect format gains the `excel` kind without a revision change.
- The code is now licensed under MPL-2.0; the documentation stays CC BY 4.0.

## 0.5.1

Chooses a JSON collection from `report`, and from `inspect`'s own output.

- `tabalyst report` gains `--collection`, as `tabalyst scan` has it. It outranks
  the Inspect file and the configuration, and cannot be used with `--scan`.
- `--collection` accepts a short form: `data.items` stands for
  `$.data.items[]`, `.` for the root array `$[]`, and a key made of digits, such
  as `groups.121`, is accepted as it is.
- When several collections are equally plausible, `tabalyst inspect` prints one
  ready-to-run `tabalyst report` command per collection.
- The report theme button cycles auto (the system preference, now the default),
  light and dark.

## 0.5.0

Adds Tabalyst Inspect and JSON Lines support.

- `tabalyst inspect` finds the collection of records of a `.json`, `.jsonl` or
  `.ndjson` file and writes an editable `<source>-inspect.json`. Its `config`
  sets the collection, the flattening of nested objects, the arrays mode and the
  error policy. Scan and Report apply it.
- When several collections are equally plausible, or none is usable, `scan` and
  `report` stop with exit code `2` and list the candidates.
- JSONL sources can be scanned and reported. A bad line is excluded, counted and
  located by default; `errors.policy: strict` stops at the first one.
- A stored scan is reused only when the full source content, the effective
  configuration and the Tabalyst version are unchanged.
- New Python functions `tabalyst.inspect()` and
  `tabalyst.generate_inspections()`. On Windows, Tabalyst expands wildcards
  itself.
- **Compatibility.** `tabalyst scan` without `-o` or `-d` no longer writes
  `<stem>.scan.json` beside a JSON source. A JSON file with a single object or a
  scalar root has no dataset. Formats: scan revision `5`, profile revision `10`,
  Inspect revision `1`; documents of 0.4.4 must be generated again.

## 0.4.4

Restores fast default CSV scans. `tabalyst scan` stores a reusable `scan.json`
without building a DuckDB database, and `tabalyst report` reuses it. Adds
`tabalyst report --details`, one standalone HTML page per column.

## 0.4.3

First beta release. Adds `tabalyst cache info` and `tabalyst cache clean` for
the disposable query caches of DuckDB projects.

## 0.4.2

Several times faster scans on large files: batched detection, and worker
processes for files of 16 MiB or more (`--workers`).

## 0.4.1

Adaptive detection (`scan.detection.warmup_values`, `scan.detection.probe_interval`)
for columns with many distinct values, and a report time that includes the scan.

## 0.4.0

Introduces Tabalyst Scan, a streaming analysis engine for CSV and JSON, and
rebuilds Tabalyst Report on it: reports for JSON files, bounded memory, no
pandas. Adds `tabalyst scan`, the detectors and the `scan` configuration
section.

## 0.3.0

Introduces Tabalyst Sample: `tabalyst sample` with `first`, `last`, `random` and
`stratified` methods, `--rows`, `--percent` and `--seed`.

## 0.2.0

Command-oriented toolkit: `tabalyst report INPUT... [OPTIONS]`, automatic report
names, several inputs and wildcards, `-d/--output-dir`, batch preflight checks,
progress on standard error and the `generate_reports()` API.

## 0.1.x

First packaged releases: `tabalyst.analyze()`, the HTML report and the JSON
profile, `executions.json`, and the refreshed report design of 0.1.2.
