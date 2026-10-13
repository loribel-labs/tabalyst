---
title: Add histograms and exact medians with a second pass
description: What tabalyst scan --deep adds to a scan by reading the source again, when it asks before starting, which analyses it runs, where it writes its document and how stored results are reused.
---

`tabalyst scan --deep` reads a file a second time to add what the first pass of a
scan does not hold: histograms of numeric fields, with exact or estimated
medians and quantiles, the exact number of distinct values of an identifier-like
field, the exact counts of a field whose scan lists only some of them, the
length distribution of a text field when the scan lacks it, the inferred patterns
counted on every value, the values that patterns and detectors leave out, the
repeated values of identifiers, the dates counted per period, the shape of the numbers
(asymmetry, outliers, decimals), the parts of the dates (year-month, weekday, hour), the missing
values and the values of a column along the file, the columns that miss a value together, the lengths of the arrays and the
sets of keys of the objects of a JSON file, the words and lines of long texts, the masks of sensitive columns, the numbers of amounts,
percentages and quantities with a unit, the correlation of
pairs of numeric columns, tables of a category against the pattern, length,
prefix or value of another column and the numbers of a column by category. It writes them to a
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
| `residual_values` | Fields whose patterns leave values out, or that a detector mostly reads but finds some invalid or unmatched values in | The values themselves with their exact counts and first records, and for each pattern an example and its distinct values |
| `duplicates_report` | Columns of almost all different values, and combinations of two columns you ask for | The values found more than once, with their counts and first records |
| `temporal_distribution` | Date fields, and columns of datetimes | The dates counted per day, month or year |
| `datetime_parts` | Date fields, columns of datetimes and of times | The dates counted by year-month, day of the week and hour, counted after a bound you give, with the ambiguous dates read under each order and the invalid ones counted by reason |
| `numeric_shape` | Numeric fields | The asymmetry and kurtosis, the outliers of Tukey, the decimals the numbers are written with, and a logarithmic and an equal-count histogram |
| `position_drift` | Fields of a dataset of at least 100 records that miss a value, or have few enough different values | The records, values and missing values of each tenth of the file, the slice where each value first appears, and whether the position tells the missing values or the values apart |
| `missing_matrix` | Columns of a dataset that lack a value in some records | For each column, the records where it lacks a value together with each other column |
| `array_profile` | JSON fields that hold arrays of different lengths | The number of arrays of every length, the quantiles of the lengths, the empty arrays and the items |
| `structure_variants` | JSON objects whose keys are not all in every object, and the records themselves (`$`) | The sets of keys the objects have, each with its exact count and the keys it lacks |
| `text_profile` | Fields of long texts (80 characters or more) | The words, lines and digits of the texts, by powers of two and by tenth of the characters |
| `fingerprint_distinct` | Fields whose values are too long for the exact set | The distinct values told apart by a 128-bit fingerprint, and the texts found more than once, by digest |
| `sensitive_forms` | Masked sensitive fields | The masks of the values and, for addresses and phone numbers, their classes, without a value or a count below a floor |
| `measure_extraction` | Fields of amounts with a currency, percentages or quantities with a unit | The numbers of the values, with the metrics of a numeric field for the whole field and for each currency or unit, and the units counted as values |
| `pearson_correlation` | Pairs of numeric columns of one dataset | The Pearson correlation over every row where both columns have a number, with the number of those rows and of the rows left out |
| `category_crosstab` | A column of a few values and another text or integer column | The count of the rows of each category in each pattern, length or prefix of the other column, with the purity of each category, the exceptions, Cramér's V and candidate rules |
| `category_stats` | A column of a few values and a numeric column | For each category: the count, extremes, sum, mean, spread, signs and a histogram of the numbers, with estimated quantiles, and the share of the variance the categories explain |

A scan always holds the length histogram of a text field unless it was limited
or turned off, so `length_distribution` is rare. `tabalyst scan --plan --deep`
shows what a run would do.

## Patterns on every value

The scan infers a hierarchy of patterns from a sample of the distinct values of a
field: families (one structure, such as `AA-9999`), their patterns of fixed length
and the nodes that set a part of the values apart (`'AK-'9999`). Its shares count
distinct values, not occurrences. The second pass reads every value of the file
once, as it is in the file (before any cleaning), finds its family and counts it for
the deepest pattern or node that reads it. The counts add up: the values read by a
family, the values no family reads (`unknown_structure`) and the values that were
not tested (too long, too many tokens, or JSON numbers and booleans) make the values
of the field. The number of patterns and nodes does not change what a value costs.

```json
{"kind": "pattern_counts", "accuracy": "exact", "computed_from": "source",
 "values": 3000, "matched": 2990,
 "families": [{"id": "f1", "occurrences": 2990,
   "distinct": {"count": 2410, "accuracy": "exact"},
   "patterns": [{"id": "f1.p1", "render": "AA-9999", "occurrences": 2990,
     "distinct": {"count": 2410, "accuracy": "exact"}, "rest": 2990}],
   "tables": [], "new_variants": {"length": 0, "segment": 0}}],
 "unknown_structure": 10,
 "excluded": {"non_string": 0, "too_long": 0, "too_complex": 0}}
```

A value that the scan never saw but that a family reads is counted as a **new
variant** of that family, not as an error: a prefix that was not in the sample
(`segment`), or a set of lengths no pattern has (`length`). A value that no family
reads is an observation about its structure, not an error: the dominant pattern is
not a rule of your data. The second pass does not look for new structures among
them. The values of each facet are counted in a table whose size is bounded
(`deep.patterns.table_bytes`): when it is full the most frequent values are kept and
the result says it is limited. The distinct values of each pattern and node are exact
unless the set that holds them would pass `deep.patterns.distinct_bytes`, and the
result then says `at_least`. When the scan holds every distinct value with its exact
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

## Values that patterns and detectors leave out

The scan counts how many distinct values no pattern reads and how many values a
detector finds invalid or does not match, and keeps a few examples. The second
pass keeps the values themselves, with their exact counts:

```json
{"kind": "residual_values", "records": true,
 "tables": [{"source": "pattern", "state": "other", "occurrences": 100,
             "distinct": 3, "complete": true,
             "listed": [{"value": "x", "count": 38, "first_record": 23},
                        {"value": "n/a", "count": 33, "first_record": 13},
                        {"value": "??", "count": 29, "first_record": 169}]}]}
```

This tells what the 100 values of a code column that follow no pattern are (`n/a`,
`??` and `x`) without opening the file, and where the first of each is. It does the
same for a detector that reads most of a column: the `invalid` values of a date column
(`2024-02-30`, with the reason `invalid_calendar_date` and the occurrences of each
reason) and its `not_matched` values (`unknown`). Each value is counted from the
first time it is met, so its count is exact; at most 10,000 distinct values are
tracked per table (`deep.residuals.max_tracked`), the occurrences of the others
are counted without their values and the result says it is bounded (`complete`
is false).

The same result gives each pattern of the scan an example, the record of its first
value and the exact number of distinct values it reads over every occurrence,
where the scan counted the distinct values of a sample.

When the scan holds every distinct value of the field with its exact count, the
source is not read: the values and counts follow from it (`computed_from` is
`samples`), without the records. Set `deep.residuals.records` to `true` to read
the source anyway and get them. A field whose values the exposure setting masks or
hides is left out.

## Repeated values

The second pass lists the values that occur more than once in a column that looks
like an identifier (almost all values different, or half of them under a name such
as `id` or `ref`), with the exact number of occurrences of each and the record of
the first:

```json
{"kind": "duplicates", "values": 1000000, "distinct": 999890,
 "redundant": 110, "unique": false,
 "repeated": {"distinct": 100, "occurrences": 210,
              "listed": [{"value": "8a1f03c9d2", "count": 4,
                          "first_record": 52113}]}}
```

A column the scan proved unique is not read. When the scan holds every distinct
value, the repeated ones follow from its exact counts without reading the source
(no record: set `deep.duplicates.records` to `true` to read it anyway). Otherwise
each value is held as a 128-bit digest and the record of its first occurrence, so
the memory grows with the number of distinct values but not with their length; it
is drawn from the same budget as the exact distinct count, and a search the budget
stops proves only a lower bound (`duplicates_limited`), never a count.

A combination of two columns is searched only when you ask for it, with a
request of the [Python API](plan.md#python-api) that names both columns,
`tabalyst.AnalysisRequest("duplicates_report", field="client", partner="year")`; the
planner never proposes one by itself. The result gives the combinations that repeat (`columns` names the two columns),
the rows where one of them has no value (`incomplete`) and the first record of
each. The source is always read.

## Amounts, percentages and quantities

A scan recognizes `$12.50`, `12,50 €`, `37%` or `215 Go` and counts each currency
or unit, but its `numeric` block only describes the numbers written without a
marker. The second pass reads the number of every such value, with the same
reading as the scan, and gives three levels:

1. **The field as a numeric field**: the members of the `numeric` block (`count`,
   `min`, `max`, `sum`, `mean`, variance, `median` and the others) and a histogram
   with its quantiles, over every value that has a number.
2. **The same for each currency or unit**: `Go`, `km/h` and `To` each get their
   own metrics and histogram, the most frequent first (20 at most, the rest
   together in `other`).
3. **The currencies or units as values**: how many there are, how many values use
   each and their share, the most frequent one, the rare ones, and whether the
   marker is written before or after the number, with a space or not.

```json
{"kind": "measures", "accuracy": "exact", "storage": "table",
 "computed_from": "source", "detector": "quantity",
 "values": 2000, "parsed": 1801, "ambiguous": 0, "invalid": 0,
 "unparsed": 199, "scan_not_tested": 0, "homogeneous": false,
 "overall": {"count": 1801, "distinct": 676, "numeric": {"...": "..."},
             "histogram": {"kind": "bins", "...": "..."}},
 "groups": [{"marker": "Go", "count": 775, "numeric": {"...": "..."},
             "histogram": {"kind": "dense_counts", "...": "..."}}],
 "markers": {"kind": "unit", "count": 1801, "distinct": 4,
             "listed": [{"value": "Go", "count": 775, "parsed": 775,
                         "share": 0.4303}],
             "modes": ["Go"], "dominant_share": 0.4303}}
```

Nothing is converted: `$` and `€` stay two currencies, `Go` and `To` two units.
When the field mixes them, `homogeneous` is false and its overall metrics add
quantities that differ: read the groups first. A value such as `$4,825`, which
the settings can read as thousands or as a decimal comma, is `ambiguous`: it is
counted with its currency and never given a number, unless the column proves a
convention (see [Values with a unit read by the evidence](#values-with-a-unit-read-by-the-evidence)).
Values with the shape of an
amount that do not hold (`$12.5.0`) are `invalid`, and the others `unparsed`. The
four counts add up to the values of the field, and the counts are those of the
scan's detector; a difference fails the analysis. For percentages,
`percent_range` counts the values below 0, from 0 to 100 and above 100.

The numbers are counted exactly, value by value, so the median, the quantiles
and the modes are exact. When a field has more than 100,000 different pairs of a
unit and a number (`deep.measures.max_values`), every group goes on in bins whose
width is a power of two: the counts, sums, means and extremes stay exact, and the
median and quantiles become estimates with their bounds (`storage` is `grid`).
When the scan holds every distinct value with its exact count, the source is not
read (`computed_from` is `samples`), and the command says how many analyses it
computed from the scan. The cost grows with the number of different
values: `tabalyst report` leaves out by itself a column of more than 16,384
different values, and says so in its plan; `--deep` computes it.

### Values with a unit read by the evidence

`1,250 Kg`, `1.250 Kg` and `1 250 Kg` are a number and a unit, but the number may
be 1250 or 1.25. Like the numbers of a column without unit, they are read by the
evidence of the column, with the evidence of the detector that reads them
(`currency`, `percentage` or `quantity`):

- If at least `detectors.<id>.min_evidence` (3) unambiguous values of the column
  are written in one convention (`12,5 Kg` is a decimal comma, `1,234.5 Kg` a
  decimal point) and none in the other, the ambiguous values are read in it and
  counted with the others. With a decimal comma proven, `1.250 Kg` is 1250, a
  thousands group, rather than 1.25.
- If the column uses both conventions, or too few values prove one, the ambiguous
  values stay `ambiguous` and are not given a number.
- A convention given by `detectors.<id>.ambiguous_convention` always wins, and
  `detectors.<id>.infer_convention: false` turns the rule off. A plain
  `1 250 Kg` reads the same in both conventions and proves nothing.

When the rule applies, the plan says so (`number_convention` in the parameters of
the analysis, with the reason `ambiguous_numbers_read_by_evidence`), `resolved`
counts the values read that way, `ambiguous` is 0, and `resolution` says what
was done and why:

```json
"parsed": 1000, "ambiguous": 0, "resolved": 382,
"resolution": {"convention": "comma", "source": "evidence",
               "evidence": {"comma": 469, "dot": 0}}
```

`parsed` includes the `resolved` values. The scan itself is not changed: its
`coverage` still counts those values as `ambiguous`, which is why the second
pass compares its counts with the scan's after adding them. The result is kept
for a given convention only: another one makes it again.

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
 "covariance": 3.0158, "slope": 3.0062, "intercept": 0.5041,
 "r_squared": 0.99093,
 "rank": {"kind": "spearman_binned", "accuracy": "estimated", "bins": 64,
          "bins_first": 64, "bins_second": 64, "edges_first": "rows",
          "edges_second": "rows", "defined": true, "coefficient": 0.99337,
          "lower": 0.96413, "upper": 0.99999}}
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

**The line.** `slope` and `intercept` are the least-squares line of the second
column on the first over the common rows, `slope = covariance / variance of the
first column`, and `r_squared` is the share of the variance of the second column
that the line explains. They come from the same co-moments as the coefficient at no
extra cost, exist when the coefficient does, and stop at the common rows: the line
says nothing of rows outside the range of the first column.

**The rank correlation.** A relation that always goes up (or always down) without
being a line has a small Pearson coefficient and a large Spearman one, the Pearson
coefficient of the ranks. The file cannot be sorted in memory, so the second pass
counts the common rows in a grid of `bins` by `bins` bins (`deep.pearson.rank_bins`,
64; `0` turns it off), with the edges of each column at quantiles of what the scan
kept of it (`edges_first` and `edges_second` say whether that was the row sample,
the distinct values or, when the scan kept too little, equal widths). The
`coefficient` is the Pearson coefficient of the mid-ranks of the bins and is an
**estimate** (`accuracy` `estimated`). `lower` and `upper` are certain bounds: the
exact Spearman coefficient, whatever order the values have inside their bins and
however many of them tie, is between them. Bins that hold few rows make the bounds
close; a column that fits in one bin has no rank, and `reason` is `single_bin_first`
or `single_bin_second` (never `0`).

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

When the rank correlation is on, the sample also gives each pair a Spearman
coefficient (`rank_coefficient`, `rank_lower`, `rank_upper`, `rank_score` in the
`exploration` of the plan), and a pair is ranked by the larger of its two scores, so
a relation that is monotone without being a line can be picked by itself.

## A category against a feature of another column

A column of a few values, such as a region, can determine the shape of another
column, such as a client identifier. The second pass counts, over every row, how
many rows of each category fall in each class of a **feature** of that other
column: the pattern that reads its value, its length, its first characters, or the
value itself (another category). It
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
most frequent first two characters of the values it lists, those of a `value` the
most frequent values of the column (at most `deep.crosstab.max_classes` less one).
Whatever is not one of
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
  each cell, in file order, with the record number. The listed cells are the 20 largest
  (`deep.crosstab.max_exception_cells`); `exceptions.complete` says whether that was all of
  them, and `cells` how many there are.
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

- `provided_rules` exist only when you gave rules to check (see below).

An association is not a cause, and the pattern of an identifier that follows its
region is a fact about the file, not a constraint of the source system.

**Two categories.** The feature `value` sets a category against the values of another
column that is a category too, for instance a region against a plan. Two columns that
could both be the category are read in one direction by the planner, with the column
that has fewer distinct values as the rows (the first of the file on a tie), so one
phenomenon does not take two tables of the automatic choice. A request can ask for
the other direction.

**A rule you give.** The API can ask the table to check rules you wrote, each the
label of a category and the label of the class its rows should take,
`tabalyst.AnalysisRequest("category_crosstab", field="region", partner="plan",
feature="value", rules=[("east", "basic")])`. Each rule is checked as it is, without a
threshold, in `provided_rules`: `provenance` `provided`, `status` (`holds`, `violated`,
`no_rows` when the category has no classified row, `unknown_category` or
`unknown_class` when a label is not on an axis of the table), `support` (the
classified rows of the category), `confidence`, `exceptions` and the
`counter_examples`: the cells that break the rule, with their exact counts and first
rows. A rule you give is never proposed by itself and is part of the key of the result.

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

## The numbers of a column by category

A category, such as a contract type, often explains a number, such as a premium. The
second pass describes the number for each value of the category, over every row: how
many numbers there are, their smallest and largest, their sum, mean and spread, how
many are positive, negative or zero, and a histogram. As for the correlations, it does
not try every pair of the file: it first rates them on the rows the scan sampled,
which needs no reading of the source, keeps the best ones, and reads the file once
for them.

```json
{"kind": "category_stats", "accuracy": "exact_counts", "precision": "float64",
 "source": "source", "rows": 3000, "counted": 2998,
 "excluded": {"category_missing": 2, "value_missing": 0, "both_missing": 0},
 "bins": {"strategy": "linear", "requested_strategy": "linear",
          "bounds_source": "range", "edges": [-3097.96, -2937.04, "..."]},
 "overall": {"count": 2998, "min": -3097.96, "max": 4948.16,
             "sum": 3669685.72, "mean": 1224.04, "std": 825.89,
             "positive": 2973, "negative": 25, "zero": 0,
             "counts": ["..."], "median": {"...": "..."}, "quantiles": ["..."]},
 "groups": [{"rows": 1228, "value_missing": 0, "count": 1228,
             "min": -1636.84, "max": 2736.77, "sum": 1358808.14,
             "mean": 1106.52, "std": 571.44,
             "positive": 1217, "negative": 11, "zero": 0,
             "counts": ["..."],
             "median": {"level": 0.5, "value": 1038.98,
                        "accuracy": "estimated", "lower": 925.1,
                        "upper": 1086.02},
             "quantiles": ["..."]}, "..."],
 "association": {"defined": true, "n": 2998, "groups": 6,
                 "eta_squared": 0.3465, "epsilon_squared": 0.3454,
                 "score": 0.5877}}
```

`groups` follow the classes of `categories` (the most frequent values of the category,
then `other` for the rest), and `rows` is `counted` plus the three exclusions: a row
with a number and no category (`category_missing`), a row with a category and no number
(`value_missing`: the cell is empty, is not a number, or does not fit a 64-bit float)
and a row with neither. A category with no number is listed with its `rows` and a
`count` of `0`, and nothing else.

**Exact or estimated.** The counts (`count`, `positive`, `negative`, `zero`, the
`counts` of the bins) are exact, and so are the smallest and largest numbers. The
sum, the mean and the spread (`std`, the population standard deviation) are computed
in 64-bit floats, the sum from correctly rounded partial sums and the spread from
stable moments. Every category is counted in the **same bins** (`bins.edges`, placed
as the other histograms are, see `deep.bin_strategy`), so the histograms of two
categories can be set side by side. A bin does not say where its numbers are, so the
quantiles (5, 25, 50, 75 and 95%) are **estimates**: each comes with the lowest and
highest value it can have, tightened by the extremes of the category, and the true
value is always between them.

**What the categories explain.** `eta_squared` is the share of the variance of the
number that the categories explain (the correlation ratio, from 0 to 1).
`epsilon_squared` is the same share corrected for the bias that grows with the number
of categories, which is why a column of many values does not look better than it is,
and `score` is its square root. The class `other` takes no part in them. There is no
`score` when the categories cannot be compared, and `reason` says why instead of
giving `0`: `too_few_rows`, `single_category` (only one category has a number) or
`no_variance` (the number never varies). It shows an association, not a cause: a
region can explain a price without causing it.

**How the pairs are chosen.** The category follows the rules of the tables above
(2 to 100 distinct values, repeated, not an identifier, not hidden by exposure) and the
number those of the correlations (numeric, varies, not an identifier). The plan
counts the columns it left out, by reason, in `relations.stats`. A pair is rated by
the corrected ratio on the interior rows of the sample (a complete sample is used
whole), and "not found in the sample" does not mean "absent". When both columns could
be the category, such as two small integer codes, the one with fewer distinct values
is the category, so that one relation does not take two places. A request can ask for
the other direction.

**What is automatic.** `tabalyst report` picks by itself the pairs whose `score` is
0.45 or more, two at most (`deep.stats.automatic_stats`). `--deep` takes every pair
the plan lists, twenty at most, after asking if the estimate calls for it. The API can
ask for any pair, even one that the sample did not show:
`tabalyst.AnalysisRequest("category_stats", field="contract_type",
partner="premium")`; the category comes first.

**Small files.** When the scan sampled every row of a CSV file (up to 1,000 rows), the
sample is the file: the pair is computed from it and the source is not read again
(`source` is `samples`).

## The shape of the numbers

A histogram says where the numbers are; it does not say whether the column is
lopsided, whether it has outliers or how many decimals its numbers are written
with. The second pass counts each different number of the column (up to
`deep.shape.max_values`, 100,000 by default) and gives the shape of the whole
column, exactly where it can.

```json
{"kind": "numeric_shape", "accuracy": "exact", "storage": "table",
 "count": 3000, "distinct": 2338,
 "moments": {"precision": "float64", "skewness": 5.1256,
             "excess_kurtosis": 51.2233},
 "tukey": {"accuracy": "exact",
           "q1": {"level": 0.25, "value": 9.86, "accuracy": "exact"},
           "q3": {"level": 0.75, "value": 37.9025, "accuracy": "exact"},
           "iqr": 28.0425,
           "fences": [{"factor": 1.5, "low": -32.20375, "high": 79.96625,
                       "below": {"certain": 0, "possible": 0},
                       "above": {"certain": 235, "possible": 235}},
                      {"factor": 3.0, "low": -74.2675, "high": 122.03,
                       "below": {"certain": 0, "possible": 0},
                       "above": {"certain": 90, "possible": 90}}]},
 "scale": {"places": [{"places": 1, "count": 561}, {"places": 2, "count": 1731},
                      {"places": 3, "count": 708}],
           "max_places": 3, "trailing_zero": 279, "mixed": true},
 "log": {"kind": "bins", "strategy": "log", "...": "..."},
 "equal_count": {"kind": "bins", "strategy": "sample_quantile", "...": "..."}}
```

- **Asymmetry and kurtosis.** `skewness` is positive when the long tail is on the
  right, `excess_kurtosis` is 0 for a normal distribution and grows with the
  weight of the tails. They come from centered sums in 64-bit floats
  (`precision`), so they are accurate to a few units in the twelfth digit, not
  exact fractions. They are absent, with a `reason`, when they have no meaning:
  `no_variance`, `too_few_values` (fewer than 3 numbers) or `not_representable`.
- **Outliers of Tukey.** The fences are `q1 - k * iqr` and `q3 + k * iqr` for
  `k` = 1.5 (mild) and 3 (far); `below` and `above` count the numbers strictly
  beyond. With `storage` `table` the quartiles are exact and so are the counts
  (`certain` equals `possible`). Beyond `deep.shape.max_values` different numbers
  the column goes on in bins: the counts of numbers, the extremes and the decimals
  stay exact, the quartiles become estimates with certain bounds (`accuracy`
  `bounds`), and each count of outliers is bracketed: `certain` numbers are
  beyond the fence whatever the true quartiles are, `possible` ones may be.
- **Decimals.** `places` counts the numbers written with 0, 1, 2... digits after
  the point, as they are written (`12.50` has 2); `trailing_zero` counts those
  whose last decimal is a 0, and `mixed` says that the decimal numbers do not all
  have the same number of decimals, which often means two sources of data.
- **Two more views of the spread.** `log` places the bins at equal ratios between
  the smallest and the largest number, which shows a skewed column; it needs
  strictly positive numbers, and `log_reason` is `non_positive` otherwise.
  `equal_count` places the inner bounds at quantiles of what the scan kept (the
  `sample_quantile` strategy of the histogram), so that the bins hold about as
  many numbers each. The counts of both are exact over the whole file whatever the
  storage, and the edges are fixed by the scan alone.

It is not chosen by `tabalyst report` by itself: ask for it with `--deep`
or `tabalyst.AnalysisRequest("numeric_shape", field="price")`.

## The parts of the dates

The distribution over time says when, over a granularity chosen from the span. The
parts say which month of which year, which day of the week and which hour, always
by month. The second pass reads each date as the scan did and places it by the calendar date as
it is written: the offset of a datetime such as `2024-03-10T23:30:00-05:00` is not
converted, so that dates and hours are the ones in the file.

```json
{"kind": "datetime_parts", "accuracy": "exact", "temporal_kind": "date",
 "zone": "as_written", "values": 1500, "count": 1316, "ambiguous": 0,
 "invalid": 52, "unplaced": 132, "scan_not_tested": 0,
 "invalid_reasons": [{"reason": "invalid_calendar_date", "count": 37},
                     {"reason": "mixed_separators", "count": 15}],
 "year_months": [{"period": "2022-03", "count": 38},
                 {"period": "2022-04", "count": 36}, "... 26 others"],
 "weekdays": [{"value": 0, "count": 190}, "... 6 others"],
 "as_of": "2023-06-30", "after_as_of": 818}
```

- **Parts.** `year_months` lists the months that occur, in order (`YYYY-MM`), whatever
  the span. The count per year and per month of the year are sums of it, so they are
  not repeated: add the months of a year for the year, the months with the same
  number for the month of the year. `weekdays` (0 for Monday to 6) lists every day of
  the week, empty ones included; `hours` (0 to 23) lists the hours that occur, for
  datetimes and times. A column of times has hours only.
- **After a bound.** With `deep.datetime.as_of` set to a date (`YYYY-MM-DD`),
  `after_as_of` counts the dates after it. The bound is never the date of the day,
  so a result does not change with the clock; without it nothing is counted.
- **Ambiguous dates.** A date such as `03/04/2024` can be the 3rd of April or the
  4th of March. When the column does not settle the order (see [Ambiguous dates
  read by the evidence](#ambiguous-dates-read-by-the-evidence)), the scan counts it
  as `ambiguous` and does not place it, and so do the parts. `simulation` reads those dates again under each order (`DMY` and
  `MDY`) and counts the year-months and days of the week each reading would give: only
  the month and the day change between the readings, never the year. It measures
  what the choice of `detectors.date.ambiguous_order` would change, and applies
  nothing. There is no simulation when the configuration already chose an order.
- **Invalid dates.** `invalid_reasons` counts the values that have the shape of a
  date and do not hold, by the reason the detector gives (`invalid_calendar_date`,
  `invalid_time`, `mixed_separators`...). Their total is the `invalid` count of the
  scan's date detector; `unplaced` is every other value (not a date, or a date of
  another kind).

`values = count + ambiguous + invalid + unplaced`. It is not chosen by
`tabalyst report` by itself: ask for it with `--deep` or
`tabalyst.AnalysisRequest("datetime_parts", field="created_at")`.

## Ambiguous dates read by the evidence

A date such as `03/04/2020` can be the 3rd of April or the 4th of March. The scan
does not guess: it counts it as `ambiguous` and does not place it. The second
pass is smarter when the column itself settles the question.

- If the unambiguous dates of the column are all day-month (`25/03/2020`,
  `14-07-2021`) and none is month-day, every ambiguous date is read day-month, and
  the other way round. The separators do not matter, and neither do dates written
  year first (`2020-03-25`), which are never ambiguous.
- If the column has both orders, or none (only ambiguous dates), they stay
  ambiguous and are not placed. So do they when too few dates prove the order:
  `deep.datetime.min_evidence` (3 by default) is the fewest unambiguous dates that
  must read in that order and none in the other.
- An order given by `detectors.date.ambiguous_order` always wins, and the setting
  `deep.datetime.infer_order` set to `false` turns the rule off.

When the rule applies, the dates are counted again from the source: the
distribution over time and the parts of the dates place the ambiguous dates with
the others, `resolved` counts them, `ambiguous` is 0, and `resolution` says what
was done and why:

```json
"resolved": 644, "ambiguous": 0,
"resolution": {"order": "DMY", "source": "evidence",
               "evidence": {"DMY": 274, "MDY": 0}}
```

`resolved` counts the ambiguous dates that are valid now (they are in `count`);
`ambiguous` is what is left. They were read day-month because 274 unambiguous
dates are day-month and none is month-day. The scan itself is not changed: its `temporal`
block still leaves those dates out, which is why the years it counts no longer
answer for such a column and the second pass reads the source.

## A column along the file

A column can change along a file without any value being wrong: the last tenth is
exported by another system, a field stops being filled from a given date, a new code
appears halfway. The totals of the scan hide it. The second pass cuts the records in
ten slices of the same size, in file order, and counts the values and the missing
ones of each.

```json
{"kind": "position_drift", "accuracy": "exact",
 "records": 1003, "values": 869, "missing": 134,
 "slices": [
   {"first_record": 1, "records": 101, "values": 97, "missing": 4},
   {"first_record": 102, "records": 100, "values": 0, "missing": 100},
   "... 8 others"],
 "missing_association": {"defined": true, "n": 1003,
                         "corrected": 0.8585, "stable": true, "...": "..."}}
```

- **Slices.** A record has a value for the field or it has none. The slice `k` (0 to
  9) holds the records `p` such that `p * 10 // records = k`, with `p` the position
  of the record from 0, so the slices differ by one record at most. `missing` is
  `records - values` and `first_record` is numbered from 1. A cell is a value when
  the scan counts it as content: an empty cell, a blank one, a null marker, a JSON
  `null` and an absent key are records without a value. The totals are checked
  against the scan, which counted the same cells.
- **Is the column drifting?** `missing_association` is Cramér's V (corrected, as for
  [a category against a feature](#a-category-against-a-feature-of-another-column)) of the
  slice against the presence of a value: it is near 0 when the missing values are
  spread evenly and approaches 1 when they sit in some slices. It has no score,
  and says why, when nothing is missing.
- **The values themselves.** When the scan holds every distinct value of the field
  with its exact count and there are at most `deep.drift.max_tracked` of them (1,000
  by default), `followed` counts each value in each slice. The scan lists 100
  values by default (`scan.limits.max_listed_frequencies`), so a column of up to 100
  different values is followed unless the scan was asked to list more: `distinct` values, the
  `max_listed` most frequent in `listed` (`counts` has ten numbers, `first_slice`
  tells where the value first appears) and the others summed up in `other`.
  `new_values` of a slice counts the values seen there for the first time, and
  `followed.association` is Cramér's V of the slice against the value, over every
  value. A field with more values is followed by its missing values only.

A change along the file shows that the column was filled or exported differently, not
why. The analysis needs at least 100 records, leaves out a field that repeats inside a
record (the items of an array), a field whose values exposure withholds, and every
field when the scan left records out (the tolerant error policy), because the number of
a record then no longer gives its place. A column that misses nothing and has too
many different values to follow has nothing to show and is not proposed.

It is not chosen by `tabalyst report` by itself: ask for it with `--deep` or
`tabalyst.AnalysisRequest("position_drift", field="region")`.

## Columns that miss a value together

When two columns lack a value in the same records, they probably come from the same
place: a form that was left half filled, a system that does not know a customer, a
join that found nothing. The scan counts the missing values of each column and says
nothing of their overlap. The second pass counts, for every pair of columns that miss
a value somewhere, the records where both do.

```json
{"kind": "missing_matrix", "accuracy": "exact",
 "records": 1003, "missing": 134, "columns": 4, "partners": 3,
 "truncated": false,
 "listed": [
   {"field": "column_4", "display": "ref", "missing": 144, "both": 120},
   {"field": "column_6", "display": "note", "missing": 247, "both": 31}]}
```

- **A result for each column.** The result of a column says how many records lack a
  value for it (`missing`) among the `columns` of the dataset that miss one, how
  many of them (`partners`) lack one in at least one of the same records, and lists
  the strongest: for each, `missing` is its own count and `both` the records where
  both columns lack a value. Every count is exact, listed or not.
- **The strongest first.** Partners are ordered by the share of the records that
  lack a value in either column where both do (120 of the 158 records that lack a
  phone or a reference), then by `both`. `max_listed` of them are listed (10 by
  default), `truncated` says that more exist. A column that is always missing with
  another has a share of 1.
- **Which columns.** The columns that have a value somewhere and miss one somewhere,
  not repeated inside a record and whose values exposure does not withhold. A dataset
  where more than `deep.missing.max_columns` (100) of them qualify is left out, because
  the pairs grow with the square of the columns, and so is a dataset where fewer than
  two do. The matrix counts the same columns whichever of them a plan selects.

The records are counted once for all the columns, in bit sets of a batch, so a
wide file costs little more than its cells. The totals are checked against the scan.
It shows that values go missing together, not why.

It is not chosen by `tabalyst report` by itself: ask for it with `--deep` or
`tabalyst.AnalysisRequest("missing_matrix")`.

## Arrays and sets of keys in JSON

A JSON file is not a table: a field can hold an array of any length, and an object can
have any of its keys. The scan counts the arrays of a field and gives the shortest, the
longest and the total of their items. It counts how many objects hold each key. It does not
tell how long the arrays usually are, nor which keys the objects have **together**. The
second pass does.

```json
{"kind": "array_profile", "accuracy": "exact",
 "arrays": 414, "empty": 61, "items": 998,
 "min_length": 0, "max_length": 5, "mean_length": 2.41,
 "quantiles": [
   {"level": 0.5, "value": 2, "accuracy": "exact"}, "... 4 others"],
 "length_histogram": [
   {"length": 0, "count": 61},
   {"length": 1, "count": 86}, "... 4 others"]}
```

- **Arrays.** The result counts every length that occurs, in an array at any depth: the
  items of an array of objects, an array in an array. The quantiles follow from the counts
  of every length, so they are exact. The totals are checked against the scan, which
  counted the same arrays. An array field whose arrays all have the same length is already
  answered by the scan (`lengths_constant`), and one whose lengths spread over more than
  `deep.arrays.max_lengths` (10,000) values is left out.

```json
{"kind": "structure_variants", "accuracy": "exact",
 "objects": 500, "keys": 4, "always": 2,
 "key_names": ["id", "tags", "orders", "addr"],
 "distinct": 4, "complete": true, "untracked": 0,
 "listed": [
   {"count": 268, "keys": 4, "absent": [], "absent_total": 0},
   {"count": 146, "keys": 3, "absent": ["addr"], "absent_total": 1}],
 "other_objects": 0}
```

- **Sets of keys.** Objects that have the same keys are one set. The result counts the
  objects of each set exactly, for the objects of a field (`addr`, `orders[]`) and for the
  records of the source, which the scan holds as no field and the plan names `$`. Each set
  lists the keys of the object that it lacks (`absent`, the first `deep.structure.max_keys`
  of them, 30 by default, and `absent_total` counts them all); `always` counts the keys that
  every object has.
- **Bounded.** `deep.structure.max_variants` sets (1,000 by default) are tracked, each
  counted exactly from its first object. If objects have more, `complete` is `false`,
  `distinct` is a lower bound and `untracked` counts the objects whose set was not
  followed. `max_listed` sets are listed, the most frequent first (10 by default); the
  others are summed up in `other_objects`.
- **Which objects.** The keys are the fields the scan named below the object, so a dataset
  whose paths the scan stopped naming (`untracked_paths`) is left out, and so is an object
  field that is alone, has no key, or whose keys are all in every object (`uniform_keys`):
  there is one set, and the scan already says so. A CSV or Excel file has no object.

Both show that arrays and objects differ, not why. They are not chosen by `tabalyst report`
by itself: ask for them with `--deep` or
`tabalyst.AnalysisRequest("structure_variants", field="$")`.

## Long texts

A column of comments, descriptions or messages is not a column of values: no two are alike,
so the scan samples them and counts none. The second pass reads every text once and keeps
what it is made of, never the text.

```json
{"kind": "text_profile", "accuracy": "exact",
 "texts": 3000, "characters": 610108, "words": 117718,
 "min_words": 15, "max_words": 63, "mean_words": 39.24,
 "lines": 4023, "max_lines": 2, "multi_line": 1023,
 "digits": 117285, "digit_share": 0.192,
 "word_buckets": [
   {"low": 8, "high": 15, "count": 35}, "... 2 others"],
 "line_buckets": [
   {"low": 1, "high": 1, "count": 1977}, "... 1 other"],
 "digit_buckets": [0, 87, 1640, 1209, 64, 0, 0, 0, 0, 0, 0]}
```

- **What is counted.** A word is a run of characters that are not white space
  (`str.split`), a line is one that `str.splitlines` cuts, and a digit is a decimal digit of
  Unicode. The texts are the original ones, before any cleaning. The buckets count the texts
  by powers of two (0, 1, 2 to 3, 4 to 7, and so on) of words and of lines; `digit_buckets`
  counts them by tenth of the characters that are digits: the first count is the texts with
  none, the next ten the texts whose share is up to a tenth, two tenths, and so on.
- **Memory.** The state is a few counters, whatever the texts. The analysis applies to a
  field whose longest value has at least `deep.texts.min_length` characters (80) or whose
  values the scan sampled as long texts.

```json
{"kind": "fingerprint_distinct", "accuracy": "fingerprint_based",
 "algorithm": "blake2b", "bits": 128,
 "values": 3000, "distinct": 300, "redundant": 2700, "unique": false,
 "repeated": 299, "repeated_occurrences": 2999,
 "listed": [
   {"digest": "992bd5b9...", "count": 21}, "... 9 others"],
 "truncated": true}
```

- **Distinct long texts.** A text too long for the exact set of the distinct count is told
  apart by a 128-bit fingerprint (BLAKE2b). Two different texts are taken for one only if
  their digests collide, which is about as unlikely as 2^-128 for a pair, so the count is
  `fingerprint_based` and not `exact`. The digest is the one the scan gives its long texts, so a
  listed digest can be found in its sample. `listed` shows the `deep.texts.max_listed`
  texts found most often (10 by default) by digest and count, never the text. A column of
  texts that are all different is answered by the scan.
- **Memory.** The table holds 16 bytes and a count for each distinct text, within the memory
  that the plan gave the exact sets of the run. If a column needs more, its result is
  `limited` with the reason `memory_budget`, as for the exact distinct count.

Neither is chosen by `tabalyst report` by itself. A field whose values exposure masks or
hides has neither.

## Sensitive columns without a value

The scan masks the values of a sensitive column (an email address, an IP address, a phone
number) and keeps their counts. The second pass may count more about it, with one rule: the
document never holds a value, nor a figure about so few values that it singles them out.

**This is off by default.** Until you set `deep.sensitive.enabled` to `true`, the second pass leaves
every masked or hidden column out, as it always did, and the plan holds no `sensitive_forms`
candidate. Turn it on in the configuration file, `{"deep": {"sensitive": {"enabled": true}}}`,
or in Python with `DeepSettings.model_validate({"sensitive": {"enabled": True}})`.

```json
{"kind": "sensitive_forms", "accuracy": "exact", "exposure": "mask",
 "values": 4000, "forms": 10, "complete": true,
 "untracked": 0, "min_count": 5,
 "listed": [{"form": "999.999.9.999", "count": 690}, "... 6 others"],
 "other_forms": 0, "other_values": 0,
 "classes": {"detector": "ip_address",
             "listed": [{"form": "ipv4_private", "count": 2700},
                        {"form": "ipv4_public", "count": 1292}],
             "other": 8, "unclassified": 0}}
```

- **Masks.** Every mask the values take, with its exact count: `192.168.1.20` is
  `999.999.9.99`. The scan lists the most frequent ones; this is all of them. A mask taken
  by fewer than `deep.sensitive.min_count` values (5 by default) is not listed but summed up in
  `other_forms` and `other_values`, and so is the least frequent listed mask when what is
  summed up would hold fewer values than that, so the sum is not a figure about a few
  values either.
- **Classes.** For a column an IP address or a phone number detector reads, the count of the
  values by class of a closed list: `ipv4_public`, `ipv4_private`, `ipv6_loopback`... for an
  address, `fr_01` to `fr_09` (the zone of a French number: a region, a mobile, a special
  line) and `nanp_geographic`, `nanp_toll_free` and `nanp_premium` for a North American
  number. The area code of a North American number is never a class. The same floor applies.
- **The exact distinct count.** `exact_distinct` also runs on a masked or hidden column,
  when the scan stopped counting its distinct values: its result is two numbers.
- **A hidden column** (`scan.exposure.sensitive_values` set to `hide`) gets the exact
  distinct count and nothing else: not even its masks.
- **No link between records.** These counts have no position, no row and no other column:
  the drift along the file, the missing values together, the pairs, the tables, the repeated
  values and the long texts stay out of a sensitive column.

These analyses are not chosen by `tabalyst report` by itself, even once enabled, and
`deep.sensitive` is part of the key of a result. Ask for them with `--deep` or
`tabalyst.AnalysisRequest("sensitive_forms", field="telephone")`.

## Exact distinct count

A scan stops counting the distinct values of a field after 100,000 of them (the
limit `max_distinct_per_field`) and keeps an estimate. The second pass counts
them all, exactly, on the original values of the file: before any cleaning, so
`00123`, `123` and `123 ` are three values, and `Ab` and `AB` two. A JSON string
`"123"` and the JSON integer `123` are two values too. Empty cells, blank cells,
null markers and JSON nulls are not values. A field whose values exposure masks or hides
is counted too once `deep.sensitive.enabled` is set (it is off by default): its result is these
numbers and no value (see [Sensitive columns without a value](#sensitive-columns-without-a-value)).

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
of a prefix) and the thresholds of the candidate rules. The `deep.stats` object does
it for the numbers by category, and sets the categories kept and the bins. The `deep.measures` object
sets how many currencies or units get metrics of their own and how many numbers
are counted exactly. The `deep.residuals` and `deep.duplicates` objects set how many
values are listed and tracked, and whether to read the source for the records. The `deep.drift` object
sets how many different values a column may have to be followed along the file and how many are listed,
and `deep.missing` how many columns a matrix of missing values may hold and how many partners are listed. The `deep.arrays`,
`deep.structure`, `deep.texts` and `deep.sensitive` objects set the lengths counted, the sets of keys tracked and listed, the length of a text and the
texts listed, and the floor under which a mask or a class is summed up. See [Deep
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
