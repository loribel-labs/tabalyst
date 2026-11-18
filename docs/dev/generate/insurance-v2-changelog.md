# Insurance V2 changelog

Maintenance document, never published. The contract is [`insurance-v2.md`](insurance-v2.md).

Two numbers are tracked here (contract 5.5 and 5.7):

- `generation_version` of `manifest.json`: an integer raised whenever the bytes of a V2 output
  change for the same inputs (seed, profile, rows, as-of date, package);
- `format_revision` of `rules.json`, `metrics.json` and `manifest.json` (`format_version`
  `0.2.0`): raised by a change of structure or meaning of one of the files.

The format is experimental during the beta: no migration is provided. Until the first release
that ships it (0.7.8, gate P2), the branch may still add members within revision 1; each one is
listed here.

## generation_version 1, format revision 1 (lot 2, 2026-11-16)

First appearance of the four files of a scenario profile:

- `truth.csv`: the 14 columns of contract 5.2; kinds `injected`, `net_difference` and
  `rule_violation` (the other three kinds arrive with lots 3 and 9);
- `rules.json` (`tabalyst.generate.rules`): `dataset`, `profile`, `as_of_date`, `conventions`
  (`branch_column`, `date_format`, `decimal`) and the rules the profile names, each with
  `detection`;
- `metrics.json` (`tabalyst.generate.metrics`): `rows`, `counts`, `scenarios`, `rules`,
  `categories`, `kinds`; `absence_probability` arrives with lot 3, still in revision 1;
- `manifest.json` (`tabalyst.generate.manifest`): the members of contract 5.5 plus `dataset`.

## generation_version 2, format revision 1 (lot 3, 2026-11-17)

`metrics.json` and `truth.csv` change for the same inputs, hence the new generation version; no
structure of `rules.json` or `manifest.json` changes, and the first release that ships the
format is still to come, so the revision stays 1:

- `metrics.json` gains `absence_probability`: per scenario, `cases`, `probability` (a sample
  size, 500, 1000, 5000, 10000 and 50000, to the exact probability for the rows of the file,
  `null` above the number of rows) and `reason`; a scenario whose case spans several rows has
  `probability` `null` and `reason` `multi_row_case`;
- `ScenarioMetrics.applied_cases` counts cases (distinct `relational` groups when a scenario has
  some) and `rows_touched` the rows they involve: they differ for a case on several rows;
- `truth.csv` uses the kinds `relational` (two lines per `reuse_value` case, `group_id`
  `<scenario>-<first row>`) and `valid_atypical` (one line per cell a `valid_atypical` scenario
  changed, severity `info`, detection `none`);
- the manifest holds `generation_version` 2.

Package side: the profile `rare_events` (34 columns, floor of 100,000 rows) and the profile key
`min_rows`; operation kinds `reuse_value` and `copy_column`; `format` values `times_100`,
`date_plus_century` and `postal_other_province`. The three legacy profiles do not move.

## Extended output profile (lot 4, 2026-11-17)

Option `--output-profile extended` on the Insurance package:

- Appends 10 priority columns after `filiale` on `insurance-combined.csv` (44 columns in total,
  the 34 of default plus 10) and on branch files (43 columns, the 33 base columns plus 10):
  `date_sinistre`, `montant_couverture`, `franchise`, `montant_indemnise`, `date_resiliation`,
  `statut_paiement`, `canal_acquisition`, `courtier_id`, `produit_code`, `nombre_reclamations`;
- Independent random streams per column `_stream(seed, dataset, column, "extended")`: base row
  draws and bytes remain strictly identical to default for the same seed;
- New rules added to the package catalogue: M07 (cancellation date), M08 (claim event date),
  M09 (claim declaration date), M10 (non-negative indemnity), M11 (indemnity cap), M12 (structural
  absence), M13 (claim counts), M24 (broker channel), M25 (product code);
- `RuleEvaluator.check` skips any rule referencing columns not present in the evaluated row;
- `manifest.json` carries `output_profile: "extended"` when selected;
- `generation_version` stays 2 (default runs keep identical bytes).

## Format catalogue F01 to F22 (lot 5, 2026-11-17)

Catalogue of format defect and variant operations completed in `generate_anomalies.py`:

- 18 new format operation values added to `FORMAT_VALUES` and `TEXT_TRANSFORMS` (bringing total format values to 52):
  - F01: `surrounding_space` (random leading/trailing spaces)
  - F03: `insert_non_breaking_space` (NBSP `\u00A0` replacing or added to spaces)
  - F04: `unicode_nfd` / `unicode_nfc` (Unicode normalization)
  - F05: `title_case` (first letter of each word capitalized)
  - F08: `phone_drop_digit` (drop random digit from phone number)
  - F09: `email_invalid` (syntax error, e.g. missing `@` or domain)
  - F10: `email_forbidden_domain` (forbidden test domain such as `example.com`, `test.invalid`)
  - F11: `postal_no_space` (Canadian postal code without space, `A1A1A1`)
  - F12: `postal_invalid_syntax` (corrupted postal code syntax)
  - F13: `decimal_comma` / `decimal_dot` (decimal comma vs dot)
  - F14: `thousands_space` / `thousands_comma` (thousands separators)
  - F18: `date_impossible` (calendar-impossible date e.g. day 00 or 32, month 00 or 13)
  - F20: `date_swap_month_day` (swapped day/month for ambiguous date, keeping canonical clean ISO date)
  - F21: `drop_leading_zeros` (drop leading zeros from identifier)
  - F22: `similar_char` (visually confusable homoglyphs: `O` <-> `0`, `l` <-> `1`)
- Canonical normalization in `generate_canonical.py`:
  - `canonical_decimal` strips thousands separators and normalizes decimal commas to plain decimal `.`.
  - F20 retains the original clean ISO date in `truth.csv`.
- Kleene 3-valued logic in `generate_rules.py`: format defects on date/decimal columns result in unknown (`None`) evaluations, ensuring that format defects never cause spurious business rule violations.
- Non-regression: 29 legacy format operations and existing profiles unchanged.
- `generation_version` stays 2.

## Business rules catalogue M01 to M25, tranche B, complete profile (lot 6, 2026-11-17)

- Complete catalogue of 25 business rules M01 to M25 configurable in `rules.yaml` of the Insurance package.
- Evaluated via `RuleEvaluator` and `RulesDocument` with Kleene three-valued logic and `RuleContext` (`as_of_date: "2026-09-16"`).
- Clean file satisfies all 25 rules with 0 violations on 20,000 rows in the `complete` profile.
- Four tranche B columns added to the `--output-profile complete` profile: `taux_remboursement`, `consentement_communication`, `gestionnaire_id`, `segment_client` (47 columns per branch, 48 on `insurance-combined.csv`).
- Deterministic independent streams per tranche B column (`_stream(seed, dataset, column, "complete")`); `default` (34 columns) and `extended` (44 columns) remain strictly byte-identical for the same seed.
- Profile `rare_events` completed with R03 (5 cases, negative indemnity, M10), R04 (10 cases, claim before contract start via `date_minus_decade`, M08), R09 (100 cases, indemnity exceeding coverage cap, M11), and valid boundary case B03 (100 cases, indemnity equal to coverage cap, M11).
- Composite multi-column violations and `contextual_invalid` category handled and verifiable directly from `rules.json` alone.
- `build_generate_plan` selects `output_profile: "extended"` by default when running `rare_events`.
- `generation_version` stays 2.

## Quality profiles, interactions C01 to C10, root causes (lot 7, 2026-11-17)

- Three new V2 quality scenario profiles added to the Insurance package:
  - `format_vs_business`: balanced comparison profile with strictly equal counts of format variants/defects (500 cases across FB_F01 and FB_F02) and business rule violations (500 cases across FB_B01 and FB_B02). Kleene logic guarantees format defects do not trigger business rule violations.
  - `anomaly_diversity`: comprehensive coverage profile featuring all 6 categories (`format_variant`, `format_invalid`, `semantic_invalid`, `business_rule_violation`, `contextual_invalid`, `valid_atypical`) and all 7 detector families (`syntactic`, `domain`, `cross_column`, `contextual`, `statistical`, `uniqueness`, `none`).
  - `clustered_errors`: localized spatial (Ontario import incident), group (agency AG-QC-001) and temporal clusters, contrasted against a uniformly diffuse control anomaly (E06, E07, E14, E15).
- Root cause traceability:
  - Scenarios sharing a common incident declare `root_cause_id` (e.g., `ontario_import` corrupting dates, decimal formats, and phone numbers in Ontario).
  - Traversed and recorded in `truth.csv` on `injected`, `net_difference`, and propagated to `rule_violation` rows.
  - Aggregated in `metrics.json` under member `root_causes` (`dict[str, RootCauseMetrics]` with `events`, `rows_touched`, and sorted `scenarios`).
  - `tabalyst.generate.metrics.schema.json` updated with `RootCauseMetrics` definition.
- Interactions C01 to C10 verified and documented: overlapping operations on shared rows, cell modification chaining, inadvertent compensation (restoring clean values with 0 net differences), Kleene 3-valued logic isolation, relational cascades, segment-specific anomalies, and collective cluster detection.
- `generation_version` stays 2.

## In-memory relational population model (lot 8, 2026-11-17)

Phase 3 begins on branch `insurance-v2/phase-3` after gate P2 ratification (direct transition to Phase 3):

- **Internal relational topology** (`src/tabalyst/generate_population.py`):
  - Six compact entity classes using `__slots__`: `Household`, `Customer`, `Broker`, `Contract`, `Claim`, `Payment`.
  - Integer date ordinals, interned strings (`_INTERNED_MANAGERS`, `_INTERNED_BROKERS`, branch codes, products, statuses), and sequence-based identifiers.
- **Relational features and cardinalities (G01 to G08)**:
  - G01: Multi-contract customers (1 to 4 policies per insured, ~28% holding 2+ contracts, with shared personal identity and contact info).
  - G02: Multi-claim contracts (up to 3 distinct claims per covered policy, chronological event/declaration dates).
  - G03: Multi-customer households (1 to 4 adult customers per residence).
  - G04: Independent broker pool (200 brokers `CRT-0101` to `CRT-0300`).
  - G05: Weighted agency allocation reflecting real branch concentrations.
  - G07: Contract renewals linked to preceding policy (`previous_contract_id`) with chronological date continuity.
  - G08: Multiple indemnity installments for settled claims strictly satisfying M25 (`sum(payments) == montant_indemnise`).
- **Relational edge cases (G09 and G10)**:
  - G09: Adult co-tenants and spouses sharing identical physical address with distinct surnames.
  - G10: Generational household members sharing address and surname with distinct first names and birth dates.
- **Strictly bounded memory**:
  - Memory consumption per contract measured under 850 bytes/contract including all entities, scaling linearly to under 410 MB for 500,000 contracts and validated via `tracemalloc`.
- **Projections for lot 9**:
  - Methods `to_flattened_row` (34, 44 or 48 columns), `to_client_row`, `to_relational_contract_row`, `to_claim_row`, `to_payment_row`.
- **Non-regression**:
  - Legacy stateless `InsuranceProvider.row()` remains completely untouched and byte-identical for existing runs.
- `generation_version` stays 2.

## Relational outputs and table truth (lot 9, 2026-11-17)

- **Relational output suite (`--relational`)**:
  - Generates four clean relational CSV tables:
    - `clients.csv`: 22 columns (`id_client`, `civilite`, `prenom`, `nom`, `date_naissance`, `sexe`, `langue_preferee`, `courriel`, `telephone`, `id_menage`, street components, city, province, postal code, country, `segment_client`, `consentement_communication`).
    - `contrats.csv`: 23 columns (`id_contrat`, `id_client`, `filiale`, `type_contrat`, `produit_code`, `date_debut`, `date_fin`, `statut_contrat`, `prime_annuelle`, `frequence_paiement`, `mode_paiement`, `statut_paiement`, `montant_couverture`, `franchise`, `taux_remboursement`, `agence_code`, `canal_acquisition`, `courtier_id`, `gestionnaire_id`, `date_creation`, `date_modification`, `date_resiliation`, `contrat_precedent_id`).
    - `reclamations.csv`: 7 columns (`id_reclamation`, `id_contrat`, `date_sinistre`, `date_reclamation`, `montant_reclamation`, `montant_indemnise`, `statut_reclamation`).
    - `paiements.csv`: 7 columns (`id_paiement`, `id_reclamation`, `id_contrat`, `date_paiement`, `montant`, `mode_paiement`, `statut_paiement`).
  - Full ground-truth artifact suite generated per table (`.truth.csv`, `.rules.json`, `.metrics.json`, `.manifest.json`), totaling 20 published files.
- **Flattened multi-contract profiles**:
  - Projections via `--output-profile flattened` (34 columns on combined, 33 on branch), `flattened-extended` (44 columns on combined, 43 on branch), and `flattened-complete` (48 columns on combined, 47 on branch).
  - Evaluated per contract with denormalized customer and primary claim data.
- **Relational ground truth**:
  - `G09` (shared household without duplicate): `valid_atypical` relational lines on `id_menage` in `clients.truth.csv` with `group_id="G09-<id_menage>"`.
  - `G10` (near-identical identities): `valid_atypical` relational lines on `nom` in `clients.truth.csv` with `group_id="G10-<id_menage>"`.
  - `M22` (orphan claim reference): `rule_violation` and `relational` lines on `id_contrat` in `reclamations.truth.csv` for orphan claims pointing to non-existent contract identifiers when anomaly profiles are active.
- **CLI integration & atomic publication**:
  - CLI option `--relational` in `tabalyst generate`.
  - Explicit error handling for single-file output `-o` and non-insurance packages.
  - Multi-table staging with atomic replace and zero leftover `.tmp` or `.bak` files.
- **Testing & verification**:
  - 6 dedicated unit and integration tests in `tests/test_generate_relational_outputs.py`.
  - 4 contract tests enabled in `tests/test_generate_insurance_v2_contract.py` (88 tests passing).
- `generation_version` stays 2.

## Distributions D01 to D15 and sampling bias E01 to E18 (lot 10, 2026-11-17)

- **Statistical distributions (§12, D01 to D15)**:
  - Added reusable, rejection-free random distributions in `src/tabalyst/generate_draws.py`:
    - `truncated_pareto` (D04, D13): exact inverse transform for heavy-tailed claim severity;
    - `bimodal_normal` (D05): two-component Gaussian mixture;
    - `power_law_weights` (D08): Zipf power-law weights for categorical concentration;
    - `seasonal_factor` (D09): harmonic seasonal multiplier around 1.0;
    - `inflation_factor` (D11): continuous compound annual inflation.
  - Integrated into `PopulationModel` (`src/tabalyst/generate_population.py`):
    - 10% of settled claims follow heavy-tailed Pareto amounts within policy bounds;
    - Broker pool follows a Zipf power law, concentrating policy intermediation;
    - Harmonic seasonal loss dates (winter peak for auto/home, summer peak for travel);
    - Compound annual synthetic inflation (+2.5%/year) on premiums.
- **Row ordering and sampling bias mechanisms (E01 to E03)**:
  - Added `--row-order` CLI option and `build_generate_plan` parameter for Insurance outputs (`--relational` and `--output-profile flattened*`):
    - `branch` (E01): rows grouped by branch;
    - `chronological` (E02): rows sorted by creation and start dates;
    - `agency` (E03): rows grouped by agency code;
    - `shuffled`: deterministically pseudo-randomized order;
    - `default`: natural branch order.
- **Dense subpopulation cluster (§12)**:
  - 200 consecutive contracts (sequences 501 to 700) featuring an abnormally high 20% claim rate (~40 claims), establishing an ideal benchmark for stratified sampling against localized clusters.
- **Simpson's paradox (E16)**:
  - Exact mathematical reversal: conditioned on each branch (Ontario, Principal, Quebec), broker policies carry higher average premiums than direct policies. Globally aggregated, direct sales carry higher average premiums than broker sales due to branch portfolio mix.
- **Unseen categories (E18)**:
  - Product code `VOY_MULTI` is strictly absent before 2024-01-01 and present afterwards, testing out-of-vocabulary model generalization.
- **Strict non-regression**:
  - Stateless `InsuranceProvider.row()` remains completely untouched and byte-identical for default generation.
- **Testing**:
  - 6 new contract tests in `tests/test_generate_insurance_v2_contract.py` (94 tests passing).
  - 6 unit tests in `tests/test_generate_draws.py`.
- `generation_version` stays 2.

## Missing data mechanisms MCAR, MAR, MNAR and reasons (lot 11, 2026-11-17)

- **Mechanisms and reasons (§11, MCAR, MAR, MNAR)**:
  - Added `missing_mechanism` (`mcar`, `mar`, `mnar`) and `missing_reason` (`unreported`, `client_refusal`, `not_applicable`, `system_omission`, `unknown`) to scenario metadata in `src/tabalyst/generate_scenarios.py`.
  - Enforced consistency rules: MCAR forbids `when`, MAR requires `when` on a distinct column, MNAR requires `when` targeting the missing column itself.
- **Condition evaluation with operators**:
  - `src/tabalyst/generate_anomalies.py` supports comparison prefixes (`>=`, `<=`, `>`, `<`, `!=`) for numeric thresholds and ISO dates.
- **Traceability in ground truth**:
  - `truth.csv`: `group_id` records `missing:<mechanism>:<reason>`. The clean value before blanking is preserved in `canonical_value` on the `injected` row, providing reference truth for imputation benchmarks.
  - `metrics.json`: `ScenarioMetrics` carries `missing_mechanism` and `missing_reason`. Top-level member `missing_data` (`MissingDataMetrics`) aggregates events, rows touched, columns, and scenarios by mechanism, counts by reason, and column-by-mechanism contingency matrix.
  - Updated committed JSON schema `src/tabalyst/schemas/tabalyst.generate.metrics.schema.json`.
- **Quality profile `missing_mechanisms`**:
  - Added to `src/tabalyst/generate_examples/insurance/dataset.yaml` with floor `min_rows: 10000`, covering MCAR, MAR, MNAR, all 5 reasons, and 4 concentration modes (uniform, Ontario branch, agency AG-QC-001, and post-2024 periods).
- **Testing**:
  - 6 new contract tests in `tests/test_generate_insurance_v2_contract.py` (100 contract tests passing).
- `generation_version` stays 2.

## Temporal drift, rule validity periods, source_system and schema_drift profile (lot 12, 2026-11-17)

- **Temporal rule validity & periods (§13)**:
  - Added `RulePeriod` model (`start`, `end`, `description`) to `Conventions.periods` in `src/tabalyst/generate_rules.py`.
  - Declared named periods in `src/tabalyst/generate_examples/insurance/rules.yaml`: `legacy_tariff` (<= 2023-12-31), `migration_ontario` (>= 2023-06-01), `schema_v2` (>= 2024-01-01), and `modern_tariff` (>= 2025-01-01).
  - Extended `Rule` model with `valid_from`, `valid_until`, `temporal_column` (defaults to `date_debut`), and `period`.
  - Added temporal filtering to `RuleEvaluator`: rows are evaluated against a rule only if their date in `temporal_column` falls within `[valid_from, valid_until]` (or period window).
  - Added temporal business rules catalogue M26 through M30 in `rules.yaml`:
    - M26: post-2024 schema version v2.0/v2.1 consistency;
    - M27: post-migration Ontario core system consistency;
    - M28: observation date vs creation date chronological coherence (`date_creation <= date_observation`);
    - M29: legacy v1.0 schema version prior to 2024-01-01;
    - M30: post-2025 regulatory home deductible minimum floor (`franchise >= 500.00`).
- **Tranche C columns & complete profile (Contract 7, §13)**:
  - Added 3 tranche C columns: `date_observation`, `version_source`, and `source_system`.
  - Added to `OUTPUT_PROFILES["complete"]`: total 50 columns on branch files and 51 columns on `insurance-combined.csv` (with `filiale`).
  - Flattened multi-contract profile `flattened-complete` aligned to 51 columns.
  - Deterministic independent generation stream per column preserves strict byte-level non-regression on all default and extended columns.
- **Scenario profile `schema_drift`**:
  - Added to `src/tabalyst/generate_examples/insurance/dataset.yaml` with floor `min_rows: 10000`, 8 scenarios, 800 events:
    - IT migrations: `SD_SYS_MIG` (100 cases, M27), `SD_VER_MIG` (100 cases, M26), `SD_FMT_MIG` (100 cases, syntactic telephone defect);
    - Anachronisms: `SD_OBS_ANACH` (50 cases, M28), `SD_VER_PREMAT` (50 cases, M29);
    - Regulatory tariff drift: `SD_DEDUCT_REG` (100 cases, M30);
    - Valid atypical drift: `SD_CHAN_DRIFT` (200 cases, web shift) and `SD_LEGACY_VAL` (100 cases, grandfathered pre-2025 deductibles).
  - Automatically defaults `effective_output` to `complete` when `--output-profile` is omitted.
- **Traceability in `metrics.json` and JSON schemas**:
  - `TemporalDriftMetrics` added to `metrics.json` carrying `active_periods`, `drift_scenarios`, and exact violations for `temporal_rules`.
  - Updated committed JSON schemas `src/tabalyst/schemas/tabalyst.generate.rules.schema.json` and `tabalyst.generate.metrics.schema.json`.
- **Testing**:
  - 5 new contract tests in `tests/test_generate_insurance_v2_contract.py` (105 contract tests passing).
- `generation_version` stays 2.

## Synthetic fraud, hard cases, noise and delayed labels, ml_labels.csv (lot 13, 2026-11-17)

- **Separate ground-truth label file `<dataset>.<profile>.ml_labels.csv` (SRS §8, §15, Lot 13)**:
  - Isolates supervised machine learning targets and continuous latent probabilities from input features.
  - 7 standard columns: `row_number`, `id_contrat`, `is_fraud`, `observed_label`, `confirmation_date`, `fraud_type`, `latent_probability`.
  - Registered in `manifest.json` with role `"ml_labels"`, carrying byte size and SHA-256 digest.
  - New committed schema `src/tabalyst/schemas/tabalyst.generate.ml_labels.schema.json` formalizing format `tabalyst.generate.ml_labels`, version `0.2.0`, revision 1.
- **Synthetic fraud patterns without trivial artifacts (SRS §8)**:
  - Modeled independently from technical format errors; all fraud rows satisfy contractual and business validity constraints (0 rule violations).
  - 4 realistic multi-class fraud typologies (ML04):
    - `phantom_claim`: expedited claims reported rapidly after policy inception without third-party physical injury;
    - `inflated_claim`: genuine loss with exaggerated claim amount staying within policy coverage caps;
    - `collusion`: concentrated suspicious claims through designated high-risk broker;
    - `organized_fraud`: coordinated ring with clustered claims across related contracts.
  - Imbalanced class prevalence rates:
    - 1% overall fraud rate (ML01);
    - 0.1% rare fraud class (ML02, `ML02_RARE_01PCT`);
    - 0.01% extremely rare single case (ML03, `ML03_EXTREME`).
- **Hard cases and continuous latent probability overlap (ML05)**:
  - Frauds share continuous distributions overlapping with clean policyholders; `latent_probability` provides continuous boundary uncertainty in `[0.45, 0.65]`.
- **Plausible false positives and valid atypicals (ML06, ML20)**:
  - Benign policyholders (`is_fraud = 0`, `category = valid_atypical`, `expected_detection = none`) exhibiting elevated suspicion traits for unsupervised anomaly detection benchmarks.
- **Label noise and delayed operational labels (ML07, ML08)**:
  - Operational tracking label noise (ML07): false negatives (`is_fraud = 1`, `observed_label = "0"`) and false positives (`is_fraud = 0`, `observed_label = "1"`).
  - Delayed unresolved investigations (ML08): open claims lacking confirmation (`observed_label = ""`, `confirmation_date = ""`).
- **Profile `ml_fraud_imbalanced`**:
  - Added to `dataset.yaml` with `min_rows: 10000`, 11 scenarios covering ML01 through ML08 and ML20.
  - Defaults `effective_output` to `extended` (44 columns on `insurance-combined.csv`).
- **Metrics integration**:
  - `MetricsDocument` carries `ml_fraud: MLFraudMetrics` tracking total rows, true frauds, observed frauds, counts per fraud type, rates, label noise, delayed labels, and atypical normal cases.
- **Testing**:
  - 8 new contract tests in `tests/test_generate_insurance_v2_contract.py` (total 113 contract tests passing).
- `generation_version` stays 2.





