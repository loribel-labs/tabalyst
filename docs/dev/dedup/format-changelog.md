# Dedup report format changelog

Maintainer notes, never published. The public page `docs/en/dedup/format-changelog.md`
is written with the rest of the public documentation (lot 11), when Tabalyst Dedup
ships: until then the format is not in a release, and the documentation site only
describes what a release contains.

A Dedup report identifies its experimental contract with three members:

```json
{
  "format": "tabalyst.dedup",
  "format_version": "0.2.0",
  "format_revision": 1
}
```

The models of `src/tabalyst/dedup/report.py` are the source of truth. The JSON Schema
`src/tabalyst/schemas/tabalyst.dedup.schema.json` is generated from them
(`dedup_schema_text()`) and a test fails when the committed file is stale. A change of
structure or meaning raises `format_revision` and is written here. The format is
experimental during the beta: breaking changes are allowed and no migration is provided.

## Version 0.2.0, revision 1 (2026-10-23)

Starting point of the format. A report describes one source and has three variants,
told apart by `status`:

- `complete`: `generator`, `source` (name, size, `mtime_ns`, SHA-256), `settings`
  (`max_rows`, `delimiter`, `encoding`, `identity`), `records` (the exact counts and
  `extra_copy_percent`), `outputs` (`csv_files_created` and, for each CSV, `null` or its
  file name, rows, size and SHA-256) and `run` (passes, storage mode, durations, memory
  peak or `null`). The counts obey the invariants of design 12.3, which the models check
  when a document is read.
- `failed`: `source` (the name, and the size and `mtime_ns` when they could be read),
  `settings`, `failure` (stable `reason`, `message` without path or cell, `limit` for the
  row limit) and `partial` (`records_read`, `certified` always `false`). It has no
  `records` and no `outputs`.

- `in_progress` (added by lot 7, 2026-10-23, still revision 1: the format has not been
  released, so adding a variant before the first release does not raise the revision):
  the recovery report of design 12.5. It has `generator`, `source` (the name, and the
  size, `mtime_ns` and SHA-256 when the run knew them), `settings` and `recovery` with two
  lists of `{file, size_bytes, sha256}`, `previous_outputs` and `planned_outputs`. It is the
  write-ahead record of a publication: a reader never takes it for a result, and the cache
  never reuses it. It has no `records` and no `outputs`.

A report holds no cell content and no absolute path. After the first release, a change of
structure or meaning of any variant raises `format_revision`.

## Batch report `tabalyst.dedup.batch`, version 0.2.0, revision 1 (2026-10-23)

`dedup.summary.json` (design 13.1) is a second document of the Dedup family. It has its own
`format "tabalyst.dedup.batch"`, the same `format_version` and its own `format_revision`
(1). The models of `src/tabalyst/dedup/batch_report.py` are the source of truth and the
schema `src/tabalyst/schemas/tabalyst.dedup.batch.schema.json` is generated from them
(`batch_schema_text()`), with a test that fails when the committed file is stale.

Members: `generator`, `status` (`complete`, `partial` when some eligible source failed,
`failed` when every one did), `inputs` and `output_dir` (the specs and the destination, relative to
the folder of the report), `counters` (`found`, `eligible`, `excluded`, `done`, `skipped`,
`failed`), `totals` (`processed` and `reused`, each with `sources`, `records`, `extra_copies`
and `duplicate_groups`), `outputs` (`csv_files_created` of this run only, `reports_available`,
`reports_updated`), `duration_seconds`, `sources` (one entry per file found: `file`, `status`
`DONE`, `SKIPPED`, `FAILED` or `EXCLUDED`, `reason`, `verification`, `report`, `records` and
`csv_files_created`) and `diagnostics`. Every member is always present; what does not apply is
`null`. The models check the rules that tie the counters, the tallies and the sources together.

The report holds no cell, no absolute path (the paths are relative to its folder with `/`, or
the bare name on another drive) and no message of an error. After the first release, a change of
structure or meaning raises `format_revision`.
