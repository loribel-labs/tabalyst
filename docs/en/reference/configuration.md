---
title: Configuration
description: Reference for the JSON configuration file read by tabalyst report, tabalyst sample, tabalyst scan and the Python API.
---

Tabalyst reads strict JSON configuration files. JSON does not allow comments;
this page is the descriptive reference for supported settings. Commands load
the files passed with `--config`, and the Python API those passed with
`config_path`; no file is loaded automatically. `tabalyst.json` is only a
conventional name.

One file can configure every command. The settings of `tabalyst report` and
`tabalyst sample` are at the top level; the settings of `tabalyst scan` are in
the `scan` object, described in [Scan settings](#scan-settings):

```json
{
  "csv": {"delimiter": ";"},
  "preview_rows": 20,
  "scan": {
    "csv": {"delimiter": ";"},
    "values": {"null_markers": ["N/A"]}
  }
}
```

Every command validates the whole file, including the sections it does not
use, so a misspelled or unknown setting is always an error. Explicit
command-line values, such as `--delimiter` and `--encoding`, are the final
override.

## CSV and preview

```json
{
  "csv": {
    "encoding": "utf-8-sig",
    "delimiter": ","
  },
  "missing_values": [""],
  "preview_rows": 10
}
```

- `csv.encoding`: source-file encoding. The default accepts UTF-8 with or without
  a BOM; `cp1252` is useful for some Windows-produced files.
- `csv.delimiter`: single-character separator, a comma by default.
- `missing_values`: strings treated as missing after surrounding whitespace is
  stripped. Comparisons remain case-sensitive.
- `preview_rows`: number of raw rows embedded in the report, from 0 to 100. It
  never limits analysis of the complete CSV.

## Value normalization

```json
{
  "normalization": {
    "trim": true,
    "collapse_internal_whitespace": true
  }
}
```

- `trim`: removes leading and trailing Unicode whitespace before analysis.
- `collapse_internal_whitespace`: replaces each internal run of horizontal
  whitespace, including tabs and non-breaking spaces, with one ordinary space.
  Line breaks are preserved.

Normalization affects type inference, distinct values, occurrences, examples and
`enum` detection. Raw CSV values remain available in the data preview, and exact
duplicate rows still compare raw values. Each column records the number and
percentage of cells changed by each operation; the dataset summary also records
both global counts. A cell changed by both operations contributes to both counts,
but never more than once to the same operation.

## Date detection

```json
{
  "date_detection": {
    "enabled": true,
    "orders": ["YMD", "MDY", "DMY"],
    "separators": ["-", "/", "."],
    "ambiguous_order": null
  }
}
```

- `enabled`: turns strict date profiling on or off.
- `orders`: accepted component orders. Years must use four digits; months and days
  may use one or two digits.
- `separators`: accepted single-character separators. Each value must use the same
  separator between both component pairs.
- `ambiguous_order`: optionally resolves values such as `02/03/2025` as `MDY` or
  `DMY`. With `null`, Tabalyst resolves them only when the same column contains
  unambiguous evidence for one order and none for the other.

Every recognized structure is validated against the calendar, including leap
years. Profiles count valid, ambiguous, invalid and non-date values separately,
then group valid occurrences by order and separator. `YYYY-MM-DD` is specifically
marked as ISO; other separators using `YMD` remain valid but are not labeled ISO.
Arbitrary text is not treated as a date error.

## Type inference

```json
{
  "type_inference": {
    "minimum_confidence": 0.95
  }
}
```

`minimum_confidence` is the proportion of present values that must agree before a
column receives a dominant physical type. Values outside that type are retained as
errors with a count and percentage. A column with no dominant family remains
`mixed` and has no misleading error rate. Numeric statistics use accepted numeric
values only.

A date column with one valid format has physical type `date`. Multiple valid date
formats produce `mixed` with semantic type `date`; malformed and unresolved
ambiguous dates contribute to the type error rate.

## String analysis

```json
{
  "string_analysis": {
    "very_short_max_length": 5,
    "short_max_length": 20,
    "medium_max_length": 50,
    "long_max_length": 255,
    "length_distribution_max_length": 50,
    "examples_per_length": 10
  }
}
```

Present normalized values in physical `text` columns are classified from their
maximum length as `very_short`, `short`, `medium`, `long` or `very_long`. A fixed
length is recorded separately when minimum and maximum match. Missing values do
not contribute to lengths. Mean and median length are calculated for every text
column; the report leaves them blank when the fixed length already conveys the
same information.

When the column maximum is at most `length_distribution_max_length`, JSON also
contains occurrence and distinct-value counts for every observed length. Each
length retains up to `examples_per_length` normalized distinct values, ordered by
descending occurrence and then alphabetically. `distinct_length_count` remains
available for every text column, including columns whose distribution is omitted.
The report orders length groups by occurrence and shows three retained examples
per length in its String analysis tooltip.

## Examples and value profiles

```json
{
  "value_examples": {
    "full_distribution_max_distinct": 50,
    "candidate_sample_size": 100,
    "short_text_max_length": 20,
    "short_text_percentile": 0.95,
    "short_text_result_size": 20,
    "long_text_result_size": 20,
    "long_text_truncate_at": 30,
    "truncation_suffix": "...",
    "inline_display_size": 3,
    "random_seed": 42
  }
}
```

- `full_distribution_max_distinct`: through this limit, every non-missing
  distinct value and its occurrence count are retained in JSON. At `50`, the
  distribution is still complete; at `51`, Tabalyst samples values.
- `candidate_sample_size`: maximum number of distinct values reproducibly sampled
  before final selection.
- `short_text_max_length` and `short_text_percentile`: a column is considered
  short text when this percentile of its sampled lengths does not exceed the
  configured length.
- `short_text_result_size`: **number of values retained for the tooltip when a
  short-text column has more than 50 distinct values.** Its default is `20`.
- `long_text_result_size`: equivalent limit for long text. Its default is also
  `20`.
- `long_text_truncate_at` and `truncation_suffix`: display limit for retained
  long-text values in both JSON and the report.
- `inline_display_size`: number of values shown directly in the `Examples` cell.
  They are always the most frequent retained values.
- `random_seed`: sampling seed, which makes JSON and reports reproducible for the
  same CSV and configuration.

The `Examples` cell shows `+N` for a complete distribution. For a sampled profile,
it shows `++`; the tooltip then shows, for example, `20 / 2,992`, meaning retained
values / actual distinct values. Tooltip values are sorted by descending occurrence
count.

## Enum candidates

```json
{
  "enum_detection": {
    "enabled": true,
    "minimum_row_count": 500,
    "maximum_distinct_values": 49,
    "eligible_types": ["text"],
    "case_sensitive": true
  }
}
```

- `enabled`: turns on optional semantic classification.
- `minimum_row_count`: minimum dataset size before an `enum` candidate is proposed.
- `maximum_distinct_values`: maximum observed non-missing value count. The default
  is `49`.
- `eligible_types`: physical types that can receive the marker; the default limits
  detection to `text` columns.
- `case_sensitive`: decides whether `Open` and `open` are separate values.

`enum` is a semantic hint: its physical type remains `text`. The report exposes
physical and semantic types in separate columns so each can be filtered directly.

## Scan settings

`tabalyst scan` and `tabalyst.generate_scans()` read the `scan` object of each
configuration file. The complete object with its defaults is:

```json
{
  "scan": {
    "csv": {"encoding": "utf-8-sig", "delimiter": ","},
    "json": {"collections": null, "discovery_max_depth": 3},
    "errors": {"policy": "strict", "max_locations": 10},
    "values": {
      "null_markers": [],
      "null_markers_case_sensitive": true,
      "missing": ["absent", "null", "empty", "blank", "marker"]
    },
    "normalization": {
      "nfc": true, "trim": true, "collapse_whitespace": true,
      "casefold": true, "strip_accents": true
    },
    "limits": {
      "max_fields": 10000, "max_depth": 64, "max_record_observations": 100000,
      "max_distinct_per_field": 100000, "max_tracked_values": 2000000,
      "max_stored_value_length": 1000, "max_listed_frequencies": 100,
      "max_samples": 100, "max_variant_groups": 100,
      "max_variants_per_group": 20, "max_evidence_examples": 10
    },
    "types": {"minimum_confidence": 0.95},
    "detection": {"minimum_share": 0.95},
    "detectors": {"number": {"enabled": true}},
    "patterns": [],
    "exposure": {"sensitive_values": "mask"},
    "random_seed": 42
  }
}
```

The scan does not read the top-level `csv` settings: set the delimiter and
encoding in `scan.csv`, or pass `--delimiter` and `--encoding`.

### Layers and merge rules

From lowest to highest priority: built-in defaults, the `scan` object of each
`--config` file in the order given, then `--delimiter`, `--encoding` and
`--collection`.

- Objects merge key by key, including `detectors.<id>`: a file that sets
  `{"detectors": {"number": {"enabled": false}}}` keeps the other number
  settings.
- Lists replace the previous list entirely, such as `null_markers`,
  `patterns` or `collections`.
- Unknown keys are errors.
- `null` is accepted only where a setting allows it; there is no syntax to
  delete a setting.

The scan document embeds the effective configuration and its SHA-256
(`config_sha256`).

### Sources and errors

- `csv.encoding`, `csv.delimiter`: as for reports. The first record is the
  header.
- `json.collections`: `null` for automatic discovery, or a list of absolute
  collection paths such as `"$.customers[]"` or `"$.customers[].orders[]"`.
  Paths must end with `[]`, be unique and not contain one another.
- `json.discovery_max_depth`: how deep automatic discovery looks for arrays
  under a root object.
- `errors.policy`: `strict` stops at the first malformed record, such as a CSV
  record with the wrong number of fields or a JSON object with a duplicate key.
  `tolerant` excludes such records, counts them and marks the scan `partial`.
  Invalid syntax, undecodable text and unreadable files stop the scan in both
  policies.
- `errors.max_locations`: how many record locations each diagnostic lists.

### Values and missing values

- `values.null_markers`: strings that stand for a missing value, such as
  `"N/A"`, compared after trimming surrounding whitespace.
- `values.null_markers_case_sensitive`: set to `false` to match `n/a` too.
- `values.missing`: the categories counted as missing: `absent` (the key or
  column does not exist in a record), `null`, `empty` (`""`), `blank`
  (whitespace only) and `marker`. Every component stays listed in the result.

### Normalization

Each stage can be turned off. They run in this order: `nfc` (Unicode
composition), `trim`, `collapse_whitespace`, `casefold` and `strip_accents`.
The first three produce the analytical value used by listings and detectors;
all stages count the values they change and group variants that become equal,
such as `Montréal` and `MONTREAL`. Raw values are never modified.

### Limits

Limits bound memory and output size. A measure that reaches a limit is marked
`limited` in the result, never estimated. Values above the maximum are
rejected before the scan starts.

| Setting | Default | Maximum | When reached |
| --- | --- | --- | --- |
| `max_fields` | 10,000 | 1,000,000 | New field paths of a dataset are counted but not analyzed. |
| `max_depth` | 64 | 1,000 | Deeper JSON content is counted but not analyzed. |
| `max_record_observations` | 100,000 | 100,000,000 | The record is an error, or excluded under `tolerant`. |
| `max_distinct_per_field` | 100,000 | 50,000,000 | Distinct values of the field stop being stored; frequencies and cardinality become limited. |
| `max_tracked_values` | 2,000,000 | 500,000,000 | Distinct values stored for the whole scan; the largest field is released first. |
| `max_stored_value_length` | 1,000 | 1,000,000 | Longer values are counted, not stored. |
| `max_listed_frequencies` | 100 | 100,000 | Most frequent values listed per field. |
| `max_samples` | 100 | 10,000 | Sample values listed per field. |
| `max_variant_groups` | 100 | 100,000 | Normalization variant groups listed per field. |
| `max_variants_per_group` | 20 | 10,000 | Variants listed per group. |
| `max_evidence_examples` | 10 | 1,000 | Example values per detector state. |

`max_distinct_per_field` cannot exceed `max_tracked_values`. Counters,
statistics and detector coverage stay exact after a limit is reached.

### Types and interpretations

- `types.minimum_confidence`: share of values that must agree for a field to
  get a technical type such as `integer` or `date`, otherwise `mixed`.
- `detection.minimum_share`: share of the values that a detector must match to
  become a candidate interpretation of the field.

### Detectors

Every detector has `enabled` (default `true`) and the settings below. Other
detector ids are errors.

| Detector | Settings and defaults |
| --- | --- |
| `number` | `conventions`: `["dot", "comma"]`, the decimal separators accepted; `ambiguous_convention`: `null`, or `dot` or `comma` to read values such as `1,234` one way. |
| `date` | `orders`: `["YMD", "MDY", "DMY"]`; `separators`: `["-", "/", "."]`; `ambiguous_order`: `null`, or `MDY` or `DMY` to read values such as `02/03/2025` one way; `month_languages`: `["en", "fr"]`. |
| `boolean` | `pairs`: `[["true", "false"], ["yes", "no"], ["y", "n"], ["oui", "non"], ["vrai", "faux"]]`. |
| `enumeration` | `minimum_values`: 500; `maximum_distinct`: 49; `case_sensitive`: `true`. |
| `email` | `max_tracked_domains`: 10,000; `max_listed_domains`: 20. |
| `url` | `schemes`: `["http", "https", "ftp"]`; `www`: `true`, accept addresses starting with `www.`; `max_tracked_hosts`: 10,000; `max_listed_hosts`: 20. |
| `phone` | `regions`: `["nanp", "fr"]`; `nanp` covers Canada and the United States. |
| `postal_code` | `regions`: `["ca", "us"]`, Canadian postal codes and ZIP codes. |
| `currency` | `conventions` and `ambiguous_convention`, as for `number`. |
| `percentage` | `conventions` and `ambiguous_convention`, as for `number`. |
| `quantity` | `conventions` and `ambiguous_convention`, as for `number`; `max_tracked_units`: 10,000; `max_listed_units`: 20. |
| `uuid` | No other setting. |
| `ip_address` | `versions`: `["ipv4", "ipv6"]`. |

Ambiguous values are never resolved from other values of the field: only
`ambiguous_convention` and `ambiguous_order` resolve them.

### Patterns

`patterns` adds your own detectors, reported as `pattern:<id>`:

```json
{
  "scan": {
    "patterns": [
      {
        "id": "customer_number",
        "regex": "C-\\d{4}",
        "description": "Customer number",
        "accepts": ["string"],
        "sensitive": false,
        "max_input_length": 256
      }
    ]
  }
}
```

- `id`: 1 to 64 letters, digits, `_` or `-`, unique.
- `regex`: a Python regular expression of at most 1,000 characters that must
  match the whole value.
- `accepts`: native types tested, among `string`, `integer`, `number` and
  `boolean`; default `["string"]`.
- `sensitive`: `true` masks the fields where the pattern matches.
- `max_input_length`: longer values are not tested; default 256, at most
  10,000.

At most 200 patterns. Regular expressions run without a timeout: use only
patterns you trust, since some expressions can take a very long time on some
values.

### Sensitive values and sampling

- `exposure.sensitive_values`: how values of sensitive fields (email
  addresses, phone numbers, IP addresses and sensitive patterns) appear in the
  result. `mask` (default) replaces letters with `A` or `a` and digits with
  `9`; `hide` removes the values and keeps the counts; `show` keeps them.
- `random_seed`: seed of the value samples, so that two scans of the same file
  with the same settings are identical.
