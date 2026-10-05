---
title: Python API
description: The public Python functions of Tabalyst for reports, scans, Inspect and sampling, with the conventions they share - batch results, errors, configuration files and progress callbacks.
---

Everything the command line does is available from Python. Import `tabalyst`
and call the functions described in the pages below. Names not documented here
are internal and may change without notice during beta.

```python
import tabalyst

batch = tabalyst.generate_reports(["*.csv"], output_dir="reports")
```

## Functions by task

| To do this | Use | Page |
| --- | --- | --- |
| Write the report and profile of one CSV file | `tabalyst.analyze()` | [Python API: reports](report.md) |
| Write reports for CSV, JSON, JSONL or Excel files | `tabalyst.generate_reports()` | [Python API: reports](report.md) |
| Get a profile or its HTML without writing files | `tabalyst.analyze_csv()`, `tabalyst.analyze_scan()`, `tabalyst.render_report()` | [Python API: reports](report.md) |
| Scan one source in memory | `tabalyst.scan()` | [Python API: scans](scan.md) |
| Write scan documents | `tabalyst.generate_scans()` | [Python API: scans](scan.md) |
| Find how to read a JSON, JSONL or Excel file | `tabalyst.inspect()`, `tabalyst.generate_inspections()` | [Python API: Inspect](inspect.md) |
| Write a smaller CSV file | `tabalyst.sample_csv()`, `tabalyst.generate_samples()` | [Python API: sampling](sample.md) |

## Conventions

### Batch functions

The `generate_*` functions take `input_specs`, a list of files and
non-recursive glob patterns, as the command line does, and process the whole
batch. They return a batch result with the same four members:

- `plan`: the jobs that were planned, and `plan.warnings`, a tuple of
  `(source, sentence)` pairs about what planning left out, such as an option that
  a source cannot use.
- `successes`: one entry per source that was processed, with its `job` and its
  `result`.
- `failures`: one entry per source that failed, with its `job` and its `error`.
  A failed source does not stop the others.
- `succeeded`: `True` when there is no failure.

The whole batch is rejected before any work when an output is unsafe, such as
two sources that map to one file or an output that would replace a source.

```python
batch = tabalyst.generate_reports(["data/*.csv"], output_dir="reports")
for failure in batch.failures:
    print(failure.job.source, failure.error)
```

### Errors

Expected failures derive from `tabalyst.TabalystError`: `ConfigurationError`
(invalid options or configuration, or a collection that must be chosen),
`InputError` (a missing, unreadable or invalid source) and `ReportError`
(a file that cannot be rendered or written). A source whose collection must be
chosen raises a `ConfigurationError`, as exit code `2` does on the command line.
Functions for one source raise the error; batch functions list it among the
failures.

### Existing files

Existing outputs are never replaced silently. Pass `force=True` when
replacement is intended. A source is never replaced.

### Configuration files

`config_path` is one JSON [configuration file](../configuration.md) or a
sequence of files merged in order. Explicit arguments override the files, which
override the defaults.

### Progress

`on_progress` is a function that receives a progress event for each phase of
each source. It is optional, and is what the command line uses to print its
progress line.

## Related pages

- [Command line (CLI)](../cli/index.md), for the same operations as commands.
- [Configuration](../configuration.md), for the files that `config_path` reads
  and the `ScanConfig` settings.
- [Scan CSV and JSON files](../../scan/files.md) and
  [Inspect JSON and JSONL files](../../inspect/json.md).
