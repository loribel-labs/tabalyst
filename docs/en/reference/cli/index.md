---
title: Command line (CLI)
description: The tabalyst commands (report, scan, inspect, sample, cache) and the conventions they share - inputs, wildcards, outputs, choosing a collection or table, progress and exit codes.
---

The `tabalyst` command has five subcommands. `python -m tabalyst` accepts the
same ones. Each has its own page with every option and examples.

| Command | Purpose | Options and examples |
| --- | --- | --- |
| `tabalyst report` | HTML report and JSON profile of CSV, JSON, JSONL or Excel files | [tabalyst report](report.md) |
| `tabalyst scan` | Complete JSON description of every field | [tabalyst scan](scan.md) |
| `tabalyst inspect` | Find how to read a JSON, JSONL or Excel file | [tabalyst inspect](inspect.md) |
| `tabalyst sample` | Smaller CSV file from a larger one | [tabalyst sample](sample.md) |
| `tabalyst cache` | Inspect and clean disposable query caches | [tabalyst cache](cache.md) |

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
- **Options by format.** `--delimiter` and `--encoding` read CSV files;
  `--collection` and `--all-collections` choose among the collections of a JSON
  file or the tables of a workbook. On a file that cannot use an option, the
  option is ignored and a warning says so, such as `--delimiter is ignored:
  sales.xlsx is not a CSV file.` Each command page has a table of the options
  by format.
- **Failures.** A failed file does not stop the others; the command returns a
  non-zero exit code at the end.
- **Progress.** Progress and diagnostics use standard error. They are off
  outside a terminal, and with `--no-progress` or `--quiet`.
- **Configuration.** No configuration file is read unless `--config` is given.
  Explicit options override the configuration file, which overrides the
  defaults. See [Configuration](../configuration.md).

## Choosing a collection or a table {#collection}

A JSON file can hold several arrays, and an Excel workbook several sheets and
tables. Tabalyst chooses one when the choice is clear, and otherwise stops with
exit code `2` and lists what you can choose from, as one command per choice, ready
to copy and run:

```text
Choose the table to analyze:
  tabalyst report shop.xlsx --collection Costs
  tabalyst report shop.xlsx --collection '$["Sales Q1"]'
Or report every table: tabalyst report shop.xlsx --all-collections
```

`scan`, `report` and `inspect` all print them. `tabalyst report` also takes
`--all-collections` to report every table in one command. The `--collection`
option takes the short form when the name is plain, and the absolute path
otherwise:

| Source | Value | Meaning |
| --- | --- | --- |
| JSON | `orders` | The array `$.orders[]` |
| JSON | `data.items` | The array `$.data.items[]` |
| JSON | `.` | The root array, `$[]` |
| JSON | `'$.data.items[]'` | The same array, as an absolute path |
| Excel | `Costs` | The sheet `Costs` |
| Excel | `Sales.Orders` | The named table `Orders` of the sheet `Sales` |
| Excel | `'$["Sales Q1"]'` | A sheet whose name is not a plain identifier (space, dot, accent) |

Put an absolute path in single quotes, so that the shell leaves `$` and `"`
alone in PowerShell and in POSIX shells. A JSON file accepts several
`--collection` options, a workbook one. [Inspect JSON files](../../inspect/json.md)
and [Inspect Excel workbooks](../../inspect/excel.md) explain how the choice is
made and how to keep it in an Inspect file.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Analysis or output failure |
| `2` | Invalid configuration or command, or a JSON or Excel source whose collection or table must be chosen (see [Inspect](../../inspect/json.md) and [Inspect Excel workbooks](../../inspect/excel.md)) |
| `4` | Input error: missing, unreadable or invalid source |

When a batch has several kinds of failure, `1` wins over `2`, which wins over
`4`.

## Environment

| Variable | Effect |
| --- | --- |
| `TABALYST_HOME` | Root of Tabalyst's local storage for stored scans and projects |
