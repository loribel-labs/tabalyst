---
title: Stratified sample
description: Create a CSV sample that approximately preserves the distribution of one or several fields with tabalyst sample --sample-method stratified, and handle the limit on strata.
---

`stratified` approximately preserves the distribution of a field with
proportional sampling. Empty field values form their own stratum.

```console
tabalyst sample customers.csv --sample-method stratified --field province --rows 1000 --seed 42
```

## Key points

- **Field:** `--field` is required. Repeat it to stratify by the combinations of
  several fields; a row belongs to the stratum of its values taken together.
- **Share:** each stratum gets rows in proportion to its size, rounded so that
  the total is exactly the size asked for.
- **Rare strata:** there is no minimum of one row. On a very unbalanced field a
  rare stratum can get no row.
- **Output:** the command prints how many strata the file has, how many got rows
  and how many did not.
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

- It preserves the proportions of the fields you name, not the rare values of
  the other columns. Use a [smart sample](smart.md) for those.
- `--yes` and `--no-html` are errors with this method (exit code 2).

See [Tabalyst Sample](index.md) for sizes, output locations and CSV formats.
