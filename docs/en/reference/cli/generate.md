---
title: "CLI: tabalyst generate"
description: The inputs, outputs and options of the tabalyst generate command.
---

`tabalyst generate` validates a Generate package and writes synthetic CSV data.
The command exists since Tabalyst 0.6.2; packages, `--example computer` and the
options marked Computer need 0.7.0 or later. `-o` and `--locales en` or `fr` for
Computer, several names in `--anomaly-profile`, `--workers`, `--no-progress` and
the progress and timing output need 0.7.3 or later. See
[Tabalyst Generate](../../generate/index.md) for a walkthrough.

```text
tabalyst generate PACKAGE (-o FILE.csv | -d DIR) [options]
tabalyst generate --example NAME (-o FILE.csv | -d DIR) [options]
tabalyst generate (PACKAGE | --example NAME) --validate-only
tabalyst generate [PACKAGE | --example NAME] --list-profiles
```

Provide exactly one source: a package directory or its `dataset.yaml`, or
`--example crm`, `--example insurance` or `--example computer`. Exactly one
destination is required, except with `--validate-only` and `--list-profiles`. A
`definition_version: 1` YAML file stops the command with `PACKAGE_FORMAT`.

| Option | Meaning |
| --- | --- |
| `--example NAME` | Use the packaged `crm`, `insurance` or `computer` example. |
| `-o`, `--output FILE` | Write one CSV. Computer: one locale (English unless `--locales fr`); with `--anomaly-profile`, the CSV holds the errors and `FILE.changes.csv` lists the changed cells, with no clean copy, summary or metadata. |
| `-d`, `--output-dir DIR` | Write all planned artifacts to a directory. |
| `--rows N` | Override the generated row count; for insurance, allocate the combined total across its branches. |
| `--seed INTEGER` | Override the root random seed. |
| `--as-of-date YYYY-MM-DD` | Override the reference date. |
| `--anomaly-profile NAME` | Produce the selected anomaly variant, cell change log and summary (with `-d`). Available across packages (Computer, CRM, Insurance). Give several names separated by commas (`--anomaly-profile a,b`) to get one variant of each (with `-d`). An unknown name lists the available ones. |
| `--list-profiles` | List available anomaly profiles for the package, or for all built-in examples when used without a package. |
| `--request FILE` | Read `rows`, `seed`, `as_of_date`, `generation_profile`, `output_profile`, `market`, `locales`, `unit_style`, `unit_columns` and `anomaly_profile` from a JSON object. Explicit options win. |
| `--generation-profile NAME` | Computer: bias the catalog selection. |
| `--output-profile NAME` | Choose the columns written. Computer: `compact`, `standard`, `extended`. Insurance: `default` (33 columns on branches, 34 combined), `extended` (43 columns on branches, 44 combined), `complete` (50 columns on branches, 51 combined), or flattened profiles (`flattened`, `flattened-extended`, `flattened-complete`). |
| `--relational` | Insurance: generate 4 relational tables (`customers.csv`, `contracts.csv`, `claims.csv`, `payments.csv` in English; `clients.csv`, `contrats.csv`, `reclamations.csv`, `paiements.csv` in French) alongside their full ground truth. |
| `--row-order NAME` | Insurance: choose contract ordering (`default`, `branch`, `chronological`, `agency`, `shuffled`). |
| `--english` | Insurance: backward-compatible alias for `--locales en`. |
| `--market ca\|us` | Computer: the offer market. |
| `--locales en\|fr\|en,fr` | Locales to generate. Insurance: defaults to `en` (`insurance-main.csv`), with `fr` (`insurance-principal.csv`) or `en,fr`. Computer: defaults to `en,fr` with `-d`, `en` with `-o`. |
| `--unit-style numeric\|localized` | Computer: plain numbers or values with units. |
| `--unit-columns A,B` | Computer: the measurement columns to write with units; implies `localized`. |
| `--validate-only` | Validate the package and write nothing. |
| `-f`, `--force` | Replace existing generated artifacts. |
| `--no-progress` | Hide the progress line. It is also hidden outside a terminal. |
| `--workers N` | Computer: processes that generate the rows; 1 uses one process. By default, 5,000 rows or more use one per spare processor, at most 6. |

In a terminal, the command shows its progress on one line that is rewritten
as the work advances, with the time spent and an estimate of the time left:

```text
Generating rows 8,000/20,000 (40%) - 4.4s, about 6.6s left
Injecting errors (en) 20,000/20,000 (100%) - 0.6s
```

When it ends, it prints the files it created and a closing line with the
number of rows, the total time, the rate, the number of changed cells and where
the time went. This line is printed outside a terminal too, so a log keeps it:

```text
Created: pcs.csv
Created: pcs.changes.csv
20,000 rows in 9.2s (2,170 rows/s), 5,672 cells changed: generating rows 8.7s, injecting errors 0.5s
```

With several processes, the line gives their number, for example
`(5,495 rows/s, 3 processes)`. The files are the same whatever the number of
processes, so a seed still gives the same data.

Explicit options override package defaults. Paths are checked before generation;
the package and packaged resources cannot be overwritten. A selected
anomaly profile keeps the clean CSV alongside its altered variant.

An insurance scenario profile (its operations declare `scenario_id`) also
writes `<dataset>.<profile>.truth.csv`, `.rules.json`, `.metrics.json` and
`.manifest.json`, published with the other files and protected the same way:
an existing one needs `--force`. See
[Insurance ground truth files](../../generate/insurance-ground-truth.md).
A profile can set a minimum number of rows: `rare_events` stops below
100,000 rows, while other V2 scenario profiles (`format_vs_business`,
`anomaly_diversity`, `clustered_errors`, `missing_mechanisms`, `schema_drift`,
`ml_fraud_imbalanced`, `ml_leakage_test`, `ml_multitask`, `technical_stress`) stop
below 10,000 rows, naming the profile, the floor and the rows requested.
Insurance generates English by default (`insurance-main.csv`, English headers,
Anglo-Saxon demographics, and relational tables `customers`, `contracts`, `claims`, `payments`).
Use `--locales fr` for French (`insurance-principal.csv`, French demographics, `clients`, etc.)
or `--locales en,fr` for both. The `--english` option is retained as an alias for `--locales en`.
See [Insurance rare events](../../generate/insurance-rare-events.md) and
[Generate insurance customers](../../generate/insurance.md).
