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

Some rules tie the values together:

- Names are English or French in about equal parts, and the cities, province
  codes and postal codes belong to Canada.
- `lifecycle_stage` is `Lead`, `Qualified`, `Opportunity` or `Customer`, and
  `lead_status` follows it: `New`, `Working`, `Negotiating` or `Converted`.
- About two thirds of the contacts have no opportunity: their
  `opportunity_stage` reads `None` and `opportunity_amount` is empty. The
  others have a stage (`Discovery`, `Proposal`, `Negotiation`, `Closed Won` or
  `Closed Lost`), an amount, a probability from 0 to 100 and a close date.
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
5,000 rows in 1.6s (3,039 rows/s), 2,109 cells changed
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
| `opportunity_probability` | Set to `120`, beyond the range | 1% |

A defect that cannot apply to a row, such as emptying a cell that is already
empty, is not counted: the summary reports the rows requested, applied and
skipped for every operation. Because the log names each changed cell, a
profile of the altered file can be checked against what was injected, for
example with [Tabalyst Report](../report/index.md).

## Next steps

- [Tabalyst Generate](index.md) explains packages and how to write your own
  anomaly profile.
- The [CLI reference](../reference/cli/generate.md) lists every option.
- [Generate computer offers](computer.md) and
  [Generate insurance customers](insurance.md) describe the other examples.
