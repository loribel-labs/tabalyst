---
title: Tabalyst Generate
description: How to create synthetic CSV datasets from the packaged CRM, insurance and computer examples or from a Generate package.
---

Tabalyst Generate creates synthetic CSV datasets for tests, demonstrations and
teaching. Install Tabalyst 0.7.0 or later to use the packages described here.

```console
tabalyst generate --example crm -o crm-contacts.csv
tabalyst generate --example insurance --rows 3000 -d insurance-output/
tabalyst generate --example computer --rows 10000 -d computer-output/
```

The CRM example creates one contacts CSV. Insurance creates three branch CSVs
and one combined CSV. With `--rows 3000`, the branches contain 2,182, 273 and
545 rows. Computer creates two CSVs of product offers, `computers-en.csv` and
`computers-fr.csv`, which describe the same rows with English or French labels,
and a `computers.meta.json` summary. These are synthetic records; the current
public insurance report uses a separate dataset and remains unchanged.

## Choose what Computer writes

The Computer example has three output profiles: `compact` (40 columns),
`standard` (70) and `extended` (111). The default is `compact`; pick another
with `--output-profile`. `--generation-profile` biases the catalog towards a
kind of product (`balanced`, `consumer`, `business`, `gaming`, `creator`,
`workstation`, `enterprise`, `mixed` or `portable_only`), `--market ca|us`
selects the offer market and `--locales en,fr` the languages written.

```console
tabalyst generate --example computer -d out/ \n  --output-profile extended
```

By default, measurements are plain numbers. `--unit-style localized` writes
them with localized units (`64 Go` in the French file, `64 GB` in the
English one), and `--unit-columns memory_gb,display_size_in` limits that to the
columns you name.

## Use a package

An example is a Generate package: a directory with a `dataset.yaml` and a
`catalog.yaml`, plus the schemas and CSV tables they reference. Pass a package
directory, or its `dataset.yaml`, instead of `--example`:

```console
tabalyst generate my-package/ -d out/ --rows 500
tabalyst generate my-package/ --validate-only
```

`--validate-only` checks the package without writing anything. The package
format is experimental during beta. The older `definition_version: 1` YAML
files, which Tabalyst 0.6.2 accepted, are no longer read: the command stops
with the error `PACKAGE_FORMAT` and there is no automatic conversion. Install
Tabalyst 0.6.2 to keep using such a file.

## Create an anomaly variant

An anomaly profile adds an altered CSV, a cell change log and a JSON summary
beside an untouched clean CSV. The insurance profile changes only the combined
dataset:

```console
tabalyst generate --example insurance --rows 3000 --anomaly-profile dirty_realistic -d insurance-dirty/
```

Insurance also offers `dirty_stress`, which gives 45 kinds of defect a fixed number
of rows each (a missing digit in 20 client identifiers, one lone `ontario`
in lower case, 8 duplicated rows) however many rows you generate, with a
`class` column in the change log. It needs enough rows for its classes and
stops with an error on a file that is too small (about 1,000 rows or more).

Computer offers `dirty_realistic`, `dirty_stress`, `unit_variants` and
`unit_variants_extended`; the last two mix unit spellings in the measurement
columns.

## Write an anomaly profile

A package declares its profiles under `anomaly_profiles`. Each operation names
a `kind`, usually a `column`, and how many rows it touches: exactly one of
`rate` (a share of the rows, from 0 to 1) or `count` (an absolute number of
rows). Giving both, or neither, is an error.

```yaml
anomaly_profiles:
  stress:
    targets: [customers]
    operations:
      - kind: format
        column: id
        value: double_hyphen
        count: 3
        class: id_hyphen
      - kind: replace
        column: country
        value: quebec
        count: 1
      - kind: duplicate_row
        count: 2
        class: copies
```

Use `count` when a defect must stay as rare in a large file as in a small one:
`count: 1` changes one row at 3,000 rows and at 100,000 rows, while `rate`
grows with the file. An operation with `count` picks its rows among those it
can change (the `when` condition holds and the cell accepts the change), and
two `count` operations never pick the same row, so each defective row belongs
to one class. A `count` larger than the number of rows, or than the rows left for the
operation, stops the command; a result file is never half written. An optional `class` (a lower-case
identifier) names the defect; it is copied to a `class` column of the
`*.changes.csv` file and to the summary. A profile with no `class` writes the
same files as before.

| `kind` | What it does |
| --- | --- |
| `set_missing` | Empties a cell. |
| `replace` | Sets the cell to the literal `value`. |
| `duplicate` | Copies a value from an earlier row of the same column. |
| `swap` | Exchanges the cell with the column named by `value`, when both are filled and differ. |
| `format` | Rewrites the cell as `value` says (below). |
| `duplicate_row` | Replaces the row with an exact copy of an earlier output row. It takes no `column` and no `value`, and runs after the other operations of the row: a row it replaces loses their changes, which the summary then counts as skipped. |

The `format` values are `upper`, `lower`, `strip`, `date_slash`,
`phone_spaces`, `insert_space` (a space inside a word), `double_space` (the
first space doubled), `drop_char` (one character removed), `double_hyphen`
(the first hyphen doubled), `suffix_x` (appends `_X`), `strip_accents`,
`negate` (a minus sign before a non-zero number), `leading_apostrophe`, `drop_digit`, `insert_double_space`,
`trailing_space`, `double_char` (one letter written twice), `swap_first_two`, `transpose` (two
adjacent letters exchanged), `replace_char` (one letter replaced by another of
the same case), `phone_double_space` (`+1-514-...` becomes `+1  514-...`),
`date_dmy` (`2024-03-31` to `31-03-2024`), `date_iso` (the reverse) and, for a
plain decimal number, `currency_suffix` (`1234.18 $`), `currency_prefix`
(`$1234.18`), `currency_fr` (`1 234,18 $`) and `currency_code` (`1234.18 CAD`).
An optional `when: {column: text}` limits an operation to rows whose cell
equals the text. With `rate`, a request that cannot apply, such as
`double_hyphen` on a cell without a hyphen, is not counted as a defect. The
summary reports the rows requested, applied and skipped for every operation.

Choose `-o` only when the result is one clean CSV. Use `-d` for multiple CSVs
or an anomaly profile. Existing output files require `--force`. Nothing is
written beside the package or into the current directory by default.

Use `--seed` and `--as-of-date YYYY-MM-DD` to override the package defaults.
Generation is reproducible with the same package, options and environment.
The [CLI reference](../reference/cli/generate.md) lists all options.
