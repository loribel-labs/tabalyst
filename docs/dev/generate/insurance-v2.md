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
| `description` | string | one line of 1 to 500 characters, shared by the operations of a scenario, copied to `manifest.json` (added at lot 2) |

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

### 4.6 What lot 1 fixed

Written when lot 1 was implemented; where it differs from 4.1 to 4.5 this is the behavior.

- **Modules.** `generate_scenarios.py` (the ten keys, `scenario_option_error` for one operation,
  `profile_scenario_error` for a whole profile, `conflict_map`), `generate_rarity.py` (only the
  bands and `band_of` / `level_of`; lot 3 adds the probability) and `generate_canonical.py`
  (`canonical_text`, `canonical_decimal`, `canonical_date`). `operation_option_error` calls
  `scenario_option_error` first, so every caller shares the rule.
- **Required keys.** `severity` is required with `scenario_id` (4.1 wins over the default table
  of 3.4, which stays a vocabulary for authors). The operations of one scenario declare the same
  `category`, `severity`, `rarity_level`, `rule_id`, `root_cause_id` and `expected_detection`,
  otherwise the profile is refused; `requires`, `conflicts_with` and `can_overlap` may differ.
- **Refusals.** A scenario key without `scenario_id`, a mix of scenario and legacy operations,
  `rate` with `scenario_id`, a `conflicts_with` that names an unknown scenario or its own,
  `duplicate_row` with `can_overlap`, a `requires` column the target dataset lacks (the message
  says which output profile provides it, table `PROVIDING_PROFILES`, lot 4 owns its content) and
  a `rarity_level` whose band does not hold the scenario total. At load the message starts with
  `profile <id>: operations[<n>]:`. The engine repeats the checks for a direct caller. A Computer
  or CRM profile that carries a scenario key is refused (`scenarios` is true for the Insurance
  package only). `rule_id` is checked against `rules.json` at lot 2, when that file exists;
  only its pattern is checked here.
- **Selection.** `_choose_rows` keeps three kinds of claim map (rows taken by an operation that
  cannot overlap, rows taken by any operation, one map per scenario named in a conflict). A
  legacy profile behaves as before: no operation overlaps. Streams of a scenario profile are
  keyed `profile:scenario_id:rank`, so appending a scenario leaves the rows and the values of
  the earlier ones alone (tested). The streams do not depend on the position, but picks follow
  the profile order, so inserting or reordering scenarios can move the rows of the others.
- **Eligibility is measured on the clean row.** An operation that shares a row is picked among
  the rows it can change in the clean file. If an earlier overlapping operation then leaves a
  row it cannot change (a `when` that no longer holds, a replacement by the value already
  there), the run fails naming the operation instead of applying fewer cases (exact or refused).
  An author chains operations that stay applicable to the intermediate value (C04: `suffix_x`
  then `upper`, or two `swap` of the same pair for C03).
- **One scenario, one case per row.** The operations of one scenario never share a row with
  each other even when both declare `can_overlap` (a scenario total counts cases, and lot 3
  derives the probability of absence from distinct rows).
- **Empty lists.** `requires: []` and `conflicts_with: []` are accepted and mean nothing.
- **Canonical failures.** `insurance_canonical` raises ValueError for a date whose row has no
  known `filiale` or does not follow its convention: a guessed value in the truth would be
  worse than a refusal.
- **Summary.** A scenario profile adds `distinct_changed_cells` and `net_differences` at the
  root and `scenario_id`, `mode` and `eligible_population` to each operation; the summary of a
  legacy profile is unchanged. `eligible_population` is the number of rows the operation can
  change in the clean file, before any claim.
- **Canonical value.** `inject_anomalies(..., on_event=, canonical=)`: `on_event` receives one
  `AnomalyEvent` per line of `changes.csv` (`event_id`, `row_number`, `operation_index`,
  `column`, `before`, `after`, `canonical_value`) and changes no file; `canonical(column,
  clean value, clean row)` computes the value, the clean cell itself when absent. Insurance
  provides `generate_insurance.insurance_canonical`: a date is read with the convention of the
  row's `filiale` and written as ISO, an amount is a plain decimal, an identifier stays as it
  is, any other text is NFC and trimmed. The service does not pass them yet: lot 2 wires them
  to `truth.csv`.

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

### 5.6 Machine learning targets, labels, leakage scenarios, and partitions (lots 13 & 14)

#### 5.6.1 Machine learning labels (`ml_labels.csv`)

`<dataset>.<profile>.ml_labels.csv` is generated for ML scenario profiles (such as `ml_fraud_imbalanced` and `ml_leakage_test`).
It isolates supervised learning targets and latent risk probabilities from input feature files.

Base columns (lot 13, for fraud-specific profiles):
- `row_number`: 1-based physical row number in the dataset CSV (matching `truth.csv`).
- `id_contrat`: Primary contract key for dataset joins.
- `is_fraud`: True ground-truth binary label (`1` = confirmed fraud, `0` = non-fraud).
- `observed_label`: Observed operational label in IT systems (`"1"` = flagged, `"0"` = cleared, empty = unresolved/pending).
- `confirmation_date`: ISO date YYYY-MM-DD of investigation conclusion or error recording, empty if unresolved.
- `fraud_type`: Synthetic fraud typology: `phantom_claim`, `inflated_claim`, `collusion`, `organized_fraud`, or empty.
- `latent_probability`: Continuous latent risk probability in [0.0, 1.0] capturing realistic statistical overlap.

Extended prediction target columns (lot 14, for extended ML profiles):
- `future_claim` (ML09): binary future claim occurrence in `{0, 1}` (~10% positive incidence).
- `cout_sinistre` (ML10): claim cost regression in floating-point euros/dollars, strictly `0.00` when `future_claim == 0` and positive amount when `1`.
- `renouvellement` & `date_renouvellement` (ML11): retention/renewal binary indicator (> 60% realistic retention rate) and next policy term effective date (empty if not renewed).
- `risque_categorie` (ML12): multiclass actuarial rating across 4 classes: `faible`, `moyen`, `eleve`, `tres_eleve`.
- `historique_sinistres` & `anciennete_client`: upstream calculated antecedent variables.
- `score_risque_interne`: latent credit/actuarial rating in `[100.0, 900.0]`.

It is registered in `manifest.json` with role `"ml_labels"`.
The JSON schema `src/tabalyst/schemas/tabalyst.generate.ml_labels.schema.json` formalizes the format
`tabalyst.generate.ml_labels`, version `0.2.0`, revision 1.

#### 5.6.2 Leakage-free dataset partitioning (`splits.csv`)

`<dataset>.<profile>.splits.csv` is generated alongside `ml_labels.csv` for ML scenario profiles.
It contains 6 standard columns:
- `row_number`: 1-based physical row number in the dataset CSV.
- `id_contrat`: Contract identifier.
- `id_client`: Customer identifier.
- `split_client`: Random grouping partition by customer (`train` ~70%, `val` ~15%, `test` ~15%) with 0 shared clients between folds, preventing cross-contract customer data leakage.
- `split_temporal`: Temporal chronological partition based on policy inception (`train` < 2023-01-01, `val` 2023-01-01 to 2024-06-30, `test` > 2024-06-30).
- `resampled_train_only`: Boolean flag indicating whether a synthetic rebalancing/resampling operation applies strictly to `train`, guaranteeing that `val` and `test` preserve their clean, natural distribution.

It is registered in `manifest.json` with role `"splits"`.
The JSON schema `src/tabalyst/schemas/tabalyst.generate.splits.schema.json` formalizes the format
`tabalyst.generate.splits`, version `0.2.0`, revision 1.
Partition counts and fold shares are serialized in `metrics.json` under `splits` (`SplitMetrics`).

Latent scores and raw risk generators that would make prediction trivial remain excluded from input feature tables (D11).

#### 5.6.3 Latent generator variables (`latent.csv`) (lot 15)

`<dataset>.<profile>.latent.csv` is produced alongside `ml_labels.csv` and `splits.csv` for ML scenario profiles (`ml_fraud_imbalanced`, `ml_leakage_test`, `ml_multitask`).
It isolates the unobserved, uncorrupted generator scores and ground-truth probabilities (SRS §8, Contract §5.6, D11, Q2):
- `row_number`: 1-based physical row number in the dataset CSV.
- `id_contrat`: Contract identifier for entity joins.
- `id_client`: Customer identifier.
- `latent_fraud_probability`: Continuous uncorrupted latent probability of fraud in `[0.0, 1.0]`.
- `latent_claim_probability`: Continuous latent probability of loss claim occurrence (`risque_sinistre`) in `[0.0, 1.0]`.
- `latent_claim_cost`: Theoretical expected loss amount in currency units.
- `latent_renewal_probability`: Continuous latent propensity for policy renewal in `[0.0, 1.0]`.
- `latent_risk_score`: Calibrated composite actuarial risk rating score in `[100.0, 900.0]`.
- `latent_churn_risk`: Continuous latent risk of customer churn in `[0.0, 1.0]` (strictly `1.0 - latent_renewal_probability`).

Strict exclusion principle (D11): none of these latent variables or generator scores are exposed in the input feature table `insurance-combined.csv`.
It is registered in `manifest.json` under role `"latent"`.
The JSON schema `src/tabalyst/schemas/tabalyst.generate.latent.schema.json` formalizes the format `tabalyst.generate.latent`, version `0.2.0`, revision 1.
Aggregated distributions and averages across all latent variables are recorded in `metrics.json` under `latent` (`LatentMetrics`).

#### 5.6.4 Final ML profiles assembly (lot 15)

The Insurance package delivers three finalized machine learning scenario profiles in `dataset.yaml`:
1. `ml_fraud_imbalanced`: imbalanced binary classification, rare typologies (1%, 0.1%, 0.01%), label noise, and delayed investigations.
2. `ml_leakage_test`: intentional leakage scenarios, post-claim temporal leakage, shortcuts, branch imbalances, and segment-conditioned missingness.
3. `ml_multitask`: comprehensive multi-task benchmark combining synthetic fraud, future claim occurrence, claim cost regression, renewal, and actuarial rating across 15 extended columns in `ml_labels.csv`.
All three profiles default to `--output-profile extended` (44 columns on `insurance-combined.csv`) and enforce a minimum floor `min_rows: 10000`.

### 5.7 Formats and versions

The four JSON files carry `format`, `format_version` and `format_revision`, in the family of
Report, Scan, Inspect and Dedup: `0.2.0`, revision 1 at their first appearance. The JSON
Schemas live in `src/tabalyst/schemas/` (`tabalyst.generate.rules.schema.json`, ...), are
generated from Pydantic models like the Dedup ones and a test fails when a committed schema
is stale. A change of structure or meaning raises `format_revision` and is written in
`docs/dev/generate/insurance-v2-changelog.md`. The format is experimental during the beta:
breaking changes are allowed, no migration is provided. The existing `format_version: "0.1.0"`
of the package and of `summary.json` is unrelated and unchanged.

### 5.8 What lot 2 fixed

Written when lot 2 was implemented; where it differs from 5.1 to 5.7 this is the behavior.

- **Modules.** `generate_rules.py` (Pydantic grammar of the rules, `RuleCatalogue`,
  `RulesDocument`, the pure `holds` and the streaming `RuleEvaluator`) and `generate_truth.py`
  (`build_truth`, `truth.csv`, the models of `metrics.json` and `manifest.json`, the schemas).
  `generate_service.py` adds the kinds `truth`, `rules`, `metrics` and `manifest` (in that
  order, after `summary`) for a scenario profile and passes `on_event` and
  `insurance_canonical` to the injection. `GenerateResult.artifacts` gives every file with its
  kind.
- **Where the rules live (D10).** A package declares a catalogue with `rules: rules.yaml` in
  `dataset.yaml` (a protected input). Only Insurance may: another package that declares one is
  refused. The catalogue holds `conventions` and the rules; its date formats must equal those of
  the branches (`BRANCHES`). The rules of a profile are those its operations name with
  `rule_id`; an unknown `rule_id` is refused at load. `rules.json` holds those rules, in
  catalogue order. A profile cannot yet list a rule it does not target (lot 6 decides).
- **First catalogue**, with the numbering of report 5, all true of the clean file (checked on
  275,000 rows): M01 end on or after start, M02 modification on or after creation, M03 birth
  before start, M04 birth from 1900-01-01 to `as_of_date`, M14 premium above zero, M21
  `id_contrat` unique, M23 known `type_contrat` and `statut_contrat`. Lot 6 completes M01 to
  M25.
- **Grammar.** Operand: a bare string is a column, `{"value": text}` a constant (ISO for a
  date), `{"param": "as_of_date"}` the date of the document. `as`: `date`, `decimal` (plain,
  `.`), `text` (default). `between` and the value tests name a `column`; `in` and `not_in` hold
  literal `values`; `unique` takes `columns` and stands alone as the `assert`. Each rule adds
  `detection` (tokens of 3.5 without `none`) and `columns` lists exactly the columns its
  expressions read. `family` is `business`, `format` or `domain`.
- **Three-valued logic.** A test of a value is unknown when the cell is empty or does not read
  as its type (a date must be written exactly in the format of its row's branch). `and`, `or`,
  `not` and `implies` follow Kleene logic; `not_empty` and `empty` are always known. A row
  breaks a rule only when `when` is true (or absent), no exception is true and `assert` is
  false. So a format defect is never also a business violation (`format_vs_business`, report 4):
  a Quebec date rewritten as ISO leaves M01 unknown on its row. `unique` ignores a key with an
  empty part.
- **Targets.** A scenario profile needs the catalogue and targets only datasets that have its
  `branch_column` (`filiale`), so `insurance-combined`; a branch file is refused (the open
  point of section 7 stays for lot 4). The columns of the rules it names must exist there.
- **One reading.** The clean file is checked in the same reading that builds the truth (clean
  and altered read together, after the injection and before publication), not in a reading of
  its own: the result is the same (a violation stops the run, nothing is published) at one
  reading fewer. The message names the rule, its title and the row.
- **Truth lines.** `injected` and `net_difference` lines carry the metadata of their scenario
  (for `net_difference`, the last event of the cell, whose `event_id` they repeat).
  A `rule_violation` line has an empty `column` and `canonical_value`, the `rule_id`,
  `category`, `severity` and `expected_detection` (its `detection`) of the rule, and the
  scenario, rarity, cause and `event_id` of the last event of the row that touched a column of
  the rule (empty when none did). A repeated key (`unique`) gives a line on each row of the
  group, `group_id` `<rule>-<first row>`, attributed to the row that repeats it. Lines of one
  cell sort by kind, then `event_id`, then `rule_id`; row lines (empty column) come first.
- **Self-check.** `metrics.counts` is recounted from the truth and must equal the summary;
  a cell that differs without an event fails the run.
- **Metrics.** `rows.by_branch` is sorted by name; `scenarios` keeps profile order;
  `eligible_population` of a scenario is the sum over its operations; `applied_cases` and
  `rows_touched` are equal while a case is one row; `rules` lists every rule of `rules.json`
  (0 included), `categories` all six categories and `kinds` all six kinds, so the shape never
  depends on the run. `absence_probability` is lot 3's.
- **Manifest.** Adds `dataset`; `output_profile` is `default` until lot 4; `files` lists every
  other artifact of the plan, in plan order, by name (never a directory), so the bytes do not
  depend on the output directory. `generation_version` is 1.
- **JSON.** Members in declared order, two-space indent, UTF-8, `\n`; `rules.json` omits an
  absent `when`. Schemas: `tabalyst.generate.{rules,metrics,manifest}.schema.json`, generated by
  `generate_truth.generate_schemas()`; a contract test fails when a committed one is stale.
- **Memory.** The truth lines are held in memory (they follow the counts); a `unique` rule
  keeps one key per row where it applies, which matters only for a profile that names M21 at
  millions of rows.

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

### 6.4 What lot 3 fixed

Written when lot 3 was implemented; where it differs from 6.1 to 6.3 this is the behavior.

- **Modules.** `generate_rarity.py` gains `SAMPLE_SIZES` and `absence_probability(rows, cases,
  sample)`; `generate_anomalies.py` the kinds `reuse_value` and `copy_column`
  (`SCENARIO_KINDS`), the `format` values `times_100` and `date_plus_century`, and
  `CONTEXTUAL_VALUES` (`postal_other_province`) with `inject_anomalies(contextual=)`;
  `generate_insurance.insurance_contextual(references)` supplies the row-aware values;
  `generate_truth.py` the `relational` and `valid_atypical` lines and `absence_probability`;
  ADR `2026-11-17-generate-rare-events-profile`.
- **Floor.** `min_rows` is a key of the profile (scenario profiles only, a whole number at least
  the largest count of the profile). `build_generate_plan` refuses fewer rows than the floor on
  a target: `Profile rare_events needs at least 100,000 rows on insurance-combined (below that
  its rare cases are not rare); 99,999 requested.` The refusal of a count above the rows or the
  eligible population stays as it was.
- **The profile `rare_events`.** In the package, 34 columns, 19 operations in 11 scenarios
  (`insurance-combined` only). As built:

  | Scenario | Cases | Level | Operations | Rule |
  | --- | ---: | --- | --- | --- |
  | R01 | 1 (2 rows) | `single` | `reuse_value` on `id_contrat` | M21 |
  | R02 | 5 | `extremely_rare` | `format date_plus_century` on `date_naissance` | M04 |
  | R05 | 20 | `very_rare` | `format times_100` on `prime_annuelle` | |
  | R06 | 25 | `very_rare` | `date_debut` in another branch's convention: `date_dmy` (principal 10), `date_mdy_iso` (ontario 8), `date_iso` (quebec 7) | |
  | R07 | 50 | `very_rare` | `format postal_other_province` on `code_postal`, `requires: [province_code]` | |
  | R08 | 50 | `very_rare` | `swap` of `date_debut` and `date_fin` | M01 |
  | R10 | 100 | `rare` | `replace` of `prime_annuelle` by `N/A` (50), `inconnu` (30), `à venir` (20) | |
  | R11 | 250 | `uncommon` | `replace` of `statut_contrat` by `inconnu` (100), `en attente` (80), `annulé` (70) | M23 |
  | R12 | 500 | `uncommon` | `replace` of `agence_code` by an agency of another branch, per branch (300, 100, 100) | |
  | B01 | 100 | `rare` | `copy_column` `date_debut` into `date_fin` where `statut_contrat` is `expiré` | M01 |
  | B02 | 100 | `rare` | `copy_column` `date_creation` into `date_modification` where there is no claim | M02 |

  Categories: R01, R07, R08 and R12 `business_rule_violation`; R02, R05 and R11
  `semantic_invalid`; R06 `contextual_invalid`; R10 `format_invalid`; B01 and B02
  `valid_atypical`. R07 and R12 name no rule: the catalogue has none for them until lot 6.
  R12 uses `replace` per branch as 6.2 said (three constants, one per branch); R07 is
  pool-aware because a constant postal code would be one value repeated 50 times.
- **R01.** `reuse_value` takes the clean value of one of the 1,000 rows before the changed one,
  so the second occurrence is near the first like a double entry. `canonical_value` of the
  changed cell stays its own clean key (what the truth must restore), not the first
  occurrence's: the relation is carried by the two `relational` lines, `group_id`
  `R01-<first row>`, one per row, the first without `event_id`. M21 also reports the two rows as
  `rule_violation` lines of its own group `M21-<first row>`; the kinds differ on purpose.
- **Valid boundary cases.** B01 and B02 are real `valid_atypical` scenarios with severity `info`
  and detection `none` (any other value is refused at load); their cells have `injected`,
  `net_difference` and `valid_atypical` lines. They are restricted by `when` so that they do not
  collide with a rule that does not exist yet (a contract that ends the day it starts only when
  already expired, a modification date equal to the creation only without claim). The cap
  boundary (10,000.00) waits for `montant_couverture` (lot 4).
- **Metrics.** `absence_probability[scenario]` is `{cases, probability, reason}`: `probability`
  maps `"500"`, `"1000"`, `"5000"`, `"10000"`, `"50000"` to the exact value for the rows of the
  file (`null` for a sample larger than the file); a scenario with a `relational` line has
  `probability` `null` and `reason` `multi_row_case`. `applied_cases` is the number of cases
  (distinct `relational` groups), `rows_touched` the rows they involve.
- **Timing.** 100,000 rows take about 35 seconds on the maintainer's machine; the contract tests
  run it once.
- **Not done on purpose.** R03, R04 and R09 (lot 6), the cap boundary (lot 4), rare-event counts
  that follow the file size (never: counts are absolute).

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

### 7.1 What lot 4 fixed

Written when lot 4 was implemented; where it differs from earlier sections this is the behavior.

- **Branch and combined layout.** Extended columns are generated per branch with the branch known.
  Each branch file (`insurance-principal.csv`, `insurance-ontario.csv`, `insurance-quebec.csv`)
  has 43 columns: the 33 base columns `FIELDS`, followed by the 10 extended columns
  `EXTENDED_FIELDS`. In `insurance-combined.csv`, the source column `filiale` is placed after the
  33 base columns and before the 10 extended columns (`[*FIELDS, "filiale", *EXTENDED_FIELDS]`),
  totaling 44 columns (matching the 34 + 10 contract target).
- **Byte-identical non-regression.** For the same seed, the first 33 columns of every branch and
  the first 34 columns of `insurance-combined.csv` are strictly byte-identical between the default
  output profile and the extended profile.
- **Independent random streams.** Every extended column draws exclusively from its own stream
  `_stream(seed, dataset, column, "extended")` via `extend_insurance_row`, without altering the
  base row stream `InsuranceProvider.row()`.
- **Clean file invariants.** The clean file satisfies every rule of the package catalogue with zero
  exception (tested on 20,000 rows):
  - `M07`: cancellation date present if and only if `statut_contrat` is `résilié`, and between
    `date_debut` and `date_fin`.
  - `M08`: claim event on or after `date_debut`.
  - `M09`: claim declared on or after `date_sinistre`.
  - `M10`: indemnity amount non-negative (`>= 0.00`).
  - `M11`: indemnity amount within coverage cap and claimed amount minus deductible.
  - `M12`: structural absence: `date_sinistre` and `montant_indemnise` empty without claim.
  - `M13`: `nombre_reclamations >= 1` with a claim, `0` without a claim.
  - `M24`: broker identifier present if and only if `canal_acquisition == "courtier"`.
  - `M25`: product code strictly matching contract type.
- **Rule evaluator column filter.** `RuleEvaluator.check` skips any rule where one of its declared
  columns is absent from the row being checked, ensuring rules targeting extended columns do not
  falsely flag default 34-column files.
- **Publication and manifest.** `build_generate_plan` accepts `--output-profile extended` on
  Insurance, refuses unknown profiles (`compact`, etc.), and passes `output_profile` to
  `GeneratePlan` and `manifest.json`.

### 7.2 What lot 6 fixed

Written when lot 6 was implemented; where it differs from earlier sections this is the behavior.

- **Business rules catalogue M01 to M25.** Complete implementation of the 25 business rules in
  `rules.yaml` of the Insurance package, evaluated via `RuleEvaluator` (Kleene three-valued logic,
  `RuleContext`). Verified on 20,000 clean rows in the `complete` profile with zero violations.
- **Tranche B columns in `complete` profile.** Four new columns appended in contract order:
  `taux_remboursement` (decimal between `0.00` and `1.00`), `consentement_communication`
  (`"true"` or `"false"`), `gestionnaire_id` (`GES-XXX`), `segment_client`
  (`particulier`, `professionnel`, `entreprise`, `vip`). The `complete` profile contains 47 columns
  per branch and 48 columns in `insurance-combined.csv` (with `filiale`).
- **Deterministic independent streams for tranche B.** Columns draw from independent random streams
  `_stream(seed, dataset, col, "complete")` via `extend_tranche_b_row`. The 34 default columns and
  the 44 extended columns remain strictly byte-identical for the same seed.
- **Completion of `rare_events`.** Added scenarios R03 (5 cases, negative indemnity), R04 (10 cases,
  claim before start with `date_minus_decade`), R09 (100 cases, indemnity exceeding coverage cap),
  and valid boundary case B03 (100 cases, indemnity equal to coverage cap). Linked R07 to M19 and
  R12 to M20. Totaling 15 scenarios, 1,416 anomaly events, and 300 valid atypical events on 100,000 rows.
- **Rules.json verification.** Every rule violation in `truth.csv` can be verified and re-evaluated
  directly from `rules.json` without access to Python source code or package YAML.
- **Output profile defaults for `rare_events`.** As `rare_events` requires extended columns,
  `build_generate_plan` selects the `extended` output profile by default when `--output-profile`
  is omitted for `rare_events`.

### 7.3 What lot 7 fixed

Written when lot 7 was implemented; where it differs from earlier sections this is the behavior.

- **V2 quality scenario profiles.** Three new profiles delivered in `dataset.yaml` of the Insurance package:
  - `format_vs_business`: balanced comparison profile with strictly equal counts (500 cases of format variants and defects vs 500 cases of business rule violations) and minimum rows floor of 10,000.
  - `anomaly_diversity`: coverage profile ensuring non-zero cases across all 6 categories (`format_variant`, `format_invalid`, `semantic_invalid`, `business_rule_violation`, `contextual_invalid`, `valid_atypical`) and 7 detector families (`syntactic`, `domain`, `cross_column`, `contextual`, `statistical`, `uniqueness`, `none`).
  - `clustered_errors`: spatial cluster on Ontario (`when: {filiale: "ontario"}`), agency cluster (`when: {agence_code: "AG-QC-001"}`), temporal/closed-status cluster, contrasted against a uniformly diffuse control anomaly (`nom` casing across all branches).
- **Root cause traceability.**
  - Operations sharing an incident declare `root_cause_id` (`ontario_import`).
  - Full traceability across `truth.csv`: written on `injected` and `net_difference` lines and inherited on `rule_violation` lines.
  - Member `root_causes` added to `MetricsDocument` (`dict[str, RootCauseMetrics]` tracking `events`, `rows_touched`, and sorted `scenarios`).
  - Schema `tabalyst.generate.metrics.schema.json` updated and validated.
- **Interactions C01 to C10.**
  - C01 (multiple anomalies per row via `can_overlap: true`)
  - C02 (masking)
  - C03 (inadvertent compensation: inverse operations restoring clean state, verified with 0 net differences)
  - C04 (successive modifications of the same cell with chained before/after values)
  - C05 (Kleene three-valued logic ensuring syntax defects leave business rules unknown rather than falsely violated)
  - C06 (relational cascade with duplicate key generating `relational` and `rule_violation` M21 rows)
  - C07 (common root cause across multiple columns and records)
  - C08 (correlated missing values across distinct columns)
  - C09 (segment-specific anomalies conditioned by `when`)
  - C10 (collective cluster detection).
- **Non-regression.** All contract tests up to lot 7 (84 tests) passing. Existing profiles and public showcase demos strictly unchanged.

## 8. Relational model (lots 8 and 9, D2)

### 8.1 Architecture and in-memory population

One in-memory population model (`PopulationModel` in `src/tabalyst/generate_population.py`)
orchestrates synthetic entities and relationships to feed two projections in lot 9: the flattened
multi-contract CSV and the four relational files (`clients.csv`, `contrats.csv`, `reclamations.csv`,
`paiements.csv`).

The internal topology comprises six compact entity classes using `__slots__`:
1. `Household`: physical residence (`id_menage`, street components, city, province, postal code,
   shared family name, language, seed). Groups 1 to 4 customers (G03).
2. `Customer`: insured individual (`id_client`, `id_menage`, civilite, first name, last name,
   adult birth date, gender, language, email, phone, client segment, communication consent).
   Owns 1 to 4 contracts (G01).
3. `Broker`: independent broker (`courtier_id`, name, province, branch). Assigned when
   `canal_acquisition == "courtier"` (G04).
4. `Contract`: insurance policy (`id_contrat`, `id_client`, branch, product type, product code,
   effective dates, status, premium, payment schedule, agency code, acquisition channel, broker,
   manager, coverage cap, deductible, reimbursement rate, `previous_contract_id` for renewals G07).
5. `Claim`: insurance claim (`id_reclamation`, `id_contrat`, loss event date, declaration date,
   claimed amount, indemnity amount, status, sequence number). A contract may have 0 to 3
   distinct claims (G02).
6. `Payment`: financial indemnity disbursement (`id_paiement`, `id_reclamation`, `id_contrat`,
   payment date, amount, payment method, payment status, sequence number). A settled claim can have
   1 to 3 installment payments satisfying M25 (`sum(payments) == montant_indemnise`) (G08).

### 8.2 Cardinalities and distributions (G01 to G08)

The model targets realistic insurance market distributions:
- **G01 (Multi-contract customers)**: ~28% of customers hold 2 or more contracts:
  1 contract (70%), 2 contracts (22%), 3 contracts (6%), 4 contracts (2%). Average: ~1.4 contracts/customer.
  For 500,000 contracts, this yields ~357,000 unique customers.
- **G02 (Multi-claim contracts)**: Claim likelihood is governed by `claim_probability` per product.
  Among contracts with claims: 1 claim (85%), 2 claims (12%), 3 claims (3%).
- **G03 (Households)**: 1 customer (75%), 2 customers (20%), 3 customers (4%), 4 customers (1%).
  Average: ~1.3 customers/household.
- **G04 (Brokers)**: Pool of 200 brokers (`CRT-0101` to `CRT-0300`) distributed across branches.
- **G05 (Agencies with heavy load)**: Contracts assigned using the weighted agency distribution from
  `agencies.csv`, concentrating thousands of contracts in major regional hubs.
- **G06 (Address changes)**: Multi-contract or renewed customers maintain their canonical household
  address with realistic temporal validity.
- **G07 (Contract renewals)**: Policies of expired or active status can be linked as renewals of a
  prior policy (`previous_contract_id`), with continuous chronological dates.
- **G08 (Disbursement installments)**: Claims with `montant_indemnise > 0.00` have 1 (65%), 2 (25%),
  or 3 (10%) payment installments whose sum equals the indemnity amount exactly (M25).

### 8.3 Relational edge cases (G09 and G10)

The population model deliberately seeds key deduplication and entity resolution benchmarks:
- **G09 (Shared address without duplicate)**: Multiple adult customers sharing the exact same
  physical address (household) with different surnames (e.g., Quebec spouses keeping maiden names,
  or co-tenants) or with identical surnames (adult family members) but distinct individual identifiers
  and birth dates, creating realistic test cases for entity resolution without false-positive duplicates.
- **G10 (Near-identical identities)**: Generational pairs sharing surname and address with very
  similar first names (e.g., father and son "Jean Tremblay" and "Jean-Pierre Tremblay", or "Robert"
  and "Robert Jr") but different birth dates and `id_client`.

### 8.4 Bounded memory and determinism

For 500,000 contracts (~360,000 customers, ~300,000 households, ~75,000 claims, ~110,000 payments):
- **Bounded memory budget**: Under 150 MB total RAM. Achieved via `__slots__` eliminating object
  `__dict__`, string interning of repeated categories (`branch`, `product`, `status`, `agency`),
  and computing detailed formatting text on projection rather than storing full row strings in memory.
- **Deterministic derivation**: Every entity stream derives deterministically from the root `seed`
  and its canonical identity (`seed`, kind, sequence id). Generating the same population with the same
  seed produces identical identifiers and attributes.
- **Stateless non-regression**: Legacy `InsuranceProvider.row()` remains completely untouched and
  stateless for existing default 34-column outputs and showcase demos.

### 8.5 What lot 8 fixed

Written when lot 8 was implemented:
- **Module**: `src/tabalyst/generate_population.py` delivering `Household`, `Customer`, `Broker`,
  `Contract`, `Claim`, `Payment`, and `PopulationModel`.
- **Invariants**: Clean population satisfies M01 through M25 with zero violations.
- **Memory**: Measured and enforced via `tracemalloc` in test suite (`tests/test_generate_population.py`).
- **Projections**: `PopulationModel` provides `to_contract_row`, `to_client_row`, `to_claim_row`,
  and `to_payment_row` ready for lot 9 file outputs.

### 8.6 What lot 9 fixed

Written when lot 9 was implemented:
- **Relational output suite (`--relational`)**: Generates four clean relational CSV tables
  (`clients.csv` 22 columns, `contrats.csv` 23 columns, `reclamations.csv` 7 columns,
  `paiements.csv` 7 columns) alongside their full truth artifact suites (`.truth.csv`,
  `.rules.json`, `.metrics.json`, `.manifest.json` per table), totaling 20 published files.
- **Flattened multi-contract profiles**: Supported via `--output-profile flattened` (34 columns on
  combined, 33 on branch), `flattened-extended` (44 columns on combined, 43 on branch), and
  `flattened-complete` (48 columns on combined, 47 on branch), projecting denormalized customer and
  primary claim attributes per contract.
- **Relational truth lines**:
  - `G09` (shared household without duplicate): `valid_atypical` relational lines on `id_menage`
    with `group_id="G09-<id_menage>"`.
  - `G10` (near-identical identities): `valid_atypical` relational lines on `nom` with
    `group_id="G10-<id_menage>"`.
  - `M22` (orphan claim reference): `rule_violation` and `relational` lines on `id_contrat` for
    orphan claims pointing to non-existent contract identifiers when anomaly profiles are active.
- **CLI & validation**: CLI option `--relational` added to `tabalyst generate`. Explicit rejection
  when passed with `-o` (`--relational generates multiple tables; use -d.`) or on non-insurance
  packages (`--relational applies to the Insurance package only.`).
- **Atomic publication**: Multi-table generation uses `batch_writer` with staging, `fsync`, backup
  preservation on failure, and atomic replacement with zero orphan `.tmp` or `.bak` files.
- **Testing & non-regression**: Dedicated test suite in `tests/test_generate_relational_outputs.py`
  (6 tests) and contract tests in `tests/test_generate_insurance_v2_contract.py` (88 tests passing).
  Showcase demos byte-identical.

### 8.7 What lot 10 fixed

Written when lot 10 was implemented:
- **Statistical distributions (§12, D01 to D15)**:
  - `src/tabalyst/generate_draws.py` extended with pure mathematical draws without rejection:
    `truncated_pareto` (D04, D13), `bimodal_normal` (D05), `power_law_weights` (D08),
    `seasonal_factor` (D09), and `inflation_factor` (D11).
  - Integrated into `PopulationModel`:
    - Heavy-tailed Pareto claim severity (D04/D13) on 10% of settled claims.
    - Zipf power-law distribution over the 200 brokers pool (D08).
    - Harmonic seasonal loss dates (D09) peaking in winter (January) for auto and home, and summer (July) for travel.
    - Compound annual synthetic inflation (D11, +2.5%/year) on base premiums.
- **Row ordering and sampling bias mechanisms (E01 to E03)**:
  - Option `--row-order` supported in CLI (`tabalyst generate`) and `build_generate_plan`:
    - `branch` (E01): Grouped by operational branch.
    - `chronological` (E02): Chronologically sorted by contract creation and start dates.
    - `agency` (E03): Grouped by agency code.
    - `shuffled`: Deterministically pseudo-randomized order.
    - `default`: Preserves original natural branch order.
- **Dense subpopulation cluster (§12)**:
  - 200 consecutive contracts (sequences 501 to 700) exhibiting an abnormally high 20% claim rate (~40 claims),
    testing stratified sampling against localized clusters representing <0.01% globally.
- **Simpson's paradox (E16)**:
  - Mathematical reversal guaranteed and verified: within each branch (Ontario, Principal, Quebec),
    broker-advised policies carry higher average premiums than direct policies. Globally aggregated,
    direct sales have higher average premiums than broker sales due to branch portfolio mix.
- **Unseen categories (E18)**:
  - Product code `VOY_MULTI` is strictly absent (0 occurrence) for contracts created before 2024-01-01,
    and present afterwards, benchmarked for out-of-vocabulary model generalization.
- **Strict non-regression**:
  - Legacy stateless `InsuranceProvider.row()` remains completely untouched and byte-identical for default runs.
- `generation_version` stays 2.

### 8.8 What lot 11 fixed

Written when lot 11 was implemented:
- **Missing data mechanisms (§11, MCAR, MAR, MNAR)**:
  - Strict formalization according to Little & Rubin (1987):
    - `mcar` (Missing Completely at Random): independent missingness, rejects any `when` condition.
    - `mar` (Missing at Random): missingness conditioned by an observed column distinct from the missing column.
    - `mnar` (Missing Not at Random): missingness conditioned by the target column itself (e.g. high values).
  - Validation in `src/tabalyst/generate_scenarios.py` rejecting invalid mechanism/condition configurations.
- **Comparison operators in `when` conditions**:
  - `src/tabalyst/generate_anomalies.py` supports comparison prefixes (`>=`, `<=`, `>`, `<`, `!=`) for numeric thresholds and ISO dates in addition to strict equality.
- **Realistic missing reasons (§10 & §11)**:
  - Standardized vocabulary in English (D14): `unreported`, `client_refusal`, `not_applicable`, `system_omission`, `unknown`.
- **Traceability in `truth.csv` and `metrics.json`**:
  - `truth.csv`: `group_id` records `missing:<mechanism>:<reason>`. The clean value before blanking is preserved in `canonical_value` on the `injected` row, providing ground truth for imputation benchmarks.
  - `metrics.json`: `ScenarioMetrics` carries `missing_mechanism` and `missing_reason`. New top-level object `missing_data` (`MissingDataMetrics`) with aggregated metrics by mechanism, exact counts by reason, and column-by-mechanism contingency matrix.
  - JSON schema `src/tabalyst/schemas/tabalyst.generate.metrics.schema.json` updated and verified.
- **Scenario profile `missing_mechanisms`**:
  - Added to `src/tabalyst/generate_examples/insurance/dataset.yaml` with floor `min_rows: 10000`, covering MCAR, MAR, MNAR, all 5 reasons, and 4 concentration modes (uniform, Ontario branch, agency AG-QC-001, and post-2024 periods).
- **Strict non-regression**:
  - All default runs and existing profiles remain byte-identical.
  - All 100 contract tests passing.
- `generation_version` stays 2.

### 8.9 What lot 12 fixed

Written when lot 12 was implemented:
- **Temporal rule validity & periods (§13)**:
  - `RulePeriod` model (`start`, `end`, `description`) added to `Conventions.periods` in `src/tabalyst/generate_rules.py`.
  - Named periods declared in `rules.yaml`: `legacy_tariff` (<= 2023-12-31), `migration_ontario` (>= 2023-06-01), `schema_v2` (>= 2024-01-01), and `modern_tariff` (>= 2025-01-01).
  - `Rule` model extended with `valid_from`, `valid_until`, `temporal_column` (defaults to `date_debut`), and `period`.
  - Temporal filtering in `RuleEvaluator`: rows are only evaluated against a rule if their `temporal_column` date falls within `[valid_from, valid_until]` (or the named period window).
  - Temporal business rules catalogue completed with M26 through M30 in `rules.yaml` (M26: post-2024 v2 schema version; M27: post-migration Ontario core system; M28: observation date vs creation date coherence; M29: legacy v1.0 schema version; M30: post-2025 habitation deductible floor).
- **Tranche C columns & complete profile (Contract 7, §13)**:
  - Tranche C delivers 3 columns: `date_observation`, `version_source`, and `source_system`.
  - Output profile `complete` now totals 50 columns on branch files and 51 columns on `insurance-combined.csv` (including `filiale`).
  - `flattened-complete` profile updated to 51 columns.
  - Deterministic independent generation stream per column preserves strict byte-level non-regression on all default and extended columns.
- **Scenario profile `schema_drift`**:
  - Profile `schema_drift` added to `dataset.yaml` with floor `min_rows: 10000`, covering 8 scenarios and 800 events:
    - IT migrations: `SD_SYS_MIG` (100 cases, M27), `SD_VER_MIG` (100 cases, M26), `SD_FMT_MIG` (100 cases, syntactic telephone defect).
    - Anachronisms: `SD_OBS_ANACH` (50 cases, M28), `SD_VER_PREMAT` (50 cases, M29).
    - Regulatory tariff drift: `SD_DEDUCT_REG` (100 cases, M30).
    - Valid atypical drift: `SD_CHAN_DRIFT` (200 cases, web shift) and `SD_LEGACY_VAL` (100 cases, grandfathered deductibles).
  - Defaults to `effective_output: complete` when `--output-profile` is omitted.
- **Traceability in `metrics.json` and JSON schemas**:
  - `TemporalDriftMetrics` added to `metrics.json` carrying `active_periods`, `drift_scenarios`, and exact violations for `temporal_rules`.
  - Updated JSON schemas `tabalyst.generate.rules.schema.json` and `tabalyst.generate.metrics.schema.json`.
- **Strict non-regression**:
  - 105 contract tests passing (Lots 0 through 12).
  - Showcase demos (`examples/showcase/`) verified and refreshed.
- `generation_version` stays 2.

### 8.10 What lot 13 fixed

Written when lot 13 was implemented:
- **Separate ground-truth label file `<dataset>.<profile>.ml_labels.csv` (SRS §8, §15, Lot 13)**:
  - Isolates supervised machine learning targets and continuous latent probabilities from input features.
  - 7 standard columns: `row_number`, `id_contrat`, `is_fraud`, `observed_label`, `confirmation_date`, `fraud_type`, `latent_probability`.
  - Registered in `manifest.json` with role `"ml_labels"`, carrying byte size and SHA-256 digest.
  - New committed schema `src/tabalyst/schemas/tabalyst.generate.ml_labels.schema.json` formalizing format `tabalyst.generate.ml_labels`, version `0.2.0`, revision 1.
- **Synthetic fraud patterns without trivial artifacts (SRS §8)**:
  - 4 realistic multi-class fraud typologies (ML04): `phantom_claim`, `inflated_claim`, `collusion`, `organized_fraud`.
  - Imbalanced class prevalence rates: 1% overall fraud rate (ML01), 0.1% rare fraud class (ML02), 0.01% single case (ML03).
  - Hard cases with continuous latent probability overlap in `[0.45, 0.65]` (ML05).
  - Plausible false positives and valid atypicals (ML06, ML20).
  - Operational label noise (ML07) and delayed unresolved investigations (ML08).
- **Profile `ml_fraud_imbalanced`**:
  - Added to `dataset.yaml` with floor `min_rows: 10000`, 11 scenarios covering ML01 through ML08 and ML20.
  - Defaults `effective_output` to `extended` (44 columns on `insurance-combined.csv`).
- **Metrics integration**:
  - `MetricsDocument` carries `ml_fraud: MLFraudMetrics`.
- **Strict non-regression**:
  - 113 contract tests passing.
- `generation_version` stays 2.

### 8.11 What lot 14 fixed

Written when lot 14 was implemented:
- **Extended ML prediction targets in `ml_labels.csv` (SRS §8 ML09-ML12)**:
  - Future claim prediction (ML09): `future_claim` in `{0, 1}` (~10% positive rate).
  - Claim cost regression (ML10): `cout_sinistre`, strictly `0.00` when `future_claim == 0` and positive amount when `1`.
  - Retention/renewal prediction (ML11): `renouvellement` (> 60% retention rate) and `date_renouvellement`.
  - Multiclass risk rating (ML12): `risque_categorie` across 4 classes: `faible`, `moyen`, `eleve`, `tres_eleve`.
  - Upstream calculated variables: `historique_sinistres` and `anciennete_client`.
  - Latent risk rating: `score_risque_interne` in `[100.0, 900.0]`.
- **Intentional leakage scenarios and shortcuts (SRS §8 ML13-ML19)**:
  - Behavioral drift (ML13, `ML13_DRIFT`) and unseen extreme values (ML14, `ML14_UNSEEN`).
  - Inter-contract customer leakage (ML15, `ML15_LEAK`).
  - Post-claim temporal leakage (ML16, `ML16_POST_LEAK`).
  - Artificial shortcut correlated to identifiers (ML17, `ML17_SHORTCUT`).
  - Subsidiary branch imbalance (ML18, `ML18_IMBALANCE`) and segment-conditioned missingness (ML19, `ML19_MISSING`).
- **Leakage-free dataset partitioning: `<dataset>.<profile>.splits.csv` (SRS §8, §15, Lot 14)**:
  - Produced alongside `ml_labels.csv` with 6 standard columns: `row_number`, `id_contrat`, `id_client`, `split_client`, `split_temporal`, `resampled_train_only`.
  - Customer-grouped fold partition (`split_client`): 70% train / 15% val / 15% test with 0 shared clients.
  - Chronological partition (`split_temporal`): strict cutoff dates separating train, val, and test.
  - Resampling isolation: `resampled_train_only` flag ensuring test folds keep uncorrupted natural distributions.
  - Registered in `manifest.json` under role `"splits"`, with size and SHA-256.
  - New committed schema `src/tabalyst/schemas/tabalyst.generate.splits.schema.json` formalizing format `tabalyst.generate.splits`, version `0.2.0`, revision 1.
  - Extended metrics `SplitMetrics` added to `metrics.json`.
- **Profile `ml_leakage_test`**:
  - Added to `dataset.yaml` with 7 scenarios, defaulting `effective_output` to `extended`.
- **Strict non-regression**:
  - 121 contract tests passing.
- `generation_version` stays 2.

### 8.12 What lot 16 fixed

Written when lot 16 was implemented:
- **Dedicated technical stress profile `technical_stress` (SRS §14, §15)**:
  - Added to `dataset.yaml` with floor `min_rows: 10000`, 9 scenarios covering T03 through T11:
    - T03 (`T03_LONG_TEXT`): Long free-text comments exceeding 600 characters in `commentaires` (text overflow / token limits).
    - T04 (`T04_JSON_TEXT`): Semi-structured JSON text formatted into string cells in `notes_gestion`.
    - T05 (`T05_QUOTED_DELIM`): RFC 4180 escaped delimiters, embedded commas, double-quote escaping.
    - T06 (`T06_MULTILINE`): Multiline CSV entries with newline characters (`\n`, `\r\n`) inside properly quoted fields.
    - T07 (`T07_UNICODE`): Complex Unicode with accented characters, emojis, non-Latin scripts (CJK, Arabic, Cyrillic), and special currency symbols.
    - T08 (`T08_HIGH_CARD`): High distinct cardinality columns populated with valid UUID v4 strings.
    - T09 (`T09_RARE_CATS`): Heavy-tailed long-tail distribution of rare categories.
    - T10 (`T10_FLOAT_PREC`): Extreme floating-point values near IEEE 754 precision boundaries, subnormals, and precision limits.
    - T11 (`T11_SPARSE`): Extremely sparse columns (99%+ missing / empty values).
  - Automatically defaults `effective_output` to `extended` (44 columns on `insurance-combined.csv`).
- **Cell-level stress generators**:
  - Implemented in `src/tabalyst/generate_anomalies.py`: `_long_text`, `_json_text`, `_quoted_delimiters`, `_multiline_text`, `_unicode_complex`, `_high_cardinality_uuid`, `_rare_category`, `_float_precision_extreme`.
- **Volumetric boundaries (T01 & T02)**:
  - T01: 1,200,000 rows exceeding standard spreadsheet limits (Excel 1,048,576 rows).
  - T02: 5,000,000 and 10,000,000 rows streaming under $O(1)$ memory budgets.
- **Heterogeneous branch schemas in combine (T12)**:
  - Outer-union column merging across branches preserving subsidiary schemas, padding missing values with `""`.
- **Malformed files isolation (D13)**:
  - Module `src/tabalyst/generate_malformed.py` isolates syntactically broken CSVs, truncated rows, and unclosed quotes into standalone test artifacts (`malformed_corrupted_separators.csv`, `malformed_truncated_lines.csv`, `malformed_unclosed_quotes.csv`, `malformed_invalid_encoding.csv`), strictly preventing pollution of reference datasets.
- **Metrics integration**:
  - `TechnicalStressMetrics` serialized in `metrics.json` under `technical_stress`.
  - Schema `tabalyst.generate.metrics.schema.json` regenerated and validated.
- **Strict non-regression**:
  - 136 contract tests passing (Lots 0-16).
- `generation_version` stays 2.

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
| 10 | distributions, ordering bias, Simpson, unseen categories | 8.7, §7, §12 |
| 11 to 12 | absence mechanisms, drift | 5.4, 5.3 |
| 13 to 15 | ML labels, leakage, splits, latent file | 5.6 |
| 16 | technical stress, malformed files in separate files (D13) | 8.12 |
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
  still raise `format_revision`), the three-valued reading of rules (5.8), the attribution of a
  `rule_violation` line to the last event of its row, and whether a profile may list rules it
  does not target.
- Lot 6: the boundary cases B01 and B02 of lot 3 carry the `when` restrictions of 6.4; the rules
  of lot 6 may need more (a claim after the end of a contract that ends the day it starts).
- Lot 4: exact formulas of the extended rules and the share of boundary values in the clean file.
- Lot 8: the model and its memory bound (gate P2).
- Whether legacy profiles should get a truth file on request (not planned: their set of
  artifacts is a non-regression reference).
