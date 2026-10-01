---
title: Inspect format
description: Structure of the Inspect file written by tabalyst inspect, with its zones, detection, warnings, the config you may edit, and how Tabalyst reads it.
---

`tabalyst inspect data.json` writes `data.json-inspect.json` beside the source:
a JSON document that says how Tabalyst understands the source and holds the
rules to read it. This page describes format `tabalyst.inspect`, version
`0.1.0a`, revision `1`, kind `json`. The format is **experimental**: it can
change incompatibly between releases. Changes are listed in the
[Inspect format changelog](inspect-format-changelog.md). For the commands, see
[Inspect JSON and JSONL files](../how-to/inspect-json-files.md).

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
    "note": "Edit only the \"config\" section. Tabalyst replaces every other section each time it inspects this source."
  },
  "source": {
    "name": "orders.json",
    "format": "json",
    "size_bytes": 60720,
    "sha256": "ece53017421aa38fc11f6f7f07a7ad0168ffe606b098618c8fb1e69c59df1a59"
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
| `inspect.kind` | The kind of Inspect, `json` for JSON, JSONL and NDJSON sources. |
| `inspect.tabalyst_version` | The version of Tabalyst that wrote the file. |
| `inspect.generated_at` | UTC time of the inspection, the only value that varies. |
| `inspect.note` | A reminder to edit only `config`. |
| `source.name` | File name of the source, with its extension. |
| `source.format` | `json`, or `jsonl` for `.jsonl` and `.ndjson` files. |
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
(see [Which setting wins](../how-to/inspect-json-files.md#which-setting-wins)).

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

When a JSON source has no Inspect file and nothing on the command line or in a
`--config` file names its collection, `tabalyst scan` and `tabalyst report`
inspect it and keep a copy of the result in Tabalyst's local storage, next to
the stored scan. The copy is rebuilt whenever the source content, the format
version, the version of Tabalyst or the discovery depth differ. It is
disposable and is never read when an Inspect file exists beside the source.
