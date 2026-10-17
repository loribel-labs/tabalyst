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
  "format_revision": 4,
  "engine": {
    "version": "0.7.0",
    "normalization_version": 1,
    "detectors": {"number": 1, "date": 1, "email": 1, "...": 1},
    "classification": {"catalogue": 4, "names": 2}
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
| `classification` | The family and type of the field, with what decided them: see [Classification](#classification). |
| `sensitive`, `exposure` | Whether the field holds sensitive values, and how they are exposed: `mask`, `hide`, `show`, or `null` for other fields. |

Values are listed as their text with their native type, for example
`{"value": "12.50", "type": "string", "count": 1}`. Listings use the analytical
value: surrounding whitespace is trimmed and repeated spaces are collapsed.

## Classification

Each field has a `classification` that names its family and type. It is decided
from the blocks of the field alone, in the first pass, so a Scan gives the same
classification with one or several workers and without the source.

```json
{
  "family": "text",
  "type": "text_short",
  "basis": "inferred",
  "state": "established",
  "traits": [],
  "evidence": [
    {"source": "technical_type", "id": "text", "role": "supports",
     "scope": {"population": "present_values", "of": 3, "partial": false,
               "accuracy": "exact"}},
    {"source": "measure", "id": "string_lengths.median_length",
     "role": "supports",
     "scope": {"population": "present_values", "of": 3, "partial": false,
               "accuracy": "exact"}}
  ],
  "alternatives": [],
  "rule_version": 4002
}
```

| Key | Content |
| --- | --- |
| `family`, `type` | Codes in lower snake case: `text` and `text_short`, `numeric` and `integer`. One pair per field; secondary properties are in `traits`. |
| `basis` | `inferred` when the evidence decided, `fallback` when the technical type or a fallback did, `declared` for a constraint the user declares (not produced yet). |
| `state` | `established` when the values themselves support the type, `candidate` when it rests on a name plus compatible values, `undetermined` when the evidence did not allow more. |
| `evidence` | The facts used: `source` (`detector`, `technical_type`, `measure`, `name_rule`, `position`), their `id` (a detector id, a measure name or a name rule id), their `role` (`supports`, `contradicts`, `context`) and their `scope` (what population the fact covers, its size, whether it is partial and its accuracy). |
| `alternatives` | Types considered and not retained, with a `reason`. Never a conclusion. |
| `traits` | Secondary properties that never change the pair: `single_pattern` or `multiple_patterns` (from [Inferred patterns](#inferred-patterns)), `constant` (one distinct value on a typed column), `observed_unique` (the exact count of distinct values equals the present values) and `first_column` (first column of a CSV or Excel table). The last two are facts about the column and never prove a role. |
| `rule_version` | The version of the rules that decided, as one integer: the catalogue version times 1,000 plus the version of the name rules (4002 is catalogue 4, name rules 2). `engine.classification` records both separately. |

There is no score and no percentage of confidence: the evidence and the state
say how firm the result is.

This version decides:

- **Other / Empty** for a field without present value, including a JSON object or
  array, whose values are not analyzed.
- **Types carried by a detector**, when it reaches `detection.minimum_share` of
  its eligible values (any detector listed in `interpretations.candidates`, not
  only the primary interpretation): `numeric/currency`, `numeric/percentage` and
  `numeric/quantity`; `contact/email` and `contact/phone`; `geographic/postal_code`;
  `web_network/url`, `web_network/ip_address` and `web_network/uuid`. A detector
  type outranks Enum, Text and the numeric types, so a column of long email
  addresses stays `contact/email`. A bare number is never `currency` or
  `percentage`: only their detector, which needs the symbol or the `%`, gives
  them.
- **Categorical**: `categorical/boolean` from the `boolean` detector or a
  `boolean` technical type (two categories such as `M` and `F` never make a
  Boolean); `categorical/enum` from the `enumeration` detector over a text
  field; `categorical/constant` for a text field with a single exact analytical
  value in at least two present occurrences.
- **Temporal**: `temporal/date` from a `date` technical type; `temporal/datetime`
  (with or without a time zone) and `temporal/time` from the `date` detector and
  the kinds of `temporal`. A column that mixes natures keeps the one with the most
  values and lists the others in `alternatives` with the reason `minority_kind`.
- **Numeric**: `numeric/integer` and `numeric/number` from the technical type
  when no detector type competes (`basis` `fallback`). An Enum candidate over a
  numeric column is an alternative with the reason `numeric_type_kept`.
- **Identifier**, from a name and compatible values: `identifier/id` and
  `identifier/unique_id`, always `candidate` (see [Identifiers](#identifiers)).
- **Other / Mixed** for a `mixed` technical type that no detector refines.
- **Text**, from a `text` technical type, in five lengths: `text_very_short`,
  `text_short`, `text_medium`, `text_long` and `text_very_long`. The length
  type is decided on the exact median of the lengths of the present values
  (`string_lengths`), with the bounds of
  [`scan.classification`](../reference/configuration.md#text-length-bounds); a
  median of 5.5 is Short with the defaults. The maximum is never a replacement:
  when `string_lengths` is not complete the type is `text` alone, `state` is
  `undetermined` and `alternatives` lists the five lengths with the reason
  `string_lengths_<status>`.

When two credible types cannot be told apart, the result is an explicit
fallback and never the first one in the order of the detectors: `state` is
`undetermined`, both candidates are in `alternatives` with the reason
`conflicting_candidates` and their evidence has the role `context`. Two
detector types, or two kinds of dates of the same weight, give `other/unknown`.
A detector type that reads a numeric column as well, such as `postal_code` or
`phone` over whole numbers of five or ten digits, keeps `numeric/integer`
undetermined: the values cannot say whether the digits are a code or a quantity.

### Names

The name of a field is read after its values, by versioned rules in French and
English (`email`, `courriel`, `code_postal`, `date_naissance`, `is_active`...).
A name never creates a type. It can only:

- **Reinforce** a type the values already support: the rule is added to
  `evidence` with the role `supports`. The type and the `state` do not change.
- **Break a tie** between types the values support equally. Five-digit whole
  numbers named `postal_code` become `geographic/postal_code`, and the same
  numbers named `postal_code_status` stay `numeric/integer`. A conflict settled
  by a name has `state` `candidate`, because the result rests on a name plus
  compatible values; the other type is in `alternatives` with the reason
  `outranked_by_name` or `weakened_by_name`.
- **Weaken** a type: a name such as `email_status` or `customer_id_length`
  describes a property of the thing it names, not the thing. If the values
  still support the type, it is kept and the rule `name.derived_measure` is
  added with the role `contradicts`.

A type that only the name suggests is listed in `alternatives` with the reason
`name_only` when the technical type allows it, and is never the result: a column
named `email` that holds free text is Text.

Names are compared as whole words, never as pieces of words, after Unicode
normalization, the split of CamelCase and acronyms (`CustomerID`, `ZIPCode`),
the removal of accents and the harmonization of separators, so `CustomerID`,
`customer_id` and `CUSTOMER-ID` read alike. The header or the key is not
changed. For a JSON field the key of the field is the name, and the keys above it
are only context: `postal.code` as one key is a postal code, `postal` containing
`code` is not. The identifier names (`id`, `customer_id`, `id_client`, `order_ref`...)
give the [identifier role](#identifiers).

The String analysis section of the report names the length of a column from
its maximum with the same bounds, so a column can be Short as a type and
`medium` there.

### Identifiers

`identifier/id` is the one type a name and the values create together. It needs:

- an identifier name rule (`id`, `identifiant`, a name that starts or ends with
  `id`, ends with `ref` or `key`, or has `customer` or `order` with `id`) and no
  weakening of it: `customer_id_length` and `order_id_status` describe a property
  of an identifier, not an identifier;
- compatible values: a `text` or `integer` technical type with no present value
  outside its family, and at least two present values.

The role replaces a Text of any length or a plain Integer, and nothing else. The
replaced type stays in `alternatives` with the reason `replaced_by_role`. An
Integer that `postal_code` or `phone` also reads (five or ten digits) is
undetermined and the identifier name settles it. A detector type, Enum, Constant,
Number, a date or time type, Boolean and Other keep their type: an identifier
never overrides a more specific type, and the role is then an alternative with
the reason `name_only`. A UUID keeps `web_network/uuid` and lists the role with the
reason `uuid_name`. The state is `candidate`, never `established`: the role rests
on a name, not on the values alone.

`identifier/unique_id` is an ID for which all of these hold:

- the field is not under a JSON array;
- no position is missing (`missing.count` is 0, and no record lacks the field,
  even if `values.missing` does not count `absent`);
- the number of distinct analytical values is exact and complete, and equals the
  number of present values. The analytical values follow the NFC, trim and
  whitespace stages, so `A` and ` A ` are the same value. A limited or estimated
  cardinality never gives a Unique ID in the Scan. The Report can refine an ID whose
  cardinality was limited with the exact distinct count of the
  [second pass](deep.md#exact-distinct-count).

The evidence of a Unique ID adds the measures `values.cardinality` and
`missing.count`, with the scope they cover: the present values and the positions
of the dataset, and `partial` set when the scan excluded records of that dataset.
A uniqueness seen in the scanned scope does not guarantee a business key,
uniqueness in the future or uniqueness in the records the scan excluded.

A column without an identifier name stays outside Identifier whatever its
position or its uniqueness: a first column of distinct dates, timestamps or
amounts keeps its type with the traits `first_column` and `observed_unique`.
`observed_unique` needs at least two present values. The trait `high_cardinality`
is not emitted: no threshold comes from the limits the Scan tracks.

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
      "grammar": {"name": "tabalyst.pattern", "version": 2},
      "algorithm": {"version": 1},
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
            "occurrences": 3000, "occurrences_basis": "exact",
            "excluded": {
              "long_text_occurrences": 0, "non_string_values": 0,
              "empty_values": 0, "too_long_values": 0,
              "too_complex_values": 0
            }
          },
          "families": [
            {
              "id": "f1", "key": "UP-D", "d": 3000, "o": 3000,
              "patterns": [
                {
                  "id": "f1.p1",
                  "signature": [
                    {"kind": "literal", "text": "CLI", "min": 1, "max": 1},
                    {"kind": "literal", "text": "-", "min": 1, "max": 1},
                    {"kind": "digit_ascii", "min": 7, "max": 7}
                  ],
                  "render": "'CLI-'9{7}",
                  "format": "AAA-9{7}",
                  "lengths": [3, 7],
                  "d": 2178, "o": 2178,
                  "examples": [0, 1, 2],
                  "nodes": []
                }
              ],
              "tables": [],
              "examples": [0, 1, 2]
            }
          ],
          "other": {"structures": 0, "d": 0, "o": 0},
          "limits": []
        }
      ]
    }
  }
}
```

- `grammar` names the version of the rules that cut a value into tokens and
  write a signature, and of the notation of `render`. A change of the rules
  raises its `version`. `algorithm.version` is the version of the discovery
  itself (its scores and constants).
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
- `families` gather the values of one structure: the classes of their tokens
  (digits, capitals, lowercase letters, other letters) and their separators,
  without the lengths (`key`: `UP-D` is capitals, a hyphen, digits). Two
  structures that differ only at the start or at the end of a block, by one or
  two positions, are one family when the part they share is at least as long:
  `AK-12345` and `AK-1234X` (`composition` lists their keys). Each family has an
  `id` (`f1`, `f2`, ...), ranked by the larger of its shares of the distinct
  values and of the occurrences, and its counts: `d` distinct values and `o`
  occurrences. A structure with a single value is a family of its own.
- A family lists its `patterns`, one for each combination of lengths found in
  the values, with `id` `f1.p1`: `'INV-'999`, `'INV-'9999` and `'INV-'99999` are
  three patterns of one family. A pattern has a fixed length at every position
  and never a range. Its `signature` is the list of its tokens: a class of
  characters (`digit_ascii`, `upper_ascii`, `lower_ascii`, `letter_unicode` for
  letters of any script, `upper_digit`, `lower_digit`, `alphanumeric`) repeated
  `min` to `max` times (always the same number), or a `literal` text. Separators,
  spaces and signs are always literals. The characters that all the values of a
  pattern have at the start of a token become a literal: `'AK-'9999`; a fixed value and the separators that touch it are written as one block of text, and a single space between two elements as it is: `'AK-' 9999`. A pattern
  of a single value folds nothing.
- `render` is a short reading of the signature: `9` for a digit, `A` for a
  capital, `a` for a lowercase letter, `@` for any letter, `X` for a capital or a
  digit, `x` for a lowercase letter or a digit, `#` for a letter or a digit, a
  count in braces for longer repeats, and literal letters and digits
  between quotes: `AA9999'A'` is two capitals, four digits and the letter A. The
  `signature` is the reference. `format` is the exact form of the commonest
  value of the pattern, and `lengths` the lengths of its tokens (a merged block
  counts as one).
- When a pattern holds several merged structures, its last positions are of the
  classes of all of them (`'AK-'9999X`), and `nodes` lists the structures with
  their own counts (`'AK-'99999`, `'AK-'9999A`), with `facet` `composition`. The
  counts of these nodes add up to the pattern, those of the patterns to the family.
- A pattern also has **nodes of content** when a part of its values is set apart
  by the first or last characters of a token, or by a short token. `facet` says
  what the node reads, counting the tokens of the structure `key` from 1 (`UP-D`
  has three: the capitals, the hyphen and the digits): `head:1` the first
  characters of the capitals, `tail:3` the last characters of the digits, `token:3`
  the whole token (at most 4 characters). A node has a `signature` and a `render`
  like a pattern (`'AK-'9999`; a tail is written after the class: `9{4}'00'`), its
  `value` (the text it fixes at its facet, spelled from the left, such as `AK`; for
  a node of `composition`, the structure it reads), `also` when a node merged into
  it (what that node fixed: `facet` and `value` pairs), its counts `d` and `o`, its
  `level` (2 under a pattern) and a `gain`: `bits_d` and
  `bits_o`, the bits it saves when the values are described by it rather than by
  the pattern (a description length, on the distinct values and on the
  occurrences; one is negative when the node is kept for the other measure only),
  and `sigma`, the share of the bits of the characters it reads that its facet
  saves. A facet is published from a `sigma` of 0.10, and only when the
  characters it reads depart from chance: letters drawn at random make no node.
  The nodes of a facet are a part of the pattern, the other values being its rest.
  A longer prefix of the same facet (`'AK'` then `'AK1'`), or a facet that depends
  on the node (the year, once the prefix is known), is nested in its `nodes`, down
  to `scan.pattern_inference.max_depth` levels (the pattern is the first). Each
  value counts for the deepest node that holds it.
- `d` and `o` count distinct values and occurrences. The distinct values are
  those of the population. `o` is `exact` when the population is every distinct
  value (`occurrences_basis`), and an indicator of discovery on a sample
  otherwise: it is not the share of the rows of the file, which only a later
  pass can give. Each value counts for one family and one pattern.
- `examples` are ids of entries of the field's sample (see
  [Distinct values and samples](#distinct-values-and-samples)). A report keeps
  fewer sample values, so some ids may not be found in it.
- `tables` of a family are of two kinds. `facet` `lengths` lists the
  combinations of lengths that `scan.pattern_inference.max_patterns_per_family`
  kept out of its patterns. A facet of content (`head:N`, `tail:N`, `token:N`) that
  is published but that no node reads, because the values it splits do not depend on
  the nodes, is a table of the family: `cells` of `value` (the characters, spelled
  from the left), `d` and `o`, `others` for the rest, and the `gain` of the facet.
  The cells and `others` add up to the family.
- `other` counts the structures that no published family reads, with their
  distinct values (`d`) and occurrences (`o`). `limits` names the budgets that
  acted: `max_values` (the population was cut to
  `scan.pattern_inference.max_values`), `max_families`,
  `max_patterns_per_family`, `max_patterns` (the patterns and nodes of the
  field, the nodes of the lowest gain going first) and `max_depth` (a node was
  below `scan.pattern_inference.max_depth` levels and was left out).
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

## Character map

`derived.characters.fields` has one entry per field, in the order of the datasets and
fields, each a [measure envelope](#measure-envelopes) of the character map of its strings
(`status` `complete`, `limited`, `not_applicable`, `disabled` or `failed`). It is computed
after the scan from the samples, never from the source.

```json
{
  "dataset": "rows", "field": "name",
  "characters": {
    "status": "complete",
    "value": {
      "basis": "exact",
      "values": 4, "characters": 20, "distinct": 11,
      "top": [{"char": "a", "codepoint": 97, "occurrence_count": 3}],
      "scripts": [{"name": "LATIN", "occurrence_count": 20}],
      "categories": [{"name": "Ll", "occurrence_count": 17}],
      "ends_uppercase": 0, "ends_lowercase": 4, "title_case": 3,
      "with_emoji": 0, "emoji_sequences": 0, "emoji": []
    }
  }
}
```

- `basis` is `exact` when the scan listed every distinct value, and `sample` when the map
  counts the stored samples only. A [second pass](deep-format.md) makes it exact.
- `top` lists the `limits.max_top_characters` most frequent characters (20 by default),
  letters and digits included, from the most to the least frequent, then by code point.
  `A` and `a` are two characters.
- `scripts` gives the characters of the letters by script (the first word of the Unicode name:
  `LATIN`, `CYRILLIC`, `CJK`...). `categories` gives all the characters by Unicode general
  category (`Lu`, `Nd`, `Po`...) and adds up to `characters`.
- `ends_uppercase` and `ends_lowercase` count the values whose last character is a capital
  or a lowercase letter, and `title_case` the values written in title case (`Jean-Pierre`,
  not `McDonald`). All three count occurrences of values.
- `emoji` lists the most frequent emoji sequences (an emoji with its skin tone and joiners, a
  flag or a keycap is one sequence). The emoji are recognized by a table of ranges, an
  approximation of the Unicode emoji.
- Above 65,536 distinct characters or 10,000 distinct emoji the entry is `limited` with the
  reason `character_limit` and lists nothing. A field exposed with `mask` or `hide` is
  `disabled`. `limits.max_top_characters` 0 removes the block.

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
  evidence. The `email`, `phone` and `postal_code` detectors add `keys`: the
  extension and domain of an address, the region and area code of a number, the
  first character and area of a postal code, counted exactly with their occurrences
  (`key`, `occurrences`, then the `keys` and `others` below) and published even on a
  masked field; see `scan.exposure.detector_keys`.
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
With the `mask` exposure, its listed values, evidence and variant
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
