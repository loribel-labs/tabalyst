---
title: Tabalyst Inspect
description: Overview of Tabalyst Inspect, the tool that finds which array of a JSON, JSONL or NDJSON file holds its records and writes an editable Inspect file.
---

A JSON file can hold several arrays. **Tabalyst Inspect** reads a JSON, JSONL or
NDJSON file once, finds which array holds the records and writes its answer in
`<source>-inspect.json` beside the source:

```console
tabalyst inspect orders.json
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
equally plausible. Inspect reads JSON and JSONL files only; CSV files are
refused.

## Pages

- [Inspect JSON and JSONL files](json.md): detection, selection rule, editing
  the `config`, JSONL files and messages.
- [Inspect format](format.md): the structure of the Inspect file, and its
  [changelog](format-changelog.md).
- [Report JSON and JSONL files](../report/json.md) and [Scan CSV and JSON files](../scan/files.md):
  the tools that apply the Inspect file.
