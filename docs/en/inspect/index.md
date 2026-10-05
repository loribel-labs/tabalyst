---
title: Tabalyst Inspect
description: Overview of Tabalyst Inspect, the tool that finds which array of a JSON, JSONL or NDJSON file, or which sheet or table of an Excel workbook, holds its records and writes an editable Inspect file.
---

A JSON file can hold several arrays, and an Excel workbook several sheets.
**Tabalyst Inspect** reads a JSON, JSONL, NDJSON or Excel (`.xlsx`, `.xlsm`) file
once, finds which array, sheet or table holds the records and writes its answer
in `<source>-inspect.json` beside the source:

```console
tabalyst inspect orders.json
tabalyst inspect sales.xlsx
```

```text
Inspect: orders.json-inspect.json
Selection: $.customers[] (the only eligible collection)
```

The `config` section of that file holds the rules that `tabalyst scan` and
`tabalyst report` apply to the source: the collection, the flattening of nested
objects, the array mode and the error policy. Edit it, then scan or report as
usual. Inspect is optional: `scan` and `report` inspect a JSON file themselves
when it has no Inspect file, and stop with exit code `2` when several arrays are
equally plausible. Inspect reads JSON, JSONL and Excel files; CSV files are
refused.

## Pages

- [Inspect JSON and JSONL files](json.md): detection, selection rule, editing
  the `config`, JSONL files and messages.
- [Inspect Excel workbooks](excel.md): sheets and named tables, the header
  row, selection, editing the `config` and messages.
- [Inspect format](format.md): the structure of the Inspect file, and its
  [changelog](format-changelog.md).
- [Report JSON and JSONL files](../report/json.md) and [Scan CSV and JSON files](../scan/files.md):
  the tools that apply the Inspect file.
