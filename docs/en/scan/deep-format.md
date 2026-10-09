---
title: Second pass format
description: Structure of the deep.json document written by tabalyst scan --deep, with its identity, plan, run, analyses and results, and the changelog of its format revisions.
---

`tabalyst scan --deep` and `tabalyst report` write a JSON document beside the scan: `deep.json` next
to a stored `scan.json`, or `<stem>.deep.json` next to a `<stem>.scan.json`. This
page describes format `tabalyst.scan.deep`, version `0.2.0`, revision `1`. The
format is **experimental**: it can change incompatibly between releases. Always
check `format`, `format_version` and `format_revision` first. Tabalyst does not
migrate a document of another revision; it makes it again. See [Add histograms and
exact medians](deep.md) for what the command does.

## Top level

```json
{
  "format": "tabalyst.scan.deep",
  "format_version": "0.2.0",
  "format_revision": 1,
  "status": "complete",
  "base": {
    "format_revision": 2,
    "engine_version": "0.6.2",
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
"sample_quantile"`). When the sample cannot place the bounds, `strategy` is
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

**`pattern_counts`**: the inferred patterns of a field counted on every value of
the file, in the original domain.

```json
{
  "kind": "pattern_counts",
  "accuracy": "exact",
  "computed_from": "source",
  "grammar_version": 1,
  "values": 3000,
  "matched": 2990,
  "candidates": [{"id": "p1", "render": "XX9999'A'", "occurrences": 2100}],
  "other": 10,
  "excluded": {"non_string": 0, "too_long": 0, "too_complex": 0},
  "overlaps": [{"patterns": ["p1", "p2"], "occurrences": 12}]
}
```

`matched` is the sum of the `occurrences` of the candidates, which are those of
the scan (`derived.patterns`) in the same order. They add up: `matched + other +
excluded = values`, with `excluded` the sum of its three members. An occurrence
counts for one candidate, the most specific that reads it; `overlaps` says how many
occurrences several candidates read. `computed_from` is `samples` when the exact
counts of the scan were enough, `source` when the file was read.

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

## Key and reuse

The `key` of an analysis is a digest of the scan it stands on, the analyzer and
its version, the field, the method with its effective parameters (the number of
bins and the strategy are among them) and the domain of the values. It does not
hold budgets, estimates or presentation. A run keeps the complete analyses of the
stored document whose key it would give again, and computes the others. A document
whose `base` is not the current scan's matches none of its keys, and is made
again; so is a file of another format or revision, or one that does not validate.

## JSON Schema

The package contains the JSON Schema of the document,
`tabalyst/schemas/tabalyst.scan.deep.schema.json`, generated from the same models
as the writer. It describes what a reader accepts.

## Changelog

### Version 0.2.0, revision 1

First revision of the format, introduced with `tabalyst scan --deep`: `base`,
`settings`, `plan`, `run` and `analyses`, with the results `dense_counts`, `bins`,
`lengths`, `distinct`, `distinct_limited` and `frequencies`, and the `original`
domain. Members without a value are left out rather than written as `null`.
The results `pattern_counts` and `periods` were added with the executors of
`pattern_validation` and `temporal_distribution`, and the domain `original` is also
that of `pattern_validation`, without a new revision: the format is not published yet.
