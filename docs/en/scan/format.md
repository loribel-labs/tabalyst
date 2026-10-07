---
title: Scan format
description: Structure of the JSON document written by tabalyst scan, with its top level, datasets, fields, measure envelopes, detectors and diagnostics.
---

`tabalyst scan data.csv` writes a reusable `scan.json` by default;
`-o` and `-d` export a standalone `<stem>.scan.json`. Both are JSON documents that
describe every field of the source. This page describes format
`tabalyst.scan`, version `0.2.0`, revision `2`. The format is
**experimental**: it can change incompatibly between releases. Always check
`format`, `format_version` and `format_revision` first; changes are listed in
the [scan format changelog](format-changelog.md).

## Top level

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.2.0",
  "format_revision": 2,
  "engine": {
    "version": "0.6.2",
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
  datasets) and `other` (setup and assembly of the result); the four parts add
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
empty records, duplicate records and a preview of the first records.

```json
{
  "with_missing": {"count": 2, "records": [2, 5]},
  "empty": {"count": 1, "records": [5]},
  "duplicates": {
    "count": {"status": "complete", "value": 1},
    "records": [3]
  },
  "preview": [
    {
      "record": 1,
      "values": {"column_1": ["1"], "column_2": ["aaa@aaaaaaa.aaa"]}
    }
  ]
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
- `preview`: the first `records.preview` records, each with its values per
  field identifier, as text. The values of an items path are listed in order;
  a JSON null is `null`; a field absent from the record has no key. Sensitive
  values go through the field's exposure; a cell holding a hidden value is
  `null`. Empty strings, blanks and null markers are shown as read.

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
| `string_characteristics`, `string_lengths` | Case, non-ASCII characters, line breaks and whitespace; length statistics and histogram. |
| `numeric`, `booleans`, `temporal` | Exact numeric statistics, boolean counts, date range and formats. |
| `normalization` | For each normalization stage, how many values it changed and the distinct values left, plus groups of variants that normalize to the same value. |
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

`values.samples` lists distinct values with their exact counts: all of them
when the field has at most `scan.limits.max_samples` (10,000 by default),
otherwise that many, drawn with `scan.random_seed` (`uniform_distinct`) or the
first distinct values seen when the table was released (`first_seen`). A sample
is a set of examples, not a statistic: its counts are exact for its values and
do not describe the other values of the field. `max_samples` cannot exceed
`max_distinct_per_field`; when it is not set it follows a lower
`max_distinct_per_field`. The selection `bottom_k`, with the members `k`,
`hash` and `threshold`, is reserved for a later revision. `kept` is the number
of values listed and `of` the number the scan sampled: a scan writes both equal.
A [report](../report/json-profile.md#reduced-samples) that holds the scan as its
base keeps fewer values and says so with `kept` below `of`.

## JSON Schema

The package contains the JSON Schema of the scan document,
`tabalyst/schemas/tabalyst.scan.schema.json`, also available from
`tabalyst.scanner.schema.scan_schema()`. It describes the base document and
accepts the namespaces `derived`, `observations`, `analyses` and `report`,
which extensions of the base may add. The package also has the schema of the
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

Tabalyst never resolves an ambiguity by guessing from other values of the
field: the evidence is published, and only the configuration resolves it,
for example with `detectors.date.ambiguous_order`.

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
`global_budget`, `record_budget`), collections not found and detector
failures. `level` is
`error` or `warning`. `count` is always complete; `locations` lists at most
`errors.max_locations` places, with `record` and `line` for CSV and JSONL,
`record` and `element` for JSON. For JSONL, `line` is the physical line number,
blank lines included, and `record` counts the non-blank lines.
