---
title: Stratified sample
description: Create a CSV sample of a given size that keeps the proportions of one or several fields, with at least one row of each value, using tabalyst sample --sample-method stratified, and handle the limit on strata.
---

`stratified` approximately preserves the distribution of a field with
proportional sampling, for a total size you choose, and keeps at least one row
of each value. Empty field values form their own stratum. To keep a fixed number
of rows per value instead, use
[`stratified-balanced`](stratified-balanced.md).

```console
tabalyst sample customers.csv --sample-method stratified --field province --rows 1000 --seed 42
```

## Key points

- **Field:** `--field` is required. Repeat it to stratify by the combinations of
  several fields; a row belongs to the stratum of its values taken together.
- **Share:** each stratum gets rows in proportion to its size, rounded so that
  the total is exactly the size asked for.
- **Rare strata:** every stratum gets at least one row, and never more than it
  has. The rows that minimum takes are taken from the other strata in
  proportion, so the shares are not exactly proportional on a very unbalanced
  field. The rounding is deterministic: the largest remainder, ties broken by
  the text of the value.
- **Size under the number of strata:** the command stops with an error that
  gives the smallest `--rows` that holds one row of each value. It never drops
  a value silently, and no file is written.
- **Output:** the command prints how many strata the file has, how many got rows
  and how many did not (none, since every stratum is kept).
- **Seed:** `--seed` repeats the choice.

```console
tabalyst sample customers.csv --sample-method stratified --field province --field language --rows 1000
```

## Limit on strata

The sample holds one counter and one reservoir per stratum while the file
streams. It stops with an error above 100,000 strata; `--max-strata` changes the
limit.

- **With a current stored scan:** if the columns already make more strata than
  the limit, the command stops before it reads the file, with the advice. It
  never makes a scan for this.
- **To run anyway:** pass `--max-strata` yourself. A product of cardinalities is
  a bound, and the combinations that exist can be far fewer.
- **Before running:** combinations of columns multiply quickly.
  [`tabalyst scan --plan --stratify-by`](../scan/plan.md#stratification-advice)
  tells which columns make good strata and how many strata a combination can
  make.

## Memory

Bounded: the requested rows, plus one count per stratum, up to `--max-strata`.

## Limits

- Before 0.7.4 a rare stratum could get no row. Samples made with an earlier
  version can differ.
- It preserves the proportions of the fields you name, not the rare values of
  the other columns. Use a [smart sample](smart.md) for those.
- `--yes` and `--no-html` are errors with this method (exit code 2).

See [Tabalyst Sample](index.md) for sizes, output locations and CSV formats.
