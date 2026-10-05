---
title: "CLI: tabalyst inspect"
description: Every option of tabalyst inspect and examples for JSON, JSONL and Excel files, including the ready-to-run report commands it prints when several collections or tables are possible.
---

```console
tabalyst inspect INPUT... [OPTIONS]
```

Reads JSON, JSONL, NDJSON or Excel (`.xlsx`, `.xlsm`) files once and writes an
Inspect file, `<source>-inspect.json`, beside each source. The file lists the
collections or tables it found, says which one it selects and why, and holds the
`config` section you can edit. CSV files, and the spreadsheet formats `.xls`,
`.xlsb` and `.ods`, are refused with exit code `2`. See [Inspect JSON
files](../../inspect/json.md) and [Inspect Excel
workbooks](../../inspect/excel.md).

## Options

| Option | Description |
| --- | --- |
| `INPUT...` | One or more JSON, JSONL, NDJSON or Excel files, or non-recursive glob patterns (required) |
| `-c`, `--config PATH` | JSON [configuration file](../configuration.md) whose `scan` section seeds a new Inspect file; repeat to merge several, in order |
| `--reset-config` | Replace the `config` of an existing Inspect file by the detected one |
| `-f`, `--force` | Replace an existing Inspect file that cannot be kept |
| `-q`, `--quiet` | Suppress success messages; warnings and the commands to choose from remain |
| `-v`, `--verbose` | List every candidate collection, sheet or table, with its size and why it is not eligible |
| `--no-progress` | Disable the progress line |
| `--help` | Show the options and exit |

An existing Inspect file keeps its `config` when you inspect again. Inspect has
no `-o` or `-d`: the file always goes beside its source.

## Examples

### A workbook with one clear table

```console
tabalyst inspect sales.xlsx -v
```

```text
Inspect: D:\work\sales.xlsx-inspect.json
Selection: $.Orders (much larger than $.Regions)
Format: excel
Candidates: 3
  $.Orders (120 elements)
  $.Regions (5 elements)
  $.Notes (0 elements, no_header)
Warning [sales.xlsx]: $.Notes has no header row that Tabalyst can recognize.
```

`tabalyst report sales.xlsx` needs no choice.

### Several tables: the commands to copy

```console
tabalyst inspect shop.xlsx
```

```text
Inspect: D:\work\shop.xlsx-inspect.json
Selection: none (several collections are equally plausible)
Warning [shop.xlsx]: 2 tables are equally plausible: $.Costs (40), $["Sales Q1"] (50). None was selected: set config.structure.dataset_path to the one to analyze.
Choose the table to analyze:
  tabalyst report shop.xlsx --collection Costs
  tabalyst report shop.xlsx --collection '$["Sales Q1"]'
Or report every table: tabalyst report shop.xlsx --all-collections
```

Copy a line to run it. The short form (`Costs`) is used whenever the name is
plain, and the quoted path otherwise. A JSON file works the same way:

```console
tabalyst inspect shop.json
```

```text
Choose the collection to analyze:
  tabalyst report shop.json --collection customers
  tabalyst report shop.json --collection orders
Or report every collection: tabalyst report shop.json --all-collections
```

### Several files, other settings

```console
tabalyst inspect "exports/*.xlsx" "logs/*.jsonl"
tabalyst inspect shop.json --config settings.json
tabalyst inspect shop.json --reset-config
```

## Exit codes

| Code | When |
| --- | --- |
| `0` | Every Inspect file was written, even when no collection could be selected |
| `2` | Invalid options, a source Inspect does not read, or an invalid Inspect file |
| `4` | A source is missing, unreadable or invalid |
