---
title: JSON profile changelog
description: Current format version and revisions of the JSON profile written by tabalyst report.
---

The JSON profile written by `tabalyst report` identifies its experimental
contract with two fields:

```json
{
  "format_version": "0.2.0",
  "format_revision": 1
}
```

`format_version` names the compatibility family. `format_revision` increases
for a meaningful structural or semantic change within that family. Styling,
documentation, performance improvements and corrections that preserve the
JSON contract do not change it. Beta revisions may be incompatible; automatic
migration is not provided.

## Version 0.2.0, revision 1 — 2026-10-06

This is the starting point for the current [JSON profile](json-profile.md).
It describes the existing Report profile, including CSV, JSON, JSONL and Excel
sources, effective settings, dataset summaries, column analysis, normalization,
detectors, issues, record previews, limits and JSON structure.
