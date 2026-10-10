---
title: Read exact, estimated and limited results
description: Explains how Tabalyst qualifies every figure as exact, estimated, sample, limited or fingerprint-based, and how the distinct sample, the row sample and the smart sample differ.
---

Every figure of a Tabalyst document says how it was obtained. Read that word
before you use the number: it tells you whether you can quote it, bound it or
only use it as a hint. This page lists the words, where they appear in the JSON
and in the report, and the three kinds of samples a Tabalyst document can hold.

## The five qualities of a figure

The report prints one of five labels next to a figure. The JSON carries the same
information in `status` and `accuracy` members.

| Label in the report | In the JSON | What you can say |
| --- | --- | --- |
| exact | `status: "complete"`, `accuracy: "exact"` or none | The figure was counted on every value of the file, for the population it names. |
| estimated | `accuracy: "estimated"`, with `method` and `relative_standard_error` | A statistical estimate from a sample of the distinct values, with an expected error. Never quote it as a count. |
| sample | `accuracy: "sample"` | Counted on a sample, not on the whole file. It describes the sample only. |
| at least | `status: "limited"` or `accuracy: "lower_bound"`, with `lower_bound` | A configured limit stopped the measure. The real figure is at least this, and `upper_bound` bounds it above when it is known. |
| not computed | `status: "not_applicable"`, `"disabled"` or `"failed"` | The scan did not produce it, and `reason` says why. A missing figure is never zero. |

A scan can be `complete` while some of its measures are `limited`: the status of
the scan is about records, the envelope of a measure is about that measure. The
[scan format](format.md#measure-envelopes) describes each envelope.

## Exact is exact for a named population

An exact count is exact for what it counts, and the JSON names it:

- Values are counted in the **original domain** (`00123`, `123` and ` 123 ` are
  three values) or in the **analytical domain** (after the normalization stages).
  `values.cardinality` is original. `values.frequencies` is analytical.
- `scope` and `population` say which records were counted. A count over the
  interior rows of a dataset is not a count over the whole dataset.
- `identity_accuracy` says how two values were told apart. `exact` means that
  equal values were compared whole. `fingerprint_based` means that two texts are
  the same entry when their 128-bit digests are equal, which is how long texts
  are tracked. It is a fingerprint, not a comparison of the full texts.
- `count_accuracy` is `exact` when a count started at the first occurrence of a
  value. For a length that entered tracking late it is `partial`, and
  `tracking_started_at_occurrence` says where the count began.

## What the second pass changes

The first pass (`tabalyst scan`) never reads the file twice, so a high-cardinality
column ends as `limited` or `estimated`. The [second pass](deep.md) reads the
source again and can replace such a figure by an exact one: the exact distinct
count of the original values, exact frequencies, exact histograms and medians,
patterns counted on every occurrence, dates per period, correlations and tables
of a category against a feature.

Its results sit in their own document, `<stem>.deep.json`, and in the
`analyses` member of a report. They keep their own words: `exact`,
`exact_counts`, `lower_bound` for a distinct count that a limit stopped, and for
a median read from bins `estimated` with a `lower` and an `upper` bound that
always contain the true value.

An estimate is replaced, never refined: the Scan keeps its estimate, and the
second pass adds the exact figure beside it.

## Three kinds of samples

A Tabalyst document can hold three different things called a sample. They answer
different questions, and none of them is a uniform sample of the file.

| | Sample of distinct values | Row sample | Smart sample |
| --- | --- | --- | --- |
| Where | `values.samples` of a field, in the [scan format](format.md#distinct-values-and-samples) | `records.sample` of a dataset, in the [scan format](format.md#row-sample) | `<stem>.sample.json` and its CSV file, in the [sample format](../sample/format.md) |
| What it holds | Distinct original values of one field, each with its exact count over the whole field | Whole rows, with the cells of every projected field | Whole rows of the source, written as a smaller CSV file |
| How it is chosen | `all` the distinct values, or the `bottom_k` of smallest priority from a stable hash of the value | The first and last rows, and a reproducible choice of rows between them | A greedy cover of the targets of a plan, from a bounded pool of candidate rows |
| Depends on | The set of distinct values and `k` only, not on the order of the records | The position of a record and the seed, never on its content | The Scan, the second pass when it is current, the requested size and the seed |
| Good for | Seeing real values, inferring patterns, exact counts per listed value | Relating the values of two fields, previews, exploring pairs | Testing and reviewing a smaller file that still shows every case the plan knows |
| Not for | A ranking (the most frequent value can be absent) or the counts of the unlisted values | Estimating the whole dataset: the middle is drawn from the interior only | Estimating proportions: rare cases are chosen on purpose |

### The sample of distinct values

Its counts are exact for the whole field, because each value was counted from
its first occurrence. What is sampled is the list, not the counts. When the
field has no more distinct values than `scan.limits.max_samples`, the sample
lists all of them. Beyond that it keeps the `k` of smallest priority, and the
cardinality of the field is then an `estimate` (KMV) with a known error, held
between its certain bounds.

### The row sample

It exists so that a later analysis can relate two fields on the same rows. A
report keeps fewer rows than the scan and says so with `kept` below `of`. The
middle is drawn from the interior (`population.scope` is `interior_rows`), so do
not add the edges to an estimate over the whole file.

### The smart sample

A [smart sample](../sample/index.md) is a CSV file chosen to cover a catalog of
targets: the values of low-cardinality columns, patterns, extremes, dates, quality
observations and relation exceptions. Its report says what it covers and what it
does not:

- `coverage.scope` is `target_catalog`. The coverage is that of the targets of the
  plan, not of every phenomenon of the data. A case that no target describes can
  be missing, and the report cannot know it.
- The proportions of the sample are not those of the file. Do not estimate the
  population from it.
- The rows come from a greedy cover of a bounded pool. The coverage is measured
  and no optimum is promised.
- Each target whose rows the plan counted exactly is checked while reading
  (`verification`). A difference means that the test and the Scan disagree.

## Rules of thumb

1. Quote a figure as a count only when its label says exact, and quote its
   population with it.
2. Treat `estimated` as an order of magnitude with a stated error, and `at least`
   as a floor.
3. Never read a missing figure as zero. Check `reason`.
4. Use a sample to look at values, never to infer the proportions of the file.
5. When an exact figure matters, ask for the [second pass](deep.md)
   (`tabalyst scan --deep`) and read its document.
