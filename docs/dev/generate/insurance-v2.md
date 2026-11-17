# Insurance V2: reference datasets (contract)

Maintenance document, never published. Written at lot 0 of the Insurance V2 plan
(private `tabalyst-gb`, `KANBAN/05-PROGRESS/2026-11-16-tabalyst-generate-insurance-v2-plan.md`),
to be read at the gate before lot 1. Source requirements: the improvement report of
2026-11-16 (`KANBAN/04-SRS/2026-11-16-generate-insurance/generate-insurance.md`, 19 sections,
quoted below as "report §n"). Contracts it builds on: `computer.md` (the package),
`design.md`, `insurance-stress-cases.md` and the ADR
[`2026-11-11-generate-cross-column-rules`](../adr/2026-11-11-generate-cross-column-rules.md).

Decisions D1 to D14 and questions Q1 to Q5 are those of the plan. The maintainer settled Q1
to Q5 and the amendment of D7 on 2026-11-16 (section 12); D4 to D14 are confirmed or amended
at gate 0 by reading this contract and the ADR.

## 1. Purpose and scope

The Insurance package of `tabalyst generate` becomes a generator of **reference datasets**:
a configurable scenario (what is injected, how rare, why) plus a verifiable ground truth
(what was injected, what is really wrong, what is valid but unusual), for exploration, data
quality, sampling and machine learning.

In scope: scenario metadata and exact counts (lot 1), ground truth files (lot 2), rarity
levels and the `rare_events` profile (lot 3), an `extended` column profile (lots 4 and 6),
format and business rule catalogues (lots 5 and 6), quality profiles (lot 7), a relational
population (lots 8 and 9), distributions, missing mechanisms and drift (lots 10 to 12), ML
labels (lots 13 to 15), technical stress files (lot 16), ergonomics (lot 17) and the
documentation (lot 19).

Out of scope, assumed: evaluating rules between columns in Scan and Report (design, Lot 5);
any public scoring or comparison command (D3, the benchmark lives in
`tabalyst-lab/benchmarks/`, lot 18); real fraud or real data.

Principles that every lot keeps:

- **Default untouched.** Without a V2 option, every file of the package is identical byte for
  byte (section 2). New behavior is opt-in.
- **The clean file holds no exception to its rules** (ADR 2026-11-11). Defects and rule
  violations come from profiles, where they are logged. A valid boundary value is not an
  exception: it can be in the clean file.
- **Exact or refused.** An option that cannot be honored fails with a message; it is never
  ignored (project rule "no silently ignored options"). `count` fails when the eligible
  population is too small.
- **The truth is a file, not a comment.** Everything a method can be scored against is
  written, versioned and reproducible from `(seed, profile, rows, as_of_date, version)`.

## 2. Non-regression references

These are the references the lots must keep identical unless a lot says otherwise and
recomputes them with its justification (plan, "rappels propres à Generate"):

| Reference | Where | What it pins |
| --- | --- | --- |
| `V1_SHA256` (six files) and `V1_SUMMARY_SCENARIO_SHA256` | `tests/test_generate_insurance.py` | the four clean CSV, `dirty_realistic` CSV and its `changes.csv`, and the summary without its version members, for 3,000 rows and seed 42 |
| regression digests | `tests/test_generate_anomalies_regression.py` | the anomaly pass |
| stress profile | `tests/test_generate_insurance_stress.py` | `dirty_stress` (845 rows, 45 classes) |
| public demo | `examples/datasets/insurance-customers-100k.json` (`dirty_stress`, 100,000 rows, seed 20260916) and `examples/showcase/insurance-customers/` | the manifest pins the `sha256` of the CSV and of its `changes.csv`; `examples/tools/regenerate.py --fresh` must leave the demo unchanged |
| 3,000-row file of the case `sample-injected-errors` | `examples/datasets/insurance-customers.csv` | the file the case and `insurance-stress-cases.md` specify |
| column count | `FIELDS` (33 named fields) plus `filiale` | 34 columns, cited by the public pages and the benchmarks of `docs/dev/scan/benchmarks.md` |
| profile names | `anomaly_profiles` of `dataset.yaml` | exactly `dirty_realistic`, `dirty_stress`, `rule_breaks` |

`tests/test_generate_insurance_v2_contract.py` holds an enabled test that fails when the
column count or the profile names move (section 11).

A measured fact the lots must not "fix" silently: the existing profiles already overlap.
Operations with `rate` select their rows independently, so on `dirty_realistic` (3,000 rows)
618 events fall on 574 rows, 44 of them carrying several events
(`summary["events"] == summary["affected_rows"] + 44` in `test_generate_insurance.py`).
Only operations with an absolute `count` never share a row (`_choose_rows` claims the rows).
D7 is stated against this reality in section 4.3.

## 3. Vocabulary

Fixed vocabulary, in English (D14). Column names of the Insurance dataset stay French.
The public glossary (`docs/en/reference/glossary.md`) takes a term in the same change that
ships it, never earlier (rule 7 of `docs/en/`).

### 3.1 Categories (D9)

| `category` | Meaning | Example |
| --- | --- | --- |
| `format_variant` | different representation, acceptable | `Tremblay` / `TREMBLAY` |
| `format_invalid` | invalid syntax | `2026-13-40` |
| `semantic_invalid` | syntactically correct, forbidden alone | negative premium |
| `business_rule_violation` | fields individually valid, jointly incompatible | end before start |
| `contextual_invalid` | depends on a branch, a product or a period | a date in another branch's convention |
| `valid_atypical` | not a defect: valid but unusual, or on a rule boundary | indemnity exactly at the cap |

The first five are those of report §4. `valid_atypical` is added because report §3 (valid
boundary cases) and §15 (atypical but valid cases, ML20) need a place in the vocabulary; it
never labels a defect.

### 3.2 Truth kinds (D4)

`kind` says what a line of the truth file asserts (section 5.2):

| `kind` | Asserts |
| --- | --- |
| `injected` | an operation changed this cell (one line per line of `changes.csv`) |
| `net_difference` | the final cell differs from the clean cell (real difference) |
| `rule_violation` | the final row breaks a rule of `rules.json`, injected or not |
| `valid_atypical` | the cell is valid but a naive detector would flag it |
| `relational` | the anomaly shows only by comparing several rows (`group_id`) |
| `uncertain` | no incontestable binary label (for example two valid readings of a date) |

A cell can carry several lines, one per kind. A change that another change undoes (C03) has
`injected` lines and no `net_difference` line.

### 3.3 Rarity levels

The unit of a level is the **case** (one event, which may touch several rows: a key reused
on two contracts is one case on two rows). Nominal counts are those of report §2; the band
is what a scenario total may be and still carry the label.

| `rarity_level` | Nominal cases | Band of a scenario total |
| --- | ---: | --- |
| `frequent` | 5,000 | 1,000 or more |
| `uncommon` | 500 | 200 to 999 |
| `rare` | 100 | 75 to 199 |
| `very_rare` | 50 | 10 to 74 |
| `extremely_rare` | 5 | 2 to 9 |
| `single` | 1 | 1 |

The bands are chosen so that every count of report §3 falls in the level its text implies
(R02 5, R04 10, R05 20, R06 25, R07 50, R08 50, R09 100, R10 100, R11 250, R12 500).
Counts are absolute: they do not follow the file size (section 6.1 for the floor).

### 3.4 Severity

`info` (harmless variant or valid atypical), `minor` (cosmetic defect, data still usable),
`major` (wrong value that analysis must treat), `critical` (breaks a key, a legal limit or an
amount). A scenario declares its severity; the default derives from the category
(`format_variant` info, `format_invalid` minor, `semantic_invalid` and `contextual_invalid`
major, `business_rule_violation` major, `valid_atypical` info).

### 3.5 Identifiers and detection families

- `scenario_id`: one test case of a profile (`R07`, `F19`, `C07`). Several operations can
  serve one scenario (one per branch); the total of their counts is the scenario count.
  Pattern `[A-Z][A-Z0-9_]{0,15}`.
- `rule_id`: the verifiable rule a case is read against (`M17`, `F09`), as written in
  `rules.json`. A scenario names at most one rule per operation.
- `root_cause_id`: groups the effects of one incident (lot 7). Pattern
  `[a-z][a-z0-9_]{0,31}`, scoped to the profile.
- `group_id`: groups the rows of one relational case (duplicate key, near-identical identities).
- `expected_detection`: families of detector that should react, joined by `|`:
  `syntactic`, `domain` (outside a referential or a range), `cross_column`, `uniqueness`,
  `contextual` (needs a branch, product or period convention), `statistical`, or `none`
  (valid atypical). It describes the kind of check, not a tool.

## 4. Scenario engine (lot 1)

### 4.1 Operation metadata

`OPERATION_KEYS` in `generate_anomalies.py` gains the keys below, all optional, validated
once in `generate_definition.py` through the shared `operation_option_error`. An invalid
value fails at load time with the profile and operation index. Only the Insurance package
accepts them at first: a Computer or CRM operation that carries one is refused, never ignored.

| Key | Type | Rule |
| --- | --- | --- |
| `scenario_id` | string | pattern of 3.5; makes the profile a V2 profile |
| `rule_id` | string | pattern of 3.5 (`M17`, `F09`); must exist in the rules of the profile from lot 2 |
| `category` | string | one of 3.1 |
| `severity` | string | one of 3.4 |
| `rarity_level` | string | one of 3.3; the scenario total must fall in the band |
| `root_cause_id` | string | pattern of 3.5 |
| `requires` | list of column names | each must exist in the output profile (section 7); otherwise the profile is refused, naming the column and the output profile that provides it |
| `conflicts_with` | list of `scenario_id` | each must exist in the profile; symmetric |
| `can_overlap` | boolean | default `false` |
| `expected_detection` | string | tokens of 3.5 |

A profile is a **V2 profile** if any operation declares `scenario_id`. Then all of its
operations declare `scenario_id`, `category` and `severity`, and all of them use `count`
(no `rate`): a mix is refused. A profile without `scenario_id` is a **legacy profile** and
keeps today's exact behavior; any V2-only key on a legacy operation is refused.
`canonical_value` and `eligible_population` are not declared: they are captured (4.5) or
counted at application. `expected_effect` of report §15 is not an operation key: it is the
free `description` of a scenario in `manifest.json` (lot 2), never interpreted.

### 4.2 Counts (D6)

`count` is the **exact mode**: exactly `count` cases among the eligible population, or a
failure naming the operation and the eligible size (`_choose_rows` already raises). `rate`
is the **requested-rate mode**: an attempt on `round(rows * rate)` rows, with the applied
number reported; it exists only in legacy profiles.

The summary of a V2 profile reports three distinct numbers, which differ:

- `events`: operations applied (one line of events per application, as today);
- `distinct_changed_cells`: distinct `(row, column)` cells that received at least one event;
- `net_differences`: cells of the final file that differ from the clean file.

`changed_cells` keeps its present meaning (lines of `changes.csv`); the summary of a legacy
profile gains nothing (the scenario digest of `test_generate_insurance.py` pins it). Each
operation entry of a V2 summary adds `mode` (`exact`), `eligible_population` (rows where the
operation can change the clean file, already computed by `_choose_rows`) and `scenario_id`.

### 4.3 Overlap (D7, amended)

Defaults: **no overlap**. Two operations of a V2 profile never share a row. `can_overlap: true`
on both of two operations allows them to share a row, unless one lists the other in
`conflicts_with`. Sharing a cell is allowed on the same terms (C04, two successive
modifications of one field). A `duplicate_row` operation still erases the earlier events of
its row (existing rule, documented in `inject_anomalies`); a V2 profile may use it only
without `can_overlap`.

Amendment of D7 recorded in the ADR `2026-11-16-generate-overlap-opt-in`: the plan stated that
operations never overlap; in the engine only `count` operations are exclusive. V2 profiles use
`count` only, so the rule is true for them, and legacy profiles are not changed.

Selection stays sequential in profile order: appending a scenario to a profile never changes
the rows picked for the earlier ones; inserting one does. The profile order is part of the
profile.

Events of a row are journaled in application order (profile order, row operations last, as
today). With overlap, an operation reads the row as the previous one left it, so `before` of
the second event is the `after` of the first.

### 4.4 Random streams (D8)

- Legacy profiles keep their streams keyed by operation position
  (`f"{profile}:{index}"`).
- V2 profiles key the selection and value streams by scenario:
  `f"{profile}:{scenario_id}:{n}"`, where `n` is the 1-based rank of the operation inside its
  scenario. Adding a scenario or reordering scenarios leaves the values of the others alone.
- Generation of the clean file: the 34 base columns keep the single sequential stream of
  `InsuranceProvider.row()`; adding a draw there would shift every value. Every column added
  by an output profile (section 7) draws from its own stream
  `_stream(seed, dataset, column, "extended")` after the base row is built, using only the base
  row and its own draws. So the first 34 columns of an extended file are byte-identical to the
  default file for the same seed.
- Entities of the relational model (lot 8) have a stream per canonical identifier
  (`seed`, kind, id).

### 4.5 Canonical value

For each event, `inject_anomalies` records the **canonical value** of the cell: the meaning
of the clean cell, normalized by type: a date as ISO 8601, an amount as a plain decimal with
`.` and no unit, a text in NFC and trimmed, an identifier as in the clean file. For most
columns it equals the clean cell. It differs where the same string is read differently:
the clean Quebec cell `05-10-2026` has the canonical value `2026-10-05`, so a defect that
rewrites it as `10-05-2026` (valid in another convention, read as 10 May) keeps the intended
day in the truth. The canonical value is held in the truth file, never in `changes.csv` (D5).

## 5. Ground truth files (lot 2)

### 5.1 Names and publication

For a V2 profile of a dataset `<dataset>` (`insurance-combined`), the plan writes, beside the
clean CSV, the altered CSV, `changes.csv` and `summary.json` of today:

| File | Role |
| --- | --- |
| `<dataset>.<profile>.truth.csv` | ground truth (5.2) |
| `<dataset>.<profile>.rules.json` | rules and conventions (5.3) |
| `<dataset>.<profile>.metrics.json` | exact counts and distributions (5.4) |
| `<dataset>.<profile>.manifest.json` | version, seed, fingerprints, configuration (5.5) |
| `<dataset>.<profile>.latent.csv` | latent generator scores, ML profiles only (5.6, Q2) |

The names of report §15 (`insurance.clean.csv`, `insurance.dirty.csv`, ...) are not used: the
package names files `<dataset-id>.csv` and `<dataset-id>.<profile>.csv`, and that stays.
A legacy profile writes none of the new files, so its set of artifacts is unchanged.
The files are published atomically with the other artifacts by `_publish_artifacts`, with the
same collision protection (`--force` replaces, otherwise refuse), and appear in the
artifacts of `GeneratePlan` and `GenerateResult` (`generate_service.py`) with their own
`kind` (`truth`, `rules`, `metrics`, `manifest`, `latent`).

### 5.2 `truth.csv`

UTF-8, `\n`, comma, header, sorted by `row_number`, `column`, then the order of the kinds in
3.2. One line per (cell or row, kind). Columns, in this order:

| Column | Content |
| --- | --- |
| `truth_id` | 1-based sequence, stable for the same inputs |
| `kind` | 3.2 |
| `scenario_id` | scenario that produced it; empty for a violation that came from the base population |
| `rule_id` | rule it breaks or tests; empty for a pure format variant with no rule |
| `category` | 3.1 |
| `severity` | 3.4 |
| `rarity_level` | 3.3 of its scenario |
| `root_cause_id` | empty when no common cause |
| `group_id` | non-empty for `relational` lines and the rows of a multi-row case |
| `event_id` | `event_id` of `changes.csv` (the last one for `net_difference`); empty when no event |
| `row_number` | line of the altered file, header being line 1 (same as `changes.csv`) |
| `column` | the cell; empty when the line is about the whole row |
| `canonical_value` | 4.5; empty when the cell is meant to be absent |
| `expected_detection` | 3.5 |

Invariants (tested at lot 2): every line of `changes.csv` has exactly one `injected` line
with the same `event_id` and `column`; every cell where altered and clean differ has one
`net_difference` line; `truth_id` is unique; every `rule_id` exists in `rules.json`.

### 5.3 `rules.json`

```json
{"format": "tabalyst.generate.rules", "format_version": "0.2.0", "format_revision": 1,
 "dataset": "insurance-combined", "profile": "rare_events", "as_of_date": "2026-09-16",
 "conventions": {"date_format": {"principal": "%Y-%m-%d", "ontario": "%m-%d-%Y",
                                  "quebec": "%d-%m-%Y"}},
 "rules": [{"id": "M01", "family": "business", "title": "End after start",
            "columns": ["date_debut", "date_fin"], "category": "business_rule_violation",
            "severity": "major",
            "when": {"op": "not_empty", "column": "date_fin"},
            "assert": {"op": "gte", "left": "date_fin", "right": "date_debut", "as": "date"},
            "exceptions": [], "valid_boundaries": ["date_fin == date_debut"]}]}
```

Rules are **data, not code** (D10): a rule declares its columns, an optional `when`, an
`assert`, authorized `exceptions` (rules of the same grammar, for example a claim declared
after the contract ended for an event inside the coverage) and its `valid_boundaries`. The
grammar is a closed list of operators evaluated by a pure function: `eq`, `gt`, `gte`, `lt`,
`lte`, `between`, `in`, `not_in`, `regex`, `not_empty`, `empty`, `unique`, `implies`,
`and`, `or`, `not`, with operands that are columns or constants and a type (`as`: `date`,
`decimal`, `text`). The evaluator lives in `src/tabalyst/generate_rules.py` and is used by
the generator itself: before injecting, a V2 profile checks that the clean file satisfies
every rule of the profile (the principle of the ADR 2026-11-11), and a violation is
verifiable from `rules.json` alone (lot 6 test). Lot 2 writes the structure with the rules
its profile uses; lot 6 completes the catalogue M01 to M25 and fixes the final operator list
(a change of this list is a change of `format_revision`).

`conventions` carries what a reader needs to interpret the file: date format per branch,
number format, referentials (provinces, agencies per branch), periods when lot 12 adds them.

### 5.4 `metrics.json`

`format: tabalyst.generate.metrics`. Members: `dataset`, `profile`, `rows` (total and per
branch), `counts` (4.2 numbers), `scenarios` (one entry per `scenario_id`: `rarity_level`,
`requested_cases`, `applied_cases`, `rows_touched`, `eligible_population`, `category`,
`severity`), `rules` (violations in the final file per `rule_id`), `categories` (cases per
category), `kinds` (truth lines per kind), and `absence_probability` (6.3). Lot 7 adds
`root_causes`; lot 10 adds the distribution statistics (quantiles, shares per category and
branch) a sampling method is compared with. Every number is computed from the files written,
never copied from a configuration.

### 5.5 `manifest.json`

`format: tabalyst.generate.manifest`. Members: `tabalyst_version`, `generation_version` (an
integer of the V2 logic, raised whenever the bytes of a V2 output change for the same
inputs, with the reason in `docs/dev/generate/insurance-v2-changelog.md`, created at lot 2),
`seed`,
`as_of_date`, `rows`, `profile`, `output_profile`, `package_version`, `definition_id`,
`scenarios` (id, description, operations, expected counts), `files` (role, name, bytes,
`sha256` of every other file of the run, never of the manifest itself), `truth_columns`
(the columns of 5.2, so a reader of `truth.csv` finds its format here).

### 5.6 Latent scores (Q2)

`risque_sinistre` and any score that would make a prediction trivial are written to
`<dataset>.<profile>.latent.csv` (a row key and the scores), listed in the manifest with
`"role": "latent"` and the note that it is not an input variable. They are never columns of
the main CSV (D11). Only the ML profiles (lots 13 to 15) write it.

### 5.7 Formats and versions

The four JSON files carry `format`, `format_version` and `format_revision`, in the family of
Report, Scan, Inspect and Dedup: `0.2.0`, revision 1 at their first appearance. The JSON
Schemas live in `src/tabalyst/schemas/` (`tabalyst.generate.rules.schema.json`, ...), are
generated from Pydantic models like the Dedup ones and a test fails when a committed schema
is stale. A change of structure or meaning raises `format_revision` and is written in
`docs/dev/generate/insurance-v2-changelog.md`. The format is experimental during the beta:
breaking changes are allowed, no migration is provided. The existing `format_version: "0.1.0"`
of the package and of `summary.json` is unrelated and unchanged.

## 6. Rarity and `rare_events` (lot 3)

### 6.1 Floor on the number of rows (Q1)

A V2 profile declares `min_rows`. `rare_events` declares `100000`: below, the command fails
naming the profile, the floor and the requested rows (a 500-case scenario at 0.5 percent of
the file is the most frequent rarity worth the name). The existing rule stays: a count above
the number of rows, or above the eligible population, fails. A floor is validated once in
`generate_definition.py`; it is neither overridable nor ignored.

### 6.2 `rare_events`

Applies to the 34 columns of the default output profile; `insurance-combined` only. One
scenario per case, with the counts of report §3:

| Scenario | Case | Cases | Level | Built with |
| --- | --- | ---: | --- | --- |
| R01 | `id_contrat` reused on two contracts | 1 (2 rows) | `single` | new row-pair operation, `relational` truth |
| R02 | future birth date | 5 | `extremely_rare` | `replace` or a new future-date value |
| R05 | annual premium multiplied by 100 | 20 | `very_rare` | new `format` value |
| R06 | date in the wrong convention for the branch | 25 | `very_rare` | existing date conversions, `contextual_invalid` |
| R07 | postal code incompatible with the province | 50 | `very_rare` | a pool-aware replacement (new) |
| R08 | contract ending before it starts | 50 | `very_rare` | `swap` of the two dates |
| R10 | amount replaced by text | 100 | `rare` | `replace` |
| R11 | unknown `statut_contrat` | 250 | `uncommon` | `replace` |
| R12 | agency of another branch | 500 | `uncommon` | `replace` with `when` per branch |

R03, R04 and R09 need columns of the extended profile and arrive at lot 6. Every scenario
that cannot be built with the existing operations adds an operation kind or a `format` value,
validated in `generate_definition.py` with one test per value (the pattern of the G1 and G1b
lots). R01 reuses a key with the clean row of the first occurrence as `canonical_value` of the
second.

Valid boundary cases (report §3) are `valid_atypical` truth lines. With 34 columns they are
rows whose values sit on a rule boundary: a customer exactly 18 at the start of the contract,
`date_fin` equal to `date_debut`, `date_modification` equal to `date_creation`, a premium at
the bound of its product. They are valid, so they may be in the clean file or written by a
`replace` with a boundary value; the choice is the lot's, and the truth line is the same. The
indemnity at the cap (9,999.99 / 10,000.00 valid, 10,000.01 invalid) arrives with
`montant_couverture` at lot 4.

### 6.3 Exact probability of absence

For a scenario of `c` single-row cases in a file of `N` rows, a uniform sample of `n` rows
without replacement holds none of them with probability

`P(none) = C(N - c, n) / C(N, n) = product for i in 0..c-1 of (N - n - i) / (N - i)`

computed exactly (`fractions.Fraction`) and stored as the correctly rounded float. It is
recomputed for the actual `N` and `c`, never copied from a table. `metrics.json` holds it for
`n` in 500, 1,000, 5,000, 10,000 and 50,000 per scenario; a scenario whose cases span several
rows stores `null` with `"reason": "multi_row_case"` (lot 9 may extend it).

Check values (computed with the formula, `n = 5,000`):

| Cases `c` | N = 500,000 (report §2) | N = 275,000 (package default) |
| ---: | ---: | ---: |
| 500 | 0.655 % | 0.0103 % |
| 100 | 36.60 % | 15.96 % |
| 50 | 60.50 % | 39.95 % |
| 5 | 95.10 % | 91.23 % |
| 1 | 99.00 % | 98.18 % |

The report's table (0.66 %, 36.6 %, 60.5 %, 95.1 %, 99 %) is exact for 500,000 rows and is not
valid for the default size, which is why it is computed.

## 7. Column profiles (lots 4 and 6)

Selected with the existing option `--output-profile` (Q4), whose value `compact` already
means a column subset for Computer; an unknown value for a package fails.

| Profile | Columns | Content |
| --- | ---: | --- |
| default (no option) | 34 | today, byte-identical (D1) |
| `extended` | 44 | the 34, then 10 appended columns |
| `complete` | 48 | `extended` plus tranche B (lot 6), then later additions |

`extended` is frozen when it is published: its bytes for a given seed never change afterwards.
New columns go in a later profile, which is why tranche B is `complete`.

`extended` appends, after `filiale` (the last column of the combined file): `date_sinistre`,
`montant_couverture`, `franchise`, `montant_indemnise`, `date_resiliation`, `statut_paiement`,
`canal_acquisition`, `courtier_id`, `produit_code`, `nombre_reclamations` (report §19).
Tranche B: `taux_remboursement`, `consentement_communication`, `gestionnaire_id`,
`segment_client`. Later: `date_dernier_paiement`, `montant_verse`, `motif_resiliation`,
`date_observation`, `version_source`, `source_system`.

Rules of the clean file (strict, no exception, evaluable by `generate_rules.py`); lot 4 fixes
the formulas, the invariants are:

- `date_sinistre` <= `date_reclamation`; `date_reclamation` stays the declaration (a claim
  declared after the end of the contract is valid when `date_sinistre` is inside the
  coverage, an exception of the rule M08 declared in `rules.json`, not hard-coded);
- `montant_indemnise` >= 0 and <= min(`montant_couverture`, claim amount minus `franchise`);
- `date_resiliation` present if and only if `statut_contrat` is `résilié`, and between
  `date_debut` and the end of the contract;
- `nombre_reclamations` >= 1 when `date_reclamation` is present;
- structural absence: `montant_indemnise` and `date_sinistre` are empty without a claim, and
  the rule says so (a structurally normal empty cell, report §10; the reason of an empty
  cell is the subject of lot 11).

A column is added to `extended` only with the rule that constrains it, the scenario that
breaks it and the test of both.

Open at lot 4: the three branch files (`insurance-principal.csv`, ...) have no `filiale`
column, so `extended` columns are derived in the combined file only, or per branch with the
branch known; the lot decides and records it here.

## 8. Relational model (lots 8 and 9, D2)

One in-memory population model (clients, households, brokers, agencies, contracts, renewals,
claims, payments) feeds two outputs: the flattened multi-contract CSV and the four files
`clients.csv`, `contrats.csv`, `reclamations.csv`, `paiements.csv`. Bounded memory for 500,000
rows, deterministic streams per entity (4.4), no second reading of an output. Truth is per
table, plus `relational` lines (G09, G10, M22). The model, its limits and the
cardinalities are written at the gate before lot 8; this section only fixes that there is
one model with two projections, never two generators. See the ADR
`2026-11-16-generate-relational-population-model`.

## 9. Documentation, versions and languages

- Public pages (Q5): `docs/en/generate/insurance.md` stays the overview; each lot that ships a
  subject adds one self-contained page (`insurance-ground-truth.md` at lot 2,
  `insurance-rare-events.md` at lot 3, then quality, ML, relational). The reference CLI page and
  the glossary are updated in the same change as the behavior. Every added page needs an entry
  in the navigation of `tabalyst-studio` (`src/navigation.ts`): mention it, do not edit it.
- Versions (Q3): the work is released as **0.7.8 after phase 2** (lot 7, gate P2), then per
  phase at gates P4 and final. Until a release, pages of `docs/en/` describe the branch; they
  are published only with the release that contains the behavior (rule 7 of `docs/en/`).
  Application versions follow PEP 440; the format versions are those of 5.7.
- Languages (D14): existing French columns kept; truth fields, rule ids, classes, kinds and
  report labels in English; public pages in English only.
- Private companions: the card
  `../tabalyst-gb/KANBAN/08-DOCS/2026-11-11-generate-regles-entre-colonnes.md` and the plan
  in `tabalyst-gb` hold progress, never this repository.

## 10. Lot map

| Lot | Delivers | Sections |
| --- | --- | --- |
| 0 | this contract, ADR, contract tests | all |
| 1 | operation metadata, overlap, counts, canonical capture | 4 |
| 2 | truth, rules, metrics, manifest, schemas, CLI and service | 5 |
| 3 | rarity levels, `min_rows`, `rare_events`, probability | 3.3, 6 |
| 4 | `extended` profile | 7 |
| 5 | format catalogue F01 to F22 | 3.1, 5.3 |
| 6 | rules M01 to M25, tranche B, `complete` | 5.3, 7 |
| 7 | quality profiles, interactions, `root_cause_id` | 3.5, 5.4 |
| 8 to 9 | population model, relational outputs | 8 |
| 10 to 12 | distributions, absence mechanisms, drift | 5.4, 5.3 |
| 13 to 15 | ML labels, leakage, splits, latent file | 5.6 |
| 16 | technical stress, malformed files in separate files (D13) | none yet |
| 17 | catalogue, several profiles, ergonomics | 9 |
| 18 | benchmark in `tabalyst-lab` (D3) | none (outside) |
| 19 | conformity, documentation, release | 9 |

## 11. Contract tests

`tests/test_generate_insurance_v2_contract.py` holds one skeleton per behavior of lots 1 to 3
(40 tests: 17 for lot 1, 12 for lot 2, 11 for lot 3), marked `insurance_v2_lot("1" | "2" | "3")`. They are skipped until the lot is
listed in `ENABLED_LOTS` of the same module, which the lot adds when it starts (the pattern of
`dedup_lot` and `report_lot`), so the suite stays green between lots. Each test name states
the expected behavior; its docstring points to the section here. The enabled test of lot 0
fails if the column count of the default profile, the names of the three legacy profiles or
the references of section 2 move.

## 12. Amendments to the plan accepted at gate 0

- **D7**: only `count` operations are exclusive today; V2 profiles use `count` only and the
  no-overlap default holds for them; legacy profiles keep their overlapping `rate` selection
  (4.3).
- **D9**: sixth category `valid_atypical` for non-defects (3.1).
- **D8**: the base row of Insurance cannot take a new draw; added columns use streams of their
  own and the first 34 columns stay identical (4.4).
- **Q1**: `min_rows` per V2 profile, 100,000 for `rare_events` (6.1).
- **Q2**: `.latent.csv` shipped beside the files, ML profiles only (5.6).
- **Q3**: 0.7.8 after phase 2, then per phase (9).
- **Q4**: `--output-profile extended`, later `complete` (7).
- **Q5**: one page per subject (9).
- **Names**: the dataset is `insurance-combined`, so files are `insurance-combined.<profile>.*`.
- **`insurance-stress-cases.md` section 6**, decision 1 ("Insurance keeps its 34 columns") is
  kept for the default profile and amended by an opt-in profile (ADR
  `2026-11-16-generate-extended-columns-opt-in`).

## 13. Open points, to settle at their gate

- Gate 2: final column order of `truth.csv`, final operator list of `rules.json` (lot 6 may
  still raise `format_revision`).
- Lot 3: the operations missing for R01, R05 and R07 (names and tests), the boundary cases kept.
- Lot 4: exact formulas of the extended rules and the share of boundary values in the clean file.
- Lot 8: the model and its memory bound (gate P2).
- Whether legacy profiles should get a truth file on request (not planned: their set of
  artifacts is a non-regression reference).
