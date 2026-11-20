---
title: Generate insurance customers
description: How to create synthetic insurance customer files for three branches and one combined file, which rules tie their columns, and which defects the dirty_realistic, dirty_stress and rule_breaks profiles inject.
---

The insurance example creates the customer files of a fictional insurer: one
CSV for each of three branches and one combined CSV that stacks them. Each row
is a customer with an address, one contract and, sometimes, one claim.

```console
tabalyst generate --example insurance --rows 3000 -d insurance-output/
```

```text
Created: insurance-output/insurance-main.csv
Created: insurance-output/insurance-ontario.csv
Created: insurance-output/insurance-quebec.csv
Created: insurance-output/insurance-combined.csv
Done in 2.6s
```

The command needs `-d`, since it writes several files. The times come from one
machine and are not a promise.

## The branches

`--rows` is the total of the combined file, shared across the branches in
fixed proportions. Without `--rows`, the default is 275,000 rows.

| File | Share | Rows by default | Rows with `--rows 3000` |
| --- | ---: | ---: | ---: |
| `insurance-main.csv` | 73% | 200,000 | 2,182 |
| `insurance-ontario.csv` | 9% | 25,000 | 273 |
| `insurance-quebec.csv` | 18% | 50,000 | 545 |
| `insurance-combined.csv` | 100% | 275,000 | 3,000 |

To unify and simplify file naming, the primary branch is always named
`insurance-main.csv` in all locales. The legacy name `insurance-principal.csv` is
no longer used.

The combined file has the same 33 columns as a branch plus `branch` (`filiale` in French), which
names the branch of the row (`main`, `ontario` or `quebec` in English; `principal`, `ontario` or `quebec` in French): 34 columns
in all. By default, columns and values are in English; pass `--locales fr` for French, or `--locales en,fr` for both.

## What the files hold

| Group | Columns |
| --- | --- |
| Customer (7) | `id_client` (`CLI-00000001`, ...), `civilite`, `prenom`, `nom`, `date_naissance`, `sexe`, `langue_preferee` |
| Address (10) | `numero_voie`, `type_voie`, `nom_voie`, `orientation`, `appartement`, `ville`, `province_code`, `province_nom`, `code_postal`, `pays_code` |
| Contact (2) | `courriel`, `telephone` |
| Contract (9) | `id_contrat`, `type_contrat`, `date_debut`, `date_fin`, `statut_contrat`, `prime_annuelle`, `frequence_paiement`, `mode_paiement`, `agence_code` |
| Record (2) | `date_creation`, `date_modification` |
| Claim (3) | `date_reclamation`, `montant_reclamation`, `reclamation_status` |

### Extended output profile

Pass `--output-profile extended` to append 10 domain columns after the base
columns:

```console
tabalyst generate --example insurance -d out/ --output-profile extended
```

| Group | Columns |
| --- | --- |
| Claim detail (4) | `date_sinistre`, `montant_couverture`, `franchise`, `montant_indemnise` |
| Contract detail (2) | `date_resiliation`, `statut_paiement` |
| Distribution (3) | `canal_acquisition`, `courtier_id`, `produit_code` |
| Activity (1) | `nombre_reclamations` |

Branch files have 43 columns; `insurance-combined.csv` keeps `filiale` in
35th position and has 44 columns. The clean files enforce domain invariants:
`date_sinistre` precedes `date_reclamation`, `montant_indemnise` never exceeds
coverage minus deductible, `date_resiliation` exists only on cancelled
contracts, and `courtier_id` is populated only when `canal_acquisition` is
`courtier`.

### Complete output profile

Pass `--output-profile complete` to append tranche B and tranche C columns after the extended
columns:

```console
tabalyst generate --example insurance -d out/ --output-profile complete
```

| Group | Columns |
| --- | --- |
| Tranche B (4) | `taux_remboursement`, `consentement_communication`, `gestionnaire_id`, `segment_client` |
| Tranche C (3) | `date_observation`, `version_source`, `source_system` |

Branch files have 50 columns; `insurance-combined.csv` has 51 columns (with `filiale`).
All columns satisfy strict domain rules: `taux_remboursement` is a bounded decimal
between `0.00` and `1.00`, `consentement_communication` is a boolean indicator,
`gestionnaire_id` follows the `GES-XXX` pattern, `segment_client` belongs to
`particulier`, `professionnel`, `entreprise` or `vip`, and tranche C captures
software versions (`v1.0`, `v2.0`, `v2.1`) and origin IT systems (`SYS_PRI`, `SYS_QC`,
`SYS_ON_CORE`, `SYS_ON_LEGACY`).

## Locales and languages

The insurance generator supports English and French. The underlying random draws
and entity properties remain deterministic: generating with the same seed
produces identical customer records, localized to the chosen language.

### English (default: `--locales en`)

By default, Insurance generates customer files in English:

```console
tabalyst generate --example insurance --rows 3000 -d out/
```

- **File names**: `insurance-main.csv`, `insurance-ontario.csv`, `insurance-quebec.csv`, and `insurance-combined.csv`.
- **Headers**: English column names (`customer_id`, `title`, `first_name`, `last_name`, `branch`, `annual_premium`, etc.).
- **Demographics & honorifics**: Anglo-Saxon first names and surnames; honorific titles `Mr.` and `Ms.`.
- **Categorical values**: English terms (`auto`, `home`, `life`, `travel` for contract types; `active`, `expired`, `suspended`, `cancelled` for contract statuses; `open`, `in_progress`, `closed`, `rejected` for claim statuses; `main`, `ontario`, `quebec` for branch).
- **Relational mode (`--relational`)**: generates `customers.csv`, `contracts.csv`, `claims.csv`, and `payments.csv`.

`--english` is retained as a backward-compatible alias for `--locales en`.

### French (`--locales fr`)

Pass `--locales fr` to generate customer files in French:

```console
tabalyst generate --example insurance --rows 3000 -d out/ --locales fr
```

- **File names**: `insurance-main.csv` (unified with English, replacing `insurance-principal.csv`), `insurance-ontario.csv`, `insurance-quebec.csv`, and `insurance-combined.csv`.
- **Headers**: French column names (`id_client`, `civilite`, `prenom`, `nom`, `filiale`, `prime_annuelle`, etc.), matching the column lists in [What the files hold](#what-the-files-hold).
- **Demographics & honorifics**: French first names and surnames; honorific titles `M.` and `Mme`.
- **Categorical values**: French terms (`auto`, `habitation`, `vie`, `voyage` for contract types; `actif`, `expiré`, `suspendu`, `résilié` for contract statuses; `ouvert`, `en_cours`, `fermé`, `rejeté` for claim statuses; `principal`, `ontario`, `quebec` for filiale).
- **Relational mode (`--relational`)**: generates `clients.csv`, `contrats.csv`, `reclamations.csv`, and `paiements.csv`.

### Both locales simultaneously (`--locales en,fr`)

Pass `--locales en,fr` to generate both variants in one command:

```console
tabalyst generate --example insurance --rows 3000 -d out/ --locales en,fr
```

```text
Created: out/insurance-main-en.csv
Created: out/insurance-ontario-en.csv
Created: out/insurance-quebec-en.csv
Created: out/insurance-combined-en.csv
Created: out/insurance-main-fr.csv
Created: out/insurance-ontario-fr.csv
Created: out/insurance-quebec-fr.csv
Created: out/insurance-combined-fr.csv
Done in 3.1s
```

When writing both locales, file stems receive `-en` and `-fr` suffixes so both sets coexist cleanly in the target directory. The primary branch is symmetrically named `insurance-main-en.csv` and `insurance-main-fr.csv`.

In relational mode (`--relational --locales en,fr`), both English tables (`customers.csv`, `contracts.csv`, `claims.csv`, `payments.csv`) and French tables (`clients.csv`, `contrats.csv`, `reclamations.csv`, `paiements.csv`) are written side-by-side.

### Column mapping between locales

The tables in [What the files hold](#what-the-files-hold) list the native French column identifiers. When generating in English (the default), headers are translated as follows:

| French column (`--locales fr`) | English column (default / `--locales en`) | Output profile |
| --- | --- | --- |
| `id_client` | `customer_id` | Base |
| `civilite` | `title` | Base |
| `prenom` | `first_name` | Base |
| `nom` | `last_name` | Base |
| `date_naissance` | `birth_date` | Base |
| `sexe` | `gender` | Base |
| `langue_preferee` | `preferred_language` | Base |
| `numero_voie` | `street_number` | Base |
| `type_voie` | `street_type` | Base |
| `nom_voie` | `street_name` | Base |
| `orientation` | `street_direction` | Base |
| `appartement` | `unit_number` | Base |
| `ville` | `city` | Base |
| `province_code` | `province_code` | Base |
| `province_nom` | `province_name` | Base |
| `code_postal` | `postal_code` | Base |
| `pays_code` | `country_code` | Base |
| `courriel` | `email` | Base |
| `telephone` | `phone` | Base |
| `id_contrat` | `contract_id` | Base |
| `type_contrat` | `contract_type` | Base |
| `date_debut` | `start_date` | Base |
| `date_fin` | `end_date` | Base |
| `statut_contrat` | `contract_status` | Base |
| `prime_annuelle` | `annual_premium` | Base |
| `frequence_paiement` | `payment_frequency` | Base |
| `mode_paiement` | `payment_method` | Base |
| `agence_code` | `agency_code` | Base |
| `date_creation` | `creation_date` | Base |
| `date_modification` | `modification_date` | Base |
| `date_reclamation` | `claim_date` | Base |
| `montant_reclamation` | `claim_amount` | Base |
| `reclamation_status` | `claim_status` | Base |
| `filiale` (combined file) | `branch` (combined file) | Base |
| `date_sinistre` | `loss_date` | Extended |
| `montant_couverture` | `coverage_amount` | Extended |
| `franchise` | `deductible` | Extended |
| `montant_indemnise` | `indemnity_amount` | Extended |
| `date_resiliation` | `cancellation_date` | Extended |
| `statut_paiement` | `payment_status` | Extended |
| `canal_acquisition` | `acquisition_channel` | Extended |
| `courtier_id` | `broker_id` | Extended |
| `produit_code` | `product_code` | Extended |
| `nombre_reclamations` | `claim_count` | Extended |
| `taux_remboursement` | `reimbursement_rate` | Complete (Tranche B) |
| `consentement_communication` | `communication_consent` | Complete (Tranche B) |
| `gestionnaire_id` | `manager_id` | Complete (Tranche B) |
| `segment_client` | `customer_segment` | Complete (Tranche B) |
| `date_observation` | `observation_date` | Complete (Tranche C) |
| `version_source` | `source_version` | Complete (Tranche C) |
| `source_system` | `source_system` | Complete (Tranche C) |

The values follow the rules of the domain, and the clean files hold no
exception to them, so they can serve to test analyses across columns:

- `type_contrat` is `auto`, `habitation`, `voyage` or `vie`, and
  `statut_contrat` is `actif`, `expiré`, `suspendu` or `résilié`. The end date
  of a contract depends on its status, and a contract starts after the
  customer's 18th birthday.
- A `voyage` contract covers one trip of 3 to 90 days, started in the last
  three years: it is `expiré` once its end date has passed, `actif` before.
- Premiums are amounts with two decimals, drawn in a range that depends on
  the product, then priced by age: an `auto` premium costs 1.8 times more
  before 25 and 1.3 times more before 30, a `vie` premium grows with age, and
  `voyage` costs 1.5 times more from 65. They are illustrative, not pricing
  guidance.
- `frequence_paiement` is monthly, quarterly, half-yearly or annual, and
  `mode_paiement` is direct debit, card, transfer or cheque. A monthly
  payment is always a direct debit or a card.
- About one customer in seven has a claim: `date_reclamation`,
  `montant_reclamation` and `reclamation_status` (`ouvert`, `en_cours`,
  `fermé` or `rejeté`) are empty for the others. A claim falls within its
  contract. One older than a year is `fermé` or `rejeté`, and one under a
  month is `ouvert` or `en_cours`. Claim amounts are many small ones and a few
  large ones (a log-normal draw), and a `fermé` claim always has an amount.
- `date_modification` comes after `date_creation` and after the claim, the
  last event of the record.
- Agency codes belong to fictional agencies linked to cities. A customer goes
  to the agency of their city when the branch has one, else to an agency of
  their province, else to any agency of the branch. Most customers are in
  Quebec.
- `courriel` is empty for about 2% of the customers under 50, 8% from 50 to 69
  and 25% from 70.
- Email addresses use the reserved `.example` domain and phone numbers use
  the fictitious `555` range.

These are synthetic records made for tests and demonstrations. They do not
come from an insurer or from an actuarial study.

## Add defects on purpose

An anomaly profile keeps all four clean files and adds an altered copy of the
combined file, a log of every changed cell and a JSON summary. The branch files
are never altered.

### A few realistic defects

`dirty_realistic` touches a handful of columns on a small share of the rows:

```console
tabalyst generate --example insurance --rows 3000 -d out/ --anomaly-profile dirty_realistic
```

```text
Created: out/insurance-main.csv
Created: out/insurance-ontario.csv
Created: out/insurance-quebec.csv
Created: out/insurance-combined.csv
Created: out/insurance-combined.dirty_realistic.csv
Created: out/insurance-combined.dirty_realistic.changes.csv
Created: out/insurance-combined.dirty_realistic.summary.json
Done in 1.7s, 618 cells changed
```

| Column | Defect | Rows |
| --- | --- | ---: |
| `courriel` | Emptied | 4% |
| `courriel` | Copied from another row, which creates duplicates | 2% |
| `telephone` | Spaces inside the number | 5% |
| `code_postal` | Emptied | 2% |
| `pays_code` | Replaced by `Canada` instead of the code | 2% |
| `type_contrat` | Written in capitals | 3% |
| `prime_annuelle` | Emptied | 1% |
| `nom` | Written in capitals | 2% |

### A fixed number of each kind of defect

`dirty_stress` gives 45 kinds of defect a fixed number of rows each, however
many rows you generate: a missing digit in 20 client identifiers
(`id_client_missing_digit`), a doubled space in 54 postal codes
(`code_postal_double_space`), a typo in 79 family names (`nom_typo`), 8
duplicated rows (`duplicate_rows`) and one negative claim amount
(`claim_amount_negative`), among others. Two defects never share a row, so
each defective row belongs to one kind.

```console
tabalyst generate --example insurance --rows 3000 -d out/ --anomaly-profile dirty_stress
```

```text
Created: out/insurance-main.csv
Created: out/insurance-ontario.csv
Created: out/insurance-quebec.csv
Created: out/insurance-combined.csv
Created: out/insurance-combined.dirty_stress.csv
Created: out/insurance-combined.dirty_stress.changes.csv
Created: out/insurance-combined.dirty_stress.summary.json
Done in 2.8s, 1,064 cells changed
```

The change log has a `class` column with the name of the kind of each
change, so you can count what was injected and compare it with what a
profile of the file finds. The profile needs enough rows for its fixed
counts: it stops with an error on a file that is too small, about 1,000 rows
or more.

### Break the rules on purpose

`rule_breaks` leaves the formats alone and breaks the rules that tie the
columns together, so an analysis across columns can be measured against
known exceptions. Each change carries its `class` in the change log:

```console
tabalyst generate --example insurance -d out/ --anomaly-profile rule_breaks
```

| Class | What changes | Rows changed by default |
| --- | --- | ---: |
| `end_before_start` | `date_fin` set to `2016-01-01`, before every start (main branch) | 797 |
| `status_vs_end_date` | `statut_contrat` set to `actif` on an expired contract | 1,495 |
| `amount_vs_claim_status` | `montant_reclamation` emptied on a `fermé` claim | 309 |
| `claim_status_without_date` | `reclamation_status` set to `ouvert` without a claim | 707 |
| `civilite_vs_sexe` | `civilite` set to `M.` for a woman | 557 |
| `province_name_vs_code` | `province_nom` set to `Ontario` for a Quebec code | 618 |
| `agency_vs_branch` | `agence_code` of the Ontario branch in the Quebec branch | 149 |
| `customer_under_18` | `date_naissance` set to `2015-05-05` (main branch) | 400 |
| `payment_vs_frequency` | `mode_paiement` set to `chèque` on a monthly payment | 543 |

A rule applies only to the rows it targets, such as the expired contracts,
so the number of rows changed depends on the data. The summary gives it for
every operation. The dates are replaced in the main branch only, whose
dates are ISO, so a broken rule never comes with a format defect.

### Quality benchmark profiles

Three scenario profiles provide controlled reference benchmarks for data quality analysis and sampling comparisons (minimum 10,000 rows):

- `format_vs_business`: strictly equal counts of format variants/defects (500 cases) and business rule violations (500 cases), allowing detectors to compare format vs business sensitivity without class imbalance.
- `anomaly_diversity`: broad coverage across all 6 categories (`format_variant`, `format_invalid`, `semantic_invalid`, `business_rule_violation`, `contextual_invalid`, `valid_atypical`) and 7 detector families.
- `clustered_errors`: spatial, agency, and temporal error clusters (such as an Ontario system import batch failure with common `root_cause_id`), contrasted with diffuse anomalies across branches.

```console
tabalyst generate --example insurance -d out/ --anomaly-profile format_vs_business
```

### Multiple simultaneous profiles and profile catalog

You can inspect all available anomaly profiles for Insurance (or any package) with `--list-profiles`:

```console
tabalyst generate --example insurance --list-profiles
```

You can also generate several anomaly profiles in a single command by passing comma-separated profile names with `-d`:

```console
tabalyst generate --example insurance -d out/ --anomaly-profile format_vs_business,anomaly_diversity
```

This generates independent altered files (`insurance-combined.format_vs_business.csv`, `insurance-combined.anomaly_diversity.csv`) and their respective isolated ground-truth suites.

### Advanced scenario profiles

Insurance V2 provides dedicated scenario profiles targeting specific quality and machine learning challenges (floor: 10,000 rows):

- `missing_mechanisms`: Little & Rubin (1987) missingness models (MCAR, MAR conditioned on branches or recent years, MNAR on extreme claim and premium values) with documented reasons (`unreported`, `client_refusal`, `system_omission`, etc.).
- `schema_drift`: IT migrations, historical tariff periods, and regulatory deductible floors across timeline windows.
- `ml_fraud_imbalanced`: synthetic fraud patterns at 1%, 0.1% and 0.01% prevalence across 4 typologies without trivial artifacts, with label noise and delayed investigation labels (`ml_labels.csv`).
- `ml_leakage_test`: intentional cross-contract, temporal, and shortcut leakage benchmarks with customer-grouped and temporal partition splits (`splits.csv`).
- `ml_multitask`: comprehensive multi-target supervised benchmark combining claim occurrence, claim cost regression, and customer retention.
- `technical_stress`: volumetric stress, multiline CSV text, complex Unicode, UUID high-cardinality columns, and extreme float precision.

### Relational database generation

Pass `--relational` with `-d` to generate a normalized 4-table relational database:

```console
tabalyst generate --example insurance -d out/ --relational
```

By default (English), this publishes `customers.csv` (22 columns), `contracts.csv` (23 columns), `claims.csv` (7 columns), and `payments.csv` (7 columns) alongside their table-specific ground-truth artifacts. Pass `--locales fr` to generate French tables (`clients.csv`, `contrats.csv`, `reclamations.csv`, `paiements.csv`), or `--locales en,fr` to write both variants side-by-side.

## Next steps

- [Insurance ground truth files](insurance-ground-truth.md) explains the
  scenario profiles, whose truth, rules, metrics and manifest files describe
  exactly what a run injected.
- [Insurance rare events](insurance-rare-events.md) describes `rare_events`,
  a profile of exact, very rare cases for at least 100,000 rows.
- [Tabalyst Generate](index.md) explains packages and how to write your own
  anomaly profile.
- The [CLI reference](../reference/cli/generate.md) lists every option.
- [Tabalyst Report](../report/index.md) analyzes a generated file, with its
  gaps and duplicates.
- [Generate CRM contacts](crm.md) and
  [Generate computer offers](computer.md) describe the other examples.
