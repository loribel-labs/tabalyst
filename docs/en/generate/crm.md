---
title: Generate CRM contacts
description: How to create a synthetic CRM contacts CSV with companies, lifecycle stages and opportunities, and which defects its anomaly profile injects.
---

The CRM example creates one CSV of sales contacts, each tied to a company,
with a lifecycle stage and, for some of them, an open or closed opportunity.

```console
tabalyst generate --example crm -o crm-contacts.csv
```

```text
Created: crm-contacts.csv
20,000 rows in 3.1s (6,412 rows/s)
```

The file has 26 columns and 20,000 rows by default; `--rows` changes the
count and `--seed` the data. The same seed gives the same file. The times
above come from one machine and are not a promise.

## What the file holds

The 26 columns fall into three groups. Contacts that belong to the same
company share every company column, because they point to the same one of 400
generated companies.

| Group | Columns |
| --- | --- |
| Contact (14) | `contact_id` (`C000001`, `C000002`, ...), `first_name`, `family_name`, `person_language` (`en` or `fr`), `email`, `phone`, `job_title`, `lead_source`, `lifecycle_stage`, `lead_status`, `owner`, `marketing_opt_in`, `created_at`, `last_activity_at` |
| Company (8) | `company_id`, `company_name`, `industry`, `company_size`, `country`, `city`, `province_code`, `postal_code` |
| Opportunity (4) | `opportunity_stage`, `opportunity_amount`, `opportunity_probability`, `opportunity_close_date` |

Rules tie the values together, so the file can serve to test analyses
across columns. The clean file holds no exception to them:

- Names are English or French in about equal parts, and the cities, province
  codes and postal codes belong to Canada.
- About two thirds of the contacts have no opportunity: their
  `opportunity_stage` reads `None` and the other opportunity columns are
  empty. The others have a stage (`Discovery`, `Proposal`, `Negotiation`,
  `Closed Won` or `Closed Lost`), an amount, a probability and a close date.
- `lifecycle_stage` follows the opportunity: `Opportunity` while it is open,
  `Customer` once won, `Lead` or `Qualified` once lost, and `Lead`,
  `Qualified` or `Customer` without one. `lead_status` follows
  `lifecycle_stage`: `New`, `Working`, `Negotiating` or `Converted`.
- `opportunity_probability` follows the stage: 10 to 25 in `Discovery`, 30 to
  50 in `Proposal`, 60 to 85 in `Negotiation`, 100 when won and 0 when lost.
- The dates follow each other. `created_at` runs from 2019 to mid-2026, with
  25% more contacts each year. `last_activity_at` is never before
  `created_at`, never after 2026-09-30 and never on a weekend. An open
  opportunity closes from 2026-10-01 to 2027-09-30, a closed one from 2024 to
  2026-09-30 and never before the contact was created.
- `opportunity_amount` is drawn from 1,500 to 175,000 with many small deals
  and few large ones: the median is about 18,000 and about 3% of the amounts
  pass 100,000 (a log-normal draw). Two factors then apply. The month of
  `opportunity_close_date`: 1.1 in January, 0.8 in July, 0.7 in August, 1.2
  in September and 0.9 in December. And `company_size`: 0.5 for `1-10`, 0.8
  for `11-50`, 1.6 for `201-1000` and 2.5 for `1001+`. An amount can
  therefore fall a little under 1,500 or reach about 525,000. Last, about 60%
  of the amounts are rounded to the hundred, like a figure typed by hand, and
  the others keep their cents, like a computed quote.
- `owner` follows `province_code`, like sales territories: Jordan Tremblay,
  Taylor Roy and Morgan Lee in Quebec, Alex Chen and Morgan Lee in Ontario,
  Sam Patel in the West and the North, Alex Chen in the Atlantic provinces.
- `marketing_opt_in` is `true` for about 35% of the contacts.
- Missing values depend on other columns. `phone` is empty for about 60% of
  the contacts without an `email`, against 3% of the others.
  `last_activity_at` is empty for about 22% of the leads but 2% of the
  customers. `opportunity_amount` is empty for about 20% of the deals in
  `Discovery` and never once won.
- Email addresses use the reserved `.example` domain and phone numbers use
  the fictitious `555` range, so none of them reaches a real person.

These are synthetic records. Nothing in them comes from a customer file.

## Add defects on purpose

The `dirty_realistic` anomaly profile keeps the clean file and writes an
altered copy with a log of every changed cell. CRM needs `-d` for that, since
the result is several files:

```console
tabalyst generate --example crm --rows 5000 -d crm-dirty/ --anomaly-profile dirty_realistic
```

```text
Created: crm-dirty/crm-contacts.csv
Created: crm-dirty/crm-contacts.dirty_realistic.csv
Created: crm-dirty/crm-contacts.dirty_realistic.changes.csv
Created: crm-dirty/crm-contacts.dirty_realistic.summary.json
5,000 rows in 0.8s (6,468 rows/s), 2,557 cells changed
```

The profile touches these columns, each on the share of rows shown:

| Column | Defect | Rows |
| --- | --- | ---: |
| `email` | Emptied | 6% |
| `email` | Copied from another row, which creates duplicates | 2% |
| `email` | Replaced by `invalid-address` | 1% |
| `phone` | Emptied | 5% |
| `phone` | Spaces inside the number | 12% |
| `company_name` | Written in capitals | 3% |
| `country` | Replaced by `CA` instead of `Canada` | 6% |
| `industry` | Written in lower case | 4% |
| `lead_source` | Written in lower case | 4% |
| `opportunity_amount` | Emptied | 4% |
| `opportunity_amount` | Written `12 500,00 $`, the French currency form | 2% |
| `opportunity_amount` | Written `12500.00 CAD`, with a currency code | 1% |
| `opportunity_probability` | Set to `120`, beyond the range | 1% |
| `created_at` | Written day first, `30-09-2026` | 2% |
| `owner` | A space added at the end | 3% |
| `job_title` | Written in lower case | 3% |

A defect that cannot apply to a row, such as emptying a cell that is already
empty, is not counted: the summary reports the rows requested, applied and
skipped for every operation. Because the log names each changed cell, a
profile of the altered file can be checked against what was injected, for
example with [Tabalyst Report](../report/index.md).

## Break the rules on purpose

The `rule_breaks` profile leaves the formats alone and breaks the rules that
tie the columns together, so an analysis across columns can be measured
against known exceptions:

```console
tabalyst generate --example crm -d crm-rules/ --anomaly-profile rule_breaks
```

Each change carries a `class` in the last column of the change log, which
names the rule it breaks. With the default 20,000 rows:

| Class | What changes | Rows changed |
| --- | --- | ---: |
| `probability_vs_stage` | `opportunity_probability` set to `90` on a lost deal, or to `5` in `Negotiation` | 80 |
| `lifecycle_vs_stage` | `lifecycle_stage` set to `Customer` on a lost deal | 40 |
| `status_vs_lifecycle` | `lead_status` set to `Converted` for a `Lead` | 77 |
| `closed_in_future` | `opportunity_close_date` set to `2027-03-15` on a won deal | 19 |
| `activity_before_creation` | `last_activity_at` set to `2018-06-01`, before every `created_at` | 100 |
| `owner_vs_territory` | `owner` set to `Sam Patel` in Quebec | 87 |
| `company_name_variant` | One letter dropped from `company_name`, so a company has two names | 40 |

A rule applies only to the rows it targets, such as the lost deals, so the
number of rows changed depends on the data. The summary gives it for every
operation.

## Next steps

- [Tabalyst Generate](index.md) explains packages and how to write your own
  anomaly profile.
- The [CLI reference](../reference/cli/generate.md) lists every option.
- [Generate computer offers](computer.md) and
  [Generate insurance customers](insurance.md) describe the other examples.
