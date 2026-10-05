---
title: Inspect format
description: Structure of the Inspect file written by tabalyst inspect, with its zones, detection, warnings, the config you may edit, and how Tabalyst reads it.
---

`tabalyst inspect data.json` writes `data.json-inspect.json` beside the source:
a JSON document that says how Tabalyst understands the source and holds the
rules to read it. This page describes format `tabalyst.inspect`, version
`0.1.0a`, revision `1`, kinds `json` and `excel`. The format is **experimental**: it can
change incompatibly between releases. Changes are listed in the
[Inspect format changelog](format-changelog.md). For the commands, see
[Inspect JSON and JSONL files](json.md) and [Inspect Excel workbooks](excel.md).
The kind `json` is described first; [the kind `excel`](#inspect-files-of-workbooks-kind-excel)
follows the same top level with its own `detection` and `config`.

## Top level

```json
{
  "format": "tabalyst.inspect",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "inspect": {
    "kind": "json",
    "tabalyst_version": "0.5.0",
    "generated_at": "2026-10-01T05:34:13Z",
    "note": "Edit only the \"config\" section. ..."
  },
  "source": {
    "name": "orders.json",
    "format": "json",
    "size_bytes": 60720,
    "sha256": "ece53017..."
  },
  "detection": {"...": "see below"},
  "warnings": [],
  "config": {
    "structure": {"dataset_path": "$.customers[]"},
    "flatten": {"enabled": true, "separator": ".", "max_depth": null},
    "arrays": {"mode": "preserve"},
    "errors": {"policy": "strict"}
  }
}
```

The sections always come in this order, with `config` last. The file is UTF-8
with two-space indentation. It holds no absolute path: `source.name` is a file
name, and the other paths point inside the source, such as `$.customers[]`.

| Section | Written by | You edit it | Effect on scans |
| --- | --- | --- | --- |
| `format`, `format_version`, `format_revision` | Tabalyst | No | A version Tabalyst does not read is refused. |
| `inspect` | Tabalyst | No | None. |
| `source` | Tabalyst | No | None: it describes the source when it was inspected. |
| `detection` | Tabalyst | No | None. |
| `warnings` | Tabalyst | No | None. |
| `config` | Tabalyst once, then you | Yes | The rules `tabalyst scan` and `tabalyst report` apply. |

For the same source, the same version of Tabalyst and the same settings, two
inspections write the same file except `inspect.generated_at`.

## `inspect` and `source`

| Key | Meaning |
| --- | --- |
| `inspect.kind` | The kind of Inspect: `json` for JSON, JSONL and NDJSON sources, `excel` for workbooks. |
| `inspect.tabalyst_version` | The version of Tabalyst that wrote the file. |
| `inspect.generated_at` | UTC time of the inspection, the only value that varies. |
| `inspect.note` | A reminder to edit only `config`. |
| `source.name` | File name of the source, with its extension. |
| `source.format` | `json`, `jsonl` for `.jsonl` and `.ndjson` files, or `excel` for `.xlsx` and `.xlsm` files. |
| `source.size_bytes` | Bytes read. |
| `source.sha256` | SHA-256 of every byte read. |

`source.sha256` records the source at inspection time. It is never used to
decide whether a stored scan can be reused.

## `detection`

| Key | Meaning |
| --- | --- |
| `scope.structure` | Always `complete`: candidates, element counts and element types come from reading the whole source. |
| `scope.detail` | Always `bounded`: fields, depths and nesting come from the first records of each candidate. |
| `scope.limits` | The bounds applied: `records` (first records observed per candidate, 1,000) and `fields` (distinct fields tracked per candidate, 1,000). |
| `scope.discovery_max_depth` | How many keys deep arrays were searched, from `scan.json.discovery_max_depth` (default 3). |
| `scope.candidates` | `truncated` when more than 100 arrays were found. Absent otherwise. |
| `root.type` | Type of the root: `object`, `array`, `string`, `number`, `boolean`, `null`, or `lines` for JSONL. |
| `candidates` | The candidate collections, in document order. |
| `selection` | The collection proposed, or none. |
| `lines` | JSONL only. Exact counts of lines: `read` (non-blank), `blank`, `objects`, `invalid`, `not_object`. `invalid` includes lines longer than `scan.limits.max_line_bytes`. |

A **candidate collection** is the root array, or an array reachable from the
root through object keys only, at most `scan.json.discovery_max_depth` keys
deep. Arrays inside the records of a candidate are not candidates: they stay
fields of the records. A JSONL file has one candidate, `$[]`.

| Key of a candidate | Meaning |
| --- | --- |
| `path` | Absolute path, such as `$.customers[]`. |
| `elements` | Exact number of elements; for JSONL, the number of object lines. |
| `element_types` | Exact number of elements per type, among `object`, `array`, `string`, `number`, `boolean`, `null`. |
| `eligible` | `true` when the candidate has at least one element and every element is an object. |
| `ineligible_reason` | Only when not eligible: `empty` or `non_object_elements`. |
| `observation` | Detail from the first records: `records` observed, distinct `fields`, `max_depth` (keys and `[]`), `nested_objects`, `arrays`, and `complete`, `false` when a bound cut the observation. |

A field that first appears after the observed records is absent from
`detection`; the scan finds it. Observations are never exhaustive when
`complete` is `false`.

### Selection

`selection.path` is the collection proposed, or `null`. `selection.basis` says
why:

| `basis` | Meaning |
| --- | --- |
| `root_array` | The root is an array of objects. |
| `jsonl_records` | The source is JSONL and has at least one object line. |
| `only_eligible_candidate` | One candidate is eligible. |
| `dominant_candidate` | Several are eligible and the largest has at least 10 times the elements of the next one, which is given in `selection.over`. |
| `ambiguous` | Several are eligible and none stands out. Nothing is selected. |
| `no_eligible_candidate` | No candidate is eligible, or the root is not an object or an array. Nothing is selected. |
| `candidates_truncated` | More than 100 arrays exist, so the list cannot prove that one stands out. Nothing is selected. |

The names of properties play no part. A tie never selects. When nothing is
selected, `config.structure.dataset_path` is `null` and `tabalyst scan` and
`tabalyst report` stop until you set it.

## `warnings`

A list of entries with `code`, `level` (`warning` or `info`) and `message`,
plus the keys that apply: `path`, `reason`, `count`, and `locations`, a list of
`{"record": n, "line": n}` of at most `scan.errors.max_locations` entries (the
`count` is always complete). Warnings never change how a scan reads the source.

| Code | Level | When | Keys |
| --- | --- | --- | --- |
| `ambiguous_collections` | warning | `basis` is `ambiguous` | `count` of eligible candidates |
| `no_collection` | warning | `basis` is `no_eligible_candidate` | `reason`: `scalar_root`, `no_array` or `no_eligible_array` |
| `candidates_truncated` | warning | The candidate list was cut at 100 | `count` kept |
| `candidate_not_eligible` | info | One per ineligible candidate, for the first 10 only | `path`, `reason` (`empty`, `non_object_elements`) |
| `candidate_not_eligible_truncated` | info | More than 10 candidates are ineligible | `count` of ineligible candidates |
| `invalid_lines` | warning | JSONL lines that are not valid JSON, or too long | `count`, `locations` |
| `non_object_lines` | warning | JSONL lines that are valid JSON but not objects | `count`, `locations` |
| `configured_path_not_found` | warning | After a new inspection, the kept `dataset_path` is not an array of the source | `path` |
| `source_name_mismatch` | info | `source.name` of the existing file differs from the source inspected | `path`: the recorded name |

`no_collection` reasons: `scalar_root` (the root is not an object or an array),
`no_array` (an object with no array reachable through keys) and
`no_eligible_array` (arrays exist and none is eligible, such as an array of
plain values). `configured_path_not_found` is only raised for a path the
candidates can judge: one reachable through keys alone within the discovery
depth. A deeper path, or one that crosses an array, is checked by the scan.

## `config`

The part you edit. Omit a key to keep the default of the layer below
(see [Which setting wins](json.md#which-setting-wins)).

| Key | Type | Default when omitted | Written by Inspect |
| --- | --- | --- | --- |
| `structure.dataset_path` | string or `null` | `null`: not decided | The selection, or `null` |
| `flatten.enabled` | boolean | `true` | The effective value |
| `flatten.separator` | string | `"."` | The effective value |
| `flatten.max_depth` | integer or `null` | `null`: no limit | The effective value |
| `arrays.mode` | string | `"preserve"` | `"preserve"` |
| `errors.policy` | `"strict"`, `"tolerant"` or `null` | `null`: the default of the format | The resolved value, never `null` |

Rules:

- `structure.dataset_path` is an absolute path that starts with `$` and ends
  with `[]`, such as `$.customers[]` or `$["a.b"][]`. For a JSONL source it must
  be `$[]` or `null`. Equal paths in different spellings are the same path.
  Writing `null` does not select the automatic discovery of `tabalyst.scan()`.
- `flatten.separator` is exactly one character that is not a letter, a digit,
  `_`, whitespace, a control character or one of `[ ] " \ $`. It changes the
  names of fields, never the paths of collections, which always use `.`. A key
  that holds the separator is written `["a/b"]`, so a key `a.b` and the nested
  keys `a` then `b` stay two distinct fields.
- `flatten.max_depth` is `null` or an integer from 1 to 1,000. Depth counts
  keys and `[]`: `address` is 1, `address.city` is 2, `orders[].amount` is 3. An
  object or array at that depth is kept whole as a complex value. `enabled:
  false` is a depth of 1.
- `arrays.mode` accepts `preserve` only. `ignore` and `explode` are refused.
- `errors.policy` is `strict` for JSON and `tolerant` for JSONL when it is
  `null`.

A `config` is kept as you wrote it when Inspect runs again: the same keys and
values, nothing added. Every setting that influences the dataset, the fields or
the records analyzed takes part in the identity of a scan.

## Reading an Inspect file

For the file beside a source, Tabalyst validates the top-level `format`,
`format_version` and `format_revision`, `inspect.kind` and `config`; the other
sections are informative, so a damaged `detection` never stops a scan. It
refuses, with exit code `2` and the name of the file:

| Case | Message names |
| --- | --- |
| Not a JSON object, or another `format` | The file |
| A `format_version` or `format_revision` it does not read | Both versions, and the two ways out: edit the file or `tabalyst inspect --force` |
| An unknown or missing `inspect.kind` | The kinds it reads |
| A missing `config`, an unknown key at any depth, a value of the wrong type (a number or boolean written as a string included) or a value outside the supported set | The key, such as `config.flatten.sepator` |

There is no migration during the beta, and Tabalyst never replaces an invalid
file with an automatic choice.

## Stored copy

When a JSON source or a workbook has no Inspect file and nothing on the command line or in a
`--config` file names its collection, `tabalyst scan` and `tabalyst report`
inspect it and keep a copy of the result in Tabalyst's local storage, next to
the stored scan. The copy is rebuilt whenever the source content, the format
version, the version of Tabalyst or the discovery depth (JSON) or header search (Excel)
differ. It is
disposable and is never read when an Inspect file exists beside the source.

## Inspect files of workbooks (kind `excel`)

`tabalyst inspect sales.xlsx` writes `sales.xlsx-inspect.json` with the same
top level, the same zones and the same reading rules as above. Only
`inspect.kind` (`excel`), `source.format` (`excel`), `detection` and `config`
differ.

```json
{
  "format": "tabalyst.inspect",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "inspect": {
    "kind": "excel",
    "tabalyst_version": "0.5.1",
    "generated_at": "2026-10-04T22:36:19Z",
    "note": "..."
  },
  "source": {
    "name": "sales.xlsx",
    "format": "excel",
    "size_bytes": 13344,
    "sha256": "35657227..."
  },
  "detection": {
    "scope": {"structure": "complete", "header_scan_rows": 50},
    "workbook": {"sheets": 3, "tables": 0},
    "candidates": [
      {
        "path": "$.Orders", "kind": "sheet", "sheet": "Orders",
        "visible": true,
        "range": "A4:I124", "header_row": 4, "elements": 120, "eligible": true,
        "observation": {
          "columns": 9, "column_names": ["order_id", "..."],
          "blank_rows": 0, "merged_ranges": 0
        }
      },
      {"path": "$.Notes", "kind": "sheet", "sheet": "Notes", "visible": true,
       "elements": 0, "eligible": false, "ineligible_reason": "no_header"}
    ],
    "selection": {
      "path": "$.Orders", "basis": "dominant_candidate", "over": "$.Regions"
    }
  },
  "warnings": [],
  "config": {"structure": {"dataset_path": "$.Orders", "header_row": null}}
}
```

### `detection` of a workbook

| Key | Meaning |
| --- | --- |
| `scope.structure` | Always `complete`: every sheet and table is read. |
| `scope.header_scan_rows` | Rows searched for the header of a sheet, from its first filled row (50). |
| `scope.candidates` | `truncated` when more than 100 candidates were found. Absent otherwise. |
| `workbook` | The number of `sheets` and of named `tables`. |
| `candidates` | The sheets and named tables, in workbook order; the tables of a sheet follow it. |
| `selection` | The table proposed, or none. |

| Key of a candidate | Meaning |
| --- | --- |
| `path` | `$.Sheet` for a sheet, `$.Sheet.Table` for a named table; a name that is not a plain identifier is quoted, `$["Q1 2026"]`. |
| `kind` | `sheet` or `table`. |
| `sheet`, `table` | The names; `table` only for a named table. |
| `visible` | `false` for a hidden sheet, and for the tables on it. |
| `range` | A1 range of the header and the data, such as `A4:I124`. Absent without a table. |
| `header_row` | The 1-based sheet row of the header. Absent without a table. |
| `elements` | Filled data rows; `0` for a candidate with none. |
| `eligible` | `true` when the candidate has a header and at least one data row. |
| `ineligible_reason` | Only when not eligible: `no_cells`, `no_header`, `no_data_rows` or `has_tables`. |
| `observation` | `columns`, `column_names` (the first 100), `blank_rows` among the data and `merged_ranges` in the table. Absent without a table. |

A sheet that holds named tables is not eligible (`has_tables`): its tables
are. `selection.basis` takes the values of the JSON kind that make sense for a
table: `only_eligible_candidate`, `dominant_candidate` (the largest eligible
table has at least 10 times the data rows of the next one, given in
`selection.over`), `ambiguous`, `no_eligible_candidate` and
`candidates_truncated`. Hidden sheets compete only when no visible table is
eligible. Sheet names play no part, and a tie never selects.

### Warnings of a workbook

The entries have the keys of the JSON kind. `ambiguous_collections`,
`no_collection` (`reason` `no_eligible_table`), `candidates_truncated`,
`candidate_not_eligible`, `candidate_not_eligible_truncated`,
`configured_path_not_found` and `source_name_mismatch` are raised as for
JSON. Five codes are specific to workbooks, all at level `warning`, with the
`path` of the table and a `count`:

| Code | When |
| --- | --- |
| `blocks_not_split` | Blank rows lie among the data of a sheet; `count` of blank rows. |
| `duplicate_headers` | The header repeats names; `count` of repeated names. |
| `blank_headers` | The header leaves cells empty; `count` of empty cells. |
| `merged_cells` | Merged ranges lie in the data; `count` of ranges. |
| `multi_level_header` | Merged cells lie on the header row; `count` of ranges. |

### `config` of a workbook

| Key | Type | Default when omitted | Written by Inspect |
| --- | --- | --- | --- |
| `structure.dataset_path` | string or `null` | `null`: not decided | The selection, or `null` |
| `structure.header_row` | integer or `null` | `null`: the detected row | `null` |

- `structure.dataset_path` is an absolute path with the workbook as root and one
  or two keys: `$.Sales` for a sheet, `$.Sales.Orders` for a named table of that
  sheet. Equal paths in different spellings are the same path
  (`$["Sales"]["Orders"]` is `$.Sales.Orders`). A path that ends with `[]`,
  has three keys or does not start with `$` is refused.
- `structure.header_row` is a 1-based row number (an integer from 1; a string, a
  boolean or `0` is refused) that replaces the detected header row of a sheet.
  It does not apply to a named table. A new file takes it from `scan.excel.header_row`
  of a `--config` file, and writes `null` when there is none.
- `flatten`, `arrays` and `errors` do not exist for a workbook, and an unknown key
  is an error that names it, as in the JSON kind.

`tabalyst scan` and `tabalyst report` apply `config` as the settings
`excel.dataset_path` and `excel.header_row` of the
[scan configuration](../reference/configuration.md#scan-settings). An Inspect
file written for another kind than the source, such as a JSON Inspect file
beside a workbook, is not replaced silently: `tabalyst inspect --force` replaces
it.
