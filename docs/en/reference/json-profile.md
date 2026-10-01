---
title: JSON profile
description: Structure of the JSON profile written by tabalyst report, with its top-level fields, column profiles, issue codes and format versioning.
---

Each `tabalyst report` run writes a JSON profile next to the HTML report, with
the same name: `orders.html` comes with `orders.json`. For a JSON source, the
default names are `orders.report.html` and `orders.report.json`, so the profile
never replaces the source. The profile holds the
complete analysis result; the HTML report is rendered from it. Use it to read
Tabalyst results from scripts or other tools.

The format is **experimental**: it can change incompatibly between releases.
Always check `format_version` and `format_revision` first. This page describes
format `0.1.0a`, revision `9`.

## Example

A shortened profile for a five-row `orders.csv`:

```json
{
  "format_version": "0.1.0a",
  "format_revision": 10,
  "generated_at": "2026-09-25T22:25:07.873024Z",
  "processing_seconds": 0.0098,
  "source": {
    "filename": "orders.csv",
    "format": "csv",
    "size_bytes": 274,
    "sha256": "7d426449e1217d4dbcad1e7e4c862d360c63d927cb775caa48007d70ac36c0c8",
    "encoding": "utf-8-sig",
    "delimiter": ","
  },
  "config": { "...": "effective report and scan settings" },
  "datasets": [
    {
      "id": "rows",
      "kind": "table",
      "summary": {
        "row_count": 5,
        "column_count": 6,
        "missing_count": 2,
        "duplicate_row_count": 1,
        "with_issues_column_count": 2
      },
      "date_summary": { "...": "present when a column contains dates" },
      "columns": [
        {
          "id": "column_3",
          "name": "amount",
          "path": "amount",
          "position": 3,
          "inferred_type": "mixed",
          "type_counts": { "number": 3, "text": 1 },
          "type_confidence": 0.75,
          "missing_count": 1,
          "missing_percent": 20.0,
          "with_issues": true,
          "distinct_count": 3,
          "examples": ["25.00", "12.50", "not available"],
          "semantic_type": null,
          "detectors": [
            {
              "id": "number",
              "status": "complete",
              "primary": false,
              "eligible_count": 4,
              "matched_count": 3,
              "matched_percent": 75.0,
              "ambiguous_count": 0,
              "invalid_count": 0,
              "formats": []
            }
          ]
        }
      ],
      "issues": [
        {
          "code": "duplicate_rows",
          "severity": "warning",
          "message": "Duplicate rows beyond their first occurrence",
          "count": 1,
          "column_ids": [],
          "row_numbers": [4]
        }
      ],
      "preview": [
        {
          "row_number": 1,
          "values": ["001", "Alice", "12.50", "2026-01-01", "true", "First order"],
          "absent": []
        }
      ],
      "limits": {
        "measures": [],
        "untracked_observations": 0,
        "depth_truncated_observations": 0,
        "diagnostics": []
      },
      "structure": null
    }
  ]
}
```

## Top-level fields

| Field | Type | Content |
| --- | --- | --- |
| `format_version` | string | Experimental format family, `"0.1.0a"`, retained during beta |
| `format_revision` | integer | Revision within the family, increased for each structural or semantic change |
| `generated_at` | string | UTC date and time of the analysis (ISO 8601) |
| `processing_seconds` | number | Scan and profile time, in seconds; for a report built from a scan document with `--scan`, the scan duration recorded in the document plus the time to read it and build the profile |
| `source` | object | The analyzed file (see below) |
| `config` | object | The effective settings, after merging defaults, the configuration files and command options: `string_analysis`, `value_examples` and `scan`, the complete scan configuration; for a report built from a scan document, `scan` is the configuration recorded in it. See the [configuration](configuration.md) |
| `datasets` | array | One profile per dataset of the file (see below) |

## `source`

| Field | Content |
| --- | --- |
| `filename` | File name, without folder |
| `format` | `csv` or `json` |
| `size_bytes` | File size in bytes |
| `sha256` | SHA-256 hash of the file, to check that two profiles describe the same file |
| `encoding` | Text encoding used to read the file |
| `delimiter` | Field delimiter used to read the file; `null` for JSON files |

## `datasets`

A CSV file has one dataset, `rows`, whose records are the rows of the file. A
JSON file has one dataset per collection found by the scan, such as
`$.customers[]`, and the dataset `$` for the rest of the document, listed only
when it holds values outside the collections. See the
[scan format](scan-format.md) for how collections are chosen.

| Field | Type | Content |
| --- | --- | --- |
| `id` | string | Dataset identifier: `rows`, `$` or a collection path such as `$.customers[]` |
| `kind` | string | `table` (CSV), `document` or `collection` (JSON) |
| `summary` | object | Dataset-level counts (see below) |
| `date_summary` | object or `null` | Dataset-level date counts, when at least one column contains date values |
| `columns` | array | One profile per column, in file order for CSV and in order of discovery for JSON |
| `issues` | array | Detected problems (see below) |
| `preview` | array | The first records, with raw values; values of sensitive columns are masked or hidden |
| `limits` | object | Measures stopped by a scan limit, structural truncation and scan diagnostics (see below) |
| `structure` | object or `null` | Paths of a JSON dataset, containers included (see below); `null` for CSV files |

In a JSON dataset, a column is a field that holds strings, numbers, booleans
or nulls, named by its path: `email`, `address.city`, `orders[].total`.
Objects and arrays themselves are not columns, except the ones kept whole at
the `scan.json.flatten.max_depth` limit, which are columns of type `complex`.
A row is a record of the dataset.

## `summary`

Counts over the whole dataset:

- size: `row_count` (records), `column_count`, `cell_count` (the places a
  value could be: one per row and column for CSV; for JSON, the occurrences
  of each field plus the objects where it is absent);
- missing values: `missing_count`, `missing_percent`;
- normalization: `trim_count`, `collapse_internal_whitespace_count`;
- structure: `duplicate_row_count`, `empty_row_count`, `empty_column_count`,
  `constant_column_count`, `with_issues_column_count`;
- `duplicate_row_status`: `complete`; `limited` when more distinct rows than
  `scan.limits.max_tracked_records` were read, `duplicate_row_count` then
  being a lower bound; or `disabled` when `scan.records.duplicates` is
  `false`, `duplicate_row_count` then being `null`;
- column families: `numeric_column_count`, `date_column_count`,
  `string_column_count`;
- type distributions: `inferred_type_counts`, `inferred_type_percents`,
  `semantic_type_counts`, `semantic_type_percents`.

Percentages are numbers from 0 to 100.

## `columns`

Each column profile always contains:

| Field | Content |
| --- | --- |
| `id` | Stable identifier from the position, such as `column_3`. Use it rather than `name`, which can be blank or repeated |
| `name` | Header text for CSV; the field path for JSON |
| `path` | Field path as displayed by the scan: the header text for CSV, a path such as `orders[].total` for JSON |
| `position` | Position in the file for CSV, in order of discovery for JSON, starting at 1 |
| `inferred_type` | `empty`, `complex`, `boolean`, `integer`, `number`, `date`, `text` or `mixed`. A column of dates is `date` even with several formats or ambiguous values. `complex` is a JSON column whose present values are all objects or arrays kept whole at the flatten limit; `type_counts` then counts `object` and `array` |
| `type_counts` | Number of present values of each type |
| `type_confidence` | Share of present values accepted by the inferred type, from 0 to 1. For `mixed` columns, the share of the largest type family; `null` for `empty` columns |
| `type_error_count`, `type_error_percent` | Values outside the inferred type; `null` for `mixed` columns |
| `missing_count`, `missing_percent` | Missing cells; for JSON, also the objects where the field is absent |
| `with_issues` | `true` when the column has missing values, its type is `mixed` or it holds ambiguous dates |
| `normalization` | Values changed by each normalization stage and the variant groups (see below); missing cells are not counted |
| `distinct_count` | Number of distinct values after normalization, even for a masked column; `null` when a scan limit stopped the count |
| `examples` | A few representative values |
| `value_profile` | Value occurrences, complete or sampled (see `selection`) |
| `semantic_type` | `date` for date columns, otherwise the id of the scan's primary interpretation, such as `enumeration`, `email`, `phone` or `postal_code`, or `null` |
| `exposure` | `mask`, `hide` or `show` for a sensitive column, the way its values appear in `examples`, `value_profile` and `preview`; `null` otherwise |
| `detectors` | The detectors that recognized values of the column, in scan order (see below); empty when none did |
| `scan_details` | Bounded field evidence retained from the exposed Scan result: presence, native types, missing breakdown, first and last values, string characteristics and lengths, numeric statistics, boolean counts and temporal ranges. See below |

`value_profile.selection` is `complete` when all available frequencies are
listed. A primary `enumeration` keeps this complete list even above
`value_examples.full_distribution_max_distinct`, if the Scan frequency measure
is complete. Otherwise the profile uses a bounded diverse or random sample.

Depending on the column, these objects are also present (otherwise `null`):

| Field | Present for | Content |
| --- | --- | --- |
| `numeric` | `integer` and `number` columns with finite values | `minimum`, `maximum`, `range`, `mean`, `median` (`null` when a scan limit stopped it), over every number of the column, including decimal commas such as `12,5` |
| `date_profile` | Columns containing date values, whatever their type | Valid, ambiguous and invalid counts, detected formats and their breakdown, and `ambiguity_evidence`: the number of unambiguous values per day-month order (`DMY`, `MDY`), shown but never applied. `resolved_ambiguous_order` is set only by `scan.detectors.date.ambiguous_order` |
| `string_profile` | `text` columns | Length statistics, length distribution and representative examples |

## `normalization`

What the scan's normalization did to the present values of the column. Raw
values are never changed.

| Field | Content |
| --- | --- |
| `trim_count`, `trim_percent` | Values changed by trimming surrounding whitespace |
| `collapse_internal_whitespace_count`, `collapse_internal_whitespace_percent` | Values changed by collapsing repeated internal whitespace |
| `stages` | One item per stage, in order: `raw`, `nfc`, `trim`, `collapse_whitespace`, `casefold`, `strip_accents` (see below) |
| `variant_group_count` | Normalized values written in at least two raw ways; `null` unless `variant_group_status` is `complete` |
| `variant_group_status` | `complete`, `limited` when a scan limit stopped the count, or `not_applicable` without text values |
| `variant_groups` | The largest groups (`scan.limits.max_variant_groups`), each with its comparison `key`, its occurrence `count`, `distinct_count` (raw spellings), `variants` (`value` and `count`, at most `scan.limits.max_variants_per_group`) and `truncated`; masked for a sensitive column, empty when hidden |
| `variant_groups_truncated` | `true` when more groups exist than are listed |

Each item of `stages` has:

| Field | Content |
| --- | --- |
| `stage` | Stage name; `raw` describes the values as read |
| `enabled` | `false` when the stage is turned off in `scan.normalization` |
| `changed_count`, `changed_percent` | Values the stage changed, given the previous enabled stage; `null` for `raw` and disabled stages |
| `distinct_count` | Distinct values after the stage; `null` unless `distinct_status` is `complete` |
| `distinct_status` | `complete`, `limited`, `not_applicable` (no values) or `disabled` |

A variant group is an analytical equivalence, such as `Montréal`,
`montreal` and `MONTREAL`, not proof that the values mean the same thing.

## `detectors`

Each item describes what one scan detector recognized in the column. The
detectors that matched values or found ambiguous or invalid ones are listed,
as well as failed ones.

| Field | Content |
| --- | --- |
| `id` | Detector id, such as `email`, `date` or `pattern:order_id` |
| `status` | `complete`, or `failed` when the detector stopped with an error |
| `primary` | `true` for the scan's primary interpretation, shown as `semantic_type` |
| `eligible_count` | Values the detector could examine |
| `matched_count`, `matched_percent` | Values recognized, and their share of the eligible values |
| `ambiguous_count` | Values with more than one reading, such as `01/02/2026` |
| `invalid_count` | Values with the right shape but an impossible content, such as `2026-02-30` |
| `formats` | Formats found, each with `format`, `count` and `percent` of the eligible values |
| `coverage` | Complete Scan coverage, including tested, not tested and not matched counts; `null` for a failed detector |
| `evidence` | Bounded exposed examples for matched, ambiguous, invalid and not matched values; `null` for a failed detector |
| `details` | Detector-specific, exposure-controlled Scan metadata |
| `adaptive` | Adaptive detection skip and probe metadata, when applicable |

## `scan_details`

The standalone column pages use these Scan facts when present. `first` and
`last` retain the record number and scalar type; their values, detector
evidence and detector details use the same `mask`, `hide` or `show` policy as
the rest of the profile. `string_lengths`, `numeric`, `booleans` and `temporal`
are `null` when the corresponding Scan measure is unavailable. The complete
Scan document has other fields and statuses; `scan_details` is a bounded
selection, not a copy of the Scan document.

## `issues`

Each issue has a `code`, a `severity` (`warning` or `info`), an English
`message`, a `count`, the affected `column_ids` and up to 10 `row_numbers`.
Row numbers count the records of the dataset from 1; a CSV header is not
counted.

| `code` | Severity | Meaning |
| --- | --- | --- |
| `duplicate_rows` | warning | Rows repeating an earlier row, beyond its first occurrence |
| `missing_values` | warning | Missing cells |
| `empty_columns` | warning | Columns without any present value |
| `mixed_types` | warning | Columns with mixed value types |
| `ambiguous_dates` | warning | Date values matching more than one day-month order |
| `ambiguous_headers` | warning | Blank or repeated column names |
| `constant_columns` | info | Columns with a single distinct present value |
| `trimmed_cells` | info | Cells changed by trimming surrounding whitespace |
| `collapsed_whitespace` | info | Cells changed by collapsing repeated internal whitespace |
| `limited_measures` | info | Columns with measures stopped by a scan limit |
| `excluded_records` | warning | Records excluded by the `tolerant` error policy, not analyzed |
| `variant_groups` | info | Values written in several ways that normalization compares as equal |

An issue is listed only when its count is above zero, except `trimmed_cells`
and `collapsed_whitespace`, which are always listed.

## `preview`

The first records of the dataset (10 by default, set by `scan.records.preview`
in the [configuration](configuration.md)), each with its `row_number` and raw `values`
in column order. The preview size does not affect the analysis, which always
reads every record. In sensitive columns, values are masked (`mask`) or `null`
(`hide`), as given by the column's `exposure`; missing cells stay as read.

For JSON, a field absent from the record is `null` and its position (from 0)
is listed in `absent`. A field under an array, such as `tags[]`, joins the
values of the record with `, `. A JSON `null` is the text `null`.

## `limits`

What the scan could not measure completely in the dataset. A limited measure
is never estimated.

| Field | Content |
| --- | --- |
| `measures` | One item per limited measure: `column_id` and `path` of its field (both `null` for a measure of the dataset), `measure` (its place in the scan result, such as `values.cardinality`, `numeric.median` or `structure.paths`), `reason` (such as `distinct_limit`, `global_budget`, `value_too_long`, `field_limit` or `record_budget`), `limit` and `lower_bound`, a proven minimum or `null` |
| `untracked_observations` | Values under paths beyond `scan.limits.max_fields`, counted but not analyzed |
| `depth_truncated_observations` | Values deeper than `scan.limits.max_depth`, counted but not analyzed |
| `diagnostics` | The scan diagnostics of this dataset and of the whole scan: `code`, `level` (`error` or `warning`), `message`, `count`, `dataset` (`null` for the whole scan), `path`, `detector` and up to `scan.errors.max_locations` `locations` (`record`, and `line` for CSV or `element` for JSON) |

## `structure`

The shape of a JSON dataset; `null` for CSV files.

| Field | Content |
| --- | --- |
| `record_types` | Number of records of each native type, such as `{"object": 60}` |
| `path_count` | Number of paths; `null` when `path_status` is `limited` |
| `path_status` | `complete`, or `limited` when the dataset has more paths than `scan.limits.max_fields` |
| `max_depth_seen` | Depth of the deepest analyzed value |
| `fields` | One item per path, in order of discovery, containers included (see below) |

Each item of `fields` has:

| Field | Content |
| --- | --- |
| `id` | Scan field id |
| `path` | Path from the record, such as `orders[].total` |
| `depth` | Number of path segments: `orders[].total` has depth 3 |
| `parent` | Path of the parent field, `null` at the record root |
| `native_types` | Occurrences of each JSON type: `object`, `array`, `string`, `integer`, `number`, `boolean`, `null` |
| `occurrences` | Values found at the path |
| `parent_type` | `record`, `object`, or `array` for array items |
| `parent_count`, `present_count`, `absent_count` | Parents that could hold the field, those that do and those that do not; `absent_count` is `null` for array items |
| `present_percent` | Share of the parents holding the field; `null` for array items, which count elements |
| `collection` | For an array analyzed as its own dataset, the id of that dataset |
| `arrays` | For arrays: `count`, `empty_count`, `minimum_length`, `maximum_length`, `mean_length` and `item_count`; `null` otherwise |
| `column` | `true` when the field is also listed in `columns` |

## Versioning

- `format_version` names the experimental format family. It stays `"0.1.0a"`
  during beta.
- `format_revision` increases for each structural or semantic change. It does
  not change for report styling or performance improvements.
- Revisions can be incompatible, and no migration is provided. See the
  [profile format changelog](profile-format-changelog.md).

The profile contains values from the source file, in `examples`,
`value_profile` and `preview`; only sensitive columns are masked. Share it as
you would share the data.
