---
title: Configuration
description: Reference for the JSON configuration file read by tabalyst report, tabalyst sample, tabalyst scan and the Python API.
---

Tabalyst reads strict JSON configuration files. JSON does not allow comments;
this page is the descriptive reference for supported settings. Commands load
the files passed with `--config`, and the Python API those passed with
`config_path`; no file is loaded automatically. `tabalyst.json` is only a
conventional name.

One file can configure every command. The `scan` object holds the analysis
settings, read by `tabalyst scan` and `tabalyst report`, described in
[Scan settings](#scan-settings). The top level holds the presentation settings
of the report and the CSV settings of `tabalyst sample`:

```json
{
  "string_analysis": {"examples_per_length": 5},
  "csv": {"delimiter": ";"},
  "scan": {
    "csv": {"delimiter": ";"},
    "values": {"null_markers": ["N/A"]},
    "records": {"preview": 20}
  }
}
```

Every command validates the whole file, including the sections it does not
use, so a misspelled or unknown setting is always an error. Explicit
command-line values, such as `--delimiter` and `--encoding`, are the final
override.

## Report settings

The report is built on Tabalyst Scan: it reads the CSV and analyzes it with the
`scan` settings, then presents the result with the settings below.

```json
{
  "string_analysis": {
    "very_short_max_length": 5,
    "short_max_length": 20,
    "medium_max_length": 50,
    "long_max_length": 255,
    "length_distribution_max_length": 50,
    "examples_per_length": 10
  },
  "value_examples": {
    "full_distribution_max_distinct": 50,
    "short_text_max_length": 20,
    "short_text_percentile": 0.95,
    "short_text_result_size": 20,
    "long_text_result_size": 20,
    "long_text_truncate_at": 30,
    "truncation_suffix": "...",
    "inline_display_size": 3
  }
}
```

### Preview

The report shows the preview of the scan: its first `scan.records.preview`
records, 10 by default (see [Records](#records)). It never limits analysis of
the complete file. Values of sensitive columns are masked or hidden in the
preview as in the rest of the report (see
[How the report uses the scan settings](#how-the-report-uses-the-scan-settings)).

### String analysis

Present values in `text` columns are classified from their maximum length as
`very_short`, `short`, `medium`, `long` or `very_long`. A fixed length is
recorded separately when minimum and maximum match. Missing values do not
contribute to lengths. Mean and median length are calculated for every text
column; the report leaves them blank when the fixed length already conveys the
same information.

When the column maximum is at most `length_distribution_max_length`, JSON also
contains the exact occurrence count of every observed length. Each length lists
up to `examples_per_length` example values, taken from the most frequent values
of the column, then from its sampled values. `distinct_length_count` remains
available for every text column, including columns whose distribution is
omitted. The report orders length groups by occurrence and shows three examples
per length in its String analysis tooltip.

### Examples and value profiles

- `full_distribution_max_distinct`: through this limit, every present distinct
  value and its occurrence count are retained in JSON. At `50`, the
  distribution is still complete; at `51`, Tabalyst selects values among a
  reproducible sample of the distinct values, whose size is
  `scan.limits.max_samples` and whose seed is `scan.random_seed`.
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

The `Examples` cell shows `+N` for a complete distribution. For a sampled profile,
it shows `++`; the tooltip then shows, for example, `20 / 2,992`, meaning retained
values / actual distinct values. Tooltip values are sorted by descending occurrence
count. For a sensitive column, the cell shows `masked` or `hidden` instead, and
the tooltip lists masked values.

### How the report uses the scan settings

| Report behavior | Scan settings |
| --- | --- |
| Reading the CSV | `scan.csv`, `--delimiter`, `--encoding` |
| Missing cells | `scan.values`: `null_markers`, `null_markers_case_sensitive` and `missing` |
| Normalization counts and distinct values | `scan.normalization`: `nfc`, `trim`, `collapse_whitespace` |
| Inferred types | `scan.types.minimum_confidence`, with the `number` and `date` detectors |
| Date analysis | `scan.detectors.date` |
| Semantic types | `scan.detection.minimum_share` and every detector |
| Masked values | `scan.exposure.sensitive_values` |
| Preview | `scan.records.preview` |
| Duplicate rows | `scan.records.duplicates` and `scan.limits.max_tracked_records` |

- **Dates.** A column whose present values are dates is `date`, even with
  several formats or ambiguous values. Ambiguous values such as `02/03/2025`
  are never resolved from other values of the column: the report counts them
  as ambiguous, shows how many unambiguous values use each order and, when only
  one order appears, suggests setting `scan.detectors.date.ambiguous_order`.
  The `ambiguous_dates` issue counts them.
- **Semantic types.** `date` for date columns, otherwise the scan's primary
  interpretation: the only detector matching at least
  `scan.detection.minimum_share` of the present values, such as `enumeration`,
  `email`, `phone` or `postal_code`. `number` and `boolean` are not repeated as
  semantic types.
- **Sensitive values.** Columns where a sensitive detector matches, such as
  email addresses and phone numbers, are masked by default in examples, value
  profiles and the preview: `jane@example.com` becomes `aaaa@aaaaaaa.aaa`. Set
  `scan.exposure.sensitive_values` to `show` to keep the values, or `hide` to
  remove them.
- **Limits.** When a scan limit stops a measure, such as the distinct values
  of a column with more than `scan.limits.max_distinct_per_field` of them, the
  report shows `limited` instead of a number and lists the column in the
  `limited_measures` issue.
- **Duplicate rows.** With more distinct rows than
  `scan.limits.max_tracked_records`, the duplicate count is a lower bound,
  shown as `≥ 12`. With `scan.records.duplicates` set to `false`, duplicates
  are not checked and the report shows `–`.

The report reads the `scan.csv` settings, not the top-level `csv` settings. When
a file sets both with different values, the report stops with an error, since
the file would otherwise be read with settings it does not expect; a value
given with `--delimiter` or `--encoding` always wins. The report also needs
every column: a CSV wider than `scan.limits.max_fields` is an error.

A report built from a scan document with `tabalyst report --scan` uses the
settings recorded in the document. Its configuration files still give the
presentation settings; settings given in their `scan` object must have the
values recorded in the document, otherwise the report stops with an error (see [Report from a scan](../how-to/scan-files.md#report-from-a-scan)).

### Settings moved to `scan`

These top-level settings are rejected with a message naming their new location:

| Former setting | New location |
| --- | --- |
| `missing_values` | `scan.values.null_markers` for markers such as `"N/A"`; empty and whitespace-only cells are missing by default (`scan.values.missing`) |
| `normalization.trim` | `scan.normalization.trim` |
| `normalization.collapse_internal_whitespace` | `scan.normalization.collapse_whitespace` |
| `date_detection` | `scan.detectors.date` |
| `type_inference.minimum_confidence` | `scan.types.minimum_confidence` |
| `enum_detection` | `scan.detectors.enumeration`: `maximum_distinct_values` is `maximum_distinct`, and `minimum_row_count` is `minimum_values`, which counts present values, not rows |
| `value_examples.candidate_sample_size` | `scan.limits.max_samples` |
| `value_examples.random_seed` | `scan.random_seed` |
| `preview_rows` | `scan.records.preview`, now up to 1,000 |

## Sample settings

```json
{
  "csv": {
    "encoding": "utf-8-sig",
    "delimiter": ","
  }
}
```

- `csv.encoding`: source-file encoding for `tabalyst sample`. The default
  accepts UTF-8 with or without a BOM; `cp1252` is useful for some
  Windows-produced files.
- `csv.delimiter`: single-character separator, a comma by default.

## Scan settings

`tabalyst scan`, `tabalyst report` and their Python functions read the `scan`
object of each configuration file. The complete object with its defaults is:

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
      "max_variants_per_group": 20, "max_evidence_examples": 10,
      "max_tracked_records": 2000000, "max_listed_records": 10
    },
    "records": {"preview": 10, "duplicates": true},
    "types": {"minimum_confidence": 0.95},
    "detection": {"minimum_share": 0.95},
    "detectors": {"number": {"enabled": true}},
    "patterns": [],
    "exposure": {"sensitive_values": "mask"},
    "random_seed": 42
  }
}
```

Scans and reports do not read the top-level `csv` settings: set the delimiter
and encoding in `scan.csv`, or pass `--delimiter` and `--encoding`.

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
| `max_tracked_records` | 2,000,000 | 500,000,000 | Distinct records stored for the whole scan to find duplicates, about 80 bytes each; later records are still compared with the stored ones, so duplicate counts become lower bounds. |
| `max_listed_records` | 10 | 10,000 | Record numbers listed per records block. |

`max_distinct_per_field` cannot exceed `max_tracked_values`. Counters,
statistics and detector coverage stay exact after a limit is reached.

### Records

- `records.preview`: how many of the first records each dataset keeps in its
  preview, from 0 to 1,000. Sensitive values are exposed as elsewhere.
- `records.duplicates`: set to `false` to skip duplicate detection, which
  stores one digest per distinct record, up to `limits.max_tracked_records`.
  The duplicate count is then `disabled`.

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
