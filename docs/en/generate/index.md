---
title: Tabalyst Generate
description: How to create synthetic CSV datasets from a YAML definition or the packaged CRM and insurance examples.
---

Tabalyst Generate creates synthetic CSV datasets for tests, demonstrations and
teaching. Install Tabalyst 0.6.2 or later to use `tabalyst generate`.

```console
tabalyst generate --example crm -o crm-contacts.csv
tabalyst generate --example insurance --rows 3000 -d insurance-output/
```

The CRM example creates one contacts CSV. Insurance creates three branch CSVs
and one combined CSV. With `--rows 3000`, the branches contain 2,182, 273 and
545 rows. These are synthetic records; the current public insurance report
uses a separate dataset and remains unchanged.

## Use a definition

Pass a YAML definition instead of `--example`:

```console
tabalyst generate examples/generate/input/crm.yaml -o contacts.csv
```

The definition must use `definition_version: 1` and declare its datasets and
columns. See the editable [CRM and insurance definitions](https://github.com/loribel-labs/tabalyst/tree/main/examples/generate/input)
for complete examples. The definition format is experimental during beta.

## Create an anomaly variant

An anomaly profile adds an altered CSV, a cell change log and a JSON summary
beside an untouched clean CSV. The insurance profile changes only the combined
dataset:

```console
tabalyst generate --example insurance --rows 3000 --anomaly-profile dirty_realistic -d insurance-dirty/
```

Choose `-o` only when the result is one clean CSV. Use `-d` for multiple CSVs
or an anomaly profile. Existing output files require `--force`. Nothing is
written beside the definition or into the current directory by default.

Use `--seed` and `--as-of-date YYYY-MM-DD` to override the definition defaults.
Generation is reproducible with the same definition, options and environment.
The [CLI reference](../reference/cli/generate.md) lists all options.
