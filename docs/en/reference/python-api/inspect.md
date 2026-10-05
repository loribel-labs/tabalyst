---
title: "Python API: Inspect"
description: The Python functions that inspect a JSON, JSONL or Excel file - inspect and generate_inspections - with their parameters, return values and examples.
---

`tabalyst.inspect()` inspects one source and `tabalyst.generate_inspections()`
several. Each writes the visible Inspect file, `<source>-inspect.json`, beside
its source. The command is [`tabalyst inspect`](../cli/inspect.md); the file is
described in the [Inspect format](../../inspect/format.md).

```python
import tabalyst

inspection = tabalyst.inspect("orders.json")
inspections = tabalyst.generate_inspections(["data/*.json", "logs/*.jsonl"])
workbook = tabalyst.inspect("sales.xlsx")
print(inspection.document.detection.selection.path)
```

## tabalyst.inspect()

```python
tabalyst.inspect(
    source,
    *,
    config_path=None,
    reset_config=False,
    force=False,
    on_progress=None,
)
```

Returns an `InspectResult` with `source`, `path` (the Inspect file that was
written) and `document` (what it holds, including `detection`, `warnings` and
`config`). Raises the error of the inspection.

- `source`: a JSON, JSONL, NDJSON or Excel (`.xlsx`, `.xlsm`) file.
- `config_path`: the `scan` section of these files seeds the `config` of a new
  Inspect file. See the [conventions](index.md#conventions).
- `reset_config`: replace the `config` of an existing Inspect file by the
  detected one. Without it, an existing file keeps its `config`.
- `force`: replace an existing Inspect file that cannot be kept.
- `on_progress`: see the [conventions](index.md#conventions).

## tabalyst.generate_inspections()

```python
tabalyst.generate_inspections(
    input_specs,
    *,
    config_path=None,
    reset_config=False,
    force=False,
    on_progress=None,
)
```

Returns a [batch result](index.md#batch-functions) whose successes hold an
`InspectResult` each. It lists the error of a source among the failures, where
`inspect()` raises it. Parameters are those of `inspect()`, with `input_specs`
for files or non-recursive glob patterns.

A source with several equally plausible collections is not a failure: its
`document.detection.selection.path` is `None` and
`document.detection.selection.basis` is `"ambiguous"`. Choose one with the
`collections` argument of `generate_reports()` or `generate_scans()`.
