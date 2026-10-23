---
title: "Python API: Dedup"
description: The Python functions that find exact duplicate rows in CSV files - dedup_csv and generate_dedups - with their parameters, the results they return, the errors they raise and examples.
---

`tabalyst.dedup_csv()` deduplicates one CSV file and `tabalyst.generate_dedups()`
several. Dedup reads CSV files only, never modifies a source and never asks a
question. The command is [`tabalyst dedup`](../cli/dedup.md); the rules are in
[Tabalyst Dedup](../../dedup/index.md).

```python
import tabalyst

result = tabalyst.dedup_csv("customers.csv")
print(result.status, [path.name for path in result.files])
print(result.report.records.extra_copies)

batch = tabalyst.generate_dedups(["*.csv"], output_dir="deduped")
for item in batch.results:
    print(item.source.name, item.status)
```

## tabalyst.dedup_csv()

```python
tabalyst.dedup_csv(
    source,
    *,
    output_dir=None,
    max_rows=None,
    delimiter=None,
    encoding=None,
    config_path=None,
    memory_budget_mb=None,
    temp_dir=None,
    force=False,
    verify_content=False,
    on_progress=None,
)
```

Deduplicates one file and returns a `tabalyst.DedupResult`. `source` is a path,
never a pattern: a name with brackets is a file, and a derived name such as
`customers.unique.csv` given here is processed. The function never writes a
batch report.

- `output_dir`: the folder for the outputs; by default the folder of the
  source.
- `max_rows`: the most data records, 10,000,000 by default.
- `delimiter`, `encoding`: how the CSV file is read and written. By default the
  [configuration](../configuration.md#dedup-settings) decides, then a comma and
  `utf-8-sig`.
- `config_path`: one JSON configuration file or a sequence of files.
- `memory_budget_mb`: the memory budget in MiB before the rows go to disk, 512
  by default.
- `temp_dir`: the folder of the temporary store of the disk path.
- `force`: process the file even if it is already processed, and replace output
  files that Dedup did not write. A source is never replaced.
- `verify_content`: decide from the SHA-256 of the source and the outputs. It
  raises `tabalyst.ConfigurationError` with `force=True`.
- `on_progress`: a function that receives a progress event for each phase.

Explicit arguments override the configuration files, which override the
defaults. All the parameters are keyword-only except `source`.

### DedupResult

| Member | Content |
| --- | --- |
| `source` | The path of the source |
| `status` | `"DONE"`, `"SKIPPED"` or `"FAILED"` |
| `reason` | `"already_processed"` for `SKIPPED`; the failure reason for `FAILED`; otherwise `None` |
| `files` | A tuple of the CSV files this call created, empty for `SKIPPED` and for a source without duplicate |
| `report` | The report just written, or the one that was already there for `SKIPPED`: a complete or a failed report model, or `None` |
| `report_path` | The path of `<stem>.dedup.json`, or `None` when none was written or read |
| `verification` | `"metadata"` or `"digest"` for `SKIPPED`, otherwise `None` |
| `error` | The `TabalystError` of a `FAILED` source, otherwise `None` |
| `duration_seconds` | The time spent on the source |

The report models have the members of the [JSON report](../../dedup/format.md):
`result.report.records.total`, `result.report.outputs.csv_files_created` and so
on.

`dedup_csv()` raises the error of a failed source after it has written its
failed report when it could. It raises `tabalyst.ConfigurationError` for an
invalid option, `tabalyst.InputError` for a source problem (missing, invalid
CSV, the row limit, a source that changed) and `tabalyst.ReportError` for a
storage or output problem, including a file under an output name that Dedup did
not write.

```python
try:
    result = tabalyst.dedup_csv("customers.csv", max_rows=1000)
except tabalyst.InputError as error:
    print(error)
```

## tabalyst.generate_dedups()

```python
tabalyst.generate_dedups(
    input_specs,
    *,
    output_dir=None,
    max_rows=None,
    delimiter=None,
    encoding=None,
    config_path=None,
    memory_budget_mb=None,
    temp_dir=None,
    force=False,
    verify_content=False,
    on_progress=None,
)
```

Plans and runs a batch and returns a `tabalyst.BatchDedupResult`.
`input_specs` is a list of files and non-recursive glob patterns, as the
command line takes. The other parameters are those of `dedup_csv()`. Derived
files that a pattern finds are skipped, an unchanged source that is already
processed is not read again, and a source that fails does not stop the others:
it is in `failures`.

`dedup.summary.json` is written unless the only input is one file without a
wildcard. A batch that is refused as a whole (an invalid option, an output that
collides with a source or with another output, a file under an output name that
Dedup did not write) raises before any work.

### BatchDedupResult

| Member | Content |
| --- | --- |
| `plan` | The plan; `plan.eligible` lists the sources and `plan.excluded` the files skipped |
| `results` | One `DedupResult` per eligible source, in order, `DONE`, `SKIPPED` or `FAILED` |
| `failures` | The `FAILED` results, each with its `error` |
| `batch_report` | The path of `dedup.summary.json`, or `None` when none was written |
| `batch_report_error` | The `ReportError` when the batch report could not be written |
| `excluded` | The files found and skipped, each as a pair `(path, reason)` such as `derived_csv` |
| `succeeded` | `True` when no source failed and the batch report, if any, was written |
| `duration_seconds` | The duration of the batch |

The skipped files are not entries of `results`: they have no result of their
own. If the batch report cannot be written, the results are still returned.

```python
batch = tabalyst.generate_dedups(["data/*.csv"], output_dir="deduped")
for failure in batch.failures:
    print(failure.source, failure.reason, failure.error)
for path, reason in batch.excluded:
    print(path.name, reason)
```

This differs a little from the other `generate_*` functions: a batch result of
Dedup has `results` instead of `successes`, since a skipped source is neither a
success nor a failure.

## Progress

`on_progress` receives events with `stage` set to `"Dedup"`, the phase, the
position of the source in the batch and the bytes read. The events carry no
cell and no path.

```python
def show(event):
    print(event.stage, event.phase, event.detail)

tabalyst.dedup_csv("customers.csv", on_progress=show)
```

## Related pages

- [Python API](index.md), for the conventions shared by all functions.
- [Format of the Dedup reports](../../dedup/format.md).
- [Configuration](../configuration.md#dedup-settings).
