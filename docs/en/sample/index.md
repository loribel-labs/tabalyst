---
title: Tabalyst Sample
description: Create smaller first, last, random, stratified, stratified-balanced or smart CSV samples with Tabalyst, and choose the method that fits.
---

Use `tabalyst sample` to create a smaller CSV without changing the source file.

```console
tabalyst sample customers.csv --smart --rows 1000
```

This creates `customers.sample.csv` beside `customers.csv`.

- **Kept as is:** header, column order, raw cell values and configured encoding.
- **Size:** choose exactly one of `--rows` (fixed count) or `--percent`.
  `stratified-balanced` is the exception: it takes `--per-value` and its size
  follows from the data.
- **Safety:** existing files are replaced only with `--force`; the source can
  never be overwritten.

## Which method to use

| Method | Use it when | Readings |
| --- | --- | --- |
| [`smart`](smart.md) (recommended) | You need every value of the small columns, the extremes and the odd cases | 2 at most (1 with a current scan) |
| [`random`](random.md) | You need a quick sample that keeps the proportions of the file | 1 |
| [`stratified`](stratified.md) | You need a sample of a given size that keeps the proportions of one field, or of a few, with a row of each value | 2 |
| [`stratified-balanced`](stratified-balanced.md) | You need up to N rows of each value, so the rare values are well represented | 1 |
| [`first`, `last`](first-last.md) | You only need the start or the end of the file | 1 |

`--smart` is short for `--sample-method smart`. The other methods are chosen
with `--sample-method`.

## Rules common to all methods

- **Size:** a percentage rounds up to the next whole row. A 100% sample contains
  every data record; a header-only CSV gives a header-only output.
- **Options:** an option the chosen method does not read is an error (exit code
  2), never silently ignored.
- **Validation:** every CSV record is checked for header, quoting and field
  count.
- **Reading time:** reading a large file can take minutes. See the
  [smart sample](smart.md#what-it-costs) for the estimate and confirmation.

## Choose output locations

Use `-o` for the complete output filename when sampling one source:

```console
tabalyst sample customers.csv --sample-method first --rows 100 -o test.csv
```

Use `-d` to put samples from one or more sources in a directory. Wildcards are
resolved by Tabalyst, including on shells that do not expand them:

```console
tabalyst sample *.csv --sample-method random --percent 5 -d samples/
```

- Outputs are named `customers.sample.csv`, `orders.sample.csv`, and so on.
- `-o` accepts only one resolved input; `-o` and `-d` cannot be combined.
- Recursive `**` patterns are not supported.

## Read other CSV formats

The default delimiter is a comma and the default encoding accepts UTF-8 with or
without a byte-order mark. Override either when necessary:

```console
tabalyst sample data.csv --sample-method random --rows 100 --delimiter ";" --encoding cp1252
```

`--config` reads the same strict JSON configuration as `tabalyst report`;
`--delimiter` and `--encoding` override its CSV settings.

## Go further

- [Smart sample](smart.md): what it covers and how it is chosen.
- [Format of the report of a smart sample](format.md): the JSON report written
  beside it.
- [CLI: tabalyst sample](../reference/cli/sample.md): every option.
- [Python API: sampling](../reference/python-api/sample.md).
