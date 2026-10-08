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
- Values longer than `scan.limits.max_stored_value_length` have their own small
  sample, `values.samples.long_texts`: a bounded preview, the original lengths,
  `truncated` and a digest of the complete text, with `fingerprint_based`
  identity (see [Long texts](format.md#long-texts)). They are no longer excluded
  from the cardinality estimate, which adds the stored values and the long
  texts (`estimate.parts`; `k` and `theta_hex` move into the parts). New limits:
  `max_long_samples` (100), `long_preview_chars` (200) and `max_sample_memory`
  (512 MiB).
- The samples have a memory budget: `values.samples` and `long_texts` can carry
  `requested_k` and `reason` `memory_budget` when a size was cut, and the scan
  adds the warning `sample_budget` (see
  [Sample sizes](format.md#sample-sizes-and-the-memory-budget)). A CSV batch of
  rows and a batch of streamed values are also bounded by size.
- A `bottom_k` sample is completed by `values.samples.by_length`: a small
  bottom-k of the values of each length, so a rare length stays visible, with
  the lengths and values beyond the limits summed in `other` (see
  [Samples by length](format.md#samples-by-length)). New limits:
  `max_samples_per_length` (100) and `max_length_strata` (64); `count_accuracy`
  can now be `partial`, for a length tracked after its first occurrence. The
  warning `sample_budget` and the sizes in force cover them too.
- Each dataset has a row sample, `records.sample`: the first and last rows and a
  reproducible choice of rows of the interior, with the cells of the same record for every
  projected field (see [Row sample](format.md#row-sample)). New settings
  `records.sample.rows` (1,000), `edge` (50), `cell_chars` (200) and `max_bytes` (16 MiB).
  `records.preview` is unchanged. A Report keeps the block without its rows.
- `derived.patterns` (optional): the structural patterns inferred from the
  samples of each text field, with their signature, rendering, coverage of the
  distinct values, overlaps and what was excluded (see
  [Inferred patterns](format.md#inferred-patterns)). New settings
  `scan.pattern_inference.enabled`, `max_patterns`, `max_value_length` and
  `min_distinct`. `run.timings` gains `derived`. A field on which the inference
  raises gets a `failed` entry and a `pattern_inference_failed` error.
- `observations` (optional): the findings of the scan about the data, apart
  from its limits, with a status (`informational`, `candidate_anomaly`,
  `confirmed_issue`), summaries and the flags `has_observations`,
  `has_quality_issues` and `has_limits` (see
  [Observations and limits](format.md#observations-and-limits)). New settings
  `scan.observations.enabled` and `max_items`. `run.timings.derived` includes
  them. A failure raises an `observations_failed` error and leaves the member
  out.
- A normalization stage that changed nothing has `equals`, the stage whose
  count it takes, and keeps that count even when the table of distinct values
  was released; `variant_groups` is complete and empty when no stage changed
  any string (see [Normalization stages](format.md#normalization-stages)).
- `run.counters` (optional): the work of the samplers, written by
  `tabalyst scan --counters`.
- The scan document is written without indentation by default; the new
  `output.json_indent` setting restores indentation (see
  [Writing the document](format.md#writing-the-document)). The content does
  not change.
- The JSON Schema of the document and a validator of its invariants are part of
  the package (see [Scan format](format.md#json-schema)).
- `values.samples` has `kept` and `of`: the number of values it lists and the
  number the scan sampled. A scan has both equal; a
  [report](../report/json-profile.md#reduced-samples) keeps fewer.
