---
title: Scan format changelog
description: How a scan document written by tabalyst scan identifies its format, and the changes of each format revision.
---

A scan document written by `tabalyst scan` identifies its contract with three
fields:

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.1.0a",
  "format_revision": 4
}
```

`format` names the kind of document; the JSON profile of `tabalyst report` has
its own [changelog](profile-format-changelog.md). `format_version` names the
experimental compatibility family, `0.1.0a` throughout the alpha.
`format_revision` is a monotonic integer incremented for each meaningful
structural or semantic change. It does not change for performance improvements,
documentation or corrections that keep the contract.

Alpha revisions may be incompatible. No automatic migration is provided.
`tabalyst report --scan` reads the current revision only: scan the source
again to report on an older document.

## Revision 4

- Rare detectors: after the warm-up, a detector that recognized at most
  `detection.rare_share` of its distinct values (default 0.001, 10 values of
  a 10,000-value warm-up), and none of those in its second half, is skipped
  too, like a detector that recognized nothing. A sensitive detector that
  found only invalid values is never skipped this way. Set
  `detection.rare_share` to `0` for the behavior of revision 3.
- `adaptive` gains `warmup_reactions`: the warm-up values the detector
  recognized, `0` for a detector that recognized nothing.
- A skipped rare detector reports `detector_skipped_reacted` when at least 10
  probed occurrences were recognized, more often than `rare_share` allows.
- New setting in `config`: `detection.rare_share`.

## Revision 3

- Adaptive detection: after the first `detection.warmup_values` distinct
  values of a field (default 10,000), a detector that recognized none of them
  skips the other values of the field, except about one in
  `detection.probe_interval` (default 100). Skipped values count as
  `not_tested`. `number` and `date` are never skipped. Set
  `detection.warmup_values` to `0` for the exhaustive detection of revision 2.
- Each `complete` detector result gains `adaptive`: `null`, or the warm-up
  size, the values not tested and the index of a new
  `detector_skipped_reacted` warning when a probe was recognized.
- New settings in `config`: `detection.warmup_values` and
  `detection.probe_interval`.

## Revision 2

- Each dataset gains `records`: records with missing values, empty records,
  duplicate records and a preview of the first records, sensitive values
  exposed as in the rest of the document.
- Duplicate records are counted within the budget of the new
  `limits.max_tracked_records` setting; beyond it, the count is a lower bound
  with reason `record_budget`, and a `record_budget` warning is reported.
- New settings in `config`: `records.preview`, `records.duplicates`,
  `limits.max_tracked_records` and `limits.max_listed_records`.

## Revision 1

- First published scan format, written by `tabalyst scan`.
- Top level: engine and detector versions, scan status, source identity with
  size, modification time and SHA-256, effective configuration and its
  SHA-256, scope and diagnostics.
- CSV and JSON datasets, with fields identified by paths, exact presence,
  native types, string categories and a configurable missing count.
- Value measures: cardinality, frequencies, samples, first and last values,
  string characteristics and lengths, exact numeric statistics, booleans and
  dates, wrapped in measure envelopes when they can be limited.
- Normalization version 1 with change counters, distinct values per stage and
  variant groups.
- Technical type, thirteen built-in detectors, declarative patterns,
  interpretations and the masking of sensitive values.
