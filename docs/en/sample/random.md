---
title: Random sample
description: Create a CSV sample drawn uniformly from the whole file with tabalyst sample --sample-method random, and repeat it with a seed.
---

`random` selects rows uniformly from the entire file. The sample approximately
keeps the proportions of the file.

```console
tabalyst sample customers.csv --sample-method random --percent 5 --seed 42
```

## Key points

- **Seed:** add `--seed` when another run must select the same rows.
- **Size:** `--rows` or `--percent`, exactly one.
- **Cost:** one reading of the file, and only the requested rows are stored in
  memory.
- **Output:** `customers.sample.csv` beside the source, in file order.

## Limits

- A rare value can be missed: a value that appears once in a million rows is
  unlikely to be drawn. Use a [smart sample](smart.md) to keep every value of the
  small columns and the odd cases.
- To keep the proportions of one field, or of a few, use a
  [stratified sample](stratified.md).
- `--field`, `--max-strata`, `--yes` and `--no-html` are errors with this method
  (exit code 2).

See [Tabalyst Sample](index.md) for sizes, output locations and CSV formats.
