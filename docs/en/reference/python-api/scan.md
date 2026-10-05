---
title: "Python API: scans"
description: The Python functions that scan a CSV, JSON, JSONL or Excel source - scan and generate_scans - with their parameters, return values and examples.
---

`tabalyst.scan()` scans one source in memory and writes nothing.
`tabalyst.generate_scans()` scans several sources and writes their scan
documents. The command is [`tabalyst scan`](../cli/scan.md); the result is
described in the [scan format](../../scan/format.md).

```python
import tabalyst

scan = tabalyst.scan("orders.json")
scans = tabalyst.generate_scans(["data/*.json"], output_dir="scans")
sheet = tabalyst.scan(
    "sales.xlsx",
    config=tabalyst.ScanConfig(excel={"dataset_path": "$.Orders"}),
)
```

## tabalyst.scan()

Reads one source completely and returns its scan result. It does not read an
Inspect file: choose the collection or the table with `config`.

```python
tabalyst.scan(
    source,
    *,
    config=None,
    registry=None,
    on_progress=None,
    on_record=None,
    workers=None,
)
```

Returns a `tabalyst.ScanResult`.

- `source`: the file to scan. A file ending in `.json` is read as JSON,
  `.jsonl` or `.ndjson` as JSONL, `.xlsx` or `.xlsm` as an Excel workbook, and
  any other as CSV.
- `config`: a `tabalyst.ScanConfig` that changes the settings, such as
  `ScanConfig(excel={"dataset_path": "$.Orders"})` for a table or
  `ScanConfig(json={"collections": ["$.customers[]"]})` for JSON collections. See
  [Configuration](../configuration.md).
- `workers`: number of processes that analyze values; `1` scans in this process.
  By default, large sources use one per spare processor. The result does not
  depend on it.
- `on_progress`: see the [conventions](index.md#conventions).
- `registry`, `on_record`: advanced. `registry` replaces the detectors (and scans
  in this process); `on_record` receives each analyzed record, in reading order,
  and must not modify it.

## tabalyst.generate_scans()

Scans several sources and writes one scan document each. It applies Inspect to
JSON, JSONL and Excel sources, as the command does.

```python
tabalyst.generate_scans(
    input_specs,
    *,
    output=None,
    output_dir=None,
    config_path=None,
    delimiter=None,
    encoding=None,
    collections=None,
    force=False,
    on_progress=None,
    workers=None,
    project_storage=False,
)
```

Returns a [batch result](index.md#batch-functions) whose successes hold the
`ScanResult` in `result`. A successful job also has `warnings`.

- `input_specs`: files or non-recursive glob patterns.
- `output`: scan filename ending in `.json`, for a single source.
- `output_dir`: folder for standalone scans named `<stem>.scan.json`.
- `delimiter`, `encoding`: CSV delimiter and text encoding.
- `collections`: JSON collections as absolute paths such as
  `["$.customers[]"]`, or the one Excel table such as `["$.Sales"]`.
- `project_storage`: `True` stores the scans in the reusable storage of the
  command, as `tabalyst scan` does without `-o` or `-d`, instead of writing
  standalone documents.
- `config_path`, `force`, `on_progress`: see the [conventions](index.md#conventions).
- `workers`: as for `scan()`.

A source whose collection or table cannot be decided fails alone with a
`ConfigurationError`; an option that a source cannot use is listed in
`batch.plan.warnings`.
