---
title: JSON profile
description: Structure of the JSON profile written by tabalyst report, with its top-level fields, column profiles, issue codes and format versioning.
---

Each `tabalyst report` run writes a JSON profile next to the HTML report, with
the same name: `orders.html` comes with `orders.json`. The profile holds the
complete analysis result; the HTML report is rendered from it. Use it to read
Tabalyst results from scripts or other tools.

The format is **experimental**: it can change incompatibly between releases.
Always check `format_version` and `format_revision` first. This page describes
format `0.1.0a`, revision `2`.

## Example

A shortened profile for a five-row `orders.csv`:

```json
{
  "format_version": "0.1.0a",
  "format_revision": 2,
  "generated_at": "2026-09-25T22:25:07.873024Z",
  "processing_seconds": 0.0098,
  "source": {
    "filename": "orders.csv",
    "size_bytes": 274,
    "sha256": "7d426449e1217d4dbcad1e7e4c862d360c63d927cb775caa48007d70ac36c0c8",
    "encoding": "utf-8-sig",
    "delimiter": ","
  },
  "config": { "...": "effective configuration" },
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
      "position": 3,
      "inferred_type": "mixed",
      "type_counts": { "number": 3, "text": 1 },
      "type_confidence": 0.75,
      "missing_count": 1,
      "missing_percent": 20.0,
      "with_issues": true,
      "distinct_count": 3,
      "examples": ["25.00", "12.50", "not available"],
      "semantic_type": null
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
      "values": ["001", "Alice", "12.50", "2026-01-01", "true", "First order"]
    }
  ]
}
```

## Top-level fields

| Field | Type | Content |
| --- | --- | --- |
| `format_version` | string | Format family, `"0.1.0a"` during the alpha |
| `format_revision` | integer | Revision within the family, increased for each structural or semantic change |
| `generated_at` | string | UTC date and time of the analysis (ISO 8601) |
| `processing_seconds` | number | CSV reading and analysis time, in seconds |
| `source` | object | The analyzed file (see below) |
| `config` | object | The effective configuration, after merging defaults, the configuration file and command options. Same structure as the [configuration file](configuration.md) |
| `summary` | object | Dataset-level counts (see below) |
| `date_summary` | object or `null` | Dataset-level date counts, when at least one column contains date values |
| `columns` | array | One profile per column, in file order |
| `issues` | array | Detected problems (see below) |
| `preview` | array | The first rows, with raw values |

## `source`

| Field | Content |
| --- | --- |
| `filename` | File name, without folder |
| `size_bytes` | File size in bytes |
| `sha256` | SHA-256 hash of the file, to check that two profiles describe the same file |
| `encoding` | Text encoding used to read the file |
| `delimiter` | Field delimiter used to read the file |

## `summary`

Counts over the whole dataset:

- size: `row_count`, `column_count`, `cell_count`;
- missing values: `missing_count`, `missing_percent`;
- normalization: `trim_count`, `collapse_internal_whitespace_count`;
- structure: `duplicate_row_count`, `empty_row_count`, `empty_column_count`,
  `constant_column_count`, `with_issues_column_count`;
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
| `name` | Header text |
| `position` | Position in the file, starting at 1 |
| `inferred_type` | `empty`, `boolean`, `integer`, `number`, `date`, `text` or `mixed` |
| `type_counts` | Number of present values of each type |
| `type_confidence` | Share of present values accepted by the inferred type, from 0 to 1. For `mixed` columns, the share of the largest type family |
| `type_error_count`, `type_error_percent` | Values outside the inferred type; `null` for `mixed` columns |
| `missing_count`, `missing_percent` | Missing cells |
| `with_issues` | `true` when the column has missing values or its type is `mixed` |
| `normalization` | Cells changed by whitespace trimming and collapsing |
| `distinct_count` | Number of distinct values after normalization |
| `examples` | A few representative values |
| `value_profile` | Value occurrences, complete or sampled (see `selection`) |
| `semantic_type` | `enum`, `date` or `null` |

Depending on the column, these objects are also present (otherwise `null`):

| Field | Present for | Content |
| --- | --- | --- |
| `numeric` | `integer` and `number` columns with finite values | `minimum`, `maximum`, `range`, `mean`, `median` |
| `date_profile` | Columns containing date values, even when their type is `mixed` | Valid, ambiguous and invalid counts, detected formats and their breakdown |
| `string_profile` | `text` columns | Length statistics, length distribution and representative examples |
| `enum` | Enumeration candidates | Observed distinct values, coverage and confidence |

## `issues`

Each issue has a `code`, a `severity` (`warning` or `info`), an English
`message`, a `count`, the affected `column_ids` and up to 10 `row_numbers`.
Row numbers count data records from 1; the header is not counted.

| `code` | Severity | Meaning |
| --- | --- | --- |
| `duplicate_rows` | warning | Rows repeating an earlier row, beyond its first occurrence |
| `missing_values` | warning | Missing cells |
| `empty_columns` | warning | Columns without any present value |
| `mixed_types` | warning | Columns with mixed value types |
| `ambiguous_headers` | warning | Blank or repeated column names |
| `constant_columns` | info | Columns with a single distinct present value |
| `trimmed_cells` | info | Cells changed by trimming surrounding whitespace |
| `collapsed_whitespace` | info | Cells changed by collapsing repeated internal whitespace |

An issue is listed only when its count is above zero, except `trimmed_cells`
and `collapsed_whitespace`, which are always listed.

## `preview`

The first rows of the file (10 by default, set by `preview_rows` in the
[configuration](configuration.md)), each with its `row_number` and raw `values`
in column order. The preview size does not affect the analysis, which always
reads every row.

## Versioning

- `format_version` names the experimental format family. It stays `"0.1.0a"`
  during the alpha.
- `format_revision` increases for each structural or semantic change. It does
  not change for report styling or performance improvements.
- Revisions can be incompatible, and no migration is provided. See the
  [profile format changelog](profile-format-changelog.md).

The profile contains values from the source file, in `examples`,
`value_profile` and `preview`. Share it as you would share the data.
