---
title: Tabalyst Sample
description: Create smaller first, last, random, stratified or smart CSV samples with Tabalyst, and read the report of what a smart sample covers.
---

Use `tabalyst sample` to create a smaller CSV without changing the source file.
Choose exactly one size option: `--rows` for a fixed count or `--percent` for a
percentage.

```console
tabalyst sample customers.csv --smart --rows 1000
```

This creates `customers.sample.csv` beside `customers.csv`. The output keeps the
header, column order, raw cell values and configured encoding. Existing files
are not replaced unless you pass `--force`; the source can never be overwritten.

`--smart` (short for `--sample-method smart`) is the recommended method: it
keeps every value of the columns that have few values, and the rare cases a
random draw drops. It costs a little more than the others, because it reads the
source twice at most: once to scan and once to choose the rows. When a current
stored [scan](../scan/index.md) exists it reads the source once. See
[Cover rare cases with a smart sample](#cover-rare-cases-with-a-smart-sample).

## Which method to use

| Method | Use it when | Readings |
| --- | --- | --- |
| `smart` (recommended) | You need every value of the small columns, the extremes and the odd cases in the sample | 2 at most (1 with a current scan) |
| `random` | You need a quick sample that keeps the proportions of the file | 1 |
| `stratified` | You need the proportions of one field, or of a few, preserved | 1 |
| `first`, `last` | You only need the start or the end of the file | 1 |

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

Each stratum gets rows in proportion to its size, rounded so that the total is
exactly the size asked for. There is no minimum of one row: on a very unbalanced
field a rare stratum can get no row, and the command prints how many strata the
file has, how many got rows and how many did not. Repeat `--field` to stratify by
the combinations of several fields; a row belongs to the stratum of its values
taken together.

```console
tabalyst sample customers.csv --sample-method stratified --field province --field language --rows 1000
```

A stratified sample holds one counter and one reservoir per stratum while the
file streams, so it stops with an error when the file has more than 100,000
strata (`--max-strata` changes the limit). When a current stored scan already
shows that the columns make more strata than that, the command stops before it
reads the file, with the advice; it never makes a scan for this. Pass
`--max-strata` yourself to run it anyway: a product of cardinalities is a bound,
and the combinations that exist can be far fewer. Combinations of columns multiply
quickly: [`tabalyst scan --plan --stratify-by`](../scan/plan.md#stratification-advice)
tells beforehand which columns make good strata and how many strata a
combination can make.

## Cover rare cases with a smart sample

A random sample can miss a value that appears once in a million rows. A smart
sample is built to keep the diversity of the file instead: every value of a
column that has few values, the shortest and longest texts, the smallest and
largest numbers, each pattern, each format of date and the cases the scan found
odd. Its proportions are not those of the file, so never estimate the population
from it.

```console
tabalyst sample customers.csv --smart --rows 1000
```

This writes `customers.sample.csv` and, beside it, `customers.sample.json`: the
[report of the sample](format.md), which says what the sample was aimed at and
what it covers, and `customers.sample.html`, a page that shows that report: the
coverage by family and weighted, the targets that are not covered with the
reason, and the exact counts of the plan that the reading confirmed. The page
is built from the report alone. Pass `--no-html` to write the CSV file and the
JSON report only. The sample needs the [scan](../scan/index.md) of the file. A
current stored scan is reused; otherwise the file is scanned first, and the
command says so before it starts. A smart sample therefore reads the source twice
at most: once to scan and once to choose the rows. It never runs a
[second pass](../scan/deep.md) by itself; a current one is used to know more about
the numbers, the patterns and the relations between columns.

The sample is built in three steps:

1. The scan gives the **targets**: things worth having in the sample, each with a
   weight. A rare target weighs more than a frequent one, up to a ceiling. The
   values of a column whose every value is known are **mandatory**. See the
   [plan](../scan/plan.md#smart-sample-plan), which you can read beforehand.
2. Reading the file, the command keeps a few candidate rows for each target in
   a bounded amount of memory, and a pool of ordinary rows chosen by a seeded hash
   of their position. A row that covers several targets is kept once.
3. It chooses the rows that cover the most weight not yet covered, the mandatory
   targets first, and fills the rest of the size with ordinary rows. A fifth of
   the size is set aside for them by default, and the share gives way to mandatory
   targets when the size is small. The rows are written in the order of the file,
   whole, with no column added.

The choice is a heuristic on a bounded pool: it measures the coverage it obtains
and promises no optimum. When the size is too small for every target, the heavier
ones win and the report lists the others with the reason. The command prints how
many targets are covered, how many of the mandatory ones, how many ordinary rows
the sample holds and how many readings of the file it cost.

On the 3,000-row `insurance-customers.csv` example, a smart sample of 100 rows
keeps all 146 distinct values of its 9 columns of 50 values or fewer. A random
sample of the same size, with the same seed, misses 48 of them. When the size is
too small for every value, the heavier targets win and the sample misses fewer
values than a random one: at 40 rows it missed 10 of the 146 (random: 67), and
at 20 rows it missed 39 (random: 86). The command line says how many mandatory
targets are covered, so compare it with what you needed.

The same seed gives the same file. `--seed` changes the choice among equal
candidates and the ordinary rows; by default it is the seed of the scan.

Reading a large file can take minutes. When the estimate reaches two minutes the
command shows it and asks before it starts. Outside a terminal it never asks: it
stops with exit code 3 unless you pass `--yes`.

Smart sampling reads CSV files only. The [`smart` settings](../reference/configuration.md#smart-settings)
change the number of candidates per target, the share of ordinary rows and the
memory the candidate rows may take.

A rare phenomenon the scan has no target for can still be missing. The report
names what it covers precisely: the catalog of targets of the plan, not every
phenomenon of the data.

### What the smart method reads and ignores

- It needs a size (`--rows` or `--percent`) like the other methods.
- `--smart` and `--sample-method smart` mean the same thing. `--smart` cannot
  be combined with another `--sample-method`, and one of the two is required.
- No option is ignored silently: an option the chosen method does not read is
  an error (exit code 2). `--field` and `--max-strata` belong to `stratified`
  alone; the targets of `smart` come from the scan, not from the fields you
  name. `--yes` and `--no-html` belong to `smart` alone. `--seed` has no effect
  with `first` and `last`, which keep the rows in file order.
- The reserve of ordinary rows is a fifth of the size by default, but the
  mandatory targets come first: on a sample of 100 rows over 9 small columns
  the reserve was 5 rows, and with 40 rows or fewer it was empty. A sample
  that small is made of covering rows only, so its proportions are far from
  those of the file.
- Its tuning (candidates per target, share of ordinary rows, memory) has no
  command-line option: it is in the
  [configuration file](../reference/configuration.md#smart-settings), given
  with `--config`.
- It does not run a [second pass](../scan/deep.md) by itself, and it reads
  CSV files only.

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
stratified sampling additionally stores one count per stratum, up to `--max-strata`.
