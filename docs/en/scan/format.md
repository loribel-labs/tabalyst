---
title: Scan format
description: Structure of the JSON document written by tabalyst scan, with its top level, datasets, fields, measure envelopes, detectors and diagnostics.
---

`tabalyst scan data.csv` writes a reusable `scan.json` by default;
`-o` and `-d` export a standalone `<stem>.scan.json`. Both are JSON documents that
describe every field of the source. This page describes format
`tabalyst.scan`, version `0.2.0`, revision `3`. The format is
**experimental**: it can change incompatibly between releases. Always check
`format`, `format_version` and `format_revision` first; changes are listed in
the [scan format changelog](format-changelog.md).

## Top level

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.2.0",
  "format_revision": 3,
  "engine": {
    "version": "0.7.0",
    "normalization_version": 1,
    "detectors": {"number": 1, "date": 1, "email": 1, "...": 1}
  },
  "status": "complete",
  "run": {
    "started_at": "2026-10-06T12:00:00Z",
    "duration_seconds": 0.0023,
    "timings": {
      "reading": 0.0009,
      "analysis": 0.001,
      "finalize": 0.0003,
      "derived": 0.0,
      "other": 0.0001
    },
    "workers": 1,
    "peak_memory_bytes": 58720256
  },
  "source": {
    "format": "csv",
    "name": "orders.csv",
    "size_bytes": 63,
    "modified_at": "2026-09-27T05:06:40.930099Z",
    "sha256": "fe7a56e5...",
    "encoding": "utf-8-sig",
    "shape": {
      "lines": 4,
      "records": 3,
      "columns": 3,
      "fields": 3,
      "datasets": 1,
      "cells": 9,
      "missing_cells": 0,
      "records_with_missing": 0,
      "empty_records": 0,
      "duplicate_records": 0
    },
    "csv": {
      "delimiter": ",",
      "quote": "\"",
      "header": ["id", "amount", "email"],
      "bom": true,
      "line_ending": "lf"
    }
  },
  "config": {"...": "effective scan configuration"},
  "config_sha256": "030617af...",
  "scope": {
    "collections": null,
    "records_read": 3,
    "records_analyzed": 3,
    "records_excluded": 0,
    "exclusions": {}
  },
  "datasets": [],
  "diagnostics": []
}
```

- `engine`: the Tabalyst version, the normalization version and the version of
  each detector that ran.
- `status`: `complete` when every record in scope was analyzed, `partial` when
  records were excluded under the `tolerant` error policy. A file that cannot
  be read produces no document.
- `run`: what varies from one run to the next on the same source, kept apart
  from the description of the data. `started_at` and `duration_seconds` give
  the time and the processing time. `timings` splits the duration in seconds:
  `reading` (reading and parsing the source, hashing included), `analysis`
  (analysis of the values; with several workers, the time the main process
  spends on it, waiting included), `finalize` (final computation of the
  datasets), `derived` (the [inferred patterns](#inferred-patterns) and the
  [observations](#observations-and-limits)) and
  `other` (setup and assembly of the result); the five parts add
  up to `duration_seconds`. `workers` is the number of processes that analyzed
  values (1 in the main process). `peak_memory_bytes` is the peak memory of the
  main process, workers excluded, when the scan ended: it covers the whole
  process and is `null` when the platform does not report it.
- `source`: the file as read. `size_bytes` and `sha256` cover every byte read.
  `encoding` is the CSV encoding, or `utf-8` or `utf-8-sig` for JSON, and
  `null` for an Excel workbook. `shape` gives its global size: `lines`
  (physical lines of a CSV file, header and multi-line cells included, `null`
  for other formats), `records` analyzed, `columns` of a CSV or Excel table
  (`null` for JSON and JSONL), `fields` and `datasets` found, and `cells`
  (`records` times `columns`, `null` for JSON and JSONL), `missing_cells`,
  `records_with_missing`, `empty_records` and `duplicate_records` (`null` when
  a count is limited or disabled), summed over the datasets. `csv` is `null` for sources that are not CSV.
  `csv` also gives the `quote` character, whether the file starts with a UTF-8
  byte order mark (`bom`) and its `line_ending` (`lf`, `crlf`, `cr`, `mixed`, or
  `null` without any line break). `excel` is `null` unless the source is a workbook: it gives the table read,
  as described [below](#excel-sources).
- `config`: the complete effective configuration, with every default, as in
  the `scan` section of a [configuration file](../reference/configuration.md#scan-settings).
  `config_sha256` is the SHA-256 of its canonical JSON (sorted keys, no
  whitespace, UTF-8): two scans with the same value used the same settings.
- `scope`: records read, analyzed and excluded, with exclusions counted by
  reason (`width_mismatch`, `duplicate_key`, `record_too_large`, and for JSONL
  `invalid_line`, `not_object` and `line_too_long`).
  `collections` is `null` for CSV, JSONL and Excel; for JSON it gives the `mode`
  (`auto` or `explicit`) and the `requested` collection paths.

## Excel sources

A workbook is read one table at a time, the one `config.excel.dataset_path`
names. `source.excel` records which:

```json
"excel": {
  "dataset_path": "$.Orders",
  "sheet": "Orders",
  "table": null,
  "range": "A4:I124",
  "header_row": 4,
  "header": ["order_id", "order_date", "customer"]
}
```

`dataset_path` is `$.Sheet` or `$.Sheet.Table`; `table` is the name of a named
table, or `null` for a sheet. `range` is the A1 range of the header and the data
actually read, `header_row` the 1-based sheet row of the header, and `header` the
header cells, which name the fields. The records are the filled rows under the
header, with `location.line` the 1-based sheet row. Values keep their Excel
type: whole numbers are `integer`, other numbers `number`, booleans `boolean`;
dates and times are `string` values in ISO 8601 that the date detector
recognizes. `config.excel` holds `dataset_path` and `header_row`, and takes part
in `config_sha256`.

## Datasets

A CSV source has one dataset, `rows`, and so has an Excel source: its table.
A JSON source has one dataset per
collection of records, and one `document` dataset when its root is not an
array and the collections were discovered automatically (`mode` `auto`). A
JSONL source has one dataset, `$[]`. The commands choose the collection with
[Inspect](../inspect/json.md) and name it explicitly, so a scan
made by `tabalyst scan` or `tabalyst report` has `mode` `explicit` and no
`document` dataset; only `tabalyst.scan()` without `json.collections` discovers
collections.

```json
{
  "id": "$.customers[]",
  "kind": "collection",
  "collection_path": [{"key": "customers"}, {"items": true}],
  "record_count": 4,
  "record_types": {"object": 4},
  "structure": {
    "paths": {"status": "complete", "value": 5},
    "untracked_observations": 0,
    "depth_truncated_observations": 0,
    "max_depth_seen": 3
  },
  "records": {"...": "record facts, described below"},
  "fields": []
}
```

- `kind`: `table` (CSV and Excel), `collection` or `document` (JSON).
- `record_count`: analyzed records; `record_types`: records per JSON type.
- `structure`: the number of distinct field paths, and what the `max_fields`
  and `max_depth` limits left out.
- `records`: facts about whole records, described in the next section.

## Records

Each dataset describes its records as a whole: records with missing values,
empty records, duplicate records and a sample of whole rows.

```json
{
  "with_missing": {"count": 2, "records": [2, 5]},
  "empty": {"count": 1, "records": [5]},
  "duplicates": {
    "count": {"status": "complete", "value": 1},
    "records": [3]
  }
}
```

- The values of a record are its strings, numbers, booleans and nulls: every
  cell of a CSV row. A JSON field absent from a record is not a value of it.
- `with_missing`: records with at least one missing value, under the
  `values.missing` setting. `empty`: records whose values are all missing.
- `duplicates`: records equal to an earlier record of the same dataset,
  beyond its first occurrence. Records are equal when every value, its field
  and its native type are equal, raw values compared, before normalization.
  `count` is a measure envelope: `limited` with reason `record_budget` when
  more distinct records than `limits.max_tracked_records` were read, its
  `lower_bound` being the duplicates found; `disabled` when
  `records.duplicates` is `false`.
- `records` lists record numbers, at most `limits.max_listed_records` of
  them. Record numbers are those of `first_record` and diagnostics.
- `sample`: the [row sample](#row-sample), absent when `records.sample.rows` is 0.
  It holds the first records, with their values per field identifier, as text.

### Row sample

`records.sample` keeps whole rows of the dataset, taken in the same pass: the first
`edge` records, the last `edge` records and, between them, a random but reproducible
choice of the others. Every row has the cells of the same record for all the projected
fields, so a later analysis can relate the values of two fields.

```json
{
  "selection": "start_middle_end",
  "hash": {"algorithm": "blake2b", "version": 1, "bits": 64, "seed": 42},
  "requested": {"rows": 1000, "edge": 50, "middle": 900},
  "middle_k": 900,
  "population": {"records": 3000, "interior": 2900, "scope": "interior_rows"},
  "complete": false,
  "threshold": "4e361452e3b67ee0",
  "fields": ["column_1", "column_2"],
  "fields_limited": false,
  "cell_chars": 200, "truncated_cells": 0,
  "bytes": 2477121, "max_bytes": 16777216,
  "kept": 1000, "of": 1000,
  "rows": [
    {"record": 1, "origins": ["start"],
     "values": {"column_1": ["a"], "column_2": ["1"]}}
  ]
}
```

- `requested`: the sizes asked for. `rows` is the total, `edge` the number of rows at
  each end and `middle` the rest, `rows` - 2 * `edge`.
- A row has the `record` number, its `origins` (`start`, `middle`, `end`; a record that is
  both at the start and at the end of a short dataset is listed once with `["start", "end"]`)
  and its `values`: text per field identifier, the values of a repeated path listed in
  order, a JSON null as `null`, `null` for a hidden cell, no key for a field absent from
  the record. Empty strings, blanks and null markers are shown as read. Rows are in source order within each group: start, middle, end.
- The middle is drawn from the interior only, records `edge` + 1 to the number of records
  minus `edge` (`population.interior`, `scope` `interior_rows`). It is not a uniform sample
  of the whole dataset: do not add the edges to an estimate over the whole dataset. The
  choice depends on the position of a record, never on its content (two identical records
  are two observations), on the `random_seed` and on the version of the hash, so the same
  source and configuration give the same rows with any number of workers.
- `complete` is true when every record is a row, which is the case for a dataset of at
  most `rows` records. `threshold` is the largest priority kept in the middle, written
  when some records of the interior were not kept.
- A cell is cut at `cell_chars` characters (all the values of a repeated path together).
  The row names the cut fields in `truncated` and `truncated_cells` counts them: a row with
  a cut or hidden cell cannot serve a relation on that field. `fields` lists the projected
  fields; `fields_limited` is true when `limits.max_fields` left some paths untracked.
- Sensitive values go through the exposure of their field: a cell holding a hidden
  value is `null`.
- `bytes` is the size of the rows by a cost model, and `max_bytes` the budget of the whole
  scan (`records.sample.max_bytes`). When the budget is exceeded, the middle shrinks first
  (`middle_k` below `requested.middle`), then the start and the end keep what fits, and the
  block says `reason` `memory_budget`.
- A Report keeps this block with the rows `report.row_sample` asks for (10 at the start,
  10 sampled and 10 at the end by default): `kept` says how many it lists and `of` how many
  the scan sampled.

## Fields

Fields are listed in order of discovery. A field is a path inside the records:
a CSV column, a JSON key, or the elements `[]` of an array.

| Key | Content |
| --- | --- |
| `id`, `path`, `display`, `name`, `parent` | Identity: an identifier such as `f4`, the path as segments, its readable form such as `orders[].amount` (keys joined with `json.flatten.separator`), the last segment and the parent field identifier. |
| `collection` | For a JSON array promoted to its own dataset, the identifier of that dataset. |
| `first_record`, `occurrences` | The first record with a value, and the number of values at this path. |
| `presence` | `parent_count`, `present` and `absent`: how often the field exists where it could exist. |
| `native_types` | Values per native type: `string`, `integer`, `number`, `boolean`, `null`, `object`, `array`. |
| `strings` | Strings per category: `empty`, `blank` (whitespace only), `marker` (a configured null marker) and `content`. |
| `missing` | The missing count, the categories included in it and each component. |
| `arrays` | For array fields: count, empty arrays, minimum, maximum and total length. |
| `values` | Analyzable values: `count`, `cardinality`, `frequencies`, `samples`, `first` and `last`. |
| `string_characteristics`, `string_lengths` | The [character profile](#character-profile): case, character classes, composition, whitespace, invisible characters, special characters and distinct characters; length statistics and histogram. |
| `numeric`, `booleans`, `temporal` | Exact numeric statistics, boolean counts, date range and formats. Numbers that a column proves to use one decimal convention include its ambiguous ones (see [Detectors](#detectors)). `numeric.coverage` gives the share of the analyzable values the statistics describe; a field that a code detector reads (`postal_code`, `phone`, `uuid`, `ip_address`) has no `numeric` block (`not_applicable`, reason `code_interpretation`). |
| `normalization` | For each normalization stage, how many values it changed and the distinct values left, plus groups of variants that normalize to the same value (see [Normalization stages](#normalization-stages)). |
| `technical_type` | `integer`, `number`, `date`, `boolean`, `text`, `mixed` or `empty`, with `confidence`, `counts` and `outside_count`. |
| `detectors` | One result per detector, described below. |
| `interpretations` | `candidates`, the detectors that matched at least 95% of the values, and `primary`, the only candidate when there is exactly one. |
| `sensitive`, `exposure` | Whether the field holds sensitive values, and how they are exposed: `mask`, `hide`, `show`, or `null` for other fields. |

Values are listed as their text with their native type, for example
`{"value": "12.50", "type": "string", "count": 1}`. Listings use the analytical
value: surrounding whitespace is trimmed and repeated spaces are collapsed.

## Measure envelopes

A measure that can be limited, disabled or inapplicable is wrapped in an
envelope with a `status`:

```json
{"status": "complete", "value": 42}
{"status": "limited", "reason": "distinct_limit",
 "limit": 100000, "lower_bound": 100001}
{"status": "not_applicable", "reason": "no_values"}
{"status": "disabled"}
{"status": "failed", "reason": "detector_error", "diagnostic": 3}
```

- `complete`: exact for its population.
- `limited`: a configured limit stopped the measure. `lower_bound`, when
  present, is a proven minimum; no estimate is ever given as a value.
- `not_applicable`: meaningless here, for example without values.
- `disabled`: turned off by configuration, or hidden because the field is
  sensitive.
- `failed`: a technical failure; `diagnostic` is its index in `diagnostics`.

A scan can be `complete` while some of its measures are `limited`: the scan
status is about records, the envelope about one measure.

## Distinct values and samples

`values.cardinality` counts the distinct values of a field in the original
domain: the values as decoded, before any normalization stage, so `00123`,
`123` and ` 123 ` are three values. It is an envelope with more members than
the others:

```json
{"status": "complete", "value": 3, "accuracy": "exact",
 "domain": "original", "identity_accuracy": "exact"}
{"status": "limited", "reason": "distinct_limit", "limit": 100000,
 "lower_bound": 100001, "domain": "original",
 "identity_accuracy": "exact", "upper_bound": 250000,
 "threshold_reached_at_record": 100000,
 "overflow_detected_at_record": 100001}
```

- `domain`: what is counted. `original` is the only domain a scan writes.
- `accuracy` of a `complete` count is `exact`. A `complete` envelope without
  `accuracy`, as in the other measures, is exact for its declared population.
- `identity_accuracy`: how two values are told apart. `exact` means that equal
  values are compared whole, never by a digest.
- `upper_bound`: the certain maximum of a `limited` count, the number of
  analyzed values of the field (`values.count`).
- `threshold_reached_at_record` and `overflow_detected_at_record`: for the
  reason `distinct_limit`, the records (numbered like `first_record`) where the
  table reached `scan.limits.max_distinct_per_field` distinct values and where
  one more was proven. A record with several values of the field counts once.
  They are absent for the other reasons and when a member is unknown: an
  absent member is never `null` and never zero.

When the table of distinct values is released, `values.cardinality` may carry
an `estimate` of the distinct count, from the sample described below:

```json
"estimate": {"accuracy": "estimated", "method": "kmv", "value": 187500.0,
             "relative_standard_error": 0.01, "k": 10000,
             "theta_hex": "0000a3f1..."}
```

- `accuracy` is `estimated`: the value is a statistical estimate, never an
  exact count. `relative_standard_error` is its expected relative error (about
  1% at `k` 10,000).
- `value` is held within the certain bounds `lower_bound` and `upper_bound`;
  `unclamped_value` is the raw estimate, present only when a bound changed it.
- `theta_hex` is the threshold of the sample (see `threshold` below). It is
  absent for a sensitive field.
- A field with [long texts](#long-texts) has two domains, the stored values and
  the long texts, which the estimate adds. `parts` gives each one as
  `{domain, accuracy, value, relative_standard_error, k, theta_hex}`: `accuracy`
  is `exact` for a domain whose sample dropped nothing (no `k` or `theta_hex`)
  and `estimated` otherwise. `relative_standard_error` is that of the sum, and
  `k` and `theta_hex` are then in the parts, not in the estimate itself.
- There is no estimate when a value fitted no sample because the
  [memory budget](#sample-sizes-and-the-memory-budget) granted a size of 0.

`values.samples` lists distinct original values with their exact counts, each
entry as `{id, value, type, count, count_accuracy, identity_accuracy}`:

- `selection` is `all` when the sample lists every distinct value of the field
  (at most `scan.limits.max_samples` of them, 10,000 by default), in the order
  they were first seen.
- Otherwise `selection` is `bottom_k`: the `k` values of smallest priority, in
  ascending priority. The priority of a value is a stable hash of its type and
  its text (`hash`: `algorithm`, `version`, `bits` and `seed`, which is
  `scan.random_seed`), so the sample depends on the set of distinct values and
  on `k`, not on the order of the records, on the reading in batches or on the
  workers. `threshold` is the largest priority kept, as hexadecimal digits,
  present once a value was dropped.
- Counts are exact for the whole field (`count_accuracy` is `exact`): a value
  of the sample was counted from its first occurrence. They are not a ranking:
  the most frequent value can be absent, and the counts of a sample do not
  describe the other values.
- `id` numbers the entry in the listing of the scan. A report that keeps some
  of the entries keeps their `id`.
- Values are in the original domain (`00123`, `123` and ` 123 ` are three
  entries), unlike `values.frequencies`, which lists analytical values.
- `kept` is the number of entries listed and `of` the number of original
  values sampled. A scan writes both equal, except for a sensitive field:
  exposure applies after the calculation, `mask` merges the values with the
  same mask and `hide` lists none, so `kept` is below `of` and the originals
  cannot be recovered from the document. A
  [report](../report/json-profile.md#reduced-samples) that holds the scan as its
  base also keeps fewer values and says so with `kept` below `of`.

`max_samples` cannot exceed `max_distinct_per_field`; when it is not set it
follows a lower `max_distinct_per_field`.

### Long texts

A value longer than `scan.limits.max_stored_value_length` (1,000 characters by
default) is never stored. It is counted and measured like any value, and a small
sample of such values is written in `values.samples.long_texts`, absent for a
field that has none:

```json
"long_texts": {"selection": "bottom_k", "k": 100, "preview_chars": 200,
               "occurrences": 36143, "kept": 100, "of": 100,
               "digest": {"algorithm": "blake2b", "bits": 128},
               "hash": {"algorithm": "blake2b", "version": 1, "bits": 128, "seed": 0},
               "threshold": "00a1f3...",
               "listed": [{"id": 0, "digest": "c2f3e568...", "type": "string",
                           "preview": "data customer contract...", "truncated": true,
                           "original_length_chars": 1520, "original_length_bytes": 1520,
                           "count": 2, "count_accuracy": "exact",
                           "identity_accuracy": "fingerprint_based"}]}
```

- `occurrences` counts every occurrence of a long value, exactly. The minimum,
  maximum, total and mean lengths are in `string_lengths`.
- An entry keeps a `preview` (the first `scan.limits.long_preview_chars`
  characters, 200 by default, cut on a character), the original lengths in
  characters and bytes, `truncated` (the preview is shorter than the text) and
  the `digest` of the complete text. Two texts with the same beginning are two
  entries. The preview says nothing certain about the pattern or the alphabet of
  the whole text.
- `identity_accuracy` is `fingerprint_based`: two texts are the same entry when
  their 128-bit digests are equal, not when the full texts were compared.
- `selection`, `k`, `hash` and `threshold` work as for the values: `all` while no
  text was dropped, then `bottom_k`. The sample holds at most
  `scan.limits.max_long_samples` texts (100 by default; 0 keeps none, and the
  occurrences are still counted).
- The listing of the values (`selection`, `kept`, `of`) describes the values
  that fit the stored length only.
- For a sensitive field the block lists nothing (`kept` is 0, `of` is not): a
  preview and a digest are the value itself.

### Samples by length

A `bottom_k` sample favors the lengths that most values have: a length that few
values share can be absent from it. `values.samples.by_length` completes it with
a sample for each length, so a rare length stays visible. It is written for a
field whose sample is `bottom_k` and absent when the sample lists every value
(`selection` `all`), or when `scan.limits.max_samples_per_length` is 0:

```json
"by_length": {"domain": "original", "unit": "characters",
              "per_length_k": 100, "max_lengths": 64, "limited": false,
              "tracked": 3,
              "strata": [
                {"length": 4, "selection": "all", "kept": 2, "of": 2,
                 "occurrences": 5, "count_accuracy": "exact",
                 "ids": [10210, 10211]},
                {"length": 8, "selection": "bottom_k", "kept": 100, "of": 100,
                 "occurrences": 999990, "count_accuracy": "exact",
                 "threshold": "0004c1...", "ids": [3, 8, 11, "..."]}
              ],
              "listed": [{"id": 10210, "value": "abcd", "type": "string",
                          "count": 3, "count_accuracy": "exact",
                          "identity_accuracy": "exact"}]}
```

- `domain` is `original` and `unit` is `characters` (code points of the original
  text): the length of `00123` is 5, whatever the normalization.
- A stratum is a bottom-k of the values of one length, with at most
  `per_length_k` values (`scan.limits.max_samples_per_length`, 100 by default).
  It uses the same priority as the sample, so a value that is in both is the
  same entry. `occurrences` is the exact number of occurrences of that length,
  `of` the values sampled and `kept` those listed; `selection` is `all` while
  the stratum dropped no value, and `threshold` works as for the sample.
- A stratum lists the `id` of its values. A value that is already in
  `samples.listed` is not copied: only the others are in `by_length.listed`,
  whose ids continue the numbering of `samples.listed`.
- Counts are exact (`count_accuracy` `exact`) for a length tracked from its
  first occurrence, as for the sample. A length admitted later has
  `count_accuracy` `partial` and `tracking_started_at_occurrence`: its counts
  cover the occurrences from that one on, and no frequency of it is exact. A scan
  tracks every length from its first occurrence, so it writes `exact` today.
- At most `scan.limits.max_length_strata` lengths (64 by default) are tracked per
  field, the first met. The others are summed in `other`: `{"lengths": 32,
  "occurrences": 96}`, the number of untracked lengths and their occurrences,
  and `limited` is `true`. The strata and `other` add up to the stored values
  of the field. The minimum, maximum and mean lengths stay exact in
  `string_lengths`.
- Values longer than `scan.limits.max_stored_value_length` are not in the strata:
  they have [their own sample](#long-texts).
- For a sensitive field the strata keep their `length`, `of` and `occurrences`
  and list nothing (`kept` is 0, `ids` is empty, no `threshold`).
- A [report](../report/json-profile.md#reduced-samples) keeps the strata
  without their values: `kept` is 0.
- `scan.limits.max_samples_per_length` and `max_length_strata` at 0 turn the
  samples by length off. Both are in the [configuration](../reference/configuration.md).

### Sample sizes and the memory budget

The scan limits the memory its samples may take with a model of their cost, not
by measuring (`scan.limits.max_sample_memory`, 512 MiB by default). Sizes are
reserved in the order the source is read, so they are the same for any number of
workers. A field never takes more than an equal share of the budget, so a source
with very many columns cuts every column alike. A long text sample and the
samples by length each take their reservation from an eighth of the budget.
The samples by length reserve the cost of a full stratum for each length they
may track, in the same order.

When the budget grants less than `scan.limits.max_samples` (or
`max_long_samples`), the block writes the size in force in `k`, the size asked
for in `requested_k` and `reason` `memory_budget` (the long texts block has
`requested_k` only), and a warning `sample_budget` names how many fields were
cut. The samples by length do the same with `max_lengths`,
`requested_max_lengths` and `reason`, only for a field that has more lengths
than the budget granted: a field that fits the lengths granted lost nothing and
says nothing. A grant of 0 lengths writes the block with `tracked` 0 and
`limited` true. A smaller sample is still a bottom-k: its estimate has the larger error of
its `k`. A size of 0 samples nothing for that field (`kept` and `of` are 0) and
the field has no estimate. Counts, lengths, statistics and the exact tables are
not affected. A sample that holds every value of its field (`selection` `all`)
is never cut.

### Counters of a run

`tabalyst scan --counters` (`tabalyst.scan(..., counters=True)`) adds
`run.counters.sampling`, the work of the samplers summed over the fields:
`hashed_keys`, `admitted_keys`, `hit_keys` (occurrences of values already in a
sample), `rejected_keys`, `evicted_keys`, `long_texts_hashed`,
`long_bytes_hashed`, `bottom_k_fields`, `reduced_fields`, `strata_fields`
(fields with samples by length), `strata_limited_fields` (those with values in
`other`), `k_effective_min`, `k_effective_max`, `sample_model_bytes`,
`long_model_bytes` and `length_model_bytes`. Without the
option the member is absent. A figure that the scan did not measure is not
written. Counters describe the run, not the data.

### Writing the document

`tabalyst scan` writes the document without indentation by default, since the
sample entries make it large (about 10 MB for 90,000 entries). Set
`output.json_indent` to `true` in the
[configuration](../reference/configuration.md#output-settings) to indent it,
with each sample entry on one line. The content is the same.

## Inferred patterns

After a scan reads the whole source, it infers the structural patterns of each
eligible field from the samples it kept, without reading the source again. They are
written in the top-level `derived.patterns` member, one entry per field, and
they are not the [configured patterns](../reference/configuration.md#patterns),
which are detectors. A pattern here is a shape, such as two capitals followed by
four digits, found among the distinct values of a field: the discovery of a
structure, not a rule that the data must follow.

```json
{
  "derived": {
    "patterns": {
      "grammar": {"name": "tabalyst.pattern", "version": 1},
      "domain": "original",
      "fields": [
        {
          "dataset": "rows",
          "field": "column_1",
          "status": "complete",
          "eligibility": {
            "state": "eligible", "score": 1.0,
            "reasons": ["regular_structure"]
          },
          "population": {
            "source": "samples", "selection": "all", "complete": true,
            "available": 3000, "distinct": 3000,
            "excluded": {
              "long_text_occurrences": 0, "non_string_values": 0,
              "empty_values": 0, "too_long_values": 0,
              "too_complex_values": 0
            }
          },
          "candidates": [
            {
              "id": "p1", "role": "principal",
              "signature": [
                {"kind": "literal", "text": "CLI", "min": 1, "max": 1},
                {"kind": "literal", "text": "-", "min": 1, "max": 2},
                {"kind": "digit_ascii", "min": 7, "max": 8}
              ],
              "render": "'CLI''-'{1,2}9{7,8}",
              "lengths": {"min": 11, "max": 13},
              "generalization": 0, "merged_structures": 1,
              "coverage": {
                "distinct": 2178, "share": 0.726, "basis": "all_distinct"
              },
              "confidence": {"method": "laplace_share", "value": 0.7257},
              "examples": [0, 1, 2]
            }
          ],
          "other": {"distinct": 0, "share": 0.0, "structures": 0},
          "overlaps": [],
          "limits": []
        }
      ]
    }
  }
}
```

- `grammar` names the version of the rules that cut a value into tokens and
  generalize them. A change of the rules raises its `version`.
- Each field has an entry. `status` is `complete`, `failed` or
  `not_applicable` with a `reason`. `failed` means the inference raised on
  that field (`reason` `inference_error`): `diagnostic` is the index of a
  `pattern_inference_failed` error in `diagnostics`, which names the field
  and the exception type, and the other fields and the rest of the scan are
  unaffected.
- Every entry has an `eligibility`: whether the field is worth a search for
  patterns, decided from the facts and the samples of the scan before any
  pattern is built. Only an `eligible` field is inferred; the others are
  `not_applicable`, and their `reason` is the first reason that kept them out.
  `state` is one of:
  - `eligible`: the values have a regular structure.
  - `low_relevance`: the field can be assessed, but a pattern would describe it
    poorly (free text, a handful of words, decimal numbers).
  - `excluded`: `exposure` (the values of a [sensitive field](#sensitive-values)
    are masked or hidden, so no pattern is inferred), `booleans_only`,
    `structures_only` (only objects or arrays), `long_texts_only` or
    `no_values`.
  - `not_assessable`: information is missing, `samples_withheld` or
    `too_few_distinct`.

  `score` runs from 0 to 1 and ranks the fields (0 for a field that is excluded
  or not assessable); a field is eligible from 0.35. `reasons` explain it:
  `regular_structure` (at most 6 forms of fixed length, such as `AA-9999`, cover
  at least 90% of the values) or `many_fixed_lengths` (they do not, as for
  hyphenated ISBNs or free text), `integer_digits` (a column of whole numbers
  of 4 digits or more, read as text) or `small_integers` (shorter ones, read as
  counts or measures), `decimal_numbers`, `no_structural_marks` (no digit and
  no separator), `few_distinct` (fewer than 8 distinct values) and
  `semantic_detector` (a detector already says what the values are, such as
  dates, which lowers the score without excluding the field).
- `population` is what the inference read: the distinct values of the field's
  [sample](#distinct-values-and-samples) and its
  [samples by length](#samples-by-length), once each. `complete` is true when the
  population is every distinct value of the field: the sample is `all` and
  nothing was excluded or cut. `available` counts the usable
  values and `distinct` those that took part. `excluded` counts what did not:
  the occurrences of [long texts](#long-texts), whose preview never gives the
  pattern of the whole text (`long_text_occurrences`), and the values that are
  neither strings nor integers (an integer is read as its decimal text), are
  empty, are longer than `scan.pattern_inference.max_value_length` or have more
  than 32 tokens.
- A candidate has an `id` (`p1`, `p2`, ...), a `role` (`principal` for the first,
  the most common, then `secondary`) and a `signature`, the list of its tokens.
  A token is a class of characters (`digit_ascii`, `upper_ascii`, `lower_ascii`,
  `letter_unicode` for letters of any script, `alphanumeric` for letters and
  digits) repeated `min` to `max` times, or a `literal` text. Separators, spaces
  and signs are always literals. A letter or digit that is the same in at least
  5 values of a structure is a literal too, so a fixed final `A` and a final
  capital are different patterns.
- `render` is a short reading of the signature: `9` for a digit, `X` for a
  capital, `x` for a lowercase letter, `@` for any letter, `#` for a letter or a
  digit, a count in braces for longer or variable repeats, and literal letters,
  digits and spaces between quotes: `XX9999'A'` is two capitals, four digits and
  the letter A. The `signature` is the reference.
- `lengths` are the shortest and longest value counted for the candidate.
  `generalization` is 0 for a structure kept as it is, 1 when letters of
  different case or script were merged and 2 when letters and digits were;
  `merged_structures` counts the structures the candidate stands for.
- `coverage` is the number of distinct values of the population that the
  candidate takes, and their `share`. Each value counts once, for the most
  specific candidate that reads it. `basis` is `all_distinct` when the
  population is every distinct value and `sample` when it is a sample. It is an
  indicator of discovery on distinct values: it is not the share of the rows of
  the file, which only a later pass can give. `confidence` is a heuristic, the
  share damped by the number of values, not a probability.
- `examples` are ids of entries of the field's sample (see
  [Distinct values and samples](#distinct-values-and-samples)). A report keeps
  fewer sample values, so some ids may not be found in it.
- `other` counts the distinct values that no candidate takes, and the number
  of structures they have. `overlaps` lists the sets of candidates that read
  the same values (a candidate with `letter_unicode` or `alphanumeric` tokens
  can read values of another structure) and how many values each set shares.
  `limits` says `max_patterns` when more structures were found than
  `scan.pattern_inference.max_patterns` allows (the smallest were generalized
  or left in `other`) and `max_values` when the population was cut.
- `scan.pattern_inference.enabled` set to `false` leaves `derived` out of the
  document. A [report](../report/json-profile.md) carries the block as it is.

## Character profile

`string_characteristics` counts the strings of a field by what their characters
are. It works on the raw values, before normalization, and counts occurrences of
values (a value found three times counts three times). Shares are not stored.

| Group | Members |
| --- | --- |
| Case | `uppercase`, `lowercase`, `mixed_case`, `no_letters`, `starts_uppercase`, `starts_lowercase` |
| Classes | `with_ascii_lowercase`, `with_ascii_uppercase`, `with_other_latin_letters`, `with_non_latin_letters`, `with_ascii_digits`, `with_other_digits` |
| Composition | `ascii_only`, `non_ascii`, `letters_only`, `digits_only`, `alphanumeric_only`, `letters_and_digits` |
| Whitespace | `with_surrounding_whitespace`, `with_repeated_whitespace`, `with_line_breaks`, `with_tabs`, `with_non_breaking_spaces` |
| Problem characters | `with_control_characters`, `with_invisible_characters` (U+200B to U+200D, U+FEFF, U+2060), `with_replacement_character` (U+FFFD) |
| Totals | `characters` (the characters of all the values), `distinct_characters` |
| Special characters | `special_characters`: the inventory of the punctuation and symbols |

`distinct_characters` is the exact number of distinct characters of the field. It
is `limited` (reason `character_limit`) above `limits.max_distinct_characters`.
`special_characters` lists, for each character that is neither a letter, a digit,
whitespace nor a control or format character, its `char`, its `codepoint`, its
`value_count` (distinct values that contain it) and its `occurrence_count`
(occurrences of values that contain it), most frequent first. The measure says
`value_count_accuracy`: `exact`, or `upper_bound` for a field whose table of
distinct values was released, since a value that comes back in a later batch is
counted again (`occurrence_count` stays exact). Above
`limits.max_special_characters` distinct characters the measure is `limited` and
lists none, so a partial list is never taken for the whole. On a sensitive field
exposed with `mask` or `hide` the counters stay and both distributions are
`disabled`.

## Normalization stages

`normalization.stages` lists `raw` and then each stage in order (`nfc`, `trim`,
`collapse_whitespace`, `casefold`, `strip_accents`). Each has `enabled`,
`changed` (the values the stage modified, given the output of the previous
enabled stage; `null` for `raw` and disabled stages) and `cardinality` (the
distinct values after the stage, in a [measure envelope](#measure-envelopes)).

A stage with `changed` 0 modified nothing, so it leaves the distinct values as
it found them. It then has `equals`, the name of the stage it takes the count
from (the previous enabled stage, or `raw`), and its `cardinality` is that
stage's: exact when that one is, and `limited` with the same reason, limit and
`lower_bound` when the table of distinct values was released. The estimate and
the upper bound of the raw count are only in `values.cardinality`. `changed` is
counted over the whole scan, so this holds even when the table was dropped
before the end.

A stage that changed something after the table was released has a `limited`
count without a bound and no `equals`: its distinct values cannot be rebuilt
from values that were dropped. A later stage that changed nothing takes that
count. When no enabled stage changed any string, `variant_groups` is complete
and empty even if the table was released, since no spelling can be grouped with
another.

## Observations and limits

After the scan, Tabalyst turns its facts into findings, written in the
top-level `observations` member. They are computed from the counts and the
inferred patterns, without reading the source, and they hold no value, only
counts and references (fields, records, diagnostics, patterns).

```json
{
  "observations": {
    "version": 1,
    "truncated": false,
    "summary": {
      "informational": 19,
      "candidate_anomalies": 24,
      "confirmed_issues": 0,
      "limits": 7,
      "has_observations": true,
      "has_quality_issues": true,
      "has_limits": true
    },
    "datasets": [{"dataset": "rows", "...": "same as summary"}],
    "items": [
      {
        "id": "o1", "rule": "duplicate_rows", "category": "records",
        "status": "candidate_anomaly", "dataset": "rows",
        "population": "records", "count": 8, "of": 3000,
        "accuracy": "exact", "records": [1521, 1814]
      }
    ],
    "limits": [
      {
        "id": "l1", "dataset": "rows", "field": "column_19",
        "measure": "values.samples", "reason": "exposure"
      }
    ]
  }
}
```

- An **observation** has a `rule`, a `category` and a `status`. `informational`
  is a remark that can be perfectly valid, such as a column that is mostly
  empty. `candidate_anomaly` is a signal that no rule can confirm, such as a
  rare pattern or duplicate rows. `confirmed_issue` is a defect by the
  structure of the source, such as excluded records or blank column names.
  `population` says what `count` counts out of `of`; `accuracy` is `exact`,
  `lower_bound` (a limit stops the count from being exact, and `limited_by`
  names it) or `sample`.
- The rules of version 2 are `excluded_records`, `ambiguous_header`,
  `duplicate_rows`, `mixed_types`, `type_outliers`, `ambiguous_dates`,
  `variant_groups`, `minority_pattern`, `minority_length` (one length holds at
  least 95% of at least 20 strings and the others at most 5%: a malformed value
  that a pattern absorbed), `missing_values`, `empty_column`,
  `constant_column`, `trimmed_cells` and `collapsed_whitespace`. A rule applies
  to a field, a dataset or the whole scan (no `dataset`). Their thresholds are
  constants of the version.
- A **limit** is what the scan could not establish: a measure stopped by a
  scan limit (`values.cardinality`, `records.duplicates.count`), a sample cut
  by the memory budget or withheld by exposure, a truncated structure, or an
  inference that failed. It is never a defect of the data, so it is listed
  apart from the observations. A stage that repeats the limit of its input is
  not listed again.
- `summary` and `datasets` (one per dataset) count the findings and give three
  flags: `has_observations` (any observation), `has_quality_issues` (a
  candidate anomaly or a confirmed issue) and `has_limits`. They are per scan
  and per dataset; for a field, read the items.
- `items` are sorted by status (confirmed issues first), then by dataset and
  field, and at most `scan.observations.max_items` (1,000) of them and of the
  limits are listed. `truncated` says a list is shorter than its count; the
  counts of `summary` are complete.
- `scan.observations.enabled` set to `false` leaves the member out. If the
  computation fails, the member is left out too and an `observations_failed`
  error in `diagnostics` says so; the scan is complete. A
  [report](../report/json-profile.md) carries the member as it is; its
  `issues` are unchanged.

## JSON Schema

The package contains the JSON Schema of the scan document,
`tabalyst/schemas/tabalyst.scan.schema.json`, also available from
`tabalyst.scanner.schema.scan_schema()`. It describes the base document and
describes `derived` (the [inferred patterns](#inferred-patterns)) and
`observations` (the [observations](#observations-and-limits)) and accepts
the namespaces `analyses` and `report`, which extensions of the base may add. The package also has the schema of the
report, `tabalyst/schemas/tabalyst.report.schema.json`
(`tabalyst.report_schema.report_schema()`). Rules that link several members, such as
a count that must equal the sum of its parts, are checked by
`tabalyst.scanner.validation.check_scan()`, which returns the violated
invariants.

## Detectors

```json
{
  "id": "number",
  "version": 1,
  "status": "complete",
  "coverage": {
    "eligible": 2, "tested": 2, "matched": 2, "ambiguous": 0,
    "invalid": 0, "not_matched": 0, "not_tested": 0,
    "share_tested": 1.0, "share_eligible": 1.0
  },
  "formats": [{"format": "0", "count": 1}, {"format": "0.0", "count": 1}],
  "evidence": {
    "matched": ["12.50", "7"], "ambiguous": [],
    "invalid": [], "not_matched": []
  },
  "details": {},
  "adaptive": null
}
```

Every detector is listed for every field, with status `complete`,
`not_applicable`, `disabled` or `failed`.

- `coverage`: `eligible` values of an accepted type, split into `matched`,
  `ambiguous` (several readings, such as `01/02/2026`), `invalid` (the right
  shape with a wrong content, such as a 13th month), `not_matched` and
  `not_tested`. Shares are rounded to four decimals.
- `formats`: the forms matched, such as `YYYY-MM-DD` or `#,##0.0`, by count.
- `evidence`: the first distinct values in each state.
- `details`: detector-specific counts, such as email domains or ambiguity
  evidence.
- `adaptive`: `null` when the detector tested every value of the field.
  When it recognized none of the first `detection.warmup_values` distinct
  values, or at most `detection.rare_share` of them and none in the second
  half of that warm-up, it is skipped for the other values except probes, and
  `adaptive` is
  `{"skipped_after": 10000, "warmup_reactions": 0, "not_tested": 1200, "diagnostic": null}`:
  the warm-up size, the warm-up values it recognized, the values it did not
  test (included in `coverage.not_tested`), and the index of a
  `detector_skipped_reacted` warning when probes were recognized more often
  than the warm-up allowed, meaning its counts are incomplete. `number` and
  `date` are never skipped.

The built-in detectors are `number`, `date`, `boolean`, `enumeration`,
`email`, `url`, `phone`, `postal_code`, `currency`, `percentage`, `quantity`,
`uuid` and `ip_address`. Patterns of the configuration appear as
`pattern:<id>`. Detectors check syntax, never real-world existence.

The evidence is published, and the configuration resolves an ambiguity,
for example with `detectors.date.ambiguous_order`. Numbers are also read by
the evidence of their own column, never by a guess:

- When at least `detectors.number.min_evidence` (3) unambiguous numbers of a
  field use one convention and none uses the other, the ambiguous numbers
  (`1,234`) are read in that convention and counted in `numeric`. With a
  decimal comma proven (`2,5`, `1.234,56`), a value such as `1.250` is read
  as 1250, a thousands group, rather than as 1.25.
- A column that uses both conventions, or too few of them, is read as before:
  its ambiguous numbers stay out of `numeric`. Spaces between thousands
  (`1 234`) prove nothing on their own.
- The `number` detector names what was done in
  `details.ambiguity.resolution`:

  ```json
  {"convention": "comma", "source": "evidence",
   "evidence": {"comma": 490, "dot": 0}, "resolved": 110}
  ```

  `resolved` counts the numbers read by the evidence. Its `coverage` and
  `formats` still describe how the values are written, so `1,234` stays
  `ambiguous` there and `numeric.count` can exceed `coverage.matched`.
- `detectors.number.infer_convention: false` turns the rule off, and
  `detectors.number.ambiguous_convention` always wins over it.
- JSON and Excel numbers are numbers already: they are kept as they are,
  never read in a convention. Only text values are.

The second pass reads the numbers of such a field as the scan counted them.

## Sensitive values

A field is sensitive when a sensitive detector (`email`, `phone`,
`ip_address`, or a pattern declared `sensitive`) matched one of its values.
With the default `mask` exposure, its listed values, evidence and variant
groups show masks: uppercase letters become `A`, other letters `a` and digits
`9`. Equal masks are merged. Under `mask` and `hide`, the `numeric` and
`temporal` blocks of a sensitive field are `disabled`, since a minimum or a
date range is itself a value. Counts are never masked.

## Diagnostics

```json
{
  "code": "csv_width_mismatch",
  "level": "error",
  "message": "...",
  "count": 2,
  "dataset": "rows",
  "field": null,
  "detector": null,
  "details": {},
  "locations": [{"record": 2, "line": 3}, {"record": 3, "line": 4}]
}
```

`measures_limited` has one diagnostic per field (`field` is the field
identifier), with `details.measures` mapping each limited measure, such as
`values.cardinality`, to its reason; its `count` is the number of limited
measures. `details` is empty for the other codes.

Diagnostics describe technical events, not data quality: excluded records,
reached limits (`field_limit`, `depth_limit`, `measures_limited`,
`global_budget`, `record_budget`, `sample_budget`), collections not found and
detector failures, and the failure of a post-scan analysis
(`pattern_inference_failed`, `observations_failed`). `level` is
`error` or `warning`. `count` is always complete; `locations` lists at most
`errors.max_locations` places, with `record` and `line` for CSV and JSONL,
`record` and `element` for JSON. For JSONL, `line` is the physical line number,
blank lines included, and `record` counts the non-blank lines.
