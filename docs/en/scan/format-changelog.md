---
title: Scan format changelog
description: Current format version and revisions of the JSON document written by tabalyst scan.
---

A scan document written by `tabalyst scan` identifies its experimental
contract with three fields:

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.2.0",
  "format_revision": 1
}
```

`format` identifies the document kind. `format_version` names the compatibility
family, and `format_revision` increases for meaningful structural or semantic
changes within it. The [JSON profile](../report/profile-changelog.md) has its
own version and changelog. Beta revisions may be incompatible; automatic
migration is not provided. `tabalyst report --scan` reads the current Scan
version only: scan the source again to use an older document.

## Version 0.2.0, revision 1 — 2026-10-06

This is the starting point for the current [Scan format](format.md). It
describes CSV, JSON, JSONL and Excel sources, their effective configuration,
datasets, fields, detectors, record facts, limits and diagnostics.
