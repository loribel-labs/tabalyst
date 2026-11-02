---
title: Smart sample
description: Create a CSV sample that covers every value of the small columns, the extremes and the odd cases of a file with tabalyst sample --smart, and read what it covers.
---

`--smart` (short for `--sample-method smart`) is the recommended method. It
keeps the diversity of the file, not its proportions.

```console
tabalyst sample customers.csv --smart --rows 1000
```

It writes three files beside the source:

| File | Content |
| --- | --- |
| `customers.sample.csv` | The sample: header, column order, raw cell values and encoding of the source |
| `customers.sample.json` | The [report](format.md): what the sample aimed at and what it covers |
| `customers.sample.html` | A page built from the report alone: coverage by family and weighted, targets not covered with the reason, exact counts of the plan. `--no-html` skips it |

## What it keeps

A random sample can miss a value that appears once in a million rows. A smart
sample keeps:

- every value of a column that has few values;
- the shortest and longest texts, the smallest and largest numbers;
- each pattern and each format of date;
- the cases the scan found odd.

Its proportions are not those of the file: never estimate the population from
it.

## What it costs

- It needs the [scan](../scan/index.md) of the file. A current stored scan is
  reused (1 reading); otherwise the file is scanned first and the command says
  so (2 readings at most).
- It never runs a [second pass](../scan/deep.md) by itself. A current one is
  used to know more about the numbers, the patterns and the relations between
  columns.
- When the estimate reaches two minutes, the command shows it and asks before it
  starts. Outside a terminal it never asks: it stops with exit code 3 unless you
  pass `--yes`.
- It reads CSV files only.

## How the rows are chosen

1. **Targets.** The scan lists things worth having in the sample, each with a
   weight. A rare target weighs more than a frequent one, up to a ceiling. The
   values of a column whose every value is known are **mandatory**. Read the
   [plan](../scan/plan.md#smart-sample-plan) beforehand.
2. **Candidates.** While reading the file, the command keeps a few candidate
   rows per target in a bounded amount of memory, plus a pool of ordinary rows
   chosen by a seeded hash of their position. A row that covers several targets
   is kept once.
3. **Cover.** It picks the rows that cover the most weight not yet covered,
   mandatory targets first, then fills the rest with ordinary rows. The rows are
   written in file order, whole, with no column added.

The choice is a heuristic on a bounded pool. It measures its coverage and
promises no optimum.

- **Reserve:** by default a fifth of the size is kept for ordinary rows
  (`smart.reserve_share`), and it gives way to the mandatory targets when the
  size is small. The command prints as `Reserve` the ordinary rows the sample
  ends up holding. They also fill the room the targets leave, so the number can
  exceed a fifth. On the 3,000-row file of the example below, it is 0 for 100
  rows, 63 for 200, 157 for 300 and 447 for 600 (seed 42).
- **Too small for every target:** the heavier ones win, and the report lists the
  others with the reason.
- **Command output:** targets covered, mandatory ones covered, ordinary rows
  held and readings of the file.
- **Seed:** the same seed gives the same file. `--seed` changes the choice among
  equal candidates and the ordinary rows. By default it is the seed of the scan.

## Example

On `insurance-customers.csv` of the examples (3,000 rows), 15 columns have 50
values or fewer: 146 distinct values in all, an empty cell counting as a value.
A smart sample of 100 rows keeps all of them. A random sample of the same size
and seed misses 49.

```console
tabalyst sample insurance-customers.csv --smart --rows 100 --seed 42
tabalyst sample insurance-customers.csv --sample-method random --rows 100 --seed 42
```

| Rows | Values missed (smart) | Values missed (random) |
| --- | --- | --- |
| 100 | 0 | 49 |
| 40 | 9 | 69 |
| 20 | 40 | 81 |

The smart command prints the mandatory targets it covered (`Mandatory: 137 of
146 covered` for 40 rows): compare them with what you needed. The numbers
depend on the seed: at 100 rows, a random sample misses 43 of these values with
the default seed and 48 with `--seed 1`; at 40 rows, a smart sample misses 9
with the default seed and 12 with `--seed 18`.

## Targets beyond values

| Target | Covered by |
| --- | --- |
| Empty cells | A row with a blank, so a rare blank in an otherwise filled column (a required identifier) is kept |
| Repeated row | A row that repeats an earlier row. At least one such row, not one per group of copies |
| Scan remarks | A cell with spaces around or inside it, a string of a rare length, and each group of variants of one value (same name, other capitals or accents). A group is covered by a variant other than the most common one. At most 20 such targets per column, largest groups first |
| Unexpected character | A string that holds it, per column, only when few strings have it |
| Values held once | One target per column (the tail, where a typo lives): the sample keeps one of them, not each. A column whose values are nearly all different, such as an identifier, has none |
| Worst cases | The rows that show the most anomalies at once. Up to `smart.worst_rows` rows (3 by default, at most a twentieth of the size), counted in `by_worst` |

A repeated row is recognized because the selection digests every row as the
scan did. Like the scan, it stops remembering digests at
`limits.max_tracked_records`, and a copy of a row it no longer remembers goes
unseen.

### Typos of a category

A frequent value with rare values one edit away (`Longueuuil` next to
`Longueuil`) gets one target, covered by a row that holds any of those rare
values.

- **Needs:** the exact count of every value of the text column, from the scan or
  from the second pass, for at most `smart.max_exact_values` values.
- **Frequent value:** at least 10 rows, and at least ten times the rows of each
  rare value.
- **Rare value:** at most 2 rows and at least 4 characters. No text has more
  than 64 characters.
- **Not a typo:** a difference of capitals, accents or spaces is a variant.
- **Budget:** at most `smart.near_share` of the rows asked for (8% by
  default), shared between the columns in turn. None when the size is too small
  for the mandatory targets.
- **Skipped:** a column of 100 values or fewer has a mandatory target for each
  value, so none of these. The plan counts the groups its limits leave out.

## Options

- A size is required (`--rows` or `--percent`), as for the other methods.
- `--smart` and `--sample-method smart` mean the same. `--smart` cannot be
  combined with another `--sample-method`, and one of the two is required.
- `--yes` and `--no-html` belong to `smart` alone.
- `--field` and `--max-strata` belong to [`stratified`](stratified.md) alone:
  the targets come from the scan, not from the fields you name.
- An option the chosen method does not read is an error (exit code 2), never
  silently ignored.
- The tuning (candidates per target, share of ordinary rows, memory) has no
  command-line option. It is in the
  [`smart` settings](../reference/configuration.md#smart-settings) of the
  configuration file, given with `--config`.

## Limits

- The report names what it covers precisely: the catalog of targets of the plan,
  not every phenomenon of the data. A rare phenomenon the scan has no target for
  can be missing.
- Percentages round up to the next whole row. See [Tabalyst Sample](index.md)
  for sizes, output locations and CSV formats.
