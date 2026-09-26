---
title: Sample CSV files
description: Create smaller first, last, random or stratified CSV samples with Tabalyst.
---

Use `tabalyst sample` to create a smaller CSV without changing the source file.
Choose exactly one size option: `--rows` for a fixed count or `--percent` for a
percentage.

```console
tabalyst sample customers.csv --sample-method random --rows 1000
```

This creates `customers.sample.csv` beside `customers.csv`. The output keeps the
header, column order, raw cell values and configured encoding. Existing files
are not replaced unless you pass `--force`; the source can never be overwritten.

## Choose a method

Keep the first or last records:

```console
tabalyst sample customers.csv --sample-method first --rows 1000
tabalyst sample customers.csv --sample-method last --rows 1000
```

Select records uniformly from the entire file. Add `--seed` when another run
must select the same records:

```console
tabalyst sample customers.csv --sample-method random --percent 5 --seed 42
```

Approximately preserve the distribution of a field with proportional
stratified sampling. Empty field values form their own stratum:

```console
tabalyst sample customers.csv --sample-method stratified --field province --rows 1000 --seed 42
```

Percentages round up to the next whole row. A 100% sample contains every data
record. A header-only CSV therefore produces a header-only output at 100%.

## Choose output locations

Use `-o` for the complete output filename when sampling one source:

```console
tabalyst sample customers.csv --sample-method first --rows 100 -o test.csv
```

Wildcards are resolved by Tabalyst, including on shells that do not expand
them. Use `-d` to put samples from one or more sources in a directory:

```console
tabalyst sample *.csv --sample-method random --percent 5 -d samples/
```

The outputs are named `customers.sample.csv`, `orders.sample.csv`, and so on.
`-o` accepts only one resolved input; `-o` and `-d` cannot be combined.
Recursive `**` patterns are not supported.

## Read other CSV formats

The default delimiter is a comma and the default encoding accepts UTF-8 with or
without a byte-order mark. Override either setting when necessary:

```console
tabalyst sample data.csv --sample-method random --rows 100 --delimiter ";" --encoding cp1252
```

`--config` reads the same strict JSON configuration used by `tabalyst report`;
`--delimiter` and `--encoding` override its CSV settings.

Sampling validates the header, quoting and field count of every CSV record. It
uses bounded memory: random sampling stores only the requested rows, while
stratified sampling additionally stores one count per distinct field value.
