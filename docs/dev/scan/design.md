# Tabalyst Scan design

Phase 0 contract, accepted at gate 0 on 2026-09-26. This document turns the
functional specification of Tabalyst Scan into the contract that the
implementation lots follow. The
specification is maintained privately (`tabalyst-gb`,
`drafts/2026-09-26-scan/Tabalyst-Scan-Cahier-des-charges.md`); its identifiers
(`Dxx`, `EFxx`, `ETxx`, `CAxx`, `Oxx`) are reused here for traceability.

The phase plan, sessions and models are in [plan.md](plan.md). The contract
tests that make this document executable are in `tests/scan/`.

## 1. Status of decisions

| Label | Meaning |
| --- | --- |
| **Accepted** | Validated by the maintainer. |
| **Proposed** | Phase 0 decision. It becomes Accepted at the phase 0 gate or is amended there. |
| **Deferred** | Deliberately left to a named lot, which must settle it before implementing the affected behavior. |

Changing a Proposed or Accepted rule later is allowed during the alpha, but the
change must update this document and the affected contract tests in the same
lot, with the reason recorded in section 17.

### Decision register

| ID | Topic | Decision | Status | Section |
| --- | --- | --- | --- | --- |
| A1 | Models | Pydantic for finalized results and configuration; plain slotted classes for mutable accumulators. | Accepted 2026-09-26 | 3, 15 |
| A2 | JSON streaming | `ijson` becomes a runtime dependency. Its pure-Python backend guarantees availability; the C backend is used when installed. | Accepted 2026-09-26 | 6 |
| A3 | Migration | New engine in `tabalyst.scanner`, beside the current engine. The report moves onto it in phase 5, then the pandas engine and dependency are removed. | Accepted 2026-09-26 | 3 |
| A4 | CSV errors | `strict` by default (current behavior); `tolerant` is opt-in. | Accepted 2026-09-26 | 14 |
| A5 | Location | Design documents live in `docs/dev/scan/`. | Accepted 2026-09-26 | - |
| O01 | Result schema | Section 16, plus the envelopes of section 8. | Accepted 2026-09-26 | 8, 16 |
| O02 | Paths and identities | Canonical segment lists, documented reversible display syntax, positional CSV identities. | Accepted 2026-09-26 | 4 |
| O03 | JSON datasets and denominators | Collection rules of section 5; denominators from parent container occurrences. | Accepted 2026-09-26 | 5, 7 |
| O04 | Null, empty, blank, markers | Disjoint categories; missing is a derived, configurable sum. | Accepted 2026-09-26 | 7 |
| O05 | Numeric conventions | Exact integer and decimal accumulation; population variance; float64 output. | Accepted 2026-09-26 | 9.4 |
| O06 | Ambiguity | The scan never resolves ambiguity from field evidence; it exposes evidence. Only explicit configuration resolves. | Accepted 2026-09-26 | 12.6 |
| O07 | Error policy | Strict and tolerant behaviors of section 14. | Accepted 2026-09-26 | 14 |
| O08 | Unicode normalization | Normalization version 1 of section 10. | Accepted 2026-09-26 | 10 |
| O09 | Limits | Initial defaults and hard caps of section 11; values revisited after phase 6 benchmarks. | Accepted 2026-09-26 | 11 |
| O10 | Sensitive values | Sensitive fields expose masked shapes by default, through one exposure gate. | Accepted 2026-09-26 | 12.8 |
| O11 | Declarative patterns | Validated Python regular expressions with length caps. | Accepted 2026-09-26 | 12.7 |
| O12 | Reuse and staleness | The report reuses a scan document; a source beside it with another size, or another content (its SHA-256, whatever its modification time), and configured scan settings that differ from the document's are stale and fail; a missing source is accepted with a warning. A document of another engine version is reported with a warning. Amended 2026-09-30 (lot JI-2, inspect design DP-D, 10.2). | Accepted 2026-09-28 (lot 5c); amended 2026-09-30 | 16.6 |
| O13 | Configuration merge | Objects merge, lists replace, unknown keys fail. | Accepted 2026-09-26 | 15 |
| O14 | Detector catalogue | Each detector gets a short specification in [detectors.md](detectors.md) before it is implemented. | Accepted 2026-09-26, file created in lot 3b | 12 |
| O15 | Empty inputs | Zero counts and `not_applicable` measures; never a division by zero. | Accepted 2026-09-26 | 9.9 |
| O16 | Report | The report is a consumer of the scan: it presents technical types, interpretations and evidence, never resolves ambiguity, and masks like the scan. | Accepted 2026-09-27 (lot 5a) | 16.4 |
| O17 | Output writing | Atomic temporary file plus replace; `--force` for existing outputs. | Accepted 2026-09-26 | 16.3 |
| O18 | Migration | See A3. | Accepted | - |
| O19 | Performance targets | Baseline recorded in `benchmarks.md`; targets decided in phase 6. | Deferred to 6 | 13 |
| O20 | Costly exact measures, external storage | Out of the first phases; exact medians only when derivable. | Deferred to 7 | 9.4 |
| O21 | Dynamic plugins | Internal registry only; no external loading. | Deferred to 7 | 12.1 |
| O22 | Approximations | Outside the contract. Any approximation requires a new explicit decision. | Accepted (specification) | 8 |
| O23 | Adaptive detection | Adaptive detectors that react to none of the first `detection.warmup_values` distinct values of a field (default 10,000) skip its later values, except probes; skipped values are `not_tested`, never guessed. `number` and `date` are never skipped. Sensitive detectors are skipped like the others for now (open point in section 13). | Accepted 2026-09-28 (lot 6) | 12.2, 13 |
| O24 | Rare detectors | Adaptive detectors that react to at most `detection.rare_share` of the warm-up values (default 0.001) and to none of its second half are skipped too; a rare sensitive detector without a match never is. Probes that react more often than the warm-up allowed raise `detector_skipped_reacted`. | Proposed 2026-09-28 (lot 6) | 12.3, 13 |
| O25 | Batch and parallel execution | Distinct values are processed in batches, detector by detector; CSV records arrive as batches of rows read column by column; large sources hand the values of each field to one worker process. Results never depend on batches or workers (principle 6). | Proposed 2026-09-28 (lot 6) | 6, 13 |

## 2. Principles

1. **Complete and exact, or explicitly limited.** Every record in the analyzed
   scope is read. A measure is either exact for its declared population or
   carries a non-`complete` status. No estimate is ever presented as a value.
2. **Facts, not verdicts.** The scan records observations, interpretations and
   their evidence. Quality judgments, issues and presentation choices belong to
   consumers such as the report.
3. **Raw values are never modified.** Normalization produces analytical forms
   and counters only.
4. **One engine, several readers.** Readers understand formats; the engine and
   detectors never test the source format.
5. **Bounded state.** Memory depends on configured limits and the number of
   tracked fields, not on the number of records.
6. **Same results whatever the internal strategy.** Execution modes and caches
   (section 13) change speed, never results.

## 3. Package, public API and models

The engine lives in the `tabalyst.scanner` package. The name avoids a
`tabalyst.scan` module that would be shadowed by a future top-level
`tabalyst.scan()` function.

```python
from tabalyst.scanner import ScanConfig, ScanResult, scan

result: ScanResult = scan("customers.json", config=ScanConfig())
document = result.model_dump(mode="json")
```

`scan(source, *, config=None, registry=None, on_progress=None,
on_record=None)` reads one source and returns a finalized `ScanResult`. It
writes nothing. `registry` replaces the default detector registry (section
12.1). `on_record` receives each analyzed `Record` (section 6), in reading
order, before the engine, so a consumer gets record-level facts in the same
pass; it must not modify the record (lot 5a). Since lot 5c the report reads
record facts from the `records` block of each dataset (section 9.10) instead. Phase 4 adds
file output, batches and the top-level alias `tabalyst.scan`: since lot 4, `tabalyst.scan`,
`tabalyst.ScanConfig` and `tabalyst.ScanResult` are exported by the package,
with `tabalyst.generate_scans()` (section 16.3).

Proposed layout, free to adapt as long as the boundaries hold:

```text
src/tabalyst/scanner/
|-- __init__.py        scan(), ScanConfig, ScanResult
|-- api.py             orchestration: reader selection, engine, timing
|-- config.py          ScanConfig, defaults and hard caps
|-- paths.py           segments, FieldPath, display and parsing
|-- observations.py    Observation, Record and reader stream items
|-- readers/           base protocol, csv_reader.py, json_reader.py
|-- engine.py          ScanEngine: datasets, dispatch, finalization
|-- structure.py       per-dataset path registry, presence, structural limits
|-- field.py           FieldScanner: counters, value tables, execution modes
|-- values.py          frequency tables, samples, first/last values, budgets
|-- measures.py        numeric, string and boolean accumulators
|-- normalization.py   normalization version 1
|-- diagnostics.py     diagnostic collector
|-- exposure.py        sensitive value gate
|-- technical.py       technical type inference
|-- workers.py         worker processes of parallel scans (lot 6)
|-- detectors/         base, registry, shape classifier, built-ins, patterns
`-- models.py          Pydantic result models
```

Rules:

- No pandas import anywhere in `tabalyst.scanner` (ET04).
- Accumulators are mutable, slotted Python classes. `finalize()` turns them into
  immutable Pydantic models (D08). Nothing mutates a model after finalization.
- Result models use `extra="forbid"`, like `tabalyst.models`.
- Fatal problems raise the existing public exceptions: `InputError` for sources,
  `ConfigurationError` for configuration.

## 4. Paths and identities (D06, O02)

### 4.1 Canonical form

A path is a tuple of segments, relative to the record root:

| Segment | Meaning | JSON form |
| --- | --- | --- |
| key | Member of an object | `{"key": "orders"}` |
| items | Any element of an array; indices are not distinguished | `{"items": true}` |
| column | CSV column at a 1-based position | `{"column": 3}` |

The empty path is the record itself. The canonical JSON form of a path is the
list of its segments. It is the identity used to compare fields across results.

### 4.2 Display syntax

The display syntax is documented and reversible so it can also be used in
configuration and on the command line:

```text
absolute  := "$" segment*
relative  := ( identifier | quoted | "[]" ) segment*
segment   := "." identifier | quoted | "[]"
quoted    := "[" json-string "]"
identifier:= [A-Za-z_][A-Za-z0-9_]*
```

- Keys matching `identifier` are written bare; every other key is written as a
  JSON string in brackets, so `a.b`, `c[]` or an empty key never collide with
  nested paths.
- The record root displays as `$`. Dataset identifiers are absolute paths such
  as `$`, `$[]` or `$.customers[]`; field displays are relative, such as
  `orders[].amount`.
- CSV columns display as their header name when it is non-blank and unique in
  the header, otherwise as `name#position` (`name#3`, `#4` for a blank header).
  CSV displays are labels only; the column segment is the identity.

### 4.3 Field identifiers

`id` is unique within one dataset result. CSV fields use `column_<position>`,
as the current profile does. JSON fields use `f<n>` in order of first
discovery. Identifiers are local to one result; use `path` across results.

## 5. Sources, datasets and records (D07, D11, O03)

| Concept | Definition |
| --- | --- |
| Source | One input file, with its format and identity. |
| Dataset | A collection of records within a source. |
| Record | One member of a dataset: a CSV data row, or one element of a JSON collection. |
| Field | A path relative to the record root, with everything observed at it. |
| Value | One occurrence at a field, with its native type. |

### 5.1 CSV

A CSV source has exactly one dataset, `rows`, of kind `table`. The first record
is the header. Each data record is represented as an object whose members are
the column segments, so presence rules are shared with JSON.

### 5.2 JSON

Automatic mode (default):

| Root | Datasets |
| --- | --- |
| Array | One dataset `$[]` of kind `collection`, whose records are the array elements. |
| Object | One dataset `$` of kind `document` with one record, the root object. Every array reachable from the root through objects only, at depth `json.discovery_max_depth` or less (default 3), also becomes a `collection` dataset. |
| Scalar | One dataset `$` of kind `document` with one record, the scalar. |

- In the document dataset, a promoted array is a field of native type `array`
  whose `collection` names the dataset holding its elements; its elements are
  not traversed again there.
- Arrays inside records are never promoted automatically: `orders[]` inside a
  customer stays a field of the customer dataset (EF07, CA04).
- Records may have any native type. Object members are fields; array elements
  are the `[]` field of the record; scalar records are analyzed at the root
  field `$`. The root field (empty path) is listed only when at least one
  record of the dataset is not an object; `record_types` always gives the
  native types of the records.
- An empty collection is a dataset with zero records.
- The document dataset has `collection_path: null`; its promoted arrays are
  listed after it, in document order.
- Promotion needs the array to be analyzed in the document: an array deeper
  than `limits.max_depth` is truncated there and never promoted.

Explicit mode: `json.collections` lists absolute paths, which may cross arrays
(`$.customers[].orders[]` gathers every order into one dataset). Only the
selected collections are analyzed; the rest of the document is outside the
requested scope, which the result states (EF05). Overlapping selections (one
path extending another), equivalent spellings of one path and an empty list are
configuration errors. Dataset identifiers and `scope.collections.requested`
use the canonical spelling (`$["a"][]` becomes `$.a[]`). Every requested
dataset is listed, in requested order;
when no array exists at its path, it has zero records and a
`json_collection_not_found` warning.

Every value of a JSON source is read; a source is UTF-8, optionally preceded
by a byte order mark, which RFC 8259 lets parsers ignore (`source.encoding` is
then `utf-8-sig`). An object with a duplicate key makes its record malformed:
which value applies is ambiguous and presence would exceed its parent count.
Under `strict` it is fatal; under `tolerant` the record is excluded with
reason `duplicate_key` (section 14). A string or key holding a lone
surrogate escape, such as `"\ud800"`, is not valid Unicode (I-JSON, RFC
7493): the source is invalid. The pure-Python backend of `ijson` keeps such
surrogates, and Tabalyst rejects them; the compiled backend rejects lone low
surrogates itself but replaces a lone high surrogate with `?` before
Tabalyst sees it, a known limitation of that backend.

The compiled backend of `ijson` crashes the process (access violation) on an
integer longer than `sys.int_max_str_digits` (4,300 digits by default) in some
parser states. Before parsing, the reader looks for a run of more digits than
that limit, at memory speed; when one exists, even inside a string, the file
is parsed by the pure-Python backend, which reports an `InputError`. A number
whose exponent `Decimal` cannot represent is an `InputError` too. Parser
messages quoted in errors are cut at 200 characters.

The JSON reader tracks its own path stack. It must not use `ijson` prefix
strings as identities, because they join keys with dots and would merge `a.b`
with `a` > `b` (specification scenario 4).

At most two passes over a JSON source are allowed; the target is one.

### 5.3 JSONL (lot JI-4)

A source ending in `.jsonl` or `.ndjson` is one dataset `$[]` of kind
`collection` whose records are its object lines (`source.format` `jsonl`). The
reader parses each line on its own and gives each record the observations it
would have as an element of a JSON array, with the same flatten and depth rules.
Its rules, exclusion reasons and policy are in inspect design section 9;
`limits.max_line_bytes` bounds a line. Locations are `{record, line}`. The
source is read once, hashed while reading.

## 6. Reader to engine contract (D04, D05, ET01, ET02)

Readers are synchronous iterators. They yield three kinds of items:

```python
@dataclass(frozen=True, slots=True)
class DatasetOpened:
    dataset: str                 # "rows", "$", "$[]", "$.customers[]"
    kind: Literal["table", "document", "collection"]
    collection_path: FieldPath | None
    fields: tuple[DeclaredField, ...] = ()   # known before any record
    container: tuple[str, FieldPath] | None = None   # ("$", customers): field
                                 # whose arrays hold the records (field.collection)

@dataclass(frozen=True, slots=True)
class DeclaredField:
    path: FieldPath
    name: str                    # CSV header name
    display: str                 # CSV label: "name", "name#3", "#4"

@dataclass(slots=True)
class Record:
    dataset: str
    index: int                   # 1-based within its dataset
    location: Location           # CSV physical lines, JSON element index
    observations: list[Observation]
    depth_truncated: int = 0     # observations below limits.max_depth, not emitted

@dataclass(frozen=True, slots=True)
class Notice:                    # technical event forwarded as a diagnostic
    code: str                    # "json_collection_not_found"
    level: Literal["error", "warning"]
    message: str
    dataset: str | None = None
    location: Location | None = None

@dataclass(frozen=True, slots=True)
class RecordExcluded:
    dataset: str
    index: int                   # counts every record read, excluded or not
    location: Location
    reason: str                  # "width_mismatch", "record_too_large"
    code: str                    # diagnostic code, "csv_width_mismatch"
    message: str                 # diagnostic message, same for every record
```

```python
class Observation(NamedTuple):   # immutable; a named tuple is cheap to build (lot 6)
    path: FieldPath              # relative to the record root
    type: NativeType             # null, boolean, integer, number, string, object, array
    value: object                # str, int, Decimal, bool or None; array length for arrays

@dataclass(slots=True)
class RecordBatch:               # lot 6: records of a table with declared fields
    dataset: str
    start: int                   # index of the first record; the others follow
    rows: list[list[str]]        # one string per declared field, in order
    lines: list[int]             # first physical line of each record
```

A reader of a dataset with declared fields may stream its records as
`RecordBatch` items instead of `Record` items: each row stands for a record
that observes its root as an object, then each declared field once, as a
string, so the engine reads the batch column by column with the same results.
The CSV reader does (lot 6). `scan(on_record=...)` still receives one
`Record` per record, built from the batch. A reader that builds paths should
reuse one path object per logical path (the JSON reader does): the engine and
record digests look paths up by identity first.

- Every record starts with an observation at the empty path describing the
  record itself. CSV records use type `object`.
- Observations appear in document order; a container is observed before its
  children. Every object and array occurrence is observed, including empty ones.
- A reader never emits absence observations; absences are derived (section 7).
- Native types follow the source's lexical form: in JSON, `1` is `integer`,
  `1.0` and `1e3` are `number` (read as `Decimal`), `"1"` is `string`. Every CSV
  value is a `string`.
- After iteration, `reader.summary()` returns the source description completed
  during reading: bytes read, SHA-256 computed while streaming, encoding, CSV
  header and delimiter.
- A CSV location is the record index and the first physical line of the
  record; a JSON location is the record index and the 0-based element index in
  its array (none for the document record).
- Records of different datasets may interleave: the JSON reader yields each
  collection element as soon as it ends and the document record last.
- A reader raises `InputError` for fatal problems (section 14). Readers
  receive the configuration and apply the error policy themselves: under
  `strict` they raise a format-specific `InputError`; under `tolerant` they
  yield `RecordExcluded`, whose `code` and `message` become the diagnostic, so
  the engine never tests the source format.
- Declared fields are registered before any record, in order, so a CSV with
  only a header still lists its columns, with the header names and labels
  that only the reader knows. Other fields are discovered from observations.
- Records are materialized one at a time. `limits.max_record_observations`
  protects against a single huge record; it counts the observations the reader
  emits, so content truncated by `limits.max_depth` does not count. Readers
  apply both limits, so they never build paths deeper than `max_depth`; the
  engine applies `max_fields`.

## 7. Presence and value categories (D12, D13, EF06-EF10, O04)

For a field at path `P` with parent path `parent(P)`:

| Counter | Definition |
| --- | --- |
| `occurrences` | Observations at `P`, whatever their native type. |
| `presence.parent_type` | `object` for key and column segments, `array` for items segments, `record` for the root field. |
| `presence.parent_count` | Objects observed at `parent(P)` for keys and columns; arrays observed at `parent(P)` for items; analyzed records for the root field. |
| `presence.present` | Equal to `occurrences`. |
| `presence.absent` | `parent_count - present` for keys, columns and the root field; `null` for items. |
| `native_types` | Occurrences per native type; only types seen are listed. |
| `first_record` | Index of the first record with an occurrence, or `null`. |

A key is absent only where its parent was an object that could have contained
it. When `address` is `null` or missing, `address.city` is neither present nor
absent in that record; the situation is visible at `address`. This keeps
presence exact for fields that appear late, without emitting absence events
(CA03).

String occurrences fall into exactly one category:

| Category | Rule, evaluated in this order |
| --- | --- |
| `empty` | The raw string is `""`. |
| `blank` | The raw string contains only whitespace (`str.isspace()`). |
| `marker` | The raw string stripped of whitespace equals a configured `values.null_markers` entry, case-sensitively unless configured otherwise. |
| `content` | Every other string. |

Invariants, checked by the contract tests:

- `sum(native_types.values()) == occurrences`
- `strings.empty + strings.blank + strings.marker + strings.content == strings.count == native_types["string"]`
- `values.count == strings.content + integer + number + boolean`

`values` is the population of analyzable scalar values used by frequencies,
normalization, detectors and statistics.

`missing.count` is a derived sum over the categories named in
`values.missing` (default `absent`, `null`, `empty`, `blank`, `marker`). The
result always lists every component and the definition used, so consumers can
recompute another definition. The default reproduces the current report,
where whitespace-only cells are missing.

Arrays add an `arrays` block to their field: `count`, `empty`, `min_length`,
`max_length` and `total_items`.

## 8. Measure envelopes (EF19, specification 7.4)

Plain counters that can never be limited (presence, native types, string
categories, normalization change counters) are plain integers. Every measure
that can be limited, disabled, inapplicable or failed is wrapped:

```json
{"status": "complete", "value": 42}
{"status": "limited", "reason": "distinct_limit", "limit": 10000, "lower_bound": 10001}
{"status": "not_applicable", "reason": "no_values"}
{"status": "disabled"}
{"status": "failed", "reason": "detector_error", "diagnostic": 3}
```

| Status | Meaning | Fields |
| --- | --- | --- |
| `complete` | Exact for the declared population. | `value` |
| `limited` | Stopped or not stored because of a limit. | `reason`, `limit`, optional `lower_bound` |
| `not_applicable` | Meaningless here, for example no values. | `reason` |
| `disabled` | Turned off by configuration. | none |
| `failed` | A technical failure prevented the measure. | `reason`, `diagnostic` (index in `diagnostics`) |

`disabled` is distinct from `not_applicable`, as the specification requires.

**Proven bound rule (ET10, CA08, CA09).** `lower_bound` is published only when
it is proven by observation: `L + 1` after `L + 1` genuinely distinct stored
values, or the stored distinct count plus one when a value too long to store
was seen (such a value differs from every stored one). Truncated values or
hashes are never used as identity proofs.

A scan can reach the end of its scope with limited measures and still have
status `complete`; scan status and measure status are independent.

## 9. Measures per field

Each block below names its population, its lot and whether it is plain or an
envelope. The JSON layout is summarized in section 16.

### 9.1 Values and frequencies (lot 2a)

`values.count` is a plain counter provided from lot 1a; the other members of
`values` arrive in lot 2a.

- The raw frequency table stores each distinct value as `(native type,
  canonical text)`, so the string `"123"` and the integer `123` are distinct
  (EF10, CA05). Canonical text is the raw string for strings, `true`/`false`
  for booleans and `str()` of the parsed value for JSON numbers. `ijson` does
  not keep the source text, so it matches the source except for the exponent
  spelling (`1e3` becomes `1E+3`) and the integer `-0`, which becomes `0`.
- Values are output as `{value, type, ...}`, where `value` is always the
  canonical text of the analytical value (a JSON string) and `type` its native
  type.
- `values.cardinality`: envelope, exact raw distinct count.
- `values.frequencies`: envelope whose value is `{distinct, listed, truncated}`.
  `distinct` counts distinct analytical values (`(type, analytical text)`),
  which may be fewer than the raw cardinality. `listed` holds the
  `limits.max_listed_frequencies` most frequent analytical values as
  `{value, type, count}`, ordered by count (descending), then value, then
  native type (`string`, `integer`, `number`, `boolean`). Output truncation is
  not a limitation of the measure: `truncated` says the listing is shorter than
  `distinct`. When the table is released, the envelope is `limited` without
  `lower_bound`: raw distinct values do not prove analytical ones.
- `values.samples`: a plain object `{selection, listed}` with up to
  `limits.max_samples` distinct analytical values, with `selection` set to
  `all` (every distinct value), `uniform_distinct` (sample of the complete
  table drawn with `random.Random(random_seed)`) or `first_seen` (first
  distinct values, used when the table is released), listed as
  `{value, type, count}` in first-seen order. Counts are complete in every
  selection. Values longer than `limits.max_stored_value_length` are never
  sampled. Samples are examples, not statistics.
- `values.first` and `values.last`: `{value, type, record}` for the first and
  last analytical values (EF21), `null` without values. They keep the whole
  value, even beyond `limits.max_stored_value_length`.
- Shares and confidences are rounded to four decimals; counts are never
  rounded.

### 9.2 String characteristics (lot 2a)

Over `content` strings, on raw values. Plain counters, always present:

| Counter | Rule |
| --- | --- |
| `non_ascii` | A character above U+007F. |
| `with_line_breaks` | A line boundary of `str.splitlines` (`\n`, `\r`, `\v`, `\f`, U+001C to U+001E, U+0085, U+2028, U+2029). |
| `with_control_characters` | A character of category `Cc` other than the tabulation and line breaks. |
| `with_surrounding_whitespace` | `value != value.strip()`. |
| `with_repeated_whitespace` | Two consecutive whitespace characters in `value.strip()`. |
| `uppercase`, `lowercase` | `str.isupper()`, `str.islower()`. |
| `mixed_case` | Cased characters, but neither `isupper()` nor `islower()`. |
| `no_letters` | No character with `str.isalpha()`. |

Case counters are exclusive; letters without case (such as CJK) count in none
of them.

### 9.3 String lengths (lot 2a)

Envelope over analytical `content` strings, in code points: `count`,
`min_length`, `max_length`, `mean_length`, `median_length` and
`length_histogram` (`[{length, count}]`, ordered by length). The mean and the
median (mean of the two middle lengths for an even count) follow the numeric
output rule of 9.4. The length histogram is independent of the frequency
table, so string lengths and their median stay exact when the table is
limited.

### 9.4 Numbers (lot 2a, extended in 3a) (EF15, O05)

Population: native `integer` and `number` values, plus strings whose
analytical value the number detector (12.10) matches, including ambiguous
values resolved by configuration. Its strict rule (optional sign, digits,
optional dot decimal, optional exponent, no leading zeros for integers) is
the rule of lot 2a; its decimal conventions extend it.

Envelope value: `count`, `native_count`, `text_count`, `min`, `max`, `sum`,
`mean`, `population_variance`, `population_std`, `positive`, `negative`, `zero`,
`integral_decimals` (decimal representations with an integral value, such as
`1.0` or `1e3`) and `median` (nested envelope).

- Integers accumulate as Python `int`; decimals as `Decimal` in an exact
  context of 200 significant digits with exponents between -1,000 and 1,000,
  trapping `Inexact`. If an operation would round or leave that range, the
  envelope becomes `limited` with reason `precision` and limit `200`. So does
  a number beyond the range of `decimal` (`1e9999999999999999999999`); a zero
  is exact whatever its exponent (`0e-5000`).
- Variance uses the complete population (divide by `n`), from exact sums.
- Output: integral results below 10^200 are JSON integers; other results are
  float64. A result that is not a finite float64 makes the envelope `limited`
  with reason `precision`.
- `median` (mean of the two middle values for an even count) is exact when
  derived from a complete frequency table. Otherwise it is `limited` with the
  reason and limit of the table (`distinct_limit`, `global_budget` or
  `value_too_long`, section 11). Other quantiles are deferred (EF22, O20).
- Values that are not finite in text (`NaN`, `inf`) are not numbers.

### 9.5 Booleans (lot 2a)

Envelope of native booleans: `{"true": n, "false": m}`, `not_applicable`
without native booleans. Textual booleans are the `boolean` detector
(12.10), which counts them in its `details`.

### 9.6 Temporal values (lot 3a) (EF16)

Produced by the date detector (12.10) from its matched values, including
ambiguous values resolved by configuration. Envelope value: `count`,
`ambiguous` (unresolved ambiguous values, excluded) and `kinds`, one entry per
kind seen, in order `date`, `datetime_naive`, `datetime_aware`, `time`:
`{kind, count, min, max, years}`. `min` and `max` are ISO strings (Python
`isoformat()`); aware values compare as instants, ties broken by their text,
and naive and aware values are never compared. `years` lists `{year, count}`
by year for dates and date-times, which is always bounded (years 1 to 9999),
and is `null` for times.

- `not_applicable` (`no_values`) without temporal or ambiguous values, or
  when the date detector has no eligible value; `disabled` when the date
  detector is disabled or absent from the registry; `failed` with the
  diagnostic of the date detector when it failed on the field.

### 9.7 Technical type (lot 3a)

A port of the current inference so the report keeps its meaning: candidate
families are tried in order `integer`, `number`, `date`, `boolean`, `text`, and
the first whose accepted share reaches `types.minimum_confidence` wins;
otherwise `mixed`; `empty` without values. Native JSON types count directly.
Output: `{type, confidence, counts, outside_count}`.

- Each value of the `values` population belongs to one family, a pure
  function of the value. Native integers, numbers and booleans are their own
  family. A string is, in this order: `date` when the date detector matches
  it as a calendar date (not a date-time or a time) or finds it ambiguous;
  `boolean` when it is `true` or `false` ignoring case (the current rule;
  other boolean words are only the `boolean` detector's); `integer` when the
  number detector matches it with an integer format, `number` when it
  matches another format or is ambiguous; otherwise `text`.
- Accepted counts: `integer` counts integers, `number` integers and numbers,
  the others their own family. Shares compare exactly with the decimal value
  of the threshold.
- `counts` lists the families seen, in family order. `confidence` is the
  accepted share of the winning family, or the largest share for `mixed`,
  rounded to four decimals, and `null` for `empty`. `outside_count` is the
  number of values outside the winning family, `null` for `mixed` and 0 for
  `empty`.
- Families depend on the number and date detectors and their settings, as
  the current date family depended on `date_detection`: a disabled or failed
  detector contributes no family. Differences with the pandas engine, adopted
  by the report in lot 5a (section 16.4): decimal conventions and month names are accepted, ambiguity is
  never resolved from evidence, and a date column with several formats or
  ambiguous values is `date`, where the current engine says `mixed`.

### 9.8 Normalization

See section 10.

### 9.9 Empty inputs (O15)

- A CSV with only a header gives a `rows` dataset with zero records and one
  field per column; counts are zero and value measures are
  `not_applicable` with reason `no_values`.
- An empty JSON array gives a dataset with zero records and no fields.
- A field without values gives `not_applicable` value measures.
- `not_applicable` measures of lot 2a use the reason `no_values`: the
  population of the measure is empty.
- An empty file is fatal: a CSV needs a header, and an empty file is not JSON.
- Percentages are left to consumers; the scan publishes counts and
  denominators, so no division by zero can occur in the scan.

### 9.10 Records (lot 5c)

Each dataset has a `records` block of record-level facts (section 16.2):

```json
{"with_missing": {"count": 2, "records": [2, 5]},
 "empty": {"count": 1, "records": [5]},
 "duplicates": {"count": {"status": "complete", "value": 1}, "records": [3]},
 "preview": [{"record": 1, "values": {"column_1": ["1"], "column_2": [""]}}]}
```

- The values of a record are its scalar observations (strings, numbers,
  booleans, nulls). An absent field is not a value of its record.
- `with_missing`: records with at least one value missing under
  `values.missing`; `empty`: records with values, all missing. A record
  without values is neither.
- `duplicates`: records equal to an earlier record of the same dataset,
  beyond the first occurrence. Records compare every observation (path,
  native type, raw value) through a 128-bit BLAKE2b digest, one per distinct
  record: exact up to a negligible collision probability. A record of a
  table is its values alone, hashed joined by NUL characters when none holds
  one (CSV values never do), otherwise with their lengths, each form with its
  own personalization (lot 6). The digests of the
  whole scan are bounded by `limits.max_tracked_records`: once it is reached,
  new digests are not stored but records are still compared with the stored
  ones, so every counted duplicate is proven, and the count of a dataset with
  an untracked record is `limited` with reason `record_budget` and the count
  as `lower_bound`. `disabled` when `records.duplicates` is `false`.
- `records` lists the first record indices, up to
  `limits.max_listed_records`.
- `preview`: the first `records.preview` records, values per field id as
  canonical text (section 9.1), in observation order for items paths; a JSON
  null is `null`; untracked paths and absent fields have no key. The exposure
  gate applies at finalization (12.8): `content` strings, numbers and
  booleans of a sensitive field are masked, or their cell is `null` under
  `hide`; nulls and non-content strings stay as read.

## 10. Normalization version 1 (D15, D16, EF33-EF38, O08)

Normalization applies to `content` strings only, never to the source. Stages
run in this order; each can be disabled:

| Stage | Definition | Default |
| --- | --- | --- |
| `nfc` | Unicode canonical composition (NFC). Compatibility forms (NFKC) are not applied. | on |
| `trim` | `str.strip()`: removes leading and trailing characters for which `str.isspace()` is true, including no-break spaces. | on |
| `collapse_whitespace` | Replaces every run of whitespace other than line breaks (`[^\S\r\n\v\f\x1c-\x1e\x85]+`) with one U+0020 space. | on |
| `casefold` | `str.casefold()`. | on |
| `strip_accents` | NFD, removal of combining marks (category `Mn`), then NFC. | on |

- The **analytical value** is the output of the enabled `nfc`, `trim` and
  `collapse_whitespace` stages. Frequencies listings, samples, lengths,
  detectors and statistics use it.
- The **comparison key** is the output of every enabled stage. It groups
  variants.
- Per stage, the result lists `{stage, enabled, changed, cardinality}`:
  `changed` counts occurrences modified by that stage given the output of the
  previous enabled stage; `cardinality` is the distinct count after the stage.
  A disabled stage passes its input through, has `changed` and `cardinality`
  set to `null` and influences nothing (CA16). The first entry is `raw`, with
  `changed` set to `null` and the raw cardinality, the same envelope as
  `values.cardinality`.
- `changed` counts `content` strings only. `cardinality` covers the whole
  `values` population by `(native type, text)`: integers, numbers and booleans
  pass through every stage unchanged, so the `raw` entry equals the raw
  cardinality.
- `changed` counters are exact streaming counters: they continue when tables
  are limited (ET09, CA17). Stage cardinalities are envelopes derived from the
  raw table: when it is released they become `limited` with the table's reason
  and limit and no `lower_bound`, since raw distinct values do not prove
  normalized ones. Without values they are `not_applicable` (`no_values`) and
  `changed` is 0.
- `variant_groups`: envelope over `content` strings whose value is
  `{groups, listed, truncated}`. `groups` counts the comparison keys with at
  least two distinct raw variants; `listed` holds the
  `limits.max_variant_groups` largest as `{key, count, distinct, variants,
  truncated}`, ordered by `count` (occurrences of every variant, descending)
  then key. `variants` holds the `limits.max_variants_per_group` most frequent
  raw strings of the group as `{value, count}`, ordered by count (descending)
  then value; `distinct` counts every raw variant and `truncated` says the
  listing is shorter. Both limits truncate output only, like
  `max_listed_frequencies`. The envelope is `limited` like stage
  cardinalities when the table is released, and `not_applicable`
  (`no_values`) without `content` strings.
- A group is an analytical equivalence under these rules, not proof of business
  identity.
- `normalization.version` is `1`. Any change to these definitions increments it.

## 11. Limits and degradation (ET05-ET11, O09)

| Setting | Default | Hard cap | Effect when reached |
| --- | --- | --- | --- |
| `max_fields` | 10,000 per dataset | 1,000,000 | New paths are not tracked; `structure.paths` becomes limited; observations counted in `structure.untracked_observations`; warning `field_limit`. |
| `max_depth` | 64 | 1,000 | Deeper content is not traversed; counted in `structure.depth_truncated_observations`; warning `depth_limit`. |
| `max_record_observations` | 100,000 | 100,000,000 | Record excluded (tolerant) or fatal (strict); `record_too_large`. |
| `max_distinct_per_field` | 100,000 | 50,000,000 | The raw table is released; cardinality, frequencies, stage cardinalities, variant groups and derived medians become limited with reason `distinct_limit`. |
| `max_tracked_values` | 2,000,000 per scan | 500,000,000 | Global budget: the largest table is released first (ties: most recently discovered field); reason `global_budget`; warning `global_budget`. |
| `max_stored_value_length` | 1,000 characters | 1,000,000 | Longer values are counted but not stored: the first one releases the raw table, and table-based measures of that field become limited with reason `value_too_long`. |
| `max_listed_frequencies` | 100 | 100,000 | Output truncation only. |
| `max_samples` | 100 | 10,000 | Output size only. |
| `max_variant_groups` | 100 | 100,000 | Output truncation only. |
| `max_variants_per_group` | 20 | 10,000 | Output truncation only. |
| `max_evidence_examples` | 10 | 1,000 | Detector evidence size only. |
| `max_tracked_records` | 2,000,000 per scan | 500,000,000 | Duplicate digests stop being stored (about 80 bytes each); later records are still compared; duplicate counts of datasets with untracked records become limited with reason `record_budget`; warning `record_budget`. |
| `max_listed_records` | 10 | 10,000 | Output truncation of the record listings only. |

- Defaults are starting values, not validated budgets. Phase 6 revisits them
  with measurements.
- Degradation is one measure at a time; counters, normalization change counts,
  numeric and string statistics and detector coverage continue after a table is
  released (ET08).
- Hard caps are the protected core configuration: a user value above a cap is
  rejected before the scan starts (CA13).
- `max_distinct_per_field` must not exceed `max_tracked_values`.
- Discovery order for budget ties is the order in which fields are registered
  across the datasets of the scan (declared CSV columns in header order), not
  the order of their first values.
- Proven lower bounds of a released table: `L + 1` for `distinct_limit`, the
  stored distinct count for `global_budget`, and the stored distinct count plus
  one for `value_too_long`, the long value being longer than every stored one.
  Canonical text lengths are compared.
- The global budget counts stored distinct values of every field of the scan.
  Finding the largest table scans the fields with a table; lot 6 may make it
  cheaper for wide sources.
- `max_fields` and `structure.paths` count field paths other than the record
  root, including declared CSV columns. The lower bound published when
  `max_fields` is reached is `max_fields + 1`: untracked paths are not
  remembered, so state stays bounded and no larger count is proven. The
  `field_limit` warning locates the first record with an untracked
  observation.
- `max_depth` is relative to the record root (`orders[].amount` has depth 3).
  An observation deeper than the limit is not emitted; every value of the
  truncated subtree counts in `depth_truncated_observations`. Array lengths
  still count truncated elements. `max_depth_seen` is the deepest analyzed
  observation, tracked or not, so it never exceeds `max_depth`. The
  `depth_limit` warning locates the first truncated record.
- A CSV header with more than `max_record_observations - 1` columns is fatal
  in both policies: every record would be too large.

## 12. Detectors (EF24-EF32, D09, D14)

### 12.1 Contract

```python
class Detector:
    id: ClassVar[str]                     # "date", "email", "pattern:customer_number"
    version: ClassVar[int] = 1
    family: ClassVar[str]                 # "number", "temporal", "contact", ...
    accepts: ClassVar[frozenset[str]] = frozenset({"string"})   # native types
    sensitive: ClassVar[bool] = False
    max_input_length: ClassVar[int | None] = None   # longer values: not_tested
    scope: ClassVar[Literal["value", "field"]] = "value"
    shapes: re.Pattern[str] | None = None            # section 12.5

    def __init__(self, settings: Mapping[str, object]) -> None: ...
    def classify(self, value: str) -> Classification | None: ...
    def classify_many(self, values: Sequence[str]) -> list[Classification | None]: ...
    def accumulator(self) -> DetectorAccumulator: ...

class DetectorAccumulator:
    def add(self, value: str, classification: Classification | None, count: int) -> None: ...
    def details(self, gate: ExposureGate) -> dict[str, object]: ...
    def field_matches(self) -> bool: ...          # field-level detectors only
    def rejects_field(self) -> bool: ...          # field-level detectors only
```

- `classify_many` (lot 6) classifies a batch of distinct values and must
  return exactly `classify` of each value, in order; the default maps
  `classify`. Built-in detectors override it to reject most values by an
  exact cheap check, without a call per value. If it raises, the engine
  classifies each value alone to locate the failure.
- `rejects_field` (lot 6) lets a field-level detector say that the field can
  no longer match whatever values follow, and that `add` no longer changes
  `details`: later values count as not matched without being classified.
  Only for detectors whose `classify` never returns `ambiguous` or
  `invalid`; `enumeration` rejects a field once it holds
  `maximum_distinct + 1` values.
- `Classification` is an immutable named tuple since lot 6, built about twice
  as fast as a frozen dataclass.

- `classify` is pure and deterministic: the same value always gives the same
  result. `None` means not matched. This makes memoization and per-distinct
  execution exact (section 13).
- `Classification` carries `state` (`matched`, `ambiguous`, `invalid`), an
  optional `format`, `candidates` for ambiguous values, an optional `reason`
  for invalid values and an optional parsed value for statistics. `invalid`
  means the value has the detector's shape but fails validation, such as
  `2026-02-30`. A `matched` value with `candidates` was ambiguous and was
  resolved by configuration. `convention` names the reading of an
  unambiguous value when several readings exist (date order, decimal
  convention); it feeds the ambiguity evidence (12.6).
- `classify` receives the analytical value of strings and the canonical text
  (9.1) of other accepted native types. Built-in detectors accept strings
  only: native values are already typed.
- The engine keeps coverage, formats (the `format` of matched values) and
  evidence for every detector. The accumulator receives
  `(value, classification, count)` for every tested value, `None` meaning not
  matched, and produces the detector-specific `details`, such as email
  domains. In both execution modes it sees the same distinct values, first
  seen first, with the same total counts. `details` receives the exposure
  gate of the field (12.8): any value it carries must go through it.
- A detector with `scope = "field"` decides at the end, through
  `field_matches()`, whether all its values match or none does; when none
  does, matched values count as `not_matched` and it has no formats.
- Any exception raised by a detector's code (`classify`, `accumulator`,
  `add`, `details`, `field_matches`) or a `classify` result that is not a
  `Classification` fails the detector on that field only (section 14). The
  `detector_failed` diagnostic names the detector, the field and the
  exception type, never its message, which could quote a value.
- `DetectorRegistry` holds detector classes by `id`, in registration order.
  `default_registry()` returns a fresh registry with the built-ins `number`,
  `date`, `boolean`, `enumeration`, `email`, `url`, `phone`, `postal_code`,
  `currency`, `percentage`, `quantity`, `uuid` and `ip_address`;
  `register(cls)` adds one and rejects
  a duplicate id. External plugin loading is deferred (O21). Declarative
  patterns (12.7) follow the registry's detectors, in configuration order.
- Configuration: `detectors.<id>` holds `enabled` and detector parameters
  (D14). Complex logic stays in code. Detectors registered without a
  configuration section receive empty settings and are enabled.
- Every field lists every registered detector, in registry order. The
  result of an enabled detector is `complete`, `not_applicable` (reason
  `no_values`, when the field has no eligible value) or `failed`; a disabled
  detector is `{"id", "version", "status": "disabled"}`.
  `engine.detectors` gives the version of each enabled detector.

### 12.2 Coverage (EF26, CA11)

For each detector and field:

- `eligible`: analyzable values of an accepted native type.
- `tested = eligible - not_tested`
- `tested = matched + ambiguous + invalid + not_matched`
- `share_tested = matched / tested` and `share_eligible = matched / eligible`,
  both published with their denominators.

`not_tested` is non-zero only for values longer than a detector's input cap
and for values skipped by adaptive detection (section 13), whose count the
result publishes in `adaptive`. With `detection.warmup_values` set to 0,
detection is exhaustive.

### 12.3 Result

```json
{
  "id": "date",
  "version": 1,
  "status": "complete",
  "coverage": {"eligible": 3, "tested": 3, "matched": 2, "ambiguous": 0,
               "invalid": 0, "not_matched": 1, "not_tested": 0,
               "share_tested": 0.6667, "share_eligible": 0.6667},
  "formats": [{"format": "YYYY-MM-DD", "count": 1}, {"format": "DD/MM/YYYY", "count": 1}],
  "evidence": {"matched": ["2026-09-26"], "invalid": [], "not_matched": ["x"]},
  "details": {},
  "adaptive": null
}
```

`adaptive` is `null` unless adaptive detection skipped the detector on the
field (section 13); it is then
`{"skipped_after": 10000, "warmup_reactions": 0, "not_tested": 1200, "diagnostic": null}`:
the warm-up size, the distinct warm-up values the detector reacted to (0, or
at most `detection.rare_share` of them for a rare detector, scan format
revision 4), the occurrences skipped (included in `coverage.not_tested`) and
the index of the `detector_skipped_reacted` warning when probes reacted more
often than the warm-up allowed, else `null`.

A failed detector has `status: "failed"`, `reason: "detector_error"`, a
`diagnostic` index and no `coverage`: a failure is never reported as values
that did not match (CA19).

- `share_tested` and `share_eligible` are rounded to four decimals;
  `share_tested` is `null` when no value was tested.
- `formats` are ordered by count (descending), then format.
- `evidence` has the keys `matched`, `ambiguous`, `invalid` and
  `not_matched`: the first distinct analytical values of each state, at most
  `limits.max_evidence_examples` each, without values longer than
  `limits.max_stored_value_length`. They go through the exposure gate
  (12.8).

### 12.4 Interpretations (EF24, EF27, CA12)

The technical type (9.7) and semantic interpretations are separate axes.
`interpretations.candidates` lists every detector whose `share_eligible`
reaches `detection.minimum_share` (default 0.95), ordered by matched count
then detector id, as `{detector, matched, share_eligible}`; a detector
without matched values never qualifies. `interpretations.primary` is the id
of the only candidate when exactly one qualifies, else `null`. Overlaps are
kept: `12345` may be an integer and a ZIP code; both are listed (CA10).

### 12.5 Shape classifier (EF30)

Each value gets a cheap shape signature (digits as `9`, letters as `A` or `a`,
other characters kept, runs compressed). Detectors may declare the shapes they
can match so others are rejected without running their full logic. Rejection
by shape is an exact `not_matched`, not `not_tested`.

- ASCII digits become `9`, uppercase letters `A`, other letters (including
  uncased ones) `a`: `2026-09-26` is `9-9-9`, `Québec` is `Aa`.
- `Detector.shapes` is a pattern the signature must fully match; it must
  accept the signature of every value `classify` can match. The signature is
  computed at most once per value, only when a detector declares shapes.
- Built-in detectors declare none: their exact first-character or
  character-set checks are cheaper than a signature. Shapes serve costlier
  detectors (catalogue, patterns).

### 12.6 Ambiguity (O06, specification 12.1)

An ambiguous value, such as `01/02/2026` when both `DD/MM/YYYY` and
`MM/DD/YYYY` are allowed, stays ambiguous. The date detector publishes, in its
`details`:

```json
"ambiguity": {"count": 1, "candidates": [{"formats": ["DD/MM/YYYY", "MM/DD/YYYY"], "count": 1}],
              "evidence": {"DMY": 1, "MDY": 0}, "resolution": null}
```

- `evidence` counts unambiguous values per order in the same field. It is
  exposed, never applied, by the scan and by the report (section 16.4).
- Only configuration resolves ambiguity (`detectors.date.ambiguous_order`),
  and then `resolution` is `{"order": "DMY", "source": "config"}` and resolved
  values count as matched.
- `count` and `candidates` cover every value ambiguous under the enabled
  readings, resolved or not, so a configured resolution shows what it
  decided; `coverage.ambiguous` counts unresolved values only. Candidates
  list their formats sorted, and are ordered by count (descending), then
  formats.
- `evidence` lists `DMY` and `MDY` when both orders are enabled, and is
  empty otherwise.
- Ambiguous values never enter statistics that need one interpretation.

The same rule applies to numbers such as `1,234`, ambiguous between a US
thousands separator and a French decimal comma: the number detector
publishes the same `ambiguity` block, with `evidence` for `comma` and `dot`
when both conventions are enabled (empty otherwise) and `resolution`
`{"convention": "comma", "source": "config"}` from
`detectors.number.ambiguous_convention`.

### 12.7 Declarative patterns (EF29, O11)

`patterns` entries become detectors with id `pattern:<id>`:

```json
{"id": "customer_number", "regex": "C-\\d{4}", "description": "Customer number",
 "accepts": ["string"], "sensitive": false, "max_input_length": 256}
```

- The regex is compiled at configuration validation and matched with
  `fullmatch`. Invalid expressions are configuration errors.
- Hard caps: 200 patterns, 1,000 characters per expression, 10,000 characters
  per tested value. Values above `max_input_length` are `not_tested`.
- Python `re` has no timeout. Catastrophic backtracking remains possible with
  hostile expressions; the documentation must say that patterns are trusted
  configuration. A safer engine is a later option.
- Pattern identifiers must be unique. The `pattern:` prefix keeps them apart
  from built-in ids; a registered detector whose id equals a pattern's
  detector id is a `ConfigurationError` when the scan starts.
- Pattern detectors have family `pattern`, no formats and no `details`; they
  follow the registry's detectors in configuration order. Values of other
  accepted native types are matched on their canonical text (9.1). Their
  specification is in [detectors.md](detectors.md).

### 12.8 Sensitive values and exposure (ET17, O10, CA20)

- A field is sensitive when a sensitive detector matched at least one of its
  values, or failed on one of them: a failure cannot prove that nothing
  matched. This is deliberately conservative.
- `exposure.sensitive_values` is `mask` (default), `hide` or `show`.
- Every value-bearing block of a sensitive field (frequencies, samples, first
  and last values, variant groups, detector evidence and value-bearing
  `details`) passes through one exposure gate at finalization, once every
  value has been tallied, in both execution modes.
- `mask` replaces each uppercase letter (`str.isupper`) with `A`, every other
  letter with `a` and each digit (`str.isdigit`) with `9`, keeps other
  characters and does not compress runs, then merges equal masks before
  listings are selected: frequencies, samples and variant groups describe the
  masked values. `frequencies.distinct` counts distinct masks; ranking and
  sampling apply to masks. Variant groups with equal masked keys merge, as do
  equal masked variants of a group; `groups` and `distinct` count masked
  entries. Evidence lists distinct masks in first-seen order.
  `values.cardinality` and stage cardinalities stay raw counts.
- `hide` removes the values and keeps counts: listings of frequencies,
  samples, variant groups and evidence are empty (`truncated` is `true` when
  something was hidden), `first` and `last` are `null`.
- `show` exposes values unchanged.
- Statistics that are values themselves, such as a minimum or a date range,
  cannot be masked: under `mask` and `hide`, the `numeric` and `temporal`
  blocks of a sensitive field are `disabled`. Counts, lengths,
  characteristics and coverage stay.
- The effective configuration is not a value-bearing block.
- The field records `sensitive` and `exposure`, the mode applied (`null` when
  the field is not sensitive).

### 12.9 Catalogue

The catalogue and its priorities come from the specification. Lot 3a ports the
current rules (numbers, dates, booleans, enumeration candidates); lot 3b starts
the priority 1 catalogue. Each detector gets a short entry in `detectors.md`
before implementation: accepted formats, normalization, validation level,
overlaps, sensitivity and test values (O14). Detectors check syntax, never
real-world existence (EF32).

### 12.10 Built-in detectors (lot 3a)

The specifications of `number`, `date`, `boolean` and `enumeration` moved to
[detectors.md](detectors.md) in lot 3b, unchanged.

## 13. Execution strategy and performance (EF30, EF31, ET12)

Every per-value computation (normalization stages, number parsing, detector
classification, shapes) is a pure function of the value. The engine exploits
this without changing results:

1. While a field's raw frequency table is complete, per-value work runs once
   per distinct value, weighted by its count, at finalization.
2. When the table is released, the engine first processes the stored distinct
   values with their counts, then switches the field to streaming mode: new
   occurrences are gathered in a batch of distinct values with their counts
   (at most `values.BATCH_SIZE`, 4,096), processed whenever it is full and at
   the end. The batch is the memoization of lot 6; it replaced a cache that
   unique values emptied constantly.
3. Both modes produce identical results. A contract test compares a scan with
   `max_distinct_per_field=1` and a scan with the default for every
   non-table measure.
4. Adaptive detection (lot 6, O23). The first `detection.warmup_values`
   distinct values of a field, in first-seen order, go through every
   detector. The next distinct value ends the warm-up: each adaptive detector
   that reacted to none of them (no `matched`, `ambiguous` or `invalid` value,
   no failure) is skipped for the rest of the field. Later values are
   classified by the other detectors only, and count as `not_tested` for the
   skipped ones, except:
   - warm-up values, at every occurrence: a streamed field keeps its warm-up
     values (at most `warmup_values` per field) to recognize them;
   - probes: values whose CRC-32 (of the raw string, or of `type:canonical`
     for other native types) is a multiple of `detection.probe_interval`,
     about one distinct value in `probe_interval`, go through every detector.
     A skipped detector that reacts on a probe keeps counting it, and the
     field gets a `detector_skipped_reacted` warning: its counts are
     incomplete, and a scan with `warmup_values` 0 gives them exactly.

   A skipped detector is never re-enabled: a re-enabled detector would count
   the later occurrences of an earlier value differently in streaming mode,
   which cannot recognize them. Every rule above depends only on the
   first-seen order of distinct values and on each value, so both execution
   modes keep identical results. `number` and `date` are never skipped: they
   give every value its technical type family (9.7). A field with at most
   `warmup_values` distinct values stays exhaustive, so small files are never
   affected.

   With `warmup_values` 10,000, a detector reacting on at least 0.05% of the
   distinct values of a field, spread through the file, is skipped by
   mistake with a probability below 1% (`e^(-p × warmup)`); interpretations
   need 95%, so they never change. Sorted files remain the risk the probes
   cover.

   Rare detectors (lot 6, O24): a detector is also skipped when it reacted to
   at most `detection.rare_share` of the warm-up values (default 0.001, so 10
   values of 10,000) and to none of the second half of the warm-up, whose
   values are those after the first `warmup_values // 2`: its reactions were
   rare and have stopped. A detector still reacting in the second half stays,
   as in a sorted column where matches become frequent (identifiers crossing
   from four to five digits make ZIP codes frequent right after 10,000). A
   rare sensitive detector that has not matched stays: the field might have
   values to mask. Reactions are counted once per distinct warm-up value,
   which a streamed field recognizes through its warm-up values, so both
   modes decide alike. After a rare skip, probes that react on at least
   `PROBE_REACTIONS` (10) occurrences, more than `rare_share` of the probed
   occurrences, raise `detector_skipped_reacted`; warm-up values met again by
   a streamed field are not probes. `rare_share` 0 gives the rule of the
   first version.

   Open point: sensitive detectors (`email`, `phone`, `ip_address`) are
   skipped like the others when they reacted to nothing. A sensitive value
   first met after the warm-up, outside a probe, is therefore not detected
   and the field is not masked (12.8). With the batches of item 5, keeping
   them would cost little: to be decided before a release that relies on
   masking.
5. Batches (lot 6, O25). Per-value work runs on batches of distinct values in
   first-seen order: strings are normalized in one pass (printable strings in
   NFC inline, with the same results as `Normalizer.run` and
   `characteristic_flags`), then each detector classifies the whole batch
   through `classify_many`, and its tally counts the unmatched values
   together. A skipped detector counts its values as not tested in one
   addition, and a field-level detector that rejects the field
   (`rejects_field`) counts them as not matched. Order-dependent outputs
   (evidence, samples, first-seen listings) follow the first-seen order of
   the batch.
6. Column batches (lot 6, O25). A `RecordBatch` (section 6) is read column by
   column: each column is counted into its table at C speed, and the strings
   that are not content are taken out again. A field's own limits
   (`max_distinct_per_field`, `max_stored_value_length`) apply to its new
   values in first-seen order, as if they were added one by one; a table
   released inside a batch already holds the later values of the batch,
   processed with their counts, which gives the same results as streaming
   them. The global budget depends on the order of values across fields: a
   batch is read column by column only when it cannot exceed the budget
   (stored values plus rows times growing columns), otherwise record by
   record, in reading order.
7. Workers (lot 6, O25). Sources of at least 16 MiB are analyzed with worker
   processes (`scan(workers=...)`, `--workers`), one per spare processor, at
   most 8: the scan process reads, keeps tables, budgets and record facts,
   and hands the per-value work of each field to one worker: its released
   table, then its streaming batches in reading order, or its complete table
   at finalization, the largest first. A worker processes the values exactly
   as the scan process would, so results are identical. Workers return value
   blocks as plain data (generic models cannot be pickled), validated again,
   with placeholder diagnostic indices that the scan process replaces by
   reporting the diagnostics in field order. Workers are subprocesses of the
   running interpreter talking pickled messages over their standard streams,
   so starting them never imports the caller's main module; when they cannot
   start, the scan stays in one process. A custom `registry` always stays in
   one process. The number of workers is not part of the configuration and
   never appears in the result.

The pandas engine of the first releases was vectorized; a pure Python
streaming engine has a higher cost per cell. The per-distinct strategy,
batches and workers are the mitigation: since lot 6, the scan is faster than
the pandas baseline with bounded memory. Measurements are in
[benchmarks.md](benchmarks.md); targets remain to be decided (O19). The next
step is reading one source with several processes, which needs mergeable
states (lot 7).

## 14. Diagnostics and error policy (O07, specification 8)

Data observations (mixed types, missing values, duplicates) are results, not
diagnostics. Diagnostics describe technical events:

```json
{"code": "csv_width_mismatch", "level": "error", "message": "...", "count": 2,
 "dataset": "rows", "field": null, "detector": null,
 "locations": [{"record": 2, "line": 3}, {"record": 3, "line": 4}]}
```

Levels are `fatal`, `error` and `warning`. `locations` keeps at most
`errors.max_locations` entries; `count` is always complete. Lost records are
never guessed when corruption prevents delimiting them.

| Situation | `strict` (default) | `tolerant` |
| --- | --- | --- |
| Unreadable file, undecodable text, NUL characters | Fatal `InputError` | Fatal |
| CSV record of unexpected width, including blank lines | Fatal `InputError` naming record and line | Record excluded, `csv_width_mismatch` error, scan status `partial` |
| CSV quoting error (`csv.Error`) | Fatal | Fatal: resynchronization is uncertain |
| Invalid JSON syntax, empty JSON file, invalid UTF-8 | Fatal | Fatal |
| JSON string or key with a lone surrogate escape (`"\ud800"`) | Fatal `InputError` | Fatal |
| JSON object with a duplicate key | Fatal `InputError` naming record and key | Record excluded, `json_duplicate_key` error, reason `duplicate_key`, status `partial` |
| Explicit JSON collection without any array at its path | Warning `json_collection_not_found`, empty dataset | Same |
| Record above `max_record_observations` | Fatal | Record excluded, `record_too_large` error, status `partial` |
| CSV header wider than `max_record_observations - 1` columns | Fatal | Fatal |
| Structural limit (`max_fields`, `max_depth`) | Warning, scan continues | Same |
| Measure limit | Envelope status, plus one `measures_limited` warning per dataset: `count` is the number of fields, the message names at most 10 | Same |
| Global value budget | One `global_budget` warning per scan: `count` is the number of released tables | Same |
| Duplicate record budget | One `record_budget` warning per scan: `count` is the number of records whose digest was not stored | Same |
| Detector exception | Detector `failed` on that field, `detector_failed` error, other analyses continue | Same |
| Skipped detector reacting on a probe (section 13) | `detector_skipped_reacted` warning per field and detector: `count` is the number of occurrences that reacted; for a rare detector, only when probes reacted more often than its warm-up | Same |

- Scan `status` is `complete` when every record in the requested scope was
  analyzed, `partial` when records were excluded. Fatal problems raise and
  produce no result.
- `scope` reports `records_read`, `records_analyzed`, `records_excluded` and
  exclusions per reason (EF05). A dataset's `record_count` counts analyzed
  records only.
- CLI exit codes follow the existing commands: 2 configuration, 4 input,
  1 other failures, 0 success including `partial`, with a warning on standard
  error.

## 15. Configuration (EF28, EF40-EF42, O13)

`ScanConfig` is a strict Pydantic model. In phase 4 it becomes the `scan`
section of `tabalyst.json`; since lot 5a the report reads its analysis
settings from it (section 16.4).

```json
{
  "scan": {
    "csv": {"encoding": "utf-8-sig", "delimiter": ","},
    "json": {
      "collections": null, "discovery_max_depth": 3,
      "flatten": {"enabled": true, "separator": ".", "max_depth": null},
      "arrays": {"mode": "preserve"}
    },
    "errors": {"policy": null, "max_locations": 10},
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
    "detection": {"minimum_share": 0.95, "warmup_values": 10000, "probe_interval": 100,
                  "rare_share": 0.001},
    "detectors": {
      "number": {"enabled": true, "conventions": ["dot", "comma"],
                 "ambiguous_convention": null},
      "date": {"enabled": true, "orders": ["YMD", "MDY", "DMY"],
               "separators": ["-", "/", "."], "ambiguous_order": null,
               "month_languages": ["en", "fr"]},
      "boolean": {"enabled": true,
                  "pairs": [["true", "false"], ["yes", "no"], ["y", "n"],
                            ["oui", "non"], ["vrai", "faux"]]},
      "enumeration": {"enabled": true, "minimum_values": 500,
                      "maximum_distinct": 49, "case_sensitive": true},
      "email": {"enabled": true, "max_tracked_domains": 10000,
                "max_listed_domains": 20},
      "url": {"enabled": true, "schemes": ["http", "https", "ftp"],
              "www": true, "max_tracked_hosts": 10000, "max_listed_hosts": 20},
      "phone": {"enabled": true, "regions": ["nanp", "fr"]},
      "postal_code": {"enabled": true, "regions": ["ca", "us"]},
      "currency": {"enabled": true, "conventions": ["dot", "comma"],
                   "ambiguous_convention": null},
      "percentage": {"enabled": true, "conventions": ["dot", "comma"],
                     "ambiguous_convention": null},
      "quantity": {"enabled": true, "conventions": ["dot", "comma"],
                   "ambiguous_convention": null, "max_tracked_units": 10000,
                   "max_listed_units": 20},
      "uuid": {"enabled": true},
      "ip_address": {"enabled": true, "versions": ["ipv4", "ipv6"]}
    },
    "patterns": [],
    "exposure": {"sensitive_values": "mask"},
    "random_seed": 42
  }
}
```

Layers, from lowest to highest priority: hard caps (never overridden, only
enforced), built-in defaults, optional profile (phase 7), configuration files
(`--config` files in order), command-line options (`--delimiter`,
`--encoding`, `--collection`).

Configuration files (lot 4, maintainer decision):

- No file is discovered automatically: `tabalyst.json` is a conventional name
  passed with `--config`, so `report` and `sample` keep their behavior.
- One file serves every command: report and sample settings at the top level,
  scan settings in the `scan` object. The scan does not inherit the top-level
  `csv` settings.
- Every command validates each whole file, the `scan` object included, so a
  mistake in another command's section never passes silently. Errors name the
  file and the dotted key, such as `scan.limits.max_fields`.

Merge rules:

- Objects merge recursively, including `detectors.<id>`.
- Lists replace the previous list entirely (`null_markers`, `patterns`,
  `collections`).
- Unknown keys are errors.
- `null` is accepted only where the schema allows it and sets that value; there
  is no deletion syntax.

The result embeds the effective configuration and `config_sha256`, the SHA-256
of its canonical JSON (sorted keys, no whitespace, UTF-8) (EF42). Since format
revision 5 the embedded configuration is the one the scan applied:
`errors.policy: null` is resolved by the source format (`strict` for CSV and
JSON, `tolerant` for JSONL), unused flatten settings are normalized, and
collection paths are canonical (`resolve_config_defaults`, inspect design 5.5,
5.6, 10.3). `flatten` is applied by the JSON reader since lot
JI-3 (inspect design 7); `arrays.mode` has one value, `preserve`.

## 16. Result document (O01)

### 16.1 Top level

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.1.0a",
  "format_revision": 5,
  "engine": {"version": "0.4.0", "normalization_version": 1,
             "detectors": {"number": 1, "date": 1, "boolean": 1,
                           "enumeration": 1, "email": 1, "url": 1,
                           "phone": 1, "postal_code": 1, "currency": 1,
                           "percentage": 1, "quantity": 1, "uuid": 1,
                           "ip_address": 1}},
  "status": "complete",
  "started_at": "2026-09-26T22:00:00Z",
  "duration_seconds": 0.012,
  "source": {"format": "json", "name": "orders.json", "size_bytes": 312,
             "modified_at": "2026-09-26T21:58:00Z", "sha256": "...",
             "encoding": "utf-8", "csv": null},
  "config": {},
  "config_sha256": "...",
  "scope": {"collections": {"mode": "auto", "requested": null},
            "records_read": 5, "records_analyzed": 5, "records_excluded": 0,
            "exclusions": {}},
  "datasets": [],
  "diagnostics": []
}
```

- `source.csv` is `{"delimiter": ",", "header": [...]}` for CSV sources and
  `null` otherwise; `source.size_bytes` is the number of bytes read and hashed.
- `scope.collections` describes JSON collection selection and is `null` for
  CSV sources, which have no collections to select.
- A `limited` envelope omits `lower_bound` when no bound is proven.
- Diagnostic `locations` list only the keys that apply: `{record, line}` for
  CSV, `{record, element}` for JSON.

The format follows the repository convention: `format_version` names the
alpha family and `format_revision` increases for each meaningful change. Its
changelog is `docs/en/scan/format-changelog.md` (lot 4).

### 16.2 Datasets and fields

```json
{
  "id": "$.customers[]",
  "kind": "collection",
  "collection_path": [{"key": "customers"}, {"items": true}],
  "record_count": 4,
  "record_types": {"object": 4},
  "structure": {"paths": {"status": "complete", "value": 5},
                "untracked_observations": 0,
                "depth_truncated_observations": 0, "max_depth_seen": 3},
  "records": {"with_missing": {"count": 1, "records": [2]},
              "empty": {"count": 0, "records": []},
              "duplicates": {"count": {"status": "complete", "value": 0},
                             "records": []},
              "preview": []},
  "fields": [
    {
      "id": "f4",
      "path": [{"key": "orders"}, {"items": true}, {"key": "amount"}],
      "display": "orders[].amount",
      "name": "amount",
      "parent": "f3",
      "collection": null,
      "first_record": 1,
      "occurrences": 4,
      "presence": {"parent_type": "object", "parent_count": 4, "present": 4, "absent": 0},
      "native_types": {"number": 1, "integer": 1, "null": 1, "string": 1},
      "strings": {"count": 1, "empty": 0, "blank": 0, "marker": 0, "content": 1},
      "missing": {"count": 1, "definition": ["absent", "null", "empty", "blank", "marker"],
                  "components": {"absent": 0, "null": 1, "empty": 0, "blank": 0, "marker": 0}},
      "arrays": null,
      "values": {"count": 3, "cardinality": {}, "frequencies": {}, "samples": {},
                 "first": {}, "last": {}},
      "string_characteristics": {},
      "string_lengths": {},
      "numeric": {},
      "booleans": {},
      "temporal": {},
      "normalization": {"version": 1, "stages": [], "variant_groups": {}},
      "technical_type": {},
      "detectors": [],
      "interpretations": {"primary": null, "candidates": []},
      "sensitive": false,
      "exposure": null
    }
  ]
}
```

Fields appear in order of discovery. Blocks introduced by later lots are
absent until their lot, then always present (with an envelope status when
they do not apply). For reuse (O12, section 16.6), the source block carries
size, modification time and SHA-256, and the result carries `config_sha256`.

### 16.3 Output files (lot 4, O17)

`tabalyst scan data.csv` stores the scan in the shared storage; since lot JI-7 so
does a JSON, JSONL or NDJSON source (it used to write `data.scan.json` beside
the source). `-o` and `-d` export `<stem>.scan.json` and follow the other commands. Writing uses a temporary file in the target
directory and an atomic replace, so an interrupted scan never leaves a partial
result. Existing outputs require `--force`; an output can never replace an
input.

Lot 4 details:

- `-o` must end in `.json`; `-d` names outputs `<stem>.scan.json`. Planning
  is shared with `report` and `sample` (`tabalyst/batch.py`): the whole batch
  is rejected before any scan on a name collision (`a.csv` and `a.json`), an
  output that would replace an input or a configuration file, or an existing
  output without `--force`.
- The temporary file is `.<name>.<random>.tmp` in the target directory,
  flushed and synchronized before `os.replace`, and removed on failure.
- A failed source does not stop the batch; exit codes are those of section
  14, the most general failure winning.
- The document is `model_dump(mode="json", by_alias=True)`, indented by two
  spaces, UTF-8 without escaping, with a final newline.
- Progress: `reading` events carry `bytes_read` and `bytes_total`, at most
  once per percent of the file and never more often than every MiB; then
  `writing`, and `complete` once the document is written.

### 16.4 Report built on Scan (lot 5a, O16)

`tabalyst report` scans the CSV with the `scan` configuration and builds the
report profile (revision 3) from the result (`report_profile.py`). Decided with
the maintainer in lot 5a:

- **One pass.** Record-level facts (preview, duplicate rows, empty rows,
  rows with missing values) were collected through `scan(on_record=...)`;
  since lot 5c they are the `records` block of the scan (section 9.10),
  bounded by `limits.max_tracked_records`.
- **Configuration.** Every analysis setting of the report, CSV reading
  included, comes from `scan`. The top level keeps the presentation settings
  (`string_analysis`, `value_examples`; `preview_rows` until lot 5c moved it
  to `scan.records.preview`) and `csv` for
  `tabalyst sample`. Former report settings are rejected with their new
  location; a top-level `csv` value that differs from `scan.csv` is an error
  for the report, since the file would otherwise be read differently than
  written, unless the command line sets that value explicitly.
- **Types.** The report type is the technical type (9.7): a date column with
  several formats or ambiguous values is `date`. Unresolved ambiguous dates
  make the column `with_issues` and are counted by the `ambiguous_dates` issue.
- **Ambiguity (12.6).** The report never resolves ambiguity: it shows the
  ambiguous values, the evidence per order, and, when the evidence is
  one-sided, suggests `detectors.date.ambiguous_order`.
- **Semantic types.** `date` when the technical type is `date`, otherwise the
  primary interpretation (12.4), except `number` and `boolean`, which repeat
  the technical type.
- **Exposure (12.8).** The report applies the scan's exposure: masked or hidden
  values in examples, value profiles and the preview of sensitive columns;
  distinct counts stay raw. Missing cells of the preview stay as read.
- **Limits.** A limited distinct count or median is `null`, shown as
  `limited`, and the column is listed by the `limited_measures` issue. Records
  excluded under the `tolerant` policy are listed by the `excluded_records`
  issue. A CSV wider than `limits.max_fields` is a configuration error for
  the report, whose counts need every column.
- **Examples.** A complete value distribution comes from the frequency listing
  when it holds every value; otherwise examples are selected among the scan
  samples. Length examples come from the listing, then the samples.
- **Sources.** CSV and JSON sources since lot 5b (section 16.5).

The parity tests (`tests/scan/test_scan_report.py`) compare the report built
on Scan with the pandas engine on both demos, each known difference listed
explicitly.

### 16.5 JSON sources and detectors in the report (lot 5b)

Decided with the maintainer in lot 5b:

- **Datasets.** Profile revision 4 moves `summary`, `date_summary`,
  `columns`, `issues` and `preview` into `datasets`, one item per scan dataset
  (`id`, `kind`). A CSV source has its one dataset; a JSON dataset is listed
  when it has at least one column, so `$` disappears when every value lies in
  collections. `source` gains `format`; `delimiter` is `null` for JSON.
- **Columns.** Every CSV column. For JSON, the fields whose native types
  include a scalar or `null`, in discovery order, named by `display`
  (`orders[].amount`) with `position` their 1-based rank. Containers are
  structure, not columns; the structure section is not part of lot 5b.
  Missing counts and percentages use the value slots of the field,
  `occurrences + presence.absent`, the row count for CSV columns;
  `cell_count` sums them.
- **Record facts.** `RowFacts` dispatches records by dataset. A record's
  values are its scalar observations; it has missing values when one is null
  (under `values.missing`) or a missing string, and is empty when all are.
  An absent field is not a value of its record. Duplicate records compare a
  digest of every observation (path, type, value). The preview keeps the
  scalar values per path: an absent field is `null` with its position in
  `absent`, the values of an items path are joined with `, `, a JSON null is
  the text `null`, and a cell with any hidden value is `null`.
- **Excluded records.** Counted per dataset from the exclusion diagnostics
  (`csv_width_mismatch`, `record_too_large`, `json_duplicate_key`).
- **Detectors.** Each column lists the detectors that are `complete` with a
  match, an ambiguous or an invalid value, and the `failed` ones:
  `eligible_count`, `matched_count`, `matched_percent`, `ambiguous_count`,
  `invalid_count`, `formats` with percentages of the eligible values, and
  `primary` for the primary interpretation. The report shows them in a
  "Detectors and formats" section, one row per column and detector.
- **Outputs.** `tabalyst report data.json` writes `data.report.html` and
  `data.report.json`, so the profile never replaces the source; CSV names are
  unchanged.
- **HTML.** Several datasets render one view each, with a dataset selector in
  the navigation and element ids prefixed `d<N>-`; a single dataset keeps
  plain ids.

### 16.6 Report from a scan document (lot 5c, O12)

Decided with the maintainer in lot 5c:

- **Command.** `tabalyst report --scan INPUT...`: the inputs are scan
  documents. The report is built from the document alone (profile revision
  5): record facts come from its `records` blocks, so it equals the report
  of the source with the same scan settings, except `generated_at` and
  `processing_seconds`. Outputs are named after `source.name`
  (`report_name`), beside the scan document by default; the planning reads
  each document for that name and protects the source beside it from being
  replaced. The execution history names the source.
- **Documents.** `format`, `format_version` and `format_revision` must be
  those of the running version, otherwise `InputError` asking for a new
  scan; there is no migration. The document is validated as `ScanResult`.
- **Staleness.** The source is looked for beside the document under
  `source.name`. Missing: accepted, the document stands on its own, and
  the command warns that the source was not checked (scans written with `-d`
  elsewhere). Another size: stale. Otherwise its SHA-256 decides, whatever the
  modification time (amended in lot JI-2, DP-D): a touched file stays fresh, a
  file rewritten with the same size and time is stale. A document whose
  `engine.version` is not the running one is reported with a warning: it is a
  file the user chose, not a cache. Stale is an
  `InputError` (exit 4) naming the source and asking for a new scan.
- **Settings.** The document's `config` is the report's `scan`
  configuration. The `scan` settings of the configuration files, merged over
  the document's configuration, must leave its `config_sha256` unchanged,
  otherwise `ConfigurationError` (exit 2): settings the files do not give,
  such as a delimiter passed to `tabalyst scan`, are not compared.
  `--delimiter` and `--encoding` are rejected with `--scan`.
- **Batches.** A document that cannot be read while planning fails its own
  job only, its report named after the document file.
- **Timing.** `processing_seconds` of the profile is the time to read the
  document and build the profile.
- **Python.** `tabalyst.generate_reports(..., from_scan=True)` and
  `tabalyst.analyze_scan(path, config_path)`.

### 16.7 Normalization, limits and structure in the report (lot 5d)

Decided with the maintainer in lot 5d, for the sections deferred by lot 5b:

- **Profile.** Revision 6. The report carries the scan blocks without
  recomputing them.
- **Normalization.** Column `normalization` lists every stage of section 10,
  `raw` first, with `changed_count` (percent of the value slots, like the
  former trim and collapse counts) and `distinct_count` with its status, and
  the variant groups as the scan lists them, so already exposed (12.8). The
  "Transformations" section is extended rather than doubled: one column per
  stage, the analytical and compared distinct counts, the group count, then a
  table of the listed groups, whitespace shown as written. New info issue
  `variant_groups`.
- **Limits.** Each dataset has `limits`: every `limited` envelope of the
  dataset (`structure.paths`, `records.duplicates.count`) and of each field,
  containers included, found by walking the scan models and named by its
  location in the scan result (`values.cardinality`, `numeric.median`,
  `normalization.stages.casefold.cardinality`); the structural counters; and
  the diagnostics of the dataset and of the whole scan. A scan-wide diagnostic
  therefore appears in every dataset view. The "Limits and diagnostics"
  section is shown only when one of them is non-empty; the
  `limited_measures` and `excluded_records` issues link to it.
- **Structure.** JSON datasets only (a CSV is flat). `structure` lists every
  field, containers included, with depth (number of segments), parent,
  native types, presence per parent and array statistics; a promoted array
  names its collection. Presence of array items counts elements, so it has no
  percentage. Datasets without columns are still omitted (16.5): their
  structure is not shown.

## 17. Changes to this document

| Date | Lot | Change | Reason |
| --- | --- | --- | --- |
| 2026-09-26 | 0 | Initial contract. | Phase 0. |
| 2026-09-26 | 0 | Gate 0: every Proposed decision accepted without change. | Maintainer validation. |
| 2026-09-26 | 1a | Section 6: `DatasetOpened.fields` (declared fields), `RecordExcluded.code` and `message`, readers apply the error policy. | A header-only CSV must list its columns, and the engine must not know CSV diagnostic codes. |
| 2026-09-26 | 1a | Section 16.1: `source.csv` content, `scope.collections` null for CSV, `lower_bound` omitted when unproven, location keys per format. | Details the example did not settle. |
| 2026-09-26 | 1b | Section 6: `DatasetOpened.container`, `Record.depth_truncated`, `Notice` stream item; readers apply `max_depth` and `max_record_observations`; JSON element index is 0-based; records of datasets may interleave. | The engine links promoted arrays and reports truncation without knowing JSON; readers never build over-deep paths. |
| 2026-09-26 | 1b | Section 5.2: duplicate keys make a record malformed; UTF-8 byte order mark accepted; explicit selections listed in order, with `json_collection_not_found` when absent; overlapping, equivalent or empty selections rejected; document `collection_path` null. | Presence must stay exact; Windows tools write a byte order mark; a mistyped path must not pass silently. Maintainer decision. |
| 2026-09-26 | 1b | Section 11: `max_fields` lower bound is `max_fields + 1`; `max_fields` covers declared CSV columns; `max_depth` and `max_depth_seen` defined; CSV header above `max_record_observations` fatal. Section 14 rows added. | Counting every distinct untracked path would break bounded state (specification scenario 5). |
| 2026-09-26 | 2a | Sections 9.1 to 9.5: canonical text is `str()` of the parsed value; values output as canonical text; `frequencies.distinct` counts analytical values, limited frequencies have no bound; samples are a plain object in first-seen order; first and last values keep whole values; characteristic definitions; exact context of 200 digits and exponents within 1,000, integral output below 10^200; median limited with the table's reason and limit; booleans envelope. | `ijson` does not keep the source text; listings are analytical; a `limited` envelope needs a limit, and section 11 already named the table's reason. |
| 2026-09-26 | 2a | Section 11: the first value too long releases the table; proven lower bounds per reason. Section 14: `measures_limited` per dataset, `global_budget` per scan, lone surrogate escapes fatal. Section 9.9: `no_values` reason. Section 5.2: lone surrogates. | Details the contract did not settle; lone surrogates cannot be written as UTF-8 and the two `ijson` backends disagreed (lot 1b note). Maintainer decision. |
| 2026-09-26 | 2b | Section 10: `changed` counts content strings after the previous enabled stage; stage cardinalities cover the `values` population, are limited without bound after release and `not_applicable` without values; `variant_groups` value is `{groups, listed, truncated}`, groups carry `distinct` and `truncated`, orderings defined. Section 11: `max_variant_groups` and `max_variants_per_group` truncate output only. | Details the contract did not settle; a `limited` envelope has no value, so the literal rule would lose every group of a field with more than 100 of them. Maintainer decision. |
| 2026-09-26 | 3a | Sections 9.4 to 9.7: numeric population from the number detector; `temporal` layout; technical type families, `null` confidence for `empty`, `null` outside count for `mixed`. Section 12: the engine keeps coverage, formats and evidence, the accumulator produces `details`; `convention`, `scope`, `max_input_length` and `shapes`; failures keep the exception type only; every registered detector listed with its status; four evidence keys; candidate layout; shapes optional; ambiguity counts include resolved values; new 12.10 with the built-in detectors. Section 15: `detectors` settings. | Details the contract did not settle. The strict number rule keeps precedence so lot 2a results are unchanged; exception messages could leak sensitive values; the shape signature cost more than it saved for the built-ins. To validate at gate 3. |
| 2026-09-26 | 3b | Section 12.1: `details` receives the exposure gate; patterns follow the registry. Section 12.7: `pattern:` ids, collision with a registered detector, family, formats and details. Section 12.8: a failed sensitive detector makes the field sensitive; masks merge before listings are selected; `hide` empties listings and nulls `first` and `last`; `numeric` and `temporal` disabled under `mask` and `hide`; `exposure` field. Section 12.10 moved to `detectors.md`. | Details the contract did not settle: merging only the listed values would give wrong counts, a detector that failed cannot prove the field holds no sensitive value, and a minimum or a date range is a value (found in review). Maintainer decision. |
| 2026-09-26 | 3b | Sections 12.1, 15 and 16.1: built-in `email` and `url` detectors, enabled by default, with their settings; their specifications and the shared counted names block of `details` are in `detectors.md`. | Priority 1 catalogue, email and URL family. |
| 2026-09-26 | 3b | Sections 12.1, 15 and 16.1: built-in `phone` detector (regions `nanp` and `fr`), enabled by default, with its `regions` setting; its specification is in `detectors.md`. | Priority 1 catalogue, phone family. |
| 2026-09-27 | 3b | Sections 12.1, 15 and 16.1: built-in `postal_code` detector (regions `ca` for Canadian postal codes and `us` for ZIP codes), enabled by default and not sensitive, with its `regions` setting; its specification is in `detectors.md`. | Priority 1 catalogue, postal code family. |
| 2026-09-27 | 3b | Sections 12.1, 15 and 16.1: built-in `currency` (symbols and ISO 4217 codes), `percentage` and `quantity` (a number and any unit) detectors, enabled by default and not sensitive, with their own number conventions and ambiguity blocks, and bounded counted units for `quantity`; their specifications are in `detectors.md`. | Priority 1 catalogue, currency and percentage family, extended to generic quantities at the maintainer's request. |
| 2026-09-27 | 3b | Sections 12.1, 15 and 16.1: built-in `uuid` (hyphenated, braced and URN forms, versions counted, not sensitive) and `ip_address` (versions `ipv4` and `ipv6`, sensitive) detectors, enabled by default, with the `versions` setting of `ip_address`; their specifications are in `detectors.md`. | Priority 1 catalogue, UUID and IP address family, the last of lot 3b. |
| 2026-09-27 | 4 | Section 15: no automatic `tabalyst.json`; one file for every command with a `scan` object, validated by every command; command-line layer. Section 16.3: output naming, shared planning, temporary file, batch failures, document serialization, byte progress. Section 5.2: integers above `sys.int_max_str_digits` parsed by the pure-Python backend, exponent overflow and long parser messages. Sections 3 and 16.1: top-level exports, format changelog page. | Maintainer decision on configuration files (report behavior unchanged); the compiled `ijson` backend crashed the process on long integers (lot 2a note). |
| 2026-09-27 | 5a | Section 3: `on_record` hook of `scan()`. Section 12.6: the report never applies ambiguity evidence. New section 16.4 and decision O16: report built on Scan, configuration in `scan`, technical types, primary interpretations as semantic types, scan exposure applied to the preview, limited measures and excluded records as issues. | Report migration; decisions of the maintainer in lot 5a (configuration, masking by default, `date` type with an `ambiguous_dates` issue, primary interpretations). |
| 2026-09-27 | 5b | Section 16.4: JSON sources accepted. New section 16.5: profile revision 4 with `datasets`, JSON columns as scalar fields named by path, value slots, record facts per dataset, preview of JSON records, detectors per column, `.report` output names for JSON sources, one HTML view per dataset. | Lot 5b; maintainer decisions (revision 4 with a dataset list, flattened paths, detectors section only). |
| 2026-09-28 | 5c | New section 9.10 and `records` block of datasets (format revision 2): records with missing values, empty records, duplicates under the new `limits.max_tracked_records` budget with reason `record_budget`, preview through the exposure gate; `records` settings and `max_listed_records`; section 14 `record_budget` warning. Section 16.4: record facts from the scan, `preview_rows` moved to `scan.records.preview`. New section 16.6 and O12 accepted: report from a scan document and the staleness rule. Pandas engine removed after gate 5. | Maintainer decisions of lot 5c: record facts in the scan so a report needs no source, stale scans fail, pandas removed at gate 5. |
| 2026-09-28 | 5d | New section 16.7: profile revision 6 with every normalization stage and the variant groups per column, limits and diagnostics per dataset, structure of JSON datasets; "Transformations" extended, "Limits and diagnostics" shown only when needed, "JSON structure" for JSON sources only. | Sections deferred by lot 5b; maintainer decisions of lot 5d. |
| 2026-09-28 | 6 | Decision O23 and section 13 item 4: adaptive detection after a warm-up of `detection.warmup_values` distinct values per field, with probes every `detection.probe_interval`; section 12.2: `not_tested` of skipped values; section 12.3: `adaptive` in detector results (scan format revision 3); section 14: `detector_skipped_reacted` warning; section 15: new `detection` settings. | Detection of high-cardinality fields dominated the scan time; exact `not_tested` counts keep the contract. Re-enabling a detector after a probe was dropped: it would break principle 6. |
| 2026-09-28 | 6 | Decisions O24 and O25 (Proposed). Section 13 items 2 and 4 to 7: streaming batches instead of the memoization cache, rare detectors, batches of distinct values, column batches, worker processes. Section 6: `RecordBatch`, `Observation` as a named tuple, shared path objects. Section 12.1: `classify_many`, `rejects_field`, `Classification` as a named tuple. Section 12.3: `adaptive.warmup_reactions` (scan format revision 4). Section 9.10: table digests joined by NUL. Section 14: warning of rare detectors. Section 15: `detection.rare_share`. | The maintainer asked for the most speed on large files, progressive learning that drops what became unlikely, and reading that uses the machine: per-call overhead dominated, not the rules. The rare rule keeps detectors reacting at the end of the warm-up, found on the sorted `id` column of the benchmark. |
| 2026-09-30 | JI-2 | Decision O12 amended and section 16.6: the SHA-256 always decides for a present source (no modification-time shortcut); another engine version warns. Section 15 and 16.1 (format revision 5): `json.flatten`, `json.arrays`, nullable `errors.policy`, the document records the resolved configuration, collection paths in canonical spelling. | Inspect design DP-D and DP-10 (scan identity), lot JI-2. |
| 2026-09-30 | JI-4 | Section 5.3: JSONL sources, read as the dataset `$[]`; `limits.max_line_bytes`; `source.format` `jsonl`. |
| 2026-10-01 | JI-7 | Section 16.3: with no `-o` or `-d`, the scan of a JSON, JSONL or NDJSON source goes to the shared storage like a CSV's. Sources of these formats are read with the configuration resolved by Inspect (inspect design 11). |
