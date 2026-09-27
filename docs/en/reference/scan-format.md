---
title: Scan format
description: Structure of the JSON document written by tabalyst scan, with its top level, datasets, fields, measure envelopes, detectors and diagnostics.
---

`tabalyst scan data.csv` writes `data.scan.json`, a JSON document that
describes every field of the source. This page describes format
`tabalyst.scan`, version `0.1.0a`, revision `1`. The format is
**experimental**: it can change incompatibly between releases. Always check
`format`, `format_version` and `format_revision` first; changes are listed in
the [scan format changelog](scan-format-changelog.md).

## Top level

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "engine": {
    "version": "0.4.0",
    "normalization_version": 1,
    "detectors": {"number": 1, "date": 1, "email": 1, "...": 1}
  },
  "status": "complete",
  "started_at": "2026-09-27T05:06:41.369888Z",
  "duration_seconds": 0.0023,
  "source": {
    "format": "csv",
    "name": "orders.csv",
    "size_bytes": 63,
    "modified_at": "2026-09-27T05:06:40.930099Z",
    "sha256": "fe7a56e5...",
    "encoding": "utf-8-sig",
    "csv": {"delimiter": ",", "header": ["id", "amount", "email"]}
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
- `source`: the file as read. `size_bytes` and `sha256` cover every byte read.
  `encoding` is the CSV encoding, or `utf-8` or `utf-8-sig` for JSON. `csv` is
  `null` for JSON sources.
- `config`: the complete effective configuration, with every default, as in
  the `scan` section of a [configuration file](configuration.md#scan-settings).
  `config_sha256` is the SHA-256 of its canonical JSON (sorted keys, no
  whitespace, UTF-8): two scans with the same value used the same settings.
- `scope`: records read, analyzed and excluded, with exclusions counted by
  reason (`width_mismatch`, `duplicate_key`, `record_too_large`).
  `collections` is `null` for CSV; for JSON it gives the `mode` (`auto` or
  `explicit`) and the `requested` collection paths.

## Datasets

A CSV source has one dataset, `rows`. A JSON source has one dataset per
collection of records, and one `document` dataset when its root is not an
array.

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
  "fields": []
}
```

- `kind`: `table` (CSV), `collection` or `document` (JSON).
- `record_count`: analyzed records; `record_types`: records per JSON type.
- `structure`: the number of distinct field paths, and what the `max_fields`
  and `max_depth` limits left out.

## Fields

Fields are listed in order of discovery. A field is a path inside the records:
a CSV column, a JSON key, or the elements `[]` of an array.

| Key | Content |
| --- | --- |
| `id`, `path`, `display`, `name`, `parent` | Identity: an identifier such as `f4`, the path as segments, its readable form such as `orders[].amount`, the last segment and the parent field identifier. |
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
{"status": "limited", "reason": "distinct_limit", "limit": 100000, "lower_bound": 100001}
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
  "evidence": {"matched": ["12.50", "7"], "ambiguous": [], "invalid": [], "not_matched": []},
  "details": {}
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
  "locations": [{"record": 2, "line": 3}, {"record": 3, "line": 4}]
}
```

Diagnostics describe technical events, not data quality: excluded records,
reached limits (`field_limit`, `depth_limit`, `measures_limited`,
`global_budget`), collections not found and detector failures. `level` is
`error` or `warning`. `count` is always complete; `locations` lists at most
`errors.max_locations` places, with `record` and `line` for CSV, `record` and
`element` for JSON.
