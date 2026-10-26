# Identifier uniqueness (Unique ID plan, lot 0)

Status: contract written at lot 0 of the Unique ID plan (`tabalyst-gb`,
`KANBAN/05-PROGRESS/2026-10-23-tabalyst-unique-id-plan.md`); implemented by lots 1 to 4; P0
finalized at lot 5 (sections 12 and 13). Lot 6 (P1) adds the Deep count of the copies of rows
(6.2, 6.6); lot 7 the Deep count of the distinct analytical values (6.1, 6.7); lot 8 the criteria of the planner, the cache and the versions (6.8, 12); lot 9 the near-unique reading (14); lot 10 the decomposition despite missing IDs (2.2, 6.9).
P2 is not delivered.
Requirements: `KANBAN/04-SRS/2026-10-23-unique-id/Tabalyst_Unique_ID_Cahier_des_Charges_v1.md`
(UID-001 to UID-010 are P0, UID-011 to UID-015 are P1 and P2 and out of this contract).
Decision record: ADR `2026-10-23-identifier-uniqueness-derived-in-report`. Tests:
`tests/report/test_identifier_uniqueness_*.py` (T01 to T34) and
`tests/scan/test_row_identity_equivalence.py` (A1).

## 1. What it is

A column the Scan classifies as `identifier/id` or `identifier/unique_id` can repeat its values
because whole rows are copied. A copy of a row repeats its ID without two distinct records
sharing it. The Report derives, per identifier column, a small object that separates:

- the **raw** uniqueness (all rows), which is the Scan's `unique_id` read again;
- the uniqueness **after row deduplication** (one occurrence of each distinct row);
- the repetitions **explained** by exact row copies and those left **residual** between distinct
  records.

Nothing here changes the Scan, its classification or `identifier.repetition` (which keeps its raw
meaning `P - D`, cahier 10.4). The object is derived from facts the Report already holds, plus an
optional Dedup report. It never reads the source and never runs Dedup.

## 2. Variables and formulas

For one identifier column of one dataset (exact integers, never floats):

| Symbol | Meaning | Taken from |
| --- | --- | --- |
| `N` | records of the dataset | `datasets[].record_count` |
| `P` | records where the ID is present | `field.values.count` |
| `M` | missing positions, `N - P` | `field.missing.count` (and `presence.absent`) |
| `D` | distinct **analytical** values, exact | `analytical_distinct(field)` or a usable Deep count (6.1) |
| `E` | extra copies of whole rows | 6.2 |
| `U` | distinct rows, `N - E` | derived |
| `R_raw` | `P - D` | derived |
| `R_residual` | repetitions among distinct rows, `U - D` | derived |

Valid only when `M = 0` and `N`, `D`, `E` are exact on the same scope:

```text
R_raw = N - D            R_explained = E            R_residual = R_raw - E = U - D
D_after_dedup = D        U = N - E
```

Invariants (a violation is `failed` with reason `inconsistent_measures`, never corrected):

```text
0 <= E <= N     0 <= D <= P     R_raw = R_explained + R_residual     0 <= R_residual <= R_raw
```

With `M = 0` a copied row repeats its ID, so `E > 0` implies `R_raw >= E`. A raw `unique_id`
(`D = N`) with `E > 0` is therefore impossible and is `failed` too (A6).

Why the formula holds: removing a copy of a row removes one occurrence of its ID and never the
last one, so the distinct IDs do not change. The distinct count is the same before and after.

### 2.1 Strict statuses

```text
raw.unique               = true   iff eligible, N >= 2, M = 0, D exact, D = N, scope complete
                           false  iff eligible, N >= 2, M = 0, D exact, D < N, scope complete
after.unique             = true   iff eligible, U >= 2, M = 0, D and E exact, U = D, scope complete
                           false  iff the same conditions with U > D
```

When `raw.unique` is true, `E = 0` follows (a copied row would repeat its ID, so `D < N`): the
object then states `E = 0` and `after_row_deduplication.unique = true` whatever the duplicate
evidence (none, disabled or limited), and a non-zero exact `E` is `failed` (A6, T28). So a raw
unique ID needs no duplicate count (T01).

`false` means a demonstrated repetition, never a missing measure: an unknown is `null`. The
threshold is `U >= 2` for any conclusion after deduplication (decision D4, T11). A dataset of
one distinct row repeated has `R_residual = 0` and yet no conclusion (example F).

With `M > 0` `E` mixes copies of rows that have an ID and copies of rows that have none, and neither
the Scan nor a Dedup report counts them apart: without the count of 2.2, nothing is subtracted and no
`unique` is emitted (cahier 5.4, T09, T10). The `raw` block is then all `null` as well.

### 2.2 Missing IDs (lot 10, cahier 5.4)

A copy of a row repeats the whole row, so its ID cell is absent or present as in the original: the
copies of the rows that have no ID (`E_missing`) are counted on those rows alone, and the rest of `E`
is the copies of rows that have an ID:

```text
E_present  = E - E_missing        U_present = P - E_present        R_residual = U_present - D
```

`E_missing` is the second-pass count of 6.9 (exact only). `E` is the exact total of 6.2 (any source).
Invariants (a violation is `failed` with `inconsistent_measures`):

```text
0 <= E_missing <= E        E_missing <= M - 1        E_present <= P - D
```

`E_missing <= M - 1` because a row without an ID that is copied leaves its first occurrence among the
distinct rows. That is also why no ID is ever strictly unique with `M > 0`, whatever `R_residual` is:
`after.unique` is `false` when `R_residual > 0` (a repetition among the rows that have an ID is
demonstrated) and `null` otherwise, never `true`; `raw.unique` is `false` when `D < P` and `null`
otherwise. The threshold is `U_present >= 2` for a conclusion (decision D4 applied to the rows that
have an ID). The status stays `limited` with the reason `missing_ids`: it is the definition of `limited`
(a threshold blocks the strict conclusion, exact figures are still given). The cahier's example E
(`,Alice` twice and `B-002,Bob`) has `E = 1`, `E_missing = 1`, `E_present = 0`, `U_present = 1`: no
conclusion. `near_unique` stays `null`.

## 3. Eligibility

The object exists for a column whose Report classification (`report_classification.refine`, so
the Scan's or the one the second pass refines) is `identifier/id` or `identifier/unique_id`, and
that is not under a JSON array. Anything else has `identifier_uniqueness: null` in its summary:
`not_applicable` stores nothing (D10). The rule never creates a role from uniqueness (T21 to T24)
and the classification is never modified (UID-001, UID-010).

## 4. Statuses, interpretations, reasons

`status` says how far the measures go; `interpretation` says what they conclude.

| `status` | Meaning |
| --- | --- |
| `complete` | every measure used is exact, comparable and verified, and a conclusion is drawn |
| `limited` | a measure exists but is partial (lower bound, estimate, partial scope), or a threshold blocks the conclusion; exact figures are still given |
| `not_assessed` | a needed measure is absent or disabled, or the rule did not run |
| `failed` | measures contradict each other; no `unique` boolean and no explained or residual figure |

| `interpretation` | Conditions |
| --- | --- |
| `raw_unique` | `raw.unique` is true (then `E = 0` or unknown) |
| `unique_after_row_deduplication` | `raw.unique` false, `after.unique` true |
| `unique_among_present_ids` | `M > 0`, `E_present` known, `U_present >= 2` and `R_residual = 0` (2.2) |
| `repeated_between_distinct_records` | `R_residual > 0` (with `M > 0` too, then `status` is `limited`) |
| `not_assessed` | everything else, with a `reason` |

`not_applicable` is not a stored status: the object is absent (3). The `reason` codes are stable
and listed here (D9). An empty `reason` (`null`) goes with `complete`.

| `reason` | With status | Meaning |
| --- | --- | --- |
| `missing_ids` | `limited` | `M > 0` (case E); the figures of 2.2 are given when `E_missing` and `E` are exact |
| `too_few_records` | `limited` | `N < 2`: raw not concluded |
| `too_few_distinct_records` | `limited` | `U < 2` (case F) |
| `scope_partial` | `limited` | `scope.complete` is false (6.3) |
| `distinct_estimated` | `limited` | `D` only estimated (KMV) or limited |
| `distinct_not_exact` | `limited` | `D` exact only in the original domain and a stage changed values (T19) |
| `distinct_unavailable` | `not_assessed` | no cardinality at all |
| `duplicates_limited` | `limited` | `E` is a lower bound and no valid Dedup report |
| `duplicates_disabled` | `not_assessed` | `records.duplicates` is `false` and no valid Dedup report |
| `inconsistent_measures` | `failed` | an invariant of 2 is broken |
| `evidence_conflict` | `failed` | two exact sources of `E` or `D` differ (6.4) |
| `computation_error` | `failed` | the rule raised; the Report is still written |

Order of the checks (the first that applies decides the reason): `distinct_*`, `scope_partial`,
`missing_ids`, `too_few_records`, `duplicates_*`, `too_few_distinct_records`, then the invariants.
`failed` always wins: a broken invariant is reported whatever else is missing.
Raw figures are given whenever `D` is exact, `M = 0`, the scope is complete and `N >= 2`.

## 5. JSON object (D5, D10)

Member `identifier_uniqueness` of `ColumnSummary` (`summary_models.py`), optional, built with the
summary when the document is built (ADR `2026-10-17-report-summary-built-with-the-document`), so
HTML and JSON read one value. Absent (`null`) outside identifier columns. All counts are integers
or `null`; `null` is never replaced by `0`. No sentence is stored.

```json
{
  "rule_version": 1,
  "status": "complete",
  "interpretation": "unique_after_row_deduplication",
  "reason": null,
  "scope": {
    "dataset": "rows",
    "population": "source_records",
    "source_records": 100000,
    "distinct_records": 99500,
    "eligible_id_values": 100000,
    "missing_id_positions": 0,
    "id_value_domain": "analytical",
    "row_identity": "full_decoded_csv_row_v1",
    "complete": true
  },
  "raw": {"unique": false, "id_distinct": 99500, "id_redundant": 500},
  "after_row_deduplication": {"unique": true, "id_distinct": 99500, "id_redundant": 0},
  "explanation": {
    "duplicate_row_extra_copies": 500,
    "id_repetitions_explained": 500,
    "id_repetitions_residual": 0
  },
  "evidence": {
    "id_cardinality": {"source": "scan.values.cardinality", "accuracy": "exact", "domain": "analytical"},
    "duplicate_rows": {
      "source": "scan.records.duplicates",
      "accuracy": "exact",
      "identity": "full_decoded_csv_row_v1",
      "report": null
    },
    "source_sha256": "ece53017...",
    "rejected": []
  }
}
```

- `scope.row_identity`: `full_decoded_csv_row_v1` for a CSV (the Scan's digest is equivalent, 6.5),
  `scan_record_v1` for any other source (the Scan's comparison of path, native type and raw value).
- `evidence.id_cardinality.source`: `scan.values.cardinality`, `deep.exact_distinct` or
  `deep.analytical_distinct` (lot 7).
  `accuracy`: `exact`, `estimated` or `limited`; `domain`: `analytical` or `original`.
- `evidence.duplicate_rows.source`: `scan.records.duplicates`, `dedup.report` or
  `deep.duplicate_rows_count` (lot 6); `accuracy`:
  `exact`, `lower_bound` or `disabled`; `report` is `null` or
  `{"name", "format_revision", "settings_identity", "content_sha256", "origin"}` with `origin`
  `colocated` or `explicit`. No path outside the file name is stored.
- `evidence.rejected`: proofs that were read and refused, `[{"source", "reason"}]`, with the
  Dedup `reason` codes of 7. A refused proof is a diagnostic, never an error of the Report.
- `evidence.conflict`: `null`, or for `evidence_conflict` `{"measure": "duplicate_rows" | "id_cardinality",
  "values": [{"source", "value"}, ...]}` with the exact values that disagree.
- `near_unique`: `null`, or for `repeated_between_distinct_records` the non-binding reading of 14 (`model_version`, `signal`,
  `residual_repetitions`, `distinct_records`, `tolerance`, `limiting_bound`).
- `explanation.duplicate_row_extra_copies_without_id`: `E_missing` (2.2). Present only for a column that
  lacks a value whose copies were counted (the member is omitted otherwise, not `null`). With `M > 0` and
  the figures given, `duplicate_row_extra_copies` stays `E`, `id_repetitions_explained` is `E_present`.
- `evidence.missing_id_copies`: `{"source": "deep.missing_id_copies", "accuracy": "exact" | "lower_bound",
  "identity"}`, omitted when the column has no missing ID or no count.
- `evidence.source_sha256`: the Scan's SHA-256 (the reference of every proof).
- `rule_version` changes with any change of formula, threshold, reason or source order; the
  derived object is recomputed from the document each time it is built, so no cache holds it
  (12.5 of the cahier is met by building it with the summary). Report `format_revision` becomes 5
  (D3); the format 0.2.0 stays.
- A column the rule raised on keeps `status: "failed"`, `reason: "computation_error"`, null figures.

Sensitive columns (T31): only counts, codes and the SHA-256 enter the object, so `mask` and `hide`
change nothing. No ID value, example or path other than file names is stored.

## 6. Evidence

### 6.1 `D`, the distinct analytical values

1. `values.cardinality` of the Scan, exact and complete in the analytical domain
   (`analytical_distinct`). An estimate or a `limited` envelope is never `D` (T18).
2. `analytical_distinct` of the second pass (lot 7, 6.7): exact, in the analytical domain, same Scan `base`,
   status `complete`, the values and the stages of the Scan. It needs no condition on the stages.
3. `exact_distinct` of the second pass, only when `report_classification._distinct_count` would
   accept it (same Scan `base`, status `complete`) **and** `_analytical_stages_unchanged` (T19, T20).
   Lot 1 reuses both and does not copy them.
4. Otherwise `D` is unknown (`distinct_*`).

### 6.2 `E`, the extra copies of whole rows

1. `datasets[].records.duplicates.count` when `complete` (T12).
2. A validated Dedup report (7), when 1 is `limited` or `disabled` (T13).
3. The Deep count of the copies (`duplicate_rows_count`, lot 6, T33, 6.6), when the second pass was
   forced or asked for and stands on this Scan.

`limited` is a lower bound and `disabled` has no value: neither is `E`.

### 6.3 `scope.complete` (D6, A2)

```text
complete = scan.status == "complete"
       and scan.scope.records_excluded == 0
       and (single dataset: dataset.record_count == scan.scope.records_read)
```

The Scan has no row limit setting: only excluded records (tolerant policy: a CSV record of the
wrong width, a JSON duplicate key, a record that is too large) make a scan `partial`. `records_excluded` is
global to the scan, so a multi-dataset source with any exclusion is not complete for any of its
datasets (conservative; T25, T26). A Dedup proof additionally needs `records.total == N` (7), which
a file with excluded records can never satisfy: Dedup refuses a CSV with a record of another width.
An incomplete scope gives `limited` / `scope_partial` and no `unique` boolean.

### 6.4 Several exact sources and conflicts (D8)

The Scan's exact count comes first. When a valid Dedup report is also present its
`records.extra_copies` must be equal; if not, the evidence is contradictory: `failed` with
`evidence_conflict`, both values in `evidence.conflict` for the diagnosis, no choice made (T28). When `D`
from the Scan and from the second pass are both exact in the same domain and differ, the same
rule applies. The three sources of `E` (Scan, Dedup report, Deep count) are compared in that order:
the first exact one is the evidence shown, any other exact one that differs is a conflict, and
among the lower bounds the highest is shown and used as the floor. A proof that is merely refused (7) is not a conflict.

The same holds for `D` (lot 7): the exact counts of 6.1 are compared in the order of 6.1. The first is
`UniquenessFacts.distinct`, the others `distinct_alternatives`; two usable exact counts that differ are
`failed` with `evidence_conflict` and `evidence.conflict.measure` `id_cardinality`. An exact original count
whose stages changed a value is no `D`, yet it bounds `D` from above (normalizing only merges values): an analytical `D` above
it is `inconsistent_measures`. A stopped analytical count (a lower bound) is never `D`.

### 6.5 Identity of the rows, A1 (D7)

Verified at lot 0 by `tests/scan/test_row_identity_equivalence.py` on adversarial CSV (empty and
long cells, BOM, quotes, multiline cells, NFC and NFD, mixed line endings, wide rows, delimiters
and encodings, random files): the Scan's `records.duplicates.count` equals Dedup's `extra_copies`
and an independent oracle. They cannot differ for a CSV that both accept, because:

- both read with `csv.reader(strict=True)`, `newline=""` and the same encoding and delimiter;
  the BOM never reaches a row; a multiline cell is one record;
- a record of another width is fatal for Dedup and for a strict Scan; a tolerant Scan excludes it
  (`records_excluded > 0`, status `partial`), and then `scope.complete` is false and no Dedup
  report can exist for that file (it is `failed`);
- a cell with a NUL is refused by the Scan reader, so its NUL-safe digest form is unreachable;
- both identities are injective on tuples of decoded strings of a fixed width (the Scan up to the
  BLAKE2b 128-bit collision probability, Dedup exactly), with no normalization.

**Rule (D7):** for a CSV source the two counts are interchangeable as `E`. The Scan's is
probabilistic by construction and documented as such; the Dedup report is the exact counterpart,
and both are labelled with `row_identity: full_decoded_csv_row_v1`. For other sources the Scan's
count is the only `E` and carries `scan_record_v1`. A Dedup report is never used for a non-CSV.

### 6.6 The Deep count of the copies (lot 6, UID-012, T33)

`count_extra_copies` (`dedup/count_only.py`) is the count-only mode of the Dedup engine: the same
canonical key (`full_decoded_csv_row_v1`), the same exact store (memory, then SQLite), the same strict
reading, and no output of any kind (no CSV, no report, no marks of records; the temporary database is
deleted). It stops cleanly at three ceilings and then returns a lower bound, never a count:

| Ceiling | Setting | Default | Stops with |
| --- | --- | --- | --- |
| accounted size of the table of distinct rows | `deep.copies.memory_mb` | 256 | `memory_budget` (only when the disk is forbidden) |
| estimated size of the temporary database | `deep.copies.disk_mb` | 2,048 (`0` forbids the disk) | `disk_budget` |
| records read | `deep.copies.max_rows` | 10,000,000 | `row_limit` |

The ceilings are bytes and records; the disk is estimated from the accounted key bytes (`estimate_disk_bytes`),
not measured on the volume, so a file stops at the same record on any machine. `CALCULATION_VERSION` (1) changes
with any change of what the count means.

The analyzer `duplicate_rows_count` (`scanner/planner/analyzers/copies.py`, `scanner/secondpass/copies.py`) gives the
engine to the planner:

- one candidate per CSV source with one dataset and at least one record, named `duplicate_rows_count:<dataset>:$`
  (`Analyzer.rows`, `facts.rows_facts`); no candidate for JSON or Excel;
- `already_satisfied` (`copies_exact`) when the Scan counted exactly; `not_applicable` when the Scan was set not to
  count (`duplicates_disabled`, never overridden, forced or not) or left records out (`records_left_out`);
- utility 40, or 50 for a dataset with an identifier candidate whose Scan count is a lower bound (6.8): asked for,
  forced, or chosen by the planner by the criteria of 6.8. Its cost is the whole file, in memory up to the ceiling;
- it reads the file on its own, outside the router and the workers, so the result does not depend on their
  number; an exact result is checked against the Scan (SHA-256 and size through the source guard, `records`
  against `record_count`, the Scan's lower bound), a stopped one only against the size and time of the file;
- the result `duplicate_rows` holds the counts, the identity, `calculation_version`, `storage` and, when exact, the
  SHA-256; the analysis is `complete`, or `limited` with the ceiling as `reason`.

`facts_from_scan` appends the result as the third `DuplicateEvidence` when the second-pass document stands on this
Scan (same base). An exact result also needs the Scan's SHA-256 and `records == N`; otherwise it is ignored, as a foreign
proof would be. `rule_version` stays 1: the P0 object was never published, so adding a source does not break a reader.

### 6.7 The Deep count of the distinct analytical values (lot 7, UID-013)

The Scan's `analytical_distinct` exists only while its table of values lives. When the table was released and a
cleaning stage (`nfc`, `trim`, `collapse_whitespace`) changed a value, `exact_distinct` (original values) is no `D` (T19).
The analyzer `analytical_distinct` (`scanner/planner/analyzers/analytical.py`, `scanner/secondpass/analytical.py`,
design 20.41) counts the analytical values exactly, with the sets and the memory stop of `exact_distinct`:

- a separate analyzer, so the original and the analytical counts are never mixed under one name; both can run on a field;
- applicable when the Scan has no analytical count and a stage changed a value; `already_satisfied`
  (`distinct_exact`) when the Scan has it; `not_applicable` (`stages_unchanged`) when `exact_distinct` is enough;
- utility 40, or 50 for an identifier candidate (6.8): asked for, forced, or chosen by the planner by the criteria of 6.8;
- the result `AnalyticalDistinctCount` (`stages`, `values`, `distinct`, `redundant`, `unique`, `changed`), or `distinct_limited`
  at the memory budget; `changed` is checked against the Scan's counters of the stages, and `values` against its count;
- in the Report it is `D` with `domain: analytical`, `stages_changed_values: false`, source `deep.analytical_distinct`.

### 6.8 When the planner runs the two counts by itself (lot 8, UID-011, cahier 12)

Decision: ADR `2026-10-24-unique-id-planner-criteria`; design 20.42. The planner reads the Scan only. A column is a
**candidate** when the Scan gives it `identifier/id` (a raw `unique_id` needs no count: `E = 0` follows), every position
holds a value (a column of a CSV file that lacks one is a candidate too since lot 10, 6.9), it is not under an array, no record was left out and the dataset has two records at least. The cases of the
cahier 12.1 (an exact `D` and `E`, a valid Dedup report, an ineligible column, missing IDs, an unique raw ID) are exactly
the columns that are not candidates or the candidates that are `already_satisfied`.

| Analysis | Chosen by itself when | Else |
| --- | --- | --- |
| `analytical_distinct` | the field is a candidate, the Scan has no analytical count and a stage changed a value (utility 50) | utility 40: asked for, forced |
| `missing_id_copies` | an identifier candidate lacks a value (6.9), the total of the copies is exact in the Scan or proved or selected, an exact distinct count of that column is in the Scan or selected, the table of the rows without an ID fits the automatic memory, the class of the record is at most `moderate` (utility 50) | `copies_unknown`, `distinct_unknown`, `budget`, `cpu_class`, `low_utility` |
| `duplicate_rows_count` | the dataset has a candidate, the Scan's count is a lower bound (not exact, not disabled), the table fits the automatic memory, the class of the record is at most `moderate` (three columns or more) and a distinct count of a candidate is exact in the Scan or selected in the plan (utility 50) | `distinct_unknown`, `budget`, `cpu_class`, `low_utility` |

Everything else of the automatic choice applies unchanged. A valid Dedup report makes the count of the copies
`already_satisfied` (`copies_proved`). The automatic count is expected to stay in memory (the ceilings of `deep.copies` still apply to a table larger than estimated): with the defaults it covers a file of up to a
few hundred thousand records, and a larger one needs `--deep` (which asks), a Dedup report or a Scan that tracked it whole
(`limits.max_tracked_records`, 2,000,000 by default).

**Cache and versions (cahier 12.5).** A stored result is reused when its key is the one the run would give it: the Scan it
stands on (source SHA-256, configuration, so the normalization stages), the analyzer and its version, the dataset, the
field, the method and its parameters (the ceilings of the copies). The version of `duplicate_rows_count` is
`CALCULATION_VERSION` of the count (`dedup/calculation.py`) and that of `analytical_distinct` is its own constant
(`analyzers/analytical.py`); a change of what a count means raises it and makes older results stale. A stopped count of the
copies is reused at the same key (its ceilings are bytes and records); a stopped set of values is not. A Dedup report is no
part of the second-pass document: the derived object is rebuilt with the summary each time, so no cache holds it.

### 6.9 The Deep count of the copies of the rows without an ID (lot 10, cahier 5.4)

Decision: ADR `2026-10-25-missing-id-copies`; design 20.43. `count_missing_id_copies` (`dedup/count_only.py`)
is the light mode of the engine: the same strict reading, canonical key (`full_decoded_csv_row_v1`), exact
store, three ceilings (`deep.copies`) and SHA-256 as 6.6, with a table of the rows that lack a value in at
least one of the named columns only, so its memory follows those rows and not the file. Per column it counts
the records without a value (`rows_without_id`, checked against `N - values.count` of the Scan), the distinct
ones and the extra copies (`extra_copies_without_id`, `E_missing`). A cell holds a value when the Scan counted
it in `values.count` (the classifier and null markers of the Scan's configuration, replayed). Its version of
calculation is `MISSING_CALCULATION_VERSION` (1).

The analyzer `missing_id_copies` (`scanner/planner/analyzers/missing_copies.py`,
`scanner/secondpass/missing_copies.py`) gives it to the planner:

- one candidate per CSV source with one dataset, named `missing_id_copies:<dataset>:$`, whose parameters are
  the three ceilings and `columns` (JSON list of field id and 1-based position, part of the key); one
  reading counts every identifier column that lacks a value;
- `not_applicable` (`no_missing_id_candidate`, `records_left_out`, or `duplicates_disabled` when the Scan did
  not count the copies and no Dedup report proves them: there would be no total);
- it needs an exact total of `E` (the Scan's exact count, a Dedup report or `duplicate_rows_count`), which the
  planner checks like the distinct count (`copies_unknown`);
- the result `MissingIdCopiesResult` (`accuracy` `exact` or `lower_bound`, `columns[]`, `source_sha256` when
  exact). A stopped count is a lower bound and never `E_missing`. Both are reusable at the same key
  (`DETERMINISTIC_STOP`).

`facts_from_scan` appends `UniquenessFacts.missing_copies` (`MissingCopiesEvidence`) when the second-pass
document stands on this Scan and the count is exact, read the very file of the Scan (SHA-256, records) and
found as many rows without a value in the column as the Scan did; otherwise it is ignored. `rule_version`
stays 1 (the P0 object was never published).

## 7. Dedup proof (UID-005)

A `<stem>.dedup.json` is read through `dedup.report.read_report` and `broken_invariants`, without
change to Dedup, and used only when every check passes. The first failed check is the `rejected`
reason (D9); the others are not looked at.

| # | Check (cahier 8.2) | `reason` |
| --- | --- | --- |
| 1 | the file reads as a `tabalyst.dedup` of the supported format and revision | `dedup_unreadable` |
| 2 | `status == "complete"` (`failed` and `in_progress` are refused) | `dedup_not_complete` |
| 3 | `source.content_sha256 == scan.source.sha256` (the name alone proves nothing) | `dedup_source_mismatch` |
| 4 | the Scan source is a CSV with a single dataset (A7) | `dedup_not_csv` |
| 5 | `settings.delimiter` and `settings.encoding` equal the Scan's (`source.csv`, `source.encoding`) | `dedup_dialect_mismatch` |
| 6 | `settings.identity == full_decoded_csv_row_v1` | `dedup_identity_unsupported` |
| 7 | `records.total == N` of the dataset (same rows, no excluded record) | `dedup_total_mismatch` |
| 8 | `broken_invariants(report) == []` | `dedup_invariants_broken` |

Encodings are compared after `codecs.lookup(...).name`, the Scan's recorded `source.encoding`
against `settings.encoding`: aliases such as `utf8` and `UTF-8` are equal, `utf-8` and `utf-8-sig`
are not. Consumers never open the CSV
outputs, never write the report, never run Dedup or `--force`, and never search folders.

### 7.1 Where the report comes from (D2, A8, A9)

1. `report --dedup-report <file or folder>` (API parameter `dedup_report`, config key
   `report.dedup_report`): a file is used as given; a folder is searched for `<source stem>.dedup.json`
   only. A missing file or folder, or a folder without the expected file, is an error of the option
   (the user named it).
2. Otherwise the `<stem>.dedup.json` beside the source, when the source is given (colocated). It is
   silently absent when absent; a present but refused one is listed in `rejected`.
3. `report --scan` without a source: only the explicit option is used, and the colocated report is
   looked for beside the scan document under the recorded source stem (A9, to confirm at lot 3).
4. The option with a source that is not a CSV, or a mode with no dataset to prove, is an error
   (project rule: no option silently ignored).

## 8. Words (D11)

The JSON holds codes; the HTML derives words in `report_labels.py` by code. The five cases of the
cahier 11.2 map to label keys (the English text is fixed at lot 4, the keys now):

| Case | Condition | Label key |
| --- | --- | --- |
| A | `interpretation == raw_unique` | `identifier_uniqueness.raw_unique` |
| B | `unique_after_row_deduplication` | `identifier_uniqueness.unique_after_row_deduplication` |
| C | `repeated_between_distinct_records` | `identifier_uniqueness.repeated_between_distinct_records` |
| D | `not_assessed`, any reason but `missing_ids` | `identifier_uniqueness.not_assessed` |
| E | reason `missing_ids`, whatever the interpretation (lot 10: with the figures of 2.2 it is `unique_among_present_ids` or `repeated_between_distinct_records`) | `identifier_uniqueness.missing_ids` |

Language rule: never write "Unique ID" without "after row deduplication" when the dataset has at
least one exact copy of a row (`E > 0` or `E` unknown with `D < N`). A repetition is an observation
of quality, not an Error: no finding of class Error is created, the raw finding stays and links to
the decomposition, and the same occurrences are never counted twice in a summary indicator.

### 8.1 Where the words are printed (lot 4)

Texts come from `report_labels.py` (`UNIQUENESS_*`), the view models from `report_uniqueness.py`
(never serialized, nothing computed beyond the case of 8). English texts, fixed at lot 4:

| Case | Title | Text |
| --- | --- | --- |
| A | Unique ID | Unique across all N source records. No missing IDs. |
| B | Unique after row deduplication | E repeated ID occurrences are fully explained by E exact duplicate rows. No ID conflicts remain among U distinct records. |
| C | ID repetitions | T repetitions: E explained by exact duplicate rows, R remain between distinct records. |
| D | Uniqueness not fully assessed | The exact number of distinct IDs or duplicate rows is unavailable. No conclusion about uniqueness after deduplication. (plus the sentence of the `reason`) |
| E | Missing IDs | Uniqueness after deduplication cannot be established: some records have no ID. With the copies of the rows without an ID counted (2.2): `M records have no ID. Among the P records that have one, E_present are exact copies of rows. No ID repeats between the U_present distinct rows that have one.` or `... R ID repetitions remain between the U_present distinct rows that have one.` |

- **Column page**: a card `#uniqueness` in 01 Summary (no renumbering), absent outside identifiers,
  with the figures (`null` printed as "not established"; none for `failed`), the evidence and the
  refused proofs. The type name of the strip and the pill comes from `ColumnPage.type_name`: Unique ID
  (A), Unique after row deduplication (B), ID otherwise; never "Probable unique ID" for such a column.
- **Findings**: the raw `identifier.repetition` card stays and gets a link to `#uniqueness`
  (`PageFinding.uniqueness_link`). No finding and no Error is created.
- **Summary table**: a short line under the overview for the concluding cases A to C only.
- **Analysis settings**: `Identifier uniqueness` entry with the rule version, the sources of the
  copies actually used, the Dedup report names and origins, and the refused proofs.

## 9. Python interface (for lots 1 and 2)

Lot 1 owns the pure rule; lot 2 owns the proofs. They share these inputs, fixed here so that they
can be built in parallel. Models are frozen Pydantic models; the rule reads no file.

```python
class DistinctEvidence:   # D
    value: int | None
    source: Literal["scan.values.cardinality", "deep.exact_distinct", "deep.analytical_distinct"]
    accuracy: Literal["exact", "estimated", "limited"]
    domain: Literal["analytical", "original"]
    stages_changed_values: bool   # an analytical stage altered a value (T19)

class DuplicateEvidence:  # E
    value: int | None             # lower bound when accuracy is lower_bound
    source: Literal["scan.records.duplicates", "dedup.report"]
    accuracy: Literal["exact", "lower_bound", "disabled"]
    identity: Literal["full_decoded_csv_row_v1", "scan_record_v1"]
    report: DedupReportRef | None

class UniquenessFacts:
    dataset: str
    eligible: bool                # identifier role, not under an array
    records: int                  # N
    present: int                  # P
    missing: int                  # M
    scope_complete: bool
    source_sha256: str
    distinct: DistinctEvidence | None
    distinct_alternatives: tuple[DistinctEvidence, ...]   # the other exact counts of D (lot 7)
    duplicates: tuple[DuplicateEvidence, ...]   # every usable source, Scan first
    rejected: tuple[RejectedProof, ...]

def assess_identifier_uniqueness(facts: UniquenessFacts) -> IdentifierUniqueness
```

`IdentifierUniqueness` is the model of 5. `assess` returns `None` when `eligible` is false (3), is deterministic, free of workers and
files, linear in the number of candidate columns, and never raises for bad evidence (it returns
`failed`).
The test helpers `tests/report/identifier_uniqueness_helpers.py` build `UniquenessFacts` through
`facts(...)` and compare with the in-memory oracle, so a change to these names is a change here.

### 9.1 Package layout

One package, one file per lot, so lots 1 and 2 never touch the same file:

| File | Lot | Content |
| --- | --- | --- |
| `src/tabalyst/identifier_uniqueness/models.py` | 1 | the models of 5 and 9, `RULE_VERSION` |
| `src/tabalyst/identifier_uniqueness/rule.py` | 1 | `assess_identifier_uniqueness` |
| `src/tabalyst/identifier_uniqueness/proof.py` | 2 | `load_dedup_proof(path, *, scan, dataset, origin) -> DuplicateEvidence \| RejectedProof`, `find_dedup_report(source_or_scan_dir, option) -> Path \| None` (7.1) |
| `src/tabalyst/identifier_uniqueness/facts.py` | 3 | `facts_from_scan(...)`: builds `UniquenessFacts` from the Report's classification, field, dataset, `analyses` and the proof |
| `src/tabalyst/identifier_uniqueness/__init__.py` | 1 | re-exports the models and `assess_identifier_uniqueness` |

Lot 3 also exposes, in `facts.py`, `facts_from_scan(scan, dataset, field_id, *, analyses=None,
dedup_report=None, source_dir=None) -> UniquenessFacts | None` (`None` for a column that is not an
identifier), which applies the Report's classification (`report_classification.refine`), the
evidence of 6 and the proof of 7.

`RejectedProof` has `source`, `reason` (the codes of 7). `DedupReportRef` has `name`,
`format_revision`, `settings_identity`, `content_sha256` and `origin`.

## 10. Test coverage by lot

`@pytest.mark.uid_lot("n")` skips a test until lot `n` is enabled in `tests/report/conftest.py`;
`uid_t(...)` names the requirement. The A1 and property tests run now.

| Lot | Tests |
| --- | --- |
| 0 | A1 (`test_row_identity_equivalence.py`), the properties of cahier 15.2 against the oracle |
| 1 | T01 to T05, T08 to T11, T18 to T22, T23 to T25, T28, T12 (Scan proofs alone), cases A to F |
| 2 | T07, T13 to T17, T32 (JSON alone), T34 and the Dedup `reason` codes of 7 |
| 3 | T12, T25, T26, T27, T29 (JSON), T30, T31, no extra reading of the source, Scan unchanged |
| 4 | T29 (HTML and JSON agree), cases A to E rendered, no double count, no automatic Error |
| 5 | The whole suite, the reference measures of 12 and the conformance of 13 |
| 6 | T33 (`test_t33_...`), `tests/dedup/test_count_only.py`, `tests/scan/test_duplicate_rows_count.py`, `tests/report/test_identifier_uniqueness_deep_copies.py` |
| 7 | `tests/scan/test_analytical_distinct.py`, `tests/report/test_identifier_uniqueness_deep_distinct.py` (T19, T20 completed by the analytical count, conflict of two `D`) |
| 8 | `tests/scan/test_unique_id_planner.py`, `tests/report/test_identifier_uniqueness_planner.py` (UID-011: the criteria, the proof, the cache and the versions) |
| 9 | `tests/report/test_identifier_uniqueness_near_unique.py` (the tolerance, its bounds, the cases without a reading, the JSON, the page, the classification unchanged) |
| 10 | `tests/dedup/test_count_missing_id_copies.py`, `tests/scan/test_missing_id_copies.py`, `tests/report/test_identifier_uniqueness_missing_ids.py` (the light count against a brute-force oracle, the analyzer and its planner criteria, the rule of 2.2 and its invariants, the whole Report and the page) |

## 11. Open points kept for later lots

- Exact figure of `scope.complete` for multi-collection JSON with exclusions (P0 is conservative).
- Gate 4: the maintainer reads the five texts of 8.1.
- Whether `report --scan` finds the colocated Dedup report beside the scan document (7.1, lot 3).
- Near-unique (14): calibrate the constants on real files (the lab holds none), and measure the number of distinct
  repeated IDs and the concentration of the repetitions, which the cahier 13 asks to tell from the extra occurrences.

## 12. Reference measures, P0 (lot 5, cahier 15.3)

Measured on 24 October 2026 on the maintainer's Windows 11 machine, with a generated CSV of
100,000 records and 6 columns (`customer_id` distinct per row, 500 exact copies of rows), through
the command line, median of 3 runs, peak resident memory of the process tree. The baseline is the
commit `8c0065d` (0.7.1) in a temporary worktree. The script and the files stay outside the
checkout (`D:\GIT.test\tabalyst\artifacts\uid-lot5`). The seconds depend on the machine and are
not a target: only the comparison between lines is read.

| Measure | 0.7.1 | Now | Peak memory (now) |
| --- | --- | --- | --- |
| `scan --no-html` | 3.08 s | 2.61 s | 179 MiB |
| `report` from the source, with no scan to reuse | 1.51 s | 1.23 s | 134 MiB |
| `report --scan` from a Scan document (facts alone) | 1.64 s | 1.34 s | 138 MiB |
| `report --scan --dedup-report` (Dedup report of the same file) | not available | 1.36 s | 137 MiB |

- **Scan:** the Scan does not import `identifier_uniqueness`; its standard path is unchanged and no
  slower within the noise of the machine. There is no "with qualification" Scan to compare.
- **Report from facts:** the qualification costs less than the noise between runs (the Report is not
  slower than 0.7.1). The JSON of the 100,000-row file gives `customer_id` as `complete`,
  `unique_after_row_deduplication`, 500 extra copies, 500 explained, `R_residual = 0`, from the Scan's
  exact counts (`scan.records.duplicates`), without reading the CSV again (test T12, gate 3).
- **Report with Dedup:** reading a valid `<stem>.dedup.json` adds a JSON read and its checks (7); the
  measure is not distinguishable from the run without it. The memory is that of the Report.
- **Not measured at lot 5:** the count-only mode and the 1 M, 5 M and 10 M rows runs, which 12.1 gives.
  No objective in seconds or in overhead is declared validated (cahier 15.3).

### 12.1 Reference measures, P1 (lot 8, cahier 15.3 and T32)

Measured on 24 October 2026 on the same machine, with `tabalyst-lab/benchmarks/copies_scale.py`: a generated CSV of
4 columns (about 50 bytes a record), each case in a fresh interpreter, one process, the default ceilings of
`deep.copies` (256 MiB, 2,048 MiB of disk, 10,000,000 records) unless said. The count agrees with the generator in
every case. The seconds depend on the machine and are not a target.

| Records | Copied | Storage | Seconds | ns a record | Peak memory | Temporary disk |
| --- | --- | --- | --- | --- | --- | --- |
| 1 M | 0, 1, 25 % | memory | 1.6, 1.7, 1.8 | 1,634, 1,646, 1,765 | 226, 225, 210 MiB | none |
| 5 M | 0, 1, 25 % | disk | 28.0, 28.0, 31.3 | 5,595, 5,599, 6,250 | 330, 345, 332 MiB | 357, 355, 268 MiB |
| 10 M | 0, 1, 25 % | disk | 57.1, 62.6, 79.8 | 5,709, 6,260, 7,981 | 328, 350, 332 MiB | 725, 718, 544 MiB |

- **Memory against disk.** In memory the count costs 1,500 to 1,800 ns a record; once the table moves to the temporary
  database (past about 1.2 M records at 256 MiB) it costs 5,600 to 8,000. `NS_PER_CELL["rows"]` stays at 6,000: inside
  the range of the estimate, above the typical disk figure, under the worst one (10 M records, a quarter of them copies).
- **What an automatic choice covers.** The table is accounted at the key bytes plus 160 bytes an entry. With the disk
  forbidden and 128 MiB (the memory of an automatic choice) the count is exact up to 500,000 records of 50 bytes
  (0.82 s, 143 MiB), and a file of 1,000,000 stops at the memory ceiling after 638,609 records. The default Scan keeps
  the copies exact up to 2,000,000 records (`limits.max_tracked_records`): the two ranges do not meet, so with the
  defaults the count of the copies is chosen by itself only when that limit was lowered; a larger file needs `--deep`
  (which asks first), a Dedup report or a Scan that tracked it whole. D13 holds; whether to give the automatic count its
  own budget or the disk is a decision for the maintainer.
- **Ceilings** (5 M records, a quarter copied): `max_rows` 2,000,000 stops with `row_limit` after 7.9 s (300 MiB,
  104 MiB of disk); `memory_mb` 64 with no disk stops with `memory_budget` after 423,097 records (0.66 s, 112 MiB);
  `disk_mb` 100 stops with `disk_budget` after 1,678,257 records (5.4 s, 79 MiB of disk). Each gives a lower bound.
- **T32 at scale** (the Scan of the file, its Dedup report, then `report --scan --dedup-report`): at 1 M records the
  Report takes 0.73 s and 155 MiB; at 10 M records (a quarter copied) 0.77 s and 156 MiB, the CSV not opened once
  (watched), the Scan document 4.8 MiB. The Scan took 5.0 and 45.8 s, Dedup 4.1 and 81.0 s. The uniqueness of the
  column is still `limited` (`distinct_estimated`): the proof gives `E`, but the Scan only estimated `D` for a column
  of more than 100,000 distinct IDs, and an exact `D` of 10 M IDs needs a set of about 1.2 GiB.
- **The copies of the rows without an ID** (lot 10, 6.9), generated CSV of 4 columns, in one
  process, memory only, measured on 25 October 2026 with the same default ceilings. The light count against the full
  count of the same file:

  | Records | Rows without an ID | Light count | Full count |
  | --- | --- | --- | --- |
  | 1 M | 0.5 % | 0.55 s, 546 ns a record | 1.69 s |
  | 1 M | 10 % | 0.68 s, 678 ns a record | 1.65 s |
  | 1 M | 50 % | 1.09 s, 1,085 ns a record | 1.84 s |
  | 5 M | 2 % | 3.77 s, 754 ns a record, in memory | 28.05 s, 5,609 ns a record, on disk |

  The table of the light count holds the rows without an ID, so it stays in memory long after the full table has moved
  to the disk (5 M records: 100,140 rows kept against 5 M). `NS_PER_CELL["rows_without_id"]` stays at 1,500.
- **The exact count of the analytical values** costs 2,336 to 2,763 ns a record on three profiles of 1 M identifiers
  (10 characters, digits, 36 characters; a fifth padded), the reading of the three columns included (about 350 ns); the
  plan's maximum memory is 125 to 152 MiB per million IDs. `NS_PER_CELL["analytical_distinct"]` stays at 2,000.

## 13. Conformance to the criteria of the cahier 18 (P0 and P1)

State after lot 5, rechecked at gate P1 (26 October 2026, release 0.7.2, P0 and P1 published together).
Maintainer documentation, never published.

| # | Criterion | Evidence | State |
| --- | --- | --- | --- |
| 1 | No regression of `identifier/id` and `identifier/unique_id` | `test_the_scan_classification_and_the_raw_finding_do_not_change`, T21 to T24 tests; the classification tests of `tests/scan/` | Met |
| 2 | A repetition explained by a copy is not shown as an ID conflict between distinct rows | T02, T05, `test_the_porte_3_deliverable_100000_rows_500_copies`; case B of the Report | Met |
| 3 | The raw reality stays and the adjusted reading is separate | `identifier.repetition` unchanged (`test_a_repetition_is_never_an_automatic_error`); the `raw` and `after_row_deduplication` blocks | Met |
| 4 | No strict `true` from an estimated, limited, incomplete, inconsistent or foreign proof | T14, T18, T25, T28, `test_no_false_is_ever_emitted_without_a_demonstrated_repetition`, the properties of 15.2 | Met |
| 5 | The usual case, a Scan entirely exact, needs no new reading | T12 (`test_t12_the_report_does_not_read_the_source_again`), the measures of 12 | Met |
| 6 | A Dedup 0.7.1 report is used with identity validation, Dedup unchanged | T13, T15 to T17, T32, T34, `test_a_refusal_never_writes_the_dedup_report`; `src/tabalyst/dedup/` unchanged at P0 (lot 6 adds `count_only.py` and makes the helper `staged` public, no behavior change) | Met |
| 7 | The JSON is versioned, verifiable and consistent with the HTML | `format_revision` 5, schema, T29 (`test_t29_the_html_and_the_json_say_the_same`), `profile-changelog.md` | Met |
| 8 | The functional, invariant, security and non-regression tests pass | the suite (T31 exposure, properties, A1); T33 is P1 and runs since lot 6 | Met (P0 and P1; T33 runs since lot 6) |
| 9 | The documentation tells raw Unique ID from Unique after row deduplication and, later, near-unique | `read-report.md` (Column page), `findings.md`, `json-profile.md`, `profile-changelog.md`, the glossary, `dedup/index.md` | Met; near-unique is documented since lot 9 (14), as a reading and never as a guarantee |
| 10 | The P1 and P2 requirements not delivered are identified and not described as available | the criteria under which the two Deep counts run by themselves are documented as they are (6.8, lot 8); plan lot 9 | Met |

Delivered at lot 6 (P1): the count-only mode of the Dedup engine and the Deep analyzer of the copies of
rows (UID-012).

Delivered at lot 7 (P1): the Deep analytical cardinality (UID-013, 6.7).

Delivered at lot 8 (P1): the criteria of the planner, the Dedup proof that spares the count, the cache and the
versions (UID-011, 6.8) and the measures at 1 M, 5 M and 10 M records (12.1).

Delivered at lot 9 (P1): the near-unique reading (UID-014, 14).

Delivered at lot 10 (P1): the decomposition despite missing IDs (cahier 5.4, 2.2 and 6.9).

Not delivered and not described as available: the composite keys, the discovery of candidates and the Smart or Explore recommendations (P2, UID-015).

### 13.1 Questions of the cahier 17, as decided (gate P1)

| Subject | Decision |
| --- | --- |
| Name of the JSON object | `identifier_uniqueness`, member of `ColumnSummary` (D5, D10) |
| Provenance | Structured `evidence`: sources, accuracies, SHA-256, rejected proofs, conflict |
| Access to a Dedup report | `report --dedup-report` (API `dedup_report`, key `report.dedup_report`); automatic discovery only of the colocated `<stem>.dedup.json` of the same source (D2) |
| Non identical exact proofs | Local `failed` / `evidence_conflict`; the Report is still generated (D8) |
| One distinct row | Not assessed: `U >= 2` for any conclusion (D4) |
| Deep trigger when `E` is limited | Planner criteria of 6.8 (D13 to D17): cost against value, deterministic budgets, a valid Dedup report spares the count |
| Near-unique | Fixed model decided on 24 October 2026, provisional constants (14) |
| Dedicated finding for residual conflicts | Not created; the raw finding links to the card |

Open at release: the constants of 14 are not calibrated on real files; with the defaults the automatic
count of the copies and the Scan's exact range do not meet (12.1, D13); the second-pass document moved from
revision 3 (published) to 4 together with the planner changes; `refine` does not promote an `id` to
`unique_id` from the analytical count (UID-001).

Follow-up for `tabalyst-studio` (nothing was edited there): no new page, so `src/navigation.ts` does
not change. The documentation site imports the edited pages (`docs/en/report/`, `docs/en/dedup/index.md`,
`docs/en/scan/deep.md`, `docs/en/reference/`) at the next release tag. The website advertises only
what the README documents, so any claim about the uniqueness after row deduplication waits for the
README line and the release.

## 14. Near-uniqueness (lot 9, UID-014)

Decision: ADR `2026-10-24-near-unique-reading`; model and constants decided by the maintainer on 24 October 2026
(provisional: no real file to calibrate them on). A near-unique reading is a **separate diagnostic**, stored in the
member `near_unique` of `identifier_uniqueness`. It is never a guarantee: the column is no `unique_id`, `unique` stays
`false`, `R_residual` and the finding `identifier.repetition` stay, and the Scan's classification is not touched (the
cahier 13 forbids a role from a percentage below 100 %, and forbids hiding a residual anomaly because it is rare).

**Model.** For `R = R_residual >= 1` among `U` distinct rows, in exact integers:

```text
T(U) = min( U // 100, isqrt(U), 1000 )        # relative, root, cap
signal = population_too_small      if U < 100
         near_unique               if R <= T(U)
         not_near_unique           otherwise
```

A fixed share is no definition of rarity: 1 % decides below 10,000 distinct rows, the square root from 10,000 to
1,000,000 and the cap above, so the tolerated share falls from 1 % to 0.1 % and less. Examples of `T`: 100 -> 1,
1,000 -> 10, 10,000 -> 100, 100,000 -> 316, 1,000,000 -> 1,000, 10,000,000 -> 1,000. Below 100 distinct rows one
repetition is already above 1 %, so there is no verdict (`population_too_small`, tolerance 0). `limiting_bound` names
the term that sets `T` (`relative`, `root`, `cap`; the first on a tie).

**When.** Only when the object is `complete` and `interpretation` is `repeated_between_distinct_records` (`R >= 1`,
`U >= 2`, no missing ID, exact `D` and `E`, complete scope). Everywhere else `near_unique` is `null`: nothing is
read from an estimate, a lower bound, a partial scope or contradictory measures (cahier 5.5). `U` is the number of
distinct rows, so the copies of rows (`E`) never count against the tolerance.

**JSON.** `near_unique`: `{"model_version": 1, "signal", "residual_repetitions", "distinct_records", "tolerance",
"limiting_bound"}`, integers and codes only. `NEAR_UNIQUE_VERSION` rises with any constant (`RELATIVE_DIVISOR`,
`ABSOLUTE_CAP`, `MIN_POPULATION` in `identifier_uniqueness/near_unique.py`) or formula; `RULE_VERSION` and
the Report `format_revision` (5, unpublished) do not move.

**Words.** `report_labels.py` (`UNIQUENESS_NEAR_*`), printed by the card `#uniqueness` of the column page under the
figures of case C: *Near-unique*, *Not near-unique* or *Too few distinct records to tell*, each with the figures, the
tolerance and its limiting term, and (for the first two) the sentence "This is a statistical reading, not a guarantee:
the repetitions stay listed and the column is not a unique ID." Not in the Summary of the dataset, not in the Findings,
not in the type name.

**Not done.** The number of distinct IDs that repeat and the concentration of the repetitions (cahier 13): after the
deduplication of the rows no per-ID frequency is held (the Scan's repeated values count raw occurrences, copies
included), so the reading uses the extra occurrences only. The constants are not calibrated on real files.
