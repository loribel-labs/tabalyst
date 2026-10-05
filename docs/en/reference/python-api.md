---
title: Python API
description: The public Python functions of Tabalyst for reports, scans, Inspect, sampling and errors, with signatures, return values and examples.
---

Everything the command line does is available from Python. Import `tabalyst`
and call the functions below. Names not listed here are internal and may
change without notice during beta.

```python
import tabalyst

batch = tabalyst.generate_reports(["*.csv"], output_dir="reports")
```

Expected failures derive from `tabalyst.TabalystError`: `ConfigurationError`,
`InputError` and `ReportError`. Existing outputs are never replaced silently;
pass `force=True` when replacement is intended.

## Reports

| Function | Returns |
| --- | --- |
| `tabalyst.analyze(csv_path, report_path, separator=None, encoding=None, config_path=None, force=False, details=False)` | The JSON-serializable profile of one CSV file, after writing its report |
| `tabalyst.generate_reports(input_specs, *, output=None, output_dir=None, separator=None, encoding=None, config_path=None, force=False, details=False, from_scan=False, workers=None)` | The batch result: `plan`, `successes`, `failures` and `succeeded` |
| `tabalyst.analyze_csv(path, config=None, workers=None)` | A `ReportProfile` model, without writing files |
| `tabalyst.analyze_scan(scan_path, config_path=None)` | A `ReportProfile` built from a scan document |
| `tabalyst.render_report(profile)` | The HTML of a report, as a string |

```python
result = tabalyst.analyze("customers.csv", "customers.html", separator=";")
reports = tabalyst.generate_reports(["scans/*.scan.json"], from_scan=True)
```

`generate_reports()` accepts CSV, JSON, JSONL and Excel sources, and scan documents
with `from_scan=True`. `config_path` is one configuration file or a sequence of
files merged in order. `workers` is the number of analysis processes.

## Scans

| Function | Returns |
| --- | --- |
| `tabalyst.scan(source, *, config=None, workers=None, ...)` | A `ScanResult`, without writing anything. It does not read an Inspect file |
| `tabalyst.generate_scans(input_specs, *, output=None, output_dir=None, config_path=None, delimiter=None, encoding=None, collections=None, force=False, workers=None, project_storage=False)` | The batch result. Writes one standalone `.scan.json` per source and applies Inspect to JSON, JSONL and Excel sources |

```python
scan = tabalyst.scan("orders.json")
scans = tabalyst.generate_scans(["data/*.json"], output_dir="scans")
sheet = tabalyst.scan(
    "sales.xlsx", config=tabalyst.ScanConfig(excel={"dataset_path": "$.Orders"})
)
```

Pass `config=tabalyst.ScanConfig(...)` to `scan()` to change its settings, and
`project_storage=True` to `generate_scans()` to use the command's reusable
storage instead of standalone documents.

## Inspect

| Function | Returns |
| --- | --- |
| `tabalyst.inspect(source, *, config_path=None, reset_config=False, force=False)` | An `InspectResult` with the path and the document of the Inspect file it wrote |
| `tabalyst.generate_inspections(input_specs, *, config_path=None, reset_config=False, force=False)` | The batch result for several sources |

```python
inspection = tabalyst.inspect("orders.json")
inspections = tabalyst.generate_inspections(["data/*.json", "logs/*.jsonl"])
workbook = tabalyst.inspect("sales.xlsx")
```

`inspect()` raises the error of the inspection, where `generate_inspections()`
lists it among the failures.

## Sampling

| Function | Returns |
| --- | --- |
| `tabalyst.sample_csv(source, *, method, rows=None, percent=None, field=None, seed=None, output=None, delimiter=",", encoding="utf-8-sig", force=False)` | A `SampleResult` |
| `tabalyst.generate_samples(input_specs, *, method, rows=None, percent=None, field=None, seed=None, output=None, output_dir=None, ...)` | The batch result |

```python
sample = tabalyst.sample_csv("customers.csv", method="random", rows=1000, seed=42)
```

`method` is `"first"`, `"last"`, `"random"` or `"stratified"`, or a
`tabalyst.SampleMethod`.

## Related pages

- [Command line (CLI)](cli.md), for the same operations as commands.
- [Configuration](configuration.md), for the files that `config_path` reads and
  the `ScanConfig` settings.
- [Scan CSV and JSON files](../scan/files.md) and
  [Inspect JSON and JSONL files](../inspect/json.md).
