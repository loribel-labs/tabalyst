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
- `values.samples` is the sample of the original values (not the analytical
  ones): `selection` is `all` (every distinct value, first-seen order) or
  `bottom_k` (the `k` values of smallest hash priority, with `k`, `hash`
  and `threshold`), which replaces `uniform_distinct` and `first_seen`. Each
  entry gains `id`, `count_accuracy` and `identity_accuracy`. For a sensitive
  field `kept` can be below `of`.
- `values.cardinality.estimate`: the KMV estimate of the distinct count of a
  limited field (`accuracy` `estimated`), when the sample saw the whole field.
- `scan.random_seed` is an integer from 0 to 2^64 - 1.
- The JSON Schema of the document and a validator of its invariants are part of
  the package (see [Scan format](format.md#json-schema)).
- `values.samples` has `kept` and `of`: the number of values it lists and the
  number the scan sampled. A scan has both equal; a
  [report](../report/json-profile.md#reduced-samples) keeps fewer.
