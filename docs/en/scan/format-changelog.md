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
  "format_revision": 3
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

## Version 0.2.0, revision 2 (2026-10-10)

Adds `run` (start, duration, timings, workers, peak memory), `source.shape`
(global size of the source), the CSV `quote`, `bom` and `line_ending`, and
diagnostic `details`; `measures_limited` is one diagnostic per field.

Also in revision 2:

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
  A Report keeps the block with a subset of its rows.
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
- `records.preview` is removed: the first records are the start of the
  [row sample](format.md#row-sample), with the same cells. The setting
  `scan.records.preview` is refused with the place of its replacements
  (`scan.records.sample.edge`, and `report.row_sample` for the rows a report
  shows).
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

## Version 0.2.0, revision 3

- `numeric.coverage` (`of`, `share`): the analyzable values (`values.count`)
  the numeric statistics describe. A column of amounts written with a currency
  sign covers only its bare numbers.
- A field that a code detector (`postal_code`, `phone`, `uuid`,
  `ip_address`) reads for at least half of its eligible values, and for at least
  as many values as the numeric block holds, has `numeric` set to
  `not_applicable` with the reason `code_interpretation`: the median of postal
  codes means nothing.
- The observation rules are version 2 and gain `minority_length`.
- Ambiguous numbers such as `1,234` are read in the convention that the other
  numbers of their column prove (at least `detectors.number.min_evidence`, none
  proving the other) and counted in `numeric`; with a decimal comma proven,
  `1.250` counts as 1250. `details.ambiguity.resolution` of `number` names it
  with `source` `evidence`, the `evidence` and the numbers `resolved`. New
  settings `detectors.<id>.infer_convention` and `min_evidence` for `number`,
  `currency`, `percentage` and `quantity`. The Scan counts no number of an amount
  and does not change for the last three: the second pass reads the values with a
  unit by the evidence of their own detector.

## Version 0.2.0, revision 4 (in preparation)

Revision 4 gathers the changes of the hierarchical pattern discovery; it is not
final until the release that ships it.

- Every entry of `derived.patterns` has an `eligibility` (`state`, `score`,
  `reasons`): whether the field is worth a search for patterns, decided before
  any pattern is built (see [Inferred patterns](format.md#inferred-patterns)).
  Only an `eligible` field is inferred. The `reason` of a `not_applicable`
  entry is the first reason that kept the field out; `technical_type` is gone.
- A column of whole numbers of 4 digits or more, such as a register number, is
  now read as text and can have patterns. Shorter whole numbers, decimal
  numbers, free text and a handful of words are `low_relevance`; booleans and
  objects or arrays only are `excluded`.
- `string_characteristics` becomes a [character profile](format.md#character-profile)
  and keeps its nine counters. It adds counters by class of character (ASCII
  lower and upper case letters, other Latin letters, other letters, ASCII and
  other digits), by start (`starts_uppercase`, `starts_lowercase`), by whitespace
  (`with_tabs`, `with_non_breaking_spaces`), by composition (`ascii_only`,
  `letters_only`, `digits_only`, `alphanumeric_only`, `letters_and_digits`) and
  for problem characters (`with_invisible_characters`,
  `with_replacement_character`), the total `characters`, the exact count
  `distinct_characters` and the inventory `special_characters`, both measure
  envelopes. New settings `scan.limits.max_special_characters` (256, 0 turns the
  inventory off) and `max_distinct_characters` (1,024).

- The inferred patterns become a hierarchy of **families** (grammar 2).
  `derived.patterns` has an `algorithm.version` next to its `grammar`, and a
  `complete` entry has `population`, `families`, `other` and `limits` in place of
  `candidates`, `other`, `overlaps` and `limits`. A family gathers the values of
  one structure, or of structures merged at the edge of a block (`AK-1234` with
  `AK-1234X`, listed in `composition`), and lists its `patterns`: one pattern per
  combination of lengths, each of fixed length with its constants folded into the
  signature (`'INV-'999`, `'INV-'9999`). A pattern holding several merged
  structures lists a `nodes` entry for each. Every count is given in distinct
  values (`d`) and occurrences (`o`). `candidates`, `generalization`,
  `merged_structures`, `confidence`, `lengths` and `overlaps` are gone: there is
  no compatibility with the flat list of revision 3.
- The notation of the signatures changes (grammar 2): `A` a capital, `a` a
  lowercase letter, `@` a letter of either case, `X` a capital or a digit, `x` a
  lowercase letter or a digit, `#` an ASCII letter or a digit, `9` a digit. The
  token kinds `upper_digit` and `lower_digit` are new, and `alphanumeric` no
  longer reads non-ASCII letters.
- A structure with one value is a family of its own, and the generalization of
  the smallest structures into wider ones is gone. A combination of lengths
  that `max_patterns_per_family` keeps out of a family is counted in a `lengths`
  table of that family.
- `scan.pattern_inference` has new settings: `max_values` (10,000, at most
  20,000), `max_families` (16), `max_patterns_per_family` (32), `max_depth` (3, at
  most 4); `max_patterns` now counts the patterns and nodes of a field (128, at
  most 1,024).
- The nodes of a pattern are no longer only the structures of a composition. A node
  has a `facet` (`composition`, or `head:N`, `tail:N` and `token:N` for the first
  or last characters of a token and a whole token), a `gain` (`bits_d`, `bits_o`,
  `sigma`) for a node of content, and its own `nodes` (a longer prefix, or a facet
  that depends on it). A facet of content that no node reads is a table of the
  family (`tables`, with the same `facet` names and the `gain` of the facet); the
  cells and `others` of a table add up to the family. A pattern folds at most three
  characters of a token as a constant, unless every value repeats the token. The
  limit `max_depth` names the setting of the same name when the tree was cut.
