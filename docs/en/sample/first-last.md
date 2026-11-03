---
title: First and last rows
description: Keep the first or the last rows of a CSV file with tabalyst sample --sample-method first or last, for a quick look at the start or the end.
---

`first` and `last` keep the first or the last records of the file, in file
order.

```console
tabalyst sample customers.csv --sample-method first --rows 1000
tabalyst sample customers.csv --sample-method last --rows 1000
```

## Key points

- **Use it when** you only need the start or the end of the file.
- **Size:** `--rows` or `--percent`, exactly one.
- **Cost:** one reading of the file.
- **Seed:** none. The rows are kept in file order, so `--seed` is an error with
  these methods (exit code 2).
- **Output:** `customers.sample.csv` beside the source.

## Limits

- The rows are not chosen to represent the file. For the proportions use a
  [random](random.md) or [stratified](stratified.md) sample; for the rare cases
  use a [smart sample](smart.md).
- `--seed`, `--field`, `--max-strata`, `--yes` and `--no-html` are errors with
  these methods (exit code 2).

See [Tabalyst Sample](index.md) for sizes, output locations and CSV formats.
