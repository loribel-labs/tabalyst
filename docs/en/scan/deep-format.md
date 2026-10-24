---
title: Second pass format
description: Structure of the deep.json document written by tabalyst scan --deep, with its identity, plan, run, analyses and results, and the changelog of its format revisions.
---

`tabalyst scan --deep` and `tabalyst report` write a JSON document beside the scan: `deep.json` next
to a stored `scan.json`, or `<stem>.deep.json` next to a `<stem>.scan.json`. This
page describes format `tabalyst.scan.deep`, version `0.2.0`, revision `4`. The
format is **experimental**: it can change incompatibly between releases. Always
check `format`, `format_version` and `format_revision` first. Tabalyst does not
migrate a document of another revision; it makes it again. See [Add histograms and
exact medians](deep.md) for what the command does.

## Top level

```json
{
  "format": "tabalyst.scan.deep",
  "format_version": "0.2.0",
  "format_revision": 4,
  "status": "complete",
  "base": {
    "format_revision": 4,
    "engine_version": "0.7.0",
    "source_sha256": "6d4d860f...",
    "config_sha256": "67dbd515...",
    "facts_sha256": "b1d9ecee..."
  },
  "settings": {"bins": 100, "bin_strategy": "linear"},
  "settings_sha256": "3cc11de3...",
  "plan": {"...": "..."},
  "run": {"...": "..."},
  "analyses": ["..."]
}
```

| Member | Meaning |
| --- | --- |
| `status` | `complete` when every analysis is complete, `partial` otherwise |
| `base` | The scan the document stands on: its format revision, the version of Tabalyst, the digest of the source, the digest of the settings and the digest of its facts. A document is valid for that scan only |
| `settings` | The `deep` settings of the run, with their digest |
| `plan` | The plan that was run, whole, as [`tabalyst scan --plan`](plan.md) describes it |
| `run` | What the latest run did |
| `analyses` | One entry per selected analysis, in the order of the plan |

The scan itself is not part of the document and is never rewritten by it.

## Run

```json
{
  "started_at": "2026-10-09T04:27:13Z",
  "duration_seconds": 0.03,
  "timings": {"reading": 0.0035, "analysis": 0.0246, "other": 0.0019},
  "workers": 1,
  "peak_memory_bytes": 83402752,
  "source_read": true,
  "source_verified": true,
  "records_read": 5000,
  "cells_read": 10000,
  "executed": 2,
  "reused": 0,
  "skipped": 0
}
```

`source_verified` says that the digest of the bytes read was compared with the
scan's at the end, as it must be before anything is written. A run that read
nothing, because every result was stored, has `source_read` and `source_verified`
false. `cells_read` counts the cells handed to the analyses, not those of the
whole file. `peak_memory_bytes` covers the whole process, so it includes earlier
work in the same process, such as a first pass.

## An analysis

```json
{
  "id": "numeric_histogram:rows:column_2",
  "analyzer": "numeric_histogram",
  "analyzer_version": 1,
  "dataset": "rows",
  "field": "column_2",
  "display": "price",
  "method": "bins",
  "parameters": {"bins": 100, "strategy": "linear"},
  "domain": "analytical",
  "key": "7900c328...",
  "status": "complete",
  "result": {"kind": "bins", "...": "..."}
}
```

An analysis of a pair of fields also has `partner`, the id of the second field, and
its `display` names both (`price and cost`). The field of the entry is the first of
the pair in the order of the dataset.

`domain` is `analytical`: values are those of the scan after its normalization,
so `" 1 "` and `"1"` are the same value. It is `original` for `exact_distinct`, which
counts the values as they are in the file, as the cardinality of the scan does.
`key` identifies what the result
depends on (see below). `status` is one of:

| Status | Meaning |
| --- | --- |
| `complete` | The result is there and agrees with the scan |
| `failed` | The analysis did not give a result; `reason` says why and `detail` gives counts or the type of an exception, never a value of your data |
| `skipped` | The analysis was selected but did not run: it needs the source and the report was built without reading it (`source_not_read` for a report of a scan document, `source_unavailable` when the source is not beside it), or it has no executor (`not_available`) |
| `limited` | The analysis met a limit and says what it holds. Only `exact_distinct` does (reason `memory_budget`): its result is a lower bound. The histograms never do, their size does not depend on the data |

The reasons of a failure are `scan_mismatch` (the counts of the second pass are
not those the scan reported, or a value cannot be read as the scan read it, such
as a decimal in a field counted by integer), `unrepresentable` (a result that a
float64 cannot hold) and `analysis_error` (the analysis raised an exception).

## Results

**`dense_counts`**: one counter per integer, for an integer field whose range
holds at most 65,536 integers. All of it is exact.

```json
{
  "kind": "dense_counts",
  "count": 5000,
  "min": 18,
  "max": 90,
  "distinct": 73,
  "values": [{"value": 18, "count": 74}, {"value": 19, "count": 71}],
  "modes": [29],
  "modes_truncated": false,
  "median": {"level": 0.5, "value": 53, "accuracy": "exact"},
  "quantiles": [{"level": 0.05, "value": 21, "accuracy": "exact"}]
}
```

`values` lists the integers that occur, in ascending order. `modes` lists every
value tied for the most frequent, ten at most. `quantiles` has the levels 0.05,
0.25, 0.5, 0.75 and 0.95.

**`bins`**: the count in each bin of a numeric field.

```json
{
  "kind": "bins",
  "strategy": "linear",
  "requested_strategy": "linear",
  "bounds_source": "range",
  "count": 5000,
  "min": 0.18,
  "max": 999.96,
  "edges": [0.18, 10.1778, "..."],
  "counts": [44, 43, "..."],
  "outside": {"below": 0, "above": 0},
  "median": {
    "level": 0.5,
    "value": 496.43,
    "accuracy": "estimated",
    "lower": 490.07,
    "upper": 500.07
  },
  "quantiles": ["..."]
}
```

Bin `i` holds the values from `edges[i]` included to `edges[i + 1]` excluded; the
last bin also includes the maximum. `counts` are exact. `edges` are written as
numbers, and an edge that a float64 cannot represent exactly may be rounded in the
file, though the counts used its exact value. `bounds_source` is `range` (equal
widths between the exact minimum and maximum), `rows` or `distinct` (quantiles of the
row sample or of the sample of distinct values, for `bin_strategy:
"sample_quantile"`), or `grid` (multiples of a power of two, in a `measures` result
beyond `max_values`; the first and last edges are the exact minimum and maximum). When the sample cannot place the bounds, `strategy` is
`linear` while `requested_strategy` is `sample_quantile`, and `reason` is
`sample_too_small` or `sample_without_spread`. `outside` counts values beyond the
bounds of the scan; anything but zero fails the analysis.

A quantile of level `q` among `n` values is interpolated linearly between the
values at ranks `(n - 1) * q` rounded down and up; the median of an even count
is the mean of the two middle values. `accuracy` is `exact` when the quantile is
read from counters of integers, and `estimated` when it is read from bins: then
`lower` and `upper` bracket it, and the true quantile is always between them.

**`lengths`**: the same block as `string_lengths` in the [scan
format](format.md): `count`, `min_length`, `max_length`, `mean_length`,
`median_length` and `length_histogram`, with `kind` added.

**`distinct`**: the exact number of distinct original values of a field.

```json
{"kind": "distinct", "accuracy": "exact", "values": 1000000,
 "distinct": 998317, "redundant": 1683, "unique": false}
```

`values` is the number of values the count is taken over (content strings and
JSON integers, numbers and booleans; empty, blank, marker and null cells are not
values), `redundant` is `values - distinct` and `unique` is `distinct == values`.

**`distinct_limited`**: what a stopped count proves.

```json
{"kind": "distinct_limited", "accuracy": "lower_bound",
 "values_read": 640000, "lower_bound": 639112}
```

The field has at least `lower_bound` distinct values among the first
`values_read`. It is never the count of the field.

**`frequencies`**: the exact count of every distinct value of a field of at most
1,000 values, from the most to the least frequent (ties by text, then by type).
Values are analytical, as in `frequencies` of the [scan format](format.md): each
has its native type, so the string `7`, the string `007` and the integer `7` are
three values.

```json
{"kind": "frequencies", "count": 5000, "distinct": 180,
 "values": [{"value": "007", "type": "string", "count": 74}],
 "modes": [{"value": "007", "type": "string", "count": 74}],
 "modes_truncated": false}
```

`modes` lists the values tied for the most frequent, ten at most.

**`pattern_counts`**: the families, patterns and nodes that the scan inferred for a
field (see [Inferred patterns](format.md#inferred-patterns)) counted on every value
of the file, in the original domain.

```json
{
  "kind": "pattern_counts",
  "accuracy": "exact",
  "computed_from": "source",
  "grammar_version": 2,
  "algorithm_version": 1,
  "values": 3000,
  "matched": 2990,
  "families": [{
    "id": "f1",
    "occurrences": 2990,
    "distinct": {"count": 2410, "accuracy": "exact"},
    "patterns": [{
      "id": "f1.p1",
      "render": "AA-9999",
      "occurrences": 2985,
      "distinct": {"count": 2405, "accuracy": "exact"},
      "rest": 85,
      "nodes": [{
        "id": "f1.p1.n1",
        "render": "'AK-'9999",
        "occurrences": 2900,
        "distinct": {"count": 2300, "accuracy": "exact"},
        "rest": 2900
      }]
    }],
    "tables": [{
      "facet": "head:1",
      "capacity": 512,
      "cells": [{"value": "AK", "occurrences": 2900},
                {"value": "KL", "occurrences": 80}],
      "others": 5,
      "saturated": true
    }],
    "new_variants": {"length": 5, "segment": 80}
  }],
  "unknown_structure": 10,
  "excluded": {"non_string": 0, "too_long": 0, "too_complex": 0}
}
```

Every value counts once, for the deepest pattern or node that reads it: `rest` is
what a pattern or a node reads and none of its `nodes` does, and `occurrences` is
`rest` plus the `occurrences` of its `nodes`. A family adds up its `patterns`, the
combinations of lengths that its `lengths` table holds and its new variants of
length. The values add up: `matched + unknown_structure + excluded = values`, with
`matched` the sum of the families and `excluded` the sum of its three members. A
value that no family reads is an observation of structure, never an error.

`new_variants` counts values of a known family that the scan never saw: a set of
lengths (`length`, the family reads the structure but no pattern has these
lengths) or the value of a segment that a facet reads (`segment`, such as a prefix
that was not in the sample), for a facet whose every value in the sample was one of
its cells. Neither is an unknown structure or an invalid value.

Each `tables` entry counts the values of a facet of the family over every
occurrence: the cells the scan listed and the values it never saw. At most
`capacity` cells are kept, the most frequent; `others` counts the occurrences of
the other values and `saturated` says that the table is limited. The table of
`lengths` lists combinations of lengths.

`distinct` is `exact` when the scan holds the whole distribution or when the set of
the distinct values fit `deep.patterns.distinct_bytes`; otherwise it is `at_least`
and the count is a lower bound. `computed_from` is `samples` when the exact counts
of the scan were enough (nothing was read), `source` when the file was read. The
result has the same members either way.

**`periods`**: the dates of a field per calendar period.

```json
{
  "kind": "periods",
  "accuracy": "exact",
  "granularity": "month",
  "temporal_kind": "date",
  "zone": "as_written",
  "values": 3000,
  "count": 2990,
  "ambiguous": 8,
  "unplaced": 2,
  "first": "2016-09",
  "last": "2027-08",
  "periods": [{"period": "2016-09", "count": 21}]
}
```

`granularity` is `day`, `month` or `year`, and `period` is written `YYYY-MM-DD`,
`YYYY-MM` or `YYYY`. `periods` lists the non-empty periods in order. `count` is the
number of dates of `temporal_kind` the scan counted, `ambiguous` the ambiguous
values of the scan, and `unplaced` the other content values (not dates, invalid,
or of another kind): `values = count + ambiguous + unplaced`.

**`pearson`**: the correlation of a pair of numeric fields over the rows where both
have a number.

```json
{
  "kind": "pearson",
  "accuracy": "exact_counts",
  "precision": "float64",
  "rule": "pairwise_complete",
  "source": "source",
  "min_pairs": 10,
  "rows": 3000,
  "pairs": 2571,
  "excluded": {"first_missing": 0, "second_missing": 429, "both_missing": 0},
  "defined": true,
  "coefficient": 0.995454,
  "mean_first": 0.0082,
  "mean_second": 0.5288,
  "std_first": 1.0016,
  "std_second": 3.0249,
  "covariance": 3.0158,
  "slope": 3.0062,
  "intercept": 0.5041,
  "r_squared": 0.99093,
  "rank": {
    "kind": "spearman_binned", "accuracy": "estimated", "bins": 64,
    "bins_first": 64, "bins_second": 64, "edges_first": "rows", "edges_second": "rows",
    "defined": true, "coefficient": 0.99337, "lower": 0.96413, "upper": 0.99999
  }
}
```

`rows = pairs + first_missing + second_missing + both_missing`. `first_missing` counts
the rows with a number in the second column only, `second_missing` in the first
only, `both_missing` in neither. The means, spreads (population) and covariance are
those of the `pairs` common rows. The counts are exact; the coefficient is computed
in 64-bit floats (`precision`). When `defined` is false there is no `coefficient`,
nor means, and `reason` is `insufficient_pairs` (fewer than `min_pairs` common rows),
`zero_variance_first` or `zero_variance_second`; a coefficient is never written as
`0` for lack of data. `source` is `samples` when the complete row sample of the scan
held every row (CSV files of up to 1,000 rows), `source` when the file was read.

`slope`, `intercept` and `r_squared` are the line of the second field on the first over the
`pairs` common rows, from the same co-moments; they are present when `coefficient` is. `rank`
is present when `deep.pearson.rank_bins` is not `0`: the Spearman coefficient read from a grid
of `bins` by `bins` bins cut at quantiles of what the scan kept (`edges_first` and `edges_second`
are `rows`, `distinct` or `range`). It is an **estimate** (`accuracy` `estimated`): `coefficient`
is the Pearson coefficient of the mid-ranks of the bins and `lower` and `upper` bound the exact
Spearman coefficient whatever the order of the values inside their bins. `bins_first` and
`bins_second` count the bins that hold a row. When `defined` is false there is no coefficient and
`reason` is `insufficient_pairs`, `single_bin_first` or `single_bin_second`.

**`crosstab`**: the table of the rows of each category by class of a feature of another
field. See [A category against a feature](deep.md#a-category-against-a-feature-of-another-column).

```json
{
  "kind": "crosstab",
  "accuracy": "exact_counts",
  "precision": "float64",
  "source": "source",
  "feature": {"kind": "prefix", "version": 1, "prefix_length": 2},
  "categories": {"field": "column_1", "display": "region", "domain": "analytical",
                 "classes": [{"id": "c1", "label": "QC"}, {"id": "other", "label": "other", "kind": "other"}]},
  "classes": {"field": "column_2", "display": "client_id", "domain": "original",
              "classes": [{"id": "x1", "label": "QC"}, {"id": "other", "label": "other", "kind": "other"}]},
  "rows": 300, "counted": 299,
  "excluded": {"category_missing": 0, "feature_missing": 1, "both_missing": 0, "unclassified": 0},
  "counts": [[100, 0], [0, 0]],
  "row_totals": [100, 0], "column_totals": [100, 0],
  "by_category": [], "purity": {}, "association": {}, "exceptions": {}, "rules": []
}
```

(Shortened: `by_category`, `purity`, `association`, `exceptions` and `rules` are described
below and in the page above.) `rows = counted + category_missing + feature_missing +
both_missing + unclassified`, and the margins add up to `counted`. The first axis,
`categories`, is the rows of `counts`, the second, `classes`, its columns; the
last class of each axis is `other`, which stays when no row falls in it. The `domain` of
an axis is the domain of the values it reads: a category is `analytical`, a
`pattern` or a `prefix` is `original` and a `length` or a `value` is `analytical`. The analysis itself has the
domain `mixed`. The `feature` kind is `pattern`, `length`, `prefix` or `value` (the value of the field
itself, against its most frequent values).

- `by_category[i]` has `rows`, `classified` (the rows in the table), `feature_missing`,
  `unclassified`, `coverage` (`classified / rows`), `dominant` (the index of the class that
  holds most of the category, the first in a tie), `dominant_count`, `purity`
  (`dominant_count / classified`) and `exceptions` (`classified - dominant_count`).
- `purity.forward` and `purity.reverse` have `dominant`, `total` and `value`; the reverse goes
  from class to category. `purity.baseline` is the share of the most frequent class.
- `association` has `defined`, `n`, `effective_categories`, `effective_classes` (the axes
  that have a count), and when defined `chi_square`, `degrees`, `cramers_v`, `corrected` (the
  bias-corrected V), `low_share` (the share of cells whose expected count is under 5, on
  the axes of at least 5 rows), `stable` and `sparse` (the number of axes with fewer than
  5 rows, which stay in the table and do not take part in `stable`). When `defined` is false there is no score and `reason` is `single_category`,
  `single_class` or `too_few_rows`; a score is never written as `0` for lack of data.
- `exceptions` has `count` (the rows outside the dominant class of their category), `cells`,
  `complete` (every cell is listed) and `listed`, the largest cells, 20 at most by default
  (`deep.crosstab.max_exception_cells`), each with `category` and `column` (indexes), `count` and
  `examples`: up to three `{record, value}` in file order, the value cut at 64 characters.
- `rules` are candidates only: `status` `candidate`, `provenance` `learned`, `category`
  and `column` (indexes), `support`, `confidence` and `exceptions`.
- `provided_rules` (only when the request gave rules) check the rules a user wrote:
  `provenance` `provided`, `status` (`holds`, `violated`, `no_rows`, `unknown_category`,
  `unknown_class`), `category_label` and `class_label`, `category` and `column` (indexes, absent
  for an unknown label), `support` (the classified rows of the category), `confidence`,
  `exceptions` and `counter_examples`, the cells outside the class in the form of `listed`.

The counts are exact and the figures computed from them (purity, V) are 64-bit floats
(`precision`). `source` is `samples` when the complete row sample of the scan held every row
(CSV files of up to 1,000 rows).

**`category_stats`**: the numbers of a column described for each value of a category. See
[The numbers of a column by category](deep.md#the-numbers-of-a-column-by-category).

```json
{
  "kind": "category_stats",
  "accuracy": "exact_counts",
  "precision": "float64",
  "source": "source",
  "categories": {"field": "column_22", "display": "type_contrat", "domain": "analytical",
                 "classes": [{"id": "c1", "label": "auto"}, {"id": "other", "label": "other", "kind": "other"}]},
  "rows": 3000, "counted": 2998,
  "excluded": {"category_missing": 2, "value_missing": 0, "both_missing": 0},
  "bins": {"strategy": "linear", "requested_strategy": "linear", "bounds_source": "range",
           "edges": [-3097.96, -2937.04, "...", 4948.16]},
  "overall": {"count": 2998, "min": -3097.96, "max": 4948.16, "sum": 3669685.72,
              "mean": 1224.04, "std": 825.89, "positive": 2973, "negative": 25, "zero": 0,
              "counts": ["..."], "median": {"...": "..."}, "quantiles": ["..."]},
  "groups": [{"rows": 1228, "value_missing": 0, "count": 1228, "...": "..."}],
  "association": {"defined": true, "n": 2998, "groups": 6, "eta_squared": 0.3465,
                  "epsilon_squared": 0.3454, "score": 0.5877}
}
```

`rows = counted + category_missing + value_missing + both_missing`: a row with a number and no category,
a row with a category and no number (the cell is empty, is not a number or does not fit a 64-bit float)
and a row with neither. `groups` follow `categories.classes` (`other` last) and each is a summary of the
numbers of one category: `count`, `min`, `max`, `sum`, `mean`, `std` (population), `positive`, `negative`
and `zero` (they add up to `count`), `counts` (one counter per bin of `bins`, adding up to `count`),
`median` and `quantiles` (levels 5, 25, 50, 75 and 95%), plus its `rows` (with or without a number) and
`value_missing`. A category with no number has `count` `0` and none of the other members except `counts`.
`overall` is the same summary for all the groups together. `bins.edges` has the extremes of the scan and
the inner edges, strictly increasing; bin `i` is `[edges[i], edges[i + 1])`, the last one closed on the right,
and a number goes to a bin by comparison of 64-bit floats. `bounds_source` is `range`, `rows` or `distinct`.
The counts, the minima and the maxima are exact; the sum, mean and spread are computed in 64-bit floats
(`precision`); the quantiles are estimates read from the bins (`accuracy` `estimated`) with `lower` and
`upper` bounds the true value cannot leave. `association` is the share of the variance the categories
explain: `eta_squared`, the same corrected for the number of groups (`epsilon_squared`, not below 0) and
its square root `score`, over the `n` numbers of the `groups` named categories (`other` takes no part).
When `defined` is false there is no figure and `reason` is `too_few_rows`, `single_category` or
`no_variance`. `source` is `samples` when the complete row sample of the scan held every row
(CSV files of up to 1,000 rows).

**`numeric_shape`**: the shape of the numbers of a column. See
[The shape of the numbers](deep.md#the-shape-of-the-numbers).

```json
{
  "kind": "numeric_shape",
  "accuracy": "exact",
  "storage": "table",
  "count": 3000,
  "distinct": 2338,
  "moments": {"precision": "float64", "skewness": 5.1256, "excess_kurtosis": 51.2233},
  "tukey": {"accuracy": "exact",
            "q1": {"level": 0.25, "value": 9.86, "accuracy": "exact"},
            "q3": {"level": 0.75, "value": 37.9025, "accuracy": "exact"},
            "iqr": 28.0425,
            "fences": [{"factor": 1.5, "low": -32.20375, "high": 79.96625,
                        "below": {"certain": 0, "possible": 0},
                        "above": {"certain": 235, "possible": 235}}]},
  "scale": {"places": [{"places": 2, "count": 3000}], "max_places": 2,
            "trailing_zero": 279, "mixed": false},
  "log": {"kind": "bins", "strategy": "log", "requested_strategy": "log", "bounds_source": "range", "...": "..."},
  "equal_count": {"kind": "bins", "strategy": "sample_quantile", "...": "..."}
}
```

`storage` is `table` when every different number was counted (`accuracy` `exact`) and `grid`
beyond `deep.shape.max_values` (`exact_counts`): `distinct` exists with the table only, the
quartiles of `tukey` are estimates read from bins whose width is a power of two (`accuracy`
`bounds`, `lower` and `upper` on `q1` and `q3`) and each count of a fence is bracketed by `certain`
and `possible`. `moments` holds `skewness` (third standardized moment of the population) and
`excess_kurtosis` (fourth, minus 3) from centered sums in 64-bit floats (`precision`), or a `reason`
instead: `no_variance`, `too_few_values` or `not_representable`. `tukey.fences` has the fences at
`factor` 1.5 and 3 interquartile ranges (`low`, `high`) and the numbers strictly `below` and `above`.
`scale.places` counts the numbers by the digits written after the point, `trailing_zero` those that end
with a 0 decimal and `mixed` is true when the decimal numbers do not share one count of decimals.
`log` (absent with a `log_reason`, `non_positive`, when a number is not positive) and `equal_count`
are `bins` histograms (see `numeric_histogram`) whose `strategy` is `log` (bounds at equal ratios) or
`sample_quantile`; the counts are exact whatever the storage.

**`datetime_parts`**: the parts of the calendar dates of a field. See
[The parts of the dates](deep.md#the-parts-of-the-dates).

```json
{
  "kind": "datetime_parts",
  "accuracy": "exact",
  "temporal_kind": "date",
  "zone": "as_written",
  "values": 1500, "count": 1316, "ambiguous": 0, "invalid": 52, "unplaced": 132,
  "scan_not_tested": 0,
  "invalid_reasons": [{"reason": "invalid_calendar_date", "count": 37}],
  "year_months": [{"period": "2022-03", "count": 38}],
  "weekdays": [{"value": 0, "count": 190}],
  "as_of": "2023-06-30", "after_as_of": 818
}
```

`values = count + ambiguous + invalid + unplaced`; `count` and `ambiguous` are those of the scan's
`temporal` block and `invalid` the `invalid` of its date detector (`scan_not_tested` values it did not
test were read here, and found at most that many more). `year_months` lists the months that occur,
in order, as `{period: "YYYY-MM", count}`; the counts per year and per month of the year are sums of
it and are not repeated. `weekdays` (0 for Monday to 6) lists every day of the week and `hours` (0 to 23)
the hours that occur, for datetimes and times; a column of times (`temporal_kind` `time`) has `hours`
only. The dates are placed by the calendar date as written (`zone`). `as_of` and `after_as_of` exist
when `deep.datetime.as_of` is set. `simulation` exists when `ambiguous` is not 0: `readings` has one
entry per order (`DMY`, `MDY`) with the `year_months`, `weekdays` and `placed` count the ambiguous
dates would give, and `after_as_of`.

**`resolution`** (in `periods` and `datetime_parts`, absent when the ambiguous dates were not read): the
order the ambiguous dates were read in. Both results also have `resolved`, the number of ambiguous
dates that this made valid (0 without a `resolution`). `order` is `DMY` or `MDY`, `source` is `evidence` (the unambiguous dates of
the column read in that order only, whatever their separator; the order of the configuration is not a
`resolution`, the scan already used it) and `evidence` counts the unambiguous dates by order. The
`resolved` dates are counted in `count` and `ambiguous` is 0 (`values = count + ambiguous + invalid + unplaced`). See
[Ambiguous dates read by the evidence](deep.md#ambiguous-dates-read-by-the-evidence).

**`measures`**: the numbers of a field of amounts with a currency, percentages or
quantities with a unit, read as the scan's `detector` (`currency`, `percentage` or
`quantity`) read them.

```json
{
  "kind": "measures",
  "accuracy": "exact",
  "storage": "table",
  "computed_from": "source",
  "detector": "currency",
  "values": 2000,
  "parsed": 1662,
  "ambiguous": 99,
  "invalid": 67,
  "unparsed": 172,
  "scan_not_tested": 0,
  "homogeneous": false,
  "overall": {
    "count": 1662,
    "distinct": 1654,
    "numeric": {"count": 1662, "min": -9985.75, "max": 997.93, "...": "..."},
    "modes": [26.83, 167.93, 412.57, 542.35,
              577.06, 585.4, 645.85, 992.14],
    "modes_truncated": false,
    "histogram": {"kind": "bins", "bounds_source": "range", "...": "..."}
  },
  "groups": [
    {"marker": "$", "count": 906, "numeric": {"...": "..."},
     "histogram": {"...": "..."}}
  ],
  "markers": {
    "kind": "currency",
    "count": 1761,
    "distinct": 3,
    "listed": [{"value": "$", "count": 1005, "parsed": 906, "share": 0.5707}],
    "truncated": false,
    "modes": ["$"],
    "dominant_share": 0.5707,
    "rare": {"share_below": 0.01, "markers": 0, "count": 0},
    "layout": {"before": 1312, "after": 449, "spaced": 756, "unspaced": 1005}
  }
}
```

- `values` are the values of the field: `parsed` have a number, `ambiguous` have a
  number part the settings can read two ways (counted, never given a number),
  `invalid` have the shape of an amount that does not hold, and `unparsed` are the
  rest. They add up to `values`. When the scan's detector tested every value, the
  first three are its `matched`, `ambiguous` and `invalid`, and the counts of each
  currency or unit are those of its `details`; a difference is `scan_mismatch`.
  `scan_not_tested` counts the values the scan's detector did not test, which the
  second pass read: it finds at least what the scan found, never more than those
  values add.
- `resolved` and `resolution` appear when the unambiguous values of the column
  prove a convention for the ambiguous ones: `resolution` has the `convention`
  (`dot` or `comma`), the `source` (`evidence`) and the `evidence`, the unambiguous
  values the scan's detector counted in each convention. `resolved` is the number
  of values read that way (the ambiguous ones and, with `comma`, `1.250` read as
  1250), `parsed` includes them and `ambiguous` is the ones left, 0. `resolved`
  is 0 and `resolution` absent otherwise. See
  [Values with a unit read by the evidence](deep.md#values-with-a-unit-read-by-the-evidence).
- `overall`, each of `groups` and `other` are levels. A level has `count`,
  `numeric` (the members of the `numeric` block of the scan, `coverage` being the
  share of `values`), `histogram` (a `dense_counts` or `bins` result) and, with
  `storage` `table`, `distinct` (numbers that differ) and `modes` (ten at most).
  `groups` are the currencies or units that have a number, the most frequent first,
  `max_groups` of them; `other` (absent when empty) holds the rest together, with
  `markers`, their number. Nothing is converted: `homogeneous` is false when
  several currencies or units have numbers.
- `storage` is `table` when every number was counted exactly: the median, the
  quantiles and the modes are `exact`, and `accuracy` is `exact`. Beyond
  `max_values` different pairs of a marker and a number, every group goes on in
  bins whose width is a power of two: `storage` is `grid`, `accuracy` is
  `exact_counts`, the counts, sums and extremes stay exact, the median of
  `numeric` is `limited` (reason `max_values`) and the quantiles of the histogram
  are estimates with their bounds. The width depends on the range of the numbers
  only, not on their order.
- `markers` counts the values written with each currency, `%` or unit, parsed or
  ambiguous (`parsed` of them have a number): `count`, `distinct`, `listed` by
  decreasing count then text (`truncated` beyond 1,000), `modes`, `dominant_share`,
  `rare` (the markers written in less than 1% of them) and `layout` (marker
  `before` or `after` the number, `spaced` or not). `kind` is `currency`, `percent`
  or `unit`.
- `percent_range`, for percentages only, counts the parsed values `below` 0,
  `within` 0 to 100 and `above` 100.
- `computed_from` is `samples` when the scan holds every distinct value with its
  exact count: the source is not read and the result is the same.

**`residual_values`**: the values that patterns and detectors leave out.

```json
{
  "kind": "residual_values",
  "accuracy": "exact",
  "computed_from": "source",
  "records": true,
  "values": 3000,
  "tables": [
    {
      "source": "pattern", "state": "other",
      "occurrences": 100, "distinct": 3, "complete": true,
      "untracked": 0, "too_long": 0, "truncated": false,
      "listed": [
        {"value": "x", "count": 38, "first_record": 23},
        {"value": "n/a", "count": 33, "first_record": 13}
      ]
    },
    {
      "source": "detector", "detector": "date", "state": "invalid",
      "occurrences": 131, "distinct": 83, "complete": true,
      "untracked": 0, "too_long": 0, "truncated": true,
      "listed": [{"value": "2002-02-31", "count": 5, "first_record": 604}],
      "reasons": [{"reason": "invalid_calendar_date", "count": 131}]
    }
  ],
  "patterns": [
    {"id": "p1", "render": "XX9999", "occurrences": 1622,
     "distinct": 1619, "distinct_accuracy": "exact",
     "example": "CH7427", "first_record": 3}
  ],
  "pattern_excluded": {"non_string": 0, "too_long": 0, "too_complex": 0},
  "detectors": [
    {"detector": "date", "eligible": 3000, "matched": 2705, "ambiguous": 0,
     "invalid": 131, "not_matched": 164, "scan_not_tested": 0}
  ]
}
```

- A table holds what one source leaves out in one state. The `pattern` source has
  the state `other`: the values no candidate pattern reads. A `detector` source
  names a detector of the scan, replayed on the analytical text of each value as the
  first pass read it, and has the state `invalid` (the shape of the detector, but
  a value that does not hold) or `not_matched`. A table with no occurrence is
  absent.
- `occurrences` is exact. A value enters the table the first time it is met, so
  the count of every listed value is exact. At most `max_tracked` distinct values
  are tracked per table; the occurrences of the values met after that are only
  counted in `untracked`, a value longer than `max_value_length` characters is
  counted in `too_long` and never listed, and `complete` is then false.
  `distinct` counts the tracked values; `listed` holds the `max_listed` most
  frequent, by count then text, and `truncated` says that more were tracked.
- `reasons` split the occurrences of an `invalid` table by the reason the detector
  gave.
- `patterns` gives each candidate pattern of the scan its `occurrences` (each value
  counts for the most specific pattern that reads it, as in `pattern_counts`), the
  `distinct` values it reads over every occurrence (`exact`, or `at_least` when
  the memory budget stopped the sets), one value it reads and, with `records`, the
  record of that value. `pattern_excluded` counts the values the patterns do not
  test: strings longer than the inference reads, strings of too many tokens, and
  JSON numbers or booleans.
- `detectors` repeats the counts of each replayed detector. They are checked against
  the scan's coverage: exactly when the scan tested every value, and, when it left
  values untested (adaptive detection), at least what it counted and no more than
  those values can add. A difference is `scan_mismatch`.
- `records` is true when the source was read: each listed value then has the
  `first_record` (from 1) of its first occurrence. When the scan holds every
  distinct value with its exact count, the source is not read, `computed_from` is
  `samples`, `records` is false and the records are absent; the setting
  `deep.residuals.records` reads the source anyway.

**`duplicates`** and **`duplicates_limited`**: the values found more than once in a
column that looks like an identifier, or in a combination of two columns.

```json
{
  "kind": "duplicates",
  "accuracy": "exact",
  "computed_from": "source",
  "records": true,
  "values": 1000000,
  "distinct": 999890,
  "redundant": 110,
  "unique": false,
  "repeated": {
    "distinct": 100, "occurrences": 210, "tracked": 100,
    "untracked": 0, "complete": true, "truncated": true,
    "listed": [{"value": "8a1f03c9d2", "count": 4, "first_record": 52113}]
  }
}
```

- `values` are the values read, `distinct` the distinct original values (exact),
  `redundant` is `values - distinct` and `unique` says that nothing repeats.
  `repeated.distinct` is how many values occur more than once and
  `repeated.occurrences` their occurrences in all, the first of each included.
- The value of a listed entry has its `count` (exact) and, with `records`, the
  `first_record`. Up to `max_tracked` repeated values are tracked; the
  occurrences of the others are in `untracked` and make `complete` false, the
  accuracy `exact_counts`. `listed` holds the `max_listed` most repeated.
- When the source is read, a value is held as a 128-bit BLAKE2b digest with the
  record of its first occurrence, so that the memory does not depend on the length
  of the values; two values collide with a probability under one in 10^20 for a
  billion values. When the scan holds every distinct value with its exact count,
  the repeated ones follow from it (`computed_from` `samples`, no record).
- For a combination of two columns (a request for the analyzer with a `partner`),
  `columns` names them, `values` are the rows where both have a value, `incomplete`
  the rows where one has none, and `value` of a listed entry is the list of their
  values. The source is always read.
- `duplicates_limited` is the result when the memory budget stopped the search
  (`status` `limited`, reason `memory_budget`): `values_read` values were met,
  with at least `distinct` distinct values and `repeated` repeated ones. It is a
  lower bound, never a count.

**`position_drift`**: a field followed by position in the file.

```json
{
  "kind": "position_drift",
  "accuracy": "exact",
  "records": 1003, "values": 869, "missing": 134,
  "slices": [
    {"first_record": 1, "records": 101, "values": 97, "missing": 4},
    {"first_record": 102, "records": 100, "values": 0, "missing": 100}
  ],
  "missing_association": {
    "defined": true, "n": 1003,
    "effective_categories": 2, "effective_classes": 10,
    "chi_square": 747.43, "degrees": 9, "cramers_v": 0.863,
    "corrected": 0.858, "low_share": 0.0, "stable": true, "sparse": 0
  },
  "followed": {
    "distinct": 4,
    "listed": [
      {"value": "QC", "type": "string", "count": 429,
       "counts": [101, 100, 99, 24, 22, 32, 29, 22, 0, 0],
       "first_slice": 0}
    ],
    "other": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    "association": {"defined": true, "corrected": 0.704, "...": "..."}
  }
}
```

- `slices` always holds ten entries. Their `records` add up to the `record_count` of the
  dataset, `values + missing = records` in each, and the sum of `values` equals the
  `values.count` of the scan, or the result is `scan_mismatch`.
  `new_values`, the distinct values seen for the first time in the slice, is present
  only with `followed`.
- `missing_association` and `followed.association` have the members of the
  `association` of a `crosstab` result: `defined` is false, with a `reason`
  (`single_category` when nothing is missing), when there is no score. The first is the
  table of presence (two rows) by slice, the second the table of every distinct
  value by slice.
- `followed` is present when the plan asked for the values (`values` 1) and lists the
  `max_listed` most frequent by count, then text, then type, with `counts`, its exact
  count in each of the ten slices, and `first_slice` (0 to 9). `other`
  sums the counts of the values not listed in each slice. The counts of every value are
  checked against the frequencies the scan lists, entry by entry.
- It is exact for every count. The values of a field whose exposure is `mask` or
  `hide` are never read: the planner leaves the field out.

**`missing_matrix`**: the columns that lack a value together with one column.

```json
{
  "kind": "missing_matrix",
  "accuracy": "exact",
  "records": 1003, "missing": 134, "columns": 4, "partners": 3,
  "truncated": false,
  "listed": [
    {"field": "column_4", "display": "ref", "missing": 144, "both": 120}
  ]
}
```

- `missing` is the number of records of the dataset without a value for the column,
  `records - values.count` of the scan, which is checked. `columns` is the number of
  columns of the dataset in the matrix, this one included, and `partners` how many of
  the others lack a value in at least one of the same records.
- `listed` holds at most `max_listed` partners, by decreasing share of the records that
  lack a value in either column where both do (`both / (missing + partner.missing -
  both)`), then by `both`, then in document order. A partner is named by its field id
  and display path; `missing` is its own count and `both` the records where both
  lack a value. `truncated` is true when `partners` exceeds the list.
- The matrix of a dataset is computed once for all its columns whichever of them the plan
  selects, and a plan whose `columns` parameter is not the number the scan gives fails
  with `scan_mismatch`.

**`date_order`**: the order of the dates of two columns, record by record.

```json
{
  "kind": "date_order",
  "accuracy": "exact",
  "records": 100000, "compared": 69105, "equal": 0, "broken": 22,
  "excluded": {"missing": 16408, "not_a_date": 0, "ambiguous": 14487, "other_kind": 0},
  "truncated": true,
  "listed": [{"record": 11656, "first": "2026-12-09", "second": "2021-08-01"}]
}
```

- The analysis belongs to the first column of the pair; `partner` of the analysis is the
  second. `compared` records have a date in both columns of the same kind, of which `equal`
  fall on the same date or instant and `broken` have the first after the second.
  `records` is `compared` plus the four counts of `excluded`, and is checked against the
  scan (`scan_mismatch`).
- `listed` holds at most `max_listed` broken records in file order, `record` counting from
  1; `first` and `second` are ISO 8601. `truncated` is true when `broken` exceeds the list.
- Plan parameter: `max_listed`. It is part of the key of the result.

**`duplicate_rows`**: the extra copies of whole rows of a CSV file, counted with the engine of Dedup.

```json
{
  "kind": "duplicate_rows",
  "accuracy": "exact",
  "identity": "full_decoded_csv_row_v1",
  "calculation_version": 1,
  "records": 2600, "distinct_rows": 2000, "extra_copies": 600, "duplicate_groups": 540,
  "storage": "memory",
  "source_sha256": "6d4d860f..."
}
```

- The analysis belongs to the dataset, under the field `$` (`duplicate_rows_count:<dataset>:$`),
  and only a CSV source with one dataset has it. `identity` says how two rows are compared: the
  decoded cells of the whole row, without normalization, as `tabalyst dedup` compares them.
  `calculation_version` changes with the meaning of the count.
- `accuracy` `exact`: the reading went to the end of the file. `extra_copies` is what Dedup
  reports for it, `records` the number of data records (checked against the scan,
  `scan_mismatch`), and `source_sha256` the SHA-256 the reading hashed, which must be the scan's
  (`StaleSource` otherwise, and no document is written). The analysis is `complete`.
- `accuracy` `lower_bound`: the reading stopped at a ceiling after `records` records. The
  analysis is `limited` with the `reason` `memory_budget`, `disk_budget` or `row_limit`,
  `extra_copies` and `duplicate_groups` are lower bounds, `distinct_rows` counts the rows read,
  and there is no `source_sha256`.
- `storage` is `memory` or `disk`: where the table of distinct rows ended. No file is written
  beside the source.
- Plan parameters: `memory_mb`, `disk_mb` and `max_rows` (the settings `deep.copies`). They are
  part of the key of the result.

**`array_profile`**: the lengths of the arrays of a field.

```json
{
  "kind": "array_profile",
  "accuracy": "exact",
  "arrays": 414, "empty": 61, "items": 998,
  "min_length": 0, "max_length": 5, "mean_length": 2.41,
  "quantiles": [
    {"level": 0.5, "value": 2, "accuracy": "exact"}
  ],
  "length_histogram": [
    {"length": 0, "count": 61},
    {"length": 1, "count": 86}
  ]
}
```

- `arrays`, `empty`, `items`, `min_length` and `max_length` are checked against the `arrays`
  block of the scan, which counted the same occurrences. `length_histogram` holds every length
  that occurs, ascending, and the `quantiles` (levels 0.05, 0.25, 0.5, 0.75 and 0.95) are exact
  and computed from it, as for a histogram of integers. A source with more distinct lengths than
  the plan allowed (`max_lengths`) fails with `scan_mismatch`.

**`structure_variants`**: the sets of keys of the objects of a field, or of the records.

```json
{
  "kind": "structure_variants",
  "accuracy": "exact",
  "objects": 500, "keys": 4, "always": 2,
  "key_names": ["id", "tags", "orders", "addr"],
  "key_names_truncated": false,
  "distinct": 4, "complete": true, "untracked": 0,
  "listed": [
    {"count": 268, "keys": 4, "absent": [], "absent_total": 0},
    {"count": 146, "keys": 3, "absent": ["addr"], "absent_total": 1}
  ],
  "other_objects": 0
}
```

- The records of a JSON source are the field `$` of the plan, which the scan holds as no
  field: `candidate.field` is `"$"`, its display `$`. `objects` is checked against the
  occurrences of the object in the scan (`native_types.object`, or `record_count` for `$`), and
  the objects that hold each key against the `presence.present` of the field below it.
- A set is the keys the scan named below the object (`keys` of them in all, the first
  `max_keys` named in `key_names` in order of the scan, with `key_names_truncated`). `listed`
  holds at most `max_listed` sets, the most frequent first (ties in order of first appearance).
  `keys` is the number of keys the set has, `absent` the keys of `key_names` it lacks and
  `absent_total` how many keys it lacks in all. `always` counts the keys every object has.
- At most `max_variants` sets are tracked, each counted exactly from its first object.
  `complete` is false when an object had another set: `distinct` is then a lower bound,
  `untracked` counts those objects, and `other_objects` the objects of the tracked sets that
  are not listed.

**`text_profile`**: the words, lines and digits of the texts of a field.

```json
{
  "kind": "text_profile",
  "accuracy": "exact",
  "texts": 3000, "characters": 610108, "words": 117718,
  "min_words": 15, "max_words": 63, "mean_words": 39.24,
  "lines": 4023, "max_lines": 2, "multi_line": 1023,
  "digits": 117285, "digit_share": 0.192,
  "word_buckets": [{"low": 8, "high": 15, "count": 35}],
  "line_buckets": [{"low": 1, "high": 1, "count": 1977}],
  "digit_buckets": [0, 87, 1640, 1209, 64, 0, 0, 0, 0, 0, 0]
}
```

- `texts` is the content strings of the field and is checked against the scan. The texts are
  the original ones (design 21): a word is what `str.split` cuts, a line what `str.splitlines`
  cuts, a digit a decimal digit of Unicode (category `Nd`). A bucket counts the texts whose
  number is from `low` to `high` (0; 1; 2 to 3; 4 to 7; and so on), from the first that holds
  a text to the last. `digit_buckets` has 11 counts: the texts without a digit, then those
  whose digits are up to a tenth of their characters, up to two tenths, and so on up to all.

**`character_profile`**: the exact character map of a field.

```json
{
  "kind": "character_profile",
  "basis": "exact",
  "values": 3000, "characters": 21089, "distinct": 37,
  "top": [{"char": "e", "codepoint": 101, "occurrence_count": 2760}],
  "scripts": [{"name": "LATIN", "occurrence_count": 20860}],
  "categories": [{"name": "Ll", "occurrence_count": 17665}],
  "ends_uppercase": 0, "ends_lowercase": 3000, "title_case": 2967,
  "with_emoji": 0, "emoji_sequences": 0, "emoji": []
}
```

- The members are those of the [character map](format.md#character-map) of the scan, counted
  on every original string instead of the samples. `values` is the content strings of the
  field and is checked against the scan. A field with more distinct characters or emoji than the
  tables hold is `limited` (reason `character_limit`) and has no result. The scan answers alone when it
  lists every distinct value, so the analysis is not run then.

**`fingerprint_distinct`**: the distinct values of a field told apart by a fingerprint.

```json
{
  "kind": "fingerprint_distinct",
  "accuracy": "fingerprint_based",
  "algorithm": "blake2b", "bits": 128,
  "values": 3000, "distinct": 300, "redundant": 2700, "unique": false,
  "repeated": 299, "repeated_occurrences": 2999,
  "listed": [{"digest": "992bd5b9...", "count": 21}],
  "truncated": true
}
```

- A value is known by the digest the scan gives its long texts: BLAKE2b over the native type,
  a NUL byte and the text in UTF-8, 128 bits, in hexadecimal. `values` is checked against the
  scan, and `distinct` against its cardinality when it counted it, or its proven lower bound.
  `repeated` counts the distinct values found more than once, `repeated_occurrences` their
  occurrences, and `listed` the `max_listed` found most often (then by digest), `truncated`
  telling that more exist. When the memory of the plan is not enough the result is
  `distinct_limited` (status `limited`, reason `memory_budget`).

**`sensitive_forms`**: the masks and classes of a masked field, without a value.

```json
{
  "kind": "sensitive_forms",
  "accuracy": "exact",
  "exposure": "mask",
  "values": 4000, "forms": 10, "complete": true, "untracked": 0,
  "min_count": 5,
  "listed": [{"form": "999.999.9.999", "count": 690}],
  "other_forms": 0, "other_values": 0,
  "classes": {
    "detector": "ip_address",
    "listed": [{"form": "ipv4_private", "count": 2700}],
    "other": 8, "unclassified": 0
  }
}
```

- A `form` is the mask the exposure gate gives the analytical text of a value (design
  12.8), and a class one of a closed list: for `ip_address` the version and the range
  (`ipv4_public`, `ipv4_private`, `ipv4_loopback`, `ipv4_link_local`, `ipv4_shared`,
  `ipv4_multicast`, `ipv4_unspecified`, `ipv4_reserved` and the same for `ipv6`), for `phone`
  `fr_01` to `fr_09`, `nanp_geographic`, `nanp_toll_free` and `nanp_premium`. `classes` is
  absent for a field no such detector reads, and `unclassified` counts the values the detector
  did not read, native numbers included.
- No count below `min_count` is written: the masks and classes with fewer values are summed up
  in `other_forms`, `other_values` and `other`, and so is the least frequent one listed when
  the sum would otherwise be below `min_count`. `listed` holds at most `max_listed` masks, the
  most frequent first (ties by text). `forms` counts the distinct masks, a lower bound when
  `complete` is false: at most `max_tracked` masks are tracked, each counted exactly from its
  first occurrence, and `untracked` values have another one (they are part of `other_values`).
- `values` is checked against the scan, and every mask the scan lists against its count, so a
  masked field whose frequencies differ fails with `scan_mismatch`. A field whose exposure is
  `hide` has no such result, and the document never holds a value of the field.

The result `distinct` of the analyzer `exact_distinct` may also be that of a field whose
exposure is `mask` or `hide`, when `deep.sensitive.enabled` is true (the default is false); the
parameter `exposure` of the analysis then names it. It holds
the same two numbers.

## Key and reuse

The `key` of an analysis is a digest of the scan it stands on, the analyzer and
its version, the field (and its partner, for a pair or a table), the method with its effective parameters (the number of
bins and the strategy are among them, for a table the feature, its classes and the thresholds of its
rules, and for an extraction the detector, `max_groups`, `max_values` and the bins, for the residual values the sources and
the settings of `deep.residuals`, for the repeated values those of `deep.duplicates`, for the numbers by category the categories kept, the bins and their strategy, for a column followed by position whether its values are followed and how many are listed, for the missing values together the number of columns and the partners listed, for the lengths of the arrays the most lengths counted, for the sets of keys the most sets tracked, listed and named, for the texts the texts listed, for the sensitive columns the floor, the masks listed and tracked and the class detector, and for a count of a masked or hidden field its exposure) and the domain of the values. It does not
hold budgets, estimates or presentation. A run keeps the complete analyses of the
stored document whose key it would give again, and computes the others. A document
whose `base` is not the current scan's matches none of its keys, and is made
again; so is a file of another format or revision, or one that does not validate.

## JSON Schema

The package contains the JSON Schema of the document,
`tabalyst/schemas/tabalyst.scan.deep.schema.json`, generated from the same models
as the writer. It describes what a reader accepts.

## Changelog

### Version 0.2.0, revision 4

The result `duplicate_rows` of the analyzer `duplicate_rows_count` (the extra copies of whole rows of a
CSV file, counted with the engine of Dedup in a reading of its own, `complete` or `limited`) and the
settings member `deep.copies` (`memory_mb`, `disk_mb`, `max_rows`). The plan names the analysis
`duplicate_rows_count:<dataset>:$`. A document of revision 3 is made again.

### Version 0.2.0, revision 3 (Tabalyst 0.7.0)

The result `date_order` of the analyzer `date_order` (the order of two dates of a record), the
settings member `deep.date_order` and the plan block `relations.orders` (the exploration of the pairs
of date columns on the row sample).
The result `character_profile` of the analyzer `character_profile` (the exact character map of a field).
The result `pattern_counts` follows the hierarchy of the scan: `families` (each with
its `patterns` and their `nodes`, the `distinct` values of each with their accuracy,
the `tables` of its facets and its `new_variants`), `unknown_structure` and
`algorithm_version` replace `candidates`, `other` and `overlaps`. The settings have the
member `deep.patterns` (`table_bytes`, `distinct_bytes`), and the plan parameters of
`pattern_validation` the members `nodes`, `facets`, `table_bytes`, `distinct_bytes`,
`grammar_version`, `algorithm_version` and `discovery_sha256`: the last three say which
discovery made the patterns the result counts, so a result is reused only for the same
one. A document of revision 2 is made again.

### Version 0.2.0, revision 2

The result `pearson` has the line of the pair (`slope`, `intercept`, `r_squared`) and the rank
correlation `rank` (`spearman_binned`, an estimate with certain bounds); the analyzer
`pearson_correlation` is at version 2 and the settings have `deep.pearson.rank_bins`. The result
`crosstab` has the feature kind `value` (a category against another category), `exceptions.complete`
and the member `provided_rules`; the settings have `deep.crosstab.max_exception_cells`. A request
can carry `rules`, which are part of the key of the table.

The results `periods` and `datetime_parts` may hold a `resolution` (the ambiguous dates read by the evidence of the
column, `deep.datetime.infer_order`), and the plan parameter `date_order`. The results `numeric_shape` of the analyzer `numeric_shape` (asymmetry, kurtosis, outliers of Tukey,
decimals, logarithmic and equal-count histograms) and `datetime_parts` of the analyzer
`datetime_parts` (year-month, weekday and hour, dates after a bound, ambiguous
dates under each reading, invalid dates by reason). `strategy` of a `bins` result may be `log`. The
settings have the members `deep.shape` and `deep.datetime`.

The results `position_drift` of the analyzer `position_drift` (the records, values and missing values of
each tenth of the file, the values followed by slice) and `missing_matrix` of the analyzer `missing_matrix`
(the records where a column lacks a value together with each other column). The settings have the members
`deep.drift` and `deep.missing`.

The results `array_profile` of the analyzer `array_profile` (the lengths of the arrays of a JSON field),
`structure_variants` of `structure_variants` (the sets of keys of the objects, and of the records under the
field `$`), `text_profile` of `text_profile` (the words, lines and digits of long texts), `fingerprint_distinct`
of `fingerprint_distinct` (the distinct values by 128-bit fingerprint, with the `fingerprint_based` accuracy)
and `sensitive_forms` of `sensitive_forms` (the masks and classes of a masked field, with a floor). The
analyzer `exact_distinct` also runs on a masked or hidden field (decision O61), with the plan parameter
`exposure`. The settings have the members `deep.arrays`, `deep.structure`, `deep.texts` and `deep.sensitive`.

The result `category_stats` of the analyzer `category_stats`: the count, extremes, sum, mean, spread,
signs and histogram of a number for each value of a category, with estimated quantiles and the share
of the variance the categories explain. The settings have the member `deep.stats`, and the plan the
members `relations.stats` and `budgets.automatic_stats`.

The results `residual_values` of the analyzer `residual_values` (the values that patterns and
detectors leave out, and the patterns over every occurrence) and `duplicates` and
`duplicates_limited` of the analyzer `duplicates_report` (the repeated values of an identifier or of a
combination of two columns). The settings have the members `deep.residuals` and `deep.duplicates`.

The result `measures` of the analyzer `measure_extraction`: the numbers of the
amounts, percentages and quantities with a unit, for the whole field and for each
currency or unit, and the currencies or units as an enumeration. `bounds_source`
of a `bins` result may be `grid`. The settings have the member `deep.measures`
(`max_groups`, `max_values`). A document of revision 1 is made again. The result
may hold `resolved` and a `resolution` (the ambiguous numbers read by the evidence
of the column), and the plan parameter `number_convention`.

### Version 0.2.0, revision 1

First revision of the format, introduced with `tabalyst scan --deep`: `base`,
`settings`, `plan`, `run` and `analyses`, with the results `dense_counts`, `bins`,
`lengths`, `distinct`, `distinct_limited` and `frequencies`, and the `original`
domain. Members without a value are left out rather than written as `null`.
The results `pattern_counts` and `periods` were added with the executors of
`pattern_validation` and `temporal_distribution`, and the domain `original` is also
that of `pattern_validation`, without a new revision: the format is not published yet.
The result `pearson`, the `partner` member of an analysis and the members `partner`,
`exploration` and `relations` of the plan (see [Plan](plan.md#pairs-of-columns)) came with
`pearson_correlation`, also without a new revision. So did the result `crosstab`, the domain
`mixed`, and `relations.tables`, the `feature` of a request and the candidates of
`category_crosstab` in the plan (see [Plan](plan.md#tables-of-a-category-against-a-feature)),
with the members `deep.crosstab` of the settings.
