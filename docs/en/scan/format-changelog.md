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
  "format_revision": 2
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

## Version 0.2.0, revision 2

Adds `run` (start, duration, timings, workers, peak memory), `source.shape`
(global size of the source), the CSV `quote`, `bom` and `line_ending`, and
diagnostic `details`; `measures_limited` is one diagnostic per field.

Also in revision 2, before its release:

- `values.cardinality` names its `domain` (`original`), its `accuracy` and its
  `identity_accuracy`. A limited count adds `upper_bound` and, for the reason
  `distinct_limit`, `threshold_reached_at_record` and
  `overflow_detected_at_record`.
- `scan.limits.max_samples` is the size of the sample the scan keeps per field:
  10,000 by default (100 before), at most 100,000 and at most
  `max_distinct_per_field`. The effective value is in `config`.
- `values.samples.selection` may be `bottom_k`, with the members `k`, `hash`
  and `threshold`: reserved, never written yet.
- The JSON Schema of the document and a validator of its invariants are part of
  the package (see [Scan format](format.md#json-schema)).
