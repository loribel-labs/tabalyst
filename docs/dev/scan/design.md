# Tabalyst Scan design

Phase 0 contract, accepted at gate 0 on 2026-09-26. This document turns the
functional specification of Tabalyst Scan into the contract that the
implementation lots follow. The
specification is maintained privately (`tabalyst-gb`,
`drafts/2026-09-26-scan/Tabalyst-Scan-Cahier-des-charges.md`); its identifiers
(`Dxx`, `EFxx`, `ETxx`, `CAxx`, `Oxx`) are reused here for traceability.

Sections 18 to 21 (2026-10-06) add the contract of the Scan and JSON work:
bottom-k samplers, the shared Scan and Report document, the second pass and the
original value domain. They are Proposed until the maintainer accepts the
baselines of lot 0.

The phase plan, sessions and models are kept in the private maintainer
repository. The contract
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
| O22 | Approximations | Outside the contract. Any approximation requires a new explicit decision. Amended by O26: approximations are admitted when named. | Accepted (specification); amended 2026-10-06 | 8, 18.1 |
| O23 | Adaptive detection | Adaptive detectors that react to none of the first `detection.warmup_values` distinct values of a field (default 10,000) skip its later values, except probes; skipped values are `not_tested`, never guessed. `number` and `date` are never skipped. Sensitive detectors are skipped like the others for now (open point in section 13). | Accepted 2026-09-28 (lot 6) | 12.2, 13 |
| O24 | Rare detectors | Adaptive detectors that react to at most `detection.rare_share` of the warm-up values (default 0.001) and to none of its second half are skipped too; a rare sensitive detector without a match never is. Probes that react more often than the warm-up allowed raise `detector_skipped_reacted`. | Proposed 2026-09-28 (lot 6) | 12.3, 13 |
| O25 | Batch and parallel execution | Distinct values are processed in batches, detector by detector; CSV records arrive as batches of rows read column by column; large sources hand the values of each field to one worker process. Results never depend on batches or workers (principle 6). | Proposed 2026-09-28 (lot 6) | 6, 13 |
| O26 | Named approximations | An estimate (KMV cardinality, quantiles rebuilt from bins) may be published when it carries `accuracy: "estimated"`, its method and its parameters. It never uses the status `complete`. Principle 1 is amended accordingly. | Proposed 2026-10-06 (Scan and JSON lot 0) | 2, 18.1 |
| O27 | Report with a reduced sample | The Scan keeps the complete bottom-k sample of each field; the Report keeps fewer values (default 100, the smallest priorities, so an exact subset of the Scan's) with the same exact counters, and declares `kept` and `of`. A Report is not a valid input to replan an analysis. Amends the rule that the Report is a strict superset of the Scan. | Proposed 2026-10-06 | 19.4 |
| O28 | Tracking limit and sample size | The exact tracking limit T (`limits.max_distinct_per_field`, default unchanged at 100,000) and the bottom-k size K (`limits.max_samples`, default 10,000, at most T) are separate settings. Amended 2026-10-07: the first version set T = K = 10,000. | Proposed 2026-10-06, amended 2026-10-07 | 18.2 |
| O29 | Report as a document family | `format: "tabalyst.report"` is a superset of the Scan: the base keeps its paths, a common loader reads the base from a Scan or a Report, and the Report adds `report` and `analyses`. | Proposed 2026-10-06 | 19 |
| O30 | One format revision per release | The unpublished revision in progress absorbs the format changes of the work; each lot updates the changelog; the revision increases once, at the release. | Proposed 2026-10-06 | 19.6 |
| O31 | Second pass | `tabalyst scan --deep` forces a second pass written to a separate `<stem>.deep.json`; `tabalyst report` lets the planner decide under deterministic budgets; `tabalyst scan` never starts it. | Proposed 2026-10-06 | 20 |
| O32 | Original value domain | Bottom-k, patterns and smart sampling rest on original values; detectors and listings keep the analytical value, with the domain named in each block. | Proposed 2026-10-06 | 21 |
| O33 | Run block | `run` (start, duration, timings, workers, peak memory) holds what varies between runs on the same source; it replaces `started_at` and `duration_seconds` at the root. | Accepted (in the code since format revision 2) | 16.1 |

## 2. Principles

1. **Complete and exact, or explicitly limited or estimated.** Every record in
   the analyzed scope is read. A measure is either exact for its declared
   population (`complete`) or carries another status. An estimate is never
   presented as an exact value: it is published only with `accuracy:
   "estimated"`, its method and its parameters (O26).
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
7. **Smart by default, explicit when costly.** An automatic mode runs an extra
   operation only when its benefit is established and its cost is low, under
   deterministic budgets (section 20.2). Forcing a costly operation shows its
   estimate and asks first. The API never prompts. No long operation runs
   silently.

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
- `values.cardinality`: envelope, exact distinct count of the original values
  (raw, decoded, before any normalization stage: section 21). It carries
  qualifiers (lot 1a): `complete` has `accuracy` (`exact`), `domain`
  (`original`) and `identity_accuracy` (`exact`: values are compared whole).
  `limited` has `domain`, `identity_accuracy`, `upper_bound` (the certain
  maximum, `values.count`) and, for the reason `distinct_limit` only,
  `threshold_reached_at_record` (the record of the T-th distinct value) and
  `overflow_detected_at_record` (the record of the (T + 1)th, which proves the
  overflow). Records are numbered like `first_record`: a record with several
  occurrences of the field counts once, and the number does not depend on the
  reader (batches of CSV columns or one value at a time) or on the workers. A
  member that is unknown is absent, never `null`. `estimate` (lot 2b) is the
  KMV estimate of 18.5, published for a `limited` count when the samples saw the
  whole field (the values and, since lot 2c, the long texts). The other envelopes keep their members; a
  `complete` envelope without `accuracy` is exact for its declared population.
- `values.frequencies`: envelope whose value is `{distinct, listed, truncated}`.
  `distinct` counts distinct analytical values (`(type, analytical text)`),
  which may be fewer than the raw cardinality. `listed` holds the
  `limits.max_listed_frequencies` most frequent analytical values as
  `{value, type, count}`, ordered by count (descending), then value, then
  native type (`string`, `integer`, `number`, `boolean`). Output truncation is
  not a limitation of the measure: `truncated` says the listing is shorter than
  `distinct`. When the table is released, the envelope is `limited` without
  `lower_bound`: raw distinct values do not prove analytical ones.
- `values.samples` (lot 2b): a plain object `{selection, kept, of, listed}`
  (and `k`, `hash`, `threshold` for `bottom_k`, section 18.9) with up to
  `limits.max_samples` (K, 10,000 by default, section 18.2) distinct **original**
  values (section 21), not analytical ones. `selection` is `all` (every
  distinct value, in first-seen order, no hash) or `bottom_k` (the K of smallest
  priority, ascending). An entry is `{id, value, type, count, count_accuracy,
  identity_accuracy}`. Counts are exact in every selection. Values longer than
  `limits.max_stored_value_length` are not in the listing: they have their own
  small sample, the `long_texts` member (section 18.6), and `selection` and `of`
  describe the listed values only. `kept` listed values out of the `of` the
  scan sampled (section 19.4); exposure can make them differ (18.9). The size
  K can be smaller than the configured one when the memory budget cut it
  (`requested_k`, `reason`, section 18.10). Samples are examples, not
  statistics. The selections `uniform_distinct` and `first_seen` of the first
  revision are gone.
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
- `sample`: the row sample (section 18.11), a start, a bottom-k of the interior
  and an end of whole rows; `preview` stays the first records only.
- `preview`: the first `records.preview` records, values per field id as
  canonical text (section 9.1), in observation order for items paths; a JSON
  null is `null`; untracked paths and absent fields have no key. The exposure
  gate applies at finalization (12.8): `content` strings, numbers and
  booleans of a sensitive field are masked, or their cell is `null` under
  `hide`; nulls and non-content strings stay as read.

### 9.11 Rates of the report (A03)

The report derives four rates per column from scan counters, with
`percent(count, total) = round(100 * count / total, 2)`, and `0.0` when the
total is zero. They are views, not collectors: nothing is recomputed from the
source. Report rates are percentages from 0 to 100; scan shares
(`share_eligible`, `share_tested`, `confidence`) are fractions from 0 to 1.

`value_slots` of a field is `occurrences + presence.absent` (`absent` counts
as 0 where it is null): the records of the dataset for a CSV column, plus the
parent objects where a JSON member is absent, so a null and an absent member
both occupy a slot.

| Rate | Count | Denominator | Notes |
| --- | --- | --- | --- |
| `missing_percent` (column) | `missing.count` | `value_slots` | Missing under `values.missing`: absent, null, empty, blank and markers by default. |
| `missing_percent` (dataset summary) | sum of `missing.count` | `cell_count`, the sum of the `value_slots` of the columns | N x C for a CSV. |
| `type_error_percent` | `technical_type.outside_count` | `values.count` | The typed population: missing values are not in it. `null` when the column is `mixed`. |
| `trim_percent` | `changed` of the `trim` stage | `value_slots` | `changed` counts `content` strings only, over every slot, so empty and null cells lower the rate: it understates the share among content strings. Kept as it is. |
| `collapse_internal_whitespace_percent` | `changed` of `collapse_whitespace` | `value_slots` | Same remark; `changed` is counted after the trim stage. |

Their meaning and units are a contract: a change needs a new name or a
declared revision. `tests/scan/test_contract_scan_json.py` (A03) pins them.

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
| `max_stored_value_length` | 1,000 characters | 1,000,000 | Longer values are counted but not stored: the first one releases the raw table, and table-based measures of that field become limited with reason `value_too_long`. A small sample of them keeps a preview and a digest (18.6). |
| `max_listed_frequencies` | 100 | 100,000 | Output truncation only. |
| `max_samples` | 10,000 (100 before lot 1a), as the size K of the sample, section 18.2 | 100,000 (10,000 before lot 1a) | Output size only. |
| `max_long_samples` | 100 (0 keeps none) | 10,000 | Size of the sample of long texts per field (18.6); the memory budget can grant less. |
| `long_preview_chars` | 200 | 1,000,000 | Characters of a long text kept as a preview; never above `max_stored_value_length`. |
| `max_sample_memory` | 512 MiB | 1 TiB | Bytes, by the cost model of 18.10, that the samples of the whole scan may reserve; a sample is cut to fit, with reason `memory_budget`. |
| `max_variant_groups` | 100 | 100,000 | Output truncation only. |
| `max_variants_per_group` | 20 | 10,000 | Output truncation only. |
| `max_evidence_examples` | 10 | 1,000 | Detector evidence size only. |
| `max_tracked_records` | 2,000,000 per scan | 500,000,000 | Duplicate digests stop being stored (about 80 bytes each); later records are still compared; duplicate counts of datasets with untracked records become limited with reason `record_budget`; warning `record_budget`. |
| `max_listed_records` | 10 | 10,000 | Output truncation of the record listings only. |

- Defaults are starting values, not validated budgets. Phase 6 revisits them
  with measurements. In the Scan and JSON work, `max_distinct_per_field`
  keeps its default and `max_samples` is the size K of the sample, default
  10,000 since lot 1a (O28, section 18.2).
- Degradation is one measure at a time; counters, normalization change counts,
  numeric and string statistics and detector coverage continue after a table is
  released (ET08).
- Hard caps are the protected core configuration: a user value above a cap is
  rejected before the scan starts (CA13).
- `max_distinct_per_field` must not exceed `max_tracked_values`, and an
  explicit `max_samples` must not exceed `max_distinct_per_field`. A
  `max_samples` that is not set takes the lower of its default and
  `max_distinct_per_field`; the document records the value in force, and so
  does `config_sha256`.
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
- Configured patterns are detectors and are not the patterns inferred from the
  samples (18.12), which are written apart in `derived.patterns`.
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

   Batches are also bounded by size (lot 2c): a CSV batch of rows closes when
   it has read `readers.csv_reader.BATCH_BYTES` (8 MiB) of the source, checked
   every 16 rows, and the streaming batch of a field closes when the heavy
   values it holds (more than `values.HEAVY_LENGTH`, 256 characters) reach
   `values.PENDING_CHARS` (8 Mi characters). Without it one batch of large
   cells would take rows times columns times the cell size. A record is never
   split: the working memory of a scan is at least that of its largest record
   (MEM-05). No result depends on where a batch ends.
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
| Pattern inference exception (18.12) | `derived.patterns` entry `failed` on that field, `pattern_inference_failed` error, other analyses continue | Same |
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
      "max_samples": 10000, "max_long_samples": 100, "long_preview_chars": 200,
      "max_sample_memory": 536870912, "max_variant_groups": 100,
      "max_variants_per_group": 20, "max_evidence_examples": 10,
      "max_tracked_records": 2000000, "max_listed_records": 10
    },
    "records": {
      "preview": 10, "duplicates": true,
      "sample": {"rows": 1000, "edge": 50, "cell_chars": 200, "max_bytes": 16777216}
    },
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
    "pattern_inference": {"enabled": true, "max_patterns": 8,
                          "max_value_length": 64, "min_distinct": 2},
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
- One file serves every command: one object per tool (`scan`, `report`) and,
  at the top level, the `csv` settings of `sample`. The scan does not inherit
  the top-level `csv` settings.
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
  "format_version": "0.2.0",
  "format_revision": 1,
  "engine": {"version": "0.6.1", "normalization_version": 1,
             "detectors": {"number": 1, "date": 1, "boolean": 1,
                           "enumeration": 1, "email": 1, "url": 1,
                           "phone": 1, "postal_code": 1, "currency": 1,
                           "percentage": 1, "quantity": 1, "uuid": 1,
                           "ip_address": 1}},
  "status": "complete",
  "run": {"started_at": "2026-10-06T12:00:00Z", "duration_seconds": 0.012,
          "timings": {"reading": 0.004, "analysis": 0.006, "finalize": 0.002,
                      "derived": 0.0, "other": 0.0},
          "workers": 1, "peak_memory_bytes": 52428800},
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

- `run` holds what varies between runs on the same source (O33): the
  `timings` (reading, analysis, finalize, derived analyses of 18.12 and
  other) add up to `duration_seconds`; `workers` is the number of processes
  that analyzed values; `peak_memory_bytes` is that of the main process, null
  when the platform does not report it; `counters` (lot 2c, 18.4) is written only
  when asked for. It is not part of the description of the data, so two scans
  of one source differ by it alone.
- `source.csv` is `{"delimiter": ",", "header": [...]}` for CSV sources and
  `null` otherwise; `source.size_bytes` is the number of bytes read and hashed.
- `scope.collections` describes JSON collection selection and is `null` for
  CSV sources, which have no collections to select.
- A `limited` envelope omits `lower_bound` when no bound is proven.
- Diagnostic `locations` list only the keys that apply: `{record, line}` for
  CSV, `{record, element}` for JSON.

The format follows the repository convention: `format_version` names the
experimental compatibility family and `format_revision` increases for each
meaningful change. Its
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
  included, comes from `scan`. The `report` object keeps the presentation
  settings (`string_analysis`, `value_examples`; since lot 1c of the Scan and
  JSON work, they were at the top level before) and the top level `csv` serves
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
| 2026-10-06 | SJ-0 | Principles 1 and 7; decisions O22 (amended) and O26 to O33; section 9.11 (rates); section 16.1 (`run`); sections 18 to 21. | Scan and JSON work, lot 0: the contract and its tests before the code. Proposed until the maintainer accepts the baselines. |
| 2026-10-07 | SJ-0 | Section 19.4b: settings by tool, new Report setting `value_examples.kept_per_column` (default 100). | Keeps the Scan sample size K and the Report sample size apart in the configuration; keeps the examples of the Report unchanged. |
| 2026-10-07 | SJ-1a | Sections 9.1, 11, 15, 18.2, 18.9, new 19.7: qualified `values.cardinality` (`domain`, `accuracy`, `identity_accuracy`, `upper_bound`, records of the limit), K = `max_samples` at 10,000 with cap 100,000 and the K and T rule, reserved `bottom_k` members, JSON Schema and validator; the Report works on at most 100 sample values. | Lot 1a of the Scan and JSON work. Dedicated cardinality models keep the other envelopes unchanged (maintainer decision of 2026-10-07). |
| 2026-10-07 | SJ-1b | Sections 9.1, 19.1 to 19.7: `values.samples` has `kept` and `of`; the Report is a `tabalyst.report` document (revision 2) with the base at its paths, the `report` block (`generated_at`, `generator`, `processing_seconds`, `config`, `base_scan`, `datasets`), reduced samples declared, the loader `load_document` and `load_base`, `facts_sha256`, the Report JSON Schema. | Scan and JSON work, lot 1b: Report as a superset of the Scan and the common loader. |
| 2026-10-07 | SJ-1c | Sections 15, 19.3, 19.4, 19.4b: the `report` object of the configuration (`string_analysis`, `value_examples` moved from the top level), `report.value_examples.kept_per_column` (1 to 1,000, default 100) replaces `REPORT_SAMPLE_SIZE`, the pages read the base through `tabalyst.report_views` (`ColumnView` with the canonical `field`, `DatasetView`), `ScanFieldDetails` removed. | Scan and JSON work, lot 1c: projections and templates of the Report from the base. Maintainer decision of 2026-10-07 on the `report` object. |
| 2026-10-07 | SJ-0 | O28 amended and section 18.2: T and K are separate (`max_distinct_per_field` unchanged, `max_samples` becomes K); `BottomKSampler.from_exact` (18.3). | Lot 0 baselines: T = 10,000 saves memory, not time, and costs exact measures that a first pass alone never gets back. Maintainer decision. |
| 2026-10-07 | SJ-2a | Sections 18.3 and 18.8: `scanner/bottomk.py` (BLAKE2b 128 bits, `HASH_VERSION` 1, `update`, `retained`, `k`), the location of the sampler state (`ValueProcessor`, in the scan process or the worker of the field), the refusal measures. | Lot 2a of the Scan and JSON work: the sampler isolated from the product and the measured hash choice. |
| 2026-10-07 | SJ-2b | Sections 9.1, 18.2, 18.3, 18.9, 19.4, 21: the bottom-k in the engine (`scanner/valuesample.py`); `values.samples` of original values, `all` or `bottom_k` (`uniform_distinct` and `first_seen` removed), entries with `id`, `count_accuracy`, `identity_accuracy`, `k`, `hash`, `threshold`; `values.cardinality.estimate` (KMV, held within the certain bounds); exposure after the calculation with `kept < of`; the Report ranks an `all` sample by priority; `random_seed` in [0, 2**64). | Lot 2b of the Scan and JSON work. Maintainer decisions of 2026-10-07 (defaults accepted): `id` is the position in the Scan listing, `kept < of` declares withheld originals, the estimate is clamped with the raw value kept, the seed is bounded. |
| 2026-10-08 | SJ-2c | Sections 9.1, 11, 13, 16.1, 18.4, 18.6, 18.9, new 18.10: long texts sampled apart (`values.samples.long_texts`, `LongTextSampler`, digest identity `fingerprint_based`), the estimate adds the values and the long texts (`estimate.parts`), settings `max_long_samples`, `long_preview_chars` and `max_sample_memory`, the memory budget of the samples in bytes with requested and effective sizes (`requested_k`, `reason`) and the warning `sample_budget`, batches bounded by size, optional `run.counters`. | Lot 2c of the Scan and JSON work. Defaults of the plan accepted by the maintainer on 2026-10-08 (`selection` describes the listed values only, estimate in two parts, budget in bytes with no floor); the session chose 512 MiB instead of 256 so that a realistic 34-column scan is never cut, and added a fair share per field to first come first served. |
| 2026-10-08 | SJ-3a | Sections 18.1, 18.4, 18.7, 18.9, 18.10: samples by length (`values.samples.by_length`, `LengthStrataSampler`, `OtherLengths`), pool of values shared with the sample by `id`, `partial` accuracy, settings `max_samples_per_length` and `max_length_strata`, the sub-budget of an eighth, counters `strata_fields`, `strata_limited_fields` and `length_model_bytes`, priorities shared between the sample and its strata. | Lot 3a of the Scan and JSON work. Defaults of the plan accepted by the maintainer on 2026-10-08 (disposition `by_length` with shared ids and a pool, static reservation with `drop` as an API only, strata only for a `bottom_k` sample, every stored type, 100 values and 64 lengths, an eighth of the budget, Report without members). |
| 2026-10-08 | SJ-2c | Section 16.3: scan and report documents are written compact by default; the top-level `output.json_indent` setting indents them with each sample entry on one line (`json_text.dump_json`). `executions.json` and the Inspect file stay indented. | Weight of the Scan (24.9 MB indented, 10.4 MB compact, 13.5 MB indented with one line per entry on `insurance-ontario`); arrays `[value, count]` refused to keep the format self-describing. Maintainer decision of 2026-10-08. |
| 2026-10-08 | SJ-3b | Sections 9.10, 15 and new 18.11: the row sample (`records.sample`, `RowSampler`, `RowPriority`), first rows, a bottom-k of the interior by a priority of the position and last rows, cells of the same row for every projected field, settings `records.sample` (`rows`, `edge`, `cell_chars`, `max_bytes`), the byte budget, the Report keeping the header only. | Lot 3b of the Scan and JSON work: ROW-01 to ROW-11 and C01 to C06. |
| 2026-10-08 | SJ-4a | New section 18.12 and notes in 12.7, 18.6, 21, 15, 16.1: pattern inference from the samples (`scanner/patterninfer.py`), `derived.patterns` in the base model (`ScanResult.derived`, carried by the Report, left out of `facts_sha256`), grammar version 1, candidates with exclusive classification and overlaps, settings `scan.pattern_inference`, `run.timings.derived`, validator and schema, a `failed` entry per field with the `pattern_inference_failed` error. | Lot 4a of the Scan and JSON work: D08, PAT-01 to PAT-06, C07 to C10. Defaults of the plan accepted by the maintainer on 2026-10-08 (placement in `derived`, active by default, no pattern for exposed fields, no row sample estimate, quoted literals in the rendering, literal after 5 values). |

## 18. Bottom-k samplers (O26, O28)

### 18.1 Named approximations (O26)

Principle 1 admits an estimate when it is named. An estimate carries
`accuracy: "estimated"`, its `method` and its `parameters`, and never the
status `complete`. Accuracy values: `exact`, `estimated`, `fingerprint_based`
(equality of a digest, not of the full value), `partial` (a count that covers
only the occurrences from a recorded point on, 18.7) and `unknown`. Two approximations
are planned: the KMV estimate of a cardinality (18.5) and quantiles rebuilt
from histogram bins (second pass). Everything the Scan already measures stays
exact for its population.

### 18.2 Tracking limit and sample size (O28)

T, the number of distinct original values tracked exactly, and K, the size of
the bottom-k sample, are two settings of `scan.limits` (the base configuration,
`ScanConfig` in `scanner/config.py`, with their hard caps in `HARD_CAPS`):

| Setting | Meaning | Default |
| --- | --- | --- |
| `max_distinct_per_field` (T) | Distinct values kept in the exact table | 100,000 (unchanged) |
| `max_samples` (K) | Size of the sample the Scan keeps, in its output (the bottom-k sample from lot 2b) | 10,000 since lot 1a (100 before); hard cap 100,000 |

`max_samples` is the existing parameter, evolved rather than doubled by a new
one: it was the size of the sample in the output and it still is. K cannot
exceed T (configuration error, as `max_distinct_per_field` cannot exceed
`max_tracked_values`). The default K is a starting value: lot 1a measures the
weight of the Scan with K entries per column (estimated at 6 to 7 MB for the
reference file, against 1.3 MB today) and the quality of pattern inference,
and may lower it; a KMV error of about 3% already serves planning at
K = 1,000.

Up to T distinct values the table is exact, as today, and no existing exact
measure changes. The first value beyond T proves overflow
(`lower_bound = T + 1`): the K best entries of the T + 1 seen are kept with
their exact counts (all of them were tracked from their first occurrence), and
the bottom-k continues on every later occurrence. A table that stays under T
keeps its sample as `all`, or reduced to its K best when it holds more than K.

Lot 1a delivers the setting: the default is 10,000, the cap is 100,000, an
explicit K above T is a configuration error, and a K that is not set follows a
lower T (a scan that lowers T alone keeps working, with K = T). Lot 2b draws the
sample with the bottom-k (18.3). The Report does not read K: it works on at
most 100 values of the sample (`value_examples.kept_per_column`, 19.4b), the
whole sample when it has no more, otherwise the 100 of smallest priority, so
its examples do not depend on K (a `bottom_k` sample gives its first 100
entries, an `all` sample is ranked by the Report with the same hash and seed).
Reading the whole sample made the Report quadratic: 0.6 s for 3,000 rows at
K = 100, 25 s at K = 1,000. `random_seed` is the seed of the hash: an unsigned
64-bit integer.

The first version of this decision (O28, 2026-10-06) set T = K = 10,000. The
baseline of lot 0 showed that it saves memory (715 to 536 MB on the reference
file) and no time, while it makes columns of 10,000 to 100,000 distinct values,
and the identifiers of every file of fewer than 100,000 rows, lose their exact
cardinality, complete frequencies and exact median until a second pass that
`tabalyst scan` never starts by itself. The maintainer therefore kept T and
separated it from K, on 2026-10-07. Lowering T remains possible if the global
memory budget (lot 2c) requires it, with a recorded reason.

### 18.3 Module `tabalyst.scanner.bottomk` (lot 2a)

The selection mechanism is isolated from the product metadata (specification
section 7). A key is `(native type, canonical original text)` (section 21), so
the string `"123"` and the integer `123` stay distinct.

| Name | Contract |
| --- | --- |
| `HASH_ALGORITHM`, `HASH_VERSION`, `HASH_BITS` | `"blake2b"`, 1 and 128: the priority function, its version and its width (18.8). |
| `priority(key, *, seed=0) -> int` | Stable priority in `[0, 2**128)`, from the full key and the seed (an integer in `[0, 2**64)`, else `ValueError`); never the builtin `hash()`. |
| `BottomKSampler(k, *, seed=0, priority=None)` | `priority` replaces the function in tests (injected collisions). `k` and `seed` are attributes. |
| `BottomKSampler.from_exact(k, counts, *, seed=0, priority=None, overflow_at_occurrence=None)` | The sample of an exact table of `counts` (key to exact count) that holds more than K keys: the K best, with their counts. The engine uses it at the overflow of its table of T keys (18.2); the result equals streaming the same keys. |
| `BottomKSampler.from_exact_strings(k, texts, counts, *, seed=0)` | `from_exact` for keys of the type `"string"` given as texts: the same sample, hashing in a tight loop and keeping only the K best (the engine's release of a table of strings, lot 2b). |
| `.add(key, count=1)` | One or `count` occurrences; `count` below 1 is a `ValueError`. |
| `.update(keys, counts)` | A batch of distinct keys with their counts (the engine's hot path: its batches of 4,096 distinct values, section 13), equivalent to adding the occurrences one by one in any order. Counts are not checked. |
| `.update_strings(texts, counts)` | `update` for keys of the type `"string"` given as texts (the engine's hot path, lot 2b): once the sample is full, a text whose priority is above the limit is rejected before any key is built or looked up. Same result as `update`; with an injected priority it defers to `update`. |
| `.entries()` | `Entry(key, priority, count)` ordered by `(priority, key)` ascending. |
| `.occurrences` | Occurrences added. |
| `.retained` | Keys in the sample (at most K). There is no `__len__`: an empty sampler must not be falsy. |
| `.distinct_exact` | True while no overflow happened and no entry was dropped. |
| `.overflow_at_occurrence` | 1-based occurrence number of the first occurrence of the (K + 1)th distinct key, else `None`. |
| `.threshold` | Largest priority of the sample once it is full after an overflow, else `None`. |
| `.reduce(k)` | Keeps the smaller priorities; a larger `k` raises `ValueError`; entries dropped make `distinct_exact` false. |
| `.kmv()` | `KmvEstimate` or `None` (18.5). |

Rules (BK-01 to BK-07, tests B01 to B06 and B09):

- The priority depends only on the key and the seed. Equal priorities are
  ordered by the complete key, ascending. Distinct keys are never merged.
- Every distinct key is kept, with its count, until K is exceeded. The first
  overflow keeps the K best of the K + 1 keys, with their counts.
- An occurrence of a retained key increments its count. An unretained key
  enters only if its priority is below the threshold, and then replaces the
  worst entry.
- The threshold never increases. A key that left never comes back, so a key of
  the final sample was admitted at its first occurrence and never left: its
  count is the exact count of the whole stream.
- The sample is a function of the set of distinct keys, not of their order
  (B03), of the seed and of K.
- K can shrink to the smaller priorities; it cannot grow, because values
  rejected earlier are lost (B09).

Implementation (lot 2a). The sampler does not keep a heap: it admits a key
whose rank `(priority, key)` is below the limit of the last compaction, and
compacts (sort, cut to K, new limit) when the first overflow is reached (K + 1
keys) and then every half of K admissions. A key of the final sample is below
every intermediate limit, so it is admitted at its first occurrence and never
lost; the public members settle to exactly K keys first. The limit compares the
complete key on equal priorities, which a heap of integers could not do. Memory
at K = 10,000 is about 5.3 MB per field (550 bytes per entry, with the keys
and the compaction slack).

Where the state lives (confirmed at lot 2a, built at lot 2b). The sample of a
field belongs to the field's `ValueProcessor` (`scanner/valuesample.py`,
`ValueSample`), the object that already receives the released table
(`release`) and then the streaming batches (`process`) of distinct values with
their counts: in the scan process of a one-process scan, in the worker of the
field in a parallel scan (section 13, item 7). The engine's `ValueTracker` keeps
only the exact table of at most T keys, so the scan process gets no new
per-value work. A `ValueSample` keeps a plain dictionary of original keys with
their counts, in first-seen order, and no hash, while the field has at most K
distinct values; the first batch that exceeds K hands that dictionary to
`BottomKSampler.from_exact`, and every later batch goes to `update`. A complete
table of more than K keys is handed to `from_exact` at finalization. Keys of
`str` are paired with the type `"string"` by `zip(repeat("string"), keys)`,
without a conversion loop. The sample reaches the scan process inside the
field's value block, as plain data like the rest. No merge between processes
is needed. A merge would nevertheless be
exact: a key of the global K best is among the K best of each partition that
holds it and was never dropped there, so its partial counts sum to the total
(useful for reading one source with several processes, section 13).

### 18.4 Counters

Counts of retained keys are exact (`count_accuracy: "exact"`) when the key
identity is exact. They are not a top-N and not a frequency table: the most
frequent value can be absent. Proportions among sampled distinct values are
not proportions of rows.

Work counters (PERF-02 and PERF-03, lot 2c). `BottomKSampler.counters` gives
the priorities computed (`hashed`), the keys that entered the sample
(`admitted`), the occurrences of keys it already held (`hits`), the keys
computed and refused (`rejected`) and the keys that left it (`evicted`):
`hashed = admitted + hits + rejected` for `update_strings`, and `hits` are not
hashed in `update`. They only move in branches that do work (admission, hit,
compaction), never per rejected key, so they cost nothing on the hot path and
are always kept. The long text sampler adds `hashed_texts` and `hashed_bytes`.
`scan(..., counters=True)` (`tabalyst scan --counters`) writes their sum over
the fields in `run.counters.sampling`, with the sizes granted (`k_effective_min`,
`k_effective_max`, `reduced_fields`, `strata_fields`, `strata_limited_fields`) and the bytes
reserved in the cost model (`sample_model_bytes`, `long_model_bytes`,
`length_model_bytes`); without the request the member is
absent. A counter that the scan did not measure is not written, never 0: bytes
hashed are known for the long texts only, and the peak memory is
`run.peak_memory_bytes` (null when the platform does not report it). Counters
belong to `run`: they are not facts and do not enter `facts_sha256`.

### 18.5 KMV estimate (lot 2a)

After an overflow, with `K > 2` and a valid sample, `KmvEstimate` gives
`estimate = (K - 1) / theta`, where `theta = threshold / 2**128`;
`relative_standard_error = 1 / sqrt(K - 2)`; `k`; `theta_hex` (the threshold
as 32 hexadecimal digits, since a 128-bit integer is not a safe JSON number).
`kmv_estimate(threshold=..., k=...)` raises `ValueError` for `k < 3`, a
threshold of 0 or one at or above `2**128`; `BottomKSampler.kmv()` returns
`None` instead for a threshold outside that range, which only injected
priorities produce. No estimate is made while the domain is exact. The estimate serves planning; it is not a count of
duplicates or a proof of uniqueness. Certain bounds (`lower_bound`,
`upper_bound`) stay separate from the statistical interval, and an estimate
may be published with a version clamped to them, with the raw value kept.
Test B13 controls the error distribution over several datasets and seeds, with
a tolerant fixed-seed check, never a bound per seed.

### 18.6 Long texts (lot 2c)

A value longer than `limits.max_stored_value_length` (1,000 characters of its
canonical text) is never stored. It is counted, measured and tested like any
value, and sampled apart.

`tabalyst.scanner.longtext.LongTextSampler(k, *, preview_chars, seed=0)` keeps
a small bottom-k of long texts (`limits.max_long_samples`, 100 by default; LONG-01
rules out thousands of descriptions). The text is read once: its digest is
`digest_of(native_type, text)`, BLAKE2b with a 128-bit digest of
`native type NUL text` in UTF-8 (lone surrogates kept), independent of the seed,
and the priority is that of the key `("digest", hexadecimal digest)` through the
sampler of 18.3, so the sample, its counts, its threshold and its KMV estimate
come from the same code. An entry stores `digest`, `type`, `preview` (the first
`preview_chars` code points, so valid UTF-8; `long_preview_chars`, 200 by
default, never above `max_stored_value_length`), `truncated`,
`original_length_chars`, `original_length_bytes`, `count` and
`identity_accuracy: "fingerprint_based"`: two texts are the same entry when their
128-bit digests are equal. Two texts with the same prefix are two entries (B07,
B08). The preview and the lengths of an entry are built when it is admitted;
a text that is not admitted costs one read. Memory is bounded by K entries
(`LONG_ENTRY_BYTES` plus the preview). A preview does not certify the pattern or
alphabet of the whole text (LONG-05): a pattern inference must not read it as
the value; the pattern inference of 18.12 excludes the long texts.

In the scan a field with long values has `values.samples.long_texts`
(absent otherwise): `{selection, k, requested_k?, preview_chars, occurrences,
kept, of, digest: {algorithm, bits}, hash?, threshold?, listed}`.
`occurrences` counts every occurrence of a long value, exactly (LONG-03: the
minimum, maximum, total and mean lengths are in `string_lengths`). `selection`
is `all` until a text was dropped, then `bottom_k` with `hash` and `threshold`.
Entries are `{id, digest, type, preview, truncated, original_length_chars,
original_length_bytes, count, count_accuracy, identity_accuracy}`. A field with
`max_long_samples` 0, or whose size the memory budget cut to 0, still counts the
occurrences and lists none (`k` 0), and then has no cardinality estimate. A
sensitive field lists none (`kept` 0): a preview and a digest are the value, and
its threshold is withheld like the one of the values.

The cardinality estimate of such a field adds two disjoint domains, the stored
values and the long texts (the split is by length of the original text): each
is exact while its sampler dropped nothing and a KMV estimate otherwise, and
`estimate.parts` gives them (`{domain, accuracy, value, relative_standard_error,
k?, theta_hex?}`). The estimate is their sum, its relative error is
`sqrt(sum((value_i * error_i)^2)) / sum(value_i)` and, with `parts`, `k` and
`theta_hex` belong to the parts. It exists once either domain dropped a key.
The certain bounds of 9.1 still clamp it.

### 18.7 Length strata (lot 3a, D07, LEN-01 to LEN-06)

`tabalyst.scanner.lengthsample.LengthStrataSampler(per_length_k, max_lengths)`
keeps a bottom-k per tracked length, with a bounded number of lengths. The
length of a key is the number of characters (code points) of its original text
(21): the engine's `string_lengths` stays the analytical histogram.

| Name | Contract |
| --- | --- |
| `.update_strings(texts, counts, priorities)`, `.update(keys, counts, priorities)` | A batch of distinct keys with their counts and priorities, which the caller computed once for the global sample (the hash is not computed twice). |
| `.from_exact_strings(...)`, `.from_exact(...)` | The strata of an exact table, equal to streaming the same keys; used when the global sample becomes a `bottom_k`, at which point the table holds every value with its exact count. |
| `.add(key, count=1)` | One key, for tests. |
| `.strata()` | `{length: Stratum}` in ascending length. A `Stratum` has `entries()`, `occurrences`, `retained`, `distinct_exact`, `threshold`, `count_accuracy` and `tracking_started_at_occurrence`. |
| `.other` | `OtherLengths`: `lengths` (distinct untracked lengths now) and `occurrences`. |
| `.limited` | True when `other.occurrences` is above 0. |
| `.drop(length)` | Gives a stratum up: its occurrences move to `other`. |

A length is tracked from its first occurrence while a place is free (first met,
first tracked: LEN-04 and the "fixed quota from admission" of the specification);
others are summed in `other` and `limited` is true (B11). Strata and `other` add
up to every occurrence the sampler received, also after a `drop`. A stratum is a
`BottomKSampler` of `per_length_k` keys with the priority of the global sample, so
the argument of 18.3 holds: a key retained was admitted at its first occurrence
and its count is exact (`count_accuracy: "exact"`). `drop(length)` is the hook
of the memory budget; a dropped length that returns, or a length of `other` that
meets a free place, is admitted late: its stratum has `count_accuracy:
"partial"` and `tracking_started_at_occurrence` after its first occurrence, and
no frequency of it is announced as exact (B12, LEN-05). Occurrences are numbered
from 1 in the order the sampler receives them (the keys of a batch in the order
of the batch).

Where it lives (`scanner/valuesample.py`). Strata exist for a field whose
sample is `bottom_k`, not for an `all` sample, which lists every value and so
every length: they start at the switch, seeded from the exact table
(`from_exact*`), then every batch gives them the priorities it computed for the
global sample (`bottomk.string_priorities`, `priorities`; `update_strings`,
`update_ranked` and `from_exact*` accept them). Per key the strata add a `len`,
one dictionary lookup and one comparison against the admission limit of the
stratum (`BottomKSampler.admission_limit`); only the keys that can enter are
handed to a stratum. The values longer than `max_stored_value_length` are not in
the strata: they have `long_texts` (18.6), with their own lengths. As the global
sample, the strata are in the `ValueProcessor` of the field (the worker of the
field in a parallel scan), and no merge is needed.

Mutualisation (LEN-02). A value of a stratum that is in the global sample is
one entry: the stratum lists its `id`. Only the others are in
`by_length.listed`, with ids that continue the numbering (18.9). The two
samplers do hold their own keys in memory (the text is shared, the tuple and the
counters are not): the saving is in the document.

Combining (LEN-06). The strata and the global sample have different selection
laws; a consumer must not add them to estimate a proportion. A stratum gives
the exact `occurrences` of its length and a bottom-k of its values; the
global sample gives the values by global priority.

### 18.8 Hash choice and refusal threshold

Decided at lot 2a from the measures of `benchmarks/bottomk_hash.py`
([benchmarks.md](benchmarks.md)): **BLAKE2b with a 128-bit digest**
(`HASH_ALGORITHM = "blake2b"`, `HASH_VERSION = 1`, `HASH_BITS = 128`). The
message is the 8-byte little-endian seed, then the type, a NUL character and
the text in UTF-8 (lone surrogates kept, `surrogatepass`); the seed is
absorbed once and the state copied for each key. It is the fastest function of
the 128-bit candidates (0.3 to 0.45 microseconds per key, encoding included;
SHA-256, SHA-1 and MD5 take 0.6 to 0.9, SHAKE-128 0.9 to 1.0) and BLAKE2s is no
faster. The 64-bit CRC-32 pairs, about 20% cheaper, are refused: 64 bits is
below the contract, and a linear checksum is not a hash whose independence
across seeds the estimate can rely on. No third-party library (xxHash, MurmurHash)
is added for a gain of about 0.2 microseconds per key. The KMV error on
sequential identifiers is within the model for every 128-bit candidate (12
seeds), so quality does not separate them.

The version is part of the output (`values.samples.hash`, 18.9). Changing the
function, the seed encoding or the key encoding raises `HASH_VERSION`; a golden
test (`tests/scan/test_bottomk.py`) pins the priorities of fixed keys.

Refusal rule: a candidate is refused when the first pass of the realistic dataset
regresses by more than 20% against the baseline of the same session, or the
worst-width dataset (30 columns including 5 unique identifiers) by more than
35%. The prototype of lot 2b (a patched `ValueProcessor`, throwaway) costs
3.4% on the combined file, 5.3% on the worst-width file and 3.4% on
`insurance-ontario` in the default parallel mode, where the workers hash. In one
process (`workers=1`, not the default) it costs 25%, 47% and 36%: the sampler
and the key conversion of the prototype, not the hash, which is about 0.35 of the
1.7 microseconds per key measured there. Lot 2b must bring the one-process cost down
(no conversion of keys, no intermediate table) and measure it again; the
parallel figures are its reference. Two levers are noted for it: a table of at
most K distinct keys needs no priority in the Scan (its sample is `all`; the
Report can hash its few kept values), and only a field whose sample must be cut
(a table above K, a released table) pays the hash.

### 18.9 Output (cardinality settled at lot 1a, samples and estimate at lot 2b)

`values.cardinality` is described in 9.1. The strata of lengths (18.7) are
`values.samples.by_length` (below).

`values.samples` also carries `requested_k` and `reason` when the memory budget
(18.10) granted a size K smaller than `limits.max_samples`: `k` is the size in
force, `requested_k` the one asked for and `reason` is `memory_budget`. They are
written only for a `bottom_k` sample that is smaller than asked (an `all`
sample, which holds every value, was not cut); `k` 0 means no value is sampled
(`kept` and `of` are 0) and the cardinality has no estimate. The `estimate`
uses the size in force (`k`). `long_texts` (18.6) is the member of the values
that are too long to be stored.

`values.samples` (lot 2b):

- `selection` is `all` when the sample holds every distinct original value
  (none was dropped or excluded): `listed` is in first-seen order, there is no
  hash and no `k`. Otherwise it is `bottom_k`: `listed` holds the sample (at
  most K entries, K being `limits.max_samples`) in ascending `(priority, key)`
  order, and the block names `k`, `hash` (`algorithm`, `version`, `bits`,
  `seed`) and, once a key was dropped, the `threshold` (32 hexadecimal digits).
- An entry is `{id, value, type, count, count_accuracy, identity_accuracy}`:
  `id` is the position of the entry in the `listed` of the Scan (kept by a
  Report that keeps a subset; the pool of lengths, below, continues the
  numbering), `value` the original text, `count_accuracy` and
  `identity_accuracy` `exact` (`partial` for a late stratum, `fingerprint_based`
  for the long texts).
- Exposure applies after the calculation on originals (21). `mask` merges the
  entries with the same mask in the order of the listing, counts added; `hide`
  lists none. `of` is always the number of originals sampled and `kept` the
  number listed, so exposure that withholds values shows as `kept < of`, which
  is the capability a planner reads (`complete_samples`) to refuse the sample
  (VAL-06). The `threshold` of a sensitive field (mode `mask` or `hide`) is not
  written: it is the priority of one of its values.

`values.samples.by_length` (lot 3a, 18.7), written for a `bottom_k` sample when
`limits.max_samples_per_length` and `limits.max_length_strata` are above 0 (and
absent for an `all` sample, whatever the lengths):

```
by_length: {
  domain: "original", unit: "characters",
  per_length_k, max_lengths, requested_max_lengths?, reason?,
  limited, tracked,
  strata: [{length, selection: "all" | "bottom_k", kept, of, occurrences,
            count_accuracy, tracking_started_at_occurrence?, threshold?, ids}],
  other?: {lengths, occurrences},
  listed: [entry]              # ids continue those of samples.listed
}
```

- A stratum lists `ids` of entries of `samples.listed` or of `by_length.listed`
  (the pool: values of a stratum that the global sample does not hold). Every id
  of a stratum exists, appears once, and names a value whose text has the length
  of the stratum (checked by `check_scan`). The pool starts at `len(samples.listed)`.
  `of` is the number of values the stratum sampled (at most `per_length_k`), `kept`
  the number listed. `occurrences` is the exact number of occurrences of the
  length since its tracking started. `tracking_started_at_occurrence` is written
  for a `partial` stratum only (an exact one began at the first occurrence).
  `threshold` is as in the sample: present once the stratum dropped a value, not
  for a sensitive field.
- `other` is written when `limited` and gives the untracked lengths and the
  occurrences counted into `other`; strata and `other` add up to the stored
  values of the field (`values.count` less the long texts). `limited` is
  also true when `max_lengths` is 0.
- Exposure: a sensitive field (mode `mask` or `hide`) keeps `length`, `of` and
  `occurrences` of its strata and lists nothing (`kept` 0, `ids` empty, no
  `threshold`, empty pool), the same capability declaration as the sample.
- Report: its base keeps the strata without their members (`kept` 0, no pool):
  the ids would point at values the Report does not hold (19.4). `facts_sha256`
  leaves the members out like the sample's.
- Memory budget: `max_lengths` is the number in force (18.10) and
  `requested_max_lengths` with `reason: memory_budget` the one asked for,
  written only for a field that has more lengths than the budget granted.

`values.cardinality.estimate` is written for a `limited` count when a sampler
dropped a key and every value reached a sample (a value that fits no sample,
because the memory budget granted a size of 0, would leave the estimator without
the whole field): `{accuracy: "estimated", method: "kmv", value,
unclamped_value?, relative_standard_error, k, theta_hex?}`. `value` is the
estimator held within `[lower_bound, upper_bound]`; `unclamped_value` is the
raw `(k - 1) / theta`, present only when a bound changed it; `theta_hex` is
absent for a sensitive field. A field with long texts has `parts` instead of
`k` and `theta_hex` (18.6). A complete count has no estimate: it is exact.

### 18.10 Memory budget of the samples (lot 2c, MEM-01 to MEM-06)

`limits.max_tracked_values` stays the budget, in values, of the exact tables
(section 11). The samples have their own budget in bytes,
`limits.max_sample_memory` (512 MiB by default), because K entries per field is
5 MB per field at K = 10,000 and a source of a thousand columns would take
gigabytes. It is a cost model, not a measurement: `memory.sample_entry_bytes`
(600 bytes of structure, which includes the slack held between two compactions,
measured at 540 bytes at K = 10,000, plus two bytes per character of the mean
stored value) and `memory.long_entry_bytes` (700 bytes plus four per preview
character). A test checks the model against `tracemalloc`.

`memory.SampleBudget` has three sub-budgets: the long texts take an eighth, the
samples by length another eighth (18.7), the samples of values the rest (MEM-01: keys, payloads, structure and compaction
slack of the samplers; the tables, the parser and the pending batches have their
own limits, 13). Sizes are reserved before the sample is built (MEM-04), in the
scan process only, in the order the source is read, so they do not depend on the
workers (principle 6):

- A released table reserves K entries for its field when it is released
  (`ValueTracker._grants`), at the record where the limit was proven, and the
  size travels to the field's processor in the `release` message.
- A complete table reserves its distinct values (at most K) in field order
  before any worker starts (`ValueTracker.reserve`, called by `ScanEngine.finalize`
  for every field).
- Long texts reserve their sample when the first long value of the field is met:
  at the release if it holds one, otherwise when the streaming batch that holds
  it is handed over (`long_k` travels with the batch). First come, first served.
- A field never takes more than the whole sample budget divided by the fields
  discovered so far: one wide source cuts every column alike instead of the
  late ones first. The size granted is `min(K, room / cost)`, 0 when not even
  one entry fits (MEM-06: the sampling of that field stops in a controlled way,
  the scan goes on, and the counters, lengths and exact tables are not touched).

The requested and the effective sizes are both in the document (MEM-03):
`values.samples.k` and `requested_k`, `values.samples.long_texts.k` and
`requested_k`, with `reason` `memory_budget` and the warning `sample_budget`
(one per scan, with the number of fields cut). Consequences are read from the
block: a cut sample is a `bottom_k`, its KMV estimate has the error of the size
in force, and a sample of size 0 has no estimate. No limit is ever lifted by a
request for an exact result (MEM-06); the exact tables are bounded by T and by
`max_tracked_values`, and lowering T stays the other way to spend less.

The samples by length (18.7) have their own sub-budget, an eighth of
`limits.max_sample_memory` (`memory.LENGTH_SHARE`), so the samples of values
keep three quarters. A field that becomes a `bottom_k` reserves the cost of a
full stratum (`per_length_k` entries) for each of the `limits.max_length_strata`
lengths it may track, at the same places as K: a released table in
`ValueTracker._grants`, a complete table of more than K values in `reserve`
(it reserves its distinct values at most), and a table that fits its sample
reserves nothing. The grant is a number of lengths, `min(requested, share /
cost of a stratum)`, travelling with the sample's in the `release` and `table`
messages, so it is the same for 1 or several workers. The sampler's `drop` is
the hook for a budget that must take a stratum back; the engine does not call it
(a scan tracks every length from its first occurrence, and a grant of fewer
lengths sums the others in `other`), so a scan writes `exact` strata today.

Bounded states (MEM-02): the number of samples (K), their length
(`max_stored_value_length`, `long_preview_chars`), the long texts (`max_long_samples`) and the
batches (13) each have a bound. The lengths, patterns and error categories of
later lots will join this table. The warm-up values of a streamed field are
bounded by `detection.warmup_values` and by the stored length. A giant record
(MEM-05) cannot be split: the working memory of the parser is the largest record
(and, for CSV, the cells of a batch of at most 8 MiB).

### 18.11 Row sample (lot 3b, D12, ROW-01 to ROW-11)

Each dataset keeps a small sample of whole rows, taken in the one pass: the
first `edge` records, a bottom-k of the interior and the last `edge` records,
with the cells of every projected field of the same row (ROW-06). It is the
common storage of the Report (the rows to show) and of the analyses of later lots
(relations between fields, which need values of the same record). Names (ROW-01):
S = `records.sample.rows` (1,000), E = `records.sample.edge` (50) and the middle
M = S - 2E (900). K is the size of the sample of distinct values and does not
appear here.

`tabalyst.scanner.rowsample.RowSampler` lives in `RecordFacts`, so in the scan
process: the workers only receive the work per value. It has two entries, one
per reader item: `add_batch(start, rows)` for the CSV batches of strings (lot 6
of the engine, section 13) and `add_record(record)` for any other `Record`.
Both give the same rows (a test compares them, and random batch sizes); only
`bytes` differs, since a record costs more in the model than a row of strings.

- **Positions.** The position of a row is the index of its record, which counts
  the records a tolerant scan excluded (they have no row and leave gaps). `start`
  is the first `edge` records read, in reading order, not the records numbered
  1 to `edge`.
- **End and middle (ROW-03, ROW-04).** The records after the start wait in a
  buffer of the latest `edge`. A record that leaves the buffer is a candidate of
  the middle; the buffer at the end is the end. The two groups are disjoint, and
  no record of the start enters the buffer. Only candidates that leave the buffer
  can enter the middle, so the last `edge` records never do, even when their
  priority is the smallest (C03). The population of the middle is the positions
  `edge` + 1 to N - `edge`, `population.interior` of them, and the block says
  `population.scope: "interior_rows"` (ROW-07). The rows of the middle are not a
  uniform sample of the whole dataset (ROW-08): `RowSample.interior()` returns
  them alone, and an estimate over the whole population would need weights
  (not delivered).
- **Small datasets.** With N < 2E the end window overlaps the start: a record is
  stored once, with `origins: ["start", "end"]`. With N at most S every record is
  a row (`complete: true`): the interior fits in the middle. With N = 0 the
  sample has no row.
- **Priority (ROW-05).** `RowPriority(seed)`: the 64-bit priority of the
  position `i` is the number `i mod 8` of the eight little-endian 64-bit words of
  BLAKE2b with a 512-bit digest (personalization `tabalyst.rows.v1`) of the seed
  and the block `i // 8`. One hash call serves eight rows: 0.07 s per million
  rows against 0.28 s for a call per row (benchmarks.md, lot 3b). It never looks at
  the cells, so two identical rows are two observations with their own
  priorities (C02). `ROW_HASH_VERSION` is 1; the seed is `random_seed`. The ties
  of a 64-bit priority are broken by the position. The middle keeps the M
  smallest `(priority, position)` among the candidates: the same rows whatever the
  batches, the readers and the number of workers (principle 6).
- **Hot path.** The priorities of the candidates of a batch are computed together
  (`RowPriority.range`) and a batch is filtered once against the threshold of the
  middle; only the few rows that can enter are projected. The buffer holds
  references to the rows of the batch (to the `Record` for the record path), not
  copies, and a row is projected only when it is admitted, at the end for the
  buffer, and for the start. A reader that reused the observations of a record
  would break the record path: none does (a test reads JSON and JSONL).
- **Cells (ROW-06, ROW-09).** The cells of a record are its scalar observations as
  canonical text per path, as the preview has them: a list when the path repeats
  (items of an array), `null` for a JSON null, no key for a path absent from the
  record. The cells of one path share `cell_chars` characters (200): the text
  that passes it is cut on a code point, the following values of the path are
  dropped, and the row lists the field in `truncated` (counted in
  `truncated_cells`). A table row projects all its columns. `fields` lists the
  projected field ids (those with a scalar value); `fields_limited` says that
  untracked paths (`limits.max_fields`) are not.
- **Exposure (12.8).** At the end, like the preview: `mask` merges, `hide` writes
  a hidden cell as `null`; nulls and strings that are not content stay as read.
  The original values stay in memory until the end, as the preview's do.
- **Budget (ROW-10, ROW-11, MEM-01 to MEM-06).** `records.sample.max_bytes` (16 MiB)
  is the budget of the rows kept by all the datasets of a scan, in bytes of a cost
  model (`rowsample.TABLE_ROW_BYTES`, `TABLE_CELL_BYTES` and `RECORD_*`, between
  0.9 and 1.6 times the `tracemalloc` figure in a test) and first come, first served. It is a limit
  on bytes: S is not an authorization to exceed it. When it is exceeded the worst
  rows of the middle are given up one by one (the size in force `middle_k` can only
  shrink, as in B09), then the start stops growing (the first rows that fit stay),
  and the end is projected from the newest row back while it fits. The end is
  charged to the budget when the dataset is finalized, so with several datasets
  the order of their finalization (the order of the datasets) is part of the
  result: a later dataset read while the budget was half spent can leave the
  earlier one only what its own end needs. The document
  says `reason: "memory_budget"` as soon as anything was cut, with `requested`,
  `middle_k`, `bytes` and `max_bytes`. A cut middle still has its `threshold`
  and is the bottom-k of its size; the shrinking depends on the data and their
  order only, so it is the same with 1 or several workers. The largest memory of
  a scan is also bounded by the record in reading and by the CSV batch (13).
- **Output.** `records.sample` (absent when `records.sample.rows` is 0):

  ```json
  {"selection": "start_middle_end",
   "hash": {"algorithm": "blake2b", "version": 1, "bits": 64, "seed": 42},
   "requested": {"rows": 1000, "edge": 50, "middle": 900}, "middle_k": 900,
   "population": {"records": 3000, "interior": 2900, "scope": "interior_rows"},
   "complete": false, "threshold": "4e361452e3b67ee0",
   "fields": ["column_1", "column_2"], "fields_limited": false,
   "cell_chars": 200, "truncated_cells": 0, "bytes": 2477121,
   "max_bytes": 16777216, "kept": 1000, "of": 1000,
   "rows": [{"record": 1, "origins": ["start"],
             "values": {"column_1": ["a"], "column_2": ["1"]}}]}
  ```

  Rows are in source order within each group: the start (with the rows that are
  also the end), the middle, the end. `threshold` (16 hexadecimal digits) is the
  largest priority kept, written once a row of the interior was not kept.
- **Report (O27, 19.4).** The Report keeps the header and no row: `kept` 0,
  `rows` empty, the same facts otherwise. `facts_sha256` leaves out `rows` and
  `kept`; `complete_samples` is false for a base that dropped rows. The
  Report's own "Data sample" still reads `records.preview` (section 9.10); lot 5
  decides what it shows of the start, the middle and the end.
- **Consumers.** `RowSample.interior()` (the rows an exploration may treat as a
  sample, C04) and `RowSample.covers(field_ids)` (false when a field is not
  projected, or has a cut or hidden cell in a row: C06) are the seams of the
  planner of lot 6a and of the relations of lot 8a. `covers` is false for a sample
  that lists no row or fewer than it sampled, which is what a Report holds. A cell is the text, not the
  native type; lot 8a decides whether the type must be added.
- **Validation.** `check_scan` checks the hash identity (algorithm, version, bits
  and the seed of the configuration), the settings in force, the population, the
  groups and their order, the fields of the cells, the counts and the threshold
  (the largest priority of the middle rows, recomputed).

### 18.12 Pattern inference (lot 4a, D08, PAT-01 to PAT-06, C07 to C10)

After the scan, `tabalyst.scanner.patterninfer.infer_patterns(datasets, settings)`
infers the structural patterns of each text field from its samples. It reads
the finished datasets, never the source (PAT-01), and `scan()` calls it once
after `finalize`; the result is `ScanResult.derived.patterns` and its time is
`run.timings.derived`. The inferred patterns are not the configured ones
(12.7): those stay detectors (`pattern:<id>`) in `field.detectors`.
`scan.pattern_inference.enabled` set to false leaves `derived` out.

**Population.** The stored distinct original values of the field: the `listed`
of `values.samples` and the pool of `by_length.listed` (once each, by `id`),
in id order, at most `MAX_VALUES` (20,000; `limits` then says `max_values`).
The two selection laws are not added (LEN-06): the population is a set of
distinct values, and its figures are counts of distinct values. Excluded, and
counted in `population.excluded`: the long texts (`long_text_occurrences`: the
preview of a long text never certifies the pattern of the whole text, LONG-05,
C10), values that are not strings, empty values, values longer than
`max_value_length` (64) and values of more than 32 tokens. A field is
`not_applicable` when its technical type is not `text` or `mixed`
(`technical_type`), when exposure masks or hides it (`exposure`: the Scan does
not give the originals back, 21), when its sample is withheld
(`samples_withheld`, `kept < of`), when it has only long texts
(`long_texts_only`), no usable value (`no_values`) or fewer than
`min_distinct` of them (`too_few_distinct`). Every field has an entry.

**Failure.** The inference of each field is isolated, as a detector is
(CA19): an exception on one field gives it a `failed` entry (`reason`
`inference_error`, `diagnostic` the index of a `pattern_inference_failed`
error naming the dataset and the field, with the exception type and never
its message, which could quote a value). The other fields, the other
analyses and the scan `status` are unaffected, and the scan that read the
whole source is not lost for a bug of this post-pass.

**Grammar, version 1 (PAT-03, PAT-04).** A value is cut into tokens: a run of
ASCII digits (`digit_ascii`), a run of ASCII capitals (`upper_ascii`), a run of
ASCII lowercase letters (`lower_ascii`), a run of letters that has a non-ASCII
letter (`letter_unicode`), and every other character, a `literal` (a run of the
same character is one token with a count). Spaces, signs and separators are
always literals; non-ASCII digits are literals. Two generalizations exist,
`letter_unicode` for any run of letters (level 1) and `alphanumeric` for a run
of letters and digits (level 2). Adjacent class tokens never share a
character, so a signature has one reading of a value and matching it is one
pass (`matches`): no regular expression is generated and nothing backtracks.
A change of a class, a rule or the rendering raises `GRAMMAR_VERSION`, in
`derived.patterns.grammar`.

**Candidates (PAT-02, PAT-05).** Values are grouped by structure (the tokens
without their lengths). A group is one candidate; each token carries the
`min` and `max` of its length (characters, or repetitions of a literal), and a
letter or digit token that is the same text in every value of a group of at
least `LITERAL_MIN_SUPPORT` (5) values becomes a `literal`: `XX9999'A'` is a
fixed final `A`, `XX9999X` any capital (C08). With more groups than
`max_patterns` (8), the groups beyond the first `max_patterns - 1` are
generalized, level 1 then level 2, until the groups of at least `min_distinct`
(2) values fit; a generalized group whose structure equals a kept one joins it.
`merged_structures` counts the structures a candidate stands for and
`generalization` its level; the candidates are ranked by values, then
signature, the first is `principal`. Groups below `min_distinct` and the groups
beyond `max_patterns` are `other` (distinct values and number of structures),
and `limits` says `max_patterns` when the bound or the ladder acted.

**Exclusive classification (PAT-08, C09).** A value counts for one candidate:
the most specific one that reads it, by literal letters and digits (more), the
generalization level (lower), the width of the repeats (narrower), then the
rank. Candidates with a `letter_unicode` or `alphanumeric` token may read
values of other structures; `overlaps` lists the sets of candidates that read
the same distinct values, with their number, and the counts of the candidates
and of `other` add up to `population.distinct`. This is the discovery
classification on the population: the validation on the whole file is the
second pass (lot 7c) and is not here.

**Output.** `derived.patterns`: `{grammar: {name: "tabalyst.pattern", version},
domain: "original", fields: [...]}`, one entry per field in the order of the
datasets and fields. A `complete` entry has `dataset`, `field`, `population`
(`source`, `selection`, `complete`, `available`, `distinct`, `excluded`),
`candidates`, `other`, `overlaps` and `limits`. A candidate has `id` (`p1`,
`p2`, ...), `role`, `signature` (tokens `{kind, text?, min, max}`), `render`,
`lengths` (observed, characters), `generalization`, `merged_structures`,
`coverage` (`distinct`, `share` to four decimals, `basis`), `confidence`
(`laplace_share`: `share * n / (n + 1)`, a heuristic and not a probability) and
`examples` (up to three ids of entries of the field's samples, the smallest).
The `render` writes `9` a digit, `X` a capital, `x` a lowercase letter, `@` any
letter, `#` a letter or a digit, with `{n}` or `{min,max}` for repeats of more
than six characters or of variable length, and quotes the literal letters,
digits, spaces and the characters `'{}@#` (`XX9999'A'`), so that a literal
letter is never read as a class (PAT-03); the signature is the reference.
`coverage.basis` is `all_distinct` when the population is every distinct value
of the field (`population.complete`: the sample is `all` and nothing was
excluded or cut) and `sample` otherwise: a discovery indicator on
distinct values, never a frequency of the file. The estimate on the row sample
and the validated coverage are not written yet (lots 7c and 8b).

`derived` is part of the base model (a Scan with it reads back) and not of
its facts: `facts_sha256` leaves it out, a Report carries it as it is (19.3)
because its base keeps fewer values and cannot compute it, and `check_scan`
checks it: one entry per field, the render of each signature, the sums, the
shares, the overlaps and, when the samples are complete, that every example
exists and matches its signature.

## 19. Scan and Report as one document family (O27, O29, O30)

### 19.1 Identity

`tabalyst.scan` is the base document. `tabalyst.report` is a superset: the
base at the same paths (`engine`, `status`, `run`, `source`, `config`,
`config_sha256`, `scope`, `datasets`, `diagnostics`), plus a `report` block
and, later, `analyses` (second-pass results). The Report profile of
revision 1 had no `format` field; the document of revision 2 identifies itself
with `format: "tabalyst.report"` and has its own `format_revision` (2), with a
reference to the revision of its base in `report.base_scan` (19.5). The root
holds the base at its own paths, so `format` and `format_revision` are the only
members of the root whose value is the Report's and not the base's.

### 19.2 Common loader

`tabalyst.scan_document.load_document(path_or_dict) -> LoadedDocument` reads a
Scan or a Report (lot 1b) and returns its `kind`, the `base` (a `ScanResult`),
the `report` block of a Report and the `capabilities` (`complete_samples`);
`load_base()` returns the base alone. The `report` block and the namespaces
`derived`, `observations` and `analyses` are not part of the base. The
loader checks `format_version` and the revision like `scan_reuse` (a document
of another revision is refused with a request to run again, never converted;
for a Report, its own revision and that of its `base_scan`), and that the base
matches the identity the Report declares (`source_sha256`, `config_sha256`,
`facts_sha256`). `require_complete_samples(purpose)` is what a planner calls:
it refuses a document whose samples are not complete (19.4). Extracting the base
of a Report gives the same model and the same facts as the Scan it was built
from, without rounding, filtering or renaming, except the reduced samples
(A02, A11). A Report is not an input of `tabalyst report --scan`: that command
reads scan documents only and says so.

### 19.3 The `report` block

It holds the generation date (`generated_at`), the generator (`name`,
`version`), `processing_seconds`, the presentation configuration (`report.config`:
`string_analysis` and `value_examples`; `config` stays the Scan configuration),
`base_scan` (19.5) and the projections `report.datasets`, one per dataset
shown, identified by the dataset `id`, with columns identified by the field `id`.
No statistic is stored twice: the copies `scan_details`, `numeric`,
`string_profile` and `date_profile` of the columns are removed and the pages
read the base (A04). Since lot 1c the pages read it through the views of
`tabalyst.report_views`, computed when a page is rendered and never stored:
`ColumnView` is the column projection plus its canonical `field` (the Scan
field, read as the Scan wrote it: the column page reads presence, first and last
values, categories, lengths, numeric, boolean and temporal facts from it) and the
three figures the pages derive (`numeric`, `date_profile`, `string_profile`:
percentages, length classes, examples by length). `DatasetView` is the dataset
projection with `ColumnView` columns. The other projections (`summary`,
`issues`, `preview`, `limits`, `structure`, the normalization and detector
blocks of a column) are unchanged and stored.
The Python model is `ReportProfile` (the document): `profile.datasets` are the
scan datasets and `profile.report.datasets` the projections.

### 19.4 Reduced samples (O27)

A Report keeps fewer sample values than its base: by default the 100 smallest
priorities of each field (`value_examples.kept_per_column`, 19.4b), an exact and deterministic subset of the Scan's, with
the same exact counters. It declares `kept` and `of` in each `values.samples` (a Scan has them equal:
`of` is the size of the sample the Scan listed, `kept` the number listed here,
`selection` still the Scan's). Lot 1b keeps what the Report already used
(`report_sample`: up to `kept_per_column` values, 100 by default; since lot 2b
the first ones of a `bottom_k` sample, and for an `all` sample the ones of
smallest priority, computed with the scan's hash and seed, so that a Report is
an exact subset of what a bottom-k of that size would keep); lot 1c made it the
setting of 19.4b. The capabilities of the loader say whether the
samples are complete (`kept == of` everywhere); a planner refuses a document
whose samples are not, so a Report is never an input to replan. The invariants
of `check_scan` apply to a reduced base: `kept` is the length of the listing and
at most `of`, `of` at most `max_samples`, and the sum of the counts of an `all`
sample equals `values.count` only when nothing was dropped. The
computation (planner, second pass, patterns) reads the Scan, in memory or from
the cache. A Report can be sent alone and rendered without the source (A10).

### 19.4b Settings by tool

One configuration file serves every command (section 15): the `scan` object
holds what Scan measures and keeps, the `report` object holds what Report
presents, and the top-level `csv` settings serve `tabalyst sample`.
Names are never reused across the two, so a number is read for one tool only:

| Setting | Where | Tool | Meaning | Default |
| --- | --- | --- | --- | --- |
| `scan.limits.max_distinct_per_field` (T) | `scan` | Scan, and Report through the scan it runs | Distinct values kept in the exact table | 100,000 |
| `scan.limits.max_samples` (K) | `scan` | Scan | Size of the bottom-k sample kept in the Scan document | 10,000 |
| `report.value_examples.kept_per_column` | `report` | Report | Sample values kept per column in the Report document: the smallest priorities of the K of the base, so an exact subset (19.4); at most K, and a Report built from a Scan with a smaller K keeps all of it and declares `kept` and `of` | 100 |
| `report.value_examples.*_result_size`, `inline_display_size`, `full_distribution_max_distinct` | `report` | Report | What the HTML shows and how examples are chosen | unchanged |

`report.value_examples.kept_per_column` (1 to 1,000) replaces the role that `max_samples` had for
the Report (the candidate pool of its examples, `candidate_sample_size` before
`max_samples`): 100 is the former default of `max_samples`, so the examples of a
Report do not move when K becomes 10,000. It is presentation: changing it never
invalidates a Scan document or starts a scan (A14), whereas a change of
`scan.limits.*` changes `config_sha256`. The Report document records the Scan
configuration in `config` and the presentation in `report.config` (19.3), which
has the shape of the `report` object of the file. The upper bound of 1,000 is
the cost of the Report: choosing diverse examples compares the candidates
pairwise: measured at lot 1c on the 34 columns and 3,000 rows of the insurance
demo, a report from a scan takes 1.2 s at 100, 3.3 s at 300 and 28 s at 1,000. Other presentation settings of
the old top level (`string_analysis`, `value_examples`) are refused with their
new place, like the settings that moved to `scan`. The Python `ReportConfig`
stays flat (presentation settings then `scan`): only the file has a `report`
object. `docs/en/reference/configuration.md` has the table of these settings by
tool.

### 19.5 Identity of the base

`report.base_scan` identifies the base a Report stands on: `format`,
`format_version` and `format_revision` of the Scan base, `engine_version`,
`source_sha256`, `config_sha256` (the existing scan identity) and
`facts_sha256`, the SHA-256 of the canonical JSON of the base without `run` and
without `listed` and `kept` of each sample, so a change of presentation or of
sample size does not change it. A Report and the Scan it comes from have the
same `facts_sha256` (`scan_document.facts_sha256`). The Scan2 document (lot 7a)
will carry the same block at its root.

### 19.6 Format revisions (O30)

The revision in progress is not published (release 0.6.2 published revision 1
of the Scan and of the Report; the Scan is at revision 2 and the Report at
revision 2 since lot 1b, which changed the structure of the Report). The work changes it in place; each
lot updates `docs/en/scan/format-changelog.md` and the Report changelog; the
revision increases once, when the release is made. No adapter reads older
documents.

### 19.7 Schema and validation of the base (lot 1a)

The JSON Schema of the base document is generated from the result models
(`tabalyst.scanner.schema.scan_schema()`) and committed as
`src/tabalyst/schemas/tabalyst.scan.schema.json`; a test fails when the file is
out of date (`python scripts/scan_schema.py` rewrites it). It describes what a
reader accepts (validation mode: models that omit unknown members cannot be
described in serialization mode), requires the constants of the format, pins
the revision and declares the namespaces `derived`, `observations`, `analyses`
and `report` of the extensions with an open schema, so that `additionalProperties:
false` does not stop a reader of the base from recognizing a Report; the schema
of the Report validates their content. Lot 1b adds it:
`tabalyst.report_schema.report_schema()`, committed as
`src/tabalyst/schemas/tabalyst.report.schema.json` and guarded like the other
(`python scripts/scan_schema.py` writes both). It requires the `report` block
and keeps `derived`, `observations` and `analyses` open. The base of a Report,
with the `format` and `format_revision` of its `base_scan`, satisfies the Scan
schema; the Report schema fixes the Report's own `format_revision` (2).

`tabalyst.scanner.validation.check_scan(result)` returns the violated
invariants between fields, which a schema cannot express: presence and native
types adding up, string categories, `values.count`, missing components, bounds
and records of the cardinality, listings against `values.count` and
`max_samples`, histogram and numeric sums, detector coverage, scope and source
shape against the datasets, and `config_sha256` against `config`. A scan the
engine produced has none. The private project storage (`projects/`) runs it
when it validates a generation and consumes the Scan base only, never a Report
(lot 1d).

## 20. Second pass and the rule of costly operations (O31)

### 20.1 Commands

| Command | Behavior |
| --- | --- |
| `tabalyst scan` | First pass only. Never automatic. |
| `tabalyst scan --deep` | Forces the second pass. With a valid Scan in the cache (source, configuration, engine), one pass; otherwise the first pass, then the second if the planner keeps analyses: at most two passes. Writes `<stem>.deep.json`. |
| `tabalyst scan --plan` | Shows the plan without running it. |
| `tabalyst report` | The planner decides whether a second pass has a benefit and a low cost, and what it holds. It names what it added or left out, and why. |
| `tabalyst report --deep` | Forces the second pass. |

The Python API is `tabalyst.scan(..., deep=True)`; it never prompts.
`deep.mode` (`auto`, `off`, `force`) is a configuration setting for scripts
and CI, with no command-line option to skip the second pass.

### 20.2 Deterministic budgets

Automatic selection uses deterministic quantities: memory in bytes, cells to
process and number of columns, never measured time, so the same file gives the
same plan on any machine. Estimated time only feeds messages. Thresholds are
calibrated at lot 6b on the baselines and recorded here.

### 20.3 Confirmation

Forcing an operation whose estimate passes the thresholds (several minutes, or
memory beyond the budget) shows the estimate and asks before starting; a batch
asks once, with the total. Outside an interactive terminal nothing is asked:
the command stops with an exit code and a message unless `--yes` is given.
`--force` keeps its meaning (overwrite an output). The API returns the plan
with `requires_confirmation` and the estimate, and executes only with an
explicit parameter.

### 20.4 Second-pass document

`<stem>.deep.json` is separate and written atomically; the Scan is not
rewritten. It carries the identity of its base (19.5), the plan, the execution
and the analyses, each with its own envelope. A change of source, schema or
configuration invalidates it (A09). A Report embeds what it needs under
`analyses`.

## 21. Original value domain (O32)

Bottom-k, patterns and smart sampling rest on original values, decoded but
before NFC, trim, whitespace collapse, casefold and accent removal: `00123`,
`123` and ` 123 ` are three values. The detectors, the frequency listings, the
lengths and the statistics keep the analytical value of section 10, and every
block names its domain (`original` or the versioned normalization pipeline), so
two populations are never confused (`telephone`: the original cardinality and
the diversity of the exposed shapes are different things).

Exposure applies after the calculation (12.8). A masked or hidden sample cannot
give back the originals to a process outside the scan; the document declares
that capability as missing (`kept < of`, 18.9), and the second pass reads the
source when it needs them. Since lot 2b `values.samples` and the KMV estimate
are in this domain: the table keys are raw decoded values, a string keeps its
text, other native types their canonical text. `frequencies`, lengths and
statistics keep the analytical value. Structural patterns could be computed before exposure and kept without
keeping the value; the inference of 18.12 does not do it: it reads the samples
of the finished scan, so a field that exposure masks or hides has no inferred
pattern (`not_applicable`, reason `exposure`).
