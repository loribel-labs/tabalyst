---
title: Dedup format changelog
description: Current format version and revisions of the JSON documents written by tabalyst dedup - the report of a source and the batch report.
---

A report written by `tabalyst dedup` identifies its experimental contract with
three fields:

```json
{
  "format": "tabalyst.dedup",
  "format_version": "0.2.0",
  "format_revision": 1
}
```

`format` identifies the document kind: `tabalyst.dedup` for the report of a
source and `tabalyst.dedup.batch` for `dedup.summary.json`. `format_version`
names the compatibility family, and `format_revision` increases for meaningful
structural or semantic changes within it. Each kind has its own revision.
Beta revisions may be incompatible; automatic migration is not provided. A
report of another revision is not recognized as a result of Tabalyst: process
the source again with `--force`. The members are described in
[Format of the Dedup reports](format.md).

## Report of a source, version 0.2.0, revision 1

The starting point of the format. A report describes one source and has
three variants, told apart by `status`:

- `complete`: `generator`, `source` (name, size, `mtime_ns`, SHA-256),
  `settings` (`max_rows`, `delimiter`, `encoding`, `identity`), `records` (the
  exact counts and `extra_copy_percent`), `outputs` (`csv_files_created` and,
  for each CSV, `null` or its file name, rows, size and SHA-256) and `run`
  (passes, storage mode, durations, memory peak or `null`).
- `failed`: `source`, `settings`, `failure` (a stable `reason`, a `message`
  and, for the row limit, the `limit`) and `partial` (`records_read`,
  `certified` always `false`). It has no `records` and no `outputs`.
- `in_progress`: the report written while the files of an earlier result are
  replaced, with `recovery` (`previous_outputs` and `planned_outputs`). It is
  not a result.

## Batch report, version 0.2.0, revision 1

The starting point of `dedup.summary.json`: `generator`, `status`
(`complete`, `partial` or `failed`), `inputs`, `output_dir`, `counters`,
`totals` (`processed` and `reused`), `outputs`, `duration_seconds`, `sources`
and `diagnostics`.

A Dedup report holds no cell of your data and no absolute path. After the
first stable release, a change of structure or meaning of any variant raises
`format_revision`.
