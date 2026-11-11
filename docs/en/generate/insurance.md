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
Created: insurance-output/insurance-principal.csv
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
| `insurance-principal.csv` | 73% | 200,000 | 2,182 |
| `insurance-ontario.csv` | 9% | 25,000 | 273 |
| `insurance-quebec.csv` | 18% | 50,000 | 545 |
| `insurance-combined.csv` | 100% | 275,000 | 3,000 |

The combined file has the same 33 columns as a branch plus `filiale`, which
names the branch of the row (`principal`, `ontario` or `quebec`): 34 columns
in all. The columns and their values are in French, as in a Quebec insurer.

## What the files hold

| Group | Columns |
| --- | --- |
| Customer (7) | `id_client` (`CLI-00000001`, ...), `civilite`, `prenom`, `nom`, `date_naissance`, `sexe`, `langue_preferee` |
| Address (10) | `numero_voie`, `type_voie`, `nom_voie`, `orientation`, `appartement`, `ville`, `province_code`, `province_nom`, `code_postal`, `pays_code` |
| Contact (2) | `courriel`, `telephone` |
| Contract (9) | `id_contrat`, `type_contrat`, `date_debut`, `date_fin`, `statut_contrat`, `prime_annuelle`, `frequence_paiement`, `mode_paiement`, `agence_code` |
| Record (2) | `date_creation`, `date_modification` |
| Claim (3) | `date_reclamation`, `montant_reclamation`, `reclamation_status` |

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
Created: out/insurance-principal.csv
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
Created: out/insurance-principal.csv
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
| `end_before_start` | `date_fin` set to `2016-01-01`, before every start (principal branch) | 797 |
| `status_vs_end_date` | `statut_contrat` set to `actif` on an expired contract | 1,495 |
| `amount_vs_claim_status` | `montant_reclamation` emptied on a `fermé` claim | 309 |
| `claim_status_without_date` | `reclamation_status` set to `ouvert` without a claim | 707 |
| `civilite_vs_sexe` | `civilite` set to `M.` for a woman | 557 |
| `province_name_vs_code` | `province_nom` set to `Ontario` for a Quebec code | 618 |
| `agency_vs_branch` | `agence_code` of the Ontario branch in the Quebec branch | 149 |
| `customer_under_18` | `date_naissance` set to `2015-05-05` (principal branch) | 400 |
| `payment_vs_frequency` | `mode_paiement` set to `chèque` on a monthly payment | 543 |

A rule applies only to the rows it targets, such as the expired contracts,
so the number of rows changed depends on the data. The summary gives it for
every operation. The dates are replaced in the principal branch only, whose
dates are ISO, so a broken rule never comes with a format defect.

## Next steps

- [Tabalyst Generate](index.md) explains packages and how to write your own
  anomaly profile.
- The [CLI reference](../reference/cli/generate.md) lists every option.
- [Tabalyst Report](../report/index.md) analyzes a generated file, with its
  gaps and duplicates.
- [Generate CRM contacts](crm.md) and
  [Generate computer offers](computer.md) describe the other examples.
