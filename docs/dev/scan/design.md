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
| O12 | Reuse and staleness | Identity fields exist from phase 1; the reuse rule is settled in lot 5c. | Deferred to 5c | 16.2 |
| O13 | Configuration merge | Objects merge, lists replace, unknown keys fail. | Accepted 2026-09-26 | 15 |
| O14 | Detector catalogue | Each detector gets a short specification in `detectors.md` before it is implemented. | Deferred to 3b | 12 |
| O15 | Empty inputs | Zero counts and `not_applicable` measures; never a division by zero. | Accepted 2026-09-26 | 9.9 |
| O16 | Report | Settled in phase 5. | Deferred to 5a | - |
| O17 | Output writing | Atomic temporary file plus replace; `--force` for existing outputs. | Accepted 2026-09-26 | 16.3 |
| O18 | Migration | See A3. | Accepted | - |
| O19 | Performance targets | Baseline recorded in `benchmarks.md`; targets decided in phase 6. | Deferred to 6 | 13 |
| O20 | Costly exact measures, external storage | Out of the first phases; exact medians only when derivable. | Deferred to 7 | 9.4 |
| O21 | Dynamic plugins | Internal registry only; no external loading. | Deferred to 7 | 12.1 |
| O22 | Approximations | Outside the contract. Any approximation requires a new explicit decision. | Accepted (specification) | 8 |

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

`scan(source, *, config=None, registry=None, on_progress=None)` reads one
source and returns a finalized `ScanResult`. It writes nothing. `registry`
replaces the default detector registry (section 12.1). Phase 4 adds file output,
batches and the top-level alias `tabalyst.scan`.

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

Explicit mode: `json.collections` lists absolute paths, which may cross arrays
(`$.customers[].orders[]` gathers every order into one dataset). Only the
selected collections are analyzed; the rest of the document is outside the
requested scope, which the result states (EF05). Overlapping selections are
rejected in the first implementation.

The JSON reader tracks its own path stack. It must not use `ijson` prefix
strings as identities, because they join keys with dots and would merge `a.b`
with `a` > `b` (specification scenario 4).

At most two passes over a JSON source are allowed; the target is one.

## 6. Reader to engine contract (D04, D05, ET01, ET02)

Readers are synchronous iterators. They yield three kinds of items:

```python
@dataclass(frozen=True, slots=True)
class DatasetOpened:
    dataset: str                 # "rows", "$", "$[]", "$.customers[]"
    kind: Literal["table", "document", "collection"]
    collection_path: FieldPath | None
    fields: tuple[DeclaredField, ...] = ()   # known before any record

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
@dataclass(frozen=True, slots=True)
class Observation:
    path: FieldPath              # relative to the record root
    type: NativeType             # null, boolean, integer, number, string, object, array
    value: object                # str, int, Decimal, bool or None; array length for arrays
```

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
  record; a JSON location is the record index and the element index in its
  array.
- A reader raises `InputError` for fatal problems (section 14). Readers
  receive the configuration and apply the error policy themselves: under
  `strict` they raise a format-specific `InputError`; under `tolerant` they
  yield `RecordExcluded`, whose `code` and `message` become the diagnostic, so
  the engine never tests the source format.
- Declared fields are registered before any record, in order, so a CSV with
  only a header still lists its columns, with the header names and labels
  that only the reader knows. Other fields are discovered from observations.
- Records are materialized one at a time. `limits.max_record_observations`
  protects against a single huge record.

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
  (EF10, CA05). Canonical text is the source text for JSON numbers and
  `true`/`false` for booleans.
- `values.cardinality`: envelope, exact raw distinct count.
- `values.frequencies`: envelope whose value is `{distinct, listed, truncated}`.
  `listed` holds the `limits.max_listed_frequencies` most frequent analytical
  values as `{value, type, count}`, ordered by count then value. Output
  truncation is not a limitation of the measure: `truncated` says the listing is
  shorter than `distinct`.
- `values.samples`: up to `limits.max_samples` distinct analytical values, with
  `selection` set to `all` (every distinct value), `uniform_distinct` (seeded
  uniform sample of the complete table) or `first_seen` (first distinct values,
  used when the table is limited), listed as `{value, type, count}`. Samples
  are examples, not statistics.
- `values.first` and `values.last`: `{value, type, record}` for the first and
  last analytical values (EF21).
- Shares and confidences are rounded to four decimals; counts are never
  rounded.

### 9.2 String characteristics (lot 2a)

Over `content` strings, on raw values: `non_ascii`, `with_line_breaks`,
`with_control_characters`, `with_surrounding_whitespace`,
`with_repeated_whitespace`, `uppercase`, `lowercase`, `mixed_case`,
`no_letters`. Plain counters.

### 9.3 String lengths (lot 2a)

Envelope over analytical `content` strings, in code points: `count`,
`min_length`, `max_length`, `mean_length`, `median_length` and
`length_histogram` (`[{length, count}]`). The length histogram is always small
and independent of the frequency table, so string lengths and their median stay
exact when the table is limited.

### 9.4 Numbers (lot 2a, extended in 3a) (EF15, O05)

Population: native `integer` and `number` values, plus strings that the number
interpretation accepts without ambiguity. Until lot 3a that interpretation is
the current strict rule (optional sign, digits, optional dot decimal, optional
exponent, no leading zeros for integers); from lot 3a it is the number detector
with its configured conventions.

Envelope value: `count`, `native_count`, `text_count`, `min`, `max`, `sum`,
`mean`, `population_variance`, `population_std`, `positive`, `negative`, `zero`,
`integral_decimals` (decimal representations with an integral value, such as
`1.0`) and `median` (nested envelope).

- Integers accumulate as Python `int`; decimals as `Decimal` in a high-precision
  context with the `Inexact` trap. If an operation would round, the envelope
  becomes `limited` with reason `precision`.
- Variance uses the complete population (divide by `n`), from exact sums.
- Output: integral results are JSON integers; other results are float64.
- `median` is exact when derived from a complete frequency table, otherwise
  `limited` with reason `frequency_table_limited`. Other quantiles are
  deferred (EF22, O20).
- Values that are not finite in text (`NaN`, `inf`) are not numbers.

### 9.5 Booleans (lot 2a)

Native booleans: counts of `true` and `false`. Textual booleans become an
interpretation in lot 3a.

### 9.6 Temporal values (lot 3a) (EF16)

Produced by the date and time detector: per kind (`date`, `datetime_naive`,
`datetime_aware`, `time`), `count`, `min` and `max` as ISO strings, plus the
distribution by year when bounded. Naive and aware values are never compared.
Ambiguous values are excluded and counted (section 12.6).

### 9.7 Technical type (lot 3a)

A port of the current inference so the report keeps its meaning: candidate
families are tried in order `integer`, `number`, `date`, `boolean`, `text`, and
the first whose accepted share reaches `types.minimum_confidence` wins;
otherwise `mixed`; `empty` without values. Native JSON types count directly.
Output: `{type, confidence, counts, outside_count}`.

### 9.8 Normalization

See section 10.

### 9.9 Empty inputs (O15)

- A CSV with only a header gives a `rows` dataset with zero records and one
  field per column; counts are zero and value measures are
  `not_applicable` with reason `no_values`.
- An empty JSON array gives a dataset with zero records and no fields.
- A field without values gives `not_applicable` value measures.
- An empty file is fatal: a CSV needs a header, and an empty file is not JSON.
- Percentages are left to consumers; the scan publishes counts and
  denominators, so no division by zero can occur in the scan.

## 10. Normalization version 1 (D15, D16, EF33-EF38, O08)

Normalization applies to `content` strings only, never to the source. Stages
run in this order; each can be disabled:

| Stage | Definition | Default |
| --- | --- | --- |
| `nfc` | Unicode canonical composition (NFC). Compatibility forms (NFKC) are not applied. | on |
| `trim` | `str.strip()`: removes leading and trailing characters for which `str.isspace()` is true, including no-break spaces. | on |
| `collapse_whitespace` | Replaces every run of whitespace other than line breaks (`[^\S\r\n\v\f\x1c-\x1e\x85  ]+`) with one U+0020 space. | on |
| `casefold` | `str.casefold()`. | on |
| `strip_accents` | NFD, removal of combining marks (category `Mn`), then NFC. | on |

- The **analytical value** is the output of the enabled `nfc`, `trim` and
  `collapse_whitespace` stages. Frequencies listings, samples, lengths,
  detectors and statistics use it.
- The **comparison key** is the output of every enabled stage. It groups
  variants.
- Per stage, the result lists `{stage, enabled, changed, cardinality}`:
  `changed` counts occurrences modified by that stage given the previous
  stage's output; `cardinality` is the distinct count after the stage. A
  disabled stage has `changed` and `cardinality` set to `null` and influences
  nothing (CA16). The first entry is `raw`, with `changed` set to `null` and
  the raw cardinality.
- `changed` counters are exact streaming counters: they continue when tables
  are limited (ET09, CA17).
- `variant_groups`: envelope listing comparison keys with at least two distinct
  raw variants, as `{key, count, variants: [{value, count}]}`, bounded by
  `limits.max_variant_groups` and `limits.max_variants_per_group`.
- A group is an analytical equivalence under these rules, not proof of business
  identity.
- `normalization.version` is `1`. Any change to these definitions increments it.

## 11. Limits and degradation (ET05-ET11, O09)

| Setting | Default | Hard cap | Effect when reached |
| --- | --- | --- | --- |
| `max_fields` | 10,000 per dataset | 1,000,000 | New paths are not tracked; `structure.paths` becomes limited; observations counted in `structure.untracked_observations`; warning `field_limit`. |
| `max_depth` | 64 | 1,000 | Deeper content is not traversed; counted in `structure.depth_truncated_observations`; warning `depth_limit`. |
| `max_record_observations` | 100,000 | 100,000,000 | Record excluded (tolerant) or fatal (strict); `record_too_large`. |
| `max_distinct_per_field` | 100,000 | 50,000,000 | The raw table is released; cardinality, frequencies, variant groups and derived medians become limited with reason `distinct_limit`. |
| `max_tracked_values` | 2,000,000 per scan | 500,000,000 | Global budget: the largest table is released first (ties: most recently discovered field); reason `global_budget`; warning `global_budget`. |
| `max_stored_value_length` | 1,000 characters | 1,000,000 | Longer values are counted but not stored; table-based measures of that field become limited with reason `value_too_long`. |
| `max_listed_frequencies` | 100 | 100,000 | Output truncation only. |
| `max_samples` | 100 | 10,000 | Output size only. |
| `max_variant_groups` | 100 | 100,000 | Variant groups limited. |
| `max_variants_per_group` | 20 | 10,000 | Variants of a group limited. |
| `max_evidence_examples` | 10 | 1,000 | Detector evidence size only. |

- Defaults are starting values, not validated budgets. Phase 6 revisits them
  with measurements.
- Degradation is one measure at a time; counters, normalization change counts,
  numeric and string statistics and detector coverage continue after a table is
  released (ET08).
- Hard caps are the protected core configuration: a user value above a cap is
  rejected before the scan starts (CA13).
- `max_distinct_per_field` must not exceed `max_tracked_values`.
- `max_fields` and `structure.paths` count field paths other than the record
  root. The lower bound published when `max_fields` is reached is the number of
  distinct paths actually seen, at least `max_fields + 1`.

## 12. Detectors (EF24-EF32, D09, D14)

### 12.1 Contract

```python
class Detector:
    id: ClassVar[str]                     # "date", "email", "pattern:customer_number"
    version: ClassVar[int] = 1
    family: ClassVar[str]                 # "number", "temporal", "contact", ...
    accepts: ClassVar[frozenset[str]] = frozenset({"string"})   # native types
    sensitive: ClassVar[bool] = False

    def __init__(self, settings: Mapping[str, object]) -> None: ...
    def classify(self, value: str) -> Classification | None: ...
    def accumulator(self) -> DetectorAccumulator: ...
```

- `classify` is pure and deterministic: the same value always gives the same
  result. `None` means not matched. This makes memoization and per-distinct
  execution exact (section 13).
- `Classification` carries `state` (`matched`, `ambiguous`, `invalid`), an
  optional `format`, `candidates` for ambiguous values, an optional `reason`
  for invalid values and an optional parsed value for statistics. `invalid`
  means the value has the detector's shape but fails validation, such as
  `2026-02-30`.
- The accumulator receives `(value, classification, count)` and produces the
  detector result: formats, evidence and detector-specific statistics such as
  email domains.
- `DetectorRegistry` holds detector classes by `id`. `default_registry()`
  returns a fresh registry with the built-ins; `register(cls)` adds one.
  External plugin loading is deferred (O21).
- Configuration: `detectors.<id>` holds `enabled` and detector parameters
  (D14). Complex logic stays in code.

### 12.2 Coverage (EF26, CA11)

For each detector and field:

- `eligible`: analyzable values of an accepted native type.
- `tested = eligible - not_tested`
- `tested = matched + ambiguous + invalid + not_matched`
- `share_tested = matched / tested` and `share_eligible = matched / eligible`,
  both published with their denominators.

Detection is exhaustive by default, so `not_tested` is 0. It becomes non-zero
only for values longer than a detector's input cap, or later for adaptive
strategies, which must then publish the reason.

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
  "details": {}
}
```

A failed detector has `status: "failed"`, a `diagnostic` index and no
`coverage`: a failure is never reported as values that did not match (CA19).

### 12.4 Interpretations (EF24, EF27, CA12)

The technical type (9.7) and semantic interpretations are separate axes.
`interpretations.candidates` lists every detector whose `share_eligible`
reaches `detection.minimum_share` (default 0.95), ordered by matched count
then detector id. `interpretations.primary` is set only when exactly one
candidate qualifies. Overlaps are kept: `12345` may be an integer and a ZIP
code; both are listed (CA10).

### 12.5 Shape classifier (EF30)

Each value gets a cheap shape signature (digits as `9`, letters as `A` or `a`,
other characters kept, runs compressed). Detectors may declare the shapes they
can match so others are rejected without running their full logic. Rejection
by shape is an exact `not_matched`, not `not_tested`.

### 12.6 Ambiguity (O06, specification 12.1)

An ambiguous value, such as `01/02/2026` when both `DD/MM/YYYY` and
`MM/DD/YYYY` are allowed, stays ambiguous. The date detector publishes, in its
`details`:

```json
"ambiguity": {"count": 1, "candidates": [{"formats": ["DD/MM/YYYY", "MM/DD/YYYY"], "count": 1}],
              "evidence": {"DMY": 1, "MDY": 0}, "resolution": null}
```

- `evidence` counts unambiguous values per order in the same field. It is
  exposed, never applied: the current report resolves ambiguity from such
  evidence, and phase 5 decides how the report presents it.
- Only configuration resolves ambiguity (`detectors.date.ambiguous_order`),
  and then `resolution` is `{"order": "DMY", "source": "config"}` and resolved
  values count as matched.
- Ambiguous values never enter statistics that need one interpretation.

The same rule applies to numbers such as `1,234`, ambiguous between a US
thousands separator and a French decimal comma.

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
- Pattern identifiers must be unique and cannot collide with built-in ids.

### 12.8 Sensitive values and exposure (ET17, O10, CA20)

- A field is sensitive when a sensitive detector matched at least one of its
  values. This is deliberately conservative.
- `exposure.sensitive_values` is `mask` (default), `hide` or `show`.
- Every value-bearing block of a sensitive field (frequencies, samples, first
  and last values, variant groups, detector evidence) passes through one
  exposure gate at finalization. `mask` replaces each uppercase letter with
  `A`, lowercase letter with `a` and digit with `9`, keeps other characters and
  does not compress runs, then merges equal masks; `hide` removes the values
  and keeps counts. The effective configuration is not a value-bearing block.
- The field records `"sensitive": true` and the exposure applied.

### 12.9 Catalogue

The catalogue and its priorities come from the specification. Lot 3a ports the
current rules (numbers, dates, booleans, enumeration candidates); lot 3b starts
the priority 1 catalogue. Each detector gets a short entry in `detectors.md`
before implementation: accepted formats, normalization, validation level,
overlaps, sensitivity and test values (O14). Detectors check syntax, never
real-world existence (EF32).

## 13. Execution strategy and performance (EF30, EF31, ET12)

Every per-value computation (normalization stages, number parsing, detector
classification, shapes) is a pure function of the value. The engine exploits
this without changing results:

1. While a field's raw frequency table is complete, per-value work runs once
   per distinct value, weighted by its count, at finalization.
2. When the table is released, the engine first processes the stored distinct
   values with their counts, then switches the field to streaming mode: each
   new occurrence is processed immediately through a bounded memoization cache.
3. Both modes produce identical results. A contract test compares a scan with
   `max_distinct_per_field=1` and a scan with the default for every
   non-table measure.

The current engine is vectorized with pandas; a pure Python streaming engine
has a higher cost per cell. The per-distinct strategy is the main mitigation.
The baseline of the current engine is recorded in
[benchmarks.md](benchmarks.md); phase 6 sets targets (O19).

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
| Invalid JSON syntax | Fatal | Fatal |
| Record above `max_record_observations` | Fatal | Record excluded, `record_too_large` error, status `partial` |
| Structural limit (`max_fields`, `max_depth`) | Warning, scan continues | Same |
| Measure limit | Envelope status, plus one `measures_limited` warning listing fields | Same |
| Detector exception | Detector `failed` on that field, `detector_failed` error, other analyses continue | Same |

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
section of `tabalyst.json`; in phase 5 the report settings are restructured
around it.

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
    "detectors": {
      "date": {"enabled": true, "orders": ["YMD", "MDY", "DMY"],
               "separators": ["-", "/", "."], "ambiguous_order": null}
    },
    "patterns": [],
    "exposure": {"sensitive_values": "mask"},
    "random_seed": 42
  }
}
```

Layers, from lowest to highest priority: hard caps (never overridden, only
enforced), built-in defaults, optional profile (phase 7), configuration files
(`tabalyst.json` then `--config` files in order), command-line options.

Merge rules:

- Objects merge recursively, including `detectors.<id>`.
- Lists replace the previous list entirely (`null_markers`, `patterns`,
  `collections`).
- Unknown keys are errors.
- `null` is accepted only where the schema allows it and sets that value; there
  is no deletion syntax.

The result embeds the effective configuration and `config_sha256`, the SHA-256
of its canonical JSON (sorted keys, no whitespace, UTF-8) (EF42).

## 16. Result document (O01)

### 16.1 Top level

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "engine": {"version": "0.4.0", "normalization_version": 1,
             "detectors": {"date": 1}},
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
alpha family and `format_revision` increases for each meaningful change. It
gets its own changelog page when `tabalyst scan` is released.

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
      "sensitive": false
    }
  ]
}
```

Fields appear in order of discovery. Blocks introduced by later lots are
absent until their lot, then always present (with an envelope status when
they do not apply). For reuse (O12, lot 5c), the source block already carries
size, modification time and SHA-256, and the result carries `config_sha256`.

### 16.3 Output files (lot 4, O17)

`tabalyst scan data.json` writes `data.scan.json` beside the source. `-o` and
`-d` follow the other commands. Writing uses a temporary file in the target
directory and an atomic replace, so an interrupted scan never leaves a partial
result. Existing outputs require `--force`; an output can never replace an
input.

## 17. Changes to this document

| Date | Lot | Change | Reason |
| --- | --- | --- | --- |
| 2026-09-26 | 0 | Initial contract. | Phase 0. |
| 2026-09-26 | 0 | Gate 0: every Proposed decision accepted without change. | Maintainer validation. |
| 2026-09-26 | 1a | Section 6: `DatasetOpened.fields` (declared fields), `RecordExcluded.code` and `message`, readers apply the error policy. | A header-only CSV must list its columns, and the engine must not know CSV diagnostic codes. |
| 2026-09-26 | 1a | Section 16.1: `source.csv` content, `scope.collections` null for CSV, `lower_bound` omitted when unproven, location keys per format. | Details the example did not settle. |
