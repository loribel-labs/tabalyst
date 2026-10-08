---
title: JSON profile changelog
description: Current format version and revisions of the JSON profile written by tabalyst report.
---

The JSON profile written by `tabalyst report` identifies its experimental
contract with two fields:

```json
{
  "format": "tabalyst.report",
  "format_version": "0.2.0",
  "format_revision": 2
}
```

`format` identifies the document kind: a report is a
[scan document](../scan/format.md) with a `report` block. `format_version` names the compatibility family. `format_revision` increases
for a meaningful structural or semantic change within that family. Styling,
documentation, performance improvements and corrections that preserve the
JSON contract do not change it. Beta revisions may be incompatible; automatic
migration is not provided.

## Version 0.2.0, revision 1 — 2026-10-06

This is the starting point for the current [JSON profile](json-profile.md).
It describes the existing Report profile, including CSV, JSON, JSONL and Excel
sources, effective settings, dataset summaries, column analysis, normalization,
detectors, issues, record previews, limits and JSON structure.

## Version 0.2.0, revision 2

The profile becomes a superset of the Scan document: it has `format:
"tabalyst.report"` and holds the scan base at the same paths (`engine`,
`status`, `run`, `source`, `config`, `config_sha256`, `scope`, `datasets`,
`diagnostics`), plus a `report` block.

- The report's own data moves under `report`: `generated_at`,
  `processing_seconds`, the presentation settings (`report.config`, with only
  `string_analysis` and `value_examples`, the `report` object of the
  configuration files; the root `config` is the scan configuration), `base_scan` (identity of the base) and the projections
  (`report.datasets`, with the summary, columns, issues, preview, limits and
  structure of each dataset). The root `datasets` are the scan datasets.
- `source` is the scan's: `filename` becomes `name`, `delimiter` is
  `source.csv.delimiter` (`null` `csv` for other sources).
- The column copies of scan facts are removed: `scan_details`, `numeric`,
  `string_profile` and `date_profile`. They are read from the fields of the
  base.
- The samples of the base are reduced and declare `kept` and `of`. How many
  values the report keeps per column is a presentation setting,
  `report.config.value_examples.kept_per_column` (1 to 1,000, 100 by default).
- A report carries the optional `derived` member of its scan, the
  [inferred patterns](../scan/format.md#inferred-patterns), as it is: the
  reduced samples cannot compute them again.
