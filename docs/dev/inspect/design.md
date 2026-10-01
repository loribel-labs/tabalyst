# Tabalyst Inspect design (JSON Inspect)

Contract of lot JI-1, written on 2026-09-30. It turns the functional
specification of JSON support (private: `tabalyst-gb`,
`TODO/drafts/2026-09-30-json-inspect/2026-09-30-Cahier-des-charges-JSON-Inspect.md`,
"the specification" below) and the scoping decisions of the maintainer into the
contract that the implementation lots JI-2 to JI-10 follow. The identifiers of
the specification (`D01-D18`, `EF-xx`, `ET-xx`, `I-xx`, `CA-xx`, `PO-xx`) are
reused for traceability. The private plan (`tabalyst-gb`,
`IN-PROGRESS/2026-09-30-Plan-JSON-Inspect.md`) holds the lots and their status;
the Scan contract is [../scan/design.md](../scan/design.md), which this document
amends where it says so. The contract tests are in `tests/inspect/`.

**Status.** Gate G1 passed on 2026-09-30: the maintainer validated this
contract, answers included (section 2). The decisions DP-01 to DP-17 are
Accepted, except the numeric parameters of section 15, which stay Deferred to
their measurements (reviewed at gate G2). Accepted is not released: nothing
here is implemented before its lot.

## 1. Scope: Inspect has several kinds

Inspect will exist for several kinds of source. This document designs the
first, **JSON Inspect**: `.json`, `.jsonl` and `.ndjson` sources. CSV Inspect
and others are not designed here and are not implemented, but nothing below may
prevent them. Hence a separation that every lot keeps:

| Layer | Content | Shared by every kind |
| --- | --- | --- |
| Inspect shell | File naming, top-level format triple, zones, `warnings`, `config` projection onto `ScanConfig`, layers, visible file, cache, re-inspection, identity | Yes |
| JSON Inspect | `inspect.kind: "json"`, the JSON content of `detection`, the keys of `config` that only make sense for JSON (`structure`, `flatten`, `arrays`), the event pass, the selection rule | No |

Rules that carry the separation:

- The document says which kind it is (`inspect.kind`). A reader that does not
  know a kind refuses the document (section 4.6).
- The `config` keys of a kind belong to that kind. `errors.policy` is shared;
  `structure`, `flatten` and `arrays` are JSON keys. A future CSV kind would add
  its own keys (such as `csv`) under `config`.
- Code: the shell is `tabalyst.inspector` (`models`, `persistence`,
  `resolution`), the JSON kind is `tabalyst.inspector.json_inspect`
  (`detect`, `parameters`). A second kind adds a sibling package and a branch
  in the shell's dispatch, nothing else.
- Public names that cannot be kind-neutral say so: `tabalyst inspect` accepts
  only the kinds that exist and refuses the others clearly (section 13).

The word "inspection" already appears in `projects/_session.py` (private
project inspection sessions). It is unrelated; Inspect, capitalized, always
means this document.

## 2. Status of decisions

| ID | Topic | Decision | Status |
| --- | --- | --- | --- |
| DP-A | Dataset | One selected dataset by default (`config.structure.dataset_path`); ambiguity suspends Scan and Report (EF-15, EF-16). Several collections remain possible through repeated `--collection` or `scan.json.collections`. | Accepted 2026-09-30 |
| DP-B | Arrays | `arrays.mode = preserve` keeps today's per-element analysis; `ignore` and `explode` are refused. | Accepted 2026-09-30 |
| DP-C | Observation | Inspect reads the whole source in one event pass; candidates and element counts are exact, field details are bounded. | Accepted 2026-09-30 |
| DP-D | Source identity | Full-content hash also for `report --scan`: a present source is always compared by content. | Accepted 2026-09-30 |
| DP-01 | Selection rule | Section 8.4. Amended: eligibility counted over the whole pass; the dominance ratio is a parameter measured before it is fixed. | Accepted (G1) |
| DP-02 | File schema | Section 4. Amended: format triple at the top level; `inspect.kind`; no `source.modified_at`; no confidence score. | Accepted 2026-09-30 (G1) |
| DP-03 | `ScanConfig` mapping | Section 5.4. | Accepted 2026-09-30 (G1) |
| DP-04 | Layers | Section 11.1. Amended: the automatic detection ranks below `--config`; only the detected `dataset_path` is automatic. | Accepted 2026-09-30 (G1) |
| DP-05 | Flatten depth | Section 7. Counting by segments, as `limits.max_depth`; disabled flatten equals depth 1. | Accepted 2026-09-30 (G1) |
| DP-06 | Error policy | Section 5.5. `null` resolves by format. | Accepted 2026-09-30 (G1) |
| DP-07 | Separator, escaping | Section 6. Amended: the separator excludes `_`; the dataset path syntax never uses it. | Accepted 2026-09-30 (G1) |
| DP-08 | Invalid JSON | Section 8.7. | Accepted 2026-09-30 (G1) |
| DP-09 | JSONL rules | Section 9. | Accepted 2026-09-30 (G1) |
| DP-10 | Scan identity | Section 10. | Accepted 2026-09-30 (G1) |
| DP-11 | Observation budget | Section 8.5. Values deferred to a measurement. | Accepted (G1); values Deferred (JI-5) |
| DP-12 | Empty and unsupported shapes | Section 8.6. | Accepted 2026-09-30 (G1) |
| DP-13 | Unresolved configuration | Section 11.4. | Accepted 2026-09-30 (G1) |
| DP-14 | Re-inspection | Section 12.3. Amended: `config` is preserved as a value, not byte for byte. | Accepted 2026-09-30 (G1) |
| DP-15 | Cache | Section 12.4. Amended: no automatic Inspect for JSONL. | Accepted 2026-09-30 (G1) |
| DP-16 | Configured path gone | Section 11.5. | Accepted 2026-09-30 (G1) |
| DP-17 | Older Inspect file | Section 11.6. | Accepted 2026-09-30 (G1) |

Changing a Proposed or Accepted rule later is allowed during the beta, but the
change must update this document and the affected contract tests in the same
lot, with the reason recorded in section 17.

### Questions answered by the maintainer (2026-09-30)

Asked at the end of lot JI-1; every answer is the recommended option. They
settled the points that were open inside the decisions, and the maintainer then
reviewed the document as written and passed gate G1.

| Q | Question | Answer | Where |
| --- | --- | --- | --- |
| Q1 | A single object or a scalar root no longer gives a one-row `$` dataset in the CLI parcours | Confirmed: `no_collection`, Scan and Report suspended; `scan()` keeps `$` | 8.6 |
| Q2 | Selection rule | Strict eligibility plus dominance ratio (value measured in JI-5, decided at G2) | 8.3, 8.4 |
| Q3 | Counting of `flatten.max_depth` | Segments, `[]` included; `enabled: false` equals depth 1 | 7.2 |
| Q4 | Layers | The automatic detection ranks below `--config`; the visible file above it | 11.1 |
| Q5 | `report --scan` on a document of another engine version | Warning only; caches (`current_scan`, projects) are invalidated | 10.2 |
| Q6 | `tabalyst inspect` options and behavior | `--config`, `--reset-config`, `--force`; writes only the visible file; `scan` and `report` never create it | 12.2, 13 |
| Q7 | `config` on re-inspection | Preserved as a value, not byte for byte | 12.3 |
| Q8 | JSONL | Implicit dataset: no automatic Inspect and no cache for JSONL | 11.2 |

## 3. Audit confirmed (JI-1)

The audit of the plan (section 3) was checked against the code of `main`
(0.4.4 prepared). Facts this contract relies on, with the file that holds each:

| Fact | Where | Consequence |
| --- | --- | --- |
| Auto discovery promotes every array reachable through keys at `json.discovery_max_depth` (3) or less, plus a `$` document dataset. A promoted array has at most 3 key segments. | `scanner/readers/json_reader.py` (`keep_abs`) | The candidate rule of section 8.2 is that rule; Inspect and the reader share its definition. |
| Explicit mode `json.collections` requires absolute paths ending in `[]`, rejects overlaps, accepts paths crossing arrays, canonicalizes only the dataset ids. | `scanner/config.py` (`JsonSettings`) | `dataset_path` projects onto it. The stored strings are not canonical: JI-2 canonicalizes them so equal paths hash equal (section 10.3). |
| `config_sha256` is the SHA-256 of the sorted, compact JSON of the complete `ScanConfig`. | `scanner/config.py` | It stays the only configuration identity. |
| `errors.policy` is `strict` or `tolerant`, default `strict`. | `scanner/config.py` | Becomes nullable (section 5.5). |
| The reader hashes every byte while parsing (`HashingStream.drain`). | `scanner/readers/base.py` | Inspect hashes during its own pass; no second read. |
| `compare_source` reads size, then modification time, and hashes only when the time differs. | `scan_reuse.py` | Changes under DP-D (section 10.2). |
| `current_scan` compares size, time, hash and `config_sha256`, never `engine.version`. | `shared_scan_service.py` | Changes under DP-10. |
| The shared cache is `workspaces/<ws>/scans/<hash of the path>/scan.json` under `workspace_writer`, written with `write_text_atomic`. | `projects/location.py`, `batch.py` | `inspect.json` sits beside it (section 12.4). |
| `Location` has `record`, `line`, `element`. CSV uses `line`, JSON `element`. | `scanner/observations.py` | JSONL uses `record` and `line`. |
| Output names: `.report.html` and `.report.json` only for `.json` sources. | `report_service.report_name` | Extended to `.jsonl` and `.ndjson` (JI-4, JI-7). |
| `_open_reader` routes `.json` to JSON and everything else to CSV. | `scanner/api.py` | Extended with `.jsonl` and `.ndjson`, case-insensitive. |

No new dependency is needed: `ijson` for `.json`, the standard `json` module
for each JSONL line.

## 4. The Inspect document

### 4.1 Layout

```json
{
  "format": "tabalyst.inspect",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "inspect": {
    "kind": "json",
    "tabalyst_version": "0.4.4",
    "generated_at": "2026-09-30T10:00:00Z",
    "note": "Edit only the \"config\" section. Tabalyst replaces every other section each time it inspects this source."
  },
  "source": {
    "name": "orders.json",
    "format": "json",
    "size_bytes": 312,
    "sha256": "..."
  },
  "detection": {
    "scope": {
      "structure": "complete",
      "detail": "bounded",
      "limits": {"records": "<RECORDS_OBSERVED>", "fields": "<FIELDS_OBSERVED>"}
    },
    "root": {"type": "object"},
    "candidates": [
      {
        "path": "$.customers[]",
        "elements": 4,
        "element_types": {"object": 4},
        "eligible": true,
        "observation": {
          "records": 4,
          "fields": 12,
          "max_depth": 4,
          "nested_objects": true,
          "arrays": true,
          "complete": true
        }
      }
    ],
    "selection": {"path": "$.customers[]", "basis": "only_eligible_candidate"}
  },
  "warnings": [],
  "config": {
    "structure": {"dataset_path": "$.customers[]"},
    "flatten": {"enabled": true, "separator": ".", "max_depth": null},
    "arrays": {"mode": "preserve"},
    "errors": {"policy": "strict"}
  }
}
```

The numbers in `limits` are the parameters of section 15, shown as symbols
because their values are not fixed yet.

Section order is fixed: `format`, `format_version`, `format_revision`,
`inspect`, `source`, `detection`, `warnings`, `config`. `config` comes last so
the part the user edits is at the end of the file.

### 4.2 Zones

| Zone | Written by | Edited by the user | Effect on Scan identity |
| --- | --- | --- | --- |
| `format`, `format_version`, `format_revision` | Tabalyst | No | None. A version the running Tabalyst does not read is refused (4.6). |
| `inspect` | Tabalyst | No | None. `tabalyst_version` is the engine version, which the identity takes from the running Tabalyst, not from this field. |
| `source` | Tabalyst | No | None. It describes the source at inspection time (I-T01, 11.6). |
| `detection` | Tabalyst | No | None. |
| `warnings` | Tabalyst | No | None. |
| `config` | Tabalyst once, then the user | Yes | Yes, through the `ScanConfig` it projects onto (5.4). |

Nothing in the file is a path other than a path inside the source (`$.a[]`).
`source.name` is a file name, never a directory (D12, EF-08). The document is
written with two-space indentation, UTF-8 without escaping, and a final
newline, like Scan documents.

`detection` is kind-specific. The shell treats it as an opaque JSON object.

### 4.3 `inspect` and `source`

| Key | Type | Meaning |
| --- | --- | --- |
| `inspect.kind` | `"json"` | The Inspect kind. Only `json` exists. |
| `inspect.tabalyst_version` | string | `engine.version` of the Tabalyst that wrote the file (DP-10). |
| `inspect.generated_at` | UTC timestamp | The only volatile value of the file (4.7). |
| `inspect.note` | string | Constant reminder to edit `config` only (EF-04). |
| `source.name` | string | File name of the source, with its extension. |
| `source.format` | `"json"` or `"jsonl"` | The reader used; `.ndjson` is `jsonl`. Not editable: it follows the extension (E7). |
| `source.size_bytes` | integer | Bytes read. |
| `source.sha256` | string | SHA-256 of every byte read (D18, ET-05). |

There is no modification time: it is volatile and carries no decision.

### 4.4 `detection` for JSON Inspect

| Key | Meaning |
| --- | --- |
| `scope.structure` | Always `"complete"`: candidates, element counts and element types come from a pass over every event of the source (DP-C). |
| `scope.detail` | Always `"bounded"`: fields, depths and nesting come from the first records of each candidate only. |
| `scope.limits` | The bounds that were applied: `records` (first records per candidate) and `fields` (distinct field paths per candidate), the parameters of section 15. |
| `root.type` | Native type of the root: `object`, `array`, `string`, `number`, `boolean`, `null`; for JSONL `lines`. |
| `candidates` | Candidate collections in document order (8.2). Empty for a scalar root. |
| `candidates[].path` | Absolute path in canonical spelling. |
| `candidates[].elements` | Exact element count. For JSONL, the number of object records. |
| `candidates[].element_types` | Exact count of elements per native type. |
| `candidates[].eligible` | The eligibility of 8.3. |
| `candidates[].ineligible_reason` | Present only when `eligible` is false: `empty` or `non_object_elements`. |
| `candidates[].observation` | Detail over the first records: `records` observed, distinct `fields` (paths relative to the record, `[]` included, record root excluded), `max_depth` (segments, deepest observed), `nested_objects` and `arrays` (an object, or an array, member exists), `complete` (false when a bound cut the observation). |
| `selection.path` | The collection Inspect proposes, or `null`. |
| `selection.basis` | Why: `root_array`, `jsonl_records`, `only_eligible_candidate`, `dominant_candidate`, `ambiguous`, `no_eligible_candidate`, `candidates_truncated`. |
| `selection.over` | Present for `dominant_candidate`: the path of the next candidate by element count. |
| `lines` | JSONL only (the key is absent for `.json`): `{"read", "blank", "objects", "invalid", "not_object"}`, exact. |

There is **no confidence score** in v1: `selection.basis` is the explanation
(EF-06 allows the notion only "when it is used"). A score would need a
calibration that no measurement supports.

A candidate list is bounded by `MAX_CANDIDATES` (section 15). When more arrays
exist, the first `MAX_CANDIDATES` in document order are kept,
`scope.candidates` is `"truncated"` (the key is absent otherwise) and the
selection is `candidates_truncated`: an incomplete list can never prove that a
collection stands out.

### 4.5 `warnings`

A list of entries, all informative (no effect on identity). An entry holds
`code`, `level` (`warning` or `info`) and `message`, plus the keys that apply:
`path`, `reason`, `count`, `locations` (`[{"record", "line"}]`, at most
`errors.max_locations` entries; `count` is always complete).

| Code | Level | When | Keys |
| --- | --- | --- | --- |
| `ambiguous_collections` | warning | `selection.basis` is `ambiguous` | `count` of eligible candidates |
| `no_collection` | warning | `selection.basis` is `no_eligible_candidate` | `reason`: `scalar_root`, `no_array`, `no_eligible_array` |
| `candidates_truncated` | warning | the candidate list was cut | `count` of candidates kept |
| `candidate_not_eligible` | info | one per ineligible candidate | `path`, `reason` (`empty`, `non_object_elements`) |
| `invalid_lines` | warning | JSONL lines that are not valid JSON | `count`, `locations` |
| `non_object_lines` | warning | JSONL lines that are valid JSON but not objects | `count`, `locations` |
| `configured_path_not_found` | warning | re-inspection: the preserved `dataset_path` is not an array of the new source | `path` |
| `source_name_mismatch` | info | `source.name` of an existing file differs from the source being inspected | `path` is the recorded name |

`no_collection` `reason`: `scalar_root` (the root is not an object or array),
`no_array` (an object root with no array reachable through keys),
`no_eligible_array` (arrays exist, none is eligible). A root array of
primitives is `no_eligible_array`.

### 4.6 Reading a document

| Case | Result |
| --- | --- |
| Not JSON, or not a JSON object | `ConfigurationError`, naming the file. Never replaced silently (I-E01). |
| `format` is not `tabalyst.inspect` | `ConfigurationError`. |
| `format_version` or `format_revision` not the ones of the running Tabalyst | `ConfigurationError` naming both versions and the two ways out: edit the file, or `tabalyst inspect --force` (CA-28, ET-02). No migration during the beta. |
| `inspect.kind` unknown or absent | `ConfigurationError` naming the kinds this Tabalyst reads. |
| `config` absent or not an object | `ConfigurationError`. |
| Unknown key in `config`, at any depth | `ConfigurationError` naming the dotted key (`config.flatten.sepator`). |
| Value of the wrong type, including booleans or numbers written as strings | `ConfigurationError`. No coercion. |
| Value outside the supported set (5.2) | `ConfigurationError` naming the key, the value and what is accepted. |

For a **visible** file, only the top-level triple, `inspect.kind` and `config`
are validated. The other zones are informative and replaced by the next
inspection; a damaged `detection` must not stop a Scan. Tabalyst reads two
values from them when they are present and well formed: `source.sha256` (11.6)
and `source.name` (`source_name_mismatch`). The cache file is machine-written
and validated completely by `InspectDocument` (4.8).

### 4.7 Stability (ET-09, EF-32, CA-27)

For the same source bytes, the same Tabalyst version and the same effective
`ScanConfig` layers, two inspections produce files that are identical except
`inspect.generated_at`. Consequences the implementation keeps:

- Candidates in document order; keys in the fixed order of 4.1; counts in the
  order `object`, `array`, `string`, `number`, `boolean`, `null` for
  `element_types` (only the types seen).
- No set or dictionary iteration order leaks; no random sampling.
- Detail observation uses the first records in reading order.

### 4.8 Models

`tabalyst.inspector.models` holds Pydantic models with `extra="forbid"`:
`InspectDocument` (the whole file), `InspectConfig` (the `config` section) and
the zone models. `InspectConfig.to_scan_layer()` returns the `scan` layer of
5.4. The test-facing interface is listed in section 16.1.

## 5. Configuration (`config`)

### 5.1 Keys and defaults

| Key | Type | Default when omitted | Written by Inspect | Editable |
| --- | --- | --- | --- | --- |
| `structure.dataset_path` | string or `null` | `null` (not decided) | the selection, or `null` | Yes |
| `flatten.enabled` | boolean | `true` | the effective value | Yes |
| `flatten.separator` | string | `"."` | the effective value | Yes |
| `flatten.max_depth` | integer or `null` | `null` (up to the safety limit) | the effective value | Yes |
| `arrays.mode` | string | `"preserve"` | `"preserve"` | Only to the same value |
| `errors.policy` | `"strict"`, `"tolerant"` or `null` | `null` (default of the format) | the resolved value, never `null` | Yes |

Not exposed in v1 (E10, DP-02): `types.mixed_types`,
`nulls.distinguish_missing_and_null`, `structure.record_type`, `limits`. Their
behavior is fixed and documented: mixed types are preserved (EF-23), absent,
`null` and empty string stay distinct (EF-24), JSON records are objects (see
8.6 for other shapes). A key exposed without alternative behavior would be a
promise the engine cannot keep. They can be added in a later revision when a
second behavior exists.

Omitting a key means "no choice": the layers below it apply (11.1). Writing a
key with `null` is a choice for `errors.policy` and `flatten.max_depth` (the
format default, no flatten limit), and the same as omitting for
`structure.dataset_path` (it cannot select the automatic discovery mode, which
the Inspect parcours never uses, DP-A).

### 5.2 Validation

- `structure.dataset_path`: an absolute path ending in `[]`, parsed by the path
  syntax of section 6.1. For a `jsonl` source it must be `$[]` or `null`: a
  JSONL file has one dataset (9.1). Anything else is an error. Equal paths in
  different spellings are accepted and canonicalized (10.3).
- `flatten.enabled`: a boolean.
- `flatten.separator`: exactly one character that is not alphanumeric
  (`str.isalnum()`), not `_`, not whitespace (`str.isspace()`), not a control
  character, and not one of `[ ] " \ $`. The characters that remain include `.`
  `/` `-` `:` `|`.
- `flatten.max_depth`: `null`, or an integer from 1 to the hard cap of
  `limits.max_depth` (1,000). The cap is the existing one, not a new value.
- `arrays.mode`: `"preserve"`. `"ignore"` and `"explode"` are refused with a
  message saying that they are not supported in this version, never accepted
  and silently ignored (EF-22).
- `errors.policy`: `"strict"`, `"tolerant"` or `null`.
- Unknown keys and mistyped values are errors (4.6). Errors name the file and
  the dotted key, as configuration files do today.

### 5.3 What Inspect writes (seed rule)

On a first inspection, `config` is the projection of the **effective
`ScanConfig` below the visible file**, that is the layers defaults, automatic
detection and `--config` files (11.1), plus the detected `dataset_path`. So a
`--config` file that sets `json.flatten.separator` to `/` gives a visible file
with `/`, and the visible file does not silently undo what the user asked for
by `--config`. `errors.policy` is always written resolved: `strict` for a
`.json` source, `tolerant` for a JSONL source, unless a layer says otherwise.

### 5.4 Projection onto `ScanConfig` (DP-03)

The Inspect file is an editable projection of the effective configuration, not
a second configuration system. `InspectConfig.to_scan_layer()` returns the
`scan` layer of the keys that are present:

```json
{"json": {"collections": ["$.customers[]"],
          "flatten": {"enabled": true, "separator": ".", "max_depth": null},
          "arrays": {"mode": "preserve"}},
 "errors": {"policy": "strict"}}
```

- `structure.dataset_path` becomes `json.collections: [path]`, and is left out
  when `null` (5.1).
- `flatten.*` becomes `json.flatten.*`; `arrays.mode` becomes
  `json.arrays.mode`; `errors.policy` is `errors.policy`.
- The layer then merges like any other (`scan_config_from_layer`): objects
  merge, lists replace, unknown keys fail.

`ScanConfig` gains `json.flatten {enabled, separator, max_depth}` and
`json.arrays {mode}`, and `errors.policy` becomes nullable (JI-2). The identity
stays `config_sha256` of the complete resolved `ScanConfig`; the Inspect file
adds no second identity mechanism.

### 5.5 Error policy resolution (DP-06, E6)

`errors.policy: null` means "the default of the format": `tolerant` for JSONL
(D16, EF-25), `strict` for CSV and JSON. One function resolves it, once, before
anything else uses the configuration:

```python
resolve_config_defaults(config: ScanConfig, source_format: "csv" | "json" | "jsonl") -> ScanConfig
```

It returns a configuration where `errors.policy` is never `null` and where an
unused flatten setting is normalized (5.6). `scan()` calls it, records the
result in `result.config`, and computes `config_sha256` from it. `current_scan`,
`scan_reuse` and the project freshness code compute the expected hash from the
same function, so the hash of a `null` policy equals the hash of the resolved
value (ET-06).

### 5.6 Normalization of unused settings (ET-06)

The hash covers "the rules really applied". When `flatten.enabled` is `false`,
`flatten.separator` and `flatten.max_depth` change nothing, so
`resolve_config_defaults` replaces them with `"."` and `null`. Two files that
differ only by those ignored values hash the same. No other setting is
normalized: JSON settings of a CSV scan, or CSV settings of a JSON scan, still
take part in the hash. That is a known cost, simple and safe: such a change
rescans, it never reuses a wrong result.

## 6. Paths, separator and escaping (PO-04, D17, EF-21)

### 6.1 Two syntaxes, one canonical form

The identity of a field is its list of **canonical segments** (`key`, `items`,
`column`), unchanged (Scan design section 4). Two textual syntaxes exist, both
reversible:

| Syntax | Used for | Separator |
| --- | --- | --- |
| Absolute (`$.customers[]`, `$["a.b"][]`) | `dataset_path`, `--collection`, dataset identifiers, `scope.collections` | Always `.` |
| Relative (`orders[].amount`) | Field `display`, hence column names | `flatten.separator` |

The separator therefore never changes how a dataset is addressed: a user who
sets `/` for column names still writes `$.results[]` in `dataset_path`.

### 6.2 Relative syntax with a separator

```text
relative  := ( identifier | quoted | "[]" ) segment*
segment   := SEP identifier | quoted | "[]"
quoted    := "[" json-string "]"
identifier:= [A-Za-z_][A-Za-z0-9_]*
```

`SEP` is `flatten.separator`. With the default it is today's syntax, byte for
byte. A key is written bare only if it matches `identifier`; every other key is
written as a JSON string in brackets. Because the separator cannot be
alphanumeric or `_` (5.2), an identifier never contains it, so "bare when it is
an identifier" is enough: a key holding the separator is always quoted. Hence:

- key `a.b` and key `a` containing `b` stay distinct (`["a.b"]` and `a.b`) with
  the default separator;
- with separator `/`, key `a/b` is `["a/b"]`, nested `a` then `b` is `a/b`, and
  key `a.b` is `["a.b"]` as it is not an identifier;
- the quoted form needs no separator before it, as today (`["é"]["x y"]`).

### 6.3 Functions

```python
format_relative(path, separator=".") -> str
parse_path(text, *, separator=".") -> FieldPath
```

`format_absolute` is unchanged. `parse_path` applies `separator` only to a
relative text; a text starting with `$` is absolute and always uses `.`.
`format_relative` and `parse_path` are inverse functions for every path and
every valid separator (CA-14); two different paths never share a display.

## 7. Flatten (EF-19, EF-20, D11, PO-05)

### 7.1 Current behavior is the default

Today every nested member is a field: `address.city` exists as a field of its
own whatever the depth, up to the safety limit `limits.max_depth` (64). That is
`flatten.enabled: true`, `flatten.max_depth: null`, and it stays the default.
Two limits exist and are different things:

| Limit | Role | Effect at the limit |
| --- | --- | --- |
| `limits.max_depth` | Protection of the reader (existing) | Content deeper is not traversed; `depth_truncated_observations` and the `depth_limit` warning. Data is lost. |
| `flatten.max_depth` | An interpretation choice | The value at the limit is kept whole as a complex value; nothing is lost; no warning. |

### 7.2 Counting

A depth is a number of **segments** (a key or `[]`) from the root of the
record, exactly as `len(path)` and `max_depth_seen` count (DP-05). Examples:
`address` is 1, `address.city` is 2, `tags[]` is 2, `orders[].amount` is 3.

With `flatten.max_depth = N`, a field whose path has at most `N` segments is
developed as usual. A container (object or array) whose path has exactly `N`
segments is observed as a complex value (native type `object` or `array`, with
the array length) and **its children are not observed at all**: no field is
created for them, they are not counted in `depth_truncated_observations`, no
warning is raised. The field of the container is kept, so Report can present it
as a column holding a complex value (JI-3).

`flatten.enabled: false` is `flatten.max_depth = 1`: only the members of the
record are fields; objects and arrays that they hold stay complex values.
Consequence worth knowing: with flatten off, the elements of an array member
(`tags[]`, 2 segments) are not analyzed, but the array itself and its lengths
are. The maintainer confirmed that `[]` counts (Q3).

### 7.3 Arrays (DP-B, EF-22, D10)

`arrays.mode = preserve` adds no row, ever. An array stays a complex value
(`tags`, native type `array`, lengths and emptiness), and, as today, its
elements are analyzed per element (`tags[]`, `orders[].amount`) as long as the
flatten limit allows. No explosion, no conversion to text.

### 7.4 Types and states (EF-23, EF-24)

Unchanged and already true in Scan: native types are exact (`integer`,
`number`, `string`, `boolean`, `null`, `object`, `array`), mixed types are listed
by count, and absent, `null` and empty string are disjoint counters
(`presence.absent`, `native_types.null`, `strings.empty`). A parent that is
`null` or missing leaves its children neither present nor absent (Scan design
section 7); that is the representation of EF-24's "parent absent or null"
case. Contract tests attach to these existing behaviors (section 16.3).

## 8. Detection (EF-05, EF-06, EF-13 to EF-17, D14, D15)

### 8.1 The event pass (DP-C, ET-08)

JSON Inspect reads **every event** of the source once, with the same parser as
the Scan reader (`ijson`; JSONL: one standard `json` parse per line), and
computes the SHA-256 of the same bytes during that read. It builds no records
and no statistics. Consequences:

- Candidates, exact element counts and exact element types cover the whole
  source.
- A syntax error anywhere, even after the observed records, fails the
  inspection (8.7).
- Fields, depths and nesting come from the first records only (8.5).
- The time of Inspect grows with the size of the source: a full parse plus a
  full hash. This is the price of DP-C and D18; it is measured in JI-8, not
  promised here (ET-11).

### 8.2 Candidates

A candidate is a collection that the Scan could analyze as a dataset:

- the root array: `$[]`; or
- an array reachable from the root through **object keys only**, with at most
  `json.discovery_max_depth` key segments (default 3, the value of the layers).

Arrays nested in a candidate's records (`$.customers[].orders[]`) are not
candidates; they remain fields of the candidate's records, as in Scan (design
section 5.2). Candidates never nest or overlap. They are listed in document
order. The path is in canonical spelling (`$["a.b"][]` is how a key holding a
dot appears).

The names of properties play no role: `results`, `data` or `items` get no
preference (PO-01).

### 8.3 Eligibility

A candidate is **eligible** when it has at least one element and every element
is an object. Otherwise it is not, with `ineligible_reason` `empty` (no
element) or `non_object_elements` (at least one element that is not an
object). This uses the exact counts of the whole pass, never a sample.

Why strict: an array that mixes objects and other values is not a table.
Choosing it silently would give a dataset whose record types are mixed; the
user can still select it explicitly (8.6). The maintainer confirmed the strict rule (Q2).

### 8.4 Selection (DP-01, EF-15, EF-16)

Deterministic, over the exact counts:

1. Root is an array. The only candidate is `$[]`. Eligible: selected,
   `root_array`. Otherwise: nothing selected, `no_eligible_candidate`.
2. Root is an object. Let `E` be the eligible candidates.
   - `|E| = 0`: `no_eligible_candidate`.
   - `|E| = 1`: that candidate, `only_eligible_candidate`.
   - `|E| ≥ 2`: let `a` be the one with most elements and `b` the next. If
     `a.elements ≥ DOMINANCE_RATIO × b.elements`, `a` is selected,
     `dominant_candidate`, with `over` = `b`. Otherwise nothing is selected:
     `ambiguous`.
3. Root is a scalar: no candidate, `no_eligible_candidate`.
4. The candidate list was truncated (4.4): `candidates_truncated`, unless the
   root is an array.
5. A JSONL source: the dataset is implicit (9.1): `jsonl_records` when at least
   one line is an object, `no_eligible_candidate` otherwise.

`DOMINANCE_RATIO` is a parameter, not a constant of this document: a number
greater than 1 fixed by a measurement (section 15). A tie never selects.
Ineligible candidates are listed but never compete: `{"results": [objects],
"tags": ["a", "b"]}` selects `results`.

When nothing is selected, `config.structure.dataset_path` is `null` and the
file says why (`basis`, `warnings`). Scan and Report refuse to continue
(11.4); no collection is ever picked to let the work go on (D14).

### 8.5 Detail observation budget (DP-11, PO-03)

Per candidate, over the first `RECORDS_OBSERVED` records, Inspect tracks
`fields` (distinct relative field paths, at most `FIELDS_OBSERVED`),
`max_depth`, `nested_objects` and `arrays`. `observation.complete` is `false`
as soon as a bound cut something: more records than observed, or more fields
than tracked. `max_depth` is exact for the records observed and is not bounded.
Memory depends on these parameters and `MAX_CANDIDATES`, not on the source.

An observed value is never presented as exhaustive: `complete: false` and
`scope.detail: "bounded"` say so (EF-05, CA-03). A field that first appears
after the observed records is absent from `detection`; the Scan finds it
(EF-18, CA-11).

### 8.6 Shapes outside the supported base (DP-12, PO-11, I-E02)

| Source | Result |
| --- | --- |
| Empty source (no byte, or only whitespace; JSONL: no non-blank line) | `InputError`, nothing written. |
| Root scalar | No candidate. `no_collection` (`scalar_root`). Unresolved. |
| Root object with no array through keys | No candidate. `no_collection` (`no_array`). Unresolved. A single object is not turned into a one-row dataset (E2). |
| Root array of primitives, or mixed | Candidate `$[]`, not eligible (`non_object_elements`). `no_collection` (`no_eligible_array`). Unresolved. |
| Empty collection | Candidate with `elements: 0`, not eligible (`empty`). Never selected by Inspect. Unresolved when alone. |
| Collection of non-objects chosen **explicitly** | Accepted by Scan, which reports `record_types`. Report support is verified in JI-7; if it cannot present such a dataset it fails with a clear error. Known limitation until then. |
| Explicit choice of an empty collection | Valid: a dataset with zero records, as today. |

"Nothing observed in the candidates" is never a proof that the source has no
collection beyond `json.discovery_max_depth`: `no_collection` says what was
searched, and the message names the discovery depth (I-E02).

### 8.7 Invalid JSON (DP-08, PO-08)

A syntax error, invalid UTF-8, a lone surrogate or any other fatal reader
problem of Scan design section 14 stops Inspect with `InputError` (exit 4) and
the position the parser reports. **No file is written**, the existing visible
file is left as it is, and no cache entry is made. Scan fails the same way. No
recovery of a damaged document is attempted, whatever the policy.

## 9. JSONL and NDJSON (EF-25 to EF-27, D16, DP-09)

### 9.1 Dataset

A JSONL source is read as a root array without the surrounding brackets: one
dataset, id `$[]`, kind `collection`, `collection_path [{"items": true}]`, whose
records are the object lines. `json.collections` for a `jsonl` source is `null`
or `["$[]"]`; any other value is a `ConfigurationError` raised before reading.
`.jsonl` and `.ndjson` (case-insensitive) are the same format; the reader is
`jsonl_reader.py`, `source.format` is `jsonl`.

### 9.2 Lines and records

| Rule | Behavior |
| --- | --- |
| Encoding | UTF-8, optionally preceded by a byte order mark (`source.encoding` `utf-8-sig`, as JSON). Invalid UTF-8 is fatal in both policies (as CSV). |
| Line separator | `\n`. A `\r` just before it is dropped. Splitting is on `\n` only, never `str.splitlines()`: U+2028, U+2029, `\x0b`, `\x0c`, `\x85` inside a string are data. A lone `\r` is JSON whitespace. |
| Last line | Valid without a final line break. |
| Blank or whitespace-only line | Ignored: not a record, not counted as read, not an error. Physical numbering still counts it. |
| Record index | 1-based over non-blank lines, excluded ones included (`RecordExcluded.index` rule). |
| Position | `{"record": n, "line": physical line, 1-based}`. |
| Valid object | A record. Nested objects and arrays follow the same rules as in a JSON element (I-F01). |
| Valid JSON that is not an object | Excluded, reason `not_object`, code `jsonl_record_not_object`. |
| Not valid JSON for Tabalyst | Excluded, reason `invalid_line`, code `jsonl_invalid_line`. "Valid" is the rule of a JSON document: RFC 8259 syntax, no `NaN` or `Infinity`, no lone surrogate escape, integers within `sys.int_max_str_digits`, exponents `Decimal` can represent. |
| Duplicate key in an object | The existing exclusion: reason `duplicate_key`, code `json_duplicate_key`. |
| Line above `limits.max_line_bytes` | Not parsed. Excluded, reason `line_too_long`, code `jsonl_line_too_long`; still hashed. The default and the cap are measured in JI-4 (section 15). |
| Record above `limits.max_record_observations` | Existing `record_too_large`. |
| No non-blank line | Fatal `InputError`: "empty". |

A JSONL record reads exactly as the same object inside a JSON array: native
types, `Decimal` for decimals, canonical text. Parity is a contract test
(section 16.3).

### 9.3 Error policy (EF-25 to EF-27)

| Policy | An excluded line | Scan status |
| --- | --- | --- |
| `tolerant` (default for JSONL) | Excluded; counted per reason; located; the rest is analyzed. | `partial`, exit 0 with a warning on standard error. |
| `strict` | `InputError` naming the record and physical line; nothing else is read. | Exit 4. |

`scope` gives `records_read`, `records_analyzed`, `records_excluded` and
`exclusions` per reason; diagnostics keep `count` complete and `locations`
bounded by `errors.max_locations`. The report shows them with the existing
`excluded_records` issue. The two policies hash differently (ET-06, CA-24).

### 9.4 Inspect on JSONL

Inspect never fails on a bad line: it counts and locates them (`lines`,
`invalid_lines`, `non_object_lines`), whatever the policy of `config`. Its
`config` is `dataset_path: "$[]"`, `errors.policy: "tolerant"` unless a layer
says otherwise. It reports a single candidate `$[]`, with the object count and
the same detail observation as JSON.

## 10. Identity and cache validity (EF-28 to EF-32, D07, D08, D18)

### 10.1 The triple

```python
@dataclass(frozen=True, slots=True)
class ScanIdentity:
    source_sha256: str
    config_sha256: str
    engine_version: str
```

Compared field by field, never concatenated (ET-07). Two Scans are
interchangeable only when the three fields are equal. Where the pieces come
from:

| Field | Source |
| --- | --- |
| `source_sha256` | SHA-256 of every byte of the source, computed by reading it now. |
| `config_sha256` | SHA-256 of the canonical JSON of the resolved `ScanConfig` (5.5, 10.3). |
| `engine_version` | `engine.version` of the document, which is the package version (E11, DP-10). |

A release therefore invalidates every cache: simple and prudent. A development
checkout that changes behavior without changing the version does not
invalidate; `refresh` (existing) is the way out.

```python
scan_identity(result: ScanResult) -> ScanIdentity        # of a document
expected_identity(source_sha256: str, config: ScanConfig) -> ScanIdentity
```

`expected_identity` resolves defaults (5.5) before hashing and takes the engine
version of the running package.

### 10.2 Where it applies

| Place | Rule |
| --- | --- |
| `current_scan` (shared cache) | Reuse only when the triple is equal. Another engine version rescans. |
| Project freshness (`projects/freshness`) | Same triple. |
| `scan_reuse.compare_source` (DP-D) | A present source is always compared by content. A different size is stale at once (the hash would differ). Otherwise the SHA-256 decides; the modification time is not consulted. `modified_at` stays recorded, informatively. Replaces the rule of Scan design O12 (to be amended in JI-2). |
| `report --scan` | The document's `engine.version` differing from the running version is a warning, not a refusal: the document is a file the user chose, not a cache (Q5, answered). |
| Visible Inspect file | Never evidence for reuse (I-T01, 11.6). |

A missing source is still accepted for `report --scan`, with a warning.

### 10.3 Canonical configuration (EF-29, CA-22)

`config_sha256` is already the hash of sorted, compact JSON, so indentation and
key order never matter. JI-2 adds the missing canonicalizations so that logical
equality gives equal hashes:

- `json.collections` entries are stored in canonical spelling
  (`$["a"][]` becomes `$.a[]`);
- `errors.policy` is resolved (5.5);
- unused flatten settings are normalized (5.6).

Dates and diagnostics are not part of `ScanConfig`, so they cannot change the
hash (CA-23). Adding fields to `ScanConfig` changes the hash of every
configuration once: the Scan format revision moves to 5 and old documents are
refused with the usual message.

## 11. Resolving the interpretation (EF-09 to EF-12)

```python
resolve_interpretation(
    source, *, scan_layer=None, collections=None, delimiter=None, encoding=None,
    location=None,
) -> Interpretation
```

`scan_layer` is the merged `scan` section of the `--config` files;
`collections`, `delimiter` and `encoding` are the command-line options.
`Interpretation` holds the effective `ScanConfig` (defaults resolved for the
source format), the `origin` of the collection (`visible`, `cache`,
`automatic`, `none`), `inspect_path` (the visible file used, or `None`) and
`notices`, the sentences to print. `scan`, `report` and the Python API call it for every `.json`,
`.jsonl` and `.ndjson` source, so both commands read a source with the same
rules (EF-11). CSV sources do not use it.

### 11.1 Layers (DP-04)

From lowest to highest priority:

1. built-in defaults;
2. **automatic detection**: only the detected `structure.dataset_path`, for a
   `.json` source with no visible file (11.2). Nothing else of the automatic
   `config` is applied; the other keys are the defaults of layer 1;
3. the `scan` section of each `--config` file, in order;
4. the **visible Inspect file** `config`, the keys it contains (5.1);
5. command-line options (`--collection`, `--delimiter`, `--encoding`).

Hard caps are enforced after merging, as today. A visible file is the most
specific choice a user made for one source, so it outranks a shared `--config`.
Automatic detection is a guess, so it ranks below any explicit setting (a
`--config` that lists `json.collections` is not overridden by a cache). A
command-line value is an explicit choice, not an autodetection, so it does not
violate EF-09; a notice says when one overrides the visible file's
`dataset_path`.

Merge rules are those of Scan design section 15: objects merge, lists replace,
unknown keys fail.

### 11.2 Sources of the collection

| Situation | Behavior |
| --- | --- |
| `.json`, visible file exists | Read and validated (4.6). The cache is not consulted and not modified (EF-09, DP-15). |
| `.json`, no visible file, valid cache | The cache's detected `dataset_path` is layer 2. |
| `.json`, no visible file, no valid cache | Automatic inspection runs, its document is written to the cache (12.4), its `dataset_path` is layer 2. |
| `.jsonl` or `.ndjson` | No detection: the dataset is `$[]` (9.1). No automatic Inspect, no cache entry. A visible file may still set the other keys. |
| Command line `--collection` | Layer 5, replaces the list of every layer. |

Automatic inspection reads the whole source once more than a Scan that has a
visible file would; the full-content hash is shared with it when the caller
passes the already computed hash (an optimization for JI-6 and JI-7, not a
behavior).

### 11.3 No choice made

After merging, a `.json` source whose `json.collections` is still `null` has no
dataset to analyze: the automatic discovery mode of `scan()` is never used by
the CLI parcours (DP-A). A visible `dataset_path: null` does not stop a lower
layer from supplying one (5.1). If none does, 11.4 applies.

### 11.4 Suspension (DP-13, EF-16, CA-09)

No Scan and no Report is run. The command fails with `ConfigurationError`
(exit 2) before reading the source for analysis, writing a Scan, a cache entry
for the Scan, or any output. The message lists every candidate with its
element count, says why nothing was selected, and gives the exits:

- with a visible file: "set `config.structure.dataset_path` in `<file>`";
- without one: "run `tabalyst inspect <source>`, edit the file", or "pass
  `--collection`";
- for `no_collection`: that no supported collection was found and the
  discovery depth searched.

The candidates come from the visible file's `detection` when it has them, else
from the cache.

### 11.5 A configured path that no longer exists (DP-16, CA-20, EF-12, E3)

When the collection of the effective configuration comes from the visible file
and the Scan reports `json_collection_not_found` for it, the run fails with
`ConfigurationError` (exit 2) naming the path and the Inspect file, **before
any Scan document, cache entry or report is written**. No other path is used.
The check runs on the in-memory result, together with the comparison of 11.6:

```python
check_result(interpretation, result: ScanResult) -> tuple[str, ...]
```

It raises for the case above and returns the notices of 11.6.

For a path that comes from a command-line option, `--config` or the automatic
layer, the existing warning and empty dataset stay (E3): they are the API's
behavior and an explicit option has no file to blame. (An automatic path
cannot be missing: the cache is bound to the hash.)

### 11.6 A visible file older than the source (DP-17, I-T01, D06)

A source that changed does not invalidate the visible file: its `config` still
applies. After reading, the run compares the SHA-256 the reader computed with
`source.sha256` of the file; when they differ `check_result` returns the notice "The
Inspect file was written for a different version of the source." and goes on.
The recorded hash is information only: it never makes a cached Scan reusable
(EF-28); reuse is decided by the triple of 10.1.

## 12. Persistence

### 12.1 Names

The visible file is `<full source name>-inspect.json` in the directory of the
source (D02, EF-02). The extension is kept, so `data.json` and `data.jsonl`
give `data.json-inspect.json` and `data.jsonl-inspect.json`, distinct (CA-02).

```python
inspect_path(source: Path) -> Path
```

Pattern expansion in `scan`, `report` and `inspect` ignores files named
`*-inspect.json`; an explicit path to such a file is refused with a message
saying it is an Inspect file (E8). A real source whose name ends in
`-inspect.json` cannot be used until renamed (known limitation).

### 12.2 Writing

`tabalyst inspect` writes only the visible file, atomically (temporary file in
the same directory, flushed, replaced), with the same helper as every other
output. It writes nothing in the storage cache. A failure to write is an error
of the action (exit 1): the requested output could not be produced.

### 12.3 Re-inspecting (DP-14, D05, EF-07, CA-04)

`tabalyst inspect` on a source that already has a visible file:

| Existing file | Result |
| --- | --- |
| Valid | `inspect`, `source`, `detection`, `warnings` are replaced. `config` is **preserved as a value**: the same keys, the same values, in the same order, nothing added or removed (a partial `config` stays partial). The file is rewritten with Tabalyst's formatting. If the preserved `dataset_path` is not an array of the new source, the warning `configured_path_not_found` is added; the inspection still succeeds. |
| Valid, with `--reset-config` | The same, but `config` is regenerated from the seed rule (5.3). |
| `config` invalid, unsupported version, unknown kind, or not a JSON object | Refused with `ConfigurationError`; the file is not touched (I-E01). |
| Any of the previous, with `--force` | Replaced by a new file. |

The amendment of the plan's "byte for byte": a JSON file cannot keep the
user's whitespace without a text-splicing parser; preserving the parsed
`config` keeps every choice, which is what D05 protects.

### 12.4 Automatic cache (DP-15, PO-12)

`inspect.json` lives next to `scan.json`:
`workspaces/<ws>/scans/<hash of the source path>/inspect.json`, from
`StorageLocation.shared_inspect_path(source)`, written under `workspace_writer`
with the atomic helper. It holds a complete `InspectDocument`. It is reused
only when all of these hold, and rebuilt otherwise:

- `source.sha256` equals the SHA-256 of the current content;
- `format_version` and `format_revision` are those of the running Tabalyst;
- `inspect.tabalyst_version` is the running version.

A missing, unreadable, corrupt or invalid cache file is not an error: it is
absent, and the inspection is redone. A failure to write the cache is a notice,
not an error: the cache is disposable and the Scan can still run. The visible
file is never regenerated, rewritten or deleted by `scan` or `report`.

## 13. Command line (provisional, settled in JI-7)

```text
tabalyst inspect INPUT... [--config FILE]... [--reset-config] [--force]
                          [--quiet] [--verbose] [--no-progress]
```

- Inputs: files and non-recursive patterns, as the other commands. Accepted
  extensions: `.json`, `.jsonl`, `.ndjson`. Another extension is refused with
  `ConfigurationError` (exit 2), saying which kinds Inspect knows; there is no
  CSV Inspect yet. Nothing is silently skipped.
- No `-o` or `-d`: the output name is fixed by 12.1.
- `--config` reads the `scan` section for the layers of 11.1 (the same files as
  `scan` and `report`). No `--collection`: the point of Inspect is to detect it.
- `--reset-config` and `--force` as in 12.3.
- Exit codes: 0 success, including an unresolved selection (the inspection
  worked; it says so); 2 configuration; 4 invalid input; 1 other failures,
  with the existing "most general failure wins" rule for batches. Batches
  plan first: a collision, or an output that would replace an input, rejects
  the whole batch before any read.
- Standard error (not part of the file): the path written, the selection and
  its basis, then each warning. Stable phrases that tests rely on are
  "different version of the source" (11.6) and "Inspect file" (11.5).

`scan` and `report` gain no Inspect-specific option. `--collection` stays.
`tabalyst.inspect(...)` joins the public API in JI-7, with the same arguments
and results as the command.

## 14. Edge cases (specification section 8)

| Situation | Behavior | Where |
| --- | --- | --- |
| Several equally plausible collections, no explicit choice | Candidates listed; Scan and Report suspended (exit 2) | 8.4, 11.4 |
| User path absent from the new source | Exit 2 before any write; no other path used | 11.5 |
| Source changed, configuration still compatible | Configuration kept; the old Scan is not reused; notice | 11.6, 10.2 |
| Key `a.b` next to nested `a` then `b` | Two fields, two displays, reversible | 6.2 |
| Flatten limit reached | The container is kept as a complex value; no warning | 7.2 |
| Empty array, array of objects, array of values | Array kept; no row added | 7.3 |
| Same property with different types | Types listed by count; no coercion | 7.4 |
| Invalid JSONL line, tolerant | Excluded, counted, located, `partial` | 9.3 |
| Invalid JSONL line, strict | Stops at the first one, with its line, exit 4 | 9.3 |
| Unsupported Inspect version | Refused, exit 2, no migration | 4.6 |
| Visible file with invalid `config` | Error; never replaced by an automatic one | 4.6, 11.1, 12.3 |
| Invalid classic JSON, even after the observed records | Inspect and Scan fail (exit 4); no file written | 8.7 |
| No supported collection | `no_collection`; unresolved; Scan and Report suspended | 8.6 |
| Path leading to a scalar or an unsupported shape | Not selected by Inspect; explicit selection runs and reports `record_types` | 8.6 |
| Empty source or collection | Empty source: error. Empty collection: never auto-selected, valid if explicit | 8.6 |
| Blank JSONL line | Ignored | 9.2 |
| Last line without line break, BOM, CRLF | Accepted | 9.2 |
| Very long JSONL line | `line_too_long` exclusion (limit measured in JI-4) | 9.2, 15 |
| Duplicate keys | Existing `duplicate_key` exclusion, JSON and JSONL | 9.2 |
| Cannot write the visible file | Error of the action (exit 1) | 12.2 |
| Cache missing, partial, corrupt | Treated as absent and rebuilt; never read as a valid Scan | 12.4 |
| Unknown `config` key, unsupported mode | Refused, naming the key | 4.6, 5.2 |
| `data.json` and `data.jsonl` | Distinct Inspect files; their `*.scan.json` outputs collide and the batch is rejected as today | 12.1, E9 |
| Inspect file given as an input | Refused | 12.1 |

## 15. Parameters pending measurement

The maintainer's rule: no numeric value is fixed without a measurement. These
parameters have a meaning, a constraint and a protocol here, and **no value**.
They live in `tabalyst.inspector.json_inspect.parameters` (the first four) and
in `LimitSettings` (`max_line_bytes`). Until measured, the module defines the
names without values and no test depends on a number: tests import the symbols
and build their data from them.

| Parameter | Meaning | Constraint | Measured in | Protocol |
| --- | --- | --- | --- | --- |
| `RECORDS_OBSERVED` | First records per candidate used for the detail observation | integer ≥ 1 | JI-5, confirmed in JI-8 | Time and memory of the observation against the bare event pass on the three public demos and on synthetic flat, nested and wide sources of increasing size; report the cost per record and how `fields`, `max_depth` and `nested_objects` converge as records grow. The lot proposes a value with the table; the maintainer decides at G2. |
| `FIELDS_OBSERVED` | Distinct field paths tracked per candidate | integer ≥ 1 | JI-5 | Memory of the field tracker on sources with many distinct keys (maps used as dictionaries); same decision path. |
| `MAX_CANDIDATES` | Candidates kept per source | integer ≥ 1 | JI-5 | Memory and time on an object with many array members; same decision path. |
| `DOMINANCE_RATIO` | Element count ratio from which the largest eligible candidate stands out | number > 1 | JI-5, reviewed at G2 | Apply the rule to the demos and to synthetic envelopes (paginated responses with a `results` array next to a small `included` array, two comparable lists, a list and a few records); show the top-two ratios, which sources become automatic or ambiguous, and let the maintainer pick on those cases. |
| `limits.max_line_bytes` | Largest JSONL line parsed | integer ≥ 1 with a hard cap | JI-4 | Memory and time of reading and parsing lines of growing size; relation to `limits.max_record_observations`; the default and the cap are decided with the table. |

The measurement is the first step of the lot, before the code that uses the
value is written, and its table is added to this section.

## 16. Tests and traceability

### 16.1 Interface the contract tests use

These names are proposed so that the tests could be written before the code.
A lot may adapt a name if it updates the tests and this section in the same
change.

| Name | Lot |
| --- | --- |
| `ScanConfig`: `json.flatten`, `json.arrays`, nullable `errors.policy` | JI-2 |
| `tabalyst.scanner.config.resolve_config_defaults(config, source_format)` | JI-2 |
| `tabalyst.scanner.identity`: `ScanIdentity`, `scan_identity(result)`, `expected_identity(sha, config)` | JI-2 |
| `tabalyst.scanner.paths.format_relative(path, separator)`, `parse_path(text, separator=)` | JI-3 |
| `tabalyst.scanner.readers.jsonl_reader`, source format `jsonl`, reason codes of 9.2 | JI-4 |
| `tabalyst.inspector.json_inspect.parameters` | JI-5 |
| `tabalyst.inspector.json_inspect.inspect_source(source, *, scan_config=None, on_progress=None) -> InspectDocument` (reads, writes nothing) | JI-5 |
| `tabalyst.inspector.models`: `InspectDocument`, `InspectConfig` with `to_scan_layer()` | JI-5 |
| `tabalyst.inspector.persistence`: `inspect_path`, `write_inspection(source, document, *, reset_config=False, force=False)`, `read_visible_inspect(path) -> VisibleInspect` (`config`, `kind`, `recorded_sha256`, `recorded_name`, `candidates`, raw `document`) | JI-6 |
| `StorageLocation.shared_inspect_path(source)` | JI-6 |
| `tabalyst.inspector.resolution`: `resolve_interpretation`, `check_result` | JI-6 |
| `tabalyst inspect`, `tabalyst.inspect()` | JI-7 |

### 16.2 Layout

`tests/inspect/` follows `tests/scan/`: tests declare their lot with
`@pytest.mark.inspect_lot("JI-2")` and are skipped while the lot is not in
`ENABLED_LOTS` of `tests/inspect/conftest.py`. A lot adds itself to that set
when its implementation starts. The marker is not `lot`, which `tests/scan`
uses for its own lots. Files are named `test_json_inspect_*.py` so another kind
can add its own.

### 16.3 Mapping of the acceptance criteria

| CA | Test | Lot |
| --- | --- | --- |
| CA-01 | `test_json_inspect_persistence.py`: file named and written beside the source, readable, zones in order, no absolute path; CLI `test_json_inspect_cli.py` | JI-6, JI-7 |
| CA-02 | `test_json_inspect_persistence.py`: names for `data.json`, `data.jsonl`, `data.ndjson`; CLI collision of scan outputs | JI-6, JI-7 |
| CA-03 | `test_json_inspect_detection.py`: scope, bounded detail, exact counts | JI-5 |
| CA-04 | `test_json_inspect_persistence.py`: re-inspection keeps `config` as a value, refreshes detection | JI-6 |
| CA-05 | `test_json_inspect_persistence.py`: visible beats cache; `test_json_inspect_cli.py`: end to end | JI-6, JI-7 |
| CA-06 | `test_json_inspect_cli.py`: report with no file, clear dataset | JI-7 |
| CA-07 | `test_json_inspect_flatten.py`: root array of objects through the whole cycle | JI-3, JI-7 |
| CA-08 | `test_json_inspect_detection.py` (`results` envelope); CLI | JI-5, JI-7 |
| CA-09 | `test_json_inspect_detection.py` (ambiguity); `test_json_inspect_cli.py` (suspension) | JI-5, JI-7 |
| CA-10 | `test_json_inspect_cli.py`: edited path, `--collection` | JI-7 |
| CA-11 | `test_json_inspect_detection.py`: late field absent from detection, present in Scan | JI-5 |
| CA-12 | `test_json_inspect_flatten.py`: depth limit keeps the complex value, no warning | JI-3 |
| CA-13 | `test_json_inspect_flatten.py`: `a.b` next to `a` > `b` | JI-3 |
| CA-14 | `test_json_inspect_paths.py`: round trip for every separator | JI-3 |
| CA-15 | `test_json_inspect_flatten.py`: arrays add no rows | JI-3 |
| CA-16 | `test_json_inspect_flatten.py`: mixed types | JI-3 |
| CA-17 | `test_json_inspect_flatten.py`: absent, `null`, empty string | JI-3 |
| CA-18 | `test_json_inspect_jsonl.py`: default policy | JI-4 |
| CA-19 | `test_json_inspect_jsonl.py`: strict policy | JI-4 |
| CA-20 | `test_json_inspect_cli.py`; `test_json_inspect_persistence.py` | JI-6, JI-7 |
| CA-21 | `test_json_inspect_identity.py`: same size, same time, other content | JI-2 |
| CA-22 | `test_json_inspect_identity.py`: spelling, order, indentation | JI-2 |
| CA-23 | `test_json_inspect_identity.py`: dates and warnings outside the hash | JI-2 |
| CA-24 | `test_json_inspect_identity.py`: path, depth, policy change the identity | JI-2 |
| CA-25 | `test_json_inspect_identity.py`: engine version | JI-2 |
| CA-26 | `test_json_inspect_identity.py`: equal triple reuses | JI-2 |
| CA-27 | `test_json_inspect_detection.py`: two inspections equal but for the date | JI-5 |
| CA-28 | `test_json_inspect_persistence.py`: unsupported version refused | JI-6 |
| I-E01 | `test_json_inspect_persistence.py` | JI-6 |
| I-T01 | `test_json_inspect_cli.py` | JI-7 |
| I-F01 | `test_json_inspect_jsonl.py`: JSONL nested objects, parity with JSON | JI-4 |

The specification's minimal matrix (section 10.2) maps as follows: simple
array, nested, JSONL, `results`, several collections, mixed types, `null` and
absence, arrays, invalid JSON, incompatible configuration, late field,
ambiguity, both JSONL policies, collisions and a changed source with identical
metadata are each covered by a test above; the matrix is closed in JI-8 with
the measurements.

## 17. Changes to this document

| Date | Lot | Change | Reason |
| --- | --- | --- | --- |
| 2026-09-30 | JI-1 | Initial contract. Amends the plan: format triple at the top level; `inspect.kind` and the shell/kind separation (the maintainer announced several Inspect kinds); `config` preserved as a value on re-inspection; automatic detection below `--config`; no automatic Inspect for JSONL; no confidence score; `_` excluded from separators; numeric parameters deferred to measurements. | Lot JI-1. |
