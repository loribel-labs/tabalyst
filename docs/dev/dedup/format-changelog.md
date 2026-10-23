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

Starting point of the format. A report describes one source and has two variants,
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

The `in_progress` variant (recovery report, design 12.5) is added with the ownership of the
outputs, in lot 7. A report holds no cell content and no absolute path.
