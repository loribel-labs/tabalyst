---
title: Stratified balanced sample
description: Create a CSV sample with up to N random rows of each value of one or several fields using tabalyst sample --sample-method stratified-balanced --per-value, so that rare values are all kept.
---

`stratified-balanced` keeps up to a quota of random rows of each value of a
field. The quota is per value, not for the whole file: the size of the sample
follows from the data.

```console
tabalyst sample customers.csv --sample-method stratified-balanced --field plan --per-value 100 --seed 42
```

## Key points

- **Quota:** `--per-value N`, a whole number of at least 1, is required. A value
  with `N` rows or fewer is kept whole; a value with more gives `N` rows drawn at
  random, without replacement.
- **Size:** the sum over the values of `min(N, rows of the value)`. It is not
  asked in advance and can be larger than `N`. `--rows` and `--percent` are
  errors with this method.
- **No redistribution:** the places a small value leaves unused are never given
  to a larger one.
- **Fields:** `--field` is required. Repeat it to apply the quota to each
  combination of values that exists in the file, not to each column.
- **Empty values:** an empty cell is a value of its own, as in
  [`stratified`](stratified.md).
- **Cost:** one reading of the file, with no scan before it. Memory holds up to
  `N` rows per value.
- **Output:** the rows are written in file order. `--seed` repeats the draw.

## Example

With `--per-value 100` on a file of 100,015 rows:

| Value | Rows in the file | Rows in the sample |
| --- | ---: | ---: |
| Standard | 70,000 | 100 |
| Premium | 20,000 | 100 |
| VIP | 10,000 | 100 |
| Rare A | 12 | 12 |
| Rare B | 3 | 3 |
| **Total** | **100,015** | **315** |

The command prints the quota, how many values were drawn from (more rows than
the quota) and how many were kept whole.

## Which stratified method

| You want | Use |
| --- | --- |
| A sample of a given size that keeps the proportions of the file | [`stratified`](stratified.md) |
| The same number of rows of each value, rare values included | `stratified-balanced` |

Neither method looks for errors: for the odd cases of a file use a
[smart sample](smart.md).

## Limit on strata

The sample holds one reservoir of up to `N` rows per value while the file
streams. It stops with an error above 100,000 values, and writes nothing;
`--max-strata` changes the limit. With a current stored scan that shows too many
values, it stops before it reads the file, as [`stratified`](stratified.md#limit-on-strata)
does.

On a column whose values are nearly all different, the sample holds nearly the
whole file. That follows from the rule, and the command says so when the sample
holds half of the file or more.

## Limits

- It does not keep the proportions of the file: never estimate the population
  from it.
- `--rows`, `--percent`, `--yes` and `--no-html` are errors with this method
  (exit code 2).

See [Tabalyst Sample](index.md) for output locations and CSV formats.
