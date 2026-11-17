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


