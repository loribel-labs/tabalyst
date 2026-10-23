---
title: Format of the Dedup reports
description: The JSON report written for each source by tabalyst dedup and the batch report dedup.summary.json - members, statuses, counts that always add up, failure reasons, and the JSON Schemas.
---

`tabalyst dedup` writes two kinds of JSON documents. The report of a source,
`<stem>.dedup.json`, has `format: "tabalyst.dedup"`. The batch report,
`dedup.summary.json`, has `format: "tabalyst.dedup.batch"`. Both have
`format_version: "0.2.0"` and `format_revision: 1`, and both are experimental
while Tabalyst is in beta: a later revision can change the structure, and
Tabalyst does not migrate older documents. See the
[format changelog](format-changelog.md).

The JSON Schemas are `tabalyst/schemas/tabalyst.dedup.schema.json` and
`tabalyst/schemas/tabalyst.dedup.batch.schema.json` in the installed package.
They are generated from the same models as the documents and refuse unknown
members and any other `format_revision`.

Neither document holds a cell of your data. The reports use no absolute path
and no message that could quote a value.

## Report of a source

The report is written last, after the CSV files it lists are published. A
report with `status` `complete` therefore proves that the whole set exists.
Every member is always present; what does not apply is `null`.

```json
{
  "format": "tabalyst.dedup",
  "format_version": "0.2.0",
  "format_revision": 1,
  "generator": {"name": "tabalyst", "version": "0.7.1"},
  "status": "complete",
  "source": {
    "name": "customers.csv",
    "size_bytes": 66,
    "mtime_ns": 1792768622411063100,
    "content_sha256": "bd9787d9..."
  },
  "settings": {
    "max_rows": 10000000,
    "delimiter": ",",
    "encoding": "utf-8-sig",
    "identity": "full_decoded_csv_row_v1"
  },
  "records": {
    "total": 6,
    "distinct": 3,
    "singletons": 1,
    "duplicate_groups": 2,
    "groups_occurring_twice": 1,
    "groups_occurring_three_plus": 1,
    "extra_copies": 3,
    "duplicate_group_occurrences": 5,
    "max_occurrences": 3,
    "extra_copy_percent": 50.0
  },
  "outputs": {
    "csv_files_created": 3,
    "unique": {
      "file": "customers.unique.csv",
      "rows": 3,
      "size_bytes": 42,
      "sha256": "90212a72..."
    },
    "duplicates": {
      "file": "customers.duplicates.csv",
      "rows": 2,
      "size_bytes": 29,
      "sha256": "04abc2f6..."
    },
    "duplicates_all": {
      "file": "customers.duplicates_all.csv",
      "rows": 5,
      "size_bytes": 60,
      "sha256": "d8618623..."
    }
  },
  "run": {
    "passes": 2,
    "storage_mode": "memory",
    "duration_seconds": 0.0093,
    "first_pass_seconds": 0.0012,
    "second_pass_seconds": 0.0073,
    "memory_peak_bytes": null
  }
}
```

The hashes are shortened here; a real report holds the 64 hexadecimal
characters.

### Members of a complete report

| Member | Content |
| --- | --- |
| `generator` | The `name` and `version` of Tabalyst that wrote it |
| `source` | `name` of the file, `size_bytes`, `mtime_ns` (modification time in nanoseconds) and `content_sha256` of the source as it was read |
| `settings` | `max_rows`, the `delimiter`, the `encoding` and the `identity` of a row, `full_decoded_csv_row_v1` |
| `records` | The counts, below |
| `outputs` | `csv_files_created`, and for each of `unique`, `duplicates` and `duplicates_all`, `null` or `file`, `rows`, `size_bytes` and `sha256` of the file as written |
| `run` | `passes` (`1` or `2`), `storage_mode` (`memory` or `disk`), `duration_seconds`, `first_pass_seconds`, `second_pass_seconds` (`null` with one pass) and `memory_peak_bytes` (`null` unless `--verbose` measured it) |

`outputs` is the inventory of the files the run published. It is also what
Tabalyst uses to know that a file under an output name is its own.
`settings.max_rows` is the limit of the run; a result stays valid when you
raise it, and a source with more records than a lowered limit is processed
again and fails.

### Counts

| Member of `records` | Meaning |
| --- | --- |
| `total` | Data records, the header excluded |
| `distinct` | Different rows; the rows of `unique.csv` |
| `singletons` | Rows that occur once |
| `duplicate_groups` | Rows that occur at least twice; the rows of `duplicates.csv` |
| `groups_occurring_twice` | Groups of exactly two occurrences |
| `groups_occurring_three_plus` | Groups of three occurrences or more |
| `extra_copies` | Occurrences after the first of their row |
| `duplicate_group_occurrences` | Occurrences of the rows of the groups, first ones included; the rows of `duplicates_all.csv` |
| `max_occurrences` | The most occurrences of one row; `0` when `total` is `0` |
| `extra_copy_percent` | `100 * extra_copies / total`, and `0` when `total` is `0` |

These always hold, and Tabalyst refuses to write or reuse a report that breaks
one:

```text
total = distinct + extra_copies
distinct = singletons + duplicate_groups
duplicate_group_occurrences = duplicate_groups + extra_copies
duplicate_groups = groups_occurring_twice + groups_occurring_three_plus
duplicate_groups = 0 if and only if max_occurrences <= 1
groups_occurring_three_plus > 0 if and only if max_occurrences >= 3
unique.rows = distinct
duplicates.rows = duplicate_groups
duplicates_all.rows = duplicate_group_occurrences
passes = 1 if and only if duplicate_groups = 0
```

`unique` and `duplicates` are present if and only if `duplicate_groups` is
above `0`, and `duplicates_all` if and only if `max_occurrences` is `3` or
more. `csv_files_created` is the number of files that are not `null`.

### No duplicate

A source without duplicate has no CSV. `outputs.csv_files_created` is `0`,
`unique`, `duplicates` and `duplicates_all` are `null`, `passes` is `1` and
`second_pass_seconds` is `null`. A file with only a header has every count at
`0`.

### Failed report

A source that fails gets a report with `status` `failed`. It has no `records`
and no `outputs`, and announces no CSV:

```json
{
  "format": "tabalyst.dedup",
  "format_version": "0.2.0",
  "format_revision": 1,
  "generator": {"name": "tabalyst", "version": "0.7.1"},
  "status": "failed",
  "source": {
    "name": "customers.csv",
    "size_bytes": 84,
    "mtime_ns": 1792768646688491500
  },
  "settings": {
    "max_rows": 3,
    "delimiter": ",",
    "encoding": "utf-8-sig",
    "identity": "full_decoded_csv_row_v1"
  },
  "failure": {
    "reason": "row_limit_exceeded",
    "message": "The file has more than 3 data records.",
    "limit": 3
  },
  "partial": {"records_read": 4, "certified": false}
}
```

`failure.reason` is a stable code; `message` is a fixed sentence with no path
and no cell. `partial.records_read` is `null` when the failure did not know it,
and `certified` is always `false`: nothing in a failed report is a result.
`source` holds the size and `mtime_ns` when they could be read. A failed
report is written when it can be; if it cannot, the original error is the one
reported. A refusal before any work (a collision, an invalid option) writes
nothing.

| `reason` | Situation | Exit code |
| --- | --- | --- |
| `row_limit_exceeded` | More than `max_rows` records | `4` |
| `invalid_csv` | Empty file, a record of the wrong width, a malformed record, a cell over 131,072 characters | `4` |
| `encoding_error` | The file cannot be decoded with the encoding | `4` |
| `source_unreadable` | The source cannot be opened or read | `4` |
| `source_changed` | The source changed between the two readings | `4` |
| `insufficient_disk_space` | The temporary store or an output found no room | `1` |
| `storage_unavailable` | The temporary folder or database is unusable | `1` |
| `output_unwritable` | An output or the report cannot be written | `1` |
| `unexpected_error` | Any other failure | `1` |

In a batch, a source that an output check refused just before its run fails
alone with the reason `output_refused` and has no report.

### In progress

Before it changes the files of an earlier result, Tabalyst replaces the report
with one that has `status` `in_progress`. It lists the files of the earlier
result (`recovery.previous_outputs`) and the files being published
(`recovery.planned_outputs`), each with `file`, `size_bytes` and `sha256`. It
keeps the output files provable if the run is interrupted, so the next run can
repair them. It is not a result and is never reused. A report you read at rest
is `complete` or `failed`; an `in_progress` one means that a run stopped.

## Batch report

`dedup.summary.json` is written by a run with a pattern or several inputs; see
[Batch and already processed files](batch.md#the-batch-report). It is replaced
at each run and describes that run.

| Member | Content |
| --- | --- |
| `generator` | As in the report of a source |
| `status` | `complete`; `partial` when some eligible source failed; `failed` when every one did |
| `inputs` | The patterns and files given |
| `output_dir` | The folder given with `-d`, relative to the folder of the batch report (so `.`), or `null` without `-d` |
| `counters` | `found`, `eligible`, `excluded`, `done`, `skipped` and `failed` |
| `totals` | `processed` (sources done in this run) and `reused` (sources skipped, from their earlier reports), each with `sources`, `records`, `extra_copies` and `duplicate_groups`; nothing is counted twice |
| `outputs` | `csv_files_created` by this run only, `reports_available` and `reports_updated` |
| `duration_seconds` | The duration of the run |
| `sources` | One entry per file found, below |
| `diagnostics` | One note for a source refused just before its run or whose failed report could not be written |

Each entry of `sources` has `file`, `status` (`DONE`, `SKIPPED`, `FAILED` or
`EXCLUDED`), `reason` (`already_processed` for `SKIPPED`, the failure reason
for `FAILED`, the exclusion reason for `EXCLUDED`, `null` for `DONE`),
`verification` (`metadata` or `digest` for `SKIPPED`), `report`,
`records` (`total`, `distinct`, `extra_copies` and `duplicate_groups`, taken
from the report of the source) and `csv_files_created`. An excluded file has no
report and no count. The counters tie together: `found` is `eligible` plus
`excluded`, and `eligible` is `done` plus `skipped` plus `failed`.

```json
{
  "format": "tabalyst.dedup.batch",
  "format_version": "0.2.0",
  "format_revision": 1,
  "generator": {"name": "tabalyst", "version": "0.7.1"},
  "status": "complete",
  "inputs": ["customers.csv", "products.csv"],
  "output_dir": null,
  "counters": {"found": 2, "eligible": 2, "excluded": 0,
               "done": 2, "skipped": 0, "failed": 0},
  "totals": {
    "processed": {"sources": 2, "records": 9, "extra_copies": 3,
                  "duplicate_groups": 2},
    "reused": {"sources": 0, "records": 0, "extra_copies": 0,
               "duplicate_groups": 0}
  },
  "outputs": {"csv_files_created": 3, "reports_available": 2,
              "reports_updated": 2},
  "duration_seconds": 0.0146,
  "sources": [
    {
      "file": "customers.csv", "status": "DONE", "reason": null,
      "verification": null, "report": "customers.dedup.json",
      "records": {"total": 6, "distinct": 3, "extra_copies": 3,
                  "duplicate_groups": 2},
      "csv_files_created": 3
    },
    {
      "file": "products.csv", "status": "DONE", "reason": null,
      "verification": null, "report": "products.dedup.json",
      "records": {"total": 3, "distinct": 3, "extra_copies": 0,
                  "duplicate_groups": 0},
      "csv_files_created": 0
    }
  ],
  "diagnostics": []
}
```

Paths in the batch report are relative to its folder and use `/`. When no
relative path exists (another drive), the name alone is given.

## Reading the reports from a script

Read `status` first, and only `complete` carries `records` and `outputs`.
Compare `format`, `format_version` and `format_revision` before you trust any
other member. To know whether a CSV file is the one a report describes,
compare its size and `sha256` with the inventory.

```python
import json

with open("customers.dedup.json", encoding="utf-8") as stream:
    report = json.load(stream)
if report["status"] == "complete":
    print(report["records"]["extra_copies"])
```
