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
  "format_revision": 5
}
```

`format` names the kind of document; the JSON profile of `tabalyst report` has
its own [changelog](../report/profile-changelog.md). `format_version` names the
experimental compatibility family, `0.1.0a` retained during beta.
`format_revision` is a monotonic integer incremented for each meaningful
structural or semantic change. It does not change for performance improvements,
documentation or corrections that keep the contract.

Beta revisions may be incompatible. No automatic migration is provided.
`tabalyst report --scan` reads the current revision only: scan the source
again to report on an older document.

## Revision 5

- `config` records the rules the scan applied, defaults resolved:
  `errors.policy` is `strict` or `tolerant`, never `null`; the setting itself
  accepts `null`, meaning the default of the source format (`strict` for CSV
  and JSON). `config_sha256` is the hash of that resolved configuration.
- `config.json` gains `flatten` (`enabled`, `separator`, `max_depth`) and
  `arrays` (`mode`). Their defaults keep the previous behavior. When
  `flatten.enabled` is `false`, `separator` and `max_depth` are recorded as
  their defaults, since they change nothing.
- `source.format` can be `jsonl`: files ending in `.jsonl` or `.ndjson` are
  read as one dataset `$[]` whose records are the object lines. Their `tolerant`
  default policy excludes a line that is not valid JSON (`jsonl_invalid_line`),
  is not an object (`jsonl_record_not_object`) or exceeds `limits.max_line_bytes`
  (`jsonl_line_too_long`), with locations `{record, line}`. `scope.collections`
  is `null`. `config.limits` gains `max_line_bytes`.
- The JSON reader applies `flatten`: a container at `max_depth` segments is
  kept whole (type and array length), its children are not observed and are not
  counted as truncated. The field `display` is joined with `flatten.separator`.
- `config.json.collections` is recorded in canonical spelling (`$.orders[]`
  for `$["orders"][]`), so equal paths give equal hashes.
- The datasets of a JSON scan made by `tabalyst scan` or `tabalyst report` come
  from [Inspect](../inspect/format.md): `scope.collections` has `mode` `explicit`
  and there is no `document` dataset `$`. `tabalyst.scan()` alone keeps the
  automatic discovery (`mode` `auto`). The document structure does not change.
- The identity of a scan is its source SHA-256, its `config_sha256` and
  `engine.version`. Another engine version is no longer reused as a stored
  scan, and a source is compared with `source.sha256` whatever its
  modification time; `source.modified_at` stays informative.

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
