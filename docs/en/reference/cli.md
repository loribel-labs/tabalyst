---
title: Command line (CLI)
description: Every tabalyst command and option for report, scan, inspect, sample and cache, with the shared conventions for inputs, outputs, wildcards, progress and exit codes.
---

The `tabalyst` command has five subcommands. `python -m tabalyst` accepts the
same ones.

| Command | Purpose | Guide |
| --- | --- | --- |
| `tabalyst report` | HTML report and JSON profile of CSV, JSON or JSONL files | [Tabalyst Report](../report/index.md) |
| `tabalyst scan` | Complete JSON description of every field | [Tabalyst Scan](../scan/files.md) |
| `tabalyst inspect` | Find how to read a JSON or JSONL file | [Tabalyst Inspect](../inspect/json.md) |
| `tabalyst sample` | Smaller CSV file from a larger one | [Tabalyst Sample](../sample/index.md) |
| `tabalyst cache` | Inspect and clean disposable query caches | [Query caches](../scan/cache.md) |

```console
tabalyst --version
tabalyst --help
tabalyst report --help
```

## Conventions

- **Inputs.** Every command except `cache` takes one or more files or
  non-recursive glob patterns, such as `*.csv`. Tabalyst expands wildcards
  itself, so they behave the same in PowerShell, `cmd` and POSIX shells. It
  does not search subfolders.
- **Outputs.** `-o` names one output file and accepts a single input. `-d`
  names an output directory and accepts one or many inputs. They are mutually
  exclusive.
- **Safety.** The whole batch is checked before any work: colliding outputs,
  an output that overwrites a source and existing outputs stop the batch.
  `--force` allows replacing outputs, never sources. Files are written
  atomically.
- **Failures.** A failed file does not stop the others; the command returns a
  non-zero exit code at the end.
- **Progress.** Progress and diagnostics use standard error. They are off
  outside a terminal, and with `--no-progress` or `--quiet`.
- **Configuration.** No configuration file is read unless `--config` is given.
  Explicit options override the configuration file, which overrides the
  defaults. See [Configuration](configuration.md).

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Analysis or output failure |
| `2` | Invalid configuration or command, or a JSON source whose collection must be chosen (see [Inspect](../inspect/json.md)) |
| `4` | Input error: missing, unreadable or invalid source |

When a batch has several kinds of failure, `1` wins over `2`, which wins over
`4`.

## tabalyst report

```console
tabalyst report INPUT... [OPTIONS]
```

Analyzes CSV, JSON or JSONL files and writes an HTML report and a JSON profile.
With `--scan`, the inputs are scan documents.

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | HTML filename for a single input |
| `-d`, `--output-dir PATH` | Directory for reports named after their sources |
| `--delimiter TEXT` | One-character CSV delimiter |
| `--encoding TEXT` | CSV text encoding |
| `-c`, `--config PATH` | JSON configuration file |
| `--scan` | Build reports from `.scan.json` documents without reading the sources |
| `-f`, `--force` | Replace existing report artifacts |
| `--details`, `--no-details` | One standalone HTML page per column (off by default) |
| `-q`, `--quiet` | Suppress success messages |
| `-v`, `--verbose` | Show detected input details |
| `--no-progress` | Disable progress |
| `--workers N` | Worker processes (1 for one process); files of 16 MiB or more use one per spare processor by default |

## tabalyst scan

```console
tabalyst scan INPUT... [OPTIONS]
```

Describes CSV, JSON or JSONL files. Without `-o` or `-d`, the scan is stored for
reuse; with them, a standalone `<stem>.scan.json` is written.

| Option | Description |
| --- | --- |
| `-o`, `--output PATH` | Scan filename ending in `.json`, for a single input |
| `-d`, `--output-dir PATH` | Directory for scans named after their sources |
| `-c`, `--config PATH` | JSON configuration file; repeat to merge several, in order |
| `--collection TEXT` | JSON collection path such as `$.customers[]`; repeatable |
| `--delimiter TEXT` | One-character CSV delimiter |
| `--encoding TEXT` | CSV text encoding |
| `-f`, `--force` | Replace existing scan files |
| `-q`, `--quiet` | Suppress success messages |
| `-v`, `--verbose` | Show detected source details |
| `--no-progress` | Disable progress |
| `--workers N` | Worker processes, as for `report` |

## tabalyst inspect

```console
tabalyst inspect INPUT... [OPTIONS]
```

Reads JSON, JSONL or NDJSON files once and writes `<source>-inspect.json` beside
each source. CSV files are refused with exit code `2`.

| Option | Description |
| --- | --- |
| `-c`, `--config PATH` | JSON configuration file; repeat to merge several, in order |
| `--reset-config` | Replace the `config` of an existing Inspect file by the detected one |
| `-f`, `--force` | Replace an existing Inspect file that cannot be kept |
| `-q`, `--quiet` | Suppress success messages |
| `-v`, `--verbose` | List every candidate collection |
| `--no-progress` | Disable progress |

## tabalyst sample

```console
tabalyst sample INPUT... --sample-method METHOD [OPTIONS]
```

Creates `<stem>.sample.csv` beside each CSV source without modifying it.

| Option | Description |
| --- | --- |
| `--sample-method` | Required: `first`, `last`, `random` or `stratified` |
| `--rows N` | Number of data rows to select |
| `--percent X` | Percentage of data rows to select (exclusive with `--rows`) |
| `--field TEXT` | Field used for stratified sampling |
| `--seed N` | Seed for reproducible random and stratified selection |
| `-o`, `--output PATH` | Output CSV filename for a single input |
| `-d`, `--output-dir PATH` | Directory for samples named after their sources |
| `-c`, `--config PATH` | JSON configuration file |
| `--delimiter TEXT` | One-character CSV delimiter |
| `--encoding TEXT` | CSV text encoding |
| `-f`, `--force` | Replace an existing sample file |

## tabalyst cache

```console
tabalyst cache info [SOURCE]
tabalyst cache clean [SOURCE]
```

`info` shows the number and size of disposable query caches, and `clean`
removes them. `SOURCE` is a CSV file whose project is selected; without it,
every project is. See [Manage query caches](../scan/cache.md).

## Environment

| Variable | Effect |
| --- | --- |
| `TABALYST_HOME` | Root of Tabalyst's local storage for stored scans and projects |
