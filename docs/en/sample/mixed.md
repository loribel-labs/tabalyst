---
title: First, random and last rows together
description: Keep the first rows, some random rows and the last rows of a CSV file in one sample with tabalyst sample --sample-method mixed, without any row kept twice.
---

`mixed` keeps the start of the file, its end and a random draw from the rows
between them, in one sample and in file order.

```console
tabalyst sample customers.csv --sample-method mixed --first-rows 100 --random-rows 800 --last-rows 100 --seed 42
```

## Key points

- **Use it when** you want to see how a file begins and ends, and what is in
  the middle.
- **Size:** `--first-rows`, `--random-rows` and `--last-rows`, each 0 or more,
  at least one above 0. `--rows` and `--percent` are errors (exit code 2).
- **No repeated row:** the random rows are drawn among the rows that the start
  and the end did not keep.
- **File shorter than the request:** the start is served first, the end keeps
  what the start left, and the random draw takes what is left of both. With 100
  rows, 75 first and 75 last give the 100 rows of the file, each once.
- **Cost:** two readings of the file.
- **Seed:** `--seed` makes the random rows reproducible. It is an error when
  `--random-rows` is 0 or absent.
- **Output:** `customers.sample.csv` beside the source. The summary shows the
  rows kept in each part (`Parts: 100 first, 800 random, 100 last`).

## Limits

- The random rows are not stratified. For the proportions of a column use a
  [stratified](stratified.md) sample; for the rare cases use a
  [smart sample](smart.md).
- `--first-rows`, `--random-rows` and `--last-rows` are errors with any other
  method (exit code 2).

See [Tabalyst Sample](index.md) for output locations and CSV formats.
