# Identifier uniqueness (Unique ID plan, lot 0)

Status: contract written at lot 0 of the Unique ID plan (`tabalyst-gb`,
`KANBAN/05-PROGRESS/2026-10-23-tabalyst-unique-id-plan.md`); implemented by lots 1 to 4; P0
finalized at lot 5 (sections 12 and 13). P1 and P2 are not delivered.
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

With `M > 0` the exact `R_residual` is not computable (`E` may count copies of rows without an
ID; the Dedup report has no per-column count), so nothing is subtracted and no `unique` is
emitted (cahier 5.4, T09, T10). The `raw` block is then all `null` as well.

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
| `repeated_between_distinct_records` | `R_residual > 0` |
| `not_assessed` | everything else, with a `reason` |

`not_applicable` is not a stored status: the object is absent (3). The `reason` codes are stable
and listed here (D9). An empty `reason` (`null`) goes with `complete`.

| `reason` | With status | Meaning |
| --- | --- | --- |
| `missing_ids` | `limited` | `M > 0` (case E) |
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
- `evidence.id_cardinality.source`: `scan.values.cardinality` or `deep.exact_distinct`.
  `accuracy`: `exact`, `estimated` or `limited`; `domain`: `analytical` or `original`.
- `evidence.duplicate_rows.source`: `scan.records.duplicates` or `dedup.report`; `accuracy`:
  `exact`, `lower_bound` or `disabled`; `report` is `null` or
  `{"name", "format_revision", "settings_identity", "content_sha256", "origin"}` with `origin`
  `colocated` or `explicit`. No path outside the file name is stored.
- `evidence.rejected`: proofs that were read and refused, `[{"source", "reason"}]`, with the
  Dedup `reason` codes of 7. A refused proof is a diagnostic, never an error of the Report.
- `evidence.conflict`: `null`, or for `evidence_conflict` `{"measure": "duplicate_rows" | "id_cardinality",
  "values": [{"source", "value"}, ...]}` with the exact values that disagree.
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
2. `exact_distinct` of the second pass, only when `report_classification._distinct_count` would
   accept it (same Scan `base`, status `complete`) **and** `_analytical_stages_unchanged` (T19, T20).
   Lot 1 reuses both and does not copy them.
3. Otherwise `D` is unknown (`distinct_*`).

### 6.2 `E`, the extra copies of whole rows

1. `datasets[].records.duplicates.count` when `complete` (T12).
2. A validated Dedup report (7), when 1 is `limited` or `disabled` (T13).
3. P1 only: a Deep count of the copies (T33).

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
rule applies. A proof that is merely refused (7) is not a conflict.

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
| E | reason `missing_ids` | `identifier_uniqueness.missing_ids` |

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
| E | Missing IDs | Uniqueness after deduplication cannot be established: some records have no ID. |

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
    source: Literal["scan.values.cardinality", "deep.exact_distinct"]
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
| P1 | T33 and the planner; out of the P0 gate |

## 11. Open points kept for later lots

- Exact figure of `scope.complete` for multi-collection JSON with exclusions (P0 is conservative).
- Gate 4: the maintainer reads the five texts of 8.1.
- Whether `report --scan` finds the colocated Dedup report beside the scan document (7.1, lot 3).
- P1: `E_present_id` per column (cahier 5.4), near-unique signal (cahier 13).

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
- **Not measured:** the count-only mode and the 1 M, 5 M and 10 M rows runs belong to P1 (lots 6 to 8).
  No objective in seconds or in overhead is declared validated (cahier 15.3).

## 13. Conformance to the criteria of the cahier 18 (P0)

State after lot 5. Maintainer documentation, never published.

| # | Criterion | Evidence | State |
| --- | --- | --- | --- |
| 1 | No regression of `identifier/id` and `identifier/unique_id` | `test_the_scan_classification_and_the_raw_finding_do_not_change`, T21 to T24 tests; the classification tests of `tests/scan/` | Met |
| 2 | A repetition explained by a copy is not shown as an ID conflict between distinct rows | T02, T05, `test_the_porte_3_deliverable_100000_rows_500_copies`; case B of the Report | Met |
| 3 | The raw reality stays and the adjusted reading is separate | `identifier.repetition` unchanged (`test_a_repetition_is_never_an_automatic_error`); the `raw` and `after_row_deduplication` blocks | Met |
| 4 | No strict `true` from an estimated, limited, incomplete, inconsistent or foreign proof | T14, T18, T25, T28, `test_no_false_is_ever_emitted_without_a_demonstrated_repetition`, the properties of 15.2 | Met |
| 5 | The usual case, a Scan entirely exact, needs no new reading | T12 (`test_t12_the_report_does_not_read_the_source_again`), the measures of 12 | Met |
| 6 | A Dedup 0.7.1 report is used with identity validation, Dedup unchanged | T13, T15 to T17, T32, T34, `test_a_refusal_never_writes_the_dedup_report`; `src/tabalyst/dedup/` untouched | Met |
| 7 | The JSON is versioned, verifiable and consistent with the HTML | `format_revision` 5, schema, T29 (`test_t29_the_html_and_the_json_say_the_same`), `profile-changelog.md` | Met |
| 8 | The functional, invariant, security and non-regression tests pass | the suite (T31 exposure, properties, A1); T33 is P1 and stays skipped | Met for P0 |
| 9 | The documentation tells raw Unique ID from Unique after row deduplication and, later, near-unique | `read-report.md` (Column page), `findings.md`, `json-profile.md`, `profile-changelog.md`, the glossary, `dedup/index.md` | Met; near-unique is not available and is not described as such |
| 10 | The P1 and P2 requirements not delivered are identified and not described as available | the pages say that no second-pass analysis counts the copies and that near-uniqueness is not available; plan lots 6 to 9 | Met |

Not delivered and not described as available: the count-only mode of the Dedup engine and the Deep
analyzer of the copies of rows (UID-012), the Deep analytical cardinality (UID-013), the planner
criteria and the cache (UID-011), near-uniqueness (UID-014), the composite keys, the discovery of
candidates and the Smart or Explore recommendations (P2, UID-015).

Follow-up for `tabalyst-studio` (nothing was edited there): no new page, so `src/navigation.ts` does
not change. The documentation site imports the edited pages (`docs/en/report/`, `docs/en/dedup/index.md`,
`docs/en/scan/deep.md`, `docs/en/reference/`) at the next release tag. The website advertises only
what the README documents, so any claim about the uniqueness after row deduplication waits for the
README line and the release.
