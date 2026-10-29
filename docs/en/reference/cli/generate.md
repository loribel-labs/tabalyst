---
title: "CLI: tabalyst generate"
description: The inputs, outputs and options of the tabalyst generate command.
---

`tabalyst generate` validates a Generate package and writes synthetic CSV data.
The command exists since Tabalyst 0.6.2; packages, `--example computer` and the
options marked Computer need 0.7.0 or later. See
[Tabalyst Generate](../../generate/index.md) for a walkthrough.

```text
tabalyst generate PACKAGE (-o FILE.csv | -d DIR) [options]
tabalyst generate --example NAME (-o FILE.csv | -d DIR) [options]
tabalyst generate (PACKAGE | --example NAME) --validate-only
```

Provide exactly one source: a package directory or its `dataset.yaml`, or
`--example crm`, `--example insurance` or `--example computer`. Exactly one
destination is required, except with `--validate-only`. A
`definition_version: 1` YAML file stops the command with `PACKAGE_FORMAT`.

| Option | Meaning |
| --- | --- |
| `--example NAME` | Use the packaged `crm`, `insurance` or `computer` example. |
| `-o`, `--output FILE` | Write one CSV. Computer: one locale (English unless `--locales fr`); with `--anomaly-profile`, the CSV holds the errors and `FILE.changes.csv` lists the changed cells, with no clean copy, summary or metadata. |
| `-d`, `--output-dir DIR` | Write all planned artifacts to a directory. |
| `--rows N` | Override the generated row count; for insurance, allocate the combined total across its branches. |
| `--seed INTEGER` | Override the root random seed. |
| `--as-of-date YYYY-MM-DD` | Override the reference date. |
| `--anomaly-profile NAME` | Produce the selected anomaly variant, cell change log and summary (with `-d`). Computer: `dirty_realistic`, `dirty_stress`, `unit_variants`, `unit_variants_extended`. An unknown name lists the available ones. |
| `--request FILE` | Read `rows`, `seed`, `as_of_date`, `generation_profile`, `output_profile`, `market`, `locales`, `unit_style`, `unit_columns` and `anomaly_profile` from a JSON object. Explicit options win. |
| `--generation-profile NAME` | Computer: bias the catalog selection. |
| `--output-profile NAME` | Computer: choose the columns written (`compact`, `standard`, `extended`). |
| `--market ca\|us` | Computer: the offer market. |
| `--locales en\|fr\|en,fr` | Computer: the languages written. Default `en,fr` with `-d`, `en` with `-o`. |
| `--unit-style numeric\|localized` | Computer: plain numbers or values with units. |
| `--unit-columns A,B` | Computer: the measurement columns to write with units; implies `localized`. |
| `--validate-only` | Validate the package and write nothing. |
| `-f`, `--force` | Replace existing generated artifacts. |

Explicit options override package defaults. Paths are checked before generation;
the package and packaged resources cannot be overwritten. A selected
anomaly profile keeps the clean CSV alongside its altered variant.
