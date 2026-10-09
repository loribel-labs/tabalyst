---
title: Add histograms and exact medians with a second pass
description: What tabalyst scan --deep adds to a scan by reading the source again, when it asks before starting, which analyses it runs, where it writes its document and how stored results are reused.
---

`tabalyst scan --deep` reads a file a second time to add what the first pass of a
scan does not hold: histograms of numeric fields, with exact or estimated
medians and quantiles, the exact number of distinct values of an identifier-like
field, the exact counts of a field whose scan lists only some of them, the
length distribution of a text field when the scan lacks it, the inferred patterns
counted on every value, the dates counted per period and the correlation of
pairs of numeric columns. It writes them to a
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
or picks by itself. See [Deep settings](../reference/configuration.md#deep-settings).

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
pass. `--yes` goes with `--deep`. With `--plan` it shows the plan without running
it.
