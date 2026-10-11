---
title: Add histograms and exact medians with a second pass
description: What tabalyst scan --deep adds to a scan by reading the source again, when it asks before starting, which analyses it runs, where it writes its document and how stored results are reused.
---

`tabalyst scan --deep` reads a file a second time to add what the first pass of a
scan does not hold: histograms of numeric fields, with exact or estimated
medians and quantiles, the exact number of distinct values of an identifier-like
field, the exact counts of a field whose scan lists only some of them, the
length distribution of a text field when the scan lacks it, the inferred patterns
counted on every value, the dates counted per period, the correlation of
pairs of numeric columns and tables of a category against the pattern, length or
prefix of another column. It writes them to a
separate document, `deep.json`, and never changes the scan. The second pass is
experimental in the beta. [`tabalyst report`](../reference/cli/report.md#second-pass)
runs it by itself for the analyses that are useful and cheap, and puts the results
in the report.

```console
tabalyst scan customers.csv --deep
```

If the scan of the file stored by Tabalyst is current (same content, settings
and version), only the second pass runs. Otherwise the first pass runs and is
stored, as `tabalyst scan` does. It then reads the file again once, whatever the
number of analyses. Messages go to standard error:

```text
Scan: scans\customers.scan.json (scanned)
Second pass [customers.csv]: reading the source again for 2 analyses, estimated under a second.
Second pass: C:\data\scans\customers.deep.json (2 analyses: 2 computed, 0 reused)
```

Without `-o` or `-d`, the document is `deep.json`, beside the stored `scan.json`
in Tabalyst's local storage. With them it is `<stem>.deep.json`, beside the scan
you asked for. See [Scan CSV and JSON files](files.md) for where the scan is
stored.

## What it adds

| Analysis | Applies to | What the document gets |
| --- | --- | --- |
| `numeric_histogram` | Numeric fields | The count of every integer when they span at most 65,536 values, with the exact mode, median and quantiles; otherwise the count in each of 100 bins, with estimated median and quantiles |
| `length_distribution` | Text fields whose scan has no length histogram | The exact count of every length |
| `exact_distinct` | Fields whose scan stopped counting distinct values | The exact number of distinct values, the number of values it counts over and how many of them repeat an earlier one |
| `exact_frequencies` | Fields of at most 1,000 distinct values whose scan lists only the most frequent | The exact count of every value |
| `pattern_validation` | Text fields with inferred patterns | How many values of the whole file each pattern reads, how many none reads, and how many were not tested |
| `temporal_distribution` | Date fields, and columns of datetimes | The dates counted per day, month or year |
| `pearson_correlation` | Pairs of numeric columns of one dataset | The Pearson correlation over every row where both columns have a number, with the number of those rows and of the rows left out |
| `category_crosstab` | A column of a few values and another text or integer column | The count of the rows of each category in each pattern, length or prefix of the other column, with the purity of each category, the exceptions, Cramér's V and candidate rules |

A scan always holds the length histogram of a text field unless it was limited
or turned off, so `length_distribution` is rare. `tabalyst scan --plan --deep`
shows what a run would do.

## Patterns on every value

The scan infers patterns such as `XX9999'A'` from a sample of the distinct values
of a field, and its shares count distinct values, not occurrences. The second pass
reads every value of the file with those patterns, as they are in the file (before
any cleaning), and counts each value once, for the most specific pattern that reads
it. The counts add up: the values read by a pattern, the values no pattern reads
(`other`) and the values that were not tested (too long, too many tokens, or JSON
numbers and booleans) make the values of the field.

```json
{"kind": "pattern_counts", "accuracy": "exact", "computed_from": "source",
 "values": 3000, "matched": 2990,
 "candidates": [{"id": "p1", "render": "XX9999'A'", "occurrences": 2100}],
 "other": 10, "excluded": {"non_string": 0, "too_long": 0, "too_complex": 0},
 "overlaps": []}
```

A value that no pattern reads is an observation about its structure, not an error:
the dominant pattern is not a rule of your data. The second pass does not look for
new patterns among them. When the scan holds every distinct value with its exact
count, the occurrences follow from those counts and the source is not read
(`computed_from` is `samples`, the result is the same).

## Dates per period

The dates the scan parsed are counted per calendar day (a span of up to two
years), month (up to 60 years) or year, with the period fixed before the reading.
A value is placed by the date it is written with: the offset of a datetime is not
converted, so `2024-03-10T23:30:00-05:00` is on the 10th, and a change of daylight
saving time moves nothing. A date that could be read day first or month first, and
that the scan did not resolve, is counted as `ambiguous` and never placed. Dates and
datetimes are not merged: a column of both has no distribution.

```json
{"kind": "periods", "accuracy": "exact", "granularity": "month",
 "temporal_kind": "date", "zone": "as_written", "values": 3000, "count": 2990,
 "ambiguous": 8, "unplaced": 2, "first": "2016-09", "last": "2027-08",
 "periods": [{"period": "2016-09", "count": 21}]}
```

The count of placed dates and the number of ambiguous values are those of the
scan; a difference fails the analysis rather than giving a result.

## Correlation between two columns

The second pass counts, over every row, the Pearson correlation of a pair of numeric
columns. It does not try every pair of the file. It first scores all the pairs of
the eligible columns on the rows the scan sampled, which needs no reading of the
source, keeps the best ones, and reads the file once for them.

```json
{"kind": "pearson", "accuracy": "exact_counts", "precision": "float64",
 "rule": "pairwise_complete", "source": "source", "min_pairs": 10,
 "rows": 3000, "pairs": 2571,
 "excluded": {"first_missing": 0, "second_missing": 429,
              "both_missing": 0},
 "defined": true, "coefficient": 0.995454, "mean_first": 0.0082,
 "mean_second": 0.5288, "std_first": 1.0016, "std_second": 3.0249,
 "covariance": 3.0158}
```

Only the rows where **both** columns have a number count (`pairwise_complete`).
The means and the spreads are those of these common rows, not the ones of each
column in the scan, which can differ when the empty cells are not the same.
`rows` is `pairs` plus the three exclusions, so nothing is left unaccounted for. A
value is missing when the cell is empty, is not a number, or does not fit a 64-bit
float.

A coefficient is never replaced by `0` when it cannot be computed. There is no
`coefficient` and `reason` says why: `insufficient_pairs` (fewer than
`min_pairs` common rows), or `zero_variance_first` or `zero_variance_second` (a
column that does not vary over the common rows). The counts are exact; the
coefficient is computed in 64-bit floats from stable co-moments, which keeps its
digits even for numbers with a large common offset. It measures a linear
association between two columns. It does not show that one causes the other, and
it can be small for a relation that is not a line.

**How the pairs are chosen.** A column takes part when it is numeric, varies, is
not an identifier, is not hidden by exposure, does not repeat inside a record (the
items of an array), and has enough numbers in the sample. An identifier is a
column of almost only distinct values whose name looks like one, or an integer
column that is almost entirely distinct. The plan counts the columns it left out,
by reason. The pairs are scored on the interior rows of the sample (a
complete sample, which holds every row of a small file, is used whole). A pair is
ranked by the lower end of its 95% interval, so that a high coefficient over a few
rows does not outrank a steady one over many. The interval is an estimate that
assumes the rows are drawn at random from a bell-shaped relation. A pair that
this sample does not show can still hold in the file: "not detected in the sample"
does not mean "absent".

**What is automatic.** `tabalyst report` picks by itself the pairs whose lower
bound is 0.45 or more, eight at most. `--deep` takes every pair the plan lists,
twenty at most, after asking if the estimate calls for it. The API can ask for any
pair, even one that the sample did not show.

**Small files.** When the scan sampled every row of a CSV file (up to 1,000
rows), the sample is the file: the pair is computed from it and the source is not
read again (`source` is `samples`).

## A category against a feature of another column

A column of a few values, such as a region, can determine the shape of another
column, such as a client identifier. The second pass counts, over every row, how
many rows of each category fall in each class of a **feature** of that other
column: the pattern that reads its value, its length, or its first characters. It
does not try every combination of the file. It first scores them on the rows the
scan sampled, which needs no reading of the source, keeps the best ones, and reads
the file once for them.

```json
{"kind": "crosstab", "accuracy": "exact_counts", "precision": "float64",
 "source": "source", "feature": {"kind": "pattern", "version": 1},
 "categories": {"field": "column_1", "display": "region", "domain": "analytical",
  "classes": [{"id": "c1", "label": "BC"}, {"id": "c2", "label": "ON"},
              {"id": "c3", "label": "QC"}, {"id": "other", "label": "other", "kind": "other"}]},
 "classes": {"field": "column_2", "display": "client_id", "domain": "original",
  "classes": [{"id": "p1", "label": "XX9999"}, {"id": "p2", "label": "999999"},
              {"id": "p3", "label": "9999-XX"}, {"id": "other", "label": "other", "kind": "other"}]},
 "rows": 300, "counted": 299,
 "excluded": {"category_missing": 0, "feature_missing": 1,
              "both_missing": 0, "unclassified": 0},
 "counts": [[0, 1, 99, 0], [2, 95, 2, 0], [96, 3, 1, 0], [0, 0, 0, 0]],
 "row_totals": [100, 99, 100, 0], "column_totals": [98, 99, 102, 0],
 "by_category": [{"rows": 100, "classified": 100, "feature_missing": 0,
   "unclassified": 0, "coverage": 1.0, "dominant": 2, "dominant_count": 99,
   "purity": 0.99, "exceptions": 1}],
 "purity": {"forward": {"dominant": 290, "total": 299, "value": 0.96990},
            "reverse": {"dominant": 290, "total": 299, "value": 0.96990},
            "baseline": 0.34114},
 "association": {"defined": true, "n": 299, "effective_categories": 3,
   "effective_classes": 3, "chi_square": 545.385, "degrees": 4,
   "cramers_v": 0.95500, "corrected": 0.95468, "low_share": 0.0, "stable": true},
 "exceptions": {"count": 9, "cells": 5, "listed": [{"category": 2, "column": 1,
   "count": 3, "examples": [{"record": 25, "value": "384512"}]}]},
 "rules": [{"status": "candidate", "provenance": "learned", "category": 2,
   "column": 0, "support": 100, "confidence": 0.96, "exceptions": 4}]}
```

(The example is shortened: a real result lists every category in `by_category`,
every cell in `counts` and up to three rows per exception.)

**What is counted.** The classes are fixed before the file is read, from what the
scan holds, so no row can create a new one: the categories are the most frequent
values of the column (at most 30), the classes of a `pattern` are the patterns the
scan inferred, those of a `length` the lengths it counted, those of a `prefix` the
most frequent first two characters of the values it lists. Whatever is not one of
them is `other`, which stays in the table with zeros when no row falls in it. Rows
with no category, no value, or a value the feature cannot classify (a JSON number
has no pattern) are left out of the table and counted by cause in `excluded`, so
`rows` is `counted` plus the exclusions.

**What it says.** Each cell is the exact count of rows. The page of the report
shows the share of each category in every class before any score.

- `coverage` of a category is the share of its rows that have a value to classify;
  a category whose values are mostly missing says little.
- `dominant` is the class that holds most of a category (a tie goes to the first
  class listed) and its `purity` the share of the category's classified rows in it.
  The other rows are its `exceptions`, with exact counts and the first three rows of
  each cell, in file order, with the record number.
- `purity.forward` is the same figure for the whole table, from category to class;
  `reverse` goes from class to category and is another number. `baseline` is the
  share of the most frequent class: a purity close to it says nothing.
- `association` is Cramér's V, the strength of the association from 0 to 1, over
  the categories and classes that have rows (an empty `other` takes no part), and
  `corrected` the same corrected for the number of rows and classes, which is what
  Tabalyst ranks by. With one category or one class, or too few rows, there is no
  score and `reason` says why (`single_category`, `single_class`, `too_few_rows`):
  it is never `0`. A score is `stable` unless the expected counts are low (more than
  a fifth of the cells under 5, or one under 1) on the categories and classes that
  hold at least 5 rows; the `sparse` ones, with fewer, are counted but do not make a
  score unstable. An unstable score is not to be called strong, and when the planner
  chooses tables by itself a table with an unstable score ranks after every stable one,
  whatever its score; it stays listed.
- `rules` are the **candidate rules** the table suggests: a category whose dominant
  class is a real pattern, length or prefix (not `other`), with at least 30 counted
  rows of which 90% are in it. A rule is learned from the data, not validated by
  anyone, and the exceptions are its counterexamples. A rule that you approve is a
  different thing.

An association is not a cause, and the pattern of an identifier that follows its
region is a fact about the file, not a constraint of the source system.

**Several features of the same two columns.** The pattern, the length and the
prefix of an identifier often say the same thing. `tabalyst report` picks by itself
only the feature with the best score for two columns, and the report prints one
block for them with the leading feature first and the others folded; a request, or
`--deep`, computes them all, and every measure stays in the document.

**How the tables are chosen.** A **category** has the exact frequencies of its values
in the scan, from 2 to 100 distinct values, is not hidden by exposure, does not repeat
inside a record, does not look like an identifier, and has repeated values (at most
half of them are distinct). The **column** of a feature is a text, mixed or integer
column that the scan gives classes for: patterns inferred, more than one length, more
than one prefix among the values it lists. The plan counts the columns it left out, by
reason. A table is ranked by its corrected Cramér's V on the interior rows of the
sample (a complete sample, which holds every row of a small file, is used whole). A
relation that this sample does not show can still hold in the file: "not found in the
sample" does not mean "absent".

**What is automatic.** `tabalyst report` picks by itself the tables whose corrected
V is 0.45 or more, eight at most, one feature for two columns. `--deep` takes every
table the plan lists, twenty at most, after asking if the estimate calls for it. The
API can ask for any table, even one that the sample did not show.

**Small files.** When the scan sampled every row of a CSV file (up to 1,000 rows), the
sample is the file: the table is computed from it and the source is not read again
(`source` is `samples`).

## Exact distinct count

A scan stops counting the distinct values of a field after 100,000 of them (the
limit `max_distinct_per_field`) and keeps an estimate. The second pass counts
them all, exactly, on the original values of the file: before any cleaning, so
`00123`, `123` and `123 ` are three values, and `Ab` and `AB` two. A JSON string
`"123"` and the JSON integer `123` are two values too. Empty cells, blank cells,
null markers and JSON nulls are not values.

```json
{"kind": "distinct", "accuracy": "exact", "values": 1000000,
 "distinct": 998317, "redundant": 1683, "unique": false}
```

`redundant` is `values - distinct`: the occurrences that repeat an earlier one,
not the number of values that appear more than once. `unique` is true when every
value is distinct. A field is only an identifier if `unique` is true; a name such
as `id` proves nothing.

The count has to fit in memory. Tabalyst plans the memory of each field from the
scan, and counts a field's values in sets of the compact integers of the digit
strings and of the strings themselves. If a field needs more than the plan gave
it (for example because some values are padded with long runs of blanks that the
scan's lengths do not show), the field **stops**: its result is `limited`, with the
reason `memory_budget`, and only says how many values were read and how many
distinct values were proven so far. That number is a lower bound, never the count.
The other analyses of the run are not affected.

## Exact or estimated

Counts are always exact. A count per integer, or per bin, is the count of every
value in the file.

- **Integers in a small range**: Tabalyst counts each integer, so the mode, the
  median and every quantile are exact. The median of an even count is the mean of
  the two middle values.
- **Other numbers**: a bin says how many values it holds, not where they are
  inside it. The median and quantiles are therefore **estimates**: each comes
  with the lowest and highest value it can have, and the true value is always
  between them. Bins are of equal width between the exact minimum and maximum of
  the scan, and the last bin includes the maximum.

The scan keeps its own median. When the scan could not compute it, because the
field has too many distinct values, the scan still says `limited` and the
second pass gives the estimate beside it. See [Second pass
format](deep-format.md) for how a result names its accuracy.

## Settings

The `deep` object of a [configuration file](../reference/configuration.md#deep-settings)
sets the bins:

```json
{"deep": {"bins": 50, "bin_strategy": "sample_quantile"}}
```

The `deep.pearson` object chooses the pairs of numeric columns: how many
columns are explored, how much work that may take and how many pairs the plan lists
or picks by itself. The `deep.crosstab` object does the same for the tables of a
category against a feature, and sets their classes (the categories kept, the length
of a prefix) and the thresholds of the candidate rules. See [Deep
settings](../reference/configuration.md#deep-settings).

`bin_strategy: "sample_quantile"` places the inner edges where the sample of
rows kept by the scan has its quantiles, which suits a very skewed distribution
such as amounts. The counts are still those of the whole file. When the scan
kept too few numbers for it, the bins are of equal width and the result says
why. Changing these settings does not make the scan stale: only the histograms
that use them are computed again.

## Stored results

Each result is stored with a key made of what it depends on: the scan, the field,
the method and the settings that change its outcome. Run the command again and
the file is not read again:

```text
Scan: scans\customers.scan.json (reused)
Second pass [customers.csv]: every result is already stored, the source is not read again.
Second pass: C:\data\scans\customers.deep.json (2 analyses: 0 computed, 2 reused, unchanged)
```

If you change the number of bins, only the histograms of numeric fields that are
binned are computed again. If a result is missing or failed, only that one is
computed. If the source, the scan settings or the version of Tabalyst changed,
the document no longer matches the scan and everything is computed again;
nothing is migrated.

## Asking first

The second pass can be costly on a very large file. It asks for a confirmation
before it starts when the estimated time may reach two minutes, or when the
selection goes beyond what Tabalyst chooses by itself on memory, cells or CPU. In
a terminal you answer the question; the default answer is no.

```console
tabalyst scan huge.csv --deep
tabalyst scan huge.csv --deep --yes
```

`--yes` starts it without asking. Outside a terminal (a script, a pipe, a
scheduled job) nothing is asked: the command stops with exit code `3` and starts
nothing unless you pass `--yes`. Exit code `3` also follows an answer of no. The
scan made to plan the second pass stays stored. With several files the question
is asked once, for all of them.

## If the file changed or is gone

Tabalyst compares the size of the file before reading it again and the digest of
what it read at the end. If the file is not the one the scan read, the
results of this run are discarded and no document is written (an earlier
`deep.json` stays as it was): the command prints an error and exits with code
`4`. Scan the file again to start from its current content. If the file cannot
be read again, the scan stays valid; restore the file and run the command again.
Tabalyst never copies a file to a temporary one.

## Python API

```python
import tabalyst

batch = tabalyst.generate_deep(["customers.csv"], confirmed=False)
for done in batch.successes:
    for analysis in done.outcome.document.analyses:
        print(analysis.id, analysis.status)
```

`tabalyst.generate_deep(inputs, confirmed=False)` does what the command does and
never prompts: when a confirmation is needed and `confirmed` is false, it raises
`tabalyst.ConfirmationRequired` before reading anything, with the estimate and
the reasons. `tabalyst.prepare_deep(inputs)` scans or reuses the scans and
returns the plans with the confirmation of the whole batch;
`tabalyst.execute_deep(preparation, confirmed=True)` runs them.

`tabalyst.run_second_pass(scan, source, plan)` runs one plan over one source and
returns the document without writing it. `previous=` takes a stored document
whose results are reused. A plan made for another scan raises
`tabalyst.StalePlan`; a file that changed raises `tabalyst.StaleSource`; a file
that cannot be read again raises `tabalyst.SourceNotReadable`.

## Options

`--deep` accepts the options that choose how the file is read and where the
scan goes (`-o`, `-d`, `-f`, `-c`, `--delimiter`, `--encoding`, `--collection`,
`--workers`, `--counters`, `-q`, `-v`, `--no-progress`). They apply to the first
pass; `--workers` also sets the processes of the second pass (`--workers 1`
keeps both in one process). `--yes` goes with `--deep`. With `--plan` it shows the plan without running
it.
